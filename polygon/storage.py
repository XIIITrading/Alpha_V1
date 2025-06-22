# polygon/storage.py - Local storage and caching for the Polygon module
"""
Storage management for local caching of market data.
Uses SQLite for metadata and parquet files for OHLCV data.
"""

import os
import sqlite3
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any, Union
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from contextlib import contextmanager
import threading
import logging

from .config import get_config, POLYGON_TIMEZONE
from .exceptions import PolygonStorageError, PolygonDataError
from .utils import parse_date, parse_timeframe, format_date_for_api, normalize_ohlcv_data


class CacheMetadata:
    """
    [CLASS SUMMARY]
    Purpose: Container for cache metadata information
    Attributes:
        - symbol: Stock ticker symbol
        - timeframe: Data timeframe (e.g., '5min')
        - start_date: Start of cached data
        - end_date: End of cached data
        - last_updated: When cache was last updated
        - row_count: Number of rows cached
        - file_path: Path to parquet file
        - file_size: Size in bytes
        - checksum: Data integrity checksum
    """
    
    def __init__(self, **kwargs):
        """Initialize metadata from kwargs"""
        self.symbol = kwargs.get('symbol')
        self.timeframe = kwargs.get('timeframe')
        self.start_date = kwargs.get('start_date')
        self.end_date = kwargs.get('end_date')
        self.last_updated = kwargs.get('last_updated')
        self.row_count = kwargs.get('row_count', 0)
        self.file_path = kwargs.get('file_path')
        self.file_size = kwargs.get('file_size', 0)
        self.checksum = kwargs.get('checksum')
        self.compression = kwargs.get('compression', 'snappy')
        self.version = kwargs.get('version', '1.0')
        
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'start_date': self.start_date.isoformat() if isinstance(self.start_date, datetime) else self.start_date,
            'end_date': self.end_date.isoformat() if isinstance(self.end_date, datetime) else self.end_date,
            'last_updated': self.last_updated.isoformat() if isinstance(self.last_updated, datetime) else self.last_updated,
            'row_count': self.row_count,
            'file_path': self.file_path,
            'file_size': self.file_size,
            'checksum': self.checksum,
            'compression': self.compression,
            'version': self.version
        }


