"""
Enhanced Error Handling for Salesforce API Operations

This module provides comprehensive error handling and retry logic
specifically designed for Salesforce API operations using simple-salesforce.
"""

import json
import logging
import time
from typing import Callable, Any, Optional

from simple_salesforce.exceptions import SalesforceError

logger = logging.getLogger(__name__)


class SalesforceErrorHandler:
    """
    Enhanced error handling for simple-salesforce operations.

    Provides intelligent retry logic with exponential backoff,
    Salesforce-aware error classification, and comprehensive logging.
    """

    # Salesforce error codes that should trigger retries
    RETRYABLE_ERROR_CODES = {
        'REQUEST_LIMIT_EXCEEDED',  # Rate limit exceeded
        'SERVER_UNAVAILABLE',      # Temporary server issues
        'TIMEOUT',                 # Request timeout
        'CONNECTION_ERROR',        # Network connectivity issues
        'INTERNAL_SERVER_ERROR',   # Generic server errors
    }

    # Salesforce error codes that should NOT be retried
    NON_RETRYABLE_ERROR_CODES = {
        'INVALID_SESSION_ID',      # Authentication expired
        'INVALID_GRANT',           # OAuth issues
        'INSUFFICIENT_ACCESS',     # Permission issues
        'MALFORMED_QUERY',         # Query syntax errors
        'INVALID_FIELD',           # Field validation errors
        'DUPLICATE_VALUE',         # Data integrity issues
    }

    @staticmethod
    def should_retry_error(error: SalesforceError) -> bool:
        """
        Determine if a Salesforce error should trigger a retry.

        Args:
            error: The SalesforceError to evaluate

        Returns:
            True if the error is retryable, False otherwise
        """
        if not hasattr(error, 'content'):
            return False

        try:
            # Try to extract error code from the response
            content = error.content
            if isinstance(content, bytes):
                content = content.decode('utf-8')

            # Look for errorCode in the response
            import json
            error_data = json.loads(content)

            # Handle both single error and multiple errors
            if isinstance(error_data, list) and error_data:
                error_code = error_data[0].get('errorCode')
            elif isinstance(error_data, dict):
                error_code = error_data.get('errorCode')
            else:
                return False

            if error_code in SalesforceErrorHandler.RETRYABLE_ERROR_CODES:
                logger.warning(f"Retryable Salesforce error: {error_code}")
                return True
            elif error_code in SalesforceErrorHandler.NON_RETRYABLE_ERROR_CODES:
                logger.error(f"Non-retryable Salesforce error: {error_code}")
                return False
            else:
                # Unknown error codes - retry to be safe
                logger.warning(f"Unknown Salesforce error code: {error_code} - retrying")
                return True

        except (json.JSONDecodeError, KeyError, AttributeError):
            # If we can't parse the error, check HTTP status
            if hasattr(error, 'status') and error.status in (500, 502, 503, 504):
                logger.warning(f"Server error (HTTP {error.status}) - retrying")
                return True
            elif hasattr(error, 'status') and error.status == 429:
                logger.warning("Rate limit exceeded - retrying")
                return True

            # Default to not retrying for unparseable errors
            logger.error(f"Unparseable Salesforce error: {error}")
            return False

    @staticmethod
    def execute_with_retry(
        operation: Callable,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        backoff_factor: float = 2.0
    ) -> Any:
        """
        Execute an operation with exponential backoff retry logic.

        Args:
            operation: The callable operation to execute
            max_retries: Maximum number of retry attempts
            base_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds
            backoff_factor: Exponential backoff multiplier

        Returns:
            The result of the successful operation

        Raises:
            SalesforceError: If all retry attempts fail
        """
        last_error: Exception = Exception("No error occurred")

        for attempt in range(max_retries + 1):
            try:
                result = operation()
                if attempt > 0:
                    logger.info(f"Operation succeeded on attempt {attempt + 1}")
                return result

            except SalesforceError as e:
                last_error = e

                if attempt == max_retries:
                    logger.error(f"Operation failed after {max_retries + 1} attempts: {e}")
                    raise

                if not SalesforceErrorHandler.should_retry_error(e):
                    logger.error(f"Non-retryable error encountered: {e}")
                    raise

                # Calculate delay with exponential backoff
                delay = min(base_delay * (backoff_factor ** attempt), max_delay)

                logger.warning(
                    f"Attempt {attempt + 1} failed, retrying in {delay:.1f}s: {e}"
                )
                time.sleep(delay)

            except OSError as e:
                # Deterministic OS errors (e.g. filename too long) should not be retried
                logger.error(f"OS error (not retryable): {e}")
                raise

            except Exception as e:
                # Non-Salesforce errors (network issues, etc.)
                last_error = e

                if attempt == max_retries:
                    logger.error(f"Operation failed after {max_retries + 1} attempts: {e}")
                    raise

                # For non-Salesforce errors, always retry
                delay = min(base_delay * (backoff_factor ** attempt), max_delay)
                logger.warning(
                    f"Non-Salesforce error on attempt {attempt + 1}, retrying in {delay:.1f}s: {e}"
                )
                time.sleep(delay)

        # This should never be reached, but just in case
        raise last_error

    @staticmethod
    def wrap_operation(operation: Callable, **retry_kwargs) -> Callable:
        """
        Wrap an operation with retry logic.

        Args:
            operation: The operation to wrap
            **retry_kwargs: Keyword arguments for execute_with_retry

        Returns:
            A wrapped callable that includes retry logic
        """
        def wrapped_operation(*args, **kwargs):
            return SalesforceErrorHandler.execute_with_retry(
                lambda: operation(*args, **kwargs),
                **retry_kwargs
            )
        return wrapped_operation