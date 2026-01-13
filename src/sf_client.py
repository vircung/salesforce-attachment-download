"""
Salesforce REST API Client

Provides a simple client for interacting with Salesforce REST API
using authentication credentials from sf CLI.
"""

import logging
import requests
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class SFAPIError(Exception):
    """Custom exception for Salesforce API errors"""
    pass


class SalesforceClient:
    """
    Simple Salesforce REST API client.

    This client handles authentication and provides methods for
    downloading attachment files.
    """

    def __init__(self, access_token: str, instance_url: str, api_version: str = "65.0"):
        """
        Initialize Salesforce client.

        Args:
            access_token: OAuth access token from sf CLI
            instance_url: Salesforce instance URL (e.g., https://instance.salesforce.com)
            api_version: API version to use (default: 65.0)
        """
        self.access_token = access_token
        self.instance_url = instance_url.rstrip('/')
        self.api_version = api_version
        self.session = requests.Session()

        # Set default headers
        self.session.headers.update({
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        })

        logger.info(f"Initialized SF client for: {instance_url}")

    def download_attachment(
        self,
        attachment_id: str,
        output_path: Path,
        chunk_size: int = 8192
    ) -> None:
        """
        Download an attachment file from Salesforce.

        The Attachment object's Body field provides a REST API endpoint path.
        This method constructs the full URL and downloads the file content.

        Args:
            attachment_id: Salesforce Attachment ID
            output_path: Local file path to save downloaded content
            chunk_size: Size of chunks for streaming download (default: 8KB)

        Raises:
            SFAPIError: If API request fails
        """
        try:
            # Construct Body field endpoint
            # Format: /services/data/v{version}/sobjects/Attachment/{id}/Body
            endpoint = f"/services/data/v{self.api_version}/sobjects/Attachment/{attachment_id}/Body"
            url = f"{self.instance_url}{endpoint}"

            logger.info(f"Downloading attachment: {attachment_id}")
            logger.debug(f"URL: {url}")

            # Make GET request with streaming enabled
            response = self.session.get(url, stream=True)

            # Check for HTTP errors
            if response.status_code == 404:
                logger.error(f"Attachment not found: {attachment_id}")
                raise SFAPIError(f"Attachment {attachment_id} not found (404)")

            response.raise_for_status()

            # Create parent directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Download file in chunks (memory efficient)
            bytes_downloaded = 0
            with output_path.open('wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:  # Filter out keep-alive chunks
                        f.write(chunk)
                        bytes_downloaded += len(chunk)

            logger.info(f"Downloaded {bytes_downloaded} bytes to: {output_path.name}")

        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error downloading {attachment_id}: {e}")
            raise SFAPIError(f"HTTP error: {e}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {attachment_id}: {e}")
            raise SFAPIError(f"Request failed: {e}")

        except IOError as e:
            logger.error(f"File write error for {output_path}: {e}")
            raise SFAPIError(f"File write error: {e}")

        except Exception as e:
            logger.error(f"Unexpected error downloading {attachment_id}: {e}")
            raise SFAPIError(f"Unexpected error: {e}")

    def close(self):
        """Close the session"""
        self.session.close()
        logger.debug("Closed SF client session")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensure session is closed"""
        self.close()
        return False
