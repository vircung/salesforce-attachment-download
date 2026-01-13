"""
CSV Validator Module

Validates CSV files containing attachment metadata.
"""

import csv
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def validate_metadata_csv(csv_path: Path) -> tuple[bool, Optional[str]]:
    """
    Validate that a CSV file has the required structure for attachment metadata.

    Checks that the file exists, is readable, and contains the required columns
    (Id, Name) needed for downloading attachments.

    Args:
        csv_path: Path to the CSV file to validate

    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if CSV is valid, False otherwise
        - error_message: None if valid, error description if invalid

    Example:
        >>> is_valid, error = validate_metadata_csv(Path("data.csv"))
        >>> if not is_valid:
        ...     print(f"Invalid CSV: {error}")
    """
    # Check file exists
    if not csv_path.exists():
        return False, f"CSV file not found: {csv_path.absolute()}"

    # Check file is readable
    if not csv_path.is_file():
        return False, f"Path is not a file: {csv_path.absolute()}"

    try:
        # Try to read and validate structure
        with csv_path.open('r', encoding='utf-8') as f:
            reader = csv.DictReader(f)

            # Check if file is empty
            fieldnames = reader.fieldnames
            if not fieldnames:
                return False, "CSV file is empty or has no header row"

            # Check required columns
            required_columns = ['Id', 'Name']
            recommended_columns = ['ParentId']  # Recommended for filtering

            missing_required = [col for col in required_columns if col not in fieldnames]
            missing_recommended = [col for col in recommended_columns if col not in fieldnames]

            if missing_required:
                return False, (
                    f"CSV is missing required columns: {', '.join(missing_required)}. "
                    f"Found columns: {', '.join(fieldnames)}. "
                    f"Expected format from Salesforce query with columns: Id, Name, ContentType, BodyLength, ParentId, etc."
                )

            # Warn about missing recommended columns (don't fail validation)
            if missing_recommended:
                logger.warning(
                    f"CSV is missing recommended column(s): {', '.join(missing_recommended)}. "
                    f"Filtering by ParentId will not be possible."
                )

            # Check if CSV has any data rows
            try:
                first_row = next(reader)
                # Validate that Id and Name are not empty in first row
                if not first_row.get('Id') or not first_row.get('Id').strip():
                    return False, "CSV has empty 'Id' field in first data row"
                if not first_row.get('Name') or not first_row.get('Name').strip():
                    return False, "CSV has empty 'Name' field in first data row"
            except StopIteration:
                return False, "CSV has header but no data rows"

        return True, None

    except UnicodeDecodeError:
        return False, f"CSV file has invalid encoding. Expected UTF-8."
    except csv.Error as e:
        return False, f"CSV parsing error: {e}"
    except Exception as e:
        return False, f"Unexpected error reading CSV: {e}"
