# polygon/core.py - Core API client for Polygon.io
"""
Core API client module for Polygon.io integration.
Handles HTTP sessions, request execution, and response parsing.
"""

import asyncio
import json
import time
from typing import Dict, Any, Optional, Union, List
from urllib.parse import urljoin, urlencode
import aiohttp
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .config import get_config, PolygonConfig
from .exceptions import (
    PolygonAPIError,
    PolygonAuthenticationError,
    PolygonRateLimitError,
    PolygonNetworkError,
    PolygonDataError,
    is_retryable_error,
    get_retry_delay
)


class PolygonSession:
    """
    [CLASS SUMMARY]
    Purpose: Manage HTTP session for Polygon API requests
    Responsibilities:
        - Session lifecycle management
        - Request/response handling
        - Error handling and retries
        - Rate limit tracking
    Usage:
        session = PolygonSession()
        response = session.request('GET', endpoint, params)
    """
    
    def __init__(self, config: Optional[PolygonConfig] = None):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize session with configuration
        Parameters:
            - config (PolygonConfig, optional): Configuration instance
        Example: session = PolygonSession()
        """
        self.config = config or get_config()
        self.logger = self.config.get_logger(__name__)
        
        # Session objects (created on demand)
        self._sync_session: Optional[requests.Session] = None
        self._async_session: Optional[aiohttp.ClientSession] = None
        
        # Request tracking for rate limiting
        self.request_timestamps: List[float] = []
        self.daily_request_count = 0
        self.last_request_day = time.strftime('%Y-%m-%d')
        
    @property
    def sync_session(self) -> requests.Session:
        """
        [FUNCTION SUMMARY]
        Purpose: Get or create synchronous session with retry configuration
        Returns: requests.Session - Configured session instance
        Note: Lazy initialization for efficiency
        """
        if self._sync_session is None:
            # Create new session
            self._sync_session = requests.Session()
            
            # Configure retry strategy
            retry_strategy = Retry(
                total=self.config.max_retries,
                backoff_factor=1,
                status_forcelist=[408, 429, 500, 502, 503, 504],
                allowed_methods=["GET", "POST", "PUT", "DELETE"]
            )
            
            # Mount adapter with retry logic
            adapter = HTTPAdapter(max_retries=retry_strategy)
            self._sync_session.mount("http://", adapter)
            self._sync_session.mount("https://", adapter)
            
            # Set default headers
            self._sync_session.headers.update({
                'User-Agent': 'Polygon-Python-Client/1.0',
                'Accept': 'application/json',
                'Accept-Encoding': 'gzip, deflate'
            })
            
        return self._sync_session
    
    async def get_async_session(self) -> aiohttp.ClientSession:
        """
        [FUNCTION SUMMARY]
        Purpose: Get or create asynchronous session
        Returns: aiohttp.ClientSession - Configured async session
        Note: Must be called within async context
        """
        if self._async_session is None or self._async_session.closed:
            # Configure timeout
            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
            
            # Create session with configuration
            self._async_session = aiohttp.ClientSession(
                timeout=timeout,
                headers={
                    'User-Agent': 'Polygon-Python-Client/1.0',
                    'Accept': 'application/json',
                    'Accept-Encoding': 'gzip, deflate'
                }
            )
            
        return self._async_session
    
    def _check_rate_limits(self) -> None:
        """
        [FUNCTION SUMMARY]
        Purpose: Check if request would exceed rate limits
        Raises: PolygonRateLimitError if limit would be exceeded
        Note: Tracks both per-minute and daily limits
        """
        current_time = time.time()
        current_day = time.strftime('%Y-%m-%d')
        
        # Reset daily counter if new day
        if current_day != self.last_request_day:
            self.daily_request_count = 0
            self.last_request_day = current_day
        
        # Remove timestamps older than 1 minute
        self.request_timestamps = [
            ts for ts in self.request_timestamps 
            if current_time - ts < 60
        ]
        
        # Check per-minute limit
        if len(self.request_timestamps) >= self.config.requests_per_minute:
            wait_time = 60 - (current_time - self.request_timestamps[0])
            raise PolygonRateLimitError(
                f"Rate limit exceeded: {self.config.requests_per_minute} requests per minute",
                retry_after=int(wait_time),
                limit_type='minute'
            )
        
        # Check daily limit
        if self.daily_request_count >= self.config.requests_per_day:
            raise PolygonRateLimitError(
                f"Daily rate limit exceeded: {self.config.requests_per_day} requests per day",
                retry_after=3600,  # Wait an hour
                limit_type='day'
            )
    
    def _record_request(self) -> None:
        """Record timestamp for rate limiting"""
        current_time = time.time()
        self.request_timestamps.append(current_time)
        self.daily_request_count += 1
    
    def _prepare_request(self, method: str, endpoint: str, 
                        params: Optional[Dict[str, Any]] = None,
                        data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Prepare request with authentication and parameters
        Parameters:
            - method (str): HTTP method
            - endpoint (str): API endpoint path
            - params (dict, optional): Query parameters
            - data (dict, optional): Request body data
        Returns: dict - Request configuration
        Example: config = _prepare_request('GET', '/v2/aggs/ticker/AAPL/range/1/day/2023-01-01/2023-01-31')
        """
        # Ensure params dict exists
        if params is None:
            params = {}
        
        # Add API key to params
        params['apiKey'] = self.config.api_key
        
        # Build full URL
        if endpoint.startswith('http'):
            url = endpoint
        else:
            url = urljoin(self.config.base_url, endpoint.lstrip('/'))
        
        # Log request details (hide API key)
        safe_params = {k: v for k, v in params.items() if k != 'apiKey'}
        self.logger.debug(f"{method} {url} with params: {safe_params}")
        
        return {
            'method': method,
            'url': url,
            'params': params,
            'data': data,
            'timeout': self.config.request_timeout
        }
    
    def _handle_response(self, response: Union[requests.Response, dict], 
                        endpoint: str) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Parse and validate API response
        Parameters:
            - response: Raw response object
            - endpoint (str): Endpoint for error context
        Returns: dict - Parsed response data
        Raises: PolygonAPIError for various error conditions
        """
        # Handle sync response
        if isinstance(response, requests.Response):
            status_code = response.status_code
            
            # Check for successful response
            if status_code == 200:
                try:
                    data = response.json()
                    self.logger.debug(f"Successful response from {endpoint}")
                    return data
                except json.JSONDecodeError as e:
                    raise PolygonDataError(
                        f"Invalid JSON response from {endpoint}",
                        data_type='json',
                        response_text=response.text[:500]
                    )
            
            # Handle error responses
            self._handle_error_response(status_code, response.text, endpoint)
        
        # Handle async response (already parsed dict)
        elif isinstance(response, dict):
            if 'error' in response:
                raise PolygonAPIError(
                    response.get('error', 'Unknown error'),
                    response_body=json.dumps(response)
                )
            return response
        
        else:
            raise PolygonDataError(f"Unexpected response type: {type(response)}")
    
    def _handle_error_response(self, status_code: int, response_text: str, 
                              endpoint: str) -> None:
        """
        [FUNCTION SUMMARY]
        Purpose: Handle HTTP error responses with specific exceptions
        Parameters:
            - status_code (int): HTTP status code
            - response_text (str): Raw response body
            - endpoint (str): API endpoint for context
        Raises: Specific PolygonError subclass based on status code
        """
        # Try to parse error message from response
        try:
            error_data = json.loads(response_text)
            error_message = error_data.get('message', error_data.get('error', 'Unknown error'))
        except:
            error_message = f"HTTP {status_code} error"
        
        # Map status codes to specific exceptions
        if status_code == 401:
            raise PolygonAuthenticationError(
                error_message,
                endpoint=endpoint,
                response_body=response_text
            )
        
        elif status_code == 429:
            # Try to extract retry-after header
            retry_after = None
            if 'retry-after' in response_text.lower():
                try:
                    retry_match = re.search(r'retry.after["\s:]+(\d+)', response_text, re.I)
                    if retry_match:
                        retry_after = int(retry_match.group(1))
                except:
                    pass
            
            raise PolygonRateLimitError(
                error_message,
                retry_after=retry_after,
                endpoint=endpoint
            )
        
        elif status_code == 404:
            raise PolygonAPIError(
                f"Endpoint not found: {endpoint}",
                status_code=status_code,
                response_body=response_text
            )
        
        elif 400 <= status_code < 500:
            raise PolygonAPIError(
                f"Client error: {error_message}",
                status_code=status_code,
                response_body=response_text,
                endpoint=endpoint
            )
        
        elif 500 <= status_code < 600:
            raise PolygonAPIError(
                f"Server error: {error_message}",
                status_code=status_code,
                response_body=response_text,
                endpoint=endpoint
            )
        
        else:
            raise PolygonAPIError(
                f"Unexpected status code {status_code}: {error_message}",
                status_code=status_code,
                response_body=response_text,
                endpoint=endpoint
            )
    
    def request(self, method: str, endpoint: str, 
                params: Optional[Dict[str, Any]] = None,
                data: Optional[Dict[str, Any]] = None,
                retry: bool = True) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Execute synchronous HTTP request with retry logic
        Parameters:
            - method (str): HTTP method (GET, POST, etc.)
            - endpoint (str): API endpoint path
            - params (dict, optional): Query parameters
            - data (dict, optional): Request body
            - retry (bool): Enable automatic retry
        Returns: dict - Parsed response data
        Example: data = session.request('GET', '/v2/aggs/ticker/AAPL/range/1/day/2023-01-01/2023-01-31')
        """
        # Check rate limits before request
        self._check_rate_limits()
        
        # Prepare request configuration
        request_config = self._prepare_request(method, endpoint, params, data)
        
        # Execute request with retry logic
        last_error = None
        for attempt in range(self.config.max_retries if retry else 1):
            try:
                # Record request for rate limiting
                self._record_request()
                
                # Execute request
                if method.upper() == 'GET':
                    response = self.sync_session.get(
                        request_config['url'],
                        params=request_config['params'],
                        timeout=request_config['timeout']
                    )
                elif method.upper() == 'POST':
                    response = self.sync_session.post(
                        request_config['url'],
                        params=request_config['params'],
                        json=request_config['data'],
                        timeout=request_config['timeout']
                    )
                else:
                    response = self.sync_session.request(
                        method,
                        request_config['url'],
                        params=request_config['params'],
                        json=request_config['data'],
                        timeout=request_config['timeout']
                    )
                
                # Handle response
                return self._handle_response(response, endpoint)
                
            except (requests.ConnectionError, requests.Timeout) as e:
                last_error = PolygonNetworkError(
                    f"Network error: {str(e)}",
                    url=request_config['url'],
                    timeout=request_config['timeout']
                )
                
            except Exception as e:
                # Check if this is already a Polygon exception
                if isinstance(e, PolygonAPIError):
                    last_error = e
                else:
                    last_error = PolygonNetworkError(f"Unexpected error: {str(e)}")
            
            # Check if we should retry
            if last_error and retry and is_retryable_error(last_error) and attempt < self.config.max_retries - 1:
                delay = get_retry_delay(last_error, attempt + 1)
                self.logger.warning(
                    f"Request failed (attempt {attempt + 1}/{self.config.max_retries}), "
                    f"retrying in {delay} seconds: {last_error}"
                )
                time.sleep(delay)
            elif last_error:
                raise last_error
        
        # If we get here, all retries failed
        if last_error:
            raise last_error
    
    async def request_async(self, method: str, endpoint: str,
                           params: Optional[Dict[str, Any]] = None,
                           data: Optional[Dict[str, Any]] = None,
                           retry: bool = True) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Execute asynchronous HTTP request with retry logic
        Parameters:
            - method (str): HTTP method
            - endpoint (str): API endpoint path
            - params (dict, optional): Query parameters
            - data (dict, optional): Request body
            - retry (bool): Enable automatic retry
        Returns: dict - Parsed response data
        Example: data = await session.request_async('GET', '/v2/aggs/ticker/AAPL/range/1/day/2023-01-01/2023-01-31')
        """
        # Check rate limits
        self._check_rate_limits()
        
        # Prepare request
        request_config = self._prepare_request(method, endpoint, params, data)
        
        # Get async session
        session = await self.get_async_session()
        
        # Execute with retry logic
        last_error = None
        for attempt in range(self.config.max_retries if retry else 1):
            try:
                # Record request
                self._record_request()
                
                # Execute async request
                async with session.request(
                    method,
                    request_config['url'],
                    params=request_config['params'],
                    json=request_config['data']
                ) as response:
                    # Check status
                    if response.status == 200:
                        data = await response.json()
                        return data
                    
                    # Handle error
                    response_text = await response.text()
                    self._handle_error_response(
                        response.status,
                        response_text,
                        endpoint
                    )
                    
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_error = PolygonNetworkError(
                    f"Async network error: {str(e)}",
                    url=request_config['url']
                )
                
            except Exception as e:
                if isinstance(e, PolygonAPIError):
                    last_error = e
                else:
                    last_error = PolygonNetworkError(f"Unexpected async error: {str(e)}")
            
            # Retry logic
            if last_error and retry and is_retryable_error(last_error) and attempt < self.config.max_retries - 1:
                delay = get_retry_delay(last_error, attempt + 1)
                self.logger.warning(
                    f"Async request failed (attempt {attempt + 1}/{self.config.max_retries}), "
                    f"retrying in {delay} seconds: {last_error}"
                )
                await asyncio.sleep(delay)
            elif last_error:
                raise last_error
        
        if last_error:
            raise last_error
    
    def close(self) -> None:
        """
        [FUNCTION SUMMARY]
        Purpose: Close all sessions and clean up resources
        Note: Should be called when done with the session
        """
        if self._sync_session:
            self._sync_session.close()
            self._sync_session = None
            
        # Note: Async session should be closed in async context
        if self._async_session and not self._async_session.closed:
            self.logger.warning("Async session not properly closed")
    
    async def close_async(self) -> None:
        """
        [FUNCTION SUMMARY]
        Purpose: Close async session properly
        Note: Must be called in async context
        """
        if self._async_session and not self._async_session.closed:
            await self._async_session.close()
            self._async_session = None
        
        # Also close sync session
        self.close()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close sessions"""
        self.close()
    
    async def __aenter__(self):
        """Async context manager entry"""
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close_async()


