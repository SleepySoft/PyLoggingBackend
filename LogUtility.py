import os
import sys
import shutil
import logging
import datetime
import threading
from typing import Optional, Union, Any
from pythonjsonlogger import jsonlogger


class ColoredFormatter(logging.Formatter):
    """
    A custom logging formatter that injects ANSI escape codes into log messages
    to colorize output based on the severity level.

    This is primarily used for human-readable console output during development.
    It overrides the standard formatting to wrap the message metadata in color tags.
    """

    # ANSI escape codes for terminal colors
    GREY = "\x1b[38;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    # The structure of the log message for the console:
    # Time - Level - [Module:Function] - Message
    # We include module and funcName to assist with debugging location.
    fmt_template = "%(asctime)s - %(levelname)s - [%(module)s:%(funcName)s] - %(message)s"

    # Mapping logging levels to their specific colorized format strings
    FORMATS = {
        logging.DEBUG: GREY + fmt_template + RESET,
        logging.INFO: GREEN + fmt_template + RESET,
        logging.WARNING: YELLOW + fmt_template + RESET,
        logging.ERROR: RED + fmt_template + RESET,
        logging.CRITICAL: BOLD_RED + fmt_template + RESET
    }

    def format(self, record):
        """
        Formats the specified record as text.

        It retrieves the colorized format string corresponding to the log record's level
        and delegates the actual formatting to the parent logging.Formatter class.
        """
        log_fmt = self.FORMATS.get(record.levelno)
        # We use a simplified time format (H:M:S) for the console to reduce visual noise
        formatter = logging.Formatter(log_fmt, datefmt='%H:%M:%S')
        return formatter.format(record)


def setup_logging(log_file='application.log', console_json=False):
    """
    Configures the root logger with a dual-handler setup:
    1. Console Handler: Outputs colorized text (default) or JSON.
    2. File Handler: Always outputs structured JSON.

    Args:
        log_file (str): The path to the log file where JSON logs will be stored.
        console_json (bool): If True, console output will be in JSON format (useful for
                             containerized environments like Docker/K8s).
                             If False, console output will be colorized text (useful for
                             local development).

    Returns:
        logging.Logger: The configured root logger instance.
    """
    # Retrieve the root logger to ensure configuration applies globally to all modules
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove any existing handlers to prevent duplicate logs or configuration conflicts
    # This is crucial when reloading modules or running in certain IDE environments
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # --- Formatter Configuration ---

    # 1. JSON Formatter: Used for file output (and optionally console).
    # It captures detailed context including the custom 'link_file' field.
    # Note: Standard fields are automatically extracted; 'link_file' relies on the 'extra' dict.
    json_formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(module)s %(funcName)s %(message)s %(link_file)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 2. Color Formatter: Used specifically for human-readable console output.
    colored_formatter = ColoredFormatter()

    # --- Handler Configuration ---

    # 1. Console Handler (StreamHandler)
    # Directs logs to standard output (stdout) to ensure they appear in the terminal.
    console_handler = logging.StreamHandler(sys.stdout)

    if console_json:
        # In production/containers, structured JSON is often preferred even on stdout
        console_handler.setFormatter(json_formatter)
    else:
        # In local development, colorized text is easier to read
        console_handler.setFormatter(colored_formatter)

    root_logger.addHandler(console_handler)

    # 2. File Handler
    # Directs logs to a file, strictly using JSON formatting for machine parsing (e.g., ELK stack).
    # This ensures that even if the console is set to text, we preserve structured data on disk.
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(json_formatter)
    root_logger.addHandler(file_handler)

    return root_logger


def backup_and_clean_previous_log_file(
        log_file: str ='application.log',
        back_folder: str ='log_history',
        clean: bool = True):
    logger = logging.getLogger()

    if os.path.exists(log_file):
        history_dir = back_folder
        if not os.path.exists(history_dir):
            os.makedirs(history_dir)
            logger.info(f"Built log archived dir: {history_dir}")

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archived_log_name = f"iis_{timestamp}.log"
        archived_log_path = os.path.join(history_dir, archived_log_name)

        try:
            shutil.copy2(log_file, archived_log_path)
            logger.info(f"log_file log file: {log_file} -> {archived_log_path}")

            if clean:
                os.remove(log_file)
                logger.info(f"Removed log file: {log_file}")

        except Exception as e:
            logger.info(f"Process log file exception: {e}")


def limit_logger_level(logger_name: str, level = logging.WARNING):
    _logger = logging.getLogger(logger_name)
    _logger.setLevel(level)


def inspect_logger(logger_name: str):
    """检查并打印一个 logger 的详细状态"""
    logger = logging.getLogger(logger_name)

    print(f"\n--- Inspecting logger: '{logger.name}' ---")
    print(f"Effective Level: {logging.getLevelName(logger.getEffectiveLevel())}")
    print(f"Propagate: {logger.propagate}")
    print(f"Handlers: {logger.handlers}")

    if not logger.handlers:
        print("Logger has no direct handlers.")
    else:
        for i, handler in enumerate(logger.handlers):
            print(f"  - Handler {i}: {handler.__class__.__name__}")
            print(f"    - Level: {logging.getLevelName(handler.level)}")
            print(f"    - Formatter: {handler.formatter}")

    if logger.parent:
        print(f"Parent logger: '{logger.parent.name}'")
    else:
        print("This is the root logger or a logger with no parent.")


# --------------------------------------------------
#                    TLS Logger
# --------------------------------------------------

