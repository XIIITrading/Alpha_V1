# polygon/__init__.py - Public API for the Polygon module
"""
Polygon.io Data Integration Module

A comprehensive Python module for fetching, caching, and managing market data from Polygon.io.
Provides intelligent rate limiting, local caching, data validation, and batch operations.

Basic Usage:
    from polygon import get_bars, get_latest_price, validate_symbol
    
    # Fetch historical data
    df = get_bars('AAPL', timeframe='5min', start='2024-01-01', end='2024-01-31')
    
    # Get latest price
    price = get_latest_price('AAPL')
    
    # Validate symbol
    is_valid = validate_symbol('AAPL')

Advanced Usage:
    from polygon import PolygonDataManager, get_storage_statistics
    
    # Create data manager for advanced operations
    manager = PolygonDataManager()
    
    # Fetch multiple symbols
    data = manager.fetch_multiple_symbols(['AAPL', 'GOOGL'], '1d')
    
    # Check cache statistics
    stats = get_storage_statistics()
"""

# Version info
__version__ = '1.0.0'
__author__ = 'AlphaXIII'

# Import core functionality
from .config import get_config, PolygonConfig
from .exceptions import (
    PolygonError,
    PolygonAPIError,
    PolygonAuthenticationError,
    PolygonRateLimitError,
    PolygonSymbolError,
    PolygonDataError,
    PolygonTimeRangeError,
    PolygonStorageError,
    PolygonConfigurationError,
    PolygonNetworkError
)

# Import main components
from .core import PolygonClient
from .fetcher import DataFetcher, BatchDataFetcher
from .storage import StorageManager, get_storage_manager
from .rate_limiter import RateLimiter, get_rate_limiter

# Import API validator
from .api_validator import PolygonAPIValidator, validate_polygon_features
from .validators.api_features import APIFeatureValidator
from .websocket import PolygonWebSocketClient

# Import utilities
from .utils import (
    parse_timeframe,
    validate_symbol,
    parse_date,
    format_date_for_api,
    is_market_open,
    is_extended_hours,
    normalize_ohlcv_data,
    validate_ohlcv_data,
    resample_ohlcv
)

# Import validators
from .validators import (
    validate_symbol_detailed,
    validate_ohlcv_integrity,
    detect_gaps,
    detect_price_anomalies,
    generate_validation_summary
)

# Simple public API functions
def get_bars(symbol: str, timeframe: str = '1day', 
             start: str = None, end: str = None,
             use_cache: bool = True, validate: bool = True) -> 'pd.DataFrame':
    """
    Get OHLCV bars for a symbol.
    
    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL')
        timeframe: Bar timeframe ('1min', '5min', '15min', '30min', '1hour', '1day')
        start: Start date (YYYY-MM-DD format or datetime)
        end: End date (YYYY-MM-DD format or datetime)
        use_cache: Use local cache if available
        validate: Validate and clean data
        
    Returns:
        DataFrame with OHLCV data
        
    Example:
        df = get_bars('AAPL', '5min', start='2024-01-01', end='2024-01-31')
    """
    from datetime import datetime, timedelta
    import pandas as pd
    
    # Default date range if not specified
    if end is None:
        end = datetime.now()
    if start is None:
        start = pd.Timestamp(end) - timedelta(days=30)
        
    fetcher = DataFetcher()
    return fetcher.fetch_data(
        symbol=symbol,
        timeframe=timeframe,
        start_date=start,
        end_date=end,
        use_cache=use_cache,
        validate=validate
    )


def get_latest_price(symbol: str) -> float:
    """
    Get the latest price for a symbol.
    
    Args:
        symbol: Stock ticker symbol
        
    Returns:
        Latest price as float, or None if not available
        
    Example:
        price = get_latest_price('AAPL')
    """
    fetcher = DataFetcher()
    df = fetcher.fetch_latest_bars(symbol, timeframe='1min', bars=1)
    
    if not df.empty:
        return float(df['close'].iloc[-1])
    return None


def get_latest_bars(symbol: str, timeframe: str = '1min', bars: int = 100) -> 'pd.DataFrame':
    """
    Get the most recent N bars for a symbol.
    
    Args:
        symbol: Stock ticker symbol
        timeframe: Bar timeframe
        bars: Number of bars to fetch
        
    Returns:
        DataFrame with recent OHLCV data
        
    Example:
        df = get_latest_bars('AAPL', '5min', bars=20)
    """
    fetcher = DataFetcher()
    return fetcher.fetch_latest_bars(symbol, timeframe, bars)


