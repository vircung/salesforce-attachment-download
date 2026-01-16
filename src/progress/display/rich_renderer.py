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
        
        # Update debouncing for performance
        self._last_update_time = 0.0
        self._pending_updates: Dict[str, StageProgress] = {}
        self._layout_cache: Optional[object] = None
        self._layout_cache_time = 0.0

    def is_available(self) -> bool:
        """Check if Rich is available."""
        try:
            from rich.console import Console
            return True
        except ImportError:
            return False

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

    def stop(self) -> None:
        """Stop the Rich progress display."""
        with self._lock:
            if self._live is not None:
                self._live.stop()
                self._live = None
                # Clear caches
                self._layout_cache = None
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
                
                # Only update if enough time has passed
                if current_time - self._last_update_time < config.debounce_interval:
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
        
        # Use cached layout if available and recent
        if (self._layout_cache is not None and 
            current_time - self._layout_cache_time < (1.0 / config.rich_refresh_rate)):
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
            base_desc += f": {stage_progress.message}"
        
        return base_desc

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

    def _create_layout(self):
        """Create the Rich layout for display."""
        # Main progress bars
        progress_panel = Panel(
            self._progress,
            title="Salesforce Attachments Extraction",
            border_style="blue",
            padding=(1, 2)
        )
        
        # Detailed information table
        details_table = self._create_details_table()
        details_panel = Panel(
            details_table,
            title="Stage Details",
            border_style="dim",
            padding=(0, 1)
        )
        
        # Overall statistics
        stats_text = self._create_stats_text()
        stats_panel = Panel(
            stats_text,
            title="Summary",
            border_style="green",
            padding=(0, 1)
        )
        
        # Combine into main table
        main_table = Table.grid(padding=1)
        main_table.add_column()
        main_table.add_row(progress_panel)
        main_table.add_row(details_panel)
        main_table.add_row(stats_panel)
        
        return main_table

    def _create_details_table(self) -> Table:
        """Create detailed information table."""
        table = Table(show_header=True, header_style="bold")
        table.add_column("Stage", style="cyan", no_wrap=True)
        table.add_column("Status", style="white")
        table.add_column("Progress", style="blue")
        table.add_column("Details", style="dim")
        
        for stage_name, stage_progress in self._stage_data.items():
            # Format progress
            if stage_progress.total:
                progress_text = f"{stage_progress.current}/{stage_progress.total}"
                percentage = (stage_progress.current / stage_progress.total) * 100
                progress_text += f" ({percentage:.1f}%)"
            else:
                progress_text = str(stage_progress.current) if stage_progress.current else "—"
            
            # Format details
            details_parts = []
            if stage_progress.details:
                for key, value in stage_progress.details.items():
                    if key in ['current_file', 'current_csv', 'current_batch']:
                        details_parts.append(f"{key}: {value}")
                    elif key in ['speed', 'throughput']:
                        details_parts.append(f"{key}: {value}")
            
            if stage_progress.error:
                details_parts.append(f"Error: {stage_progress.error}")
            
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
        with self._lock:
            try:
                summary_table = Table.grid(padding=(0, 2))
                summary_table.add_column(style="cyan bold")
                summary_table.add_column()

                summary_table.add_row("CSV files processed:", f"{stats.get('total_csv_files', 0)}")
                summary_table.add_row("Total records:", f"{stats.get('total_records', 0)}")
                summary_table.add_row(
                    "Total attachments:",
                    f"{stats.get('total_attachments', 0)}",
                )

                success_text = Text("✓ WORKFLOW COMPLETE", style="bold green")
                panel = Panel(
                    summary_table,
                    title=success_text,
                    border_style="green",
                    padding=(1, 2),
                )

                self.console.print()
                self.console.print(panel)
                self.console.print()
                logger.debug("Displayed Rich completion summary")
            except Exception as e:
                logger.warning(f"Failed to display Rich completion summary: {e}")


# Utility function to check Rich availability
def is_rich_available() -> bool:
    """Check if Rich library is available."""
    try:
        import rich
        return True
    except ImportError:
        return False