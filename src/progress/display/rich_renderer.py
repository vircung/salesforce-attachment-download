"""
Rich Progress Renderer

Provides sophisticated hierarchical progress display using the Rich library.
Integrates with LoggingManager to display critical errors during progress tracking.
"""

import logging
import time
from threading import RLock
from typing import Dict, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    Progress, TaskID, BarColumn, TextColumn, 
    TimeElapsedColumn, TimeRemainingColumn, SpinnerColumn
)
from rich.table import Table
from rich.text import Text

from src.progress.core.tracker import ProgressRenderer
from src.progress.core.stage import StageStatus, StageProgress

logger = logging.getLogger(__name__)


class RichProgressRenderer(ProgressRenderer):
    """
    Rich-based progress renderer with hierarchical display.
    
    Features:
    - Tree-style hierarchical layout
    - Individual progress bars for each stage
    - Detailed sub-information for each stage
    - Color-coded status indicators
    - Real-time updates
    """

    def __init__(self, console: Optional[Console] = None) -> None:
        """
        Initialize Rich progress renderer.
        
        Args:
            console: Optional Rich console instance
        """
        self.console = console or Console()
        self._lock = RLock()
        self._live: Optional[Live] = None
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console
        )
        self._tasks: Dict[str, TaskID] = {}
        self._stage_data: Dict[str, StageProgress] = {}
        self._start_time = time.time()
        
        # Update debouncing for performance - SOQL phase needs longer debounce
        self._last_update_time = 0.0
        self._pending_updates: Dict[str, StageProgress] = {}
        self._layout_cache: Optional[object] = None
        self._layout_cache_time = 0.0
        # Cache for details table to avoid recomputation
        self._details_cache: Dict[str, str] = {}
        self._details_cache_time = 0.0

    def is_available(self) -> bool:
        """Check if Rich is available."""
        try:
            from rich.console import Console
            return True
        except ImportError:
            return False

    def _initialize_stages(self) -> None:
        """
        Initialize all workflow stages with PENDING status.
        
        Called when renderer starts to ensure all stages visible
        immediately with consistent initial state. Stages are:
        - csv_processing
        - soql_query
        - file_downloads
        """
        stage_names = ["csv_processing", "soql_query", "file_downloads"]
        
        for stage_name in stage_names:
            if stage_name not in self._stage_data:
                # Create initial progress snapshot
                initial_progress = StageProgress(
                    current=0,
                    total=None,  # Will be set when phase starts
                    status=StageStatus.PENDING,
                    message="",
                    details={},
                    error=None
                )
                # Add to stage data so it appears in table
                self._stage_data[stage_name] = initial_progress
                # Create task for progress bar
                self._create_task(stage_name, initial_progress)

    def start(self) -> None:
        """Start the Rich progress display."""
        from src.progress.config import get_config
        config = get_config()
        
        with self._lock:
            if self._live is not None:
                return
            
            self._start_time = time.time()
            layout = self._create_layout()
            self._layout_cache = layout
            self._layout_cache_time = self._start_time
            
            self._live = Live(
                layout, 
                console=self.console,
                refresh_per_second=config.rich_refresh_rate,
                transient=False
            )
            self._live.start()
            
            # Initialize all stages for visibility
            self._initialize_stages()
            # Force initial render with all stages visible
            self._update_live_display()

    def stop(self) -> None:
        """Stop the Rich progress display."""
        with self._lock:
            if self._live is not None:
                # Process any pending updates before stopping
                if self._pending_updates:
                    self._process_pending_updates()
                
                # Force a final display update by invalidating cache
                # This ensures the completed status is visible
                self._layout_cache = None
                layout = self._create_layout()
                self._live.update(layout)
                
                self._live.stop()
                self._live = None
                # Clear caches
                self._layout_cache = None
                self._details_cache.clear()
                self._pending_updates.clear()

    def update_stage(self, stage_name: str, stage_progress: StageProgress) -> None:
        """Update progress for a specific stage with debouncing."""
        from src.progress.config import get_config
        config = get_config()
        
        with self._lock:
            self._stage_data[stage_name] = stage_progress
            
            # Store pending update for debouncing
            if config.enable_update_debouncing:
                self._pending_updates[stage_name] = stage_progress
                current_time = time.time()
                
                # Use longer debounce interval for SOQL phase to reduce update frequency
                debounce_interval = config.debounce_interval
                if stage_name == "soql_query":
                    debounce_interval = max(debounce_interval, 0.2)  # 200ms minimum for SOQL
                
                # Only update if enough time has passed
                time_diff = current_time - self._last_update_time
                if time_diff < debounce_interval:
                    return
                
                self._last_update_time = current_time
            
            # Process all pending updates
            self._process_pending_updates()

    def _process_pending_updates(self):
        """Process all pending stage updates."""
        updates_to_process = list(self._pending_updates.items())
        self._pending_updates.clear()
        
        # Update progress tasks
        for stage_name, stage_progress in updates_to_process:
            if stage_name not in self._tasks:
                self._create_task(stage_name, stage_progress)
            else:
                self._update_task(stage_name, stage_progress)
        
        # Update live display with caching
        if self._live:
            try:
                self._update_live_display()
            except Exception as e:
                logger.warning(f"Failed to update Rich display: {e}")

    def _update_live_display(self) -> None:
        """Update live display with layout caching."""
        from src.progress.config import get_config
        config = get_config()
        
        current_time = time.time()
        
        # Check if we need to update based on time and data changes
        cache_valid = (
            self._layout_cache is not None and 
            current_time - self._layout_cache_time < (1.0 / config.rich_refresh_rate)
        )
        
        # For SOQL phase, be more aggressive with caching to reduce updates
        if cache_valid:
            # Additional check: see if any stage data has actually changed
            # This prevents unnecessary updates when data is the same
            data_changed = False
            for stage_name, stage_progress in self._stage_data.items():
                cached_details = self._details_cache.get(stage_name)
                current_details = self._get_details_text(stage_name, stage_progress)
                if cached_details != current_details:
                    data_changed = True
                    break
            
            if not data_changed:
                return
        
        # Create new layout and cache it
        layout = self._create_layout()
        self._layout_cache = layout
        self._layout_cache_time = current_time
        
        if self._live is not None:
            self._live.update(layout)

    def _create_task(self, stage_name: str, stage_progress: StageProgress):
        """Create a new progress task for a stage."""
        description = self._get_stage_description(stage_name, stage_progress)
        total = stage_progress.total or 100
        
        task_id = self._progress.add_task(
            description=description,
            total=total,
            completed=stage_progress.current
        )
        self._tasks[stage_name] = task_id

    def _update_task(self, stage_name: str, stage_progress: StageProgress) -> None:
        """Update an existing progress task."""
        if stage_name not in self._tasks:
            return
        
        task_id = self._tasks[stage_name]
        description = self._get_stage_description(stage_name, stage_progress)
        
        # Update task properties
        self._progress.update(
            task_id,
            description=description,
            completed=stage_progress.current,
            total=stage_progress.total or 100
        )

    def _get_stage_description(self, stage_name: str, stage_progress: StageProgress) -> str:
        """Get formatted description for a stage."""
        # Color-code based on status
        status_colors = {
            StageStatus.PENDING: "dim",
            StageStatus.RUNNING: "blue",
            StageStatus.COMPLETED: "green",
            StageStatus.FAILED: "red",
            StageStatus.SKIPPED: "yellow"
        }
        
        color = status_colors.get(stage_progress.status, "white")
        status_icon = self._get_status_icon(stage_progress.status)
        
        # Format stage name
        display_name = stage_name.replace('_', ' ').title()
        
        base_desc = f"[{color}]{status_icon} {display_name}[/{color}]"
        
        if stage_progress.message:
            message = self._truncate_text(stage_progress.message)
            base_desc += f": {message}"
        
        return base_desc

    def _truncate_text(self, text: str, max_length: int = 60) -> str:
        """Truncate long text to avoid panel width jumps."""
        if len(text) <= max_length:
            return text
        return f"{text[:max_length - 3]}..."

    def _get_status_icon(self, status: StageStatus) -> str:
        """Get Unicode icon for stage status."""
        icons = {
            StageStatus.PENDING: "⏳",
            StageStatus.RUNNING: "🔄", 
            StageStatus.COMPLETED: "✅",
            StageStatus.FAILED: "❌",
            StageStatus.SKIPPED: "⏭️"
        }
        return icons.get(status, "•")

    def _get_panel_width(self) -> int:
        """Get a stable panel width based on terminal size."""
        terminal_width = getattr(self.console, "width", 0) or 0
        min_width = 80
        if terminal_width:
            return max(min_width, terminal_width)
        return min_width

    def _truncate_detail_value(self, label: str, value: object, details_width: int) -> object:
        """Trim long detail values to fit the details column."""
        if not isinstance(value, str):
            return value
        available = max(10, details_width - len(label) - 4)
        if len(value) <= available:
            return value
        return f"{value[:available - 3]}..."

    def _get_details_text(self, stage_name: str, stage_progress: StageProgress) -> str:
        """Get formatted details text for a stage (used for caching)."""
        details_width = 40  # Approximate width for caching comparison
        
        # Format details based on status
        if stage_progress.status == StageStatus.PENDING:
            return "Waiting to start..."
        elif stage_progress.status == StageStatus.SKIPPED:
            return "Skipped"
        elif stage_progress.status == StageStatus.FAILED:
            return f"Failed: {stage_progress.error}" if stage_progress.error else "Failed"
        else:
            # RUNNING or COMPLETED: show actual details
            details_parts = []
            if stage_progress.details:
                from src.progress.utils import get_detail_display_items

                for label, value in get_detail_display_items(stage_name, stage_progress.details):
                    value = self._truncate_detail_value(label, value, details_width)
                    details_parts.append(f"{label}: {value}")
            
            if stage_progress.error:
                details_parts.append(f"Error: {stage_progress.error}")
            
            if stage_name in ["csv_processing", "soql_query"]:
                details_parts = details_parts[:1]
            
            return " | ".join(details_parts) if details_parts else "—"

    def _create_layout(self):
        """Create the Rich layout for display."""
        panel_width = self._get_panel_width()

        # Main progress bars
        progress_panel = Panel(
            self._progress,
            title="Salesforce Attachments Extraction",
            border_style="blue",
            padding=(1, 2),
            width=panel_width,
            expand=True
        )
        
        # Detailed information table
        details_table = self._create_details_table(panel_width)
        details_panel = Panel(
            details_table,
            title="Stage Details",
            border_style="dim",
            padding=(0, 1),
            width=panel_width,
            expand=True
        )
        
        # Overall statistics
        stats_text = self._create_stats_text()
        stats_panel = Panel(
            stats_text,
            title="Summary",
            border_style="green",
            padding=(0, 1),
            width=panel_width,
            expand=True
        )
        
        # Combine into main table
        main_table = Table.grid(padding=1, expand=True)
        main_table.add_column(ratio=1)
        main_table.add_row(progress_panel)
        main_table.add_row(details_panel)
        main_table.add_row(stats_panel)
        
        return main_table

    def _create_details_table(self, panel_width: int) -> Table:
        """Create detailed information table."""
        table_width = max(80, panel_width - 4)
        table = Table(show_header=True, header_style="bold", expand=True, width=table_width)
        stage_width = 16
        status_width = 11
        progress_width = 17
        table.add_column("Stage", style="cyan", no_wrap=True, width=stage_width)
        table.add_column("Status", style="white", no_wrap=True, width=status_width)
        table.add_column("Progress", style="blue", no_wrap=True, width=progress_width)
        details_width = max(20, table_width - stage_width - status_width - progress_width - 6)
        table.add_column("Details", style="dim", overflow="fold", width=details_width)
        
        for stage_name, stage_progress in self._stage_data.items():
            # Format progress
            if stage_progress.status == StageStatus.PENDING:
                # For pending stages, show waiting indicator
                progress_text = "Waiting"
            elif stage_progress.total:
                progress_text = f"{stage_progress.current}/{stage_progress.total}"
                percentage = (stage_progress.current / stage_progress.total) * 100
                progress_text += f" ({percentage:.1f}%)"
            else:
                progress_text = str(stage_progress.current) if stage_progress.current else "—"
            
            # Format details based on status
            if stage_progress.status == StageStatus.PENDING:
                details_text = "Waiting to start..."
            elif stage_progress.status == StageStatus.SKIPPED:
                details_text = "Skipped"
            elif stage_progress.status == StageStatus.FAILED:
                details_text = f"Failed: {stage_progress.error}" if stage_progress.error else "Failed"
            else:
                # RUNNING or COMPLETED: show actual details
                details_parts = []
                if stage_progress.details:
                    from src.progress.utils import get_detail_display_items

                    for label, value in get_detail_display_items(stage_name, stage_progress.details):
                        value = self._truncate_detail_value(label, value, details_width)
                        details_parts.append(f"{label}: {value}")
                
                if stage_progress.error:
                    details_parts.append(f"Error: {stage_progress.error}")
                
                if stage_name in ["csv_processing", "soql_query"]:
                    details_parts = details_parts[:1]
                
                details_text = " | ".join(details_parts) if details_parts else "—"
            
            # Add row with color coding
            status_color = {
                StageStatus.PENDING: "dim",
                StageStatus.RUNNING: "blue", 
                StageStatus.COMPLETED: "green",
                StageStatus.FAILED: "red",
                StageStatus.SKIPPED: "yellow"
            }.get(stage_progress.status, "white")
            
            table.add_row(
                stage_name.replace('_', ' ').title(),
                f"[{status_color}]{stage_progress.status.value.title()}[/{status_color}]",
                progress_text,
                details_text
            )
        
        return table

    def _create_stats_text(self) -> Text:
        """Create summary statistics text."""
        elapsed = time.time() - self._start_time
        elapsed_formatted = f"{elapsed:.1f}s"

        # Count stages by status
        status_counts = {}
        for stage_progress in self._stage_data.values():
            status = stage_progress.status
            status_counts[status] = status_counts.get(status, 0) + 1

        # Format statistics
        stats_parts = [f"Elapsed: {elapsed_formatted}"]
        download_stage = self._stage_data.get("file_downloads")
        if download_stage and download_stage.total is not None:
            stats_parts.append(f"Downloads: {download_stage.current}/{download_stage.total}")

        if StageStatus.COMPLETED in status_counts:
            stats_parts.append(f"✅ {status_counts[StageStatus.COMPLETED]} completed")

        if StageStatus.RUNNING in status_counts:
            stats_parts.append(f"🔄 {status_counts[StageStatus.RUNNING]} running")

        if StageStatus.FAILED in status_counts:
            stats_parts.append(f"❌ {status_counts[StageStatus.FAILED]} failed")

        if StageStatus.SKIPPED in status_counts:
            stats_parts.append(f"⏭️ {status_counts[StageStatus.SKIPPED]} skipped")

        return Text(" | ".join(stats_parts))

    def display_completion_summary(self, stats: Dict[str, int]) -> None:
        """Display workflow completion summary panel."""
        return


# Utility function to check Rich availability
def is_rich_available() -> bool:
    """Check if Rich library is available."""
    try:
        import rich
        return True
    except ImportError:
        return False