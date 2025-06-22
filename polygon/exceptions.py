"""
Custom exceptions for Polygon.io module.
""" 

# polygon/exceptions.py - Custom exceptions for the Polygon module
"""
Custom exception classes for the Polygon module.
Provides specific error types for different failure scenarios.
"""

from typing import Optional, Dict, Any
from datetime import datetime


class PolygonError(Exception):
    """
    [CLASS SUMMARY]
    Purpose: Base exception class for all Polygon module errors
    Usage: Base class for inheritance, rarely raised directly
    Attributes:
        - message: Error description
        - details: Additional context dictionary
        - timestamp: When the error occurred (UTC)
    """
    
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize base exception with message and optional details
        Parameters:
            - message (str): Human-readable error description
            - details (dict, optional): Additional context about the error
        Example: PolygonError("API request failed", {"status_code": 500})
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}
        self.timestamp = datetime.utcnow()
        
    def __str__(self) -> str:
        """Format error message with details if available"""
        if self.details:
            details_str = ", ".join(f"{k}={v}" for k, v in self.details.items())
            return f"{self.message} ({details_str})"
        return self.message


class PolygonAPIError(PolygonError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when Polygon API returns an error response
    Usage: Handle API-specific errors like invalid requests or server errors
    Common scenarios:
        - 400: Bad Request (invalid parameters)
        - 401: Unauthorized (invalid API key)
        - 403: Forbidden (subscription limit)
        - 404: Not Found (invalid symbol)
        - 500: Internal Server Error
    """
    
    def __init__(self, message: str, status_code: Optional[int] = None, 
                 response_body: Optional[str] = None, **kwargs):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize API error with HTTP details
        Parameters:
            - message (str): Error description
            - status_code (int, optional): HTTP status code
            - response_body (str, optional): Raw API response
            - **kwargs: Additional details
        Example: PolygonAPIError("Invalid API key", status_code=401)
        """
        details = kwargs
        if status_code:
            details['status_code'] = status_code
        if response_body:
            details['response_body'] = response_body
            
        super().__init__(message, details)
        self.status_code = status_code
        self.response_body = response_body


class PolygonAuthenticationError(PolygonAPIError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when API key is invalid or missing
    Usage: Specific handling for authentication failures
    Note: Inherits from PolygonAPIError with status_code=401
    """
    
    def __init__(self, message: str = "Invalid or missing API key", **kwargs):
        """Initialize authentication error"""
        super().__init__(message, status_code=401, **kwargs)


class PolygonRateLimitError(PolygonAPIError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when API rate limit is exceeded
    Usage: Implement retry logic with backoff
    Attributes:
        - retry_after: Seconds to wait before retrying
        - limit_type: Which limit was hit (minute/day)
    """
    
    def __init__(self, message: str = "Rate limit exceeded", 
                 retry_after: Optional[int] = None, 
                 limit_type: Optional[str] = None, **kwargs):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize rate limit error with retry information
        Parameters:
            - message (str): Error description
            - retry_after (int, optional): Seconds to wait
            - limit_type (str, optional): 'minute' or 'day'
        Example: PolygonRateLimitError(retry_after=60, limit_type='minute')
        """
        details = kwargs
        if retry_after:
            details['retry_after'] = retry_after
        if limit_type:
            details['limit_type'] = limit_type
            
        super().__init__(message, status_code=429, **details)
        self.retry_after = retry_after
        self.limit_type = limit_type


class PolygonSymbolError(PolygonError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when a symbol/ticker is invalid or not found
    Usage: Handle invalid ticker symbols
    Attributes:
        - symbol: The invalid symbol
        - suggestions: List of similar valid symbols (if available)
    """
    
    def __init__(self, symbol: str, message: Optional[str] = None, 
                 suggestions: Optional[list] = None, **kwargs):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize symbol error with suggestions
        Parameters:
            - symbol (str): The invalid symbol
            - message (str, optional): Custom error message
            - suggestions (list, optional): Similar valid symbols
        Example: PolygonSymbolError("AAPL1", suggestions=["AAPL", "AAPL.W"])
        """
        if message is None:
            message = f"Invalid or unknown symbol: {symbol}"
            
        details = kwargs
        details['symbol'] = symbol
        if suggestions:
            details['suggestions'] = suggestions
            
        super().__init__(message, details)
        self.symbol = symbol
        self.suggestions = suggestions or []


class PolygonDataError(PolygonError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when data validation fails or data is corrupted
    Usage: Handle data quality issues
    Common scenarios:
        - Missing required fields
        - Invalid timestamps
        - Negative prices/volumes
        - Data gaps
    """
    
    def __init__(self, message: str, data_type: Optional[str] = None,
                 field: Optional[str] = None, value: Any = None, **kwargs):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize data error with validation details
        Parameters:
            - message (str): Error description
            - data_type (str, optional): Type of data (e.g., 'ohlcv', 'trades')
            - field (str, optional): Field that failed validation
            - value (Any, optional): The invalid value
        Example: PolygonDataError("Negative price", field="close", value=-10.5)
        """
        details = kwargs
        if data_type:
            details['data_type'] = data_type
        if field:
            details['field'] = field
        if value is not None:
            details['value'] = value
            
        super().__init__(message, details)
        self.data_type = data_type
        self.field = field
        self.value = value


class PolygonTimeRangeError(PolygonError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when requested time range is invalid
    Usage: Handle date/time parameter errors
    Common scenarios:
        - Start date after end date
        - Date range too large for subscription
        - Requesting future data
        - Date before available history
    """
    
    def __init__(self, message: str, start_date: Optional[datetime] = None,
                 end_date: Optional[datetime] = None, max_range: Optional[str] = None, **kwargs):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize time range error
        Parameters:
            - message (str): Error description
            - start_date (datetime, optional): Requested start
            - end_date (datetime, optional): Requested end
            - max_range (str, optional): Maximum allowed range
        Example: PolygonTimeRangeError("Range too large", max_range="2 years")
        """
        details = kwargs
        if start_date:
            details['start_date'] = start_date.isoformat()
        if end_date:
            details['end_date'] = end_date.isoformat()
        if max_range:
            details['max_range'] = max_range
            
        super().__init__(message, details)
        self.start_date = start_date
        self.end_date = end_date
        self.max_range = max_range


class PolygonStorageError(PolygonError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when local storage operations fail
    Usage: Handle cache and file system errors
    Common scenarios:
        - Disk full
        - Permission denied
        - Corrupted cache database
        - Parquet file errors
    """
    
    def __init__(self, message: str, operation: Optional[str] = None,
                 path: Optional[str] = None, **kwargs):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize storage error
        Parameters:
            - message (str): Error description
            - operation (str, optional): Operation that failed (read/write/delete)
            - path (str, optional): File or directory path
        Example: PolygonStorageError("Permission denied", operation="write", path="/data/cache")
        """
        details = kwargs
        if operation:
            details['operation'] = operation
        if path:
            details['path'] = path
            
        super().__init__(message, details)
        self.operation = operation
        self.path = path


class PolygonConfigurationError(PolygonError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when configuration is invalid or missing
    Usage: Handle setup and configuration issues
    Common scenarios:
        - Missing API key
        - Invalid configuration values
        - Incompatible settings
    """
    
    def __init__(self, message: str, config_key: Optional[str] = None,
                 config_value: Any = None, **kwargs):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize configuration error
        Parameters:
            - message (str): Error description
            - config_key (str, optional): Configuration key that failed
            - config_value (Any, optional): The invalid value
        Example: PolygonConfigurationError("Invalid tier", config_key="subscription_tier", config_value="pro")
        """
        details = kwargs
        if config_key:
            details['config_key'] = config_key
        if config_value is not None:
            details['config_value'] = config_value
            
        super().__init__(message, details)
        self.config_key = config_key
        self.config_value = config_value


class PolygonNetworkError(PolygonError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when network connectivity issues occur
    Usage: Handle connection timeouts and network failures
    Common scenarios:
        - Connection timeout
        - DNS resolution failure
        - SSL certificate errors
        - Proxy issues
    """
    
    def __init__(self, message: str, url: Optional[str] = None,
                 timeout: Optional[int] = None, **kwargs):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize network error
        Parameters:
            - message (str): Error description
            - url (str, optional): URL that failed
            - timeout (int, optional): Timeout value in seconds
        Example: PolygonNetworkError("Connection timeout", url="https://api.polygon.io", timeout=30)
        """
        details = kwargs
        if url:
            details['url'] = url
        if timeout:
            details['timeout'] = timeout
            
        super().__init__(message, details)
        self.url = url
        self.timeout = timeout


class PolygonWebSocketError(PolygonError):
    """
    [CLASS SUMMARY]
    Purpose: Raised when WebSocket connection issues occur
    Usage: Handle real-time data stream errors
    Common scenarios:
        - Connection dropped
        - Invalid subscription
        - Message parsing errors
    """
    
    def __init__(self, message: str, connection_state: Optional[str] = None,
                 subscription: Optional[str] = None, **kwargs):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize WebSocket error
        Parameters:
            - message (str): Error description
            - connection_state (str, optional): Current connection state
            - subscription (str, optional): Failed subscription details
        Example: PolygonWebSocketError("Connection lost", connection_state="disconnected")
        """
        details = kwargs
        if connection_state:
            details['connection_state'] = connection_state
        if subscription:
            details['subscription'] = subscription
            
        super().__init__(message, details)
        self.connection_state = connection_state
        self.subscription = subscription


# Exception utility functions
def is_retryable_error(error: Exception) -> bool:
    """
    [FUNCTION SUMMARY]
    Purpose: Determine if an error should trigger a retry
    Parameters:
        - error (Exception): The error to check
    Returns: bool - True if error is retryable
    Example: if is_retryable_error(e): retry_with_backoff()
    """
    # Rate limit errors are retryable after waiting
    if isinstance(error, PolygonRateLimitError):
        return True
    
    # Network errors are often transient
    if isinstance(error, PolygonNetworkError):
        return True
    
    # Some API errors are retryable
    if isinstance(error, PolygonAPIError):
        # 5xx errors are server issues, likely temporary
        if error.status_code and 500 <= error.status_code < 600:
            return True
        # 408 Request Timeout
        if error.status_code == 408:
            return True
    
    # WebSocket disconnections can be retried
    if isinstance(error, PolygonWebSocketError):
        return error.connection_state == "disconnected"
    
    return False


def get_retry_delay(error: Exception, attempt: int = 1) -> int:
    """
    [FUNCTION SUMMARY]
    Purpose: Calculate delay before retrying after an error
    Parameters:
        - error (Exception): The error that occurred
        - attempt (int): Retry attempt number (1-based)
    Returns: int - Seconds to wait before retry
    Example: time.sleep(get_retry_delay(error, attempt=2))
    """
    # Rate limit errors may specify retry delay
    if isinstance(error, PolygonRateLimitError) and error.retry_after:
        return error.retry_after
    
    # Exponential backoff for other errors
    base_delay = 1  # Start with 1 second
    max_delay = 300  # Cap at 5 minutes
    
    # Calculate exponential backoff with jitter
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    
    # Add jitter to prevent thundering herd
    import random
    jitter = random.uniform(0, delay * 0.1)  # Up to 10% jitter
    
    return int(delay + jitter)