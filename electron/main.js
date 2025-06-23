// electron/main.js
// This is the main entry point for the Electron application
// It manages the application lifecycle and bootstraps all core systems

// Import Electron modules
const { app, BrowserWindow, ipcMain, Menu, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs');

// Import custom managers and handlers
const WindowManager = require('./src/main/WindowManager');
const IPCHandler = require('./src/main/IPCHandler');
const MenuBuilder = require('./src/main/MenuBuilder');
const StateManager = require('./src/main/StateManager');
const AppUpdater = require('./src/main/AppUpdater');
const PolygonBridge = require('./src/main/PolygonBridge');

// Import configuration files
const appConfig = require('./config/app.config');
const windowConfig = require('./config/window.config');

// Development tools (only in dev mode)
const isDevelopment = process.env.NODE_ENV === 'development';
if (isDevelopment) {
    require('electron-debug')({ showDevTools: true });
}

// Global references to prevent garbage collection
let windowManager = null;  // Manages all application windows
let ipcHandler = null;     // Handles all IPC communication
let stateManager = null;   // Manages persistent application state
let appUpdater = null;     // Handles auto-updates
let polygonBridge = null;  // Manages Polygon server connection

// Single instance lock - ensures only one instance of the app runs
const gotTheLock = app.requestSingleInstanceLock();

// If we didn't get the lock, another instance is running
if (!gotTheLock) {
    app.quit(); // Quit this instance
} else {
    // Handle second instance attempt - focus existing window
    app.on('second-instance', (event, commandLine, workingDirectory) => {
        // If someone tried to run a second instance, focus our main window
        if (windowManager) {
            const mainWindow = windowManager.getWindow('main');
            if (mainWindow) {
                if (mainWindow.isMinimized()) mainWindow.restore();
                mainWindow.focus();
            }
        }
    });
}

// Enable sandbox for all renderers (security best practice)
app.enableSandbox();

// Initialize the application when Electron is ready
app.whenReady().then(async () => {
    console.log('[Main] Application starting...');
    
    try {
        // Initialize state manager first (loads saved preferences)
        stateManager = new StateManager({
            name: 'alpha-v1-state',
            defaults: {
                windowStates: {},      // Saved window positions/sizes
                preferences: {         // User preferences
                    theme: 'dark',
                    autoConnect: true,
                    multiWindow: true
                },
                recentSymbols: [],     // Recently viewed symbols
                layouts: {}            // Saved table layouts
            }
        });
        
        // Initialize window manager with saved state
        windowManager = new WindowManager({
            stateManager: stateManager,
            windowConfig: windowConfig,
            isDevelopment: isDevelopment
        });
        
        // Initialize IPC handler for inter-process communication
        ipcHandler = new IPCHandler({
            windowManager: windowManager,
            stateManager: stateManager
        });

        // Initialize Polygon Bridge
        polygonBridge = new PolygonBridge({
            ipcHandler: ipcHandler,
            autoStartServer: false, // Never auto-start (assume server is running)
            serverUrl: 'http://127.0.0.1:8200',
            wsUrl: 'ws://127.0.0.1:8200'
        });

        // Set up Polygon Bridge event handlers
        polygonBridge.on('ready', () => {
            console.log('[Main] PolygonBridge ready');
        });

        polygonBridge.on('server-exit', ({ code, signal }) => {
            console.error(`[Main] Polygon server exited unexpectedly: ${code} ${signal}`);
        });

        polygonBridge.on('market-data', ({ windowId, subscriptionId, stream, data }) => {
            const window = windowManager.getWindow(windowId);
            if (window && !window.isDestroyed()) {
                window.webContents.send('market-data', {
                    subscriptionId,
                    stream,
                    data
                });
            }
        });

        polygonBridge.on('reconnection-failed', ({ clientId, attempts }) => {
            console.error(`[Main] WebSocket reconnection failed for ${clientId} after ${attempts} attempts`);
            const windowId = clientId.replace('window-', '');
            const window = windowManager.getWindow(windowId);
            if (window && !window.isDestroyed()) {
                window.webContents.send('connection-error', {
                    type: 'websocket',
                    message: 'Lost connection to market data. Please check your connection.'
                });
            }
        });

        // Initialize the bridge
        try {
            await polygonBridge.initialize();
            console.log('[Main] PolygonBridge initialized successfully');
        } catch (error) {
            console.error('[Main] Failed to initialize PolygonBridge:', error);
            if (!isDevelopment) {
                dialog.showErrorBox('Connection Error', 
                    'Failed to connect to market data server. Please ensure the server is running.');
            }
        }
        
        // Set up application menu
        const menuBuilder = new MenuBuilder({
            windowManager: windowManager,
            isDevelopment: isDevelopment
        });
        Menu.setApplicationMenu(menuBuilder.buildMenu());
        
        // Initialize auto-updater (production only)
        if (!isDevelopment && appConfig.common.autoUpdate) {
            appUpdater = new AppUpdater();
            appUpdater.checkForUpdates();
        }
        
        // Get window dimensions and position
        // Note: WindowManager creates IDs like "main-1", so we need to check both
        const windowId = 'main-1'; // First main window
        const width = stateManager.get(`windowStates.${windowId}.width`) || 
                     stateManager.get('windowStates.main.width', 1600);
        const height = stateManager.get(`windowStates.${windowId}.height`) || 
                      stateManager.get('windowStates.main.height', 900);
        let x = stateManager.get(`windowStates.${windowId}.x`) || 
                stateManager.get('windowStates.main.x');
        let y = stateManager.get(`windowStates.${windowId}.y`) || 
                stateManager.get('windowStates.main.y');
        
        // Validate window position - reset if off-screen
        const { screen } = require('electron');
        const displays = screen.getAllDisplays();
        const primaryDisplay = screen.getPrimaryDisplay();
        
        console.log('[Main] Available displays:', displays.length);
        displays.forEach((display, index) => {
            console.log(`[Main] Display ${index}:`, {
                id: display.id,
                bounds: display.bounds,
                workArea: display.workArea,
                scaleFactor: display.scaleFactor
            });
        });
        
        const { width: screenWidth, height: screenHeight } = primaryDisplay.workAreaSize;
        const scaleFactor = primaryDisplay.scaleFactor || 1;
        
        console.log('[Main] Primary display scale factor:', scaleFactor);
        
        // Check if window position is valid
        let isPositionValid = false;
        if (x !== undefined && y !== undefined) {
            // Check if position is within any display
            isPositionValid = displays.some(display => {
                const bounds = display.bounds;
                return x >= bounds.x && x < bounds.x + bounds.width &&
                       y >= bounds.y && y < bounds.y + bounds.height;
            });
        }
        
        if (!isPositionValid) {
            console.log('[Main] Window position invalid or off-screen, centering on primary display');
            x = primaryDisplay.bounds.x + Math.round((screenWidth - width) / 2);
            y = primaryDisplay.bounds.y + Math.round((screenHeight - height) / 2);
        }
        
        // Ensure reasonable dimensions
        const finalWidth = Math.min(width, screenWidth);
        const finalHeight = Math.min(height, screenHeight);
        
        console.log('[Main] Screen dimensions:', { screenWidth, screenHeight });
        console.log('[Main] Creating main window with dimensions:', { 
            width: finalWidth, 
            height: finalHeight, 
            x, 
            y 
        });
        
        // Create the main application window - don't pass saved state, let WindowManager handle it
        const mainWindow = await windowManager.createWindow('main', {
            width: 1600,
            height: 900,
            center: true, // Always center on first launch
            show: false   // Don't show until positioned
        });
        
        // Add debugging and ensure window is shown
        if (mainWindow) {
            console.log('[Main] Main window created successfully');
            console.log('[Main] Window ID:', mainWindow.id);
            console.log('[Main] Window visible:', mainWindow.isVisible());
            console.log('[Main] Window bounds:', mainWindow.getBounds());
            console.log('[Main] Window is minimized:', mainWindow.isMinimized());
            console.log('[Main] Window is focused:', mainWindow.isFocused());
            
            // Force show the window if it's not visible
            if (!mainWindow.isVisible()) {
                console.log('[Main] Window not visible, forcing show...');
                mainWindow.show();
            }
            
            // If window is minimized, restore it
            if (mainWindow.isMinimized()) {
                console.log('[Main] Window is minimized, restoring...');
                mainWindow.restore();
            }
            
            // Force correct window bounds after creation
            setTimeout(() => {
                if (mainWindow && !mainWindow.isDestroyed()) {
                    console.log('[Main] Force-setting window bounds to correct values');
                    mainWindow.setBounds({
                        x: x,
                        y: y,
                        width: finalWidth,
                        height: finalHeight
                    });
                    mainWindow.center();
                    mainWindow.show();
                    mainWindow.focus();
                }
            }, 100);
            
            // Set up event handlers for debugging
            
            mainWindow.on('show', () => {
                console.log('[Main] Window show event');
            });
            
            mainWindow.on('hide', () => {
                console.log('[Main] Window hide event');
            });
            
            mainWindow.on('close', () => {
                console.log('[Main] Window closing');
            });
            
            mainWindow.on('closed', () => {
                console.log('[Main] Window closed');
            });
            
            // Notify renderer that application is ready
            mainWindow.webContents.on('did-finish-load', () => {
                console.log('[Main] Window finished loading');
                mainWindow.webContents.send('app:ready', {
                    version: app.getVersion(),
                    platform: process.platform,
                    config: appConfig.common
                });
            });
            
            mainWindow.webContents.on('did-fail-load', (event, errorCode, errorDescription) => {
                console.error('[Main] Window failed to load:', errorCode, errorDescription);
            });
            
            mainWindow.webContents.on('crashed', (event, killed) => {
                console.error('[Main] Window crashed:', killed);
            });
            
            // Open DevTools in development
            if (isDevelopment) {
                mainWindow.webContents.openDevTools();
            }
            
        } else {
            console.error('[Main] Failed to create main window - window is null');
            throw new Error('Failed to create main window');
        }
        
        // Set up global shortcuts (imported from config)
        setupGlobalShortcuts();
        
        console.log('[Main] Application initialized successfully');
        
    } catch (error) {
        console.error('[Main] Failed to initialize application:', error);
        dialog.showErrorBox('Initialization Error', 
            `Failed to start application: ${error.message}`);
        app.quit();
    }
});

// Handle all windows being closed
app.on('window-all-closed', () => {
    console.log('[Main] All windows closed');
    
    // On macOS, keep app running even when all windows are closed
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

// Handle app reactivation (macOS specific)
app.on('activate', async () => {
    console.log('[Main] App activated');
    
    // On macOS, re-create window when dock icon is clicked
    if (windowManager && windowManager.getWindowCount() === 0) {
        await windowManager.createWindow('main');
    }
});

// Handle app termination
app.on('before-quit', async (event) => {
    console.log('[Main] Application shutting down...');
    
    // Prevent default quit to save state first
    event.preventDefault();
    
    try {
        // Save all window states
        if (windowManager) {
            windowManager.saveAllWindowStates();
        }
        
        // Save any pending state changes
        if (stateManager) {
            await stateManager.save();
        }
        
        // Clean up IPC handlers
        if (ipcHandler) {
            ipcHandler.cleanup();
        }

        // Shutdown Polygon Bridge
        if (polygonBridge) {
            await polygonBridge.shutdown();
        }
        
        console.log('[Main] Cleanup complete, quitting...');
        
        // Now actually quit
        app.exit(0);
        
    } catch (error) {
        console.error('[Main] Error during shutdown:', error);
        app.exit(1);
    }
});

// Handle certificate errors (important for localhost development)
app.on('certificate-error', (event, webContents, url, error, certificate, callback) => {
    if (isDevelopment && url.startsWith('https://localhost')) {
        // Ignore certificate errors in development for localhost
        event.preventDefault();
        callback(true);
    } else {
        // Use default behavior in production
        callback(false);
    }
});

// Set up global keyboard shortcuts
function setupGlobalShortcuts() {
    const { globalShortcut } = require('electron');
    const shortcuts = require('./config/shortcuts.config');
    
    // Register each shortcut from config
    Object.entries(shortcuts.global).forEach(([action, accelerator]) => {
        const success = globalShortcut.register(accelerator, () => {
            console.log(`[Main] Global shortcut triggered: ${action}`);
            
            // Send action to focused window
            const focusedWindow = BrowserWindow.getFocusedWindow();
            if (focusedWindow) {
                focusedWindow.webContents.send('shortcut:triggered', { action });
            }
        });
        
        if (!success) {
            console.warn(`[Main] Failed to register shortcut: ${accelerator}`);
        }
    });
}

// Export for testing purposes
module.exports = { windowManager, ipcHandler, stateManager, polygonBridge };