"""
Download Stage

Progress tracking for file downloads with detailed throughput information.
"""

import time
from typing import Dict, Any, Optional

from src.progress.stages.base import WorkflowStage, StageConfig

# Configuration for download stage
DOWNLOAD_STAGE_CONFIG = StageConfig(
    name="file_downloads",
    description="Downloading attachment files",
    message_template="Downloading {current}/{total} files - {current_file}",
    details_fields=["current_file", "file_size", "speed", "success_count", "failed_count", "skipped_count", "bytes_transferred"]
)


class DownloadStage(WorkflowStage):
    """Progress stage for file download operations."""
    
    def __init__(self):
        super().__init__(DOWNLOAD_STAGE_CONFIG)
        self._start_time: Optional[float] = None
        self._bytes_transferred = 0

    def start_downloads(self, total_files: int):
        """Start download phase."""
        self._start_time = time.time()
        self._bytes_transferred = 0
        
        self.start(
            total=total_files,
            message=f"Starting download of {total_files} files"
        )

    def update_download(
        self,
        completed_files: int,
        current_file: Optional[str] = None,
        file_size: Optional[int] = None,
        success_count: Optional[int] = None,
        failed_count: Optional[int] = None,
        skipped_count: Optional[int] = None,
        bytes_transferred: Optional[int] = None
    ):
        """Update download progress with throughput calculation."""
        if bytes_transferred is not None:
            self._bytes_transferred = bytes_transferred
        
        # Calculate speed
        speed_str = ""
        if self._start_time and self._bytes_transferred > 0:
            elapsed = max(0.1, time.time() - self._start_time)
            speed_mbps = (self._bytes_transferred / (1024 * 1024)) / elapsed
            speed_str = f"{speed_mbps:.1f} MB/s"
        
        # Format file size
        file_size_str = ""
        if file_size:
            file_size_mb = file_size / (1024 * 1024)
            file_size_str = f"{file_size_mb:.1f} MB"
        
        # Build status counts
        status_parts = []
        if success_count is not None:
            status_parts.append(f"✓{success_count}")
        if failed_count is not None:
            status_parts.append(f"✗{failed_count}")
        if skipped_count is not None:
            status_parts.append(f"⊙{skipped_count}")
        
        # Build message
        message = f"Downloaded {completed_files}/{self.progress.total} files"
        display_file = self._truncate_filename(current_file) if current_file else None
        
        # Build details
        details = {}
        if display_file:
            details['current_file'] = display_file
        if file_size_str:
            details['file_size'] = file_size_str
        if speed_str:
            details['speed'] = speed_str
        if success_count is not None:
            details['success_count'] = success_count
        if failed_count is not None:
            details['failed_count'] = failed_count
        if skipped_count is not None:
            details['skipped_count'] = skipped_count
        if bytes_transferred is not None:
            bytes_mb = bytes_transferred / (1024 * 1024)
            details['bytes_transferred'] = f"{bytes_mb:.1f} MB"
        
        self.update_progress(
            current=completed_files,
            message=message,
            details=details if details else None
        )

    def _truncate_filename(self, filename: Optional[str], max_length: int = 40) -> Optional[str]:
        """Truncate filename to avoid UI width jumps."""
        if not filename:
            return filename
        if len(filename) <= max_length:
            return filename
        return f"{filename[:max_length - 3]}..."

    def complete_downloads(self, total_downloaded: int, total_failed: int = 0, total_skipped: int = 0):
        """Mark download phase as completed."""
        message = f"Downloaded {total_downloaded} file(s)"
        if total_failed > 0:
            message += f" ({total_failed} failed)"
        if total_skipped > 0:
            message += f" ({total_skipped} skipped)"
        
        self.complete(message=message)
 
    def get_display_info(self) -> Dict[str, Any]:

        """Get download-specific information for display."""
        return super().get_display_info()
