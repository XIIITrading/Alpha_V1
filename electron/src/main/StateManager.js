// electron/src/main/StateManager.js
// Manages persistent application state using electron-store
// Provides a centralized way to save and load user preferences, window states, and app data

// Import required modules
const Store = require('electron-store');
const { app } = require('electron');
const path = require('path');
const fs = require('fs').promises;
const EventEmitter = require('events');

// StateManager class extends EventEmitter to notify about state changes
class StateManager extends EventEmitter {
    // Constructor accepts configuration options
    constructor(options = {}) {
        // Call parent constructor
        super();
        
        // Default configuration for electron-store
        const defaultConfig = {
            // Name of the storage file (without extension)
            name: options.name || 'app-state',
            
            // File extension for the storage file
            fileExtension: 'json',
            
            // Directory to store the file (defaults to app's userData)
            cwd: options.cwd || app.getPath('userData'),
            
            // Encryption key (optional - for sensitive data)
            encryptionKey: options.encryptionKey || null,
            
            // Pretty print JSON for debugging
            prettify: process.env.NODE_ENV === 'development',
            
            // Watch for external changes to the file - DISABLED to avoid the error
            watch: false,  // Changed from true to false
            
            // Access nested properties with dot notation
            accessPropertiesByDotNotation: true,
            
            // Clear invalid config instead of throwing
            clearInvalidConfig: true,
            
            // Default values for the store
            defaults: options.defaults || this.getDefaultState()
        };
        
        // Create the electron-store instance
        this.store = new Store(defaultConfig);
        
        // Store configuration for reference
        this.config = defaultConfig;
        
        // Cache for frequently accessed values (performance optimization)
        this.cache = new Map();
        
        // Track if cache is enabled
        this.cacheEnabled = options.enableCache !== false;  // Default to true
        
        // Maximum cache size (prevent memory issues)
        this.maxCacheSize = options.maxCacheSize || 100;
        
        // Auto-save debounce timeout (ms)
        this.autoSaveDelay = options.autoSaveDelay || 1000;
        
        // Pending saves (for debouncing)
        this.pendingSaves = new Map();
        
        // Migration version tracking
        this.schemaVersion = options.schemaVersion || 1;
        
        // Backup configuration
        this.backupEnabled = options.enableBackup !== false;  // Default to true
        this.maxBackups = options.maxBackups || 5;
        
        // Initialize the state manager
        this.initialize();
        
        // Log initialization
        console.log('[StateManager] Initialized with store at:', this.store.path);
    }
    
    /**
     * Gets default state structure
     * @returns {Object} Default state object
     */
    getDefaultState() {
        return {
            // Application preferences
            preferences: {
                theme: 'dark',                    // UI theme
                language: 'en',                   // Language setting
                autoSave: true,                   // Auto-save enabled
                confirmExit: true,                // Confirm before exit
                startupBehavior: 'restore',       // restore, fresh, or minimal
                defaultLayout: 'standard'         // Default window layout
            },
            
            // Window states (position, size, etc.)
            windowStates: {},
            
            // User workspace data
            workspace: {
                recentFiles: [],                  // Recently opened files
                openTabs: [],                     // Currently open tabs
                activeSymbols: [],                // Active trading symbols
                watchlists: {}                    // User watchlists
            },
            
            // Trading specific settings
            trading: {
                defaultOrderType: 'limit',        // Default order type
                defaultQuantity: 100,             // Default trade quantity
                riskPerTrade: 1.0,               // Risk percentage per trade
                profitTarget: 2.0,               // Risk/reward ratio
                stopLossEnabled: true,           // Auto stop-loss
                trailingStopEnabled: false       // Trailing stop
            },
            
            // Data feed settings
            dataFeed: {
                autoConnect: true,                // Auto-connect on startup
                reconnectAttempts: 3,             // Max reconnection attempts
                updateInterval: 1000,             // Update interval (ms)
                cacheEnabled: true,               // Enable data caching
                cacheExpiry: 3600                 // Cache expiry (seconds)
            },
            
            // UI customization
            ui: {
                sidebarVisible: true,             // Show sidebar
                sidebarWidth: 250,                // Sidebar width
                fontSize: 14,                     // Base font size
                compactMode: false,               // Compact UI mode
                animations: true,                 // Enable animations
                soundEnabled: true                // Enable sound alerts
            },
            
            // Performance settings
            performance: {
                hardwareAcceleration: true,       // GPU acceleration
                maxMemoryUsage: 2048,            // Max memory (MB)
                logLevel: 'info',                // Logging level
                telemetryEnabled: false          // Anonymous telemetry
            },
            
            // Schema version for migrations
            _schemaVersion: this.schemaVersion
        };
    }
    
