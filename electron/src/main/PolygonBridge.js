// electron/src/main/PolygonBridge.js
/**
 * PolygonBridge - Connects Electron app to FastAPI Polygon server
 * 
 * This module:
 * - Manages REST API connections to the FastAPI server
 * - Handles WebSocket connections for real-time data
 * - Integrates with IPCHandler event system
 * - Provides automatic reconnection and error handling
 */

const WebSocket = require('ws');
const EventEmitter = require('events');
const path = require('path');
const { spawn } = require('child_process');
const log = require('electron-log');

// Configure logging for this module
const logger = log.scope('PolygonBridge');

class PolygonBridge extends EventEmitter {
    constructor(options = {}) {
        super();
        
        // Configuration
        this.serverUrl = options.serverUrl || 'http://localhost:8200';
        this.wsUrl = options.wsUrl || 'ws://localhost:8200';
        this.autoStartServer = options.autoStartServer || false;
        this.serverStartTimeout = options.serverStartTimeout || 10000;
        this.reconnectInterval = options.reconnectInterval || 5000;
        this.maxReconnectAttempts = options.maxReconnectAttempts || 10;
        
        // State management
        this.initialized = false;
        this.serverProcess = null;
        this.wsConnections = new Map(); // clientId -> WebSocket
        this.subscriptions = new Map(); // subscriptionId -> { clientId, symbols, channels }
        this.reconnectAttempts = new Map(); // clientId -> attempt count
        
        // IPC Handler reference
        this.ipcHandler = options.ipcHandler;
        
        // Bind methods
        this.handleDataRequest = this.handleDataRequest.bind(this);
        this.handleDataSubscribe = this.handleDataSubscribe.bind(this);
        this.handleDataUnsubscribe = this.handleDataUnsubscribe.bind(this);
        
        logger.info('PolygonBridge initialized with config:', {
            serverUrl: this.serverUrl,
            wsUrl: this.wsUrl,
            autoStartServer: this.autoStartServer
        });
    }
    
    /**
     * Initialize the bridge
     */
    async initialize() {
        if (this.initialized) {
            logger.warn('PolygonBridge already initialized');
            return;
        }
        
        try {
            // Start server if configured
            if (this.autoStartServer) {
                await this.startServer();
            }
            
            // Verify server is accessible
            await this.verifyServerConnection();
            
            // Set up event listeners
            this.setupEventListeners();
            
            this.initialized = true;
            logger.info('PolygonBridge initialized successfully');
            
            // Emit ready event
            this.emit('ready');
            
        } catch (error) {
            logger.error('Failed to initialize PolygonBridge:', error);
            throw error;
        }
    }
    
    /**
     * Start the FastAPI server
     */
    async startServer() {
        return new Promise((resolve, reject) => {
            logger.info('Starting FastAPI server...');
            
            const pythonPath = process.platform === 'win32' ? 'python' : 'python3';
            const serverPath = path.join(__dirname, '..', '..', '..', '..', 'polygon_server', 'start_server.py');
            
            // Spawn Python server process
            this.serverProcess = spawn(pythonPath, [serverPath], {
                cwd: path.dirname(serverPath),
                env: { ...process.env },
                stdio: ['ignore', 'pipe', 'pipe']
            });
            
            let serverStarted = false;
            const timeout = setTimeout(() => {
                if (!serverStarted) {
                    this.serverProcess.kill();
                    reject(new Error('Server start timeout'));
                }
            }, this.serverStartTimeout);
            
            // Handle stdout
            this.serverProcess.stdout.on('data', (data) => {
                const message = data.toString().trim();
                logger.debug(`[Server] ${message}`);
                
                // Check for startup confirmation
                if (message.includes('Uvicorn running') || message.includes('Started server')) {
                    serverStarted = true;
                    clearTimeout(timeout);
                    
                    // Wait a bit for full initialization
                    setTimeout(() => resolve(), 1000);
                }
            });
            
            // Handle stderr
            this.serverProcess.stderr.on('data', (data) => {
                logger.error(`[Server Error] ${data.toString().trim()}`);
            });
            
            // Handle process exit
            this.serverProcess.on('exit', (code, signal) => {
                logger.warn(`Server process exited with code ${code}, signal ${signal}`);
                this.emit('server-exit', { code, signal });
            });
            
            // Handle process errors
            this.serverProcess.on('error', (error) => {
                logger.error('Server process error:', error);
                clearTimeout(timeout);
                reject(error);
            });
        });
    }
    
