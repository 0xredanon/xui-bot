class BotError(Exception):
    """Base exception class for bot-related errors"""
    def __init__(self, message: str = None):
        self.message = message
        super().__init__(self.message)

class ConfigError(BotError):
    """Raised when there's an error in configuration"""
    pass

class DatabaseError(BotError):
    """Raised when there's a database-related error"""
    pass

class APIError(BotError):
    """Raised when there's an API-related error"""
    def __init__(self, message: str = None, status_code: int = None):
        self.status_code = status_code
        super().__init__(message)

class CommandError(BotError):
    """Raised when there's an error executing a command"""
    pass

class ValidationError(BotError):
    """Raised when there's a validation error"""
    pass

class AuthenticationError(BotError):
    """Raised when there's an authentication error"""
    pass

class RateLimitError(BotError):
    """Raised when rate limit is exceeded"""
    def __init__(self, message: str = None, retry_after: int = None):
        self.retry_after = retry_after
        super().__init__(message)

class NetworkError(BotError):
    """Raised when there's a network-related error"""
    pass 