    /**
     * Initializes the state manager
     */
    initialize() {
        console.log('[StateManager] Initializing...');
        
        try {
            // Check if migration is needed
            this.checkAndMigrate();
            
            // Create initial backup if enabled
            if (this.backupEnabled) {
                this.createBackup('initial');
            }
            
            // Validate current state
            this.validateState();
            
            // Emit ready event
            this.emit('ready');
            
            console.log('[StateManager] Initialization complete');
            
        } catch (error) {
            console.error('[StateManager] Initialization failed:', error);
            
            // Try to restore from backup
            if (this.backupEnabled) {
                this.restoreFromBackup();
            } else {
                // Reset to defaults if no backup
                this.reset();
            }
        }
    }
    
    /**
     * Gets a value from the state
     * @param {string} key - Dot notation key path
     * @param {*} defaultValue - Default value if key doesn't exist
     * @returns {*} The value at the key path
     */
    get(key, defaultValue) {
        // Check cache first if enabled
        if (this.cacheEnabled && this.cache.has(key)) {
            const cached = this.cache.get(key);
            
            // Update cache access time for LRU
            this.cache.delete(key);
            this.cache.set(key, cached);
            
            return cached.value;
        }
        
        try {
            // Get value from store
            const value = this.store.get(key, defaultValue);
            
            // Cache the value if caching is enabled
            if (this.cacheEnabled) {
                this.addToCache(key, value);
            }
            
            return value;
            
        } catch (error) {
            console.error(`[StateManager] Error getting key "${key}":`, error);
            return defaultValue;
        }
    }
    
    /**
     * Sets a value in the state
     * @param {string} key - Dot notation key path
     * @param {*} value - Value to set
     */
    set(key, value) {
        try {
            // Get old value for change detection
            const oldValue = this.get(key);
            
            // Set value in store
            this.store.set(key, value);
            
            // Update cache if enabled
            if (this.cacheEnabled) {
                this.addToCache(key, value);
            }
            
            // Schedule auto-save if enabled
            this.scheduleAutoSave();
            
            // Emit change event
            this.emit('change', {
                key,
                oldValue,
                newValue: value,
                timestamp: Date.now()
            });
            
            // Emit specific key change event
            this.emit(`change:${key}`, {
                oldValue,
                newValue: value
            });
            
        } catch (error) {
            console.error(`[StateManager] Error setting key "${key}":`, error);
            throw error;
        }
    }
    
    /**
     * Deletes a key from the state
     * @param {string} key - Key to delete
     */
    delete(key) {
        try {
            // Get old value for event
            const oldValue = this.get(key);
            
            // Delete from store
            this.store.delete(key);
            
            // Remove from cache
            if (this.cacheEnabled) {
                this.cache.delete(key);
            }
            
            // Schedule auto-save
            this.scheduleAutoSave();
            
            // Emit change event
            this.emit('change', {
                key,
                oldValue,
                newValue: undefined,
                deleted: true,
                timestamp: Date.now()
            });
            
        } catch (error) {
            console.error(`[StateManager] Error deleting key "${key}":`, error);
            throw error;
        }
    }
    
    /**
     * Checks if a key exists
     * @param {string} key - Key to check
     * @returns {boolean} True if key exists
     */
    has(key) {
        try {
            return this.store.has(key);
        } catch (error) {
            console.error(`[StateManager] Error checking key "${key}":`, error);
            return false;
        }
    }
    
    /**
     * Gets all keys in the store
     * @returns {string[]} Array of all keys
     */
    getKeys() {
        try {
            // Get all data
            const data = this.store.store;
            
            // Extract all keys recursively
            const keys = [];
            const extractKeys = (obj, prefix = '') => {
                for (const key in obj) {
                    const fullKey = prefix ? `${prefix}.${key}` : key;
                    keys.push(fullKey);
                    
                    // Recurse for nested objects
                    if (typeof obj[key] === 'object' && obj[key] !== null && !Array.isArray(obj[key])) {
                        extractKeys(obj[key], fullKey);
                    }
                }
            };
            
            extractKeys(data);
            return keys;
            
        } catch (error) {
            console.error('[StateManager] Error getting keys:', error);
            return [];
        }
    }
    
