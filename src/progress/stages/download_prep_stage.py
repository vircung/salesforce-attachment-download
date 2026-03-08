"""
Download Prep Stage

Progress tracking for pre-download scanning and batch splitting.
"""

from typing import Dict, Any

from src.progress.stages.base import WorkflowStage, StageConfig

DOWNLOAD_PREP_STAGE_CONFIG = StageConfig(
    name="download_prep",
    description="Preparing downloads",
    message_template="Scanning {current}/{total} objects",
    details_fields=["object_name", "to_download", "skipped"]
)


class DownloadPrepStage(WorkflowStage):
    """Progress stage for download preparation (scan, collision detection, split)."""

    def __init__(self):
        super().__init__(DOWNLOAD_PREP_STAGE_CONFIG)

    def start_prep(self, total_objects: int):
        """Start prep phase."""
        self.start(
            total=total_objects,
            message=f"Preparing downloads for {total_objects} objects"
        )

    def update_object(self, object_idx: int, object_name: str,
                      to_download: int, skipped: int):
        """Update progress for one object.

        Args:
            object_idx: 1-indexed object number
            object_name: CSV/object name for display
            to_download: number of files to download for this object
            skipped: skipped_existing + skipped_permanent for this object
        """
        message = f"Scanning {object_idx}/{self._progress.total} objects"

        details: Dict[str, Any] = {
            'object_name': object_name,
            'to_download': to_download,
            'skipped': skipped,
        }

        self.update_progress(
            current=object_idx,
            message=message,
            details=details,
        )

    def complete_prep(self, total_to_download: int, total_skipped: int):
        """Mark prep phase as completed."""
        message = f"Prepared {total_to_download} files for download, {total_skipped} skipped"
        self.complete(message=message)
