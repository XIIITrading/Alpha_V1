#!/usr/bin/env python3
"""
Live test script for polygon WebSocket implementation
Run this to verify WebSocket connectivity and data reception
"""

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Force import from local polygon module, not installed package
project_root = Path(__file__).parent.parent.parent  # Go up to AlphaXIII_V2
sys.path.insert(0, str(project_root))  # Insert at beginning to take precedence

# Debug import path
print(f"Project root: {project_root}")
print(f"Python path[0]: {sys.path[0]}")

# Now import from local polygon module
try:
    # Import the websocket module directly to avoid package conflicts
    import polygon.websocket as ws_module
    PolygonWebSocketClient = ws_module.PolygonWebSocketClient
    
    # Import config
    import polygon.config as config_module
    PolygonConfig = config_module.PolygonConfig
    
    print(f"Successfully imported from local polygon module")
    print(f"WebSocket module location: {ws_module.__file__}")
except ImportError as e:
    print(f"Error importing polygon module: {e}")
    print(f"Checking if files exist:")
    websocket_file = project_root / 'polygon' / 'websocket.py'
    config_file = project_root / 'polygon' / 'config.py'
    print(f"  websocket.py exists: {websocket_file.exists()}")
    print(f"  config.py exists: {config_file.exists()}")
    sys.exit(1)

# ANSI colors for output
class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'