    /**
     * Gets the entire store data
     * @returns {Object} Complete store data
     */
    getAll() {
        try {
            return this.store.store;
        } catch (error) {
            console.error('[StateManager] Error getting all data:', error);
            return {};
        }
    }
    
    /**
     * Resets the store to default values
     */
    reset() {
        try {
            console.log('[StateManager] Resetting to defaults...');
            
            // Create backup before reset
            if (this.backupEnabled) {
                this.createBackup('before-reset');
            }
            
            // Clear the store
            this.store.clear();
            
            // Set defaults
            const defaults = this.getDefaultState();
            for (const key in defaults) {
                this.store.set(key, defaults[key]);
            }
            
            // Clear cache
            this.cache.clear();
            
            // Emit reset event
            this.emit('reset');
            
            console.log('[StateManager] Reset complete');
            
        } catch (error) {
            console.error('[StateManager] Error resetting store:', error);
            throw error;
        }
    }
    
    /**
     * Saves the current state (force write to disk)
     */
    async save() {
        try {
            // Force write to disk (electron-store usually auto-saves)
            // This is mainly for explicit save operations
            
            // Create backup if enabled
            if (this.backupEnabled) {
                await this.createBackup('manual-save');
            }
            
            // Emit save event
            this.emit('save');
            
            return true;
            
        } catch (error) {
            console.error('[StateManager] Error saving state:', error);
            throw error;
        }
    }
    
    /**
     * Adds a value to the cache with LRU eviction
     * @param {string} key - Cache key
     * @param {*} value - Value to cache
     */
    addToCache(key, value) {
        // Check cache size limit
        if (this.cache.size >= this.maxCacheSize) {
            // Remove oldest entry (first in map)
            const firstKey = this.cache.keys().next().value;
            this.cache.delete(firstKey);
        }
        
        // Add to cache
        this.cache.set(key, {
            value,
            timestamp: Date.now()
        });
    }
    
    /**
     * Clears the cache
     */
    clearCache() {
        this.cache.clear();
        console.log('[StateManager] Cache cleared');
    }
    
    /**
     * Schedules an auto-save with debouncing
     */
    scheduleAutoSave() {
        // Clear existing timeout
        if (this.autoSaveTimeout) {
            clearTimeout(this.autoSaveTimeout);
        }
        
        // Schedule new save
        this.autoSaveTimeout = setTimeout(() => {
            this.save().catch(error => {
                console.error('[StateManager] Auto-save failed:', error);
            });
        }, this.autoSaveDelay);
    }
    
    /**
     * Validates the current state structure
     */
    validateState() {
        console.log('[StateManager] Validating state...');
        
        try {
            const state = this.getAll();
            const defaults = this.getDefaultState();
            
            // Check for required top-level keys
            for (const key in defaults) {
                if (!(key in state)) {
                    console.warn(`[StateManager] Missing key: ${key}, adding default`);
                    this.set(key, defaults[key]);
                }
            }
            
            // Validate specific structures
            this.validatePreferences();
            this.validateWindowStates();
            this.validateTradingSettings();
            
            console.log('[StateManager] Validation complete');
            
        } catch (error) {
            console.error('[StateManager] Validation failed:', error);
            throw error;
        }
    }
    
    /**
     * Validates preferences structure
     */
    validatePreferences() {
        const prefs = this.get('preferences', {});
        const defaultPrefs = this.getDefaultState().preferences;
        
        // Ensure all preference keys exist
        for (const key in defaultPrefs) {
            if (!(key in prefs)) {
                this.set(`preferences.${key}`, defaultPrefs[key]);
            }
        }
        
        // Validate theme
        const validThemes = ['dark', 'light', 'auto'];
        if (!validThemes.includes(prefs.theme)) {
            this.set('preferences.theme', 'dark');
        }
        
        // Validate language
        const validLanguages = ['en', 'es', 'fr', 'de', 'ja', 'zh'];
        if (!validLanguages.includes(prefs.language)) {
            this.set('preferences.language', 'en');
        }
    }
    
