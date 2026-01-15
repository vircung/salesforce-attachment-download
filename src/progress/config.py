"""
Progress Configuration Module

Configuration dataclass and renderer selection improvements with thread safety.
"""

import logging
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, Type, Optional

from .core.tracker import ProgressRenderer

logger = logging.getLogger(__name__)


@dataclass
class ProgressConfig:
    """Configuration settings for progress tracking system."""
    
    # Update frequencies (in seconds)
    min_update_interval: float = 0.1  # Minimum time between updates
    rich_refresh_rate: int = 4  # Rich renderer refresh rate (Hz)
    debounce_interval: float = 0.05  # Debouncing for rapid updates
    
    # Memory management
    max_details_entries: int = 50  # Maximum entries in details dict
    max_history_size: int = 100  # Maximum progress history entries
    
    # Error handling
    max_callback_errors: int = 5  # Max callback errors before disabling
    callback_timeout: float = 1.0  # Callback timeout in seconds
    log_callback_errors: bool = True  # Whether to log callback errors
    
    # Performance tuning
    enable_progress_caching: bool = True  # Cache progress copies
    cache_dirty_threshold: int = 10  # Updates before forcing cache refresh
    enable_update_debouncing: bool = True  # Debounce rapid updates
    
    # Thread safety
    renderer_selection_timeout: float = 5.0  # Timeout for renderer selection
    callback_copy_timeout: float = 1.0  # Timeout for callback list copying


# Global configuration instance
_config = ProgressConfig()
_config_lock = RLock()


def get_config() -> ProgressConfig:
    """Get the current global progress configuration."""
    with _config_lock:
        return _config


def set_config(config: ProgressConfig) -> None:
    """Set the global progress configuration."""
    global _config
    with _config_lock:
        _config = config


def update_config(**kwargs) -> None:
    """Update specific configuration values."""
    global _config
    with _config_lock:
        for key, value in kwargs.items():
            if hasattr(_config, key):
                setattr(_config, key, value)
            else:
                raise ValueError(f"Unknown configuration option: {key}")


class RendererRegistry:
    """Thread-safe registry for progress renderers with auto-selection."""
    
    def __init__(self):
        self._lock = RLock()
        self._renderers: Dict[str, Type[ProgressRenderer]] = {}
        self._cached_selection: Optional[Type[ProgressRenderer]] = None
        self._last_selection_time: float = 0
        self._selection_cache_ttl: float = 30.0  # Cache for 30 seconds
    
    def register(self, name: str, renderer_class: Type[ProgressRenderer]) -> None:
        """Register a renderer class."""
        with self._lock:
            self._renderers[name] = renderer_class
            # Invalidate cached selection
            self._cached_selection = None
            logger.debug(f"Registered renderer: {name}")
    
    def get_renderer(self, name: str) -> Optional[Type[ProgressRenderer]]:
        """Get a specific renderer by name."""
        with self._lock:
            return self._renderers.get(name)
    
    def auto_select(self) -> Optional[Type[ProgressRenderer]]:
        """
        Automatically select the best available renderer.
        
        Thread-safe with caching to avoid repeated expensive checks.
        """
        config = get_config()
        
        with self._lock:
            current_time = time.time()
            
            # Use cached selection if still valid
            if (self._cached_selection is not None and 
                current_time - self._last_selection_time < self._selection_cache_ttl):
                return self._cached_selection
            
            try:
                # Try renderers in priority order
                selected_renderer = self._select_best_renderer()
                
                # Cache the result
                self._cached_selection = selected_renderer
                self._last_selection_time = current_time
                
                if selected_renderer:
                    logger.debug(f"Auto-selected renderer: {selected_renderer.__name__}")
                else:
                    logger.warning("No suitable progress renderer found")
                
                return selected_renderer
                
            except Exception as e:
                logger.error(f"Error during renderer auto-selection: {e}")
                self._cached_selection = None
                return None
    
    def _select_best_renderer(self) -> Optional[Type[ProgressRenderer]]:
        """Select the best available renderer based on priority and availability."""
        # Import here to avoid circular imports
        try:
            from .display.rich_renderer import RichProgressRenderer, is_rich_available
            from .display.tqdm_renderer import TqdmProgressRenderer, is_tqdm_available
        except ImportError as e:
            logger.error(f"Failed to import renderers: {e}")
            return None
        
        # Priority order: Rich > Tqdm
        renderers_to_try = [
            ('rich', RichProgressRenderer, is_rich_available),
            ('tqdm', TqdmProgressRenderer, is_tqdm_available),
        ]
        
        for name, renderer_class, availability_check in renderers_to_try:
            try:
                if availability_check():
                    # Test instantiation to ensure it works
                    test_instance = renderer_class()
                    if test_instance.is_available():
                        return renderer_class
            except Exception as e:
                logger.debug(f"Renderer {name} unavailable: {e}")
                continue
        
        return None
    
    def clear_cache(self) -> None:
        """Clear the renderer selection cache."""
        with self._lock:
            self._cached_selection = None
            self._last_selection_time = 0
    
    def list_available(self) -> Dict[str, bool]:
        """List all renderers and their availability."""
        with self._lock:
            result = {}
            for name, renderer_class in self._renderers.items():
                try:
                    instance = renderer_class()
                    result[name] = instance.is_available()
                except Exception:
                    result[name] = False
            return result


# Global renderer registry
_renderer_registry = RendererRegistry()


def get_renderer_registry() -> RendererRegistry:
    """Get the global renderer registry."""
    return _renderer_registry


def auto_select_renderer() -> Optional[ProgressRenderer]:
    """
    Auto-select and instantiate the best available renderer.
    
    Returns:
        ProgressRenderer instance or None if no renderer available
    """
    renderer_class = _renderer_registry.auto_select()
    if renderer_class is None:
        return None
    
    try:
        return renderer_class()
    except Exception as e:
        logger.error(f"Failed to instantiate renderer {renderer_class.__name__}: {e}")
        return None


# Initialize default renderers
def _initialize_default_renderers():
    """Initialize the default renderer registry."""
    try:
        from .display.rich_renderer import RichProgressRenderer
        _renderer_registry.register('rich', RichProgressRenderer)
    except ImportError:
        pass
    
    try:
        from .display.tqdm_renderer import TqdmProgressRenderer  
        _renderer_registry.register('tqdm', TqdmProgressRenderer)
    except ImportError:
        pass


# Initialize on import
_initialize_default_renderers()