class StorageManager:
    """
    [CLASS SUMMARY]
    Purpose: Manage local storage for Polygon data
    Responsibilities:
        - SQLite database for cache metadata
        - Parquet file management for OHLCV data
        - Cache queries and updates
        - Data compression and optimization
        - Cache invalidation and cleanup
    Usage:
        storage = StorageManager()
        storage.save_data(df, 'AAPL', '5min')
        cached_df = storage.load_data('AAPL', '5min', start_date, end_date)
    """
    
    def __init__(self, config=None):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize storage manager with configuration
        Parameters:
            - config (PolygonConfig, optional): Configuration instance
        Example: storage = StorageManager()
        """
        self.config = config or get_config()
        self.logger = self.config.get_logger(__name__)
        
        # Thread lock for database operations
        self._db_lock = threading.Lock()
        
        # Initialize storage paths
        self._init_storage_paths()
        
        # Initialize database
        self._init_database()
        
    def _init_storage_paths(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Create necessary directories for storage
        Creates: cache and parquet directories if they don't exist
        """
        # Ensure directories exist
        self.config.cache_dir.mkdir(parents=True, exist_ok=True)
        self.config.parquet_dir.mkdir(parents=True, exist_ok=True)
        
        # Create subdirectories for organization
        self.symbol_dir = self.config.parquet_dir / 'symbols'
        self.symbol_dir.mkdir(exist_ok=True)
        
        self.logger.info(f"Storage initialized at {self.config.data_dir}")
        
    def _init_database(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize SQLite database for cache metadata
        Creates: Database tables if they don't exist
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Create cache metadata table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    last_updated TEXT NOT NULL,
                    row_count INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER NOT NULL,
                    checksum TEXT,
                    compression TEXT DEFAULT 'snappy',
                    version TEXT DEFAULT '1.0',
                    UNIQUE(symbol, timeframe)
                )
            ''')
            
            # Create index for faster queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_symbol_timeframe 
                ON cache_metadata(symbol, timeframe)
            ''')
            
            # Create cache access log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cache_access_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    timeframe TEXT NOT NULL,
                    access_time TEXT NOT NULL,
                    access_type TEXT NOT NULL,
                    rows_accessed INTEGER
                )
            ''')
            
            # Create cleanup log table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS cleanup_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    cleanup_time TEXT NOT NULL,
                    files_removed INTEGER,
                    space_freed_mb REAL,
                    reason TEXT
                )
            ''')
            
            conn.commit()
            
        self.logger.debug("Database initialized successfully")
        
    @contextmanager
    def _get_db_connection(self):
        """
        [FUNCTION SUMMARY]
        Purpose: Get thread-safe database connection
        Yields: sqlite3.Connection - Database connection
        Note: Uses context manager for automatic cleanup
        """
        conn = None
        try:
            with self._db_lock:
                conn = sqlite3.connect(
                    str(self.config.cache_db_path),
                    check_same_thread=False
                )
                conn.row_factory = sqlite3.Row
                yield conn
        except sqlite3.Error as e:
            raise PolygonStorageError(
                f"Database error: {str(e)}",
                operation='connect',
                path=str(self.config.cache_db_path)
            )
        finally:
            if conn:
                conn.close()
                
    def _get_cache_filepath(self, symbol: str, timeframe: str) -> Path:
        """
        [FUNCTION SUMMARY]
        Purpose: Generate consistent file path for cached data
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
        Returns: Path - Full path to parquet file
        Example: path = _get_cache_filepath('AAPL', '5min')
        """
        # Create symbol-specific directory
        symbol_path = self.symbol_dir / symbol.upper()
        symbol_path.mkdir(exist_ok=True)
        
        # Generate filename
        filename = f"{symbol.upper()}_{timeframe}.parquet"
        return symbol_path / filename
        
    def _calculate_checksum(self, df: pd.DataFrame) -> str:
        """
        [FUNCTION SUMMARY]
        Purpose: Calculate checksum for data integrity
        Parameters:
            - df (DataFrame): Data to checksum
        Returns: str - MD5 checksum
        """
        # Convert DataFrame to bytes for hashing
        df_bytes = pd.util.hash_pandas_object(df).values.tobytes()
        return hashlib.md5(df_bytes).hexdigest()
        
    def save_data(self, df: pd.DataFrame, symbol: str, timeframe: str,
                  update_metadata: bool = True) -> CacheMetadata:
        """
        [FUNCTION SUMMARY]
        Purpose: Save OHLCV data to local cache
        Parameters:
            - df (DataFrame): OHLCV data to save
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
            - update_metadata (bool): Update database metadata
        Returns: CacheMetadata - Metadata about saved cache
        Example: metadata = storage.save_data(df, 'AAPL', '5min')
        """
        if df.empty:
            raise PolygonDataError("Cannot save empty DataFrame")
            
        # Normalize symbol and timeframe
        symbol = symbol.upper()
        
        try:
            # Get file path
            file_path = self._get_cache_filepath(symbol, timeframe)
            
            # Ensure DataFrame is sorted by time
            df_sorted = df.sort_index()
            
            # Check if cache exists and merge if needed
            if file_path.exists() and self.config.cache_enabled:
                existing_df = self._read_parquet_file(file_path)
                if not existing_df.empty:
                    # Merge with existing data
                    df_sorted = self._merge_dataframes(existing_df, df_sorted)
                    self.logger.debug(f"Merged with existing cache for {symbol} {timeframe}")
            
            # Calculate metadata
            start_date = df_sorted.index.min()
            end_date = df_sorted.index.max()
            row_count = len(df_sorted)
            checksum = self._calculate_checksum(df_sorted)
            
            # Save to parquet
            compression = 'snappy' if self.config.use_compression else None
            pq.write_table(
                pa.Table.from_pandas(df_sorted, preserve_index=True),
                file_path,
                compression=compression
            )
            
            # Get file size
            file_size = file_path.stat().st_size
            
            # Create metadata object
            metadata = CacheMetadata(
                symbol=symbol,
                timeframe=timeframe,
                start_date=start_date,
                end_date=end_date,
                last_updated=datetime.now(POLYGON_TIMEZONE),
                row_count=row_count,
                file_path=str(file_path),
                file_size=file_size,
                checksum=checksum,
                compression=compression or 'none'
            )
            
            # Update database if requested
            if update_metadata:
                self._update_cache_metadata(metadata)
                
            # Log access
            self._log_cache_access(symbol, timeframe, 'write', row_count)
            
            self.logger.info(
                f"Saved {row_count} rows for {symbol} {timeframe} "
                f"({file_size / 1024 / 1024:.2f} MB)"
            )
            
            return metadata
            
        except Exception as e:
            raise PolygonStorageError(
                f"Failed to save data: {str(e)}",
                operation='write',
                path=str(file_path) if 'file_path' in locals() else None
            )
            
    def load_data(self, symbol: str, timeframe: str,
                  start_date: Optional[Union[str, datetime]] = None,
                  end_date: Optional[Union[str, datetime]] = None) -> Optional[pd.DataFrame]:
        """
        [FUNCTION SUMMARY]
        Purpose: Load cached data for symbol and timeframe
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
            - start_date (datetime, optional): Filter start date
            - end_date (datetime, optional): Filter end date
        Returns: DataFrame or None - Cached data if available
        Example: df = storage.load_data('AAPL', '5min', start_date, end_date)
        """
        if not self.config.cache_enabled:
            return None
            
        symbol = symbol.upper()
        
        try:
            # Check if cache exists
            metadata = self.get_cache_metadata(symbol, timeframe)
            if not metadata:
                return None
                
            # Load parquet file
            file_path = Path(metadata.file_path)
            if not file_path.exists():
                self.logger.warning(f"Cache file missing: {file_path}")
                self._remove_cache_metadata(symbol, timeframe)
                return None
                
            # Read data
            df = self._read_parquet_file(file_path)
            
            if df.empty:
                return None
                
            # Apply date filters if provided
            if start_date or end_date:
                df = self._filter_by_date_range(df, start_date, end_date)
                
            # Log access
            self._log_cache_access(symbol, timeframe, 'read', len(df))
            
            self.logger.debug(
                f"Loaded {len(df)} rows from cache for {symbol} {timeframe}"
            )
            
            return df
            
        except Exception as e:
            self.logger.error(f"Failed to load cache: {str(e)}")
            return None
            
    def _read_parquet_file(self, file_path: Path) -> pd.DataFrame:
        """
        [FUNCTION SUMMARY]
        Purpose: Read parquet file with error handling
        Parameters:
            - file_path (Path): Path to parquet file
        Returns: DataFrame - Loaded data
        """
        try:
            df = pd.read_parquet(file_path)
            
            # Ensure datetime index
            if not isinstance(df.index, pd.DatetimeIndex):
                if 'datetime' in df.columns:
                    df = df.set_index('datetime')
                elif 'timestamp' in df.columns:
                    df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
                    df = df.set_index('datetime')
                    
            # Ensure UTC timezone
            if df.index.tz is None:
                df.index = df.index.tz_localize(POLYGON_TIMEZONE)
            elif df.index.tz != POLYGON_TIMEZONE:
                df.index = df.index.tz_convert(POLYGON_TIMEZONE)
                
            return df
            
        except Exception as e:
            raise PolygonStorageError(
                f"Failed to read parquet file: {str(e)}",
                operation='read',
                path=str(file_path)
            )
            
    def _merge_dataframes(self, existing_df: pd.DataFrame, 
                         new_df: pd.DataFrame) -> pd.DataFrame:
        """
        [FUNCTION SUMMARY]
        Purpose: Merge existing and new data, handling overlaps
        Parameters:
            - existing_df (DataFrame): Existing cached data
            - new_df (DataFrame): New data to merge
        Returns: DataFrame - Merged data
        """
        # Combine and remove duplicates (keep latest)
        combined = pd.concat([existing_df, new_df])
        
        # Remove duplicates, keeping the last (most recent) entry
        combined = combined[~combined.index.duplicated(keep='last')]
        
        # Sort by index
        combined = combined.sort_index()
        
        return combined
        
    def _filter_by_date_range(self, df: pd.DataFrame,
                             start_date: Optional[Union[str, datetime]],
                             end_date: Optional[Union[str, datetime]]) -> pd.DataFrame:
        """
        [FUNCTION SUMMARY]
        Purpose: Filter DataFrame by date range
        Parameters:
            - df (DataFrame): Data to filter
            - start_date: Start date (inclusive)
            - end_date: End date (inclusive)
        Returns: DataFrame - Filtered data
        """
        if start_date:
            start_dt = parse_date(start_date)
            df = df[df.index >= start_dt]
            
        if end_date:
            end_dt = parse_date(end_date)
            # Make end date inclusive by adding 1 day
            end_dt = end_dt + timedelta(days=1)
            df = df[df.index < end_dt]
            
        return df
        
    def get_cache_metadata(self, symbol: str, timeframe: str) -> Optional[CacheMetadata]:
        """
        [FUNCTION SUMMARY]
        Purpose: Get cache metadata from database
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
        Returns: CacheMetadata or None - Metadata if cache exists
        Example: metadata = storage.get_cache_metadata('AAPL', '5min')
        """
        symbol = symbol.upper()
        
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM cache_metadata 
                WHERE symbol = ? AND timeframe = ?
            ''', (symbol, timeframe))
            
            row = cursor.fetchone()
            
            if row:
                return CacheMetadata(
                    symbol=row['symbol'],
                    timeframe=row['timeframe'],
                    start_date=parse_date(row['start_date']),
                    end_date=parse_date(row['end_date']),
                    last_updated=parse_date(row['last_updated']),
                    row_count=row['row_count'],
                    file_path=row['file_path'],
                    file_size=row['file_size'],
                    checksum=row['checksum'],
                    compression=row['compression'],
                    version=row['version']
                )
                
        return None
        
    def _update_cache_metadata(self, metadata: CacheMetadata):
        """
        [FUNCTION SUMMARY]
        Purpose: Update or insert cache metadata in database
        Parameters:
            - metadata (CacheMetadata): Metadata to save
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Use REPLACE to update or insert
            cursor.execute('''
                REPLACE INTO cache_metadata (
                    symbol, timeframe, start_date, end_date, last_updated,
                    row_count, file_path, file_size, checksum, compression, version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                metadata.symbol,
                metadata.timeframe,
                metadata.start_date.isoformat() if isinstance(metadata.start_date, datetime) else metadata.start_date,
                metadata.end_date.isoformat() if isinstance(metadata.end_date, datetime) else metadata.end_date,
                metadata.last_updated.isoformat() if isinstance(metadata.last_updated, datetime) else metadata.last_updated,
                metadata.row_count,
                metadata.file_path,
                metadata.file_size,
                metadata.checksum,
                metadata.compression,
                metadata.version
            ))
            
            conn.commit()
            
    def _remove_cache_metadata(self, symbol: str, timeframe: str):
        """
        [FUNCTION SUMMARY]
        Purpose: Remove cache metadata from database
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM cache_metadata 
                WHERE symbol = ? AND timeframe = ?
            ''', (symbol.upper(), timeframe))
            conn.commit()
            
    def _log_cache_access(self, symbol: str, timeframe: str, 
                         access_type: str, rows_accessed: int):
        """
        [FUNCTION SUMMARY]
        Purpose: Log cache access for analytics
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
            - access_type (str): 'read' or 'write'
            - rows_accessed (int): Number of rows
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO cache_access_log 
                (symbol, timeframe, access_time, access_type, rows_accessed)
                VALUES (?, ?, ?, ?, ?)
            ''', (
                symbol.upper(),
                timeframe,
                datetime.now(POLYGON_TIMEZONE).isoformat(),
                access_type,
                rows_accessed
            ))
            conn.commit()
            
    def has_cache(self, symbol: str, timeframe: str,
                  start_date: Optional[Union[str, datetime]] = None,
                  end_date: Optional[Union[str, datetime]] = None) -> bool:
        """
        [FUNCTION SUMMARY]
        Purpose: Check if cache exists for given parameters
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
            - start_date (datetime, optional): Required start date
            - end_date (datetime, optional): Required end date
        Returns: bool - True if cache covers requested range
        Example: if storage.has_cache('AAPL', '5min', start, end): ...
        """
        metadata = self.get_cache_metadata(symbol, timeframe)
        
        if not metadata:
            return False
            
        # Check if file exists
        if not Path(metadata.file_path).exists():
            return False
            
        # If no date range specified, cache exists
        if not start_date and not end_date:
            return True
            
        # Check if cache covers requested range
        if start_date:
            start_dt = parse_date(start_date)
            if metadata.start_date > start_dt:
                return False
                
        if end_date:
            end_dt = parse_date(end_date)
            if metadata.end_date < end_dt:
                return False
                
        return True
        
    def get_missing_ranges(self, symbol: str, timeframe: str,
                          start_date: Union[str, datetime],
                          end_date: Union[str, datetime]) -> List[Tuple[datetime, datetime]]:
        """
        [FUNCTION SUMMARY]
        Purpose: Identify date ranges not in cache
        Parameters:
            - symbol (str): Stock symbol
            - timeframe (str): Data timeframe
            - start_date: Requested start date
            - end_date: Requested end date
        Returns: list - List of (start, end) tuples for missing data
        Example: missing = storage.get_missing_ranges('AAPL', '5min', start, end)
        """
        start_dt = parse_date(start_date)
        end_dt = parse_date(end_date)
        
        # Get existing cache metadata
        metadata = self.get_cache_metadata(symbol, timeframe)
        
        # If no cache, entire range is missing
        if not metadata or not Path(metadata.file_path).exists():
            return [(start_dt, end_dt)]
            
        missing_ranges = []
        
        # Check for missing data before cache start
        if start_dt < metadata.start_date:
            missing_ranges.append((start_dt, metadata.start_date - timedelta(seconds=1)))
            
        # Check for missing data after cache end
        if end_dt > metadata.end_date:
            missing_ranges.append((metadata.end_date + timedelta(seconds=1), end_dt))
            
        return missing_ranges
        
    def clear_cache(self, symbol: Optional[str] = None,
                   timeframe: Optional[str] = None,
                   older_than_days: Optional[int] = None) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Clear cache based on criteria
        Parameters:
            - symbol (str, optional): Clear specific symbol
            - timeframe (str, optional): Clear specific timeframe
            - older_than_days (int, optional): Clear data older than N days
        Returns: dict - Cleanup statistics
        Example: stats = storage.clear_cache(older_than_days=30)
        """
        stats = {
            'files_removed': 0,
            'space_freed_mb': 0,
            'entries_removed': 0
        }
        
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Build query
            query = "SELECT * FROM cache_metadata WHERE 1=1"
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol.upper())
                
            if timeframe:
                query += " AND timeframe = ?"
                params.append(timeframe)
                
            if older_than_days:
                cutoff_date = datetime.now(POLYGON_TIMEZONE) - timedelta(days=older_than_days)
                query += " AND last_updated < ?"
                params.append(cutoff_date.isoformat())
                
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            # Remove files and metadata
            for row in rows:
                file_path = Path(row['file_path'])
                if file_path.exists():
                    file_size = file_path.stat().st_size
                    file_path.unlink()
                    stats['files_removed'] += 1
                    stats['space_freed_mb'] += file_size / 1024 / 1024
                    
                # Remove metadata
                cursor.execute(
                    "DELETE FROM cache_metadata WHERE id = ?",
                    (row['id'],)
                )
                stats['entries_removed'] += 1
                
            conn.commit()
            
        # Log cleanup
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO cleanup_log 
                (cleanup_time, files_removed, space_freed_mb, reason)
                VALUES (?, ?, ?, ?)
            ''', (
                datetime.now(POLYGON_TIMEZONE).isoformat(),
                stats['files_removed'],
                stats['space_freed_mb'],
                f"Manual cleanup: symbol={symbol}, timeframe={timeframe}, older_than={older_than_days}"
            ))
            conn.commit()
            
        self.logger.info(
            f"Cache cleanup completed: removed {stats['files_removed']} files, "
            f"freed {stats['space_freed_mb']:.2f} MB"
        )
        
        return stats
        
    def get_cache_statistics(self) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Get overall cache statistics
        Returns: dict - Cache usage statistics
        Example: stats = storage.get_cache_statistics()
        """
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            
            # Total cache entries
            cursor.execute("SELECT COUNT(*) as count FROM cache_metadata")
            total_entries = cursor.fetchone()['count']
            
            # Total size
            cursor.execute("SELECT SUM(file_size) as total_size FROM cache_metadata")
            total_size = cursor.fetchone()['total_size'] or 0
            
            # By symbol
            cursor.execute('''
                SELECT symbol, COUNT(*) as count, SUM(file_size) as size
                FROM cache_metadata
                GROUP BY symbol
                ORDER BY size DESC
                LIMIT 10
            ''')
            top_symbols = [dict(row) for row in cursor.fetchall()]
            
            # By timeframe
            cursor.execute('''
                SELECT timeframe, COUNT(*) as count, SUM(file_size) as size
                FROM cache_metadata
                GROUP BY timeframe
                ORDER BY count DESC
            ''')
            by_timeframe = [dict(row) for row in cursor.fetchall()]
            
            # Recent access
            cursor.execute('''
                SELECT symbol, timeframe, COUNT(*) as access_count
                FROM cache_access_log
                WHERE access_time > datetime('now', '-7 days')
                GROUP BY symbol, timeframe
                ORDER BY access_count DESC
                LIMIT 10
            ''')
            recent_access = [dict(row) for row in cursor.fetchall()]
            
        return {
            'total_entries': total_entries,
            'total_size_mb': total_size / 1024 / 1024,
            'top_symbols': top_symbols,
            'by_timeframe': by_timeframe,
            'recent_access': recent_access,
            'cache_directory': str(self.config.parquet_dir),
            'database_path': str(self.config.cache_db_path)
        }
        
    def optimize_cache(self) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Optimize cache by removing duplicates and recompressing
        Returns: dict - Optimization statistics
        Example: stats = storage.optimize_cache()
        """
        stats = {
            'files_optimized': 0,
            'space_saved_mb': 0,
            'errors': []
        }
        
        with self._get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM cache_metadata")
            
            for row in cursor.fetchall():
                try:
                    file_path = Path(row['file_path'])
                    if not file_path.exists():
                        continue
                        
                    # Read current file
                    original_size = file_path.stat().st_size
                    df = self._read_parquet_file(file_path)
                    
                    # Remove any duplicates
                    df = df[~df.index.duplicated(keep='last')]
                    
                    # Rewrite with optimal compression
                    pq.write_table(
                        pa.Table.from_pandas(df, preserve_index=True),
                        file_path,
                        compression='snappy'
                    )
                    
                    # Calculate space saved
                    new_size = file_path.stat().st_size
                    if new_size < original_size:
                        stats['files_optimized'] += 1
                        stats['space_saved_mb'] += (original_size - new_size) / 1024 / 1024
                        
                except Exception as e:
                    stats['errors'].append(f"{row['symbol']}_{row['timeframe']}: {str(e)}")
                    
        self.logger.info(
            f"Cache optimization completed: {stats['files_optimized']} files, "
            f"saved {stats['space_saved_mb']:.2f} MB"
        )
        
        return stats


# Public convenience functions
def get_storage_manager() -> StorageManager:
    """
    [FUNCTION SUMMARY]
    Purpose: Get or create singleton storage manager
    Returns: StorageManager - Storage instance
    Example: storage = get_storage_manager()
    """
    if not hasattr(get_storage_manager, '_instance'):
        get_storage_manager._instance = StorageManager()
    return get_storage_manager._instance


__all__ = [
    'StorageManager',
    'CacheMetadata',
    'get_storage_manager'
]