"""
Centralized Exception Handler Module

Provides consistent error handling and logging across the application.
"""

import logging
from typing import Dict, Tuple

logger = logging.getLogger(__name__)


class WorkflowExceptionHandler:
    """Centralized exception handling with consistent error messages."""

    ERROR_MESSAGES: Dict[type, Tuple[str, str]] = {
        # Import these when needed to avoid circular imports
    }

    @classmethod
    def handle_and_log(cls, error: Exception, context: str = "") -> int:
        """Handle exception with consistent logging."""
        from src.exceptions import SFAuthError, SFQueryError, SFAPIError

        error_type = type(error)
        primary_msg = ""
        suggestion_msg = ""

        if error_type == SFAuthError:
            primary_msg = "Salesforce authentication failed"
            suggestion_msg = "Please check your Salesforce CLI authentication (run: sf org list)"
        elif error_type == SFQueryError:
            primary_msg = "SOQL query failed"
            suggestion_msg = "Check query syntax and record IDs"
        elif error_type == SFAPIError:
            primary_msg = "Salesforce API error"
            suggestion_msg = "Check network connection and API access"
        elif error_type == FileNotFoundError:
            primary_msg = "File not found"
            suggestion_msg = "Check that the specified file or directory exists"
        elif error_type == PermissionError:
            primary_msg = "Permission denied"
            suggestion_msg = "Check file permissions and access rights"
        elif error_type == ValueError:
            primary_msg = "Invalid input or configuration"
            suggestion_msg = "Check input parameters and configuration values"
        else:
            primary_msg = f"Unexpected error: {type(error).__name__}"
            suggestion_msg = "Check logs for detailed error information"

        if context:
            logger.error(f"{context}: {primary_msg}")
        else:
            logger.error(primary_msg)

        if str(error):
            logger.error(f"Details: {error}")

        logger.error(f"Suggestion: {suggestion_msg}")
        logger.debug("Full error details:", exc_info=True)

        return 2