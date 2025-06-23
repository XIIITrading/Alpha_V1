// electron/src/main/WindowManager.js
// Manages creation, tracking, and lifecycle of all application windows
// Supports multiple window types with different configurations

const { BrowserWindow, screen, ipcMain } = require('electron');
const path = require('path');
const EventEmitter = require('events');

class WindowManager extends EventEmitter {
    constructor(options = {}) {
        super();
        
        // Store configuration options
        this.stateManager = options.stateManager;           // For saving/loading window states
        this.windowConfig = options.windowConfig;           // Window type configurations
        this.isDevelopment = options.isDevelopment || false; // Development mode flag
        
        // Track all active windows
        this.windows = new Map();        // Map of windowId -> BrowserWindow instance
        this.windowTypes = new Map();    // Map of windowId -> window type
        this.windowGroups = new Map();   // Map of groupId -> Set of windowIds
        
        // Window ID counter (ensures unique IDs)
        this.nextWindowId = 1;
        
        // Default window options (can be overridden per window type)
        this.defaultOptions = {
            width: 1200,
            height: 800,
            minWidth: 800,
            minHeight: 600,
            frame: true,                           // Native window frame
            show: false,                           // Don't show until ready
            backgroundColor: '#1e1e1e',            // Dark background
            titleBarStyle: 'default',              // Platform-specific title bar
            webPreferences: {
                nodeIntegration: false,            // Security: no direct Node access
                contextIsolation: true,            // Security: isolated context
                preload: path.join(__dirname, '../../preload.js'),
                sandbox: true,                     // Security: sandboxed renderer
                webSecurity: true,                 // Security: enforce same-origin
                allowRunningInsecureContent: false // Security: no mixed content
            }
        };
        
        // Set up IPC handlers for window management
        this.setupIPC();
        
        console.log('[WindowManager] Initialized');
    }
    
    /**
     * Creates a new window of the specified type
     * @param {string} windowType - Type of window (main, scanner, positions, etc.)
     * @param {Object} customOptions - Custom options to override defaults
     * @returns {Promise<BrowserWindow>} The created window
     */
    async createWindow(windowType = 'main', customOptions = {}) {
        console.log(`[WindowManager] Creating window: ${windowType}`);
        
        try {
            // Get window-type specific configuration
            const typeConfig = this.windowConfig[windowType] || {};
            
            // Generate unique window ID
            const windowId = `${windowType}-${this.nextWindowId++}`;
            
            // Merge options: defaults -> type config -> custom options -> saved state
            const savedState = this.loadWindowState(windowId);
            const windowOptions = {
                ...this.defaultOptions,
                ...typeConfig.options,
                ...customOptions,
                ...savedState,
                title: customOptions.title || typeConfig.title || 'Alpha V1 Trading'
            };
            
            // Ensure window appears on screen (handles multi-monitor setups)
            this.ensureWindowOnScreen(windowOptions);
            
            // Create the browser window
            const window = new BrowserWindow(windowOptions);
            
            // Store window references
            this.windows.set(windowId, window);
            this.windowTypes.set(windowId, windowType);
            
            // Add to window group if specified
            if (typeConfig.group) {
                this.addToGroup(windowId, typeConfig.group);
            }
            
            // Set up window event handlers
            this.setupWindowEvents(window, windowId);
            
            // Load the appropriate content
            await this.loadWindowContent(window, windowType, typeConfig);
            
            // Show window when ready (prevents visual flash)
            window.once('ready-to-show', () => {
                console.log(`[WindowManager] Window ready: ${windowId}`);
                
                // Apply saved window state if available
                if (savedState.isMaximized) {
                    window.maximize();
                } else if (savedState.isFullScreen) {
                    window.setFullScreen(true);
                }
                
                // Show the window
                window.show();
                
                // Focus window if it's the main window or explicitly requested
                if (windowType === 'main' || customOptions.focus !== false) {
                    window.focus();
                }
                
                // Open DevTools in development mode
                if (this.isDevelopment && typeConfig.devTools !== false) {
                    window.webContents.openDevTools();
                }
            });
            
            // Emit window created event
            this.emit('window-created', { windowId, windowType, window });
            
            return window;
            
        } catch (error) {
            console.error(`[WindowManager] Failed to create window:`, error);
            throw error;
        }
    }
    
