"""
Progress Utilities

Helper functions for setting up and managing progress tracking.
"""

import logging
from typing import Optional

from .core import ProgressTracker, ProgressMode, ProgressRenderer
from .display.rich_renderer import RichProgressRenderer, is_rich_available
from .display.tqdm_renderer import TqdmProgressRenderer, is_tqdm_available

logger = logging.getLogger(__name__)


def create_progress_tracker(mode_str: str = "auto") -> ProgressTracker:
    """
    Create a progress tracker with the specified mode.
    
    Args:
        mode_str: Progress mode string ("auto", "on", "off")
        
    Returns:
        ProgressTracker instance
    """
    try:
        mode = ProgressMode(mode_str.lower())
    except ValueError:
        logger.warning(f"Invalid progress mode '{mode_str}', using 'auto'")
        mode = ProgressMode.AUTO
    
    return ProgressTracker(mode=mode)


def auto_select_renderer() -> Optional[ProgressRenderer]:
    """
    Automatically select the best available progress renderer.
    
    This function is deprecated. Use config.auto_select_renderer() instead.
    
    Returns:
        Best available renderer or None if none available
    """
    # Import here to avoid circular imports
    from .config import auto_select_renderer as config_auto_select
    return config_auto_select()


def setup_progress_tracker(
    mode_str: str = "auto",
    renderer: Optional[ProgressRenderer] = None
) -> ProgressTracker:
    """
    Setup a complete progress tracker with automatic renderer selection.
    
    Args:
        mode_str: Progress mode string ("auto", "on", "off")
        renderer: Optional specific renderer to use
        
    Returns:
        Configured ProgressTracker instance
    """
    tracker = create_progress_tracker(mode_str)
    
    if not renderer and tracker.mode != ProgressMode.OFF:
        from .config import auto_select_renderer as config_auto_select
        renderer = config_auto_select()
    
    if renderer:
        tracker.set_renderer(renderer)
        logger.debug(f"Progress tracker setup with {type(renderer).__name__}")
    else:
        logger.debug("Progress tracker setup without renderer")
    
    return tracker


def log_progress_setup(tracker: ProgressTracker):
    """Log information about progress tracker setup."""
    if tracker.mode == ProgressMode.OFF:
        logger.info("Progress display: disabled")
    elif tracker._renderer:
        renderer_name = type(tracker._renderer).__name__
        logger.info(f"Progress display: {renderer_name}")
    else:
        logger.info("Progress display: enabled but no renderer available")


def check_progress_dependencies() -> dict:
    """
    Check availability of progress display dependencies.
    
    Returns:
        Dictionary with availability information
    """
    from .config import get_renderer_registry
    registry = get_renderer_registry()
    available_renderers = registry.list_available()
    
    return {
        'rich_available': available_renderers.get('rich', False),
        'tqdm_available': available_renderers.get('tqdm', False),
        'any_available': any(available_renderers.values()),
        'available_renderers': available_renderers
    }