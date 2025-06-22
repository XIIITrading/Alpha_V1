// electron/src/main/AppUpdater.js
// Handles automatic application updates using electron-updater
// Manages update checking, downloading, and installation with user notifications

// Import required modules
const { autoUpdater } = require('electron-updater');          // Auto-update functionality
const { dialog, BrowserWindow, app, ipcMain } = require('electron');  // Electron modules
const log = require('electron-log');                          // Logging for updates
const path = require('path');                                 // Path utilities
const EventEmitter = require('events');                       // Event system

// Configure electron-log for update logging
log.transports.file.level = 'info';                          // File log level
log.transports.console.level = 'debug';                       // Console log level
log.transports.file.maxSize = 5 * 1024 * 1024;              // 5MB max log file size
log.transports.file.file = path.join(app.getPath('userData'), 'update.log');

// AppUpdater class manages the auto-update process
class AppUpdater extends EventEmitter {
    // Constructor initializes the updater
    constructor(options = {}) {
        // Call parent constructor
        super();
        
        // Configuration options
        this.config = {
            // Update check interval (default: 4 hours)
            checkInterval: options.checkInterval || 4 * 60 * 60 * 1000,
            
            // Allow pre-release versions
            allowPrerelease: options.allowPrerelease || false,
            
            // Allow downgrade
            allowDowngrade: options.allowDowngrade || false,
            
            // Update channel (stable, beta, alpha)
            channel: options.channel || 'stable',
            
            // Auto download updates
            autoDownload: options.autoDownload !== false,  // Default true
            
            // Auto install on app quit
            autoInstallOnAppQuit: options.autoInstallOnAppQuit !== false,  // Default true
            
            // Show notification dialogs
            showNotifications: options.showNotifications !== false,  // Default true
            
            // Force update for critical updates
            forceUpdate: options.forceUpdate || false,
            
            // Update server URL (optional - uses GitHub releases by default)
            feedURL: options.feedURL || null
        };
        
        // Update state tracking
        this.state = {
            checking: false,              // Currently checking for updates
            downloading: false,           // Currently downloading update
            downloaded: false,            // Update downloaded and ready
            error: null,                  // Last error
            updateInfo: null,             // Latest update information
            downloadProgress: null,       // Download progress info
            lastCheck: null              // Last check timestamp
        };
        
        // Auto-check timer reference
        this.checkTimer = null;
        
        // Windows to notify about updates
        this.notificationWindows = new Set();
        
        // Initialize the updater
        this.initialize();
        
        // Log initialization
        log.info('[AppUpdater] Initialized with config:', this.config);
    }
    
    /**
     * Initializes the auto-updater
     */
    initialize() {
        try {
            // Configure auto-updater
            this.configureUpdater();
            
            // Set up event handlers
            this.setupEventHandlers();
            
            // Set up IPC handlers for renderer communication
            this.setupIPCHandlers();
            
            // Start auto-check timer if enabled
            if (this.config.checkInterval > 0) {
                this.startAutoCheckTimer();
            }
            
            log.info('[AppUpdater] Initialization complete');
            
        } catch (error) {
            log.error('[AppUpdater] Initialization failed:', error);
            this.state.error = error;
        }
    }
    
    /**
     * Configures the auto-updater settings
     */
    configureUpdater() {
        // Set update channel
        if (this.config.channel !== 'stable') {
            autoUpdater.channel = this.config.channel;
        }
        
        // Set pre-release preference
        autoUpdater.allowPrerelease = this.config.allowPrerelease;
        
        // Set downgrade preference
        autoUpdater.allowDowngrade = this.config.allowDowngrade;
        
        // Set auto-download preference
        autoUpdater.autoDownload = this.config.autoDownload;
        
        // Set auto-install preference
        autoUpdater.autoInstallOnAppQuit = this.config.autoInstallOnAppQuit;
        
        // Set custom feed URL if provided
        if (this.config.feedURL) {
            autoUpdater.setFeedURL({
                provider: 'generic',
                url: this.config.feedURL
            });
        }
        
        // Configure logger
        autoUpdater.logger = log;
        autoUpdater.logger.transports.file.level = 'info';
        
        // Platform-specific configuration
        if (process.platform === 'darwin') {
            // macOS specific settings
            // Ensure app is signed for auto-update to work
            if (!app.isInApplicationsFolder()) {
                log.warn('[AppUpdater] App not in Applications folder, updates may not work');
            }
        } else if (process.platform === 'win32') {
            // Windows specific settings
            // NSIS installer handles most update logic
        } else if (process.platform === 'linux') {
            // Linux specific settings
            // AppImage updates supported
            if (!process.env.APPIMAGE) {
                log.warn('[AppUpdater] Not running as AppImage, updates disabled');
                this.config.checkInterval = 0;  // Disable auto-check
            }
        }
    }
    