class WebSocketTester:
    def __init__(self):
        self.client = None
        self.data_received = {
            'trades': 0,
            'quotes': 0,
            'aggregates': 0
        }
        self.start_time = None
        self.test_symbols = ['AAPL', 'MSFT']  # Popular symbols for testing
        
    async def data_handler(self, data):
        """Handle incoming data and display it"""
        event_type = data.get('event_type')
        symbol = data.get('symbol')
        
        # Count by type
        if event_type == 'trade':
            self.data_received['trades'] += 1
            print(f"{Colors.GREEN}[TRADE]{Colors.END} {symbol}: ${data['price']:.2f} x {data['size']} @ {self._format_time(data['timestamp'])}")
        
        elif event_type == 'quote':
            self.data_received['quotes'] += 1
            bid_price = data.get('bid_price', 0) or 0
            bid_size = data.get('bid_size', 0) or 0
            ask_price = data.get('ask_price', 0) or 0
            ask_size = data.get('ask_size', 0) or 0
            print(f"{Colors.BLUE}[QUOTE]{Colors.END} {symbol}: Bid ${bid_price:.2f} x {bid_size} | Ask ${ask_price:.2f} x {ask_size}")
        
        elif event_type == 'aggregate':
            self.data_received['aggregates'] += 1
            print(f"{Colors.YELLOW}[BAR]{Colors.END} {symbol}: O:${data['open']:.2f} H:${data['high']:.2f} L:${data['low']:.2f} C:${data['close']:.2f} V:{data['volume']}")
        
        # Show running totals every 10 messages
        total = sum(self.data_received.values())
        if total % 10 == 0:
            self._print_stats()
    
    def _format_time(self, timestamp_ms):
        """Format millisecond timestamp to readable time"""
        if isinstance(timestamp_ms, int):
            return datetime.fromtimestamp(timestamp_ms / 1000).strftime('%H:%M:%S.%f')[:-3]
        return str(timestamp_ms)
    
    def _print_stats(self):
        """Print current statistics"""
        elapsed = (datetime.now() - self.start_time).total_seconds()
        total = sum(self.data_received.values())
        rate = total / elapsed if elapsed > 0 else 0
        
        print(f"\n{Colors.BOLD}=== Stats ==={Colors.END}")
        print(f"Uptime: {elapsed:.1f}s | Rate: {rate:.1f} msg/s")
        print(f"Trades: {self.data_received['trades']} | Quotes: {self.data_received['quotes']} | Bars: {self.data_received['aggregates']}")
        print(f"{Colors.BOLD}============{Colors.END}\n")
    
    async def test_connection(self):
        """Test basic connection and authentication"""
        print(f"\n{Colors.BOLD}Testing WebSocket Connection...{Colors.END}\n")
        
        try:
            # Create client
            config = PolygonConfig()
            self.client = PolygonWebSocketClient(config)
            
            # Test connection
            print(f"1. Connecting to {self.client.ws_url}...")
            connected = await self.client.connect()
            
            if connected:
                print(f"{Colors.GREEN}✓ Connected successfully{Colors.END}")
                print(f"{Colors.GREEN}✓ Authenticated successfully{Colors.END}")
            else:
                print(f"{Colors.RED}✗ Connection failed{Colors.END}")
                return False
            
            # Get status
            status = self.client.get_status()
            print(f"\n{Colors.BOLD}Connection Status:{Colors.END}")
            print(f"  Connected: {status['connected']}")
            print(f"  Authenticated: {status['authenticated']}")
            print(f"  Running: {status['running']}")
            
            return True
            
        except Exception as e:
            print(f"{Colors.RED}✗ Error: {e}{Colors.END}")
            import traceback
            traceback.print_exc()
            return False
    
    async def test_subscriptions(self):
        """Test subscribing to data streams"""
        print(f"\n{Colors.BOLD}Testing Subscriptions...{Colors.END}\n")
        
        self.start_time = datetime.now()
        
        try:
            # Subscribe to trades
            print(f"2. Subscribing to trades for {', '.join(self.test_symbols)}...")
            sub_id = await self.client.subscribe(
                self.test_symbols, 
                ['T'],  # Just trades for now
                self.data_handler
            )
            print(f"{Colors.GREEN}✓ Subscribed to trades (ID: {sub_id}){Colors.END}")
            
            # Wait a bit, then add quotes
            await asyncio.sleep(3)
            
            print(f"\n3. Adding quote subscription...")
            await self.client.subscribe(
                self.test_symbols,
                ['Q'],  # Quotes
                self.data_handler
            )
            print(f"{Colors.GREEN}✓ Subscribed to quotes{Colors.END}")
            
            # Listen for data
            print(f"\n{Colors.YELLOW}Listening for data (press Ctrl+C to stop)...{Colors.END}")
            print(f"{Colors.YELLOW}Note: If no data appears, markets may be closed{Colors.END}\n")
            
            # Create listen task
            listen_task = asyncio.create_task(self.client.listen())
            
            # Run for 30 seconds or until interrupted
            try:
                await asyncio.wait_for(listen_task, timeout=30)
            except asyncio.TimeoutError:
                print(f"\n{Colors.YELLOW}Test completed (30 second timeout){Colors.END}")
            
        except KeyboardInterrupt:
            print(f"\n{Colors.YELLOW}Test interrupted by user{Colors.END}")
        except Exception as e:
            print(f"{Colors.RED}✗ Subscription error: {e}{Colors.END}")
            import traceback
            traceback.print_exc()
        
        # Final stats
        self._print_stats()
    
    async def test_error_handling(self):
        """Test error scenarios"""
        print(f"\n{Colors.BOLD}Testing Error Handling...{Colors.END}\n")
        
        # Test invalid symbol
        try:
            print("4. Testing invalid subscription...")
            await self.client.subscribe(
                ['INVALID_SYMBOL_12345'], 
                ['T'], 
                self.data_handler
            )
            # Polygon might accept the subscription but not send data
            print(f"{Colors.YELLOW}⚠ Subscription accepted (may not receive data){Colors.END}")
        except Exception as e:
            print(f"{Colors.GREEN}✓ Error handled: {e}{Colors.END}")
    
    async def run_all_tests(self):
        """Run all tests in sequence"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}Polygon WebSocket Live Test{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")
        
        # Check for API key
        api_key = os.getenv('POLYGON_API_KEY')
        if not api_key:
            # Try to load from .env file
            env_file = project_root / '.env'
            if env_file.exists():
                from dotenv import load_dotenv
                load_dotenv(env_file)
                api_key = os.getenv('POLYGON_API_KEY')
            
            if not api_key:
                print(f"{Colors.RED}✗ POLYGON_API_KEY not found{Colors.END}")
                print(f"  Option 1: set POLYGON_API_KEY=your_key_here")
                print(f"  Option 2: Add to .env file in project root")
                return
        
        print(f"{Colors.GREEN}✓ API key found{Colors.END}")
        print(f"  Key: {api_key[:8]}...{api_key[-4:]}\n")
        
        try:
            # Test 1: Connection
            if not await self.test_connection():
                return
            
            # Test 2: Subscriptions
            await self.test_subscriptions()
            
            # Test 3: Error handling
            await self.test_error_handling()
            
            # Cleanup
            print(f"\n{Colors.BOLD}Cleaning up...{Colors.END}")
            await self.client.disconnect()
            print(f"{Colors.GREEN}✓ Disconnected{Colors.END}")
            
            # Summary
            print(f"\n{Colors.BOLD}{Colors.GREEN}All tests completed!{Colors.END}")
            
        except Exception as e:
            print(f"\n{Colors.RED}Test failed with error: {e}{Colors.END}")
            import traceback
            traceback.print_exc()
            if self.client:
                await self.client.disconnect()


async def main():
    """Main entry point"""
    tester = WebSocketTester()
    await tester.run_all_tests()


if __name__ == "__main__":
    # Run the test
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Test cancelled by user{Colors.END}")