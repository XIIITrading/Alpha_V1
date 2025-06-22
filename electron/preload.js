/**
 * Preload Script - Secure Bridge between Main and Renderer Processes
 * 
 * This script runs in a special context that has access to both:
 * - Node.js APIs (like require, process)
 * - Browser/DOM APIs (like window, document)
 * 
 * Its primary job is to safely expose specific functionality to the renderer
 * without giving it full Node.js access (which would be a security risk)
 */

const { contextBridge, ipcRenderer } = require('electron');

/**
 * contextBridge.exposeInMainWorld creates a secure bridge
 * It adds an object to the renderer's 'window' object
 * This is the ONLY safe way to expose functionality to the renderer
 */
contextBridge.exposeInMainWorld('electronAPI', {
    
    // ============= Generic Invoke Method =============
    /**
     * Generic invoke method for IPC calls
     * Useful for calling handlers not explicitly defined below
     */
    invoke: (channel, ...args) => {
        return ipcRenderer.invoke(channel, ...args);
    },
    
    // ============= Window Management =============
    window: {
        /**
         * Create a new window of a specific type
         * @param {string} type - Window type: 'scanner', 'positions', 'settings'
         * @param {object} options - Window-specific options
         * @returns {Promise<string>} - Window ID of created window
         */
        create: (type, options = {}) => {
            // ipcRenderer.invoke sends a message and waits for a response
            return ipcRenderer.invoke('window:create', { type, options });
        },

        /**
         * Get information about the current window
         * @returns {Promise<object>} - Window info (id, type, bounds, etc.)
         */
        getCurrentInfo: () => {
            return ipcRenderer.invoke('window:get-current');
        },

        /**
         * Send message to a specific window
         * @param {string} targetWindowId - ID of target window
         * @param {string} channel - Message channel name
         * @param {*} data - Data to send
         */
        sendTo: (targetWindowId, channel, data) => {
            return ipcRenderer.invoke('window:send-to', { 
                targetWindowId, 
                channel, 
                data 
            });
        },

        /**
         * Close a specific window or current if no ID provided
         * @param {string} [windowId] - Optional window ID
         */
        close: (windowId) => {
            return ipcRenderer.invoke('window:close', { windowId });
        }
    },

    // ============= State Management =============
    state: {
        /**
         * Save data to persistent storage
         * @param {string} key - Dot-notation path (e.g., 'settings.theme')
         * @param {*} value - Value to store
         */
        save: (key, value) => {
            return ipcRenderer.invoke('state:save', { key, value });
        },

        /**
         * Load data from persistent storage
         * @param {string} key - Dot-notation path
         * @param {*} defaultValue - Default if key doesn't exist
         * @returns {Promise<*>} - Stored value or default
         */
        load: (key, defaultValue = null) => {
            return ipcRenderer.invoke('state:load', { key, defaultValue });
        },

        /**
         * Delete data from persistent storage
         * @param {string} key - Dot-notation path
         */
        delete: (key) => {
            return ipcRenderer.invoke('state:delete', { key });
        },

        /**
         * Listen for state changes from other windows
         * @param {function} callback - Called when state changes
         * @returns {function} - Call to remove listener
         */
        onChange: (callback) => {
            // This creates a wrapper function that extracts just the data
            const subscription = (event, data) => callback(data);
            
            // Add the listener
            ipcRenderer.on('state:changed', subscription);
            
            // Return a function to remove the listener
            return () => {
                ipcRenderer.removeListener('state:changed', subscription);
            };
        }
    },

    // ============= Data Operations =============
    data: {
        /**
         * Request data from integration layer
         * @param {object} params - Full request parameters including source
         * @returns {Promise<*>} - Requested data
         */
        request: (params) => {
            return ipcRenderer.invoke('data:request', params);
        },

        /**
         * Subscribe to real-time data stream
         * @param {object} params - Full subscription parameters
         * @returns {Promise<object>} - Subscription info with ID
         */
        subscribe: (params) => {
            return ipcRenderer.invoke('data:subscribe', params);
        },

        /**
         * Unsubscribe from data stream
         * @param {object} params - Unsubscribe parameters with subscriptionId
         */
        unsubscribe: (params) => {
            return ipcRenderer.invoke('data:unsubscribe', params);
        },

        /**
         * Listen for real-time data updates
         * @param {function} callback - Called with data updates
         * @returns {function} - Call to remove listener
         */
        onUpdate: (callback) => {
            const subscription = (event, data) => callback(data);
            ipcRenderer.on('data:update', subscription);
            return () => {
                ipcRenderer.removeListener('data:update', subscription);
            };
        }
    },

    // ============= Market Data Operations =============
    market: {
        /**
         * Listen for real-time market data
         * @param {function} callback - Called with market data
         * @returns {function} - Call to remove listener
         */
        onData: (callback) => {
            const subscription = (event, data) => callback(data);
            ipcRenderer.on('market-data', subscription);
            return () => {
                ipcRenderer.removeListener('market-data', subscription);
            };
        },

        /**
         * Listen for connection errors
         * @param {function} callback - Called with error info
         * @returns {function} - Call to remove listener
         */
        onConnectionError: (callback) => {
            const subscription = (event, error) => callback(error);
            ipcRenderer.on('connection-error', subscription);
            return () => {
                ipcRenderer.removeListener('connection-error', subscription);
            };
        }
    },

    // ============= Bridge Operations =============
    bridge: {
        /**
         * Get PolygonBridge status
         * @returns {Promise<object>} - Bridge connection status
         */
        getStatus: () => {
            return ipcRenderer.invoke('bridge:get-status');
        }
    },

    // ============= Perspective Operations =============
    perspective: {
        /**
         * Send data to Perspective tables
         * This is optimized for high-frequency updates
         * @param {string} tableName - Target table name
         * @param {ArrayBuffer|object} data - Data to send (can be binary)
         */
        update: (tableName, data) => {
            // For performance, we use send instead of invoke (fire-and-forget)
            ipcRenderer.send('perspective:update', { tableName, data });
        },

        /**
         * Create a new Perspective table
         * @param {string} tableName - Unique table name
         * @param {object} schema - Table schema definition
         * @param {object} options - Table options
         */
        createTable: (tableName, schema, options = {}) => {
            return ipcRenderer.invoke('perspective:create-table', { 
                tableName, 
                schema, 
                options 
            });
        },

        /**
         * Update a Perspective table (with invoke for confirmation)
         * @param {string} tableName - Target table name
         * @param {object} data - Data to update
         * @param {object} options - Update options
         */
        updateTable: (tableName, data, options = {}) => {
            return ipcRenderer.invoke('perspective:update-table', { 
                tableName, 
                data, 
                options 
            });
        },

        /**
         * Clear a Perspective table
         * @param {string} tableName - Table to clear
         */
        clearTable: (tableName) => {
            return ipcRenderer.invoke('perspective:clear-table', { tableName });
        },

        /**
         * Get table schema
         * @param {string} tableName - Table name
         * @returns {Promise<object>} - Table schema
         */
        getSchema: (tableName) => {
            return ipcRenderer.invoke('perspective:get-schema', { tableName });
        },

        /**
         * Get table metadata
         * @param {string} tableName - Table name
         * @returns {Promise<object>} - Table info (schema, size, etc.)
         */
        getTableInfo: (tableName) => {
            return ipcRenderer.invoke('perspective:table-info', { tableName });
        }
    },

    // ============= Application Control =============
    app: {
        /**
         * Get application information
         * @returns {Promise<object>} - App version, environment, etc.
         */
        getInfo: () => {
            return ipcRenderer.invoke('app:get-info');
        },

        /**
         * Restart the application
         * @returns {Promise<object>} - Success status
         */
        restart: () => {
            return ipcRenderer.invoke('app:restart');
        },

        /**
         * Quit the application
         * @returns {Promise<object>} - Success status
         */
        quit: () => {
            return ipcRenderer.invoke('app:quit');
        },

        /**
         * Open external URL in default browser
         * @param {string} url - URL to open
         * @returns {Promise<object>} - Success status
         */
        openExternal: (url) => {
            return ipcRenderer.invoke('app:open-external', { url });
        },

        /**
         * Show item in file explorer/finder
         * @param {string} path - Path to show
         * @returns {Promise<object>} - Success status
         */
        showItemInFolder: (path) => {
            return ipcRenderer.invoke('app:show-item-in-folder', { path });
        },

        /**
         * Show error dialog
         * @param {string} title - Dialog title
         * @param {string} content - Error message
         * @returns {Promise<object>} - Success status
         */
        showError: (title, content) => {
            return ipcRenderer.invoke('app:show-error', { title, content });
        },

        /**
         * Listen for app-wide events
         * @param {string} eventName - Event to listen for
         * @param {function} callback - Event handler
         * @returns {function} - Call to remove listener
         */
        on: (eventName, callback) => {
            const subscription = (event, data) => callback(data);
            ipcRenderer.on(`app:${eventName}`, subscription);
            return () => {
                ipcRenderer.removeListener(`app:${eventName}`, subscription);
            };
        },

        /**
         * Show a native dialog
         * @param {object} options - Dialog options
         * @returns {Promise<object>} - Dialog result
         */
        showDialog: (options) => {
            return ipcRenderer.invoke('app:show-dialog', options);
        }
    },

    // ============= System Operations =============
    system: {
        /**
         * Get system version information
         * @returns {Promise<object>} - Version info
         */
        getVersion: () => {
            return ipcRenderer.invoke('system:get-version');
        },

        /**
         * Get system paths
         * @returns {Promise<object>} - System paths
         */
        getPaths: () => {
            return ipcRenderer.invoke('system:get-paths');
        },

        /**
         * Get system metrics
         * @returns {Promise<object>} - CPU, memory, etc.
         */
        getMetrics: () => {
            return ipcRenderer.invoke('system:get-metrics');
        }
    },

    // ============= Development Tools =============
    dev: {
        /**
         * Log to main process console (useful for debugging)
         * @param {string} level - Log level (info, warn, error)
         * @param {string} message - Log message
         * @param {*} data - Additional data
         */
        log: (level, message, data) => {
            ipcRenderer.send('dev:log', { level, message, data });
        },

        /**
         * Get performance metrics
         * @returns {Promise<object>} - CPU, memory, etc.
         */
        getMetrics: () => {
            return ipcRenderer.invoke('dev:get-metrics');
        }
    },

    // ============= Event Listeners =============
    /**
     * Listen for events from main process
     * @param {string} channel - Channel to listen on
     * @param {function} callback - Event handler
     * @returns {function} - Call to remove listener
     */
    on: (channel, callback) => {
        const subscription = (event, ...args) => callback(...args);
        ipcRenderer.on(channel, subscription);
        return () => {
            ipcRenderer.removeListener(channel, subscription);
        };
    },

    /**
     * One-time event listener
     * @param {string} channel - Channel to listen on
     * @param {function} callback - Event handler
     */
    once: (channel, callback) => {
        ipcRenderer.once(channel, (event, ...args) => callback(...args));
    },

    /**
     * Remove all listeners for a channel
     * @param {string} channel - Channel to clear
     */
    removeAllListeners: (channel) => {
        ipcRenderer.removeAllListeners(channel);
    }
});

/**
 * Also expose a way to check if we're in development mode
 * This is useful for conditional features like dev tools
 */
contextBridge.exposeInMainWorld('isDevelopment', process.env.NODE_ENV === 'development');

/**
 * Expose platform information for platform-specific UI
 */
contextBridge.exposeInMainWorld('platform', {
    name: process.platform, // 'darwin', 'win32', 'linux'
    arch: process.arch,     // 'x64', 'arm64', etc.
    versions: {
        electron: process.versions.electron,
        chrome: process.versions.chrome,
        node: process.versions.node
    }
});

// Log that preload script has loaded successfully
console.log('Preload script loaded successfully');
console.log('Platform:', process.platform);
console.log('Electron:', process.versions.electron);