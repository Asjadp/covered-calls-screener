"""
Background API Telemetry & Rate Limiter Engine
---------------------------------------------
Silent background engine enforcing:
- Doubled Cooldown Delay: 1.2s between calls
- Burst Limiter: Maximum 5 live requests per 60-second rolling window
- Session Cap: Maximum 10 live calls per session
"""

import time
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import threading

COOLDOWN_DELAY = 1.2        # 1.2s cooldown delay between requests
SESSION_API_CAP = 10        # Maximum 10 live calls per session
BURST_LIMIT_PER_MIN = 5     # Maximum 5 live calls in any 60-second rolling window

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
