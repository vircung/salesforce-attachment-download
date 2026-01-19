"""
Directory Manager Module

Manages workflow directory structure and temporary directory lifecycle.
Provides consistent directory naming and creation across workflow phases.
"""

import logging
from pathlib import Path
import shutil
from dataclasses import dataclass

from src.workflows.common import ensure_directories
from src.api.sf_client import DEFAULT_TMP_DIR_NAME

logger = logging.getLogger(__name__)


@dataclass
class CsvDirectories:
    """Directory structure for a single CSV file."""
    csv_output_dir: Path
    metadata_dir: Path
    files_dir: Path


def create_csv_directories(
    output_dir: Path,
    csv_name: str
) -> CsvDirectories:
    """
    Create and return directory structure for a CSV file.

    Creates directories:
      - {output_dir}/{csv_name}/
      - {output_dir}/{csv_name}/metadata/
      - {output_dir}/{csv_name}/files/

    Args:
        output_dir: Base output directory
        csv_name: Name of the CSV file (used in path)

    Returns:
        CsvDirectories with all three paths

    Raises:
        Exception: If directory creation fails
    """
    # Create output_dir / csv_name (csv_output_dir)
    csv_output_dir = output_dir / csv_name

    # Create metadata_dir (csv_output_dir / 'metadata')
    metadata_dir = csv_output_dir / 'metadata'

    # Create files_dir (csv_output_dir / 'files')
    files_dir = csv_output_dir / 'files'

    # Use ensure_directories() from src.workflows.common
    ensure_directories(csv_output_dir, metadata_dir, files_dir)

    # Log directory creation
    logger.info(f"Output directories:")
    logger.info(f"  Metadata: {metadata_dir}")
    logger.info(f"  Files: {files_dir}")

    # Return CsvDirectories with all three paths
    return CsvDirectories(
        csv_output_dir=csv_output_dir,
        metadata_dir=metadata_dir,
        files_dir=files_dir
    )


def get_temp_download_dir(output_dir: Path) -> Path:
    """
    Get path to global temp download directory.

    Path: {output_dir}/.tmp_downloads/

    Note: Does NOT create the directory, just returns the path.
    """
    # Return output_dir / DEFAULT_TMP_DIR_NAME
    return output_dir / DEFAULT_TMP_DIR_NAME


def clean_temp_directory(temp_dir: Path) -> None:
    """
    Clean temp directory if it exists.
    Silently ignores if directory doesn't exist or already clean.
    """
    # Use shutil.rmtree() to clean directory
    # Wrap in try/except to silently ignore missing directories
    try:
        if temp_dir.exists():
            shutil.rmtree(temp_dir)
            logger.info(f"Cleaned temp directory: {temp_dir}")
    except Exception as e:
        logger.debug(f"Could not clean temp directory {temp_dir}: {e}")