    /**
     * Sets up event handlers for auto-updater events
     */
    setupEventHandlers() {
        // Checking for update
        autoUpdater.on('checking-for-update', () => {
            log.info('[AppUpdater] Checking for updates...');
            
            // Update state
            this.state.checking = true;
            this.state.error = null;
            this.state.lastCheck = Date.now();
            
            // Emit event
            this.emit('checking-for-update');
            
            // Notify windows
            this.notifyWindows('updater:checking');
        });
        
        // Update available
        autoUpdater.on('update-available', (info) => {
            log.info('[AppUpdater] Update available:', info.version);
            
            // Update state
            this.state.checking = false;
            this.state.updateInfo = info;
            
            // Emit event
            this.emit('update-available', info);
            
            // Notify windows
            this.notifyWindows('updater:available', info);
            
            // Show notification if enabled
            if (this.config.showNotifications) {
                this.showUpdateAvailableDialog(info);
            }
            
            // Auto-download if enabled
            if (this.config.autoDownload) {
                this.downloadUpdate();
            }
        });
        
        // No update available
        autoUpdater.on('update-not-available', (info) => {
            log.info('[AppUpdater] No updates available');
            
            // Update state
            this.state.checking = false;
            this.state.updateInfo = null;
            
            // Emit event
            this.emit('update-not-available', info);
            
            // Notify windows
            this.notifyWindows('updater:not-available', info);
        });
        
        // Download progress
        autoUpdater.on('download-progress', (progressInfo) => {
            // Log progress periodically (every 10%)
            const percent = Math.round(progressInfo.percent);
            if (!this.lastLoggedPercent || percent >= this.lastLoggedPercent + 10) {
                log.info(`[AppUpdater] Download progress: ${percent}%`);
                this.lastLoggedPercent = percent;
            }
            
            // Update state
            this.state.downloading = true;
            this.state.downloadProgress = {
                bytesPerSecond: progressInfo.bytesPerSecond,
                percent: progressInfo.percent,
                transferred: progressInfo.transferred,
                total: progressInfo.total,
                // Calculate time remaining
                secondsRemaining: progressInfo.total > 0 && progressInfo.bytesPerSecond > 0
                    ? Math.round((progressInfo.total - progressInfo.transferred) / progressInfo.bytesPerSecond)
                    : null
            };
            
            // Emit event
            this.emit('download-progress', this.state.downloadProgress);
            
            // Notify windows
            this.notifyWindows('updater:progress', this.state.downloadProgress);
        });
        
        // Update downloaded
        autoUpdater.on('update-downloaded', (info) => {
            log.info('[AppUpdater] Update downloaded:', info.version);
            
            // Reset logged percent
            this.lastLoggedPercent = null;
            
            // Update state
            this.state.downloading = false;
            this.state.downloaded = true;
            this.state.downloadProgress = null;
            this.state.updateInfo = info;
            
            // Emit event
            this.emit('update-downloaded', info);
            
            // Notify windows
            this.notifyWindows('updater:downloaded', info);
            
            // Show notification if enabled
            if (this.config.showNotifications) {
                this.showUpdateReadyDialog(info);
            }
        });
        
        // Error occurred
        autoUpdater.on('error', (error) => {
            log.error('[AppUpdater] Update error:', error);
            
            // Update state
            this.state.checking = false;
            this.state.downloading = false;
            this.state.error = error;
            
            // Emit event
            this.emit('error', error);
            
            // Notify windows
            this.notifyWindows('updater:error', {
                message: error.message,
                stack: process.env.NODE_ENV === 'development' ? error.stack : undefined
            });
            
            // Show error notification if enabled and not a network error
            if (this.config.showNotifications && !this.isNetworkError(error)) {
                this.showErrorDialog(error);
            }
        });
    }
    