    /**
     * Verify server connection
     */
    async verifyServerConnection() {
        try {
            const response = await fetch(`${this.serverUrl}/health`);
            if (!response.ok) {
                throw new Error(`Server health check failed: ${response.status}`);
            }
            
            const health = await response.json();
            logger.info('Server health check passed:', health);
            
        } catch (error) {
            logger.error('Server connection verification failed:', error);
            throw new Error('Cannot connect to Polygon server. Ensure it is running.');
        }
    }
    
    /**
     * Set up event listeners for IPC communication
     */
    setupEventListeners() {
        if (!this.ipcHandler) {
            logger.warn('No IPC handler provided, skipping event listener setup');
            return;
        }
        
        // Listen for data requests
        this.ipcHandler.on('data-request', this.handleDataRequest);
        
        // Listen for subscription requests
        this.ipcHandler.on('data-subscribe', this.handleDataSubscribe);
        
        // Listen for unsubscribe requests
        this.ipcHandler.on('data-unsubscribe', this.handleDataUnsubscribe);
        
        logger.info('Event listeners set up successfully');
    }
    
    /**
     * Handle data request (REST API call)
     */
    async handleDataRequest({ operationId, source, params, windowId }) {
        logger.debug(`Handling data request: ${operationId}`, { source, params });
        
        try {
            let response;
            
            switch (source) {
                case 'polygon':
                    response = await this.fetchPolygonData(params);
                    break;
                    
                case 'cache':
                    response = await this.fetchCachedData(params);
                    break;
                    
                case 'calculate':
                    response = await this.calculateData(params);
                    break;
                    
                default:
                    throw new Error(`Unknown data source: ${source}`);
            }
            
            // Emit response
            this.ipcHandler.emit(`data-response-${operationId}`, {
                success: true,
                data: response
            });
            
        } catch (error) {
            logger.error(`Data request failed for ${operationId}:`, error);
            
            // Emit error response
            this.ipcHandler.emit(`data-response-${operationId}`, {
                success: false,
                error: error.message
            });
        }
    }
    
