"""
Progress-aware download functionality.

Wraps the main download function with progress tracking capabilities.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from src.api.sf_auth import get_sf_auth_info
from src.api.sf_client import SalesforceClient
from src.exceptions import SFAuthError, SFAPIError
from src.query.filters import ParentIdFilter, apply_parent_id_filter, log_filter_summary
from src.download.metadata import read_metadata_csv
from src.download.filename import (
    FilenameInfo,
    DEFAULT_PARENT_ID,
    sanitize_filename,
    detect_filename_collisions,
)
from src.download.stats import DownloadStats
from src.progress.stages.download_stage import DownloadStage

logger = logging.getLogger(__name__)


def download_attachments_with_progress(
    metadata_csv: Path,
    output_dir: Path,
    progress_stage: DownloadStage,
    org_alias: Optional[str] = None,
    chunk_size: int = 8192,
    filter_config: Optional[ParentIdFilter] = None
) -> Dict[str, Any]:
    """
    Download attachments with progress tracking.
    
    This is a progress-aware wrapper around the main download functionality.
    
    Args:
        metadata_csv: Path to CSV file with attachment metadata
        output_dir: Directory to save downloaded files
        progress_stage: Progress stage to update during downloads
        org_alias: Optional Salesforce org alias (uses default org if None)
        chunk_size: Download chunk size in bytes (default: 8192)
        filter_config: Optional filter configuration for ParentId filtering

    Returns:
        Dictionary with summary statistics
    """
    stats = DownloadStats()

    try:
        # Step 1: Get SF authentication
        logger.debug("Retrieving Salesforce authentication")
        auth_info = get_sf_auth_info(org_alias)
        logger.debug(f"Authenticated as: {auth_info['username']}")

        # Step 2: Initialize SF client
        logger.debug("Initializing Salesforce API client")
        
        with SalesforceClient(
            access_token=auth_info['access_token'],
            instance_url=auth_info['instance_url'],
            api_version=auth_info['api_version']
        ) as client:

            # Step 3: Read metadata
            logger.debug("Reading attachment metadata")
            attachments = read_metadata_csv(metadata_csv)
            original_count = len(attachments)

            # Step 3.5: Apply filtering if configured
            if filter_config and filter_config.has_filters() and filter_config.strategy == 'python':
                logger.debug("Applying ParentId filter")
                attachments = apply_parent_id_filter(attachments, filter_config)
                log_filter_summary(original_count, len(attachments), filter_config)

                # If no attachments match, exit gracefully
                if len(attachments) == 0:
                    logger.warning("No attachments matched the filter criteria. Skipping download phase.")
                    stats.total = 0
                    progress_stage.skip("No attachments match filter criteria")
                    return stats.to_dict()

            stats.total = len(attachments)

            # Step 3.6: Detect filename collisions
            logger.debug("Analyzing filename collisions")
            filename_info_map = detect_filename_collisions(attachments)
            logger.debug(f"Collision analysis complete for {len(attachments)} attachments")

            # Step 4: Start downloads with progress tracking
            logger.info(f"Downloading {stats.total} attachment(s)...")
            progress_stage.start_downloads(stats.total)
            
            output_dir.mkdir(parents=True, exist_ok=True)

            for idx, attachment in enumerate(attachments, 1):
                attachment_id = attachment['Id']
                parent_id = attachment.get('ParentId', DEFAULT_PARENT_ID)
                original_name = attachment['Name']

                # Get pre-computed filename info
                filename_info = filename_info_map.get(attachment_id)
                if filename_info:
                    safe_name = filename_info.safe_name
                    has_collision = filename_info.has_collision
                else:
                    safe_name = sanitize_filename(original_name)
                    has_collision = False

                # Determine filename based on collision detection
                if has_collision:
                    output_filename = f"{parent_id}_{attachment_id}_{safe_name}"
                else:
                    output_filename = f"{parent_id}_{safe_name}"

                output_path = output_dir / output_filename

                # Path traversal validation
                try:
                    resolved_path = output_path.resolve()
                    resolved_output_dir = output_dir.resolve()
                    if not str(resolved_path).startswith(str(resolved_output_dir)):
                        logger.error(f"Path traversal attempt detected: {original_name}")
                        stats.failed += 1
                        stats.errors.append({
                            'id': attachment_id,
                            'name': original_name,
                            'error': 'Path traversal validation failed'
                        })
                        progress_stage.fail_file(original_name, "Path traversal validation failed")
                        continue
                except (OSError, ValueError) as e:
                    logger.error(f"Path validation error for {original_name}: {e}")
                    stats.failed += 1
                    stats.errors.append({
                        'id': attachment_id,
                        'name': original_name,
                        'error': f'Path validation error: {e}'
                    })
                    progress_stage.fail_file(original_name, f"Path validation error: {e}")
                    continue

                # Update progress with current file
                progress_stage.update_download(
                    completed_files=idx - 1,
                    current_file=original_name,
                    success_count=stats.success,
                    failed_count=stats.failed,
                    skipped_count=stats.skipped
                )

                logger.info(f"[{idx}/{stats.total}] {original_name}")

                # Check if file already exists
                if output_path.exists():
                    logger.info(f"  ⊙ Skipped (already exists)")
                    stats.skipped += 1
                    progress_stage.complete_file(
                        original_name, 
                        file_size=None, 
                        success=True, 
                        skipped=True
                    )
                    continue

                try:
                    # Download with progress indication
                    file_size = client.download_attachment(attachment_id, output_path, chunk_size=chunk_size)
                    stats.success += 1
                    logger.info(f"  ✓ Downloaded")
                    
                    # Update progress with successful download
                    progress_stage.complete_file(
                        original_name,
                        file_size=file_size,
                        success=True,
                        skipped=False
                    )

                except SFAPIError as e:
                    stats.failed += 1
                    error_msg = str(e)
                    stats.errors.append({
                        'id': attachment_id,
                        'name': original_name,
                        'error': error_msg
                    })
                    logger.error(f"  ✗ Error: {error_msg}")
                    
                    # Update progress with failed download
                    progress_stage.fail_file(original_name, error_msg)
                    continue

        # Summary
        logger.info(f"Download complete: {stats.success} downloaded, {stats.skipped} skipped, {stats.failed} failed")

        if stats.errors:
            logger.warning("\nFailed downloads:")
            for error in stats.errors:
                logger.warning(f"  - {error['name']} (ID: {error['id']}): {error['error']}")

        return stats.to_dict()

    except SFAuthError as e:
        logger.error(f"Authentication failed: {e}")
        progress_stage.fail(str(e), "Authentication failed")
        raise

    except FileNotFoundError as e:
        logger.error(f"File not found: {e}")
        progress_stage.fail(str(e), "File not found")
        raise

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        progress_stage.fail(str(e), "Unexpected error")
        raise