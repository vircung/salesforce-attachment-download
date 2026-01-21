"""
SF CLI Authentication Adapter for simple-salesforce

This module provides an adapter class that bridges sf CLI authentication
to simple-salesforce client creation, enabling hybrid authentication.
"""

from typing import Optional
import logging

from simple_salesforce.api import Salesforce

from src.api.sf_auth import get_sf_auth_info

logger = logging.getLogger(__name__)


class SFCLIAuthAdapter:
    """
    Adapter for sf CLI authentication to simple-salesforce.

    This adapter uses sf CLI to extract session credentials and creates
    simple-salesforce clients for API operations, maintaining backward
    compatibility with existing org configurations.
    """

    def __init__(self, org_alias: Optional[str] = None):
        """
        Initialize the authentication adapter.

        Args:
            org_alias: Optional Salesforce org alias. If None, uses default org.
        """
        self.org_alias = org_alias
        self._sf_client: Optional[Salesforce] = None

    def get_client(self) -> Salesforce:
        """
        Get or create a simple-salesforce client.

        Returns a cached client if one exists, otherwise creates a new one
        using authentication information from sf CLI.

        Returns:
            Salesforce: Authenticated simple-salesforce client instance

        Raises:
            SFAuthError: If authentication information cannot be retrieved
        """
        if not self._sf_client:
            auth_info = get_sf_auth_info(self.org_alias)
            self._sf_client = Salesforce(
                instance_url=auth_info['instance_url'],
                session_id=auth_info['access_token'],
                version=auth_info.get('api_version', '65.0')
            )
            
            # Fix: Ensure Authorization header is set for REST API calls
            # simple-salesforce doesn't automatically set Bearer token for session_id
            if 'Authorization' not in self._sf_client.session.headers:
                self._sf_client.session.headers['Authorization'] = f'Bearer {auth_info["access_token"]}'
                logger.debug("Set Authorization header for REST API authentication")
        
        return self._sf_client

    def refresh_client(self) -> Salesforce:
        """
        Force refresh of the cached client.

        Useful when session might have expired or authentication needs
        to be refreshed.

        Returns:
            Salesforce: Fresh authenticated simple-salesforce client instance
        """
        self._sf_client = None
        return self.get_client()