"""
Thread-Local Logging Proxy with Leveling Support

This module provides a thread-local logger mechanism where loggers can either:
1. Reuse a parent logger stored in thread-local storage (TLS) for all messages (non-leveling).
2. Create hierarchical child loggers under the parent (leveling mode).

Key Components:
- `_tls`: Thread-local storage for the parent logger and cached proxy loggers.
- `set_tls_logger()`: Sets the parent logger in TLS and clears cached proxies.
- `_LazyTLSLogger`: Proxy that lazily creates real loggers on first use.

Usage:

1. Set a parent logger for the current thread:
   >>> set_tls_logger(logging.getLogger("app"))

2. Create proxy loggers:
   >>> logger_plain = _LazyTLSLogger("module", use_leveling=False)  # Reuses parent
   >>> logger_level = _LazyTLSLogger("module.sub", use_leveling=True)  # Child of parent

3. Use like a standard logger:
   >>> logger_plain.info("Message")  # Logged under parent "app"
   >>> logger_level.debug("Detail")  # Logged under "app.module.sub"

Design:
- Non-Leveling Mode: All messages use the SAME parent logger from TLS.
- Leveling Mode: Creates hierarchical loggers (parent.child) for granular control.
- Caching: Proxies cache real loggers in TLS to avoid repeated creation.

Example Workflow:

# Main thread
parent_logger = logging.getLogger("app")
set_tls_logger(parent_logger)

# In a worker thread
def worker():
    set_tls_logger(parent_logger)  # Inherit parent
    task_logger = _LazyTLSLogger("worker", use_leveling=False)
    task_logger.error("Error!")  # Uses "app"

    detail_logger = _LazyTLSLogger("worker.db", use_leveling=True)
    detail_logger.info("Query")  # Uses "app.worker.db"
"""

_tls = threading.local()
_tls_lock = threading.Lock()


def _get_parent() -> Optional[Union[logging.Logger, str]]:
    """Retrieve the parent logger from thread-local storage."""
    return getattr(_tls, "logger", None)


class _LazyTLSLogger:
    """
    A lazy proxy logger that defers creation until first use, supporting two modes:
    - Non-Leveling: Directly uses the parent logger from TLS.
    - Leveling: Creates a hierarchical child logger under the parent.

    Args:
        base_name: Base name for the logger (ignored in non-leveling mode).
        use_leveling: If True, creates hierarchical loggers; else uses parent directly.

    Usage:
        # In a thread with parent logger set via `set_tls_logger()`
        logger = _LazyTLSLogger("module.sub", use_leveling=True)
        logger.info("Message")  # Real logger created here
    """
    __slots__ = ("_base_name", "_cache_key", "_use_leveling")

    def __init__(self, base_name: str, use_leveling: bool = False) -> None:
        self._base_name = base_name
        self._cache_key = f"_lazy_{'leveling' if use_leveling else 'plain'}_{base_name}"
        self._use_leveling = use_leveling

    def _create_real(self) -> logging.Logger:
        """Create the real logger based on the current TLS parent and mode."""
        parent = _get_parent()
        if parent is None:
            return logging.getLogger(self._base_name)

        if self._use_leveling:
            parent_name = parent.name if isinstance(parent, logging.Logger) else parent
            if not parent_name.strip():  # Avoid empty base names
                return logging.getLogger(self._base_name)

            return logging.getLogger(f"{parent_name}.{self._base_name}")
        else:
            # Non-leveling: reuse parent logger object directly
            return parent if isinstance(parent, logging.Logger) else logging.getLogger(parent)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._real_logger(), name)

    def __setattr__(self, key: str, value: Any) -> None:
        if key in self.__slots__:
            super().__setattr__(key, value)
        else:
            setattr(self._real_logger(), key, value)

    def __delattr__(self, name: str) -> None:
        delattr(self._real_logger(), name)

    def _real_logger(self) -> logging.Logger:
        """Return the real logger, creating and caching it if necessary."""
        if (real := getattr(_tls, self._cache_key, None)) is None:
            with _tls_lock:  # Ensure thread safety for the same thread
                if (real := getattr(_tls, self._cache_key, None)) is None:
                    real = self._create_real()
                    setattr(_tls, self._cache_key, real)
        return real


def set_tls_logger(
        logger: Union[logging.Logger, str, None]
) -> Optional[Union[logging.Logger, str]]:
    """
    Set the parent logger for the current thread and clear cached proxies.

    Args:
        logger: The parent logger (a Logger object, string name, or None to clear).

    Returns:
        The previous parent logger.

    Usage:
        # Set a new parent logger
        old_logger = set_tls_logger(logging.getLogger("new_parent"))

        # Clear the parent logger for the thread
        set_tls_logger(None)
    """
    with _tls_lock:
        old = _get_parent()

        if isinstance(logger, str):
            logger = logging.getLogger(logger)

        if logger is None:
            if hasattr(_tls, "logger"):
                del _tls.logger
        else:
            _tls.logger = logger

        # Clear cached proxy loggers
        keys_to_delete = [key for key in vars(_tls)
                          if key.startswith(("_lazy_plain_", "_lazy_leveling_"))]
        for key in keys_to_delete:
            try:
                delattr(_tls, key)
            except AttributeError:
                pass

        return old



def get_tls_logger(name: str) -> _LazyTLSLogger:
    """Delay-create logger named *name* (no leveling)."""
    return _LazyTLSLogger(name, use_leveling=False)


def create_tls_leveling_logger(name: str) -> _LazyTLSLogger:
    """Delay-create logger by appending *name* to TLS parent."""
    return _LazyTLSLogger(name, use_leveling=True)