    /**
     * Sets up IPC handlers for renderer communication
     */
    setupIPCHandlers() {
        // Check for updates
        ipcMain.handle('updater:check', async () => {
            try {
                const result = await this.checkForUpdates();
                return { success: true, result };
            } catch (error) {
                return { success: false, error: error.message };
            }
        });
        
        // Download update
        ipcMain.handle('updater:download', async () => {
            try {
                await this.downloadUpdate();
                return { success: true };
            } catch (error) {
                return { success: false, error: error.message };
            }
        });
        
        // Install update
        ipcMain.handle('updater:install', async () => {
            try {
                await this.installUpdate();
                return { success: true };
            } catch (error) {
                return { success: false, error: error.message };
            }
        });
        
        // Get update state
        ipcMain.handle('updater:get-state', async () => {
            return this.state;
        });
        
        // Set configuration
        ipcMain.handle('updater:set-config', async (event, config) => {
            try {
                this.updateConfig(config);
                return { success: true };
            } catch (error) {
                return { success: false, error: error.message };
            }
        });
        
        // Register window for notifications
        ipcMain.handle('updater:register-window', async (event) => {
            const window = BrowserWindow.fromWebContents(event.sender);
            if (window) {
                this.registerWindow(window);
            }
            return { success: true };
        });
        
        // Unregister window
        ipcMain.handle('updater:unregister-window', async (event) => {
            const window = BrowserWindow.fromWebContents(event.sender);
            if (window) {
                this.unregisterWindow(window);
            }
            return { success: true };
        });
    }
    
    /**
     * Checks for updates
     * @returns {Promise} Update check result
     */
    async checkForUpdates() {
        log.info('[AppUpdater] Manual update check requested');
        
        // Don't check if already checking
        if (this.state.checking) {
            log.warn('[AppUpdater] Already checking for updates');
            return null;
        }
        
        try {
            // Reset error state
            this.state.error = null;
            
            // Check for updates
            const result = await autoUpdater.checkForUpdates();
            
            return result;
            
        } catch (error) {
            log.error('[AppUpdater] Check for updates failed:', error);
            this.state.error = error;
            throw error;
        }
    }
    
    /**
     * Downloads the available update
     */
    async downloadUpdate() {
        log.info('[AppUpdater] Download update requested');
        
        // Check if update is available
        if (!this.state.updateInfo) {
            log.warn('[AppUpdater] No update available to download');
            return;
        }
        
        // Don't download if already downloading or downloaded
        if (this.state.downloading || this.state.downloaded) {
            log.warn('[AppUpdater] Update already downloading or downloaded');
            return;
        }
        
        try {
            // Start download
            await autoUpdater.downloadUpdate();
            
        } catch (error) {
            log.error('[AppUpdater] Download failed:', error);
            this.state.error = error;
            throw error;
        }
    }
    
    /**
     * Installs the downloaded update
     * @param {boolean} forceRestart - Force restart now
     */
    async installUpdate(forceRestart = false) {
        log.info('[AppUpdater] Install update requested');
        
        // Check if update is downloaded
        if (!this.state.downloaded) {
            log.warn('[AppUpdater] No update downloaded');
            return;
        }
        
        try {
            // Set auto-install to false to control restart
            autoUpdater.autoInstallOnAppQuit = !forceRestart;
            
            if (forceRestart) {
                // Quit and install immediately
                log.info('[AppUpdater] Restarting to install update...');
                
                // Notify windows about restart
                this.notifyWindows('updater:restarting');
                
                // Give windows time to save state
                setTimeout(() => {
                    autoUpdater.quitAndInstall();
                }, 1000);
                
            } else {
                // Install on next app quit
                log.info('[AppUpdater] Update will be installed on next restart');
                
                // Notify user
                if (this.config.showNotifications) {
                    dialog.showMessageBox({
                        type: 'info',
                        title: 'Update Ready',
                        message: 'The update will be installed when you quit the application.',
                        buttons: ['OK']
                    });
                }
            }
            
        } catch (error) {
            log.error('[AppUpdater] Install failed:', error);
            this.state.error = error;
            throw error;
        }
    }
    