class PolygonClient:
    """
    [CLASS SUMMARY]
    Purpose: High-level client for Polygon API operations
    Responsibilities:
        - Endpoint-specific methods
        - Response parsing and validation
        - Pagination handling
        - Data normalization
    Usage:
        client = PolygonClient()
        bars = client.get_aggregates('AAPL', '1', 'minute', '2023-01-01', '2023-01-02')
    """
    
    def __init__(self, config: Optional[PolygonConfig] = None):
        """
        [FUNCTION SUMMARY]
        Purpose: Initialize client with configuration
        Parameters:
            - config (PolygonConfig, optional): Configuration instance
        Example: client = PolygonClient()
        """
        self.config = config or get_config()
        self.session = PolygonSession(self.config)
        self.logger = self.config.get_logger(__name__)
    
    def get_aggregates(self, ticker: str, multiplier: int, timespan: str,
                      from_date: str, to_date: str,
                      adjusted: bool = True, sort: str = 'asc',
                      limit: int = 50000) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Get aggregate bars for a ticker
        Parameters:
            - ticker (str): Stock symbol
            - multiplier (int): Size of time window
            - timespan (str): Time unit (minute, hour, day, etc.)
            - from_date (str): Start date (YYYY-MM-DD)
            - to_date (str): End date (YYYY-MM-DD)
            - adjusted (bool): Include adjusted prices
            - sort (str): Sort order (asc/desc)
            - limit (int): Maximum results
        Returns: dict - API response with results
        Example: data = client.get_aggregates('AAPL', 1, 'day', '2023-01-01', '2023-01-31')
        """
        # Build endpoint
        endpoint = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}"
        
        # Build parameters
        params = {
            'adjusted': str(adjusted).lower(),
            'sort': sort,
            'limit': limit
        }
        
        # Execute request
        response = self.session.request('GET', endpoint, params=params)
        
        # Validate response structure
        if 'results' not in response:
            self.logger.warning(f"No results in aggregate response for {ticker}")
            response['results'] = []
        
        return response
    
    def get_ticker_details(self, ticker: str, date: Optional[str] = None) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Get detailed information about a ticker
        Parameters:
            - ticker (str): Stock symbol
            - date (str, optional): As-of date for historical details
        Returns: dict - Ticker information
        Example: details = client.get_ticker_details('AAPL')
        """
        # Build endpoint
        endpoint = f"/v3/reference/tickers/{ticker}"
        
        # Add date parameter if provided
        params = {}
        if date:
            params['date'] = date
        
        # Execute request
        response = self.session.request('GET', endpoint, params=params)
        
        return response
    
    def get_market_status(self) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Get current market status
        Returns: dict - Market status information
        Example: status = client.get_market_status()
        """
        endpoint = "/v1/marketstatus/now"
        return self.session.request('GET', endpoint)
    
    def search_tickers(self, search: str, active: bool = True,
                      limit: int = 100) -> Dict[str, Any]:
        """
        [FUNCTION SUMMARY]
        Purpose: Search for tickers by name or symbol
        Parameters:
            - search (str): Search query
            - active (bool): Only active tickers
            - limit (int): Maximum results
        Returns: dict - Search results
        Example: results = client.search_tickers('Apple')
        """
        endpoint = "/v3/reference/tickers"
        
        params = {
            'search': search,
            'active': str(active).lower(),
            'limit': limit,
            'order': 'asc',
            'sort': 'ticker'
        }
        
        return self.session.request('GET', endpoint, params=params)
    
    def validate_ticker(self, ticker: str) -> bool:
        """
        [FUNCTION SUMMARY]
        Purpose: Check if a ticker symbol is valid
        Parameters:
            - ticker (str): Stock symbol to validate
        Returns: bool - True if valid
        Example: is_valid = client.validate_ticker('AAPL')
        """
        try:
            response = self.get_ticker_details(ticker)
            return 'results' in response or 'status' in response
        except PolygonAPIError as e:
            if e.status_code == 404:
                return False
            raise
    
    def close(self) -> None:
        """Close the underlying session"""
        self.session.close()
    
    async def close_async(self) -> None:
        """Close async session"""
        await self.session.close_async()
    
    def __enter__(self):
        """Context manager support"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up on exit"""
        self.close()


# Import required for status code parsing
import re