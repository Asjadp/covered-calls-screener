"""
Background API Telemetry, Market-Hours Caching & Rate Limiter Engine
-------------------------------------------------------------------
Enforces:
1. Market-Closed Smart Cache: Once closing/after-hours data is captured for a ticker,
   NEVER send a second API request until next market open at 9:30 AM ET.
2. In-Memory 15-Minute Cache TTL during market hours.
3. Burst Limiter: Maximum 5 live calls per 60-second rolling window.
4. Session Cap: Maximum 10 live calls per session.
5. Cooldown Delay: 1.2s between consecutive requests.
"""

import time
from datetime import datetime, time as dtime, timedelta
from typing import Dict, Any, List, Optional, Tuple
import threading
from zoneinfo import ZoneInfo

COOLDOWN_DELAY = 1.2        # 1.2s cooldown delay between requests
SESSION_API_CAP = 10        # Maximum 10 live calls per session
BURST_LIMIT_PER_MIN = 5     # Maximum 5 live calls in any 60-second rolling window

def is_market_open_now(now_et: Optional[datetime] = None) -> bool:
    """Check if US equity options market is currently open (Mon-Fri 9:30 AM - 4:00 PM ET)."""
    if now_et is None:
        now_et = datetime.now(ZoneInfo("America/New_York"))
    weekday = now_et.weekday()
    if weekday >= 5:  # Saturday or Sunday
        return False
    return dtime(9, 30) <= now_et.time() < dtime(16, 0)

def get_last_market_close_dt(now_et: datetime) -> datetime:
    """Return the datetime of the most recent market close (4:00 PM ET)."""
    weekday = now_et.weekday()
    if weekday == 5:  # Saturday
        days_back = 1
        return (now_et - timedelta(days=days_back)).replace(hour=16, minute=0, second=0, microsecond=0)
    elif weekday == 6:  # Sunday
        days_back = 2
        return (now_et - timedelta(days=days_back)).replace(hour=16, minute=0, second=0, microsecond=0)
    elif weekday == 0 and now_et.time() < dtime(9, 30):  # Monday pre-market
        days_back = 3
        return (now_et - timedelta(days=days_back)).replace(hour=16, minute=0, second=0, microsecond=0)
    else:  # Monday through Friday
        if now_et.time() >= dtime(16, 0):
            return now_et.replace(hour=16, minute=0, second=0, microsecond=0)
        else:
            return (now_et - timedelta(days=1)).replace(hour=16, minute=0, second=0, microsecond=0)

def is_snapshot_frozen_after_market_close(snapshot_timestamp_str: str) -> bool:
    """
    Returns True if:
    1. The market is currently closed, AND
    2. The snapshot was captured AFTER the most recent market close.
    When True, option settlement prices are 100% frozen and 0 API calls should be made.
    """
    try:
        now_et = datetime.now(ZoneInfo("America/New_York"))
        if is_market_open_now(now_et):
            return False  # Market is currently trading
        
        last_close_et = get_last_market_close_dt(now_et)
        snap_dt = datetime.strptime(snapshot_timestamp_str, "%Y-%m-%d %H:%M:%S")
        snap_dt_et = snap_dt.replace(tzinfo=ZoneInfo("America/New_York"))
        
        return snap_dt_et >= last_close_et
    except Exception:
        return False

class APITelemetry:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(APITelemetry, cls).__new__(cls)
                cls._instance._init_state()
            return cls._instance

    def _init_state(self):
        self.api_calls = 0
        self.api_success = 0
        self.api_errors = 0
        self.cache_hits = 0
        self.total_latency_ms = 0.0
        self.recent_logs: List[Dict[str, Any]] = []
        self.recent_request_timestamps: List[float] = []

    def can_make_api_call(self) -> Tuple[bool, str]:
        """Check both session cap and 5 req/min rolling burst limit."""
        with self._lock:
            if self.api_calls >= SESSION_API_CAP:
                return False, f"Session cap of {SESSION_API_CAP} live API calls reached"
            
            # Clean up timestamps older than 60 seconds
            now = time.time()
            self.recent_request_timestamps = [t for t in self.recent_request_timestamps if (now - t) < 60.0]
            if len(self.recent_request_timestamps) >= BURST_LIMIT_PER_MIN:
                return False, f"Burst rate limit reached ({BURST_LIMIT_PER_MIN} live requests/min)"
            
            return True, ""

    def apply_throttle(self):
        """Pause 1.2s between requests to respect rate limits."""
        time.sleep(COOLDOWN_DELAY)

    def record_api_call(self, endpoint: str, symbol: str, success: bool, latency_ms: float, error: Optional[str] = None):
        """Record an outbound API request to Yahoo Finance."""
        with self._lock:
            self.api_calls += 1
            now = time.time()
            self.recent_request_timestamps.append(now)
            self.total_latency_ms += latency_ms
            if success:
                self.api_success += 1
                status_str = "SUCCESS (200)"
            else:
                self.api_errors += 1
                status_str = f"ERROR ({error or 'Rate Limited'})"

            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol.upper(),
                "endpoint": endpoint,
                "status": status_str,
                "latency_ms": round(latency_ms, 1),
                "is_cache": False
            }
            self.recent_logs.insert(0, log_entry)
            if len(self.recent_logs) > 30:
                self.recent_logs.pop()

    def record_cache_hit(self, symbol: str, source: str = "Database"):
        """Record a request served from local DB/cache (0 external API calls)."""
        with self._lock:
            self.cache_hits += 1
            log_entry = {
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "symbol": symbol.upper(),
                "endpoint": f"Cached ({source})",
                "status": "CACHE HIT (0 API Calls)",
                "latency_ms": 1.0,
                "is_cache": True
            }
            self.recent_logs.insert(0, log_entry)
            if len(self.recent_logs) > 30:
                self.recent_logs.pop()

    def get_metrics(self) -> Dict[str, Any]:
        """Return real-time API telemetry metrics."""
        with self._lock:
            total_reqs = self.api_calls + self.cache_hits
            cache_rate = (self.cache_hits / total_reqs * 100.0) if total_reqs > 0 else 100.0
            avg_latency = (self.total_latency_ms / self.api_calls) if self.api_calls > 0 else 0.0

            return {
                "total_requests": total_reqs,
                "api_calls": self.api_calls,
                "api_success": self.api_success,
                "api_errors": self.api_errors,
                "cache_hits": self.cache_hits,
                "cache_hit_rate_pct": round(cache_rate, 1),
                "avg_latency_ms": round(avg_latency, 1),
                "recent_logs": list(self.recent_logs),
                "cap_remaining": max(0, SESSION_API_CAP - self.api_calls),
                "session_cap": SESSION_API_CAP,
                "burst_limit": BURST_LIMIT_PER_MIN,
                "cooldown_sec": COOLDOWN_DELAY
            }

# Global Singleton Instance
api_monitor = APITelemetry()