def validate_ticker(symbol: str) -> bool:
    """
    Check if a ticker symbol is valid.
    
    Args:
        symbol: Stock ticker symbol to validate
        
    Returns:
        True if valid, False otherwise
        
    Example:
        if validate_ticker('AAPL'):
            print("Valid symbol")
    """
    try:
        result = validate_symbol_detailed(symbol)
        if result['valid']:
            # Double-check with API
            client = PolygonClient()
            return client.validate_ticker(symbol)
        return False
    except:
        return False


def clear_cache(symbol: str = None, older_than_days: int = None) -> dict:
    """
    Clear cached data.
    
    Args:
        symbol: Clear specific symbol (None for all)
        older_than_days: Clear data older than N days
        
    Returns:
        Dictionary with cleanup statistics
        
    Example:
        stats = clear_cache(older_than_days=30)
    """
    storage = get_storage_manager()
    return storage.clear_cache(symbol=symbol, older_than_days=older_than_days)


def get_storage_statistics() -> dict:
    """
    Get cache storage statistics.
    
    Returns:
        Dictionary with storage usage information
        
    Example:
        stats = get_storage_statistics()
        print(f"Cache size: {stats['total_size_mb']:.2f} MB")
    """
    storage = get_storage_manager()
    return storage.get_cache_statistics()


def get_rate_limit_status() -> dict:
    """
    Get current rate limit status.
    
    Returns:
        Dictionary with current usage vs limits
        
    Example:
        status = get_rate_limit_status()
        print(f"Requests used today: {status['daily']['used']}/{status['daily']['limit']}")
    """
    limiter = get_rate_limiter()
    return limiter.get_current_usage()


def check_market_status() -> dict:
    """
    Check if the market is currently open.
    
    Returns:
        Dictionary with market status information
        
    Example:
        status = check_market_status()
        if status['is_open']:
            print("Market is open")
    """
    from datetime import datetime
    
    current_time = datetime.now()
    return {
        'is_open': is_market_open(current_time),
        'is_extended_hours': is_extended_hours(current_time),
        'current_time': current_time.isoformat(),
        'timezone': 'UTC'
    }


def validate_api_features(use_cache: bool = True) -> dict:
    """
    Validate all Polygon API features.
    
    Tests API functionality and access to all features in your subscription tier.
    
    Args:
        use_cache: Use cached validation results if available
        
    Returns:
        Dictionary with validation results for all features
        
    Example:
        results = validate_api_features()
        print(f"API Status: {results['overall_status']}")
    """
    import asyncio
    validator = PolygonAPIValidator()
    
    # Run async validation in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(validator.validate_all_features(use_cache=use_cache))
    finally:
        loop.close()


