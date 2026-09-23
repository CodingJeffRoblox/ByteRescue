"""File-based logging for ByteRescue.

When the app is launched by double-clicking ByteRescue.bat, stderr isn't
visible anywhere -- an exception inside a Tkinter callback (which Tkinter
normally just prints to stderr and swallows) would previously vanish with
no trace at all. This gives every run a log file, and hooks Tkinter's
callback-exception path so nothing gets silently lost again.

The file always gets everything (DEBUG and up). If ByteRescue is run from
a console (the normal case -- ByteRescue.ps1 launches it in the elevated
PowerShell window it opens, which stays open), that same console also gets
a live stream at INFO and up, so you can watch what's happening in real
time instead of only checking the file after the fact. Set the
BYTERESCUE_DEBUG environment variable to anything non-empty to bump the
console stream to DEBUG too, for a fully verbose run.
"""

import logging
import os
import platform
import sys
import traceback
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_PATH = LOG_DIR / "byterescue.log"

_logger = None


def get_logger():
    global _logger
    if _logger is not None:
        return _logger

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("byterescue")
    logger.setLevel(logging.DEBUG)

    from logging.handlers import RotatingFileHandler
    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=2 * 1024 * 1024, backupCount=2, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
    logger.addHandler(file_handler)

    if sys.stderr is not None:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG if os.environ.get("BYTERESCUE_DEBUG") else logging.INFO)
        console_handler.setFormatter(logging.Formatter("[ByteRescue] %(levelname)-7s %(message)s"))
        logger.addHandler(console_handler)

    _logger = logger
    logger.info("=" * 70)
    logger.info("ByteRescue starting up")
    _log_environment(logger)
    return logger


def _log_environment(logger):
    """Logged once per run, unconditionally -- this is exactly the
    information someone would otherwise have to be asked for when
    reporting an issue (Python build, OS build, whether elevated)."""
    try:
        from . import __version__
    except Exception:
        __version__ = "unknown"
    logger.info("ByteRescue version: %s", __version__)
    logger.info("Python: %s (%s)", sys.version.replace("\n", " "), sys.executable)
    logger.info("Platform: %s", platform.platform())
    logger.info("Elevated (Administrator): %s", _is_admin())
    logger.info("Working directory: %s", os.getcwd())


def _is_admin():
    if platform.system() != "Windows":
        return "n/a (not Windows)"
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return "unknown"


def install_tk_exception_logging(root):
    """Route exceptions raised inside Tkinter callbacks (after()/bind/etc)
    to the log file instead of Tkinter's default stderr-only behavior,
    which is invisible when launched without a console window."""
    logger = get_logger()

    def report_callback_exception(exc_type, exc_value, exc_tb):
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logger.error("Unhandled exception in a GUI callback:\n%s", text)
        try:
            from tkinter import messagebox
            messagebox.showerror(
                "ByteRescue",
                "An unexpected error occurred.\n\n"
                f"{exc_type.__name__}: {exc_value}\n\n"
                f"Details were written to:\n{LOG_PATH}",
            )
        except Exception:
            pass

    root.report_callback_exception = report_callback_exception


def log_exception(context):
    """Call from inside an except block to record a traceback with context,
    e.g. `except Exception: applog.log_exception('recovery scan thread')`."""
    get_logger().error("Exception in %s:\n%s", context, traceback.format_exc())


def excepthook_to_log(exc_type, exc_value, exc_tb):
    """Install via sys.excepthook to also catch exceptions outside Tkinter
    callbacks (e.g. in a bare threading.Thread target)."""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    get_logger().error("Unhandled exception:\n%s", text)
    sys.__excepthook__(exc_type, exc_value, exc_tb)