    /**
     * Loads content into the window based on type
     * @param {BrowserWindow} window - The window to load content into
     * @param {string} windowType - Type of window
     * @param {Object} typeConfig - Window type configuration
     */
    async loadWindowContent(window, windowType, typeConfig) {
        // Determine the HTML file to load
        const htmlFile = typeConfig.html || 'index.html';
        const htmlPath = path.join(__dirname, '../renderer', htmlFile);
        
        // Load the HTML file
        await window.loadFile(htmlPath);
        
        // Send initial configuration to renderer
        window.webContents.send('window:config', {
            windowType,
            config: typeConfig.renderer || {},
            isDevelopment: this.isDevelopment
        });
    }
    
    /**
     * Sets up event handlers for a window
     * @param {BrowserWindow} window - The window to set up events for
     * @param {string} windowId - Unique window identifier
     */
    setupWindowEvents(window, windowId) {
        // Handle window close
        window.on('close', (event) => {
            console.log(`[WindowManager] Window closing: ${windowId}`);
            
            // Save window state before closing
            this.saveWindowState(windowId);
            
            // Check if this is the last window of a required type
            const windowType = this.windowTypes.get(windowId);
            if (windowType === 'main' && this.getWindowsByType('main').length === 1) {
                // Emit event to allow app to decide whether to quit
                this.emit('last-main-window-closing', { window, windowId });
            }
        });
        
        // Handle window closed
        window.on('closed', () => {
            console.log(`[WindowManager] Window closed: ${windowId}`);
            
            // Clean up references
            this.windows.delete(windowId);
            this.windowTypes.delete(windowId);
            this.removeFromAllGroups(windowId);
            
            // Emit window closed event
            this.emit('window-closed', { windowId });
        });
        
        // Handle window state changes for state persistence
        const saveStateDebounced = this.debounce(() => {
            this.saveWindowState(windowId);
        }, 1000);
        
        // Track window move/resize
        window.on('moved', saveStateDebounced);
        window.on('resized', saveStateDebounced);
        window.on('maximize', saveStateDebounced);
        window.on('unmaximize', saveStateDebounced);
        window.on('enter-full-screen', saveStateDebounced);
        window.on('leave-full-screen', saveStateDebounced);
        
        // Handle window focus for group management
        window.on('focus', () => {
            this.emit('window-focused', { windowId, window });
            
            // Bring related windows to front if configured
            const group = this.getWindowGroup(windowId);
            if (group && this.windowConfig[this.windowTypes.get(windowId)]?.focusGroup) {
                this.focusWindowGroup(group);
            }
        });
        
        // Handle navigation (security)
        window.webContents.on('will-navigate', (event, url) => {
            // Prevent navigation to external URLs
            if (!url.startsWith('file://')) {
                console.warn(`[WindowManager] Blocked navigation to: ${url}`);
                event.preventDefault();
            }
        });
        
        // Handle new window requests (security)
        window.webContents.setWindowOpenHandler(({ url }) => {
            // Deny all new window requests by default
            console.warn(`[WindowManager] Blocked new window: ${url}`);
            return { action: 'deny' };
        });
    }
    
    /**
     * Gets a window by ID
     * @param {string} windowId - Window identifier
     * @returns {BrowserWindow|null} The window or null if not found
     */
    getWindow(windowId) {
        return this.windows.get(windowId) || null;
    }
    
    /**
     * Gets all windows of a specific type
     * @param {string} windowType - Type of windows to get
     * @returns {Array<BrowserWindow>} Array of windows
     */
    getWindowsByType(windowType) {
        const windows = [];
        for (const [windowId, window] of this.windows) {
            if (this.windowTypes.get(windowId) === windowType) {
                windows.push(window);
            }
        }
        return windows;
    }
    