    /**
     * Shows update available dialog
     * @param {Object} info - Update information
     */
    async showUpdateAvailableDialog(info) {
        // Don't show if force update is enabled (will auto-download)
        if (this.config.forceUpdate) {
            return;
        }
        
        // Build release notes
        const releaseNotes = this.formatReleaseNotes(info);
        
        // Show dialog
        const result = await dialog.showMessageBox({
            type: 'info',
            title: 'Update Available',
            message: `A new version (${info.version}) is available.`,
            detail: releaseNotes,
            buttons: this.config.autoDownload 
                ? ['OK', 'View Details'] 
                : ['Download', 'Later', 'View Details'],
            defaultId: 0,
            cancelId: 1
        });
        
        // Handle response
        if (!this.config.autoDownload && result.response === 0) {
            // User chose to download
            this.downloadUpdate();
        } else if (result.response === (this.config.autoDownload ? 1 : 2)) {
            // User chose to view details
            if (info.releaseNotes) {
                // Open release notes in browser
                const { shell } = require('electron');
                shell.openExternal(info.releaseNotes);
            }
        }
    }
    
    /**
     * Shows update ready dialog
     * @param {Object} info - Update information
     */
    async showUpdateReadyDialog(info) {
        // Force update check
        if (this.config.forceUpdate) {
            // Auto-install for critical updates
            this.installUpdate(true);
            return;
        }
        
        // Build message
        const message = `Version ${info.version} has been downloaded and is ready to install.`;
        
        // Show dialog
        const result = await dialog.showMessageBox({
            type: 'info',
            title: 'Update Ready to Install',
            message: message,
            detail: 'The application needs to restart to apply the update.',
            buttons: ['Restart Now', 'Later'],
            defaultId: 0,
            cancelId: 1
        });
        
        // Handle response
        if (result.response === 0) {
            // User chose to restart now
            this.installUpdate(true);
        }
    }
    
    /**
     * Shows error dialog
     * @param {Error} error - Error object
     */
    showErrorDialog(error) {
        // Don't show for common network errors
        if (this.isNetworkError(error)) {
            return;
        }
        
        // Show error dialog
        dialog.showErrorBox(
            'Update Error',
            `An error occurred while checking for updates:\n\n${error.message}`
        );
    }
    
    /**
     * Formats release notes for display
     * @param {Object} info - Update information
     * @returns {string} Formatted release notes
     */
    formatReleaseNotes(info) {
        let notes = `Current version: ${app.getVersion()}\n`;
        notes += `New version: ${info.version}\n\n`;
        
        if (info.releaseNotes) {
            // Handle different release note formats
            if (typeof info.releaseNotes === 'string') {
                notes += info.releaseNotes;
            } else if (Array.isArray(info.releaseNotes)) {
                // Array of release note objects
                info.releaseNotes.forEach(note => {
                    if (note.version) {
                        notes += `\nVersion ${note.version}:\n`;
                    }
                    notes += note.note || note.text || '';
                });
            }
        } else {
            notes += 'No release notes available.';
        }
        
        return notes;
    }
    
    /**
     * Checks if error is a network error
     * @param {Error} error - Error to check
     * @returns {boolean} True if network error
     */
    isNetworkError(error) {
        const networkErrors = [
            'ENOTFOUND',
            'ECONNREFUSED',
            'ETIMEDOUT',
            'ENETUNREACH',
            'EAI_AGAIN'
        ];
        
        return networkErrors.some(code => 
            error.code === code || 
            error.message.includes(code)
        );
    }
    
    /**
     * Starts the auto-check timer
     */
    startAutoCheckTimer() {
        // Clear existing timer
        this.stopAutoCheckTimer();
        
        // Don't start if interval is 0
        if (this.config.checkInterval <= 0) {
            return;
        }
        
        log.info(`[AppUpdater] Starting auto-check timer (${this.config.checkInterval}ms)`);
        
        // Set up interval
        this.checkTimer = setInterval(() => {
            log.info('[AppUpdater] Auto-check timer triggered');
            this.checkForUpdates().catch(error => {
                log.error('[AppUpdater] Auto-check failed:', error);
            });
        }, this.config.checkInterval);
        
        // Also check immediately on start (after a delay)
        setTimeout(() => {
            this.checkForUpdates().catch(error => {
                log.error('[AppUpdater] Initial check failed:', error);
            });
        }, 30000);  // 30 seconds after app start
    }
    
    /**
     * Stops the auto-check timer
     */
    stopAutoCheckTimer() {
        if (this.checkTimer) {
            clearInterval(this.checkTimer);
            this.checkTimer = null;
            log.info('[AppUpdater] Stopped auto-check timer');
        }
    }
    
    /**
     * Updates configuration
     * @param {Object} config - New configuration values
     */
    updateConfig(config) {
        log.info('[AppUpdater] Updating configuration:', config);
        
        // Update config values
        Object.assign(this.config, config);
        
        // Apply changes
        if ('allowPrerelease' in config) {
            autoUpdater.allowPrerelease = config.allowPrerelease;
        }
        
        if ('allowDowngrade' in config) {
            autoUpdater.allowDowngrade = config.allowDowngrade;
        }
        
        if ('autoDownload' in config) {
            autoUpdater.autoDownload = config.autoDownload;
        }
        
        if ('autoInstallOnAppQuit' in config) {
            autoUpdater.autoInstallOnAppQuit = config.autoInstallOnAppQuit;
        }
        
        if ('channel' in config) {
            autoUpdater.channel = config.channel;
        }
        
        // Restart timer if interval changed
        if ('checkInterval' in config) {
            this.startAutoCheckTimer();
        }
    }
    
    /**
     * Registers a window for update notifications
     * @param {BrowserWindow} window - Window to register
     */
    registerWindow(window) {
        this.notificationWindows.add(window);
        
        // Remove on close
        window.once('closed', () => {
            this.notificationWindows.delete(window);
        });
        
        log.info(`[AppUpdater] Registered window for notifications (total: ${this.notificationWindows.size})`);
    }
    
    /**
     * Unregisters a window from notifications
     * @param {BrowserWindow} window - Window to unregister
     */
    unregisterWindow(window) {
        this.notificationWindows.delete(window);
        log.info(`[AppUpdater] Unregistered window from notifications (total: ${this.notificationWindows.size})`);
    }
    
    /**
     * Notifies all registered windows
     * @param {string} channel - IPC channel
     * @param {*} data - Data to send
     */
    notifyWindows(channel, data) {
        for (const window of this.notificationWindows) {
            if (!window.isDestroyed()) {
                window.webContents.send(channel, data);
            }
        }
    }
    
    /**
     * Gets update statistics
     * @returns {Object} Update statistics
     */
    getStatistics() {
        return {
            // Current version
            currentVersion: app.getVersion(),
            
            // Update state
            state: this.state,
            
            // Configuration
            config: this.config,
            
            // Statistics
            stats: {
                lastCheck: this.state.lastCheck 
                    ? new Date(this.state.lastCheck).toISOString() 
                    : 'Never',
                nextCheck: this.checkTimer && this.state.lastCheck
                    ? new Date(this.state.lastCheck + this.config.checkInterval).toISOString()
                    : 'N/A',
                registeredWindows: this.notificationWindows.size
            },
            
            // Platform info
            platform: {
                os: process.platform,
                arch: process.arch,
                updateSupported: this.isUpdateSupported()
            }
        };
    }
    
    /**
     * Checks if updates are supported on this platform
     * @returns {boolean} True if updates are supported
     */
    isUpdateSupported() {
        // macOS: Supported if signed and in Applications
        if (process.platform === 'darwin') {
            return app.isInApplicationsFolder();
        }
        
        // Windows: Always supported with NSIS
        if (process.platform === 'win32') {
            return true;
        }
        
        // Linux: Only AppImage is supported
        if (process.platform === 'linux') {
            return !!process.env.APPIMAGE;
        }
        
        // Other platforms: Not supported
        return false;
    }
    
    /**
     * Cleans up the updater
     */
    cleanup() {
        log.info('[AppUpdater] Cleaning up...');
        
        // Stop auto-check timer
        this.stopAutoCheckTimer();
        
        // Clear notification windows
        this.notificationWindows.clear();
        
        // Remove all listeners
        this.removeAllListeners();
        
        log.info('[AppUpdater] Cleanup complete');
    }
}

// Export the AppUpdater class
module.exports = AppUpdater;