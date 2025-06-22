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
        
        // Create the main application window
        const mainWindow = await windowManager.createWindow('main', {
            width: stateManager.get('windowStates.main.width', 1600),
            height: stateManager.get('windowStates.main.height', 900),
            x: stateManager.get('windowStates.main.x'),
            y: stateManager.get('windowStates.main.y')
        });
        
        // Set up global shortcuts (imported from config)
        setupGlobalShortcuts();
        
        // Notify renderer that application is ready
        mainWindow.webContents.on('did-finish-load', () => {
            mainWindow.webContents.send('app:ready', {
                version: app.getVersion(),
                platform: process.platform,
                config: appConfig.common
            });
        });
        
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
module.exports = { windowManager, ipcHandler, stateManager };