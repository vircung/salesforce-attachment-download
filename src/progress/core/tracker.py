"""
Core Progress Tracker Module

Main progress tracker class that coordinates multiple stages and renderers.
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum
from threading import RLock
from typing import Dict, Optional, List, Any, TYPE_CHECKING

from src.progress.core.stage import ProgressStage, StageStatus

if TYPE_CHECKING:
    from src.logging import LoggingManager

logger = logging.getLogger(__name__)


class ProgressMode(Enum):
    """Progress display modes."""
    AUTO = "auto"      # Automatically choose best renderer
    ON = "on"          # Force progress display (prefer rich)
    OFF = "off"        # Disable progress display


class ProgressRenderer(ABC):
    """Abstract base class for progress renderers."""

    @abstractmethod
    def start(self) -> None:
        """Start the progress display."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the progress display."""
        pass

    @abstractmethod
    def update_stage(self, stage_name: str, stage_progress: Any) -> None:
        """Update progress for a specific stage."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this renderer is available in the current environment."""
        pass

    def display_completion_summary(self, stats: Dict[str, int]) -> None:
        """Display completion summary. Default no-op."""
        return


class ProgressTracker:
    """
    Main progress tracker that coordinates stages and rendering.
    
    Thread-safe tracker that manages multiple progress stages and delegates
    display rendering to pluggable renderer implementations.
    
    Integrates with LoggingManager to prevent console logging conflicts
    during progress display.
    """

    def __init__(
        self,
        mode: ProgressMode = ProgressMode.AUTO,
        logging_manager: Optional["LoggingManager"] = None,
    ) -> None:
        """
        Initialize progress tracker.
        
        Args:
            mode: Progress display mode
            logging_manager: LoggingManager instance (optional)
        """
        self.mode = mode
        self._lock = RLock()
        self._stages: Dict[str, ProgressStage] = {}
        self._renderer: Optional[ProgressRenderer] = None
        self._is_started = False

        # Logging integration (set by main.py after instantiation)
        self._logging_manager = logging_manager
        self._logging_mode_active = False

    def add_stage(self, stage: ProgressStage) -> None:
        """
        Add a progress stage to track.
        
        Args:
            stage: ProgressStage instance to add
        """
        with self._lock:
            self._stages[stage.name] = stage
            # Register callback to receive updates
            stage.add_callback(self._on_stage_update)

    def remove_stage(self, stage_name: str) -> None:
        """Remove a progress stage."""
        with self._lock:
            if stage_name in self._stages:
                stage = self._stages[stage_name]
                stage.remove_callback(self._on_stage_update)
                del self._stages[stage_name]

    def get_stage(self, stage_name: str) -> Optional[ProgressStage]:
        """Get a progress stage by name."""
        with self._lock:
            return self._stages.get(stage_name)

    def set_renderer(self, renderer: Optional[ProgressRenderer]) -> None:
        """Set the progress renderer."""
        with self._lock:
            self._renderer = renderer

    def start(self) -> None:
        """Start progress tracking and display."""
        with self._lock:
            if self._is_started:
                return
            
            # Enable progress mode in logging manager if available
            if self._logging_manager and self.mode != ProgressMode.OFF:
                try:
                    self._logging_manager.enable_progress_mode()
                    self._logging_mode_active = True
                    logger.debug("Enabled progress mode in logging manager")
                except Exception as e:
                    logger.warning(f"Failed to enable logging progress mode: {e}")
            
            # Auto-select renderer if none set
            if not self._renderer and self.mode != ProgressMode.OFF:
                self._renderer = self._auto_select_renderer()
            
            # Start renderer if available
            if self._renderer and self.mode != ProgressMode.OFF:
                try:
                    self._renderer.start()
                    logger.debug(f"Started progress renderer: {type(self._renderer).__name__}")
                except Exception as e:
                    logger.warning(f"Failed to start progress renderer: {e}")
                    # Fall back to no progress display on renderer error
                    self._renderer = None
            
            self._is_started = True

    def stop(self) -> None:
        """Stop progress tracking and display."""
        with self._lock:
            if not self._is_started:
                return
            
            # Give renderers a moment to process final stage updates
            # This ensures completion status is visible before display stops
            import time
            time.sleep(0.2)
            
            # Stop renderer first
            if self._renderer:
                try:
                    self._renderer.stop()
                    logger.debug(f"Stopped progress renderer: {type(self._renderer).__name__}")
                except Exception as e:
                    logger.warning(f"Error stopping progress renderer: {e}")
            
            # Disable progress mode in logging manager
            if self._logging_manager and self._logging_mode_active:
                try:
                    self._logging_manager.disable_progress_mode()
                    self._logging_mode_active = False
                    logger.debug("Disabled progress mode in logging manager")
                except Exception as e:
                    logger.warning(f"Failed to disable logging progress mode: {e}")
            
            self._is_started = False

    def _on_stage_update(self, stage_name: str, stage_progress):
        """Callback for stage updates with error handling."""
        if self._renderer and self._is_started and self.mode != ProgressMode.OFF:
            try:
                self._renderer.update_stage(stage_name, stage_progress)
            except Exception as e:
                # Log but don't let rendering errors affect progress
                logger.warning(f"Renderer update failed for stage {stage_name}: {e}")

    def _auto_select_renderer(self) -> Optional[ProgressRenderer]:
        """
        Automatically select the best available renderer with thread safety.
        
        """
        with self._lock:
            if self._renderer is not None:
                return self._renderer

            try:
                from src.progress.config import auto_select_renderer

                renderer = auto_select_renderer()
                if renderer:
                    logger.debug(f"Auto-selected renderer: {type(renderer).__name__}")
                else:
                    logger.warning("No suitable progress renderer available")

                return renderer
            except Exception as e:
                logger.error(f"Failed to auto-select renderer: {e}")
                return None

    def get_summary(self) -> Dict[str, Dict]:
        """Get summary of all stages."""
        with self._lock:
            summary = {}
            for name, stage in self._stages.items():
                progress = stage.progress
                summary[name] = {
                    'status': progress.status.value,
                    'current': progress.current,
                    'total': progress.total,
                    'message': progress.message,
                    'error': progress.error,
                    'details': progress.details
                }
            return summary

    def has_failures(self) -> bool:
        """Check if any stage has failed."""
        with self._lock:
            return any(
                stage.progress.status == StageStatus.FAILED 
                for stage in self._stages.values()
            )

    def is_complete(self) -> bool:
        """Check if all stages are complete or skipped."""
        with self._lock:
            if not self._stages:
                return False
            
            return all(
                stage.progress.status in (StageStatus.COMPLETED, StageStatus.SKIPPED)
                for stage in self._stages.values()
            )

    def display_completion_summary(self, stats: Dict[str, int]) -> None:
        """Display workflow completion summary via renderer when available."""
        if self._renderer and self._is_started and self.mode != ProgressMode.OFF:
            try:
                self._renderer.display_completion_summary(stats)
            except Exception as e:
                logger.warning(f"Failed to display completion summary: {e}")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop()