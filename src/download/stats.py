"""
Download Statistics

Data classes for tracking download operation statistics.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any
import threading


@dataclass
class DownloadStats:
    """Statistics for attachment download operations."""
    total: int = 0
    success: int = 0
    failed: int = 0
    skipped: int = 0
    completed: int = 0
    bytes_transferred: int = 0
    errors: List[Dict[str, str]] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        with self.lock:
            return {
                'total': self.total,
                'success': self.success,
                'failed': self.failed,
                'skipped': self.skipped,
                'completed': self.completed,
                'bytes_transferred': self.bytes_transferred,
                'errors': self.errors
            }
