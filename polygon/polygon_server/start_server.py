#!/usr/bin/env python3
"""
Polygon Data Server Startup Script
Unified REST and WebSocket server for Polygon.io data
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path

# Fix Python path to ensure polygon module can be imported
project_root = Path(__file__).parent.parent.parent  # Go up to project root
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Also add the polygon directory to path
polygon_dir = Path(__file__).parent.parent
if str(polygon_dir) not in sys.path:
    sys.path.insert(0, str(polygon_dir))

# Try to load dotenv
try:
    from dotenv import load_dotenv
    # Load environment variables from .env file
    env_path = project_root / '.env'
    if env_path.exists():
        load_dotenv(env_path)
        print(f"Loaded environment from {env_path}")
    else:
        load_dotenv()  # Try to find .env in current directory
except ImportError:
    print("python-dotenv not installed. Using system environment variables only.")
    print("Install with: pip install python-dotenv")

# ANSI color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_banner():
    """Display startup banner"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("╔" + "═" * 58 + "╗")
    print("║" + " " * 15 + "Polygon Data Server v1.0" + " " * 19 + "║")
    print("╠" + "═" * 58 + "╣")
    print("║" + " " * 11 + "REST API + WebSocket Streaming" + " " * 17 + "║")
    print("╚" + "═" * 58 + "╝")
    print(f"{Colors.END}\n")


def create_env_template():
    """Create a .env template file"""
    env_content = """# Polygon Data Server Configuration
# This file should NOT be committed to version control

# Polygon.io API Configuration
POLYGON_API_KEY=your_polygon_api_key_here

# Server Configuration
SERVER_HOST=0.0.0.0
SERVER_PORT=8200
SERVER_WORKERS=1

# CORS Settings (comma-separated origins)
CORS_ORIGINS=*

# Cache Settings
CACHE_DIR=./polygon_cache
CACHE_TTL=3600

# WebSocket Settings
WS_HEARTBEAT=30
WS_MAX_CONNECTIONS=100

# Logging
LOG_LEVEL=INFO
LOG_FILE=polygon_server.log

# Polygon Tier (basic, starter, developer, advanced)
POLYGON_TIER=advanced
"""
    env_file = project_root / '.env'
    env_file.write_text(env_content)


def configure_environment():
    """Set up and validate environment variables"""
    print(f"{Colors.YELLOW}Configuring environment...{Colors.END}")
    
    # Check for Polygon API key
    polygon_key = os.getenv('POLYGON_API_KEY')
    if not polygon_key:
        print(f"{Colors.RED}✗ POLYGON_API_KEY not found{Colors.END}")
        print(f"  Add it to your .env file:")
        print(f"  POLYGON_API_KEY=your_key_here")
        
        env_file = project_root / '.env'
        if not env_file.exists():
            print(f"\n{Colors.YELLOW}No .env file found. Creating template...{Colors.END}")
            create_env_template()
            print(f"{Colors.GREEN}✓ Created .env file. Please add your API key and restart.{Colors.END}")
            sys.exit(1)
        
        print(f"\n{Colors.RED}Cannot start server without API key{Colors.END}")
        sys.exit(1)
    else:
        # Mask the API key for security
        masked_key = polygon_key[:8] + '...' + polygon_key[-4:] if len(polygon_key) > 12 else 'key_configured'
        print(f"{Colors.GREEN}✓ Polygon API key found: {masked_key}{Colors.END}")
    
    # Set server configuration with defaults
    os.environ['SERVER_HOST'] = os.getenv('SERVER_HOST', '0.0.0.0')
    os.environ['SERVER_PORT'] = os.getenv('SERVER_PORT', '8200')
    os.environ['LOG_LEVEL'] = os.getenv('LOG_LEVEL', 'INFO')
    
    print(f"{Colors.GREEN}✓ Environment configured{Colors.END}")


def install_dependencies():
    """Install required dependencies"""
    print(f"{Colors.YELLOW}Installing dependencies...{Colors.END}")
    
    requirements_file = Path(__file__).parent / 'requirements.txt'
    if requirements_file.exists():
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)], check=True)
        print(f"{Colors.GREEN}✓ Dependencies installed{Colors.END}")
    else:
        print(f"{Colors.RED}✗ requirements.txt not found{Colors.END}")
        sys.exit(1)


