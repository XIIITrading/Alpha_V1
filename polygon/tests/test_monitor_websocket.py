# monitor_websocket.py
"""
Monitor your existing backend WebSocket activity
Place this in your backend directory and run it
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path
import sys

# Add backend to path if needed
sys.path.append(str(Path(__file__).parent.parent))


class WebSocketMonitor:
    """Monitor existing WebSocket connections and data flow"""
    
    def __init__(self):
        self.log_file = Path("polygon/data/logs/polygon.log")
        self.stats = {
            "messages": 0,
            "trades": 0,
            "quotes": 0,
            "aggregates": 0,
            "errors": 0,
            "symbols": set()
        }
        
    def parse_log_line(self, line):
        """Parse a log line for WebSocket activity"""
        if "WebSocket" not in line:
            return None
            
        # Extract timestamp and message
        try:
            parts = line.split(" - ", 3)
            if len(parts) >= 4:
                timestamp = parts[0]
                level = parts[2]
                message = parts[3].strip()
                
                return {
                    "timestamp": timestamp,
                    "level": level,
                    "message": message
                }
        except:
            return None
    
    async def monitor_logs(self, duration=30):
        """Monitor log file for WebSocket activity"""
        print(f"📊 Monitoring WebSocket Activity for {duration} seconds...")
        print("-" * 60)
        
        if not self.log_file.exists():
            print(f"❌ Log file not found: {self.log_file}")
            return
        
        # Get initial file position
        with open(self.log_file, 'r') as f:
            f.seek(0, 2)  # Go to end of file
            initial_pos = f.tell()
        
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < duration:
            with open(self.log_file, 'r') as f:
                f.seek(initial_pos)
                new_lines = f.readlines()
                initial_pos = f.tell()
                
                for line in new_lines:
                    parsed = self.parse_log_line(line)
                    if parsed:
                        self.process_log_entry(parsed)
            
            # Show periodic updates
            if self.stats["messages"] > 0 and self.stats["messages"] % 10 == 0:
                self.show_stats()
            
            await asyncio.sleep(0.5)
        
        # Final stats
        print("\n" + "=" * 60)
        print("FINAL STATISTICS")
        self.show_stats()
    
    def process_log_entry(self, entry):
        """Process a parsed log entry"""
        msg = entry["message"]
        
        # Count message types
        if "trade" in msg.lower():
            self.stats["trades"] += 1
        elif "quote" in msg.lower():
            self.stats["quotes"] += 1
        elif "aggregate" in msg.lower():
            self.stats["aggregates"] += 1
        elif "error" in msg.lower():
            self.stats["errors"] += 1
        
        # Extract symbols
        for word in msg.split():
            if word.isupper() and len(word) <= 5 and word.isalpha():
                self.stats["symbols"].add(word)
        
        self.stats["messages"] += 1
        
        # Display important messages
        if entry["level"] in ["ERROR", "WARNING"]:
            print(f"\n⚠️  [{entry['timestamp']}] {msg}")
        elif "subscribed" in msg.lower() or "connected" in msg.lower():
            print(f"\n✅ [{entry['timestamp']}] {msg}")
    
    def show_stats(self):
        """Display current statistics"""
        print(f"\n📈 WebSocket Statistics:")
        print(f"   Total Messages: {self.stats['messages']}")
        print(f"   Trades: {self.stats['trades']}")
        print(f"   Quotes: {self.stats['quotes']}")
        print(f"   Aggregates: {self.stats['aggregates']}")
        print(f"   Errors: {self.stats['errors']}")
        if self.stats['symbols']:
            print(f"   Active Symbols: {', '.join(sorted(self.stats['symbols']))}")
    
    async def check_backend_websocket(self):
        """Check if WebSocket service is running"""
        try:
            # Try to import and check the service
            from backend.services.polygon_websocket import PolygonWebSocketService
            print("✅ Backend WebSocket service found")
            return True
        except ImportError:
            print("⚠️  Backend WebSocket service not found in expected location")
            return False


async def main():
    """Main monitoring function"""
    print("🔍 WebSocket Activity Monitor")
    print("=" * 60)
    
    monitor = WebSocketMonitor()
    
    # Check backend
    await monitor.check_backend_websocket()
    
    # Monitor logs
    await monitor.monitor_logs(duration=30)
    
    print("\n💡 Tips:")
    print("1. Make sure your backend is running with WebSocket enabled")
    print("2. Subscribe to symbols through your backend API")
    print("3. Check backend console for real-time messages")
    print("4. WebSocket data is being processed by your market structure service")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring stopped by user")