    /**
     * Gets the count of active windows
     * @returns {number} Number of active windows
     */
    getWindowCount() {
        return this.windows.size;
    }
    
    /**
     * Closes a window by ID
     * @param {string} windowId - Window identifier
     */
    closeWindow(windowId) {
        const window = this.windows.get(windowId);
        if (window && !window.isDestroyed()) {
            window.close();
        }
    }
    
    /**
     * Closes all windows of a specific type
     * @param {string} windowType - Type of windows to close
     */
    closeWindowsByType(windowType) {
        const windows = this.getWindowsByType(windowType);
        windows.forEach(window => {
            if (!window.isDestroyed()) {
                window.close();
            }
        });
    }
    
    /**
     * Closes all windows
     */
    closeAllWindows() {
        for (const window of this.windows.values()) {
            if (!window.isDestroyed()) {
                window.close();
            }
        }
    }
    
    /**
     * Adds a window to a group
     * @param {string} windowId - Window identifier
     * @param {string} groupId - Group identifier
     */
    addToGroup(windowId, groupId) {
        if (!this.windowGroups.has(groupId)) {
            this.windowGroups.set(groupId, new Set());
        }
        this.windowGroups.get(groupId).add(windowId);
    }
    
    /**
     * Removes a window from all groups
     * @param {string} windowId - Window identifier
     */
    removeFromAllGroups(windowId) {
        for (const group of this.windowGroups.values()) {
            group.delete(windowId);
        }
    }
    
    /**
     * Gets the group a window belongs to
     * @param {string} windowId - Window identifier
     * @returns {string|null} Group ID or null
     */
    getWindowGroup(windowId) {
        for (const [groupId, windowIds] of this.windowGroups) {
            if (windowIds.has(windowId)) {
                return groupId;
            }
        }
        return null;
    }
    
    /**
     * Focuses all windows in a group
     * @param {string} groupId - Group identifier
     */
    focusWindowGroup(groupId) {
        const windowIds = this.windowGroups.get(groupId);
        if (windowIds) {
            for (const windowId of windowIds) {
                const window = this.windows.get(windowId);
                if (window && !window.isDestroyed()) {
                    window.show();
                }
            }
        }
    }
    
    /**
     * Saves window state to persistent storage
     * @param {string} windowId - Window identifier
     */
    saveWindowState(windowId) {
        const window = this.windows.get(windowId);
        if (!window || window.isDestroyed()) return;
        
        const bounds = window.getBounds();
        const state = {
            x: bounds.x,
            y: bounds.y,
            width: bounds.width,
            height: bounds.height,
            isMaximized: window.isMaximized(),
            isFullScreen: window.isFullScreen()
        };
        
        // Save to state manager
        if (this.stateManager) {
            this.stateManager.set(`windowStates.${windowId}`, state);
        }
    }
    
    /**
     * Loads window state from persistent storage
     * @param {string} windowId - Window identifier
     * @returns {Object} Saved window state or empty object
     */
    loadWindowState(windowId) {
        if (!this.stateManager) return {};
        
        return this.stateManager.get(`windowStates.${windowId}`, {});
    }
    
    /**
     * Saves all window states
     */
    saveAllWindowStates() {
        for (const windowId of this.windows.keys()) {
            this.saveWindowState(windowId);
        }
    }
    
