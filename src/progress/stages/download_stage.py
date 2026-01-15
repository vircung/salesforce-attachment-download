"""
Download Stage

Progress tracking for file downloads with detailed throughput information.
"""

import time
from pathlib import Path
from typing import Dict, Any, Optional

from src.progress.core.stage import ProgressStage


class DownloadStage(ProgressStage):
    """
    Progress stage for file download operations.
    
    Tracks:
    - Total files to download
    - Current file being downloaded
    - Download speed/throughput
    - Success/failure/skip counts
    - Bytes transferred
    """

    def __init__(self):
        super().__init__(
            name="file_downloads",
            description="Downloading attachment files"
        )
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
        """Update download progress."""
        details = {}
        
        if current_file:
            # Shorten long filenames for display
            display_name = Path(current_file).name
            if len(display_name) > 40:
                display_name = display_name[:37] + "..."
            details["current_file"] = display_name
        
        if file_size is not None:
            details["file_size"] = self._format_bytes(file_size)
        
        if success_count is not None:
            details["success_count"] = success_count
        
        if failed_count is not None:
            details["failed_count"] = failed_count
        
        if skipped_count is not None:
            details["skipped_count"] = skipped_count
        
        # Update bytes transferred
        if bytes_transferred is not None:
            self._bytes_transferred = bytes_transferred
        
        # Calculate speed
        speed = self._calculate_speed()
        if speed:
            details["speed"] = speed
        
        # Build message
        message_parts = [f"Downloading files ({completed_files}/{self.progress.total})"]
        
        if current_file:
            message_parts.append(f"Current: {details['current_file']}")
        
        # Add counts summary
        counts = []
        if success_count is not None:
            counts.append(f"✓{success_count}")
        if failed_count is not None and failed_count > 0:
            counts.append(f"✗{failed_count}")
        if skipped_count is not None and skipped_count > 0:
            counts.append(f"⊙{skipped_count}")
        
        if counts:
            message_parts.append(f"[{'/'.join(counts)}]")
        
        if speed:
            message_parts.append(speed)
        
        self.update_progress(
            current=completed_files,
            message=" | ".join(message_parts),
            details=details
        )

    def complete_file(
        self, 
        filename: str, 
        file_size: Optional[int] = None,
        success: bool = True,
        skipped: bool = False
    ):
        """Mark a file download as completed."""
        current = self.progress.current + 1
        
        # Update byte counter
        if file_size and success:
            self._bytes_transferred += file_size
        
        # Update progress details
        details = self.progress.details.copy()
        
        if success and not skipped:
            details["success_count"] = details.get("success_count", 0) + 1
        elif skipped:
            details["skipped_count"] = details.get("skipped_count", 0) + 1
        else:
            details["failed_count"] = details.get("failed_count", 0) + 1
        
        # Calculate updated speed
        speed = self._calculate_speed()
        if speed:
            details["speed"] = speed
        
        # Build completion message
        status_icon = "✓" if success else ("⊙" if skipped else "✗")
        display_name = Path(filename).name
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."
        
        message = f"{status_icon} {display_name}"
        if file_size and success:
            message += f" ({self._format_bytes(file_size)})"
        
        self.update_progress(
            current=current,
            message=message,
            details=details
        )

    def fail_file(self, filename: str, error: str):
        """Mark a file download as failed."""
        current = self.progress.current + 1
        
        details = self.progress.details.copy()
        details["failed_count"] = details.get("failed_count", 0) + 1
        
        display_name = Path(filename).name
        if len(display_name) > 30:
            display_name = display_name[:27] + "..."
        
        self.update_progress(
            current=current,
            message=f"✗ {display_name}: {error}",
            details=details
        )

    def _calculate_speed(self) -> Optional[str]:
        """Calculate current download speed."""
        if not self._start_time or self._bytes_transferred <= 0:
            return None
        
        elapsed = time.time() - self._start_time
        if elapsed <= 0:
            return None
        
        bytes_per_second = self._bytes_transferred / elapsed
        return self._format_bytes(bytes_per_second) + "/s"

    def _format_bytes(self, bytes_count: int | float) -> str:
        """Format byte count for human reading."""
        if bytes_count < 1024:
            return f"{bytes_count:.0f}B"
        elif bytes_count < 1024 * 1024:
            return f"{bytes_count / 1024:.1f}KB"
        elif bytes_count < 1024 * 1024 * 1024:
            return f"{bytes_count / (1024 * 1024):.1f}MB"
        else:
            return f"{bytes_count / (1024 * 1024 * 1024):.1f}GB"

    def get_display_info(self) -> Dict[str, Any]:
        """Get download stage display information."""
        progress = self.progress
        
        info = {
            "stage": "File Downloads",
            "status": progress.status.value,
            "progress": f"{progress.current}/{progress.total}" if progress.total else str(progress.current),
            "details": []
        }
        
        # Add current file
        if "current_file" in progress.details:
            info["details"].append(f"File: {progress.details['current_file']}")
        
        # Add download speed
        if "speed" in progress.details:
            info["details"].append(f"Speed: {progress.details['speed']}")
        
        # Add file size
        if "file_size" in progress.details:
            info["details"].append(f"Size: {progress.details['file_size']}")
        
        # Add success/fail/skip counts
        counts = []
        if "success_count" in progress.details:
            counts.append(f"✓{progress.details['success_count']}")
        if "failed_count" in progress.details and progress.details['failed_count'] > 0:
            counts.append(f"✗{progress.details['failed_count']}")
        if "skipped_count" in progress.details and progress.details['skipped_count'] > 0:
            counts.append(f"⊙{progress.details['skipped_count']}")
        
        if counts:
            info["details"].append(f"Status: {'/'.join(counts)}")
        
        # Add bytes transferred
        if self._bytes_transferred > 0:
            info["details"].append(f"Transferred: {self._format_bytes(self._bytes_transferred)}")
        
        return info