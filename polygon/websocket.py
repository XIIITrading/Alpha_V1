# polygon/websocket.py
import asyncio
import websockets
import json
from typing import Dict, List, Callable, Optional, Set
from datetime import datetime
import logging
from collections import defaultdict

from .config import get_config, POLYGON_TIMEZONE
from .exceptions import PolygonWebSocketError, PolygonAuthenticationError, PolygonNetworkError
from .utils import normalize_ohlcv_data
from .validators import validate_ohlcv_integrity


class PolygonWebSocketClient:
    """
    WebSocket client for real-time Polygon.io data
    
    Handles connection management, authentication, subscriptions,
    and real-time data streaming with automatic reconnection.
    """
    
    def __init__(self, config=None, storage=None):
        """
        Initialize WebSocket client
        
        Args:
            config: Configuration object (uses default if None)
            storage: Optional StorageManager for caching real-time data
        """
        self.config = config or get_config()
        self.storage = storage
        self.logger = self.config.get_logger(__name__)
        
        # Connection settings
        self.ws_url = getattr(self.config, 'websocket_url', 'wss://socket.polygon.io/stocks')
        self.connection = None
        self.authenticated = False
        self.running = False
        
        # Subscription management
        self.subscriptions = defaultdict(set)  # {symbol: {channels}}
        self.callbacks = defaultdict(list)      # {symbol: [callbacks]}
        
        # Reconnection settings
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 1.0  # seconds
        self.max_reconnect_delay = 30.0
        
        # Performance tracking
        self.message_count = 0
        self.last_message_time = None
        self.connection_start_time = None
        
    async def connect(self):
        """
        Establish WebSocket connection and authenticate
        
        Returns:
            bool: True if connected successfully
            
        Raises:
            PolygonWebSocketError: Connection failed
            PolygonAuthenticationError: Authentication failed
        """
        try:
            self.logger.info(f"Connecting to WebSocket: {self.ws_url}")
            
            # Create WebSocket connection
            self.connection = await websockets.connect(
                self.ws_url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10
            )
            
            # Authenticate
            await self._authenticate()
            
            self.running = True
            self.reconnect_attempts = 0
            self.connection_start_time = datetime.now()
            
            self.logger.info("WebSocket connected and authenticated successfully")
            return True
            
        except websockets.exceptions.WebSocketException as e:
            self.logger.error(f"WebSocket connection failed: {e}")
            raise PolygonWebSocketError(f"Connection failed: {e}")
        except Exception as e:
            self.logger.error(f"Unexpected error during connection: {e}")
            raise PolygonNetworkError(f"Network error: {e}")
    
    async def _authenticate(self):
        auth_msg = {
            "action": "auth",
            "params": self.config.api_key
        }
        
        self.logger.info("Sending authentication request...")
        await self.connection.send(json.dumps(auth_msg))
        
        # First message is usually the connection confirmation
        response = await self.connection.recv()
        data = json.loads(response)
        self.logger.debug(f"First response: {json.dumps(data, indent=2)}")
        
        # Check if this is just a connection message
        if isinstance(data, list) and len(data) > 0:
            first_msg = data[0]
            if (first_msg.get("ev") == "status" and 
                first_msg.get("status") == "connected"):
                self.logger.info("Connection confirmed, waiting for auth response...")
                # Wait for the actual auth response
                response = await self.connection.recv()
                data = json.loads(response)
                self.logger.debug(f"Auth response: {json.dumps(data, indent=2)}")
        
        # Now check for authentication success
        auth_success = False
        
        if isinstance(data, list) and len(data) > 0:
            first_msg = data[0]
            if first_msg.get("status") == "auth_success":
                auth_success = True
            elif (first_msg.get("ev") == "status" and 
                first_msg.get("status") == "auth_success"):
                auth_success = True
                
        elif isinstance(data, dict):
            if data.get("status") == "auth_success":
                auth_success = True
            elif (data.get("ev") == "status" and 
                data.get("status") == "auth_success"):
                auth_success = True
            elif data.get("message") == "authenticated":
                auth_success = True
        
        if auth_success:
            self.authenticated = True
            self.logger.info("Authentication successful")
            return
        else:
            self.logger.error(f"Authentication failed. Response: {json.dumps(data)}")
            raise PolygonAuthenticationError(f"Authentication failed: {data}")
    
    async def subscribe(self, symbols: List[str], channels: List[str], 
                       callback: Callable, subscription_id: Optional[str] = None):
        """
        Subscribe to real-time data for symbols
        
        Args:
            symbols: List of ticker symbols
            channels: List of channel types ['T', 'Q', 'A', 'AM']
                     T = Trades, Q = Quotes, A = Aggregates, AM = Aggregate Minute
            callback: Async function to call with data
            subscription_id: Optional ID to track this subscription
            
        Returns:
            str: Subscription ID for later unsubscribe
        """
        if not self.authenticated:
            raise PolygonWebSocketError("Must be authenticated before subscribing")
        
        # Validate channels
        valid_channels = {'T', 'Q', 'A', 'AM'}
        invalid_channels = set(channels) - valid_channels
        if invalid_channels:
            raise ValueError(f"Invalid channels: {invalid_channels}")
        
        # Store callbacks
        sub_id = subscription_id or f"sub_{datetime.now().timestamp()}"
        for symbol in symbols:
            self.callbacks[symbol].append((sub_id, callback))
            self.subscriptions[symbol].update(channels)
        
        # Build subscription message
        subscriptions = []
        for channel in channels:
            for symbol in symbols:
                subscriptions.append(f"{channel}.{symbol}")
        
        sub_msg = {
            "action": "subscribe",
            "params": ",".join(subscriptions)
        }
        
        await self.connection.send(json.dumps(sub_msg))
        self.logger.info(f"Subscribed to {len(subscriptions)} channels for {len(symbols)} symbols")
        
        return sub_id
    
    async def unsubscribe(self, symbols: List[str], channels: Optional[List[str]] = None,
                         subscription_id: Optional[str] = None):
        """
        Unsubscribe from real-time data
        
        Args:
            symbols: List of symbols to unsubscribe
            channels: Specific channels to unsubscribe (all if None)
            subscription_id: Remove specific subscription callback
        """
        if not self.authenticated:
            return
        
        # Remove callbacks if subscription_id provided
        if subscription_id:
            for symbol in symbols:
                self.callbacks[symbol] = [
                    (sid, cb) for sid, cb in self.callbacks[symbol]
                    if sid != subscription_id
                ]
        
        # Determine channels to unsubscribe
        if channels is None:
            channels = list(set().union(*[self.subscriptions[s] for s in symbols]))
        
        # Build unsubscribe message
        unsubscriptions = []
        for channel in channels:
            for symbol in symbols:
                unsubscriptions.append(f"{channel}.{symbol}")
        
        unsub_msg = {
            "action": "unsubscribe",
            "params": ",".join(unsubscriptions)
        }
        
        await self.connection.send(json.dumps(unsub_msg))
        self.logger.info(f"Unsubscribed from {len(unsubscriptions)} channels")
        
        # Update tracking
        for symbol in symbols:
            if channels:
                self.subscriptions[symbol] -= set(channels)
            else:
                self.subscriptions[symbol].clear()
    
    async def listen(self):
        """
        Main listening loop for receiving data
        
        Handles incoming messages, errors, and reconnection
        """
        while self.running:
            try:
                if not self.connection or (hasattr(self.connection, 'state') and self.connection.state.name != 'OPEN'):
                    await self._reconnect()
                    continue
                
                # Receive message
                message = await self.connection.recv()
                await self._handle_message(message)
                
            except websockets.exceptions.ConnectionClosedError as e:
                self.logger.warning(f"WebSocket connection closed: {e}")
                await self._reconnect()
                
            except websockets.exceptions.WebSocketException as e:
                self.logger.error(f"WebSocket error: {e}")
                await self._reconnect()
                
            except Exception as e:
                self.logger.error(f"Unexpected error in listen loop: {e}")
                # Don't reconnect for unknown errors, just log
                await asyncio.sleep(0.1)  # Prevent tight loop
    
    async def _handle_message(self, message: str):
        """
        Process incoming WebSocket message
        
        Args:
            message: Raw message string from WebSocket
        """
        try:
            data = json.loads(message)
            
            # Handle different message types
            if isinstance(data, list):
                for item in data:
                    await self._process_data_item(item)
            else:
                await self._process_data_item(data)
            
            # Update metrics
            self.message_count += 1
            self.last_message_time = datetime.now()
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse message: {e}")
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")
    
    async def _process_data_item(self, data: Dict):
        """
        Process individual data item
        
        Args:
            data: Parsed data dictionary
        """
        # Get event type and symbol
        event_type = data.get('ev')
        symbol = data.get('sym')
        
        if not event_type or not symbol:
            return
        
        # Get callbacks for this symbol
        callbacks = self.callbacks.get(symbol, [])
        
        # Process based on event type
        processed_data = None
        
        if event_type == 'T':  # Trade
            processed_data = self._process_trade(data)
        elif event_type == 'Q':  # Quote
            processed_data = self._process_quote(data)
        elif event_type in ['A', 'AM']:  # Aggregate
            processed_data = self._process_aggregate(data)
        elif event_type == 'status':  # Status message
            await self._handle_status_message(data)
            return
        
        # Call registered callbacks
        if processed_data:
            for sub_id, callback in callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(processed_data)
                    else:
                        callback(processed_data)
                except Exception as e:
                    self.logger.error(f"Callback error for {symbol}: {e}")
            
            # Optionally update storage
            if self.storage and hasattr(self.storage, 'update_realtime'):
                try:
                    await self.storage.update_realtime(symbol, processed_data)
                except Exception as e:
                    self.logger.error(f"Storage update error: {e}")
    
    def _process_trade(self, data: Dict) -> Dict:
        """Process trade data"""
        return {
            'event_type': 'trade',
            'symbol': data['sym'],
            'timestamp': data['t'],  # Already in milliseconds
            'price': data['p'],
            'size': data['s'],
            'conditions': data.get('c', []),
            'exchange': data.get('x'),
            'trade_id': data.get('i')
        }
    
    def _process_quote(self, data: Dict) -> Dict:
        """Process quote data"""
        return {
            'event_type': 'quote',
            'symbol': data['sym'],
            'timestamp': data['t'],
            'bid_price': data.get('bp'),
            'bid_size': data.get('bs'),
            'ask_price': data.get('ap'),
            'ask_size': data.get('as'),
            'exchange': data.get('x')
        }
    
    def _process_aggregate(self, data: Dict) -> Dict:
        """Process aggregate bar data"""
        return {
            'event_type': 'aggregate',
            'symbol': data['sym'],
            'timestamp': data.get('s', data.get('t')),  # Start time
            'open': data['o'],
            'high': data['h'],
            'low': data['l'],
            'close': data['c'],
            'volume': data['v'],
            'vwap': data.get('vw'),
            'transactions': data.get('n')
        }
    
    async def _handle_status_message(self, data: Dict):
        """Handle status messages from server"""
        status = data.get('status')
        message = data.get('message', '')
        
        self.logger.info(f"Status message: {status} - {message}")
        
        # Handle specific status types
        if status == 'error':
            self.logger.error(f"Server error: {message}")
    
    async def _reconnect(self):
        """
        Attempt to reconnect with exponential backoff
        """
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            self.logger.error("Max reconnection attempts reached, stopping")
            self.running = False
            return
        
        self.reconnect_attempts += 1
        delay = min(
            self.reconnect_delay * (2 ** (self.reconnect_attempts - 1)),
            self.max_reconnect_delay
        )
        
        self.logger.info(f"Reconnecting in {delay} seconds (attempt {self.reconnect_attempts})")
        await asyncio.sleep(delay)
        
        try:
            await self.connect()
            
            # Resubscribe to previous subscriptions
            if self.subscriptions:
                for symbol, channels in self.subscriptions.items():
                    if channels:
                        # Find callbacks for this symbol
                        callbacks = self.callbacks.get(symbol, [])
                        if callbacks:
                            # Use first callback for resubscription
                            _, callback = callbacks[0]
                            await self.subscribe([symbol], list(channels), callback)
            
        except Exception as e:
            self.logger.error(f"Reconnection failed: {e}")
    
    async def disconnect(self):
        """
        Disconnect WebSocket connection
        """
        self.running = False
        
        if self.connection:
            try:
                await self.connection.close()
            except Exception as e:
                self.logger.debug(f"Error closing connection: {e}")
                
        self.authenticated = False
        self.logger.info("WebSocket disconnected")
    
    def get_status(self) -> Dict:
    
        # Check connection state properly
        is_connected = False
        if self.connection is not None:
            # Use the state property for websockets library
            try:
                is_connected = self.connection.state.name == 'OPEN'
            except:
                # Fallback to checking if connection exists
                is_connected = self.connection is not None
        
        return {
            'connected': is_connected,
            'authenticated': self.authenticated,
            'running': self.running,
            'subscriptions': {
                symbol: list(channels) 
                for symbol, channels in self.subscriptions.items()
            },
            'message_count': self.message_count,
            'last_message_time': self.last_message_time.isoformat() if self.last_message_time else None,
            'uptime_seconds': (
                (datetime.now() - self.connection_start_time).total_seconds()
                if self.connection_start_time else 0
            ),
            'reconnect_attempts': self.reconnect_attempts
        }
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.connect()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.disconnect()


# Example usage function for testing
async def example_websocket_usage():
    """
    Example of how to use the WebSocket client
    """
    from .config import PolygonConfig
    
    # Initialize client
    config = PolygonConfig()
    client = PolygonWebSocketClient(config)
    
    # Define callback
    async def handle_data(data):
        print(f"Received {data['event_type']} for {data['symbol']}: {data}")
    
    try:
        # Connect
        await client.connect()
        
        # Subscribe to trades and quotes for AAPL
        await client.subscribe(['AAPL', 'MSFT'], ['T', 'Q'], handle_data)
        
        # Listen for data
        await client.listen()
        
    except KeyboardInterrupt:
        print("Stopping...")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    # Test the WebSocket client
    asyncio.run(example_websocket_usage())