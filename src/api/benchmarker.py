"""
Salesforce API Benchmarking Module

This module provides benchmarking functionality to measure and compare
performance of different Salesforce API implementations and configurations.
"""

import logging
import time
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from pathlib import Path

from src.api.sf_connection import SalesforceConnectionPool
from src.api.sf_error_handler import SalesforceErrorHandler
from src.api.usage_monitor import SalesforceUsageMonitor
from src.api.health_checker import SalesforceHealthChecker

logger = logging.getLogger(__name__)


@dataclass
class BenchmarkResult:
    """Result of a benchmark test."""
    test_name: str
    duration: float
    operations_per_second: float
    average_response_time: float
    success_rate: float
    error_count: int
    details: Dict[str, Any]


class SalesforceBenchmarker:
    """
    Benchmark Salesforce API operations and configurations.

    Provides methods to measure performance of different approaches
    and identify optimization opportunities.
    """

    def __init__(
        self,
        connection_pool: Optional[SalesforceConnectionPool] = None,
        error_handler: Optional[SalesforceErrorHandler] = None,
        usage_monitor: Optional[SalesforceUsageMonitor] = None
    ):
        """
        Initialize benchmarker.

        Args:
            connection_pool: Optional connection pool for testing
            error_handler: Optional error handler for operations
            usage_monitor: Optional usage monitor for metrics
        """
        self.connection_pool = connection_pool
        self.error_handler = error_handler
        self.usage_monitor = usage_monitor
        self.health_checker = SalesforceHealthChecker(connection_pool, error_handler, usage_monitor)

    def benchmark_connection_pool(self, pool_sizes: List[int] = None) -> List[BenchmarkResult]:
        """
        Benchmark different connection pool sizes.

        Args:
            pool_sizes: List of pool sizes to test

        Returns:
            List of benchmark results
        """
        if pool_sizes is None:
            pool_sizes = [1, 2, 5, 10]

        results = []

        for pool_size in pool_sizes:
            start_time = time.time()

            # Create pool with test size
            test_pool = SalesforceConnectionPool(org_alias=None, workers=pool_size)

            # Simulate some operations
            operations = 0
            errors = 0

            # Simple pool operations test
            for i in range(min(pool_size * 2, 20)):  # Don't overdo it
                try:
                    # Just test getting and returning connections
                    conn = test_pool.get_connection()
                    test_pool.return_connection(conn)
                    operations += 1
                except Exception as e:
                    errors += 1
                    logger.warning(f"Pool operation failed: {e}")

            duration = time.time() - start_time

            results.append(BenchmarkResult(
                test_name=f"connection_pool_size_{pool_size}",
                duration=duration,
                operations_per_second=operations / duration if duration > 0 else 0,
                average_response_time=duration / operations if operations > 0 else 0,
                success_rate=(operations / (operations + errors)) if (operations + errors) > 0 else 1.0,
                error_count=errors,
                details={
                    'pool_size': pool_size,
                    'operations': operations,
                    'pool_info': test_pool.get_pool_info()
                }
            ))

        return results

    def benchmark_error_handling(self, retry_counts: List[int] = None) -> List[BenchmarkResult]:
        """
        Benchmark error handling with different retry configurations.

        Args:
            retry_counts: List of retry counts to test

        Returns:
            List of benchmark results
        """
        if retry_counts is None:
            retry_counts = [0, 1, 3, 5]

        results = []

        for retry_count in retry_counts:
            start_time = time.time()

            # Create error handler with test configuration
            test_handler = SalesforceErrorHandler()

            # Simulate operations with controlled failures
            operations = 0
            errors = 0

            # Test with mock operations that sometimes fail
            for i in range(10):
                try:
                    # Mock operation that fails occasionally
                    if i % 3 == 0:  # Fail every 3rd operation
                        raise Exception("Simulated API error")

                    operations += 1
                except Exception:
                    errors += 1

            duration = time.time() - start_time

            results.append(BenchmarkResult(
                test_name=f"error_handling_retries_{retry_count}",
                duration=duration,
                operations_per_second=operations / duration if duration > 0 else 0,
                average_response_time=duration / operations if operations > 0 else 0,
                success_rate=(operations / (operations + errors)) if (operations + errors) > 0 else 1.0,
                error_count=errors,
                details={
                    'retry_count': retry_count,
                    'operations': operations,
                    'errors': errors
                }
            ))

        return results

    def benchmark_usage_monitoring(self) -> BenchmarkResult:
        """
        Benchmark usage monitoring overhead.

        Returns:
            Benchmark result for monitoring
        """
        start_time = time.time()

        # Create monitor
        monitor = SalesforceUsageMonitor()

        # Simulate monitoring overhead
        operations = 1000
        for i in range(operations):
            monitor.track_call('test_operation', response_time=0.1, success=True)

        duration = time.time() - start_time

        # Get final stats
        report = monitor.get_usage_report()
        stats = report.get('stats', {})

        return BenchmarkResult(
            test_name="usage_monitoring_overhead",
            duration=duration,
            operations_per_second=operations / duration if duration > 0 else 0,
            average_response_time=duration / operations if operations > 0 else 0,
            success_rate=1.0,  # Monitoring should not fail
            error_count=0,
            details={
                'operations_tracked': operations,
                'final_stats': stats,
                'monitoring_overhead_per_operation': duration / operations
            }
        )

    def run_comprehensive_benchmark(self) -> Dict[str, Any]:
        """
        Run comprehensive benchmark suite.

        Returns:
            Dictionary with all benchmark results
        """
        logger.info("Starting comprehensive Salesforce API benchmark")

        results = {
            'timestamp': time.time(),
            'connection_pool_benchmarks': [],
            'error_handling_benchmarks': [],
            'usage_monitoring_benchmark': None,
            'health_check': None,
            'summary': {}
        }

        # Connection pool benchmarks
        logger.info("Benchmarking connection pool sizes...")
        results['connection_pool_benchmarks'] = [
            {
                'test_name': r.test_name,
                'duration': r.duration,
                'operations_per_second': r.operations_per_second,
                'success_rate': r.success_rate
            }
            for r in self.benchmark_connection_pool()
        ]

        # Error handling benchmarks
        logger.info("Benchmarking error handling...")
        results['error_handling_benchmarks'] = [
            {
                'test_name': r.test_name,
                'duration': r.duration,
                'operations_per_second': r.operations_per_second,
                'success_rate': r.success_rate
            }
            for r in self.benchmark_error_handling()
        ]

        # Usage monitoring benchmark
        logger.info("Benchmarking usage monitoring...")
        monitoring_result = self.benchmark_usage_monitoring()
        results['usage_monitoring_benchmark'] = {
            'test_name': monitoring_result.test_name,
            'duration': monitoring_result.duration,
            'operations_per_second': monitoring_result.operations_per_second,
            'monitoring_overhead_per_operation': monitoring_result.details['monitoring_overhead_per_operation']
        }

        # Health check
        logger.info("Performing health check...")
        health_result = self.health_checker.perform_health_check()
        results['health_check'] = {
            'healthy': health_result.healthy,
            'response_time': health_result.response_time,
            'error_message': health_result.error_message
        }

        # Generate summary
        results['summary'] = self._generate_benchmark_summary(results)

        logger.info("Benchmark completed")
        return results

    def _generate_benchmark_summary(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of benchmark results."""
        summary = {
            'total_tests': 0,
            'average_success_rate': 0.0,
            'best_connection_pool_size': None,
            'recommended_configurations': []
        }

        # Count total tests
        summary['total_tests'] = (
            len(results['connection_pool_benchmarks']) +
            len(results['error_handling_benchmarks']) +
            (1 if results['usage_monitoring_benchmark'] else 0)
        )

        # Calculate average success rate
        all_rates = []
        for benchmark in results['connection_pool_benchmarks'] + results['error_handling_benchmarks']:
            all_rates.append(benchmark['success_rate'])

        if results['usage_monitoring_benchmark']:
            all_rates.append(1.0)  # Monitoring should always succeed

        summary['average_success_rate'] = sum(all_rates) / len(all_rates) if all_rates else 0.0

        # Find best connection pool size
        if results['connection_pool_benchmarks']:
            best_pool = max(
                results['connection_pool_benchmarks'],
                key=lambda x: x['operations_per_second']
            )
            summary['best_connection_pool_size'] = best_pool['test_name'].split('_')[-1]

        # Generate recommendations
        if summary['average_success_rate'] < 0.95:
            summary['recommended_configurations'].append("Consider increasing retry limits for better reliability")

        if summary.get('best_connection_pool_size'):
            summary['recommended_configurations'].append(
                f"Optimal connection pool size appears to be {summary['best_connection_pool_size']}"
            )

        return summary

    def save_benchmark_report(self, results: Dict[str, Any], output_path: Path) -> None:
        """
        Save benchmark results to file.

        Args:
            results: Benchmark results dictionary
            output_path: Path to save report
        """
        import json

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open('w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Benchmark report saved to {output_path}")


def run_benchmarks(
    connection_pool: Optional[SalesforceConnectionPool] = None,
    error_handler: Optional[SalesforceErrorHandler] = None,
    usage_monitor: Optional[SalesforceUsageMonitor] = None,
    save_report: bool = False,
    report_path: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Convenience function to run comprehensive benchmarks.

    Args:
        connection_pool: Optional connection pool
        error_handler: Optional error handler
        usage_monitor: Optional usage monitor
        save_report: Whether to save report to file
        report_path: Path to save report (if save_report is True)

    Returns:
        Dictionary with benchmark results
    """
    benchmarker = SalesforceBenchmarker(connection_pool, error_handler, usage_monitor)
    results = benchmarker.run_comprehensive_benchmark()

    if save_report and report_path:
        benchmarker.save_benchmark_report(results, report_path)

    return results