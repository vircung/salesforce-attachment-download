"""
Keyboard Listener for Worker Activity Panel Toggle

Daemon thread that reads single keypresses from stdin in cbreak mode.
Unix-only (tty/termios). Silently disabled on Windows or non-TTY stdin.
"""

import atexit
import logging
import signal
import sys
import threading
from typing import Optional

logger = logging.getLogger(__name__)

# Module-level storage for terminal restoration safety net
_original_termios = None

try:
    import termios
    import tty
    _TERMIOS_AVAILABLE = True
except ImportError:
    _TERMIOS_AVAILABLE = False


def _restore_terminal() -> None:
    """Restore original terminal settings. Called by atexit and signal handlers."""
    global _original_termios
    if _original_termios is not None and _TERMIOS_AVAILABLE:
        try:
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _original_termios)
        except (OSError, ValueError):
            pass
        _original_termios = None


class KeyboardListener:
    """Daemon thread listening for keypress to toggle worker panel.

    Only activates when:
    - stdin is a TTY
    - tty/termios modules are available (Unix)

    Restores terminal settings on stop(), atexit, and SIGTERM/SIGINT/SIGHUP.
    """

    def __init__(self, tracker: "WorkerActivityTracker") -> None:
        from src.progress.worker_tracker import WorkerActivityTracker
        self._tracker: WorkerActivityTracker = tracker
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._available = False

    @property
    def available(self) -> bool:
        """Whether the keyboard listener can operate in this environment."""
        return self._available

    def start(self) -> None:
        """Start the keyboard listener if possible."""
        if not _TERMIOS_AVAILABLE:
            logger.debug("Keyboard listener disabled: termios not available")
            return

        if not sys.stdin.isatty():
            logger.debug("Keyboard listener disabled: stdin is not a TTY")
            return

        global _original_termios
        try:
            _original_termios = termios.tcgetattr(sys.stdin.fileno())
        except (OSError, ValueError) as e:
            logger.debug("Keyboard listener disabled: cannot read terminal settings: %s", e)
            return

        # Register cleanup before entering cbreak
        atexit.register(_restore_terminal)
        self._install_signal_handlers()

        self._available = True
        self._tracker.keyboard_available = True
        self._stop_event.clear()

        self._thread = threading.Thread(
            target=self._listen_loop,
            name="keyboard-listener",
            daemon=True,
        )
        self._thread.start()
        logger.debug("Keyboard listener started")

    def stop(self) -> None:
        """Stop the listener and restore terminal settings."""
        self._stop_event.set()
        _restore_terminal()
        self._available = False
        self._tracker.keyboard_available = False
        # Don't join daemon thread — it may be blocked on stdin.read(1)
        self._thread = None
        logger.debug("Keyboard listener stopped")

    def _listen_loop(self) -> None:
        """Read single keypresses in cbreak mode."""
        try:
            tty.setcbreak(sys.stdin.fileno())
            while not self._stop_event.is_set():
                # Use select-style timeout to check stop_event periodically
                # stdin.read(1) blocks, so we check isatty and use a short approach
                try:
                    ch = sys.stdin.read(1)
                    if ch == 'w':
                        new_state = self._tracker.toggle_panel()
                        logger.debug("Worker panel toggled: %s", "visible" if new_state else "hidden")
                except (OSError, ValueError):
                    break
        except (OSError, ValueError):
            pass
        finally:
            _restore_terminal()

    def _install_signal_handlers(self) -> None:
        """Install signal handlers for terminal restoration.

        Only installs from the main thread. Wraps existing handlers
        to avoid breaking signal chains (e.g. KeyboardInterrupt for SIGINT).
        """
        if threading.current_thread() is not threading.main_thread():
            logger.debug("Skipping signal handler installation: not main thread")
            return

        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            try:
                prev_handler = signal.getsignal(sig)
                def _handler(signum, frame, _prev=prev_handler):
                    _restore_terminal()
                    if callable(_prev) and _prev not in (signal.SIG_DFL, signal.SIG_IGN):
                        _prev(signum, frame)
                    elif _prev == signal.SIG_DFL:
                        signal.signal(signum, signal.SIG_DFL)
                        signal.raise_signal(signum)
                signal.signal(sig, _handler)
            except (OSError, ValueError):
                pass
