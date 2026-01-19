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

    def estimate_total_files(self, records_dir: Path) -> int:
        """
        Quick estimate of total CSV files in directory.
        
        Scans directory for .csv files (no subdirectories) to get
        initial total estimate. Called before full discovery starts.
        
        Args:
            records_dir: Directory containing CSV files
            
        Returns:
            Count of .csv files found, or 0 if error
        """
        try:
            csv_files = list(records_dir.glob("*.csv"))
            return len(csv_files)
        except Exception:
            return 0  # Fallback: return 0 if scan fails

    def set_processing_total(self, estimated_files: int) -> None:
        """
        Pre-populate processing total with initial estimate.
        
        Starts the processing stage with estimated file count
        so progress is visible from the start.
        
        Args:
            estimated_files: Estimated number of CSV files
        """
        self.start(
            total=estimated_files,
            message="Processing CSV files"
        )

    def get_display_info(self) -> Dict[str, Any]:
        """Get CSV-specific information for display."""
        return super().get_display_info()
