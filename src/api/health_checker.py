"""
Salesforce Health Check and Performance Monitoring

This module provides health check functionality and performance monitoring
for Salesforce API operations, including connection testing, rate limit monitoring,
and performance metrics collection.
"""

import logging
import time
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from simple_salesforce.api import Salesforce

from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check operation."""
    healthy: bool
    response_time: float
    error_message: Optional[str] = None
    details: Dict[str, Any] = None


@dataclass
class PerformanceMetrics:
    """Performance metrics for API operations."""
    operation: str
    count: int
    average_response_time: float
    min_response_time: float
    max_response_time: float
    error_rate: float
    throughput_per_minute: float


class SalesforceHealthChecker:
    """
    Health checker for Salesforce API connectivity and performance.

    Provides methods to test API connectivity, monitor performance,
    and detect potential issues before they cause failures.
    """

    def __init__(
        self,
        connection_pool: Optional[SalesforceConnectionPool] = None,
        error_handler: Optional[SalesforceErrorHandler] = None,
        usage_monitor: Optional[SalesforceUsageMonitor] = None
    ):
        """
        Initialize health checker.

        Args:
            connection_pool: Optional connection pool for testing
            error_handler: Optional error handler for operations
            usage_monitor: Optional usage monitor for metrics
        """
        self.connection_pool = connection_pool
        self.error_handler = error_handler
        self.usage_monitor = usage_monitor

    def perform_health_check(self) -> HealthCheckResult:
        """
        Perform a comprehensive health check of Salesforce connectivity.

        Returns:
            HealthCheckResult with health status and details
        """
        start_time = time.time()

        try:
            if not self.connection_pool:
                return HealthCheckResult(
                    healthy=False,
                    response_time=0.0,
                    error_message="No connection pool available for health check"
                )

            # Test basic connectivity with a simple query
            sf_client = self.connection_pool.get_connection()

            try:
                # Simple query to test connectivity
                result = sf_client.query("SELECT Id FROM User LIMIT 1")
                response_time = time.time() - start_time

                # Check if we got a valid response
                if result.get('totalSize', 0) >= 0:
                    details = {
                        'api_version': getattr(sf_client, 'sf_version', 'unknown'),
                        'instance_url': getattr(sf_client, 'base_url', 'unknown'),
                        'records_returned': result.get('totalSize', 0)
                    }

                    return HealthCheckResult(
                        healthy=True,
                        response_time=response_time,
                        details=details
                    )
                else:
                    return HealthCheckResult(
                        healthy=False,
                        response_time=response_time,
                        error_message="Invalid API response",
                        details={'response': result}
                    )

            finally:
                self.connection_pool.return_connection(sf_client)

        except Exception as e:
            response_time = time.time() - start_time
            return HealthCheckResult(
                healthy=False,
                response_time=response_time,
                error_message=str(e)
            )

    def get_performance_metrics(self) -> List[PerformanceMetrics]:
        """
        Get current performance metrics from usage monitor.

        Returns:
            List of PerformanceMetrics for different operations
        """
        if not self.usage_monitor:
            return []

        report = self.usage_monitor.get_usage_report()
        stats = report.get('stats', {})

        metrics = []

        # Query metrics
        if stats.get('query_calls', 0) > 0:
            metrics.append(PerformanceMetrics(
                operation='query',
                count=stats['query_calls'],
                average_response_time=stats.get('average_response_time', 0.0),
                min_response_time=0.0,  # Would need to track this in monitor
                max_response_time=0.0,  # Would need to track this in monitor
                error_rate=0.0,  # Would need error tracking
                throughput_per_minute=stats.get('calls_per_minute', 0.0)
            ))

        # Download metrics
        if stats.get('download_calls', 0) > 0:
            metrics.append(PerformanceMetrics(
                operation='download',
                count=stats['download_calls'],
                average_response_time=stats.get('average_response_time', 0.0),
                min_response_time=0.0,
                max_response_time=0.0,
                error_rate=0.0,
                throughput_per_minute=0.0  # Downloads are slower, different metric
            ))

        return metrics

    def check_rate_limits(self) -> Dict[str, Any]:
        """
        Check current API rate limit status.

        Returns:
            Dictionary with rate limit information
        """
        if not self.usage_monitor:
            return {'error': 'No usage monitor available'}

        stats = self.usage_monitor.stats

        return {
            'remaining_calls': stats.rate_limit_remaining,
            'reset_time': stats.rate_limit_reset,
            'is_near_limit': stats.rate_limit_remaining is not None and stats.rate_limit_remaining < 100,
            'estimated_reset_in_seconds': (
                stats.rate_limit_reset - time.time()
                if stats.rate_limit_reset else None
            )
        }

    def get_connection_pool_status(self) -> Dict[str, Any]:
        """
        Get status of the connection pool.

        Returns:
            Dictionary with pool status information
        """
        if not self.connection_pool:
            return {'error': 'No connection pool available'}

        info = self.connection_pool.get_pool_info()

        return {
            'pool_size': info['pool_size'],
            'org_alias': info['org_alias'],
            'available_connections': info['queue_size'],
            'utilization_rate': (info['pool_size'] - info['queue_size']) / info['pool_size']
            if info['pool_size'] > 0 else 0
        }

    def perform_diagnostic_check(self) -> Dict[str, Any]:
        """
        Perform comprehensive diagnostic check.

        Returns:
            Dictionary with diagnostic results
        """
        diagnostics = {
            'timestamp': time.time(),
            'health_check': None,
            'performance_metrics': [],
            'rate_limits': {},
            'connection_pool': {},
            'recommendations': []
        }

        # Health check
        health_result = self.perform_health_check()
        diagnostics['health_check'] = {
            'healthy': health_result.healthy,
            'response_time': health_result.response_time,
            'error_message': health_result.error_message
        }

        # Performance metrics
        diagnostics['performance_metrics'] = [
            {
                'operation': m.operation,
                'count': m.count,
                'average_response_time': m.average_response_time,
                'throughput_per_minute': m.throughput_per_minute
            }
            for m in self.get_performance_metrics()
        ]

        # Rate limits
        diagnostics['rate_limits'] = self.check_rate_limits()

        # Connection pool
        diagnostics['connection_pool'] = self.get_connection_pool_status()

        # Generate recommendations
        diagnostics['recommendations'] = self._generate_recommendations(diagnostics)

        return diagnostics

    def _generate_recommendations(self, diagnostics: Dict[str, Any]) -> List[str]:
        """Generate recommendations based on diagnostic results."""
        recommendations = []

        # Health check recommendations
        health = diagnostics.get('health_check', {})
        if not health.get('healthy'):
            recommendations.append("API connectivity issues detected - check authentication and network")

        if health.get('response_time', 0) > 5.0:
            recommendations.append("Slow API response times detected - consider optimizing queries")

        # Rate limit recommendations
        rate_limits = diagnostics.get('rate_limits', {})
        if rate_limits.get('is_near_limit'):
            remaining = rate_limits.get('remaining_calls', 0)
            recommendations.append(f"Approaching API rate limit ({remaining} calls remaining) - consider reducing batch sizes")

        # Performance recommendations
        for metric in diagnostics.get('performance_metrics', []):
            if metric['average_response_time'] > 2.0:
                recommendations.append(f"Slow {metric['operation']} operations detected - consider query optimization")

        # Connection pool recommendations
        pool = diagnostics.get('connection_pool', {})
        utilization = pool.get('utilization_rate', 0)
        if utilization > 0.8:
            recommendations.append("High connection pool utilization - consider increasing pool size")

        return recommendations


def perform_health_check(
    connection_pool: Optional[SalesforceConnectionPool] = None,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None
) -> HealthCheckResult:
    """
    Convenience function to perform a health check.

    Args:
        connection_pool: Optional connection pool
        error_handler: Optional error handler
        usage_monitor: Optional usage monitor

    Returns:
        HealthCheckResult
    """
    checker = SalesforceHealthChecker(connection_pool, error_handler, usage_monitor)
    return checker.perform_health_check()


def get_performance_report(
    usage_monitor: Optional[SalesforceUsageMonitor] = None
) -> Dict[str, Any]:
    """
    Convenience function to get performance report.

    Args:
        usage_monitor: Optional usage monitor

    Returns:
        Dictionary with performance report
    """
    if not usage_monitor:
        return {'error': 'No usage monitor available'}

    return usage_monitor.get_usage_report()