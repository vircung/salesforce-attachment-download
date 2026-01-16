"""
SOQL Query Stage

Progress tracking for SOQL query execution and batch processing.
"""

from typing import Dict, Any, Optional

from src.progress.stages.base import WorkflowStage, StageConfig

# Configuration for SOQL query stage
SOQL_STAGE_CONFIG = StageConfig(
    name="soql_query",
    description="Executing SOQL queries for attachments",
    message_template="Batch {current_batch}/{total} - Found {total_attachments} attachments",
    details_fields=["current_csv", "current_batch", "batch_size", "batch_records", "total_attachments"]
)


class SoqlQueryStage(WorkflowStage):
    """Progress stage for SOQL query operations."""
    
    def __init__(self):
        super().__init__(SOQL_STAGE_CONFIG)

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
            self.update_progress(details={"current_csv": csv_name})

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
            details=details if details else None
        )

    def complete_batch(
        self, 
        message: str = "",
        batch_num: Optional[int] = None,
        records_found: Optional[int] = None,
        total_attachments: Optional[int] = None
    ):
        """Mark batch as complete."""
        # Build message from parameters if not provided
        if not message and batch_num is not None:
            msg_parts = [f"Batch {batch_num}"]
            if records_found is not None:
                msg_parts.append(f"found {records_found}")
            if total_attachments is not None:
                msg_parts.append(f"total {total_attachments}")
            message = " ".join(msg_parts)
        
        # Update with current progress
        if batch_num is not None or total_attachments is not None:
            details = {}
            if batch_num is not None:
                details["current_batch"] = batch_num
            if total_attachments is not None:
                details["total_attachments"] = total_attachments
            
            self.update_progress(
                message=message,
                details=details if details else None
            )
        else:
            self.complete(message)

    def get_display_info(self) -> Dict[str, Any]:
        """Get SOQL-specific information for display."""
        return super().get_display_info()
