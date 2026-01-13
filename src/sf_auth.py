"""
Salesforce CLI Authentication Utilities

This module provides functions to extract authentication credentials
from an active Salesforce CLI session for reuse in REST API calls.
"""

import json
import subprocess
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class SFAuthError(Exception):
    """Custom exception for Salesforce authentication errors"""
    pass


def get_sf_auth_info(org_alias: Optional[str] = None) -> Dict[str, str]:
    """
    Extract access token and instance URL from sf CLI session.

    Args:
        org_alias: Optional org alias/username. If None, uses default org.

    Returns:
        Dictionary with keys: access_token, instance_url, org_id, username, api_version

    Raises:
        SFAuthError: If authentication info cannot be retrieved
    """
    try:
        # Build sf org display command
        cmd = ["sf", "org", "display", "--json"]

        if org_alias:
            cmd.extend(["--target-org", org_alias])

        logger.info(f"Retrieving auth info for org: {org_alias or 'default'}")

        # Execute command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )

        # Parse JSON response
        response = json.loads(result.stdout)

        # Check for errors in response
        if response.get("status") != 0:
            error_msg = response.get("message", "Unknown error")
            raise SFAuthError(f"SF CLI error: {error_msg}")

        # Extract required fields
        result_data = response.get("result", {})

        auth_info = {
            "access_token": result_data.get("accessToken"),
            "instance_url": result_data.get("instanceUrl"),
            "org_id": result_data.get("id"),
            "username": result_data.get("username"),
            "api_version": result_data.get("apiVersion", "65.0")
        }

        # Validate required fields
        if not auth_info["access_token"] or not auth_info["instance_url"]:
            raise SFAuthError("Missing access token or instance URL in response")

        logger.info(f"Successfully retrieved auth for: {auth_info['username']}")
        logger.debug(f"Instance URL: {auth_info['instance_url']}")

        return auth_info

    except subprocess.CalledProcessError as e:
        error_output = e.stderr if e.stderr else e.stdout
        logger.error(f"SF CLI command failed: {error_output}")
        raise SFAuthError(f"Failed to execute sf CLI: {error_output}")

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse SF CLI output: {e}")
        raise SFAuthError(f"Invalid JSON response from sf CLI: {e}")

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        raise SFAuthError(f"Unexpected error retrieving auth info: {e}")
