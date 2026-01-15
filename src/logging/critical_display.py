"""
Critical Message Display

Rich-based display system for showing critical error messages during progress tracking.
Integrates with Rich progress display to show error panels without disrupting progress bars.
"""

import logging
import sys
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    Console = None
    Panel = None
    Text = None


class CriticalMessageDisplay:
    """
    Display critical error messages within Rich progress UI.
    
    Provides Rich-styled error panels that can be displayed during
    progress tracking without disrupting the progress bars.
    """
    
    def __init__(self, console: Optional[Console] = None):
        """
        Initialize critical message display.
        
        Args:
            console: Optional Rich console instance. If None, creates new console
                    or falls back to stderr if Rich is unavailable.
        """
        if RICH_AVAILABLE:
            self.console = console or Console(stderr=True)
            self.rich_available = True
        else:
            self.console = None
            self.rich_available = False
    
    def display_error(self, record: logging.LogRecord) -> None:
        """
        Display an error message immediately.
        
        If Rich is available, displays as a styled error panel.
        Otherwise, falls back to stderr output.
        
        Args:
            record: LogRecord containing error information
        """
        if self.rich_available and self.console:
            self._display_rich_error(record)
        else:
            self._display_fallback_error(record)
    
    def _display_rich_error(self, record: logging.LogRecord) -> None:
        """Display error using Rich formatting."""
        try:
            # Format error message
            message = record.getMessage()
            
            # Create styled text
            error_text = Text()
            error_text.append("ERROR", style="bold red")
            
            # Add module information if available
            if hasattr(record, 'name') and record.name:
                error_text.append(f" ({record.name})", style="dim red")
            
            error_text.append(f": {message}", style="red")
            
            # Add location information if available
            if hasattr(record, 'funcName') and hasattr(record, 'lineno'):
                location = f"{record.funcName}() line {record.lineno}"
                error_text.append(f"\nLocation: {location}", style="dim")
            
            # Create error panel
            panel = Panel(
                error_text,
                title="⚠️  Critical Error",
                border_style="red",
                padding=(0, 1),
                expand=False
            )
            
            # Display immediately to stderr
            self.console.print(panel, file=sys.stderr)
            
        except Exception:
            # If Rich display fails, fall back to stderr
            self._display_fallback_error(record)
    
    def _display_fallback_error(self, record: logging.LogRecord) -> None:
        """Fallback error display using plain text to stderr."""
        try:
            message = record.getMessage()
            
            # Simple formatted output
            error_line = f"ERROR: {message}"
            
            # Add location if available
            if hasattr(record, 'name') and record.name:
                error_line += f" ({record.name})"
            
            if hasattr(record, 'funcName') and hasattr(record, 'lineno'):
                error_line += f" [{record.funcName}:{record.lineno}]"
            
            sys.stderr.write(f"{error_line}\n")
            sys.stderr.flush()
            
        except Exception:
            # Last resort - just output the basic message
            try:
                sys.stderr.write(f"ERROR: {record.msg}\n")
                sys.stderr.flush()
            except Exception:
                pass  # Give up on error display
    
    def display_warning(self, record: logging.LogRecord) -> None:
        """
        Display a warning message.
        
        Similar to display_error but with warning styling.
        Can be used for displaying buffered warnings after progress completes.
        
        Args:
            record: LogRecord containing warning information
        """
        if self.rich_available and self.console:
            self._display_rich_warning(record)
        else:
            self._display_fallback_warning(record)
    
    def _display_rich_warning(self, record: logging.LogRecord) -> None:
        """Display warning using Rich formatting."""
        try:
            message = record.getMessage()
            
            # Create styled text
            warning_text = Text()
            warning_text.append("WARNING", style="bold yellow")
            
            if hasattr(record, 'name') and record.name:
                warning_text.append(f" ({record.name})", style="dim yellow")
            
            warning_text.append(f": {message}", style="yellow")
            
            # Create warning panel
            panel = Panel(
                warning_text,
                title="⚠️  Warning",
                border_style="yellow",
                padding=(0, 1),
                expand=False
            )
            
            self.console.print(panel)
            
        except Exception:
            self._display_fallback_warning(record)
    
    def _display_fallback_warning(self, record: logging.LogRecord) -> None:
        """Fallback warning display using plain text."""
        try:
            message = record.getMessage()
            warning_line = f"WARNING: {message}"
            
            if hasattr(record, 'name') and record.name:
                warning_line += f" ({record.name})"
            
            print(warning_line)
            
        except Exception:
            try:
                print(f"WARNING: {record.msg}")
            except Exception:
                pass
    
    @staticmethod
    def is_available() -> bool:
        """Check if Rich-based display is available."""
        return RICH_AVAILABLE