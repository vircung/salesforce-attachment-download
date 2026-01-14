"""
Salesforce Attachments Extract - Exceptions

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
    - Network errors
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