    /**
     * Ensures window appears on screen (handles multi-monitor)
     * @param {Object} windowOptions - Window options object
     */
    ensureWindowOnScreen(windowOptions) {
        const displays = screen.getAllDisplays();
        const primaryDisplay = screen.getPrimaryDisplay();
        
        console.log('[WindowManager] Ensuring window on screen:', {
            passedOptions: {
                x: windowOptions.x,
                y: windowOptions.y,
                width: windowOptions.width,
                height: windowOptions.height
            },
            displays: displays.length,
            primaryDisplay: primaryDisplay.bounds
        });
        
        // Validate dimensions first
        const maxWidth = primaryDisplay.workAreaSize.width;
        const maxHeight = primaryDisplay.workAreaSize.height;
        
        // Ensure reasonable dimensions
        if (windowOptions.width > maxWidth || windowOptions.width < 100) {
            console.log(`[WindowManager] Adjusting width from ${windowOptions.width} to 1600`);
            windowOptions.width = Math.min(1600, maxWidth);
        }
        if (windowOptions.height > maxHeight || windowOptions.height < 100) {
            console.log(`[WindowManager] Adjusting height from ${windowOptions.height} to 900`);
            windowOptions.height = Math.min(900, maxHeight);
        }
        
        // Check if saved position is still valid
        if (windowOptions.x !== undefined && windowOptions.y !== undefined) {
            const windowBounds = {
                x: windowOptions.x,
                y: windowOptions.y,
                width: windowOptions.width,
                height: windowOptions.height
            };
            
            // Check if window is on any display
            let isOnScreen = false;
            for (const display of displays) {
                const bounds = display.bounds;
                // Check if at least 100x100 pixels of the window are visible
                const visibleLeft = Math.max(windowBounds.x, bounds.x);
                const visibleTop = Math.max(windowBounds.y, bounds.y);
                const visibleRight = Math.min(windowBounds.x + windowBounds.width, bounds.x + bounds.width);
                const visibleBottom = Math.min(windowBounds.y + windowBounds.height, bounds.y + bounds.height);
                
                if (visibleRight - visibleLeft >= 100 && visibleBottom - visibleTop >= 100) {
                    isOnScreen = true;
                    break;
                }
            }
            
            // If not on screen, center on primary display
            if (!isOnScreen) {
                console.log('[WindowManager] Window position off-screen, centering');
                delete windowOptions.x;
                delete windowOptions.y;
                windowOptions.center = true;
            }
        } else {
            // No saved position, center on primary display
            console.log('[WindowManager] No saved position, centering window');
            windowOptions.center = true;
        }
    }
    
    /**
     * Sets up IPC handlers for window management
     */
    setupIPC() {
        // Handle window creation requests from renderer
        ipcMain.handle('window:create', async (event, { type, options }) => {
            try {
                const window = await this.createWindow(type, options);
                return { success: true, windowId: this.getWindowId(window) };
            } catch (error) {
                return { success: false, error: error.message };
            }
        });
        
        // Handle window close requests
        ipcMain.handle('window:close', async (event, { windowId }) => {
            this.closeWindow(windowId);
            return { success: true };
        });
        
        // Handle window state queries
        ipcMain.handle('window:get-state', async (event) => {
            const window = BrowserWindow.fromWebContents(event.sender);
            const windowId = this.getWindowId(window);
            
            return {
                windowId,
                windowType: this.windowTypes.get(windowId),
                bounds: window.getBounds(),
                isMaximized: window.isMaximized(),
                isFullScreen: window.isFullScreen(),
                isFocused: window.isFocused()
            };
        });
        
        // Handle window group queries
        ipcMain.handle('window:get-group', async (event) => {
            const window = BrowserWindow.fromWebContents(event.sender);
            const windowId = this.getWindowId(window);
            const groupId = this.getWindowGroup(windowId);
            
            if (groupId) {
                const groupWindows = Array.from(this.windowGroups.get(groupId))
                    .map(id => ({
                        windowId: id,
                        windowType: this.windowTypes.get(id),
                        isFocused: this.windows.get(id)?.isFocused()
                    }));
                
                return { groupId, windows: groupWindows };
            }
            
            return null;
        });
    }
    
    /**
     * Gets window ID from BrowserWindow instance
     * @param {BrowserWindow} window - Browser window instance
     * @returns {string|null} Window ID or null
     */
    getWindowId(window) {
        for (const [windowId, win] of this.windows) {
            if (win === window) {
                return windowId;
            }
        }
        return null;
    }
    
    /**
     * Utility function to debounce frequent events
     * @param {Function} func - Function to debounce
     * @param {number} wait - Wait time in milliseconds
     * @returns {Function} Debounced function
     */
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
}

module.exports = WindowManager;