import logging
import logging.handlers
import os
from datetime import datetime
from pathlib import Path

class CustomLogger:
    """Custom logger with file and console output"""
    
    def __init__(self, name: str, level: str = "DEBUG"):
        self._name = name
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))
        
        # Clear any existing handlers to avoid duplicates
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # Create temp_logs directory in current directory
        logs_dir = Path(os.getcwd()) / 'temp_logs'
        logs_dir.mkdir(exist_ok=True)
        
        # Create file handler
        try:
            file_handler = logging.handlers.RotatingFileHandler(
                filename=logs_dir / f"{name}.log",
                maxBytes=5 * 1024 * 1024,  # 5 MB
                backupCount=3
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except Exception as e:
            print(f"Warning: Could not create log file for {name}: {str(e)}")
            # Continue even if file logging fails
        
        # Create console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
    @property
    def name(self):
        return self._name
        
    def debug(self, message):
        self.logger.debug(message)
        
    def info(self, message):
        self.logger.info(message)
        
    def warning(self, message):
        self.logger.warning(message)
        
    def error(self, message):
        self.logger.error(message)
        
    def critical(self, message):
        self.logger.critical(message)
    
    def exception(self, message: str, *args, exc_info=True, **kwargs):
        self.logger.exception(message, *args, exc_info=exc_info, **kwargs)

# Create a decorator for error handling
def error_handler(logger):
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Error in {func.__name__}: {str(e)}")
                raise
        return wrapper
    return decorator 