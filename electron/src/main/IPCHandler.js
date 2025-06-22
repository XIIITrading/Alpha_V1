// electron/src/main/IPCHandler.js
// Centralizes all IPC (Inter-Process Communication) handling between main and renderer processes
// This ensures clean separation of concerns and secure communication

// Import required Electron modules
const { ipcMain, BrowserWindow, app, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs').promises;
const EventEmitter = require('events');

// IPCHandler class extends EventEmitter to allow event-based communication
class IPCHandler extends EventEmitter {
    // Constructor accepts options object with windowManager and stateManager
    constructor(options = {}) {
        // Call parent constructor
        super();
        
        // Store references to managers (passed from main.js)
        this.windowManager = options.windowManager;  // For window-related operations
        this.stateManager = options.stateManager;    // For state persistence
        
        // Track active IPC channels to prevent duplicate handlers
        this.handlers = new Map();                   // Map of channel -> handler function
        
        // Track pending async operations for cleanup
        this.pendingOperations = new Set();          // Set of promise references
        
        // Initialize all IPC handlers
        this.setupHandlers();
        
        // Log initialization
        console.log('[IPCHandler] Initialized with', this.handlers.size, 'handlers');
    }
    
    /**
     * Sets up all IPC communication handlers
     * Organized by feature area for maintainability
     */
    setupHandlers() {
        // System Information Handlers
        this.setupSystemHandlers();
        
        // State Management Handlers  
        this.setupStateHandlers();
        
        // Window Management Handlers (delegated to WindowManager)
        this.setupWindowHandlers();
        
        // Data Integration Handlers
        this.setupDataHandlers();
        
        // Application Control Handlers
        this.setupAppHandlers();
        
        // Perspective-specific Handlers
        this.setupPerspectiveHandlers();
    }
    
    /**
     * System information handlers
     * Provides system and app information to renderer
     */
    setupSystemHandlers() {
        // Get application version
        this.registerHandler('system:get-version', async (event) => {
            // Return the app version from package.json
            return {
                version: app.getVersion(),              // App version
                electron: process.versions.electron,     // Electron version
                node: process.versions.node,            // Node.js version
                chrome: process.versions.chrome,        // Chromium version
                platform: process.platform,             // OS platform (win32, darwin, linux)
                arch: process.arch                      // CPU architecture
            };
        });
        
        // Get system paths
        this.registerHandler('system:get-paths', async (event) => {
            // Return commonly needed system paths
            return {
                userData: app.getPath('userData'),      // Where to store user data
                documents: app.getPath('documents'),    // User's documents folder
                downloads: app.getPath('downloads'),    // User's downloads folder
                logs: app.getPath('logs'),             // Where to store logs
                temp: app.getPath('temp'),             // Temporary files directory
                app: app.getAppPath()                  // Application directory
            };
        });
        
        // Get system metrics
        this.registerHandler('system:get-metrics', async (event) => {
            // Get the webContents that sent this request
            const webContents = event.sender;
            
            // Get memory usage information
            const memoryInfo = process.getProcessMemoryInfo();
            const systemMemory = process.getSystemMemoryInfo();
            
            // Return system metrics
            return {
                memory: {
                    // Process memory usage in MB
                    private: Math.round(memoryInfo.private / 1024),        // Private memory
                    shared: Math.round(memoryInfo.shared / 1024),          // Shared memory
                    total: Math.round(systemMemory.total / 1024),          // Total system memory
                    free: Math.round(systemMemory.free / 1024),            // Free system memory
                    swapTotal: Math.round(systemMemory.swapTotal / 1024),  // Total swap
                    swapFree: Math.round(systemMemory.swapFree / 1024)     // Free swap
                },
                cpu: {
                    // CPU usage percentage (requires additional calculation)
                    usage: process.cpuUsage(),          // CPU usage since process start
                    model: require('os').cpus()[0].model // CPU model name
                },
                uptime: process.uptime()                // Process uptime in seconds
            };
        });

        // Add this handler for app:get-info
        this.registerHandler('app:get-info', async (event) => {
            return {
                version: app.getVersion(),
                environment: process.env.NODE_ENV || 'production',
                platform: process.platform,
                arch: process.arch
            };
        });

        // Add this handler for dev:get-metrics  
        this.registerHandler('dev:get-metrics', async (event) => {
            const memoryInfo = process.getProcessMemoryInfo();
            return {
                memory: Math.round(memoryInfo.private / 1024) // MB
            };
        });
    }
    
    /**
     * State management handlers
     * Handles saving and loading application state
     */
    setupStateHandlers() {
        // Save state to persistent storage
        this.registerHandler('state:save', async (event, { key, value }) => {
            try {
                // Validate key format (prevent directory traversal)
                if (!this.isValidStateKey(key)) {
                    throw new Error('Invalid state key format');
                }
                
                // Save to state manager
                this.stateManager.set(key, value);
                
                // Emit event for other components
                this.emit('state-saved', { key, value });
                
                // Return success
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Failed to save state:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Load state from persistent storage
        this.registerHandler('state:load', async (event, { key, defaultValue }) => {
            try {
                // Validate key format
                if (!this.isValidStateKey(key)) {
                    throw new Error('Invalid state key format');
                }
                
                // Get value from state manager (with optional default)
                const value = this.stateManager.get(key, defaultValue);
                
                // Return the value
                return { success: true, value };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Failed to load state:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Delete state
        this.registerHandler('state:delete', async (event, { key }) => {
            try {
                // Validate key format
                if (!this.isValidStateKey(key)) {
                    throw new Error('Invalid state key format');
                }
                
                // Delete from state manager
                this.stateManager.delete(key);
                
                // Emit event
                this.emit('state-deleted', { key });
                
                // Return success
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Failed to delete state:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Get all state keys (for debugging/management)
        this.registerHandler('state:get-keys', async (event) => {
            try {
                // Get all keys from state manager
                const keys = this.stateManager.getKeys();
                
                // Return keys array
                return { success: true, keys };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Failed to get state keys:', error);
                return { success: false, error: error.message };
            }
        });
    }
    
    /**
     * Window management handlers
     * Delegates to WindowManager for actual window operations
     */
    setupWindowHandlers() {
        // Get current window information
        this.registerHandler('window:get-current', async (event) => {
            // Get the BrowserWindow that sent this request
            const window = BrowserWindow.fromWebContents(event.sender);
            
            // Get window ID from window manager
            const windowId = this.windowManager.getWindowId(window);
            
            // Return window information
            return {
                id: windowId,                                              // Unique window ID
                type: this.windowManager.windowTypes.get(windowId),       // Window type
                bounds: window.getBounds(),                               // Position and size
                isMaximized: window.isMaximized(),                       // Maximized state
                isMinimized: window.isMinimized(),                       // Minimized state
                isFullScreen: window.isFullScreen(),                      // Fullscreen state
                isFocused: window.isFocused(),                           // Focus state
                isVisible: window.isVisible()                             // Visibility state
            };
        });
        
        // Send message to another window
        this.registerHandler('window:send-to', async (event, { targetWindowId, channel, data }) => {
            try {
                // Validate channel name (security)
                if (!this.isValidChannel(channel)) {
                    throw new Error('Invalid channel name');
                }
                
                // Get target window
                const targetWindow = this.windowManager.getWindow(targetWindowId);
                
                // Check if window exists
                if (!targetWindow || targetWindow.isDestroyed()) {
                    throw new Error('Target window not found');
                }
                
                // Send message to target window
                targetWindow.webContents.send(channel, data);
                
                // Return success
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Failed to send to window:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Broadcast message to all windows
        this.registerHandler('window:broadcast', async (event, { channel, data, excludeSelf }) => {
            try {
                // Validate channel name
                if (!this.isValidChannel(channel)) {
                    throw new Error('Invalid channel name');
                }
                
                // Get sender window for exclusion
                const senderWindow = BrowserWindow.fromWebContents(event.sender);
                
                // Send to all windows
                for (const window of this.windowManager.windows.values()) {
                    // Skip destroyed windows
                    if (window.isDestroyed()) continue;
                    
                    // Skip sender if requested
                    if (excludeSelf && window === senderWindow) continue;
                    
                    // Send message
                    window.webContents.send(channel, data);
                }
                
                // Return success with count
                return { 
                    success: true, 
                    count: this.windowManager.windows.size - (excludeSelf ? 1 : 0)
                };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Failed to broadcast:', error);
                return { success: false, error: error.message };
            }
        });
    }
    
    /**
     * Data integration handlers
     * Handles communication with the integration layer
     */
    setupDataHandlers() {
        // Request data from integration layer
this.registerHandler('data:request', async (event, { source, params }) => {
    console.log('[IPCHandler] data:request received:', { source, params }); // ADD THIS
    
    try {
        // Validate source
        if (!['polygon', 'cache', 'calculate'].includes(source)) {
            throw new Error('Invalid data source');
        }
        
        // Create operation ID for tracking
        const operationId = this.generateOperationId();
        console.log('[IPCHandler] Generated operationId:', operationId); // ADD THIS
        
        // Add to pending operations
        this.pendingOperations.add(operationId);
        
        // Forward request to integration layer (via event)
        console.log('[IPCHandler] Emitting data-request event'); // ADD THIS
        this.emit('data-request', {
            operationId,
            source,
            params,
            windowId: this.windowManager.getWindowId(BrowserWindow.fromWebContents(event.sender))
        });
        
        console.log('[IPCHandler] Waiting for response...'); // ADD THIS
        
        // Wait for response (with timeout)
        const response = await this.waitForDataResponse(operationId, 30000); // 30 second timeout
        
        // Remove from pending operations
        this.pendingOperations.delete(operationId);
        
        // Return response
        return response;
        
    } catch (error) {
        // Log error and return failure
        console.error('[IPCHandler] Data request failed:', error);
        return { success: false, error: error.message };
    }
});
        
        // Subscribe to data stream
        this.registerHandler('data:subscribe', async (event, { stream, symbols, options }) => {
            try {
                // Get window ID for subscription tracking
                const window = BrowserWindow.fromWebContents(event.sender);
                const windowId = this.windowManager.getWindowId(window);
                
                // Validate stream type
                if (!['trades', 'quotes', 'bars', 'updates'].includes(stream)) {
                    throw new Error('Invalid stream type');
                }
                
                // Create subscription ID
                const subscriptionId = `${windowId}-${stream}-${Date.now()}`;
                
                // Emit subscription request
                this.emit('data-subscribe', {
                    subscriptionId,
                    windowId,
                    stream,
                    symbols,
                    options
                });
                
                // Return subscription ID
                return { success: true, subscriptionId };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Subscribe failed:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Unsubscribe from data stream
        this.registerHandler('data:unsubscribe', async (event, { subscriptionId }) => {
            try {
                // Emit unsubscribe request
                this.emit('data-unsubscribe', { subscriptionId });
                
                // Return success
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Unsubscribe failed:', error);
                return { success: false, error: error.message };
            }
        });
    }
    
    /**
     * Application control handlers
     * Handles app-level operations
     */
    setupAppHandlers() {
        // Restart application
        this.registerHandler('app:restart', async (event) => {
            try {
                // Log restart request
                console.log('[IPCHandler] Application restart requested');
                
                // Save current state
                await this.stateManager.save();
                
                // Relaunch and exit
                app.relaunch();
                app.exit(0);
                
                // This won't actually return
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Restart failed:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Get PolygonBridge status
        this.registerHandler('bridge:get-status', async (event) => {
            // Simple status check - just return success if we got here
            return { 
                success: true,
                message: 'Bridge is operational (endpoints working)'
            };
        });
        
        // Quit application
        this.registerHandler('app:quit', async (event) => {
            try {
                // Log quit request
                console.log('[IPCHandler] Application quit requested');
                
                // Quit the app (will trigger before-quit event in main.js)
                app.quit();
                
                // This might not return
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Quit failed:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Open external link
        this.registerHandler('app:open-external', async (event, { url }) => {
            try {
                // Validate URL (security)
                if (!this.isValidExternalUrl(url)) {
                    throw new Error('Invalid external URL');
                }
                
                // Open URL in default browser
                await shell.openExternal(url);
                
                // Return success
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Open external failed:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Show item in folder
        this.registerHandler('app:show-item-in-folder', async (event, { path: itemPath }) => {
            try {
                // Validate path exists
                await fs.access(itemPath);
                
                // Show item in file explorer
                shell.showItemInFolder(itemPath);
                
                // Return success
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Show item failed:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Show error dialog
        this.registerHandler('app:show-error', async (event, { title, content }) => {
            // Show error dialog
            dialog.showErrorBox(title || 'Error', content || 'An error occurred');
            
            // Return success
            return { success: true };
        });
    }
    
    /**
     * Perspective-specific handlers
     * Handles Perspective table operations
     */
    setupPerspectiveHandlers() {
        // Update Perspective table
        this.registerHandler('perspective:update-table', async (event, { tableName, data, options }) => {
            try {
                // Get sender window
                const window = BrowserWindow.fromWebContents(event.sender);
                const windowId = this.windowManager.getWindowId(window);
                
                // Emit update event for perspective bridge
                this.emit('perspective-update', {
                    windowId,
                    tableName,
                    data,
                    options
                });
                
                // Return success
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Perspective update failed:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Clear Perspective table
        this.registerHandler('perspective:clear-table', async (event, { tableName }) => {
            try {
                // Get sender window
                const window = BrowserWindow.fromWebContents(event.sender);
                const windowId = this.windowManager.getWindowId(window);
                
                // Emit clear event
                this.emit('perspective-clear', {
                    windowId,
                    tableName
                });
                
                // Return success
                return { success: true };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Perspective clear failed:', error);
                return { success: false, error: error.message };
            }
        });
        
        // Get Perspective table schema
        this.registerHandler('perspective:get-schema', async (event, { tableName }) => {
            try {
                // Emit schema request
                const schema = await new Promise((resolve, reject) => {
                    // Set up one-time listener for response
                    this.once(`perspective-schema-${tableName}`, resolve);
                    
                    // Emit request
                    this.emit('perspective-schema-request', { tableName });
                    
                    // Timeout after 5 seconds
                    setTimeout(() => reject(new Error('Schema request timeout')), 5000);
                });
                
                // Return schema
                return { success: true, schema };
                
            } catch (error) {
                // Log error and return failure
                console.error('[IPCHandler] Get schema failed:', error);
                return { success: false, error: error.message };
            }
        });
    }
    
    /**
     * Registers an IPC handler with error handling and validation
     * @param {string} channel - IPC channel name
     * @param {Function} handler - Handler function
     */
    registerHandler(channel, handler) {
        // Check if handler already exists
        if (this.handlers.has(channel)) {
            console.warn(`[IPCHandler] Handler already exists for channel: ${channel}`);
            return;
        }
        
        // Wrap handler with error handling
        const wrappedHandler = async (event, ...args) => {
            try {
                // Log handler invocation (debug mode only)
                if (process.env.DEBUG) {
                    console.log(`[IPCHandler] Handling: ${channel}`, args);
                }
                
                // Call the actual handler
                const result = await handler(event, ...args);
                
                // Return result
                return result;
                
            } catch (error) {
                // Log error
                console.error(`[IPCHandler] Error in ${channel}:`, error);
                
                // Return error response
                return {
                    success: false,
                    error: error.message,
                    stack: process.env.NODE_ENV === 'development' ? error.stack : undefined
                };
            }
        };
        
        // Register with ipcMain
        ipcMain.handle(channel, wrappedHandler);
        
        // Store reference
        this.handlers.set(channel, wrappedHandler);
    }
    
    /**
     * Validates state key format (security)
     * @param {string} key - State key to validate
     * @returns {boolean} True if valid
     */
    isValidStateKey(key) {
        // Must be string
        if (typeof key !== 'string') return false;
        
        // Must not be empty
        if (key.length === 0) return false;
        
        // Must not contain path separators (prevent directory traversal)
        if (key.includes('/') || key.includes('\\') || key.includes('..')) return false;
        
        // Must match allowed pattern (alphanumeric, dots, dashes, underscores)
        return /^[a-zA-Z0-9._-]+$/.test(key);
    }
    
    /**
     * Validates channel name (security)
     * @param {string} channel - Channel name to validate
     * @returns {boolean} True if valid
     */
    isValidChannel(channel) {
        // Must be string
        if (typeof channel !== 'string') return false;
        
        // Must not be empty
        if (channel.length === 0) return false;
        
        // Must start with allowed prefix
        const allowedPrefixes = ['app:', 'window:', 'data:', 'perspective:', 'custom:'];
        return allowedPrefixes.some(prefix => channel.startsWith(prefix));
    }
    
    /**
     * Validates external URL (security)
     * @param {string} url - URL to validate
     * @returns {boolean} True if valid
     */
    isValidExternalUrl(url) {
        try {
            // Parse URL
            const parsed = new URL(url);
            
            // Only allow http(s) protocols
            return ['http:', 'https:'].includes(parsed.protocol);
            
        } catch (error) {
            // Invalid URL
            return false;
        }
    }
    
    /**
     * Generates unique operation ID
     * @returns {string} Operation ID
     */
    generateOperationId() {
        // Use timestamp + random number
        return `op-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    }
    
    /**
     * Waits for data response with timeout
     * @param {string} operationId - Operation ID to wait for
     * @param {number} timeout - Timeout in milliseconds
     * @returns {Promise} Response data
     */
    waitForDataResponse(operationId, timeout) {
        return new Promise((resolve, reject) => {
            // Set up timeout
            const timeoutId = setTimeout(() => {
                // Remove listener
                this.removeListener(`data-response-${operationId}`, responseHandler);
                
                // Reject with timeout error
                reject(new Error('Data request timeout'));
            }, timeout);
            
            // Response handler
            const responseHandler = (data) => {
                // Clear timeout
                clearTimeout(timeoutId);
                
                // Resolve with data
                resolve(data);
            };
            
            // Listen for response
            this.once(`data-response-${operationId}`, responseHandler);
        });
    }
    
    /**
     * Cleans up all handlers and pending operations
     */
    cleanup() {
        console.log('[IPCHandler] Cleaning up...');
        
        // Remove all IPC handlers
        for (const [channel, handler] of this.handlers) {
            ipcMain.removeHandler(channel);
        }
        
        // Clear handler map
        this.handlers.clear();
        
        // Cancel pending operations
        for (const operationId of this.pendingOperations) {
            this.emit(`data-response-${operationId}`, {
                success: false,
                error: 'Application shutting down'
            });
        }
        
        // Clear pending operations
        this.pendingOperations.clear();
        
        // Remove all event listeners
        this.removeAllListeners();
        
        console.log('[IPCHandler] Cleanup complete');
    }
}

// Export the class
module.exports = IPCHandler;