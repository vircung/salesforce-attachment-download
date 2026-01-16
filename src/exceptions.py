"""
Salesforce Attachments Downloader - Exceptions

Centralized exception hierarchy for all Salesforce-related errors.
"""


class SalesforceError(Exception):
    """Base exception for all Salesforce operations."""
    pass


class SFAuthError(SalesforceError):
    """Exception for Salesforce authentication errors.

    Raised when:
    - SF CLI is not authenticated
    - Access token is invalid or expired
    - Org alias is not found
    """
    pass


class SFAPIError(SalesforceError):
    """Exception for Salesforce API errors.

    Raised when:
    - REST API request fails
    - Resource not found (404)
    - Permission denied
    """
    pass


class SFNetworkError(SFAPIError):
    """Exception for Salesforce network or service errors.

    Raised when:
    - Network connection fails
    - API service returns non-auth fatal errors (5xx/4xx non-404)
    """
    pass


class SFQueryError(SalesforceError):
    """Exception for SOQL query execution errors.

    Raised when:
    - SOQL query syntax is invalid
    - Query length exceeds Salesforce limits
    - Insufficient permissions to query objects
    - sf data query command fails
    """
    pass