def start_server(host: str = None, port: int = None, workers: int = 1, reload: bool = False):
    """Start the Polygon data server"""
    print_banner()
    
    # Configure environment first
    configure_environment()
    
    # Use provided values or environment defaults
    host = host or os.getenv('SERVER_HOST', '0.0.0.0')
    port = port or int(os.getenv('SERVER_PORT', '8200'))
    
    # Import and verify server app exists
    try:
        from polygon.polygon_server.server import app
        print(f"{Colors.GREEN}✓ Server app imported successfully{Colors.END}")
    except ImportError as e:
        print(f"{Colors.RED}✗ Failed to import server app: {e}{Colors.END}")
        print(f"Current directory: {os.getcwd()}")
        print(f"Python path: {sys.path[:3]}")
        sys.exit(1)
    
    # Start the server
    print(f"\n{Colors.GREEN}Starting Polygon Data Server...{Colors.END}")
    print(f"Host: {Colors.BOLD}{host}{Colors.END}")
    print(f"Port: {Colors.BOLD}{port}{Colors.END}")
    print(f"Workers: {Colors.BOLD}{workers if not reload else 1}{Colors.END}")
    print(f"\n{Colors.BOLD}URLs:{Colors.END}")
    print(f"  Base URL: {Colors.BOLD}http://localhost:{port}{Colors.END}")
    print(f"  API Docs: {Colors.BOLD}http://localhost:{port}/docs{Colors.END}")
    print(f"  Health:   {Colors.BOLD}http://localhost:{port}/health{Colors.END}")
    print(f"  WebSocket: {Colors.BOLD}ws://localhost:{port}/ws/{{client_id}}{Colors.END}")
    print(f"\n{Colors.YELLOW}Press Ctrl+C to stop the server{Colors.END}\n")
    
    # Try running with uvicorn module first (more reliable)
    try:
        cmd = [
            sys.executable, '-m', 'uvicorn',
            'polygon.polygon_server.server:app',
            '--host', host,
            '--port', str(port),
            '--workers', str(workers if not reload else 1),
            '--log-level', os.getenv('LOG_LEVEL', 'INFO').lower()
        ]
        
        if reload:
            cmd.append('--reload')
        
        subprocess.run(cmd, check=True)
        
    except subprocess.CalledProcessError:
        # If module approach fails, try direct import
        print(f"{Colors.YELLOW}Trying direct uvicorn import...{Colors.END}")
        try:
            import uvicorn
            uvicorn.run(
                app,  # Pass the app object directly
                host=host,
                port=port,
                workers=workers if not reload else 1,
                reload=reload,
                log_level=os.getenv('LOG_LEVEL', 'INFO').lower()
            )
        except ImportError:
            print(f"{Colors.RED}✗ uvicorn not installed{Colors.END}")
            print(f"Install with: {sys.executable} -m pip install uvicorn[standard]")
            sys.exit(1)
        except Exception as e:
            print(f"{Colors.RED}✗ Server startup failed: {e}{Colors.END}")
            sys.exit(1)
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Shutting down server...{Colors.END}")
        print(f"{Colors.GREEN}✓ Server stopped{Colors.END}")


def test_connection(port: int = 8200):
    """Test if the server is running"""
    try:
        import requests
    except ImportError:
        print(f"{Colors.YELLOW}Installing requests for connection test...{Colors.END}")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'], check=True)
        import requests
    
    print(f"\n{Colors.YELLOW}Testing server connection...{Colors.END}")
    
    base_url = f'http://localhost:{port}'
    
    # Test health endpoint
    try:
        response = requests.get(f'{base_url}/health')
        if response.status_code == 200:
            print(f"{Colors.GREEN}✓ Server is running and healthy{Colors.END}")
            
            # Test status endpoint for more details
            status_response = requests.get(f'{base_url}/status')
            if status_response.status_code == 200:
                data = status_response.json()
                print(f"\n{Colors.BOLD}Server Status:{Colors.END}")
                print(f"  Version: {data.get('version', 'unknown')}")
                print(f"  Uptime: {data.get('uptime_seconds', 0):.1f} seconds")
                print(f"  Polygon Connected: {data.get('polygon_connected', False)}")
                print(f"  WebSocket Clients: {data.get('websocket_clients', 0)}")
            
            print(f"\n{Colors.BOLD}Available Endpoints:{Colors.END}")
            print(f"  API Docs: {base_url}/docs")
            print(f"  REST API: {base_url}/api/v1/*")
            print(f"  WebSocket: ws://localhost:{port}/ws/{{client_id}}")
            
            return True
        else:
            print(f"{Colors.RED}✗ Server returned status {response.status_code}{Colors.END}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"{Colors.RED}✗ Could not connect to server at port {port}{Colors.END}")
        print(f"  Make sure the server is running:")
        print(f"  python -m polygon.polygon_server.start_server")
        return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='Polygon Data Server - Unified REST and WebSocket API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python start_server.py                    # Start with defaults
  python start_server.py --port 8300        # Use custom port
  python start_server.py --reload           # Enable auto-reload (development)
  python start_server.py --test             # Test server connection
  python start_server.py --install-deps     # Install dependencies only
        """
    )
    
    # Server options
    parser.add_argument(
        '--host', 
        default=None,
        help='Host to bind to (default: 0.0.0.0)'
    )
    parser.add_argument(
        '--port', 
        type=int, 
        default=None,
        help='Port to bind to (default: 8200)'
    )
    parser.add_argument(
        '--workers', 
        type=int, 
        default=1,
        help='Number of worker processes (default: 1)'
    )
    parser.add_argument(
        '--reload', 
        action='store_true',
        help='Enable auto-reload for development'
    )
    
    # Other options
    parser.add_argument(
        '--test', 
        action='store_true',
        help='Test if server is running'
    )
    parser.add_argument(
        '--install-deps',
        action='store_true',
        help='Install dependencies only'
    )
    
    args = parser.parse_args()
    
    # Handle special modes
    if args.test:
        test_connection(args.port or 8200)
        return
    
    if args.install_deps:
        install_dependencies()
        return
    
    # Start server
    start_server(
        host=args.host,
        port=args.port,
        workers=args.workers,
        reload=args.reload
    )


if __name__ == '__main__':
    main()