    /**
     * Validates window states
     */
    validateWindowStates() {
        const windowStates = this.get('windowStates', {});
        
        // Remove invalid window states
        for (const windowId in windowStates) {
            const state = windowStates[windowId];
            
            // Check for required properties
            if (!state || typeof state !== 'object' ||
                !('x' in state) || !('y' in state) ||
                !('width' in state) || !('height' in state)) {
                
                console.warn(`[StateManager] Invalid window state for ${windowId}, removing`);
                this.delete(`windowStates.${windowId}`);
            }
        }
    }
    
    /**
     * Validates trading settings
     */
    validateTradingSettings() {
        const trading = this.get('trading', {});
        
        // Validate risk per trade (must be between 0 and 100)
        if (typeof trading.riskPerTrade !== 'number' || 
            trading.riskPerTrade < 0 || 
            trading.riskPerTrade > 100) {
            this.set('trading.riskPerTrade', 1.0);
        }
        
        // Validate default quantity (must be positive)
        if (typeof trading.defaultQuantity !== 'number' || 
            trading.defaultQuantity <= 0) {
            this.set('trading.defaultQuantity', 100);
        }
        
        // Validate order type
        const validOrderTypes = ['market', 'limit', 'stop', 'stop-limit'];
        if (!validOrderTypes.includes(trading.defaultOrderType)) {
            this.set('trading.defaultOrderType', 'limit');
        }
    }
    
    /**
     * Checks if migration is needed and performs it
     */
    checkAndMigrate() {
        const currentVersion = this.get('_schemaVersion', 0);
        
        if (currentVersion < this.schemaVersion) {
            console.log(`[StateManager] Migrating from version ${currentVersion} to ${this.schemaVersion}`);
            
            // Create backup before migration
            if (this.backupEnabled) {
                this.createBackup(`migration-v${currentVersion}-to-v${this.schemaVersion}`);
            }
            
            // Perform migrations
            this.performMigrations(currentVersion, this.schemaVersion);
            
            // Update schema version
            this.set('_schemaVersion', this.schemaVersion);
        }
    }
    
    /**
     * Performs schema migrations
     * @param {number} fromVersion - Starting version
     * @param {number} toVersion - Target version
     */
    performMigrations(fromVersion, toVersion) {
        // Define migration functions for each version
        const migrations = {
            // Version 1 -> 2 migration example
            2: () => {
                console.log('[StateManager] Migrating to v2...');
                // Add new fields, restructure data, etc.
                const oldData = this.get('tradingSettings');
                if (oldData) {
                    this.set('trading', oldData);
                    this.delete('tradingSettings');
                }
            },
            
            // Version 2 -> 3 migration example
            3: () => {
                console.log('[StateManager] Migrating to v3...');
                // Add performance settings
                if (!this.has('performance')) {
                    this.set('performance', {
                        hardwareAcceleration: true,
                        maxMemoryUsage: 2048,
                        logLevel: 'info',
                        telemetryEnabled: false
                    });
                }
            }
        };
        
        // Run migrations sequentially
        for (let version = fromVersion + 1; version <= toVersion; version++) {
            if (migrations[version]) {
                try {
                    migrations[version]();
                    console.log(`[StateManager] Migration to v${version} complete`);
                } catch (error) {
                    console.error(`[StateManager] Migration to v${version} failed:`, error);
                    throw error;
                }
            }
        }
    }
    
    /**
     * Creates a backup of the current state
     * @param {string} reason - Reason for backup
     */
    async createBackup(reason = 'manual') {
        if (!this.backupEnabled) return;
        
        try {
            // Get backup directory
            const backupDir = path.join(this.config.cwd, 'backups');
            
            // Ensure backup directory exists
            await fs.mkdir(backupDir, { recursive: true });
            
            // Generate backup filename with timestamp
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const backupFile = path.join(backupDir, `state-backup-${timestamp}-${reason}.json`);
            
            // Get current state
            const state = this.getAll();
            
            // Write backup file
            await fs.writeFile(backupFile, JSON.stringify(state, null, 2));
            
            console.log(`[StateManager] Backup created: ${backupFile}`);
            
            // Clean up old backups
            await this.cleanupBackups(backupDir);
            
        } catch (error) {
            console.error('[StateManager] Backup failed:', error);
            // Don't throw - backups shouldn't break the app
        }
    }
    
