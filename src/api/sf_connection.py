"""
Salesforce Connection Pool for simple-salesforce

This module provides a thread-safe connection pool for managing
simple-salesforce client instances with optimal pool sizing.
"""

from queue import Queue
from threading import Lock
from typing import Optional

from simple_salesforce.api import Salesforce

from src.api.sf_auth_adapter import SFCLIAuthAdapter

from src.config_limits import ConnectionPool, Workers


def calculate_pool_size(workers: int) -> int:
    """
    Calculate optimal connection pool size for simple-salesforce.

    Based on simple-salesforce using requests.Session with default pool_maxsize=10.
    For concurrent operations, use max(10, workers * 2) for safety margin.

    Args:
        workers: Number of concurrent worker threads/processes

    Returns:
        Optimal pool size for the given number of workers
    """
    # simple-salesforce uses requests.Session (default pool_maxsize=10)
    # For N workers, use max(10, N*2) for safety margin
    return max(ConnectionPool.MIN_POOL_SIZE, workers * 2)


class SalesforceConnectionPool:
    """
    Thread-safe connection pool for simple-salesforce clients.

    Manages a pool of authenticated Salesforce clients for efficient
    reuse across multiple operations and threads.
    """

    def __init__(self, org_alias: Optional[str] = None, workers: int = Workers.DEFAULT):
        """
        Initialize the connection pool.

        Args:
            org_alias: Optional Salesforce org alias. If None, uses default org.
            workers: Number of concurrent workers to optimize pool size for
        """
        self.org_alias = org_alias
        self.pool_size = calculate_pool_size(workers)
        self._pool: Queue[Salesforce] = Queue(maxsize=self.pool_size)
        self._lock = Lock()
        self._instance_url: str = ''
        self._initialize_pool()

    def _initialize_pool(self) -> None:
        """
        Initialize the pool with authenticated client instances.

        Creates the specified number of simple-salesforce clients
        using the authentication adapter. Captures instance_url from
        the auth adapter for use in download URLs.
        """
        from src.api.sf_auth import get_sf_auth_info
        auth_info = get_sf_auth_info(self.org_alias)
        self._instance_url = auth_info.get('instance_url', '')

        adapter = SFCLIAuthAdapter(self.org_alias)
        for _ in range(self.pool_size):
            client = adapter.get_client()
            self._pool.put(client)

    @property
    def instance_url(self) -> str:
        """Salesforce instance URL (e.g. https://myorg.my.salesforce.com)."""
        return self._instance_url

    def get_connection(self) -> Salesforce:
        """
        Get a connection from the pool.

        Returns an authenticated simple-salesforce client instance.
        Blocks if no connections are available.

        Returns:
            Salesforce: Authenticated client instance
        """
        return self._pool.get()

    def return_connection(self, conn: Salesforce) -> None:
        """
        Return a connection to the pool.

        Args:
            conn: The client instance to return to the pool
        """
        self._pool.put(conn)

    def get_pool_info(self) -> dict:
        """
        Get information about the current pool state.

        Returns:
            Dictionary with pool size and current usage information
        """
        return {
            'pool_size': self.pool_size,
            'org_alias': self.org_alias,
            'queue_size': self._pool.qsize()
        }