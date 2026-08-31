"""
API Monitor & Rate Limiter Telemetry Engine
-------------------------------------------
Tracks outbound requests to Yahoo Finance / yfinance API, counts success/error responses,
monitors cache efficiency, and enforces production rate limits to prevent IP throttling.
"""

import time
from datetime import datetime
from typing import Dict, Any, List, Optional
import threading

# Optimal production constants for Yahoo Finance
RECOMMENDED_REQUEST_DELAY = 0.6  # 600ms delay between requests prevents 429 throttles
DEFAULT_SESSION_API_CAP = 40     # Maximum live API calls allowed per session

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
        self.cooldown_delay = RECOMMENDED_REQUEST_DELAY
        self.session_api_cap = DEFAULT_SESSION_API_CAP

    def record_api_call(self, endpoint: str, symbol: str, success: bool, latency_ms: float, error: Optional[str] = None):
        """Record an outbound API request to Yahoo Finance."""
        with self._lock:
            self.api_calls += 1
            self.total_latency_ms += latency_ms
            if success:
                self.api_success += 1
                status_str = "SUCCESS (200)"
            else:
                self.api_errors += 1
                status_str = f"ERROR ({error or 'Rate Limited'})"

            log_entry = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "symbol": symbol.upper(),
                "endpoint": endpoint,
                "status": status_str,
                "latency_ms": round(latency_ms, 1),
                "is_cache": False
            }
            self.recent_logs.insert(0, log_entry)
            if len(self.recent_logs) > 20:
                self.recent_logs.pop()

    def record_cache_hit(self, symbol: str, source: str = "Database"):
        """Record a request served from local DB/cache (0 external API calls)."""
        with self._lock:
            self.cache_hits += 1
            log_entry = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "symbol": symbol.upper(),
                "endpoint": f"Cached ({source})",
                "status": "CACHE HIT (0 API Calls)",
                "latency_ms": 1.2,
                "is_cache": True
            }
            self.recent_logs.insert(0, log_entry)
            if len(self.recent_logs) > 20:
                self.recent_logs.pop()

    def get_metrics(self) -> Dict[str, Any]:
        """Return comprehensive real-time API telemetry metrics."""
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
                "cap_remaining": max(0, self.session_api_cap - self.api_calls),
                "cooldown_delay": self.cooldown_delay,
                "session_cap": self.session_api_cap
            }

    def can_make_api_call(self) -> bool:
        """Check if session is within rate limit cap."""
        with self._lock:
            return self.api_calls < self.session_api_cap

    def apply_throttle(self):
        """Pause between requests to respect Yahoo Finance rate limits."""
        if self.cooldown_delay > 0:
            time.sleep(self.cooldown_delay)

    def reset_stats(self):
        """Reset telemetry counters."""
        with self._lock:
            self._init_state()

# Global Singleton Instance
api_monitor = APITelemetry()
