# polygon/fetcher.py - High-level data fetching for the Polygon module
"""
High-level data fetching module that orchestrates API calls, caching,
rate limiting, and data validation for efficient market data retrieval.
"""

import asyncio
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union, Any, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

from .config import get_config, POLYGON_TIMEZONE
from .core import PolygonClient
from .storage import get_storage_manager, StorageManager
from .rate_limiter import get_rate_limiter, RateLimiter
from .validators import (
    validate_ohlcv_integrity,
    detect_gaps,
    generate_validation_summary
)
from .utils import (
    parse_date,
    parse_timeframe,
    validate_symbol,
    format_date_for_api,
    split_large_date_range,
    normalize_ohlcv_data,
    validate_ohlcv_data,
    calculate_bars_in_range,
    estimate_data_size
)
from .exceptions import (
    PolygonError,
    PolygonAPIError,
    PolygonSymbolError,
    PolygonTimeRangeError,
    PolygonDataError
)


class DataFetcher:
    """
    [CLASS SUMMARY]
    Purpose: High-level interface for fetching market data
    Responsibilities:
        - Coordinate API calls with caching
        - Handle rate limiting automatically
        - Validate and clean data
        - Support batch operations
        - Manage large date ranges
        - Provide progress callbacks
    Usage:
        fetcher = DataFetcher()
        df = fetcher.fetch_data('AAPL', '5min', start_date, end_date)
    """
    
    def __init__(self, config=None, client=None, storage=None, rate_limiter=None):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize data fetcher with dependencies
        Parameters:
            - config (PolygonConfig, optional): Configuration instance
            - client (PolygonClient, optional): API client instance
            - storage (StorageManager, optional): Storage manager instance
            - rate_limiter (RateLimiter, optional): Rate limiter instance
        Example: fetcher = DataFetcher()
        """
        self.config = config or get_config()
        self.client = client or PolygonClient(self.config)
        self.storage = storage or get_storage_manager()
        self.rate_limiter = rate_limiter or get_rate_limiter()
        self.logger = self.config.get_logger(__name__)
        
        # Progress tracking
        self._progress_callback = None
        self._cancel_requested = False
        
    def fetch_data(self, symbol: str, timeframe: str,
                   start_date: Union[str, datetime],
                   end_date: Union[str, datetime],
                   use_cache: bool = True,
                   validate: bool = True,
                   fill_gaps: bool = False,
                   adjust_splits: bool = True) -> pd.DataFrame:
        """
        [FUNCTION SUMMARY]
        Purpose: Fetch market data with intelligent caching and validation
        Parameters:
            - symbol (str): Stock ticker symbol
            - timeframe (str): Data timeframe (e.g., '5min', '1d')
            - start_date: Start date for data
            - end_date: End date for data
            - use_cache (bool): Use local cache if available
            - validate (bool): Run data validation
            - fill_gaps (bool): Attempt to fill data gaps
            - adjust_splits (bool): Apply split adjustments
        Returns: DataFrame - OHLCV data
        Example: df = fetcher.fetch_data('AAPL', '5min', '2023-01-01', '2023-01-31')
        """
        # Validate inputs
        symbol = validate_symbol(symbol)
        start_dt = parse_date(start_date)
        end_dt = parse_date(end_date)
        multiplier, timespan = parse_timeframe(timeframe)
        
        # Log request
        self.logger.info(
            f"Fetching {symbol} {timeframe} data from {start_dt.date()} to {end_dt.date()}"
        )
        
        # Check cache first
        if use_cache:
            cached_df = self._fetch_from_cache(symbol, timeframe, start_dt, end_dt)
            if cached_df is not None and not cached_df.empty:
                # Check if cache fully covers requested range
                missing_ranges = self.storage.get_missing_ranges(
                    symbol, timeframe, start_dt, end_dt
                )
                
                if not missing_ranges:
                    self.logger.info(f"Returned {len(cached_df)} rows from cache")
                    if validate:
                        cached_df = self._validate_and_clean(cached_df, symbol, timeframe)
                    return cached_df
                    
                # Partial cache hit - fetch missing ranges
                self.logger.info(f"Partial cache hit, fetching {len(missing_ranges)} missing ranges")
                all_data = [cached_df]
                
                for missing_start, missing_end in missing_ranges:
                    missing_df = self._fetch_from_api(
                        symbol, multiplier, timespan, missing_start, missing_end, adjust_splits
                    )
                    if not missing_df.empty:
                        all_data.append(missing_df)
                        
                # Combine all data
                df = pd.concat(all_data).sort_index()
                df = df[~df.index.duplicated(keep='last')]
                
            else:
                # No cache, fetch all from API
                df = self._fetch_from_api(
                    symbol, multiplier, timespan, start_dt, end_dt, adjust_splits
                )
        else:
            # Skip cache, fetch directly from API
            df = self._fetch_from_api(
                symbol, multiplier, timespan, start_dt, end_dt, adjust_splits
            )
            
        # Save to cache
        if use_cache and not df.empty:
            try:
                self.storage.save_data(df, symbol, timeframe)
            except Exception as e:
                self.logger.warning(f"Failed to save to cache: {e}")
                
        # Validate and clean if requested
        if validate and not df.empty:
            df = self._validate_and_clean(df, symbol, timeframe)
            
        # Fill gaps if requested
        if fill_gaps and not df.empty:
            df = self._fill_data_gaps(df, timeframe)
            
        # Final date filtering to ensure we return exactly what was requested
        df = df[(df.index >= start_dt) & (df.index <= end_dt + timedelta(days=1))]
        
        self.logger.info(f"Returned {len(df)} rows for {symbol} {timeframe}")
        
        return df
        
    def _fetch_from_cache(self, symbol: str, timeframe: str,
                         start_date: datetime, end_date: datetime) -> Optional[pd.DataFrame]:
        """
        [FUNCTION SUMMARY]
        Purpose: Try to fetch data from local cache
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
            - start_date (datetime): Start date
            - end_date (datetime): End date
        Returns: DataFrame or None - Cached data if available
        """
        try:
            return self.storage.load_data(symbol, timeframe, start_date, end_date)
        except Exception as e:
            self.logger.warning(f"Cache read failed: {e}")
            return None
            
    def _fetch_from_api(self, symbol: str, multiplier: int, timespan: str,
                       start_date: datetime, end_date: datetime,
                       adjust_splits: bool = True) -> pd.DataFrame:
        """
        [FUNCTION SUMMARY]
        Purpose: Fetch data from Polygon API with rate limiting
        Parameters:
            - symbol (str): Stock symbol
            - multiplier (int): Timeframe multiplier
            - timespan (str): Timeframe unit
            - start_date (datetime): Start date
            - end_date (datetime): End date
            - adjust_splits (bool): Apply adjustments
        Returns: DataFrame - Fetched OHLCV data
        """
        all_data = []
        
        # Check if we need to split the date range
        max_days = self.config.max_days_per_request
        # For annual limits, no need to multiply by 365
        date_ranges = split_large_date_range(start_date, end_date, max_days)
        
        total_ranges = len(date_ranges)
        
        for i, (chunk_start, chunk_end) in enumerate(date_ranges):
            # Check for cancellation
            if self._cancel_requested:
                self.logger.info("Fetch cancelled by user")
                break
                
            # Update progress
            if self._progress_callback:
                progress = (i / total_ranges) * 100
                self._progress_callback(progress, f"Fetching chunk {i+1}/{total_ranges}")
                
            # Wait for rate limit
            wait_time = self.rate_limiter.wait_if_needed(priority=3)
            if wait_time > 0:
                self.logger.debug(f"Rate limit wait: {wait_time:.1f}s")
                
            try:
                # Make API request
                start_time = datetime.now()
                response = self.client.get_aggregates(
                    ticker=symbol,
                    multiplier=multiplier,
                    timespan=timespan,
                    from_date=format_date_for_api(chunk_start),
                    to_date=format_date_for_api(chunk_end),
                    adjusted=adjust_splits,
                    limit=50000
                )
                
                # Record request for rate limiting
                response_time = (datetime.now() - start_time).total_seconds()
                self.rate_limiter.record_request(response_time=response_time, success=True)
                
                # Process results
                if response.get('results'):
                    df_chunk = normalize_ohlcv_data(response['results'])
                    if not df_chunk.empty:
                        all_data.append(df_chunk)
                        self.logger.debug(
                            f"Fetched {len(df_chunk)} rows for "
                            f"{chunk_start.date()} to {chunk_end.date()}"
                        )
                else:
                    self.logger.warning(
                        f"No data returned for {symbol} "
                        f"{chunk_start.date()} to {chunk_end.date()}"
                    )
                    
            except PolygonAPIError as e:
                self.rate_limiter.record_request(success=False)
                if e.status_code == 404:
                    raise PolygonSymbolError(
                        symbol,
                        f"Symbol {symbol} not found or no data available"
                    )
                else:
                    raise
                    
            except Exception as e:
                self.rate_limiter.record_request(success=False)
                self.logger.error(f"API request failed: {e}")
                raise
                
        # Combine all chunks
        if all_data:
            df = pd.concat(all_data).sort_index()
            df = df[~df.index.duplicated(keep='last')]
            return df
        else:
            return pd.DataFrame()
            
    def _validate_and_clean(self, df: pd.DataFrame, symbol: str, 
                           timeframe: str) -> pd.DataFrame:
        """
        [FUNCTION SUMMARY]
        Purpose: Validate and clean fetched data
        Parameters:
            - df (DataFrame): Raw OHLCV data
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
        Returns: DataFrame - Cleaned data
        """
        if df.empty:
            return df
            
        # Run validation
        report = validate_ohlcv_integrity(df, symbol, timeframe)
        
        if not report.is_valid:
            self.logger.warning(
                f"Data validation issues for {symbol}: {report.issues}"
            )
            
        # Apply cleaning
        cleaned_df = validate_ohlcv_data(df, symbol)
        
        # Log if rows were removed
        if len(cleaned_df) < len(df):
            removed = len(df) - len(cleaned_df)
            self.logger.info(f"Removed {removed} invalid rows during cleaning")
            
        return cleaned_df
        
    def _fill_data_gaps(self, df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
        """
        [FUNCTION SUMMARY]
        Purpose: Fill gaps in data using forward fill or interpolation
        Parameters:
            - df (DataFrame): OHLCV data with gaps
            - timeframe (str): Data timeframe
        Returns: DataFrame - Data with gaps filled
        Note: Only fills small gaps to avoid creating misleading data
        """
        if df.empty or len(df) < 2:
            return df
            
        # Detect gaps
        gaps = detect_gaps(df, timeframe, market_hours_only=True)
        
        if not gaps['gaps']:
            return df
            
        # Only fill small gaps (less than 5 bars)
        multiplier, timespan = parse_timeframe(timeframe)
        
        for gap in gaps['gaps']:
            if gap['missing_bars'] <= 5:
                # Create expected index
                freq_mapping = {
                    'minute': f'{multiplier}T',
                    'hour': f'{multiplier}H',
                    'day': f'{multiplier}D'
                }
                
                if timespan in freq_mapping:
                    # Reindex to include missing timestamps
                    expected_index = pd.date_range(
                        start=gap['start'],
                        end=gap['end'],
                        freq=freq_mapping[timespan]
                    )
                    
                    # Forward fill prices, set volume to 0
                    df = df.reindex(df.index.union(expected_index))
                    df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].fillna(method='ffill')
                    df['volume'] = df['volume'].fillna(0)
                    
        self.logger.info(f"Filled {len(gaps['gaps'])} small gaps in data")
        
        return df
        
    def fetch_multiple_symbols(self, symbols: List[str], timeframe: str,
                              start_date: Union[str, datetime],
                              end_date: Union[str, datetime],
                              max_workers: int = 5,
                              **kwargs) -> Dict[str, pd.DataFrame]:
        """
        [FUNCTION SUMMARY]
        Purpose: Fetch data for multiple symbols in parallel
        Parameters:
            - symbols (list): List of stock symbols
            - timeframe (str): Data timeframe
            - start_date: Start date
            - end_date: End date
            - max_workers (int): Maximum parallel workers
            - **kwargs: Additional arguments for fetch_data
        Returns: dict - {symbol: DataFrame} mapping
        Example: data = fetcher.fetch_multiple_symbols(['AAPL', 'GOOGL'], '1d', start, end)
        """
        results = {}
        errors = {}
        
        # Estimate total time
        estimate = self.rate_limiter.estimate_time_for_requests(len(symbols))
        self.logger.info(
            f"Fetching {len(symbols)} symbols, estimated time: "
            f"{estimate['total_time_seconds']:.1f}s using {estimate['strategy']} strategy"
        )
        
        # Use ThreadPoolExecutor for parallel fetching
        with ThreadPoolExecutor(max_workers=min(max_workers, len(symbols))) as executor:
            # Submit all tasks
            future_to_symbol = {
                executor.submit(
                    self.fetch_data,
                    symbol,
                    timeframe,
                    start_date,
                    end_date,
                    **kwargs
                ): symbol
                for symbol in symbols
            }
            
            # Process completed tasks
            completed = 0
            for future in as_completed(future_to_symbol):
                symbol = future_to_symbol[future]
                completed += 1
                
                try:
                    df = future.result()
                    results[symbol] = df
                    self.logger.debug(f"Completed {symbol} ({completed}/{len(symbols)})")
                    
                    # Update progress
                    if self._progress_callback:
                        progress = (completed / len(symbols)) * 100
                        self._progress_callback(progress, f"Completed {symbol}")
                        
                except Exception as e:
                    errors[symbol] = str(e)
                    self.logger.error(f"Failed to fetch {symbol}: {e}")
                    
        # Log summary
        self.logger.info(
            f"Batch fetch complete: {len(results)} successful, {len(errors)} failed"
        )
        
        if errors:
            self.logger.warning(f"Failed symbols: {list(errors.keys())}")
            
        return results
        
    def fetch_latest_bars(self, symbols: Union[str, List[str]], 
                         timeframe: str = '1min',
                         bars: int = 100) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
        """
        [FUNCTION SUMMARY]
        Purpose: Fetch most recent bars for symbol(s)
        Parameters:
            - symbols: Single symbol or list of symbols
            - timeframe (str): Data timeframe
            - bars (int): Number of recent bars to fetch
        Returns: DataFrame or dict of DataFrames
        Example: df = fetcher.fetch_latest_bars('AAPL', '5min', bars=20)
        """
        # Calculate date range
        end_date = datetime.now(POLYGON_TIMEZONE)
        
        # Estimate start date based on bars and timeframe
        multiplier, timespan = parse_timeframe(timeframe)
        
        # Add buffer for weekends/holidays
        days_back = {
            'minute': max(1, bars * multiplier / 390) * 2,  # 390 minutes per trading day
            'hour': max(1, bars * multiplier / 6.5) * 2,    # 6.5 hours per trading day
            'day': bars * 2,                                 # Account for weekends
            'week': bars * 7,
            'month': bars * 31,
        }.get(timespan, bars)
        
        start_date = end_date - timedelta(days=int(days_back))
        
        # Handle single symbol vs multiple
        if isinstance(symbols, str):
            df = self.fetch_data(symbols, timeframe, start_date, end_date)
            # Return only the requested number of bars
            return df.tail(bars)
        else:
            results = self.fetch_multiple_symbols(
                symbols, timeframe, start_date, end_date
            )
            # Trim each result to requested bars
            return {
                symbol: df.tail(bars) for symbol, df in results.items()
            }
            
    def update_cache(self, symbol: str, timeframe: str) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Update cached data to current time
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
        Returns: dict - Update statistics
        Example: stats = fetcher.update_cache('AAPL', '5min')
        """
        stats = {
            'symbol': symbol,
            'timeframe': timeframe,
            'rows_added': 0,
            'cache_updated': False,
            'error': None
        }
        
        try:
            # Get current cache metadata
            metadata = self.storage.get_cache_metadata(symbol, timeframe)
            
            if metadata:
                # Fetch from last cached date to now
                start_date = metadata.end_date + timedelta(seconds=1)
                end_date = datetime.now(POLYGON_TIMEZONE)
                
                # Only update if there's a gap
                if start_date < end_date:
                    df = self.fetch_data(
                        symbol, timeframe, start_date, end_date,
                        use_cache=False  # Don't use cache for update
                    )
                    
                    if not df.empty:
                        stats['rows_added'] = len(df)
                        stats['cache_updated'] = True
                        self.logger.info(
                            f"Updated cache for {symbol} {timeframe}: "
                            f"added {len(df)} rows"
                        )
                else:
                    stats['error'] = "Cache already up to date"
            else:
                stats['error'] = "No existing cache to update"
                
        except Exception as e:
            stats['error'] = str(e)
            self.logger.error(f"Cache update failed: {e}")
            
        return stats
        
    def get_data_summary(self, symbol: str, timeframe: str,
                        start_date: Union[str, datetime],
                        end_date: Union[str, datetime]) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Get summary of data availability without fetching
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
            - start_date: Start date
            - end_date: End date
        Returns: dict - Data availability summary
        Example: summary = fetcher.get_data_summary('AAPL', '1d', start, end)
        """
        start_dt = parse_date(start_date)
        end_dt = parse_date(end_date)
        
        # Check cache coverage
        cached_ranges = []
        missing_ranges = []
        
        if self.storage.has_cache(symbol, timeframe):
            metadata = self.storage.get_cache_metadata(symbol, timeframe)
            if metadata:
                # Determine overlap with requested range
                cache_start = max(metadata.start_date, start_dt)
                cache_end = min(metadata.end_date, end_dt)
                
                if cache_start <= cache_end:
                    cached_ranges.append((cache_start, cache_end))
                    
            missing_ranges = self.storage.get_missing_ranges(
                symbol, timeframe, start_dt, end_dt
            )
        else:
            missing_ranges = [(start_dt, end_dt)]
            
        # Estimate data size and cost
        estimate = estimate_data_size(
            1,  # Single symbol
            (end_dt - start_dt).days,
            timeframe
        )
        
        # Calculate coverage
        total_days = (end_dt - start_dt).days
        cached_days = sum((end - start).days for start, end in cached_ranges)
        coverage_pct = (cached_days / total_days * 100) if total_days > 0 else 0
        
        return {
            'symbol': symbol,
            'timeframe': timeframe,
            'requested_range': {
                'start': start_dt.isoformat(),
                'end': end_dt.isoformat(),
                'days': total_days
            },
            'cache_coverage': {
                'percentage': round(coverage_pct, 2),
                'cached_ranges': [(s.isoformat(), e.isoformat()) for s, e in cached_ranges],
                'missing_ranges': [(s.isoformat(), e.isoformat()) for s, e in missing_ranges]
            },
            'estimated_bars': estimate['total_bars'],
            'estimated_size_mb': estimate['storage_mb'],
            'estimated_api_calls': estimate['api_calls'] if missing_ranges else 0,
            'data_available': coverage_pct == 100
        }
        
    def validate_dataset(self, df: pd.DataFrame, symbol: str, 
                        timeframe: str,
                        start_date: Optional[datetime] = None,
                        end_date: Optional[datetime] = None) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Run comprehensive validation on a dataset
        Parameters:
            - df (DataFrame): Data to validate
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
            - start_date (datetime, optional): Expected start
            - end_date (datetime, optional): Expected end
        Returns: dict - Validation report
        Example: report = fetcher.validate_dataset(df, 'AAPL', '5min')
        """
        return generate_validation_summary(
            df, symbol, timeframe, start_date, end_date
        )
        
    def set_progress_callback(self, callback: Optional[Callable[[float, str], None]]):
        """
        [FUNCTION SUMMARY]
        Purpose: Set callback for progress updates
        Parameters:
            - callback: Function(progress_pct, message) or None
        Example: fetcher.set_progress_callback(lambda p, m: print(f"{p:.1f}%: {m}"))
        """
        self._progress_callback = callback
        
    def cancel_operation(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Cancel ongoing fetch operation
        Example: fetcher.cancel_operation()
        """
        self._cancel_requested = True
        

class BatchDataFetcher(DataFetcher):
    """
    [CLASS SUMMARY]
    Purpose: Specialized fetcher for batch operations
    Note: Extends DataFetcher with optimizations for bulk data retrieval
    Usage:
        batch = BatchDataFetcher()
        universe = batch.fetch_universe(['AAPL', 'GOOGL', 'MSFT'], '1d', start, end)
    """
    
    def fetch_universe(self, symbols: List[str], timeframe: str,
                      start_date: Union[str, datetime],
                      end_date: Union[str, datetime],
                      aligned: bool = True,
                      min_data_pct: float = 80) -> pd.DataFrame:
        """
        [FUNCTION SUMMARY]
        Purpose: Fetch aligned data for multiple symbols
        Parameters:
            - symbols (list): List of symbols
            - timeframe (str): Data timeframe
            - start_date: Start date
            - end_date: End date
            - aligned (bool): Align all symbols to same timestamps
            - min_data_pct (float): Minimum data percentage to include symbol
        Returns: DataFrame - Multi-index DataFrame with all symbols
        Example: universe = batch.fetch_universe(['AAPL', 'GOOGL'], '1d', start, end)
        """
        # Fetch all symbols
        all_data = self.fetch_multiple_symbols(
            symbols, timeframe, start_date, end_date,
            validate=True, use_cache=True
        )
        
        # Filter symbols with insufficient data
        valid_symbols = []
        for symbol, df in all_data.items():
            if not df.empty:
                expected_bars = calculate_bars_in_range(start_date, end_date, timeframe)
                data_pct = (len(df) / expected_bars) * 100
                
                if data_pct >= min_data_pct:
                    valid_symbols.append(symbol)
                else:
                    self.logger.warning(
                        f"Excluding {symbol}: only {data_pct:.1f}% data available"
                    )
                    
        if not valid_symbols:
            return pd.DataFrame()
            
        # Create multi-index DataFrame
        if aligned:
            # Find common timestamps
            common_index = None
            for symbol in valid_symbols:
                if common_index is None:
                    common_index = all_data[symbol].index
                else:
                    common_index = common_index.intersection(all_data[symbol].index)
                    
            # Build aligned DataFrame
            aligned_data = {}
            for symbol in valid_symbols:
                df = all_data[symbol].loc[common_index]
                for col in df.columns:
                    aligned_data[(symbol, col)] = df[col]
                    
            result = pd.DataFrame(aligned_data)
            result.columns = pd.MultiIndex.from_tuples(result.columns)
            
            self.logger.info(
                f"Created aligned universe with {len(valid_symbols)} symbols, "
                f"{len(result)} common timestamps"
            )
            
        else:
            # Concatenate with symbol as additional index level
            frames = []
            for symbol in valid_symbols:
                df = all_data[symbol].copy()
                df['symbol'] = symbol
                frames.append(df)
                
            result = pd.concat(frames)
            result = result.set_index('symbol', append=True)
            result = result.swaplevel()
            
            self.logger.info(
                f"Created universe with {len(valid_symbols)} symbols, "
                f"{len(result)} total rows"
            )
            
        return result
        
    def create_rolling_dataset(self, symbol: str, timeframe: str,
                              lookback_days: int,
                              update_existing: bool = True) -> pd.DataFrame:
        """
        [FUNCTION SUMMARY]
        Purpose: Create/update a rolling dataset that maintains N days of history
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
            - lookback_days (int): Days of history to maintain
            - update_existing (bool): Update if dataset exists
        Returns: DataFrame - Rolling dataset
        Example: df = batch.create_rolling_dataset('AAPL', '5min', lookback_days=30)
        """
        end_date = datetime.now(POLYGON_TIMEZONE)
        start_date = end_date - timedelta(days=lookback_days)
        
        # Check for existing data
        if update_existing and self.storage.has_cache(symbol, timeframe):
            # Update cache first
            self.update_cache(symbol, timeframe)
            
            # Load updated data
            df = self.storage.load_data(symbol, timeframe, start_date, end_date)
            
            # Trim to lookback period
            if not df.empty:
                df = df[df.index >= start_date]
                
                self.logger.info(
                    f"Updated rolling dataset for {symbol} {timeframe}: "
                    f"{len(df)} rows, {lookback_days} days"
                )
                
                return df
                
        # Fetch fresh data
        df = self.fetch_data(symbol, timeframe, start_date, end_date)
        
        self.logger.info(
            f"Created rolling dataset for {symbol} {timeframe}: "
            f"{len(df)} rows, {lookback_days} days"
        )
        
        return df


# Convenience functions
def fetch_data(symbol: str, timeframe: str = '1d',
              start_date: Optional[Union[str, datetime]] = None,
              end_date: Optional[Union[str, datetime]] = None,
              **kwargs) -> pd.DataFrame:
    """
    [FUNCTION SUMMARY]
    Purpose: Simple function to fetch market data
    Parameters:
        - symbol (str): Stock symbol
        - timeframe (str): Data timeframe
        - start_date: Start date (default: 30 days ago)
        - end_date: End date (default: today)
        - **kwargs: Additional options
    Returns: DataFrame - OHLCV data
    Example: df = fetch_data('AAPL', '5min')
    """
    # Default date range
    if end_date is None:
        end_date = datetime.now(POLYGON_TIMEZONE)
    if start_date is None:
        start_date = end_date - timedelta(days=30)
        
    fetcher = DataFetcher()
    return fetcher.fetch_data(symbol, timeframe, start_date, end_date, **kwargs)


def fetch_latest(symbol: str, timeframe: str = '1min', bars: int = 100) -> pd.DataFrame:
    """
    [FUNCTION SUMMARY]
    Purpose: Fetch latest bars for a symbol
    Parameters:
        - symbol (str): Stock symbol
        - timeframe (str): Data timeframe
        - bars (int): Number of recent bars
    Returns: DataFrame - Recent OHLCV data
    Example: df = fetch_latest('AAPL', '5min', bars=20)
    """
    fetcher = DataFetcher()
    return fetcher.fetch_latest_bars(symbol, timeframe, bars)


__all__ = [
    'DataFetcher',
    'BatchDataFetcher',
    'fetch_data',
    'fetch_latest'
]