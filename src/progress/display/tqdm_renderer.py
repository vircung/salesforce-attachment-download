"""
tqdm Progress Renderer

Provides fallback progress display using tqdm for broader compatibility.
"""

import sys
from threading import RLock
from typing import Dict, Optional, TextIO, TYPE_CHECKING

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    tqdm = None

if TYPE_CHECKING:
    from tqdm import tqdm as tqdm_type

from src.progress.core.tracker import ProgressRenderer
from src.progress.core.stage import StageStatus, StageProgress


class TqdmProgressRenderer(ProgressRenderer):
    """
    tqdm-based progress renderer for compatibility.
    
    Features:
    - Simple progress bars for each stage
    - Compatible with most terminal environments
    - Fallback when Rich is not available
    """

    def __init__(self, file: Optional[TextIO] = None, disable_on_non_tty: bool = True):
        """
        Initialize tqdm progress renderer.
        
        Args:
            file: Output stream (defaults to stderr)
            disable_on_non_tty: Disable progress when not in TTY environment
        """
        self.file = file or sys.stderr
        self.disable_on_non_tty = disable_on_non_tty
        self._lock = RLock()
        self._progress_bars: Dict[str, "tqdm_type"] = {}
        self._stage_data: Dict[str, StageProgress] = {}
        self._is_started = False

    def is_available(self) -> bool:
        """Check if tqdm is available."""
        return TQDM_AVAILABLE

    def start(self):
        """Start tqdm progress display."""
        if not TQDM_AVAILABLE:
            return
        
        with self._lock:
            if self._is_started:
                return
            
            self._is_started = True
            # tqdm bars are created on-demand when stages update

    def stop(self):
        """Stop tqdm progress display."""
        if not TQDM_AVAILABLE:
            return
        
        with self._lock:
            if not self._is_started:
                return
            
            # Close all progress bars
            for pbar in self._progress_bars.values():
                try:
                    pbar.close()
                except Exception:
                    pass
            
            self._progress_bars.clear()
            self._is_started = False

    def update_stage(self, stage_name: str, stage_progress: StageProgress):
        """Update progress for a specific stage."""
        if not TQDM_AVAILABLE or not self._is_started:
            return
        
        with self._lock:
            self._stage_data[stage_name] = stage_progress
            
            # Create progress bar if it doesn't exist
            if stage_name not in self._progress_bars:
                self._create_progress_bar(stage_name, stage_progress)
            else:
                self._update_progress_bar(stage_name, stage_progress)

    def _create_progress_bar(self, stage_name: str, stage_progress: StageProgress):
        """Create a new tqdm progress bar for a stage."""
        if tqdm is None:
            return

        # Format description
        description = self._format_description(stage_name, stage_progress)
        
        # Determine if progress should be disabled
        disable_progress = (
            self.disable_on_non_tty and 
            not self.file.isatty() if hasattr(self.file, 'isatty') else False
        )
        
        # Create progress bar
        total = stage_progress.total if stage_progress.total and stage_progress.total > 0 else None
        
        pbar = tqdm(
            desc=description,
            total=total,
            initial=stage_progress.current,
            file=self.file,
            disable=disable_progress,
            ascii=True,  # For broader compatibility
            unit='items',
            dynamic_ncols=True,
            position=len(self._progress_bars)  # Stack progress bars
        )
        
        self._progress_bars[stage_name] = pbar

    def _update_progress_bar(self, stage_name: str, stage_progress: StageProgress):
        """Update an existing tqdm progress bar."""
        if stage_name not in self._progress_bars:
            return
        
        pbar = self._progress_bars[stage_name]
        
        try:
            # Update description
            description = self._format_description(stage_name, stage_progress)
            pbar.set_description(description)
            
            # Update total if it has changed
            if stage_progress.total and stage_progress.total != pbar.total:
                pbar.total = stage_progress.total
                pbar.refresh()
            
            # Update progress
            if stage_progress.current is not None:
                # Calculate difference to update by
                current_pos = getattr(pbar, 'n', 0)
                diff = stage_progress.current - current_pos
                if diff != 0:
                    pbar.update(diff)
            
            # Handle completion/failure
            if stage_progress.status == StageStatus.COMPLETED:
                if pbar.total:
                    pbar.n = pbar.total
                pbar.set_description(f"✓ {description}")
                pbar.refresh()
            elif stage_progress.status == StageStatus.FAILED:
                pbar.set_description(f"✗ {description}")
                if stage_progress.error:
                    pbar.write(f"Error in {stage_name}: {stage_progress.error}")
                pbar.refresh()
            elif stage_progress.status == StageStatus.SKIPPED:
                pbar.set_description(f"⊙ {description}")
                pbar.refresh()
                
        except Exception:
            # Ignore errors in progress bar updates
            pass

    def _format_description(self, stage_name: str, stage_progress: StageProgress) -> str:
        """Format description for tqdm progress bar."""
        # Convert stage name to display format
        display_name = stage_name.replace('_', ' ').title()
        
        # Add status indicator
        status_indicators = {
            StageStatus.PENDING: "⏳",
            StageStatus.RUNNING: "🔄",
            StageStatus.COMPLETED: "✓",
            StageStatus.FAILED: "✗", 
            StageStatus.SKIPPED: "⊙"
        }
        
        indicator = status_indicators.get(stage_progress.status, "•")
        base_desc = f"{indicator} {display_name}"
        
        # Add message if available
        if stage_progress.message:
            base_desc += f": {stage_progress.message}"
        
        # Add key details in a compact format
        if stage_progress.details:
            details_parts = []
            for key, value in stage_progress.details.items():
                if key in ['current_file', 'current_csv', 'current_batch', 'csv_name'] and value:
                    # Shorten file names for display
                    if isinstance(value, str) and len(value) > 20:
                        value = "..." + value[-17:]
                    details_parts.append(f"{key.split('_')[-1]}: {value}")
            
            if details_parts:
                base_desc += f" ({', '.join(details_parts[:2])})"  # Limit to 2 details
        
        return base_desc

    def write_message(self, message: str):
        """Write a message above all progress bars."""
        if not TQDM_AVAILABLE or not self._is_started:
            print(message, file=self.file)
            return
        
        # Use tqdm.write to properly display message above progress bars
        if self._progress_bars:
            # Use any progress bar to write the message
            first_pbar = next(iter(self._progress_bars.values()))
            first_pbar.write(message)
        else:
            print(message, file=self.file)


# Utility function to check tqdm availability
def is_tqdm_available() -> bool:
    """Check if tqdm library is available."""
    return TQDM_AVAILABLE