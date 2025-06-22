"""
API rate limiting management for Polygon.io.
"""

# polygon/rate_limiter.py - Rate limiting for Polygon API requests
"""
Rate limiting module for managing API quotas and request throttling.
Implements intelligent rate limiting with queuing and backoff strategies.
"""

import time
import asyncio
import threading
from collections import deque
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable, Any, Tuple
import json
from pathlib import Path
from dataclasses import dataclass, field
from queue import PriorityQueue, Queue
import math

from .config import get_config, POLYGON_TIMEZONE
from .exceptions import PolygonRateLimitError, PolygonConfigurationError


@dataclass
class RateLimitStats:
    """
    [CLASS SUMMARY]
    Purpose: Container for rate limit statistics
    Attributes:
        - requests_per_minute: Current requests in the last minute
        - requests_today: Total requests today
        - last_reset_time: When daily counter was reset
        - total_requests: All-time request count
        - rate_limit_hits: Number of times rate limited
        - average_response_time: Average API response time
    """
    requests_per_minute: int = 0
    requests_today: int = 0
    last_reset_time: datetime = field(default_factory=lambda: datetime.now(POLYGON_TIMEZONE))
    total_requests: int = 0
    rate_limit_hits: int = 0
    average_response_time: float = 0.0
    total_wait_time: float = 0.0
    successful_requests: int = 0
    failed_requests: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary"""
        return {
            'requests_per_minute': self.requests_per_minute,
            'requests_today': self.requests_today,
            'last_reset_time': self.last_reset_time.isoformat(),
            'total_requests': self.total_requests,
            'rate_limit_hits': self.rate_limit_hits,
            'average_response_time': round(self.average_response_time, 3),
            'total_wait_time': round(self.total_wait_time, 3),
            'successful_requests': self.successful_requests,
            'failed_requests': self.failed_requests,
            'success_rate': round(self.successful_requests / max(self.total_requests, 1) * 100, 2)
        }


@dataclass
class QueuedRequest:
    """
    [CLASS SUMMARY]
    Purpose: Container for queued API requests
    Attributes:
        - priority: Request priority (lower = higher priority)
        - timestamp: When request was queued
        - callback: Function to execute
        - args: Positional arguments
        - kwargs: Keyword arguments
        - retry_count: Number of retries
    """
    priority: int
    timestamp: datetime
    callback: Callable
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)
    retry_count: int = 0
    
    def __lt__(self, other):
        """Compare by priority for queue ordering"""
        return self.priority < other.priority


class RateLimiter:
    """
    [CLASS SUMMARY]
    Purpose: Manage API rate limiting and request throttling
    Responsibilities:
        - Track request rates per minute and day
        - Queue requests when approaching limits
        - Implement exponential backoff
        - Provide usage statistics
        - Handle multiple rate limit tiers
    Usage:
        limiter = RateLimiter()
        limiter.check_and_wait()  # Will wait if needed
        # Make API call
        limiter.record_request()
    """
    
    def __init__(self, config=None):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize rate limiter with configuration
        Parameters:
            - config (PolygonConfig, optional): Configuration instance
        Example: limiter = RateLimiter()
        """
        self.config = config or get_config()
        self.logger = self.config.get_logger(__name__)
        
        # Thread safety
        self._lock = threading.Lock()
        
        # Request tracking
        self._minute_requests = deque()  # Timestamps of requests in last minute
        self._daily_requests = 0
        self._last_daily_reset = datetime.now(POLYGON_TIMEZONE).date()
        
        # Statistics
        self.stats = RateLimitStats()
        self._response_times = deque(maxlen=100)  # Keep last 100 response times
        
        # Request queue for when rate limited
        self._request_queue = PriorityQueue()
        self._queue_processor_thread = None
        self._stop_processor = threading.Event()
        
        # Load persisted stats if available
        self._load_stats()
        
        # Start queue processor
        self._start_queue_processor()
        
    def _load_stats(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Load persisted rate limit statistics
        Note: Helps maintain accurate counts across restarts
        """
        stats_file = self.config.data_dir / 'rate_limit_stats.json'
        
        if stats_file.exists():
            try:
                with open(stats_file, 'r') as f:
                    data = json.load(f)
                    
                # Restore daily count if same day
                last_reset = datetime.fromisoformat(data.get('last_reset_time', ''))
                if last_reset.date() == datetime.now(POLYGON_TIMEZONE).date():
                    self._daily_requests = data.get('requests_today', 0)
                    self.stats.requests_today = self._daily_requests
                    
                # Restore cumulative stats
                self.stats.total_requests = data.get('total_requests', 0)
                self.stats.rate_limit_hits = data.get('rate_limit_hits', 0)
                self.stats.successful_requests = data.get('successful_requests', 0)
                self.stats.failed_requests = data.get('failed_requests', 0)
                
                self.logger.debug(f"Loaded rate limit stats: {self._daily_requests} requests today")
                
            except Exception as e:
                self.logger.warning(f"Failed to load rate limit stats: {e}")
                
    def _save_stats(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Persist rate limit statistics to disk
        Note: Called periodically to maintain state
        """
        stats_file = self.config.data_dir / 'rate_limit_stats.json'
        
        try:
            with open(stats_file, 'w') as f:
                json.dump(self.stats.to_dict(), f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save rate limit stats: {e}")
            
    def _reset_daily_counter_if_needed(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Reset daily request counter at midnight
        Note: Called before checking limits
        """
        current_date = datetime.now(POLYGON_TIMEZONE).date()
        
        if current_date > self._last_daily_reset:
            with self._lock:
                self._daily_requests = 0
                self._last_daily_reset = current_date
                self.stats.requests_today = 0
                self.stats.last_reset_time = datetime.now(POLYGON_TIMEZONE)
                self.logger.info("Reset daily request counter")
                
    def _clean_minute_window(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Remove requests older than 1 minute from tracking
        Note: Maintains sliding window of requests
        """
        cutoff_time = time.time() - 60
        
        while self._minute_requests and self._minute_requests[0] < cutoff_time:
            self._minute_requests.popleft()
            
    def get_current_usage(self) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Get current rate limit usage statistics
        Returns: dict - Current usage vs limits
        Example: usage = limiter.get_current_usage()
        """
        with self._lock:
            self._clean_minute_window()
            self._reset_daily_counter_if_needed()
            
            # Calculate percentages
            minute_usage_pct = (len(self._minute_requests) / self.config.requests_per_minute) * 100
            daily_usage_pct = (self._daily_requests / self.config.requests_per_day) * 100
            
            return {
                'minute': {
                    'used': len(self._minute_requests),
                    'limit': self.config.requests_per_minute,
                    'remaining': max(0, self.config.requests_per_minute - len(self._minute_requests)),
                    'usage_pct': round(minute_usage_pct, 2)
                },
                'daily': {
                    'used': self._daily_requests,
                    'limit': self.config.requests_per_day,
                    'remaining': max(0, self.config.requests_per_day - self._daily_requests),
                    'usage_pct': round(daily_usage_pct, 2)
                },
                'queue_size': self._request_queue.qsize(),
                'tier': self.config.subscription_tier
            }
            
    def check_limit(self) -> Tuple[bool, Optional[float]]:
        """
        [FUNCTION SUMMARY]
        Purpose: Check if request would exceed rate limits
        Returns: tuple - (is_allowed, wait_time_seconds)
        Example: allowed, wait_time = limiter.check_limit()
        """
        with self._lock:
            self._clean_minute_window()
            self._reset_daily_counter_if_needed()
            
            # Apply buffer to limits
            minute_limit = int(self.config.requests_per_minute * self.config.rate_limit_buffer)
            daily_limit = int(self.config.requests_per_day * self.config.rate_limit_buffer)
            
            # Check daily limit
            if self._daily_requests >= daily_limit:
                # Calculate time until midnight
                now = datetime.now(POLYGON_TIMEZONE)
                midnight = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                wait_seconds = (midnight - now).total_seconds()
                
                return False, wait_seconds
            
            # Check minute limit
            current_minute_requests = len(self._minute_requests)
            if current_minute_requests >= minute_limit:
                # Calculate wait time
                oldest_request = self._minute_requests[0]
                wait_seconds = 60 - (time.time() - oldest_request) + 1
                
                return False, max(wait_seconds, 1)
            
            return True, None
            
    def wait_if_needed(self, priority: int = 5) -> float:
        """
        [FUNCTION SUMMARY]
        Purpose: Wait if rate limit would be exceeded
        Parameters:
            - priority (int): Request priority (1=highest, 10=lowest)
        Returns: float - Seconds waited
        Example: wait_time = limiter.wait_if_needed(priority=1)
        """
        total_wait = 0.0
        
        while True:
            allowed, wait_time = self.check_limit()
            
            if allowed:
                break
                
            if wait_time:
                # Log wait reason
                usage = self.get_current_usage()
                if usage['daily']['remaining'] == 0:
                    self.logger.warning(
                        f"Daily rate limit reached ({usage['daily']['used']}/{usage['daily']['limit']}), "
                        f"waiting {wait_time:.1f} seconds"
                    )
                else:
                    self.logger.debug(
                        f"Minute rate limit reached ({usage['minute']['used']}/{usage['minute']['limit']}), "
                        f"waiting {wait_time:.1f} seconds"
                    )
                
                # High priority requests get shorter waits
                adjusted_wait = wait_time * (0.5 if priority <= 2 else 1.0)
                
                # Update stats
                self.stats.rate_limit_hits += 1
                self.stats.total_wait_time += adjusted_wait
                total_wait += adjusted_wait
                
                # Wait
                time.sleep(adjusted_wait)
                
        return total_wait
        
    def record_request(self, response_time: Optional[float] = None,
                      success: bool = True):
        """
        [FUNCTION SUMMARY]
        Purpose: Record that a request was made
        Parameters:
            - response_time (float, optional): API response time in seconds
            - success (bool): Whether request succeeded
        Example: limiter.record_request(response_time=0.523, success=True)
        """
        with self._lock:
            # Add to tracking
            current_time = time.time()
            self._minute_requests.append(current_time)
            self._daily_requests += 1
            
            # Update stats
            self.stats.requests_per_minute = len(self._minute_requests)
            self.stats.requests_today = self._daily_requests
            self.stats.total_requests += 1
            
            if success:
                self.stats.successful_requests += 1
            else:
                self.stats.failed_requests += 1
            
            # Track response time
            if response_time is not None:
                self._response_times.append(response_time)
                self.stats.average_response_time = sum(self._response_times) / len(self._response_times)
            
            # Save stats periodically
            if self.stats.total_requests % 100 == 0:
                self._save_stats()
                
    def estimate_time_for_requests(self, num_requests: int) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Estimate time needed for N requests
        Parameters:
            - num_requests (int): Number of requests to make
        Returns: dict - Time estimates and strategy
        Example: estimate = limiter.estimate_time_for_requests(1000)
        """
        usage = self.get_current_usage()
        
        # Current available capacity
        minute_available = usage['minute']['remaining']
        daily_available = usage['daily']['remaining']
        
        # If requests fit in current limits
        if num_requests <= min(minute_available, daily_available):
            return {
                'total_time_seconds': num_requests * self.stats.average_response_time,
                'wait_time_seconds': 0,
                'strategy': 'immediate',
                'batches': 1
            }
        
        # Calculate batching strategy
        requests_per_minute = self.config.requests_per_minute * self.config.rate_limit_buffer
        
        # Time for requests at max rate
        minutes_needed = math.ceil(num_requests / requests_per_minute)
        total_seconds = minutes_needed * 60
        
        # Add average response time
        total_seconds += num_requests * self.stats.average_response_time
        
        # Check daily limit
        if num_requests > daily_available:
            days_needed = math.ceil(num_requests / self.config.requests_per_day)
            return {
                'total_time_seconds': days_needed * 86400,
                'wait_time_seconds': total_seconds - (num_requests * self.stats.average_response_time),
                'strategy': 'multi_day',
                'batches': days_needed,
                'warning': f'Exceeds daily limit, will take {days_needed} days'
            }
        
        return {
            'total_time_seconds': total_seconds,
            'wait_time_seconds': total_seconds - (num_requests * self.stats.average_response_time),
            'strategy': 'batched',
            'batches': minutes_needed
        }
        
    def queue_request(self, callback: Callable, *args,
                     priority: int = 5, **kwargs) -> None:
        """
        [FUNCTION SUMMARY]
        Purpose: Queue a request for later execution
        Parameters:
            - callback (Callable): Function to call
            - *args: Positional arguments for callback
            - priority (int): Priority (1=highest, 10=lowest)
            - **kwargs: Keyword arguments for callback
        Example: limiter.queue_request(api_call, 'AAPL', priority=1)
        """
        request = QueuedRequest(
            priority=priority,
            timestamp=datetime.now(POLYGON_TIMEZONE),
            callback=callback,
            args=args,
            kwargs=kwargs
        )
        
        self._request_queue.put(request)
        self.logger.debug(f"Queued request with priority {priority}, queue size: {self._request_queue.qsize()}")
        
    def _start_queue_processor(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Start background thread to process queued requests
        Note: Automatically processes queue while respecting rate limits
        """
        if self._queue_processor_thread and self._queue_processor_thread.is_alive():
            return
            
        self._stop_processor.clear()
        self._queue_processor_thread = threading.Thread(
            target=self._process_queue,
            name="RateLimiterQueueProcessor",
            daemon=True
        )
        self._queue_processor_thread.start()
        self.logger.debug("Started queue processor thread")
        
    def _process_queue(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Background thread that processes queued requests
        Note: Runs continuously until stopped
        """
        while not self._stop_processor.is_set():
            try:
                # Get request with timeout
                try:
                    request = self._request_queue.get(timeout=1)
                except:
                    continue
                    
                # Wait for rate limit
                wait_time = self.wait_if_needed(priority=request.priority)
                
                if wait_time > 0:
                    self.logger.debug(f"Queue processor waited {wait_time:.1f}s for rate limit")
                
                # Execute request
                start_time = time.time()
                try:
                    result = request.callback(*request.args, **request.kwargs)
                    response_time = time.time() - start_time
                    self.record_request(response_time=response_time, success=True)
                    
                except Exception as e:
                    response_time = time.time() - start_time
                    self.record_request(response_time=response_time, success=False)
                    
                    # Retry logic
                    if request.retry_count < 3:
                        request.retry_count += 1
                        request.priority = min(request.priority + 1, 10)  # Lower priority
                        self._request_queue.put(request)
                        self.logger.warning(f"Request failed, requeuing (attempt {request.retry_count}): {e}")
                    else:
                        self.logger.error(f"Request failed after 3 attempts: {e}")
                        
            except Exception as e:
                self.logger.error(f"Queue processor error: {e}")
                
    def get_cost_estimate(self, num_requests: int) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Estimate API cost for number of requests
        Parameters:
            - num_requests (int): Number of API requests
        Returns: dict - Cost estimates by tier
        Example: cost = limiter.get_cost_estimate(10000)
        """
        # Polygon pricing (approximate, check current pricing)
        tier_costs = {
            'basic': {'monthly': 0, 'per_request': 0},
            'starter': {'monthly': 99, 'included_requests': 100000, 'per_extra': 0.001},
            'developer': {'monthly': 399, 'included_requests': 1000000, 'per_extra': 0.0005},
            'advanced': {'monthly': 999, 'included_requests': float('inf'), 'per_extra': 0}
        }
        
        current_tier = self.config.subscription_tier
        tier_info = tier_costs.get(current_tier, tier_costs['basic'])
        
        # Calculate cost
        if current_tier == 'basic':
            estimated_cost = 0  # Free tier
            recommendation = "Consider upgrading for more requests" if num_requests > 1000 else None
        else:
            monthly_cost = tier_info['monthly']
            included = tier_info.get('included_requests', 0)
            
            if num_requests <= included:
                estimated_cost = 0  # Within included requests
                recommendation = None
            else:
                extra_requests = num_requests - included
                extra_cost = extra_requests * tier_info['per_extra']
                estimated_cost = extra_cost
                recommendation = f"${extra_cost:.2f} for {extra_requests} requests over limit"
        
        return {
            'tier': current_tier,
            'num_requests': num_requests,
            'estimated_cost': round(estimated_cost, 2),
            'monthly_base': tier_info.get('monthly', 0),
            'recommendation': recommendation,
            'requests_per_dollar': 1 / tier_info.get('per_extra', 1) if tier_info.get('per_extra') else float('inf')
        }
        
    def get_statistics(self) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Get comprehensive rate limiter statistics
        Returns: dict - Detailed statistics
        Example: stats = limiter.get_statistics()
        """
        usage = self.get_current_usage()
        stats_dict = self.stats.to_dict()
        
        # Add calculated metrics
        if self.stats.total_requests > 0:
            stats_dict['average_wait_per_request'] = round(
                self.stats.total_wait_time / self.stats.total_requests, 3
            )
        
        # Add usage info
        stats_dict['current_usage'] = usage
        
        # Add timing estimates
        if self._response_times:
            stats_dict['response_time_percentiles'] = {
                'p50': round(sorted(self._response_times)[len(self._response_times)//2], 3),
                'p95': round(sorted(self._response_times)[int(len(self._response_times)*0.95)], 3),
                'p99': round(sorted(self._response_times)[int(len(self._response_times)*0.99)], 3),
            }
        
        return stats_dict
        
    def reset_statistics(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Reset all statistics to zero
        Note: Does not reset current rate limit counters
        Example: limiter.reset_statistics()
        """
        self.stats = RateLimitStats()
        self._response_times.clear()
        self._save_stats()
        self.logger.info("Reset rate limiter statistics")
        
    def stop(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Stop the rate limiter and save state
        Note: Call this before application shutdown
        Example: limiter.stop()
        """
        # Stop queue processor
        self._stop_processor.set()
        if self._queue_processor_thread:
            self._queue_processor_thread.join(timeout=5)
        
        # Save final stats
        self._save_stats()
        
        self.logger.info("Rate limiter stopped")


class AsyncRateLimiter:
    """
    [CLASS SUMMARY]
    Purpose: Async version of rate limiter for async/await code
    Note: Shares state with sync RateLimiter through same tracking
    Usage:
        async with AsyncRateLimiter() as limiter:
            await limiter.wait_if_needed()
            # Make async API call
            limiter.record_request()
    """
    
    def __init__(self, sync_limiter: Optional[RateLimiter] = None):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize async rate limiter
        Parameters:
            - sync_limiter (RateLimiter, optional): Sync limiter to share state with
        """
        self._sync_limiter = sync_limiter or RateLimiter()
        
    async def wait_if_needed(self, priority: int = 5) -> float:
        """
        [FUNCTION SUMMARY]
        Purpose: Async wait if rate limit would be exceeded
        Parameters:
            - priority (int): Request priority
        Returns: float - Seconds waited
        Example: wait_time = await limiter.wait_if_needed()
        """
        total_wait = 0.0
        
        while True:
            allowed, wait_time = self._sync_limiter.check_limit()
            
            if allowed:
                break
                
            if wait_time:
                # Update stats
                self._sync_limiter.stats.rate_limit_hits += 1
                self._sync_limiter.stats.total_wait_time += wait_time
                total_wait += wait_time
                
                # Async wait
                await asyncio.sleep(wait_time)
                
        return total_wait
        
    def record_request(self, response_time: Optional[float] = None,
                      success: bool = True):
        """Record request (same as sync version)"""
        self._sync_limiter.record_request(response_time, success)
        
    def get_current_usage(self) -> Dict[str, Any]:
        """Get current usage (same as sync version)"""
        return self._sync_limiter.get_current_usage()
        
    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics (same as sync version)"""
        return self._sync_limiter.get_statistics()
        
    async def __aenter__(self):
        """Async context manager entry"""
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        pass


# Global rate limiter instance
_global_limiter = None


def get_rate_limiter() -> RateLimiter:
    """
    [FUNCTION SUMMARY]
    Purpose: Get or create global rate limiter instance
    Returns: RateLimiter - Singleton rate limiter
    Example: limiter = get_rate_limiter()
    """
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = RateLimiter()
    return _global_limiter


def get_async_rate_limiter() -> AsyncRateLimiter:
    """
    [FUNCTION SUMMARY]
    Purpose: Get async rate limiter that shares state with sync limiter
    Returns: AsyncRateLimiter - Async rate limiter instance
    Example: async_limiter = get_async_rate_limiter()
    """
    return AsyncRateLimiter(get_rate_limiter())


__all__ = [
    'RateLimiter',
    'AsyncRateLimiter',
    'RateLimitStats',
    'get_rate_limiter',
    'get_async_rate_limiter'
]