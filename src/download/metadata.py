"""
Metadata Reader

Functions for reading and validating attachment metadata from CSV files.
"""

import csv
import logging
from pathlib import Path
from typing import List, Dict

logger = logging.getLogger(__name__)


def read_metadata_csv(csv_path: Path) -> List[Dict[str, str]]:
    """
    Read attachment metadata from CSV file.

    Expected columns: Id, Name, ContentType, BodyLength, ParentId, etc.

    Args:
        csv_path: Path to CSV file containing attachment metadata

    Returns:
        List of dictionaries with attachment metadata

    Raises:
        FileNotFoundError: If CSV file does not exist
        ValueError: If CSV is missing required columns (Id, Name, ParentId)
    """
    logger.debug(f"Reading metadata from: {csv_path}")

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Metadata CSV file not found at path: {csv_path.absolute()}. "
            f"Please ensure the file exists and the path is correct."
        )

    attachments = []
    with csv_path.open('r', encoding='utf-8') as f:
        reader = csv.DictReader(f)

        # Validate required columns
        required_cols = ['Id', 'Name', 'ParentId']
        if not all(col in reader.fieldnames for col in required_cols):
            raise ValueError(f"CSV missing required columns: {required_cols}")

        for row in reader:
            attachments.append(row)

    logger.debug(f"Found {len(attachments)} attachments in metadata")
    return attachments