    /**
     * Cleans up old backups keeping only the most recent ones
     * @param {string} backupDir - Backup directory path
     */
    async cleanupBackups(backupDir) {
        try {
            // Get all backup files
            const files = await fs.readdir(backupDir);
            const backupFiles = files
                .filter(f => f.startsWith('state-backup-') && f.endsWith('.json'))
                .map(f => ({
                    name: f,
                    path: path.join(backupDir, f)
                }));
            
            // Sort by creation time (newest first)
            const stats = await Promise.all(
                backupFiles.map(async f => ({
                    ...f,
                    stats: await fs.stat(f.path)
                }))
            );
            
            stats.sort((a, b) => b.stats.mtime - a.stats.mtime);
            
            // Delete old backups beyond the limit
            const toDelete = stats.slice(this.maxBackups);
            for (const file of toDelete) {
                await fs.unlink(file.path);
                console.log(`[StateManager] Deleted old backup: ${file.name}`);
            }
            
        } catch (error) {
            console.error('[StateManager] Backup cleanup failed:', error);
        }
    }
    
    /**
     * Restores state from the most recent backup
     */
    async restoreFromBackup() {
        if (!this.backupEnabled) return false;
        
        try {
            console.log('[StateManager] Attempting to restore from backup...');
            
            // Get backup directory
            const backupDir = path.join(this.config.cwd, 'backups');
            
            // Check if backup directory exists
            try {
                await fs.access(backupDir);
            } catch {
                console.log('[StateManager] No backup directory found');
                return false;
            }
            
            // Get all backup files
            const files = await fs.readdir(backupDir);
            const backupFiles = files
                .filter(f => f.startsWith('state-backup-') && f.endsWith('.json'))
                .map(f => path.join(backupDir, f));
            
            if (backupFiles.length === 0) {
                console.log('[StateManager] No backup files found');
                return false;
            }
            
            // Get most recent backup
            const stats = await Promise.all(
                backupFiles.map(async f => ({
                    file: f,
                    mtime: (await fs.stat(f)).mtime
                }))
            );
            
            stats.sort((a, b) => b.mtime - a.mtime);
            const mostRecent = stats[0].file;
            
            // Read backup file
            const backupData = await fs.readFile(mostRecent, 'utf8');
            const backupState = JSON.parse(backupData);
            
            // Clear current store
            this.store.clear();
            
            // Restore from backup
            for (const key in backupState) {
                this.store.set(key, backupState[key]);
            }
            
            // Clear cache
            this.cache.clear();
            
            console.log(`[StateManager] Restored from backup: ${path.basename(mostRecent)}`);
            
            // Emit restore event
            this.emit('restore', { backupFile: mostRecent });
            
            return true;
            
        } catch (error) {
            console.error('[StateManager] Restore from backup failed:', error);
            return false;
        }
    }
    
    /**
     * Gets state statistics
     * @returns {Object} Statistics about the state
     */
    getStatistics() {
        try {
            const state = this.getAll();
            const json = JSON.stringify(state);
            
            return {
                // Size in bytes
                sizeBytes: Buffer.byteLength(json, 'utf8'),
                
                // Size in KB
                sizeKB: (Buffer.byteLength(json, 'utf8') / 1024).toFixed(2),
                
                // Number of top-level keys
                topLevelKeys: Object.keys(state).length,
                
                // Total number of keys (including nested)
                totalKeys: this.getKeys().length,
                
                // Cache statistics
                cache: {
                    enabled: this.cacheEnabled,
                    size: this.cache.size,
                    maxSize: this.maxCacheSize,
                    hitRate: 'N/A'  // Would need to track hits/misses
                },
                
                // File path
                filePath: this.store.path,
                
                // Schema version
                schemaVersion: this.get('_schemaVersion', 0)
            };
            
        } catch (error) {
            console.error('[StateManager] Error getting statistics:', error);
            return null;
        }
    }
    
    /**
     * Cleans up and closes the state manager
     */
    cleanup() {
        console.log('[StateManager] Cleaning up...');
        
        // Clear any pending auto-save
        if (this.autoSaveTimeout) {
            clearTimeout(this.autoSaveTimeout);
        }
        
        // Save current state
        this.save().catch(error => {
            console.error('[StateManager] Final save failed:', error);
        });
        
        // Clear cache
        this.cache.clear();
        
        // Remove all listeners
        this.removeAllListeners();
        
        console.log('[StateManager] Cleanup complete');
    }
}

// Export the StateManager class
module.exports = StateManager;