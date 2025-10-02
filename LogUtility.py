import datetime
import os
import shutil
import sys
import logging
from pythonjsonlogger import jsonlogger


# Configure root logger with JSON formatting
def setup_logging(log_file='application.log'):
    """Configure structured JSON logging for all modules"""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    root_logger.handlers = []

    # JSON formatter with structured data
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(name)s %(levelname)s %(module)s %(funcName)s %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # File handler
    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(formatter)
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
