"""
CSV Processing Stage

Progress tracking for CSV file discovery, processing, and ID extraction.
"""

from pathlib import Path
from typing import Dict, Any, Optional

from src.progress.stages.base import WorkflowStage, StageConfig

# Configuration for CSV processing stage
CSV_STAGE_CONFIG = StageConfig(
    name="csv_processing",
    description="Discovering and processing CSV files",
    message_template="Processing CSV files ({current}/{total})",
    details_fields=["current_csv", "current_records", "total_records", "files_found"]
)


class CsvProcessingStage(WorkflowStage):
    """Progress stage for CSV processing operations."""
    
    def __init__(self):
        super().__init__(CSV_STAGE_CONFIG)

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
        
        self.update_progress(
            current=completed_files,
            message=f"Processing CSV files ({completed_files}/{self.progress.total})",
            details=details if details else None
        )

    def complete_file(self, filename: str, file_records: int, total_records: int):
        """Mark a CSV file as complete."""
        self.update_progress(
            message=f"Completed {filename}: {file_records} records",
            details={"last_file": filename, "total_records": total_records}
        )

    def get_display_info(self) -> Dict[str, Any]:
        """Get CSV-specific information for display."""
        return super().get_display_info()
