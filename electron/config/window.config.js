/**
 * Window Configuration for Alpha V1 Trading Tool
 * 
 * This file defines all window presets and configurations
 * Location: electron/config/window.config.js
 */

const path = require('path');

// Window configuration object
const windowConfig = {
    // Default settings for all windows
    defaults: {
        width: 1200,
        height: 800,
        minWidth: 800,
        minHeight: 600,
        frame: true,
        backgroundColor: '#0d0d0d',
        webPreferences: {
            // Security settings - CRITICAL
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: true,
            
            // Path to preload script (relative to this config file)
            preload: path.join(__dirname, '..', 'preload.js'),
            
            // Performance settings
            backgroundThrottling: false,
            
            // Disable features we don't need
            webviewTag: false,
            navigateOnDragDrop: false,
            
            // Enable DevTools in development
            devTools: process.env.NODE_ENV === 'development'
        },
        
        // Don't show window until ready to prevent white flash
        show: false,
        
        // Platform-specific title bar
        titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default'
    },
    
    // Window-specific configurations
    windows: {
        // Main trading window
        main: {
            id: 'main',
            title: 'Alpha V1 Trading Tool',
            
            // Path to HTML file (relative to electron root)
            // This is the CRITICAL line that needs to be correct
            file: path.join(__dirname, '..', 'src', 'renderer', 'index.html'),
            
            // Main window specific size
            width: 1400,
            height: 900,
            center: true
        },
        
        // Scanner window (uses same HTML, different tab)
        scanner: {
            id: 'scanner',
            title: 'Scanner - Alpha V1',
            file: path.join(__dirname, '..', 'src', 'renderer', 'index.html'),
            width: 1200,
            height: 700,
            alwaysOnTop: false,
            resizable: true
        },
        
        // Positions window
        positions: {
            id: 'positions',
            title: 'Positions - Alpha V1',
            file: path.join(__dirname, '..', 'src', 'renderer', 'index.html'),
            width: 1000,
            height: 600,
            alwaysOnTop: true,
            resizable: true
        },
        
        // Settings window (placeholder for future)
        settings: {
            id: 'settings',
            title: 'Settings - Alpha V1',
            file: path.join(__dirname, '..', 'src', 'renderer', 'index.html'),
            width: 800,
            height: 600,
            resizable: false,
            minimizable: false,
            maximizable: false
        }
    }
};

// Helper function to get window configuration
function getWindowConfig(windowType, overrides = {}) {
    const base = windowConfig.defaults;
    const specific = windowConfig.windows[windowType] || {};
    
    // Merge configurations
    const config = {
        ...base,
        ...specific,
        ...overrides,
        webPreferences: {
            ...base.webPreferences,
            ...(specific.webPreferences || {}),
            ...(overrides.webPreferences || {})
        }
    };
    
    return config;
}

// Export the configuration
module.exports = {
    ...windowConfig,
    getWindowConfig
};