"""
CSV Processing Stage

Progress tracking for CSV file discovery, processing, and ID extraction.
"""

from pathlib import Path
from typing import Dict, Any, Optional

from src.progress.core.stage import ProgressStage


class CsvProcessingStage(ProgressStage):
    """
    Progress stage for CSV processing operations.
    
    Tracks:
    - CSV files discovered
    - Current CSV being processed
    - Records extracted per CSV
    - Total records across all CSVs
    """

    def __init__(self):
        super().__init__(
            name="csv_processing",
            description="Discovering and processing CSV files"
        )

    def start_discovery(self, records_dir: Path):
        """Start CSV discovery phase."""
        self.update_progress(
            current=0,
            message=f"Discovering CSV files in {records_dir.name}",
            details={"records_dir": str(records_dir)}
        )

    def update_discovery(self, files_found: int, current_file: Optional[str] = None):
        """Update CSV discovery progress."""
        details = {"files_found": files_found}
        if current_file:
            details["current_file"] = current_file
        
        self.update_progress(
            current=files_found,
            message=f"Found {files_found} CSV file(s)",
            details=details
        )

    def start_processing(self, total_files: int):
        """Start CSV processing phase."""
        self.start(
            total=total_files,
            message="Processing CSV files"
        )

    def update_processing(
        self, 
        completed_files: int,
        current_csv: Optional[str] = None,
        current_records: Optional[int] = None,
        total_records: Optional[int] = None
    ):
        """Update CSV processing progress."""
        details = {}
        
        if current_csv:
            details["current_csv"] = current_csv
        
        if current_records is not None:
            details["current_records"] = current_records
        
        if total_records is not None:
            details["total_records"] = total_records
        
        message_parts = [f"Processing CSV files ({completed_files}/{self.progress.total})"]
        
        if current_csv:
            message_parts.append(f"Current: {current_csv}")
        
        if total_records is not None:
            message_parts.append(f"Total records: {total_records}")
        
        self.update_progress(
            current=completed_files,
            message=" | ".join(message_parts),
            details=details
        )

    def complete_file(self, csv_name: str, records_count: int, total_records: int):
        """Mark a CSV file as completed."""
        current = self.progress.current + 1
        
        self.update_progress(
            current=current,
            message=f"Completed {csv_name} ({records_count} records)",
            details={
                "completed_csv": csv_name,
                "csv_records": records_count,
                "total_records": total_records
            }
        )

    def get_display_info(self) -> Dict[str, Any]:
        """Get CSV processing display information."""
        progress = self.progress
        
        info = {
            "stage": "CSV Processing",
            "status": progress.status.value,
            "progress": f"{progress.current}/{progress.total}" if progress.total else str(progress.current),
            "details": []
        }
        
        # Add current file info
        if "current_csv" in progress.details:
            info["details"].append(f"Processing: {progress.details['current_csv']}")
        
        if "current_file" in progress.details:
            info["details"].append(f"File: {progress.details['current_file']}")
        
        # Add record counts
        if "total_records" in progress.details:
            info["details"].append(f"Total records: {progress.details['total_records']}")
        
        if "current_records" in progress.details:
            info["details"].append(f"Current: {progress.details['current_records']} records")
        
        # Add files found during discovery
        if "files_found" in progress.details:
            info["details"].append(f"Files found: {progress.details['files_found']}")
        
        return info