# Advanced API - Main data manager class
class PolygonDataManager:
    """
    Main interface for advanced Polygon data operations.
    
    Provides high-level methods for data fetching, caching, and management
    with full control over all module features.
    
    Example:
        manager = PolygonDataManager()
        
        # Fetch with custom settings
        df = manager.fetch_data('AAPL', '5min', start, end, validate=True)
        
        # Batch operations
        universe = manager.fetch_universe(['AAPL', 'GOOGL', 'MSFT'], '1day')
    """
    
    def __init__(self, config: PolygonConfig = None):
        """Initialize data manager with optional custom configuration."""
        self.config = config or get_config()
        self.fetcher = DataFetcher(config=self.config)
        self.batch_fetcher = BatchDataFetcher(config=self.config)
        self.storage = get_storage_manager()
        self.rate_limiter = get_rate_limiter()
        self.client = PolygonClient(config=self.config)
        self.api_validator = PolygonAPIValidator(client=self.client)
        
    def fetch_data(self, symbol: str, timeframe: str,
                   start_date, end_date, **kwargs) -> 'pd.DataFrame':
        """Fetch data with full control over options."""
        return self.fetcher.fetch_data(
            symbol, timeframe, start_date, end_date, **kwargs
        )
        
    def fetch_multiple_symbols(self, symbols: list, timeframe: str,
                              start_date, end_date, **kwargs) -> dict:
        """Fetch data for multiple symbols in parallel."""
        return self.fetcher.fetch_multiple_symbols(
            symbols, timeframe, start_date, end_date, **kwargs
        )
        
    def fetch_universe(self, symbols: list, timeframe: str,
                      start_date, end_date, **kwargs) -> 'pd.DataFrame':
        """Fetch aligned data for multiple symbols."""
        return self.batch_fetcher.fetch_universe(
            symbols, timeframe, start_date, end_date, **kwargs
        )
        
    def update_cache(self, symbol: str, timeframe: str) -> dict:
        """Update cached data to current time."""
        return self.fetcher.update_cache(symbol, timeframe)
        
    def validate_data(self, df: 'pd.DataFrame', symbol: str, 
                     timeframe: str) -> dict:
        """Run comprehensive validation on dataset."""
        return self.fetcher.validate_dataset(df, symbol, timeframe)
        
    def validate_api_features(self, use_cache: bool = True) -> dict:
        """Validate all Polygon API features."""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self.api_validator.validate_all_features(use_cache=use_cache)
            )
        finally:
            loop.close()
    
    def get_data_summary(self, symbol: str, timeframe: str,
                        start_date, end_date) -> dict:
        """Get summary of data availability without fetching."""
        return self.fetcher.get_data_summary(
            symbol, timeframe, start_date, end_date
        )
        
    def search_symbols(self, query: str, active_only: bool = True) -> list:
        """Search for symbols by name or ticker."""
        response = self.client.search_tickers(query, active=active_only)
        if 'results' in response:
            return [
                {
                    'symbol': r.get('ticker'),
                    'name': r.get('name'),
                    'type': r.get('type'),
                    'exchange': r.get('primary_exchange')
                }
                for r in response['results']
            ]
        return []
        
    def get_ticker_details(self, symbol: str) -> dict:
        """Get detailed information about a ticker."""
        return self.client.get_ticker_details(symbol)
        
    def clear_cache(self, symbol: str = None, timeframe: str = None,
                   older_than_days: int = None) -> dict:
        """Clear cache with specific criteria."""
        return self.storage.clear_cache(
            symbol=symbol,
            timeframe=timeframe,
            older_than_days=older_than_days
        )
        
    def optimize_storage(self) -> dict:
        """Optimize cache storage by removing duplicates and recompressing."""
        return self.storage.optimize_cache()
        
    def get_statistics(self) -> dict:
        """Get comprehensive module statistics."""
        return {
            'storage': self.storage.get_cache_statistics(),
            'rate_limit': self.rate_limiter.get_statistics(),
            'config': self.config.to_dict()
        }


# Module initialization
def initialize(api_key: str = None, **config_overrides):
    """
    Initialize the polygon module with custom settings.
    
    Args:
        api_key: Polygon API key (if not in environment)
        **config_overrides: Override default configuration
        
    Example:
        import polygon
        polygon.initialize(api_key='your-key', subscription_tier='starter')
    """
    if api_key:
        import os
        os.environ['POLYGON_API_KEY'] = api_key
        
    # Reset config with overrides
    from .config import get_config
    get_config(reset=True, **config_overrides)

# Simple API functions
async def stream_trades(symbols, callback):
    """Stream real-time trades"""
    client = PolygonWebSocketClient()
    await client.connect()
    await client.subscribe(symbols, ['T'], callback)
    return client

# List of main public exports
__all__ = [
    # Simple API functions
    'get_bars',
    'get_latest_price',
    'get_latest_bars',
    'validate_ticker',
    'clear_cache',
    'get_storage_statistics',
    'get_rate_limit_status',
    'check_market_status',
    'validate_api_features',
    'initialize',
    
    # Advanced API
    'PolygonDataManager',
    
    # Core classes for direct use
    'PolygonClient',
    'DataFetcher',
    'BatchDataFetcher',
    'StorageManager',
    'RateLimiter',
    'PolygonAPIValidator',
    
    # Configuration
    'PolygonConfig',
    'get_config',
    
    # Exceptions
    'PolygonError',
    'PolygonAPIError',
    'PolygonAuthenticationError',
    'PolygonRateLimitError',
    'PolygonSymbolError',
    'PolygonDataError',
    'PolygonTimeRangeError',
    'PolygonStorageError',
    'PolygonConfigurationError',
    'PolygonNetworkError',
    
    # Utilities
    'parse_timeframe',
    'validate_symbol',
    'parse_date',
    'is_market_open',
    'is_extended_hours',
    
    # API validation
    'validate_polygon_features',
    'APIFeatureValidator',
    
    # Websocket
    'PolygonWebSocketClient',
    'stream_trades',

    # Version
    '__version__'
]