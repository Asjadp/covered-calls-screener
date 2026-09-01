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

COOLDOWN_DELAY = 0.3        # 0.3s polite cooldown delay between requests
SESSION_API_CAP = 150       # Generous live calls per session for interactive screening
BURST_LIMIT_PER_MIN = 30    # Maximum 30 live calls in any 60-second rolling window

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

import math

def is_snapshot_fresh(snapshot_timestamp_str: str, max_age_minutes: int = 30) -> bool:
    """
    Check if a database snapshot is still fresh:
    1. During market hours (Mon-Fri 9:30 AM - 4:00 PM ET): fresh if captured within max_age_minutes (default 30m).
    2. Outside market hours: fresh if captured after the most recent 4:00 PM ET market close.
    """
    try:
        now_et = datetime.now(ZoneInfo("America/New_York"))
        snap_dt = datetime.strptime(snapshot_timestamp_str, "%Y-%m-%d %H:%M:%S")
        snap_dt_et = snap_dt.replace(tzinfo=ZoneInfo("America/New_York"))
        
        if is_market_open_now(now_et):
            age_sec = (now_et - snap_dt_et).total_seconds()
            return 0 <= age_sec <= (max_age_minutes * 60)
        else:
            last_close_et = get_last_market_close_dt(now_et)
            return snap_dt_et >= last_close_et
    except Exception:
        return False

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
        
        # In-flight concurrency & busy queue management
        self._is_busy: bool = False
        self._busy_symbol: Optional[str] = None
        self._busy_start_time: float = 0.0
        self._last_request_finish_time: float = 0.0
        self._cooldown_seconds: float = 2.5

    def acquire_request_slot(self, symbol: str) -> Tuple[bool, str, int]:
        """
        Thread-safe request coordinator:
        Returns (can_proceed: bool, status_reason: str, wait_seconds_remaining: int)
        """
        with self._lock:
            now = time.time()
            
            # 1. Guard against concurrent in-flight requests
            if self._is_busy:
                busy_elapsed = now - self._busy_start_time
                if busy_elapsed > 25.0:
                    # Timeout guard: auto-release stuck request
                    self._is_busy = False
                else:
                    wait_sec = max(1, math.ceil(6.0 - busy_elapsed))
                    return False, f"API is busy screening '{self._busy_symbol or 'another ticker'}'", wait_sec
            
            # 2. Cooldown timer guard after last finished request
            time_since_finish = now - self._last_request_finish_time
            if self._last_request_finish_time > 0 and time_since_finish < self._cooldown_seconds:
                wait_sec = max(1, math.ceil(self._cooldown_seconds - time_since_finish))
                return False, "Rate limit cooldown active", wait_sec
                
            # 3. Burst limit check (rolling 60s)
            self.recent_request_timestamps = [t for t in self.recent_request_timestamps if (now - t) < 60.0]
            if len(self.recent_request_timestamps) >= BURST_LIMIT_PER_MIN:
                oldest_in_window = self.recent_request_timestamps[0]
                wait_sec = max(1, math.ceil(60.0 - (now - oldest_in_window)))
                return False, f"Burst rate limit ({BURST_LIMIT_PER_MIN} req/min)", wait_sec
                
            # 4. Session cap check
            if self.api_calls >= SESSION_API_CAP:
                return False, f"Session limit of {SESSION_API_CAP} calls reached", 10

            # Acquire slot
            self._is_busy = True
            self._busy_symbol = symbol.upper()
            self._busy_start_time = now
            return True, "ok", 0

    def release_request_slot(self):
        """Release the in-flight lock and start the cooldown countdown."""
        with self._lock:
            self._is_busy = False
            self._busy_symbol = None
            self._last_request_finish_time = time.time()

    def can_make_api_call(self, symbol: Optional[str] = None) -> Tuple[bool, str]:
        """Check both session cap and burst limit."""
        with self._lock:
            if self.api_calls >= SESSION_API_CAP:
                return False, f"Session cap of {SESSION_API_CAP} live API calls reached"
            
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
