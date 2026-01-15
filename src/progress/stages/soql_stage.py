"""
SOQL Query Stage

Progress tracking for SOQL query execution and batch processing.
"""

from typing import Dict, Any, Optional

from src.progress.core.stage import ProgressStage


class SoqlQueryStage(ProgressStage):
    """
    Progress stage for SOQL query operations.
    
    Tracks:
    - Total batches to execute
    - Current batch being processed
    - Records found per batch
    - Cumulative attachments found
    """

    def __init__(self):
        super().__init__(
            name="soql_query",
            description="Executing SOQL queries for attachments"
        )

    def start_querying(self, total_batches: int, csv_name: Optional[str] = None):
        """Start SOQL querying phase."""
        message = f"Querying attachments ({total_batches} batches)"
        if csv_name:
            message += f" for {csv_name}"
        
        self.start(
            total=total_batches,
            message=message
        )
        
        if csv_name:
            self.update_progress(details={"csv_name": csv_name})

    def update_batch(
        self,
        completed_batches: int,
        current_batch: Optional[int] = None,
        batch_size: Optional[int] = None,
        records_found: Optional[int] = None,
        total_attachments: Optional[int] = None
    ):
        """Update batch processing progress."""
        details = {}
        
        if current_batch is not None:
            details["current_batch"] = current_batch
        
        if batch_size is not None:
            details["batch_size"] = batch_size
        
        if records_found is not None:
            details["batch_records"] = records_found
        
        if total_attachments is not None:
            details["total_attachments"] = total_attachments
        
        # Build message
        message_parts = []
        if current_batch is not None:
            message_parts.append(f"Batch {current_batch}/{self.progress.total}")
        else:
            message_parts.append(f"Completed {completed_batches}/{self.progress.total} batches")
        
        if records_found is not None:
            message_parts.append(f"Found {records_found} attachments")
        
        if total_attachments is not None:
            message_parts.append(f"Total: {total_attachments}")
        
        self.update_progress(
            current=completed_batches,
            message=" | ".join(message_parts),
            details=details
        )

    def complete_batch(
        self, 
        batch_num: int, 
        records_found: int, 
        total_attachments: int
    ):
        """Mark a batch as completed."""
        current = self.progress.current + 1
        
        self.update_progress(
            current=current,
            message=f"Batch {batch_num} complete: {records_found} attachments",
            details={
                "last_batch": batch_num,
                "last_batch_records": records_found,
                "total_attachments": total_attachments
            }
        )

    def start_csv_batches(self, csv_name: str, total_batches: int):
        """Start processing batches for a specific CSV."""
        self.update_progress(
            current=0,
            total=total_batches,
            message=f"Processing {csv_name} ({total_batches} batches)",
            details={
                "csv_name": csv_name,
                "csv_batches": total_batches
            }
        )

    def get_display_info(self) -> Dict[str, Any]:
        """Get SOQL query display information."""
        progress = self.progress
        
        info = {
            "stage": "SOQL Queries",
            "status": progress.status.value,
            "progress": f"{progress.current}/{progress.total}" if progress.total else str(progress.current),
            "details": []
        }
        
        # Add current batch info
        if "current_batch" in progress.details:
            info["details"].append(f"Batch: {progress.details['current_batch']}")
        
        # Add CSV being processed
        if "csv_name" in progress.details:
            info["details"].append(f"CSV: {progress.details['csv_name']}")
        
        # Add batch size
        if "batch_size" in progress.details:
            info["details"].append(f"Batch size: {progress.details['batch_size']}")
        
        # Add records found
        if "batch_records" in progress.details:
            info["details"].append(f"Batch records: {progress.details['batch_records']}")
        
        if "total_attachments" in progress.details:
            info["details"].append(f"Total attachments: {progress.details['total_attachments']}")
        
        return info