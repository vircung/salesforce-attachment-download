"""
Salesforce API Usage Monitoring

This module provides comprehensive tracking and monitoring of Salesforce
API usage, including call counts, response times, and rate limiting.
"""

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class APIUsageStats:
    """
    Container for API usage statistics.

    Tracks various metrics about Salesforce API operations.
    """
    total_calls: int = 0
    query_calls: int = 0
    download_calls: int = 0
    error_calls: int = 0
    response_times: deque[float] = field(default_factory=lambda: deque(maxlen=1000))
    last_call_time: Optional[float] = None
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[float] = None

    def get_average_response_time(self) -> float:
        """Calculate average response time."""
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    def get_calls_per_minute(self) -> float:
        """Estimate calls per minute based on recent activity."""
        if self.last_call_time is None or not self.response_times:
            return 0.0

        # Use last 10 calls to estimate rate
        recent_times = list(self.response_times)[-10:]
        if len(recent_times) < 2:
            return 0.0

        time_span = sum(recent_times)
        if time_span == 0:
            return 0.0

        return 60.0 / (time_span / len(recent_times))

    def to_dict(self) -> Dict[str, Any]:
        """Convert stats to dictionary for serialization."""
        return {
            'total_calls': self.total_calls,
            'query_calls': self.query_calls,
            'download_calls': self.download_calls,
            'error_calls': self.error_calls,
            'average_response_time': self.get_average_response_time(),
            'calls_per_minute': self.get_calls_per_minute(),
            'rate_limit_remaining': self.rate_limit_remaining,
            'rate_limit_reset': self.rate_limit_reset,
        }


class SalesforceUsageMonitor:
    """
    Monitor Salesforce API usage and performance.

    Tracks API calls, response times, error rates, and provides
    insights into API usage patterns and potential rate limiting.
    """

    def __init__(self, max_response_times: int = 1000):
        """
        Initialize the usage monitor.

        Args:
            max_response_times: Maximum number of response times to keep in history
        """
        self.stats = APIUsageStats()
        self.max_response_times = max_response_times
        self._start_time = time.time()

    def track_call(
        self,
        call_type: str,
        response_time: Optional[float] = None,
        success: bool = True,
        headers: Optional[Dict[str, str]] = None
    ) -> None:
        """
        Track an API call.

        Args:
            call_type: Type of call ('query', 'download', 'describe', etc.)
            response_time: Time taken for the call in seconds
            success: Whether the call was successful
            headers: Response headers for rate limit information
        """
        self.stats.total_calls += 1
        self.stats.last_call_time = time.time()

        if call_type == 'query':
            self.stats.query_calls += 1
        elif call_type == 'download':
            self.stats.download_calls += 1

        if not success:
            self.stats.error_calls += 1

        if response_time is not None:
            self.stats.response_times.append(response_time)

        # Extract rate limit information from headers
        if headers:
            self._extract_rate_limit_info(headers)

        # Log significant events
        if self.stats.total_calls % 100 == 0:
            logger.info(f"API usage milestone: {self.stats.total_calls} total calls")
            logger.info(f"Average response time: {self.stats.get_average_response_time():.2f}s")

        # Warn about high error rates
        error_rate = self.stats.error_calls / self.stats.total_calls
        if error_rate > 0.1 and self.stats.total_calls > 10:
            logger.warning(f"High error rate detected: {error_rate:.1%}")

    def _extract_rate_limit_info(self, headers: Dict[str, str]) -> None:
        """
        Extract rate limit information from response headers.

        Args:
            headers: HTTP response headers
        """
        # Salesforce API rate limit headers
        remaining = headers.get('Sforce-Limit-Info', '').split(',')[0]
        if 'api-usage=' in remaining:
            try:
                usage_info = remaining.split('api-usage=')[1]
                used, total = usage_info.split('/')
                remaining_calls = int(total) - int(used)
                self.stats.rate_limit_remaining = remaining_calls

                # Estimate reset time (Salesforce resets every 24 hours)
                if remaining_calls < 100:  # Getting close to limit
                    self.stats.rate_limit_reset = time.time() + 86400  # 24 hours

            except (ValueError, IndexError):
                pass

    def get_usage_report(self) -> Dict[str, Any]:
        """
        Generate a comprehensive usage report.

        Returns:
            Dictionary containing usage statistics and insights
        """
        runtime = time.time() - self._start_time

        report = {
            'runtime_seconds': runtime,
            'stats': self.stats.to_dict(),
            'insights': self._generate_insights(),
        }

        return report

    def _generate_insights(self) -> Dict[str, Any]:
        """
        Generate insights based on usage patterns.

        Returns:
            Dictionary of insights and recommendations
        """
        insights = {}

        # Error rate analysis
        if self.stats.total_calls > 0:
            error_rate = self.stats.error_calls / self.stats.total_calls
            if error_rate > 0.05:
                insights['error_rate'] = f"High error rate: {error_rate:.1%}"
            elif error_rate > 0.01:
                insights['error_rate'] = f"Moderate error rate: {error_rate:.1%}"

        # Rate limit warnings
        if self.stats.rate_limit_remaining is not None and self.stats.rate_limit_remaining < 100:
            insights['rate_limit'] = f"Approaching rate limit: {self.stats.rate_limit_remaining} calls remaining"

        # Performance insights
        avg_time = self.stats.get_average_response_time()
        if avg_time > 5.0:
            insights['performance'] = f"Slow responses: {avg_time:.2f}s average"
        elif avg_time > 1.0:
            insights['performance'] = f"Moderate response times: {avg_time:.2f}s average"

        # Call distribution
        if self.stats.total_calls > 10:
            query_ratio = self.stats.query_calls / self.stats.total_calls
            download_ratio = self.stats.download_calls / self.stats.total_calls

            if query_ratio > 0.8:
                insights['distribution'] = "Heavy query usage - consider bulk API for large datasets"
            elif download_ratio > 0.8:
                insights['distribution'] = "Heavy download usage - monitor bandwidth and rate limits"

        return insights

    def reset(self) -> None:
        """Reset all usage statistics."""
        self.stats = APIUsageStats()
        self._start_time = time.time()
        logger.info("Usage monitor reset")

    def log_summary(self) -> None:
        """Log a summary of current usage statistics."""
        report = self.get_usage_report()
        stats = report['stats']

        logger.info("=== Salesforce API Usage Summary ===")
        logger.info(f"Total calls: {stats['total_calls']}")
        logger.info(f"Query calls: {stats['query_calls']}")
        logger.info(f"Download calls: {stats['download_calls']}")
        logger.info(f"Error calls: {stats['error_calls']}")
        logger.info(f"Average response time: {stats['average_response_time']:.2f}s")
        logger.info(f"Calls per minute: {stats['calls_per_minute']:.1f}")

        if report['insights']:
            logger.info("Insights:")
            for key, value in report['insights'].items():
                logger.info(f"  {key}: {value}")

        logger.info("===================================")