    /**
     * Fetch data from Polygon API via server
     */
    async fetchPolygonData(params) {
        const { endpoint, method = 'GET', data, ...queryParams } = params;
        
        // Build URL with query parameters
        const url = new URL(`${this.serverUrl}/api/v1${endpoint}`);
        Object.entries(queryParams).forEach(([key, value]) => {
            if (value !== undefined && value !== null) {
                url.searchParams.append(key, value);
            }
        });
        
        // Make request
        const options = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json'
            }
        };
        
        if (data && method !== 'GET') {
            options.body = JSON.stringify(data);
        }
        
        const response = await fetch(url.toString(), options);
        
        if (!response.ok) {
            const error = await response.text();
            throw new Error(`API request failed: ${response.status} - ${error}`);
        }
        
        return await response.json();
    }
    
    /**
     * Fetch cached data
     */
    async fetchCachedData(params) {
        const response = await fetch(`${this.serverUrl}/api/v1/cache/stats`);
        
        if (!response.ok) {
            throw new Error(`Cache request failed: ${response.status}`);
        }
        
        return await response.json();
    }
    
    /**
     * Calculate derived data
     */
    async calculateData(params) {
        // This would call a calculation endpoint if available
        // For now, return mock data
        return {
            calculated: true,
            params: params,
            result: {}
        };
    }
    
    /**
     * Handle subscription request (WebSocket)
     */
    async handleDataSubscribe({ subscriptionId, windowId, stream, symbols, options }) {
        logger.info(`Handling subscription: ${subscriptionId}`, { stream, symbols });
        
        try {
            // Use windowId as clientId for WebSocket connection
            const clientId = `window-${windowId}`;
            
            // Get or create WebSocket connection
            let ws = this.wsConnections.get(clientId);
            if (!ws || ws.readyState !== WebSocket.OPEN) {
                ws = await this.createWebSocketConnection(clientId);
            }
            
            // Send subscription message
            const subscribeMessage = {
                action: 'subscribe',
                symbols: symbols,
                channels: this.mapStreamToChannels(stream)
            };
            
            ws.send(JSON.stringify(subscribeMessage));
            
            // Store subscription info
            this.subscriptions.set(subscriptionId, {
                clientId,
                windowId,
                stream,
                symbols,
                options
            });
            
            // Emit success
            this.emit('subscription-created', {
                subscriptionId,
                windowId,
                symbols
            });
            
        } catch (error) {
            logger.error(`Subscription failed for ${subscriptionId}:`, error);
            this.emit('subscription-error', {
                subscriptionId,
                error: error.message
            });
        }
    }
    
    /**
     * Handle unsubscribe request
     */
    async handleDataUnsubscribe({ subscriptionId }) {
        logger.info(`Handling unsubscribe: ${subscriptionId}`);
        
        const subscription = this.subscriptions.get(subscriptionId);
        if (!subscription) {
            logger.warn(`Subscription not found: ${subscriptionId}`);
            return;
        }
        
        try {
            const { clientId, symbols } = subscription;
            const ws = this.wsConnections.get(clientId);
            
            if (ws && ws.readyState === WebSocket.OPEN) {
                // Send unsubscribe message
                const unsubscribeMessage = {
                    action: 'unsubscribe',
                    symbols: symbols
                };
                
                ws.send(JSON.stringify(unsubscribeMessage));
            }
            
            // Remove subscription
            this.subscriptions.delete(subscriptionId);
            
            // Close WebSocket if no more subscriptions for this client
            const hasMoreSubscriptions = Array.from(this.subscriptions.values())
                .some(sub => sub.clientId === clientId);
            
            if (!hasMoreSubscriptions && ws) {
                ws.close();
                this.wsConnections.delete(clientId);
            }
            
        } catch (error) {
            logger.error(`Unsubscribe failed for ${subscriptionId}:`, error);
        }
    }
    
    /**
     * Create WebSocket connection
     */
    async createWebSocketConnection(clientId) {
        return new Promise((resolve, reject) => {
            logger.info(`Creating WebSocket connection for ${clientId}`);
            
            const wsUrl = `${this.wsUrl}/ws/${clientId}`;
            const ws = new WebSocket(wsUrl);
            
            // Connection timeout
            const timeout = setTimeout(() => {
                ws.close();
                reject(new Error('WebSocket connection timeout'));
            }, 5000);
            
            // Handle open
            ws.on('open', () => {
                clearTimeout(timeout);
                logger.info(`WebSocket connected for ${clientId}`);
                
                // Store connection
                this.wsConnections.set(clientId, ws);
                
                // Reset reconnect attempts
                this.reconnectAttempts.delete(clientId);
                
                resolve(ws);
            });
            
            // Handle messages
            ws.on('message', (data) => {
                try {
                    const message = JSON.parse(data.toString());
                    this.handleWebSocketMessage(clientId, message);
                } catch (error) {
                    logger.error(`Failed to parse WebSocket message:`, error);
                }
            });
            
            // Handle errors
            ws.on('error', (error) => {
                logger.error(`WebSocket error for ${clientId}:`, error);
                clearTimeout(timeout);
                reject(error);
            });
            
            // Handle close
            ws.on('close', (code, reason) => {
                logger.warn(`WebSocket closed for ${clientId}: ${code} - ${reason}`);
                this.wsConnections.delete(clientId);
                
                // Attempt reconnection for active subscriptions
                this.handleWebSocketReconnection(clientId);
            });
            
            // Handle ping/pong for keepalive
            ws.on('ping', () => ws.pong());
        });
    }
    
    /**
     * Handle incoming WebSocket message
     */
    handleWebSocketMessage(clientId, message) {
        const { type, data, timestamp } = message;
        
        logger.debug(`WebSocket message from ${clientId}:`, type);
        
        switch (type) {
            case 'connected':
                logger.info(`Client ${clientId} connected to server`);
                break;
                
            case 'subscribed':
                logger.info(`Subscription confirmed for ${clientId}:`, data);
                break;
                
            case 'market_data':
                // Forward market data to appropriate window
                this.forwardMarketData(clientId, data);
                break;
                
            case 'error':
                logger.error(`Server error for ${clientId}:`, message.message);
                break;
                
            case 'pong':
                // Heartbeat response
                logger.debug(`Heartbeat response from ${clientId}`);
                break;
                
            default:
                logger.warn(`Unknown message type from ${clientId}:`, type);
        }
    }
    
    /**
     * Forward market data to renderer process
     */
    forwardMarketData(clientId, data) {
        // Find all subscriptions for this client
        const clientSubscriptions = Array.from(this.subscriptions.entries())
            .filter(([_, sub]) => sub.clientId === clientId);
        
        // Forward data to each subscription's window
        for (const [subscriptionId, subscription] of clientSubscriptions) {
            const { windowId, stream } = subscription;
            
            // Check if data matches subscription
            if (this.dataMatchesSubscription(data, subscription)) {
                // Emit data event for window
                this.emit('market-data', {
                    windowId,
                    subscriptionId,
                    stream,
                    data
                });
            }
        }
    }
    
    /**
     * Check if data matches subscription criteria
     */
    dataMatchesSubscription(data, subscription) {
        const { symbols } = subscription;
        
        // Check if data symbol matches subscription
        if (data.symbol && symbols.includes(data.symbol)) {
            return true;
        }
        
        // Check for batch data
        if (Array.isArray(data)) {
            return data.some(item => item.symbol && symbols.includes(item.symbol));
        }
        
        return false;
    }
    
    /**
     * Handle WebSocket reconnection
     */
    async handleWebSocketReconnection(clientId) {
        // Check if there are active subscriptions for this client
        const activeSubscriptions = Array.from(this.subscriptions.values())
            .filter(sub => sub.clientId === clientId);
        
        if (activeSubscriptions.length === 0) {
            logger.info(`No active subscriptions for ${clientId}, skipping reconnection`);
            return;
        }
        
        // Get reconnect attempt count
        const attempts = (this.reconnectAttempts.get(clientId) || 0) + 1;
        this.reconnectAttempts.set(clientId, attempts);
        
        if (attempts > this.maxReconnectAttempts) {
            logger.error(`Max reconnection attempts reached for ${clientId}`);
            this.emit('reconnection-failed', { clientId, attempts });
            return;
        }
        
        // Calculate backoff delay
        const delay = Math.min(this.reconnectInterval * attempts, 30000);
        
        logger.info(`Reconnecting ${clientId} in ${delay}ms (attempt ${attempts})`);
        
        setTimeout(async () => {
            try {
                // Create new connection
                const ws = await this.createWebSocketConnection(clientId);
                
                // Resubscribe to all active subscriptions
                for (const subscription of activeSubscriptions) {
                    const subscribeMessage = {
                        action: 'subscribe',
                        symbols: subscription.symbols,
                        channels: this.mapStreamToChannels(subscription.stream)
                    };
                    
                    ws.send(JSON.stringify(subscribeMessage));
                }
                
                logger.info(`Reconnected and resubscribed for ${clientId}`);
                
            } catch (error) {
                logger.error(`Reconnection failed for ${clientId}:`, error);
                // Will retry again
                this.handleWebSocketReconnection(clientId);
            }
        }, delay);
    }
    
    /**
     * Map stream type to Polygon channels
     */
    mapStreamToChannels(stream) {
        const channelMap = {
            'trades': ['T'],
            'quotes': ['Q'],
            'bars': ['A', 'AM'],
            'updates': ['T', 'Q', 'A']
        };
        
        return channelMap[stream] || ['T'];
    }
    
    /**
     * Get bridge status
     */
    getStatus() {
        return {
            initialized: this.initialized,
            serverUrl: this.serverUrl,
            serverRunning: this.serverProcess !== null,
            websocketConnections: this.wsConnections.size,
            activeSubscriptions: this.subscriptions.size,
            connections: Array.from(this.wsConnections.entries()).map(([clientId, ws]) => ({
                clientId,
                readyState: ws.readyState,
                subscriptions: Array.from(this.subscriptions.values())
                    .filter(sub => sub.clientId === clientId).length
            }))
        };
    }
    
    /**
     * Shutdown the bridge
     */
    async shutdown() {
        logger.info('Shutting down PolygonBridge...');
        
        try {
            // Close all WebSocket connections
            for (const [clientId, ws] of this.wsConnections) {
                ws.close();
            }
            this.wsConnections.clear();
            
            // Clear subscriptions
            this.subscriptions.clear();
            
            // Stop server if we started it
            if (this.serverProcess) {
                logger.info('Stopping FastAPI server...');
                this.serverProcess.kill();
                this.serverProcess = null;
            }
            
            // Remove event listeners
            if (this.ipcHandler) {
                this.ipcHandler.off('data-request', this.handleDataRequest);
                this.ipcHandler.off('data-subscribe', this.handleDataSubscribe);
                this.ipcHandler.off('data-unsubscribe', this.handleDataUnsubscribe);
            }
            
            this.initialized = false;
            logger.info('PolygonBridge shutdown complete');
            
        } catch (error) {
            logger.error('Error during shutdown:', error);
        }
    }
}

module.exports = PolygonBridge;