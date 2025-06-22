// electron/src/main/MenuBuilder.js
// Creates and manages the application menu bar with all menus and shortcuts
// Handles platform-specific differences (Windows/Linux vs macOS)

// Import required Electron modules
const { Menu, MenuItem, shell, dialog, BrowserWindow, app } = require('electron');
const path = require('path');

// MenuBuilder class creates the application menu
class MenuBuilder {
    // Constructor accepts options for customization
    constructor(options = {}) {
        // Store window manager reference for window operations
        this.windowManager = options.windowManager;
        
        // Development mode flag affects menu items shown
        this.isDevelopment = options.isDevelopment || false;
        
        // Platform detection for platform-specific menu differences
        this.isMac = process.platform === 'darwin';     // macOS
        this.isWindows = process.platform === 'win32';  // Windows
        this.isLinux = process.platform === 'linux';    // Linux
        
        // Store menu reference for updates
        this.menu = null;
        
        // Keyboard accelerators (shortcuts) - platform aware
        this.accelerators = {
            // File menu shortcuts
            newWindow: this.isMac ? 'Cmd+N' : 'Ctrl+N',
            openFile: this.isMac ? 'Cmd+O' : 'Ctrl+O',
            save: this.isMac ? 'Cmd+S' : 'Ctrl+S',
            saveAs: this.isMac ? 'Shift+Cmd+S' : 'Ctrl+Shift+S',
            preferences: this.isMac ? 'Cmd+,' : 'Ctrl+,',
            quit: this.isMac ? 'Cmd+Q' : 'Ctrl+Q',
            
            // Edit menu shortcuts
            undo: this.isMac ? 'Cmd+Z' : 'Ctrl+Z',
            redo: this.isMac ? 'Shift+Cmd+Z' : 'Ctrl+Y',
            cut: this.isMac ? 'Cmd+X' : 'Ctrl+X',
            copy: this.isMac ? 'Cmd+C' : 'Ctrl+C',
            paste: this.isMac ? 'Cmd+V' : 'Ctrl+V',
            selectAll: this.isMac ? 'Cmd+A' : 'Ctrl+A',
            find: this.isMac ? 'Cmd+F' : 'Ctrl+F',
            
            // View menu shortcuts
            reload: this.isMac ? 'Cmd+R' : 'Ctrl+R',
            forceReload: this.isMac ? 'Shift+Cmd+R' : 'Ctrl+Shift+R',
            toggleDevTools: this.isMac ? 'Alt+Cmd+I' : 'Ctrl+Shift+I',
            actualSize: this.isMac ? 'Cmd+0' : 'Ctrl+0',
            zoomIn: this.isMac ? 'Cmd+Plus' : 'Ctrl+Plus',
            zoomOut: this.isMac ? 'Cmd+-' : 'Ctrl+-',
            toggleFullscreen: this.isMac ? 'Ctrl+Cmd+F' : 'F11',
            
            // Window menu shortcuts
            minimize: this.isMac ? 'Cmd+M' : 'Ctrl+M',
            close: this.isMac ? 'Cmd+W' : 'Ctrl+W',
            
            // Trading specific shortcuts
            openScanner: this.isMac ? 'Cmd+1' : 'Ctrl+1',
            openPositions: this.isMac ? 'Cmd+2' : 'Ctrl+2',
            openSignals: this.isMac ? 'Cmd+3' : 'Ctrl+3',
            openLevels: this.isMac ? 'Cmd+4' : 'Ctrl+4',
            
            // Data shortcuts
            refreshData: 'F5',
            connectData: this.isMac ? 'Cmd+D' : 'Ctrl+D',
            exportData: this.isMac ? 'Cmd+E' : 'Ctrl+E'
        };
        
        // Log initialization
        console.log('[MenuBuilder] Initialized for platform:', process.platform);
    }
    
    /**
     * Builds and returns the complete application menu
     * @returns {Menu} The constructed menu
     */
    buildMenu() {
        // Create menu template array
        const template = [];
        
        // macOS specific app menu (first menu)
        if (this.isMac) {
            template.push(this.buildMacAppMenu());
        }
        
        // File menu - always present
        template.push(this.buildFileMenu());
        
        // Edit menu - always present
        template.push(this.buildEditMenu());
        
        // View menu - always present
        template.push(this.buildViewMenu());
        
        // Trading menu - custom for this app
        template.push(this.buildTradingMenu());
        
        // Data menu - custom for this app
        template.push(this.buildDataMenu());
        
        // Window menu - always present
        template.push(this.buildWindowMenu());
        
        // Help menu - always present
        template.push(this.buildHelpMenu());
        
        // Developer menu - only in development mode
        if (this.isDevelopment) {
            template.push(this.buildDeveloperMenu());
        }
        
        // Build menu from template
        this.menu = Menu.buildFromTemplate(template);
        
        // Return the menu
        return this.menu;
    }
    
    /**
     * Builds macOS application menu (first menu on macOS)
     * @returns {Object} Menu template object
     */
    buildMacAppMenu() {
        return {
            // Use app name as label
            label: app.getName(),
            submenu: [
                // About item - shows app info
                {
                    label: `About ${app.getName()}`,
                    role: 'about'  // macOS built-in about dialog
                },
                
                // Separator line
                { type: 'separator' },
                
                // Preferences item
                {
                    label: 'Preferences...',
                    accelerator: this.accelerators.preferences,
                    click: () => this.handlePreferences()
                },
                
                // Separator line
                { type: 'separator' },
                
                // Services submenu (macOS specific)
                {
                    label: 'Services',
                    role: 'services',    // macOS services menu
                    submenu: []          // macOS populates this
                },
                
                // Separator line
                { type: 'separator' },
                
                // Hide app
                {
                    label: `Hide ${app.getName()}`,
                    accelerator: 'Cmd+H',
                    role: 'hide'         // macOS hide app
                },
                
                // Hide others
                {
                    label: 'Hide Others',
                    accelerator: 'Cmd+Shift+H',
                    role: 'hideOthers'   // macOS hide other apps
                },
                
                // Show all
                {
                    label: 'Show All',
                    role: 'unhide'       // macOS unhide all
                },
                
                // Separator line
                { type: 'separator' },
                
                // Quit app
                {
                    label: `Quit ${app.getName()}`,
                    accelerator: this.accelerators.quit,
                    click: () => app.quit()
                }
            ]
        };
    }
    
    /**
     * Builds File menu
     * @returns {Object} Menu template object
     */
    buildFileMenu() {
        // File menu items array
        const fileMenuItems = [
            // New Window
            {
                label: 'New Window',
                accelerator: this.accelerators.newWindow,
                click: () => this.handleNewWindow()
            },
            
            // Separator
            { type: 'separator' },
            
            // Open Workspace
            {
                label: 'Open Workspace...',
                accelerator: this.accelerators.openFile,
                click: () => this.handleOpenWorkspace()
            },
            
            // Save Workspace
            {
                label: 'Save Workspace',
                accelerator: this.accelerators.save,
                click: () => this.handleSaveWorkspace()
            },
            
            // Save Workspace As
            {
                label: 'Save Workspace As...',
                accelerator: this.accelerators.saveAs,
                click: () => this.handleSaveWorkspaceAs()
            },
            
            // Separator
            { type: 'separator' },
            
            // Export submenu
            {
                label: 'Export',
                submenu: [
                    // Export to CSV
                    {
                        label: 'Export Table to CSV...',
                        click: () => this.handleExport('csv')
                    },
                    // Export to JSON
                    {
                        label: 'Export Table to JSON...',
                        click: () => this.handleExport('json')
                    },
                    // Export to Excel
                    {
                        label: 'Export Table to Excel...',
                        click: () => this.handleExport('xlsx')
                    }
                ]
            },
            
            // Separator
            { type: 'separator' }
        ];
        
        // Add preferences on non-macOS platforms
        if (!this.isMac) {
            fileMenuItems.push(
                // Preferences
                {
                    label: 'Preferences...',
                    accelerator: this.accelerators.preferences,
                    click: () => this.handlePreferences()
                },
                // Separator
                { type: 'separator' }
            );
        }
        
        // Add quit on non-macOS platforms
        if (!this.isMac) {
            fileMenuItems.push({
                label: 'Quit',
                accelerator: this.accelerators.quit,
                click: () => app.quit()
            });
        }
        
        // Return file menu
        return {
            label: 'File',
            submenu: fileMenuItems
        };
    }
    
    /**
     * Builds Edit menu
     * @returns {Object} Menu template object
     */
    buildEditMenu() {
        return {
            label: 'Edit',
            submenu: [
                // Undo
                {
                    label: 'Undo',
                    accelerator: this.accelerators.undo,
                    role: 'undo'  // Built-in undo functionality
                },
                
                // Redo
                {
                    label: 'Redo',
                    accelerator: this.accelerators.redo,
                    role: 'redo'  // Built-in redo functionality
                },
                
                // Separator
                { type: 'separator' },
                
                // Cut
                {
                    label: 'Cut',
                    accelerator: this.accelerators.cut,
                    role: 'cut'   // Built-in cut functionality
                },
                
                // Copy
                {
                    label: 'Copy',
                    accelerator: this.accelerators.copy,
                    role: 'copy'  // Built-in copy functionality
                },
                
                // Paste
                {
                    label: 'Paste',
                    accelerator: this.accelerators.paste,
                    role: 'paste' // Built-in paste functionality
                },
                
                // Select All
                {
                    label: 'Select All',
                    accelerator: this.accelerators.selectAll,
                    role: 'selectAll' // Built-in select all
                },
                
                // Separator
                { type: 'separator' },
                
                // Find
                {
                    label: 'Find...',
                    accelerator: this.accelerators.find,
                    click: () => this.handleFind()
                }
            ]
        };
    }
    
    /**
     * Builds View menu
     * @returns {Object} Menu template object
     */
    buildViewMenu() {
        // View menu items
        const viewMenuItems = [
            // Reload
            {
                label: 'Reload',
                accelerator: this.accelerators.reload,
                click: (item, focusedWindow) => {
                    // Reload the focused window if available
                    if (focusedWindow) {
                        focusedWindow.reload();
                    }
                }
            },
            
            // Force Reload
            {
                label: 'Force Reload',
                accelerator: this.accelerators.forceReload,
                click: (item, focusedWindow) => {
                    // Force reload (ignore cache)
                    if (focusedWindow) {
                        focusedWindow.webContents.reloadIgnoringCache();
                    }
                }
            },
            
            // Separator
            { type: 'separator' },
            
            // Actual Size
            {
                label: 'Actual Size',
                accelerator: this.accelerators.actualSize,
                click: (item, focusedWindow) => {
                    // Reset zoom to 100%
                    if (focusedWindow) {
                        focusedWindow.webContents.setZoomLevel(0);
                    }
                }
            },
            
            // Zoom In
            {
                label: 'Zoom In',
                accelerator: this.accelerators.zoomIn,
                click: (item, focusedWindow) => {
                    // Increase zoom level
                    if (focusedWindow) {
                        const currentZoom = focusedWindow.webContents.getZoomLevel();
                        focusedWindow.webContents.setZoomLevel(currentZoom + 0.5);
                    }
                }
            },
            
            // Zoom Out
            {
                label: 'Zoom Out',
                accelerator: this.accelerators.zoomOut,
                click: (item, focusedWindow) => {
                    // Decrease zoom level
                    if (focusedWindow) {
                        const currentZoom = focusedWindow.webContents.getZoomLevel();
                        focusedWindow.webContents.setZoomLevel(currentZoom - 0.5);
                    }
                }
            },
            
            // Separator
            { type: 'separator' },
            
            // Toggle Fullscreen
            {
                label: 'Toggle Fullscreen',
                accelerator: this.accelerators.toggleFullscreen,
                click: (item, focusedWindow) => {
                    // Toggle fullscreen mode
                    if (focusedWindow) {
                        focusedWindow.setFullScreen(!focusedWindow.isFullScreen());
                    }
                }
            }
        ];
        
        // Add developer tools in development or if explicitly enabled
        if (this.isDevelopment) {
            viewMenuItems.push(
                // Separator
                { type: 'separator' },
                
                // Toggle Developer Tools
                {
                    label: 'Toggle Developer Tools',
                    accelerator: this.accelerators.toggleDevTools,
                    click: (item, focusedWindow) => {
                        // Toggle DevTools for focused window
                        if (focusedWindow) {
                            focusedWindow.webContents.toggleDevTools();
                        }
                    }
                }
            );
        }
        
        // Return view menu
        return {
            label: 'View',
            submenu: viewMenuItems
        };
    }
    
    /**
     * Builds Trading menu (custom for this app)
     * @returns {Object} Menu template object
     */
    buildTradingMenu() {
        return {
            label: 'Trading',
            submenu: [
                // Scanner Window
                {
                    label: 'Market Scanner',
                    accelerator: this.accelerators.openScanner,
                    click: () => this.handleOpenTradingWindow('scanner')
                },
                
                // Positions Window
                {
                    label: 'Active Positions',
                    accelerator: this.accelerators.openPositions,
                    click: () => this.handleOpenTradingWindow('positions')
                },
                
                // Signals Window
                {
                    label: 'Trade Signals',
                    accelerator: this.accelerators.openSignals,
                    click: () => this.handleOpenTradingWindow('signals')
                },
                
                // HVN Levels Window
                {
                    label: 'HVN Levels',
                    accelerator: this.accelerators.openLevels,
                    click: () => this.handleOpenTradingWindow('levels')
                },
                
                // Separator
                { type: 'separator' },
                
                // Layout submenu
                {
                    label: 'Layouts',
                    submenu: [
                        // Save Current Layout
                        {
                            label: 'Save Current Layout...',
                            click: () => this.handleSaveLayout()
                        },
                        
                        // Separator
                        { type: 'separator' },
                        
                        // Default layouts
                        {
                            label: 'Default Layout',
                            click: () => this.handleLoadLayout('default')
                        },
                        {
                            label: 'Scanner Focus',
                            click: () => this.handleLoadLayout('scanner')
                        },
                        {
                            label: 'Position Management',
                            click: () => this.handleLoadLayout('positions')
                        },
                        {
                            label: 'Multi-Monitor',
                            click: () => this.handleLoadLayout('multi')
                        }
                    ]
                },
                
                // Separator
                { type: 'separator' },
                
                // Trading Settings
                {
                    label: 'Trading Settings...',
                    click: () => this.handleTradingSettings()
                }
            ]
        };
    }
    
    /**
     * Builds Data menu (custom for this app)
     * @returns {Object} Menu template object
     */
    buildDataMenu() {
        return {
            label: 'Data',
            submenu: [
                // Connect/Disconnect
                {
                    label: 'Connect to Data Feed',
                    accelerator: this.accelerators.connectData,
                    click: () => this.handleDataConnection()
                },
                
                // Refresh Data
                {
                    label: 'Refresh All Data',
                    accelerator: this.accelerators.refreshData,
                    click: () => this.handleRefreshData()
                },
                
                // Separator
                { type: 'separator' },
                
                // Symbol Management
                {
                    label: 'Symbol Lists',
                    submenu: [
                        // Add Symbol
                        {
                            label: 'Add Symbol...',
                            click: () => this.handleAddSymbol()
                        },
                        
                        // Remove Symbol
                        {
                            label: 'Remove Symbol...',
                            click: () => this.handleRemoveSymbol()
                        },
                        
                        // Separator
                        { type: 'separator' },
                        
                        // Import List
                        {
                            label: 'Import Symbol List...',
                            click: () => this.handleImportSymbols()
                        },
                        
                        // Export List
                        {
                            label: 'Export Symbol List...',
                            click: () => this.handleExportSymbols()
                        }
                    ]
                },
                
                // Separator
                { type: 'separator' },
                
                // Cache Management
                {
                    label: 'Cache',
                    submenu: [
                        // Clear Cache
                        {
                            label: 'Clear All Cache',
                            click: () => this.handleClearCache()
                        },
                        
                        // Cache Statistics
                        {
                            label: 'Cache Statistics...',
                            click: () => this.handleCacheStats()
                        }
                    ]
                },
                
                // Separator
                { type: 'separator' },
                
                // Data Settings
                {
                    label: 'Data Settings...',
                    click: () => this.handleDataSettings()
                }
            ]
        };
    }
    
    /**
     * Builds Window menu
     * @returns {Object} Menu template object
     */
    buildWindowMenu() {
        // Window menu items
        const windowMenuItems = [
            // Minimize
            {
                label: 'Minimize',
                accelerator: this.accelerators.minimize,
                role: 'minimize'  // Built-in minimize
            }
        ];
        
        // Add close on non-macOS
        if (!this.isMac) {
            windowMenuItems.push({
                label: 'Close',
                accelerator: this.accelerators.close,
                role: 'close'  // Built-in close
            });
        }
        
        // Add separator
        windowMenuItems.push({ type: 'separator' });
        
        // Add window arrangement options
        windowMenuItems.push(
            // Bring All to Front (macOS)
            ...(this.isMac ? [{
                label: 'Bring All to Front',
                role: 'front'  // macOS bring to front
            }] : []),
            
            // Arrange Windows
            {
                label: 'Arrange Windows',
                submenu: [
                    // Cascade
                    {
                        label: 'Cascade',
                        click: () => this.handleArrangeWindows('cascade')
                    },
                    
                    // Tile Horizontally
                    {
                        label: 'Tile Horizontally',
                        click: () => this.handleArrangeWindows('tileHorizontal')
                    },
                    
                    // Tile Vertically
                    {
                        label: 'Tile Vertically',
                        click: () => this.handleArrangeWindows('tileVertical')
                    }
                ]
            }
        );
        
        // Return window menu
        return {
            label: 'Window',
            role: 'window',     // Platform-specific window menu behavior
            submenu: windowMenuItems
        };
    }
    
    /**
     * Builds Help menu
     * @returns {Object} Menu template object
     */
    buildHelpMenu() {
        return {
            label: 'Help',
            role: 'help',       // Platform-specific help menu behavior
            submenu: [
                // Documentation
                {
                    label: 'Documentation',
                    click: () => {
                        // Open documentation in browser
                        shell.openExternal('https://docs.alpha-v1.com');
                    }
                },
                
                // Keyboard Shortcuts
                {
                    label: 'Keyboard Shortcuts',
                    click: () => this.handleShowShortcuts()
                },
                
                // Separator
                { type: 'separator' },
                
                // Report Issue
                {
                    label: 'Report Issue...',
                    click: () => {
                        // Open issue tracker
                        shell.openExternal('https://github.com/alpha-v1/issues');
                    }
                },
                
                // Separator
                { type: 'separator' },
                
                // Check for Updates
                {
                    label: 'Check for Updates...',
                    click: () => this.handleCheckUpdates()
                },
                
                // About (non-macOS)
                ...(this.isMac ? [] : [
                    { type: 'separator' },
                    {
                        label: 'About',
                        click: () => this.handleAbout()
                    }
                ])
            ]
        };
    }
    
    /**
     * Builds Developer menu (only in development mode)
     * @returns {Object} Menu template object
     */
    buildDeveloperMenu() {
        return {
            label: 'Developer',
            submenu: [
                // Reload without cache
                {
                    label: 'Reload Without Cache',
                    accelerator: 'Shift+F5',
                    click: (item, focusedWindow) => {
                        if (focusedWindow) {
                            focusedWindow.webContents.reloadIgnoringCache();
                        }
                    }
                },
                
                // Open DevTools for all windows
                {
                    label: 'Open All DevTools',
                    click: () => {
                        // Open DevTools for all windows
                        BrowserWindow.getAllWindows().forEach(window => {
                            window.webContents.openDevTools();
                        });
                    }
                },
                
                // Separator
                { type: 'separator' },
                
                // Show App Data
                {
                    label: 'Show App Data Folder',
                    click: () => {
                        // Open app data folder
                        shell.openPath(app.getPath('userData'));
                    }
                },
                
                // Show Logs
                {
                    label: 'Show Logs Folder',
                    click: () => {
                        // Open logs folder
                        shell.openPath(app.getPath('logs'));
                    }
                },
                
                // Separator
                { type: 'separator' },
                
                // Crash test
                {
                    label: 'Test Crash',
                    click: () => {
                        // Intentionally crash for testing
                        process.crash();
                    }
                },
                
                // Memory test
                {
                    label: 'Test Memory Leak',
                    click: () => this.handleMemoryTest()
                }
            ]
        };
    }
    
    // ===== Handler Methods =====
    // These methods handle menu item clicks
    
    /**
     * Handles creating a new window
     */
    async handleNewWindow() {
        console.log('[MenuBuilder] Creating new window');
        
        try {
            // Create new main window
            await this.windowManager.createWindow('main');
        } catch (error) {
            console.error('[MenuBuilder] Failed to create window:', error);
            dialog.showErrorBox('Error', 'Failed to create new window');
        }
    }
    
    /**
     * Handles opening a trading-specific window
     * @param {string} windowType - Type of trading window
     */
    async handleOpenTradingWindow(windowType) {
        console.log(`[MenuBuilder] Opening ${windowType} window`);
        
        try {
            // Check if window already exists
            const existingWindows = this.windowManager.getWindowsByType(windowType);
            
            if (existingWindows.length > 0) {
                // Focus existing window
                existingWindows[0].focus();
            } else {
                // Create new window
                await this.windowManager.createWindow(windowType);
            }
        } catch (error) {
            console.error(`[MenuBuilder] Failed to open ${windowType}:`, error);
            dialog.showErrorBox('Error', `Failed to open ${windowType} window`);
        }
    }
    
    /**
     * Handles preferences dialog
     */
    handlePreferences() {
        console.log('[MenuBuilder] Opening preferences');
        
        // Send message to focused window to open preferences
        const focusedWindow = BrowserWindow.getFocusedWindow();
        if (focusedWindow) {
            focusedWindow.webContents.send('menu:preferences');
        }
    }
    
    /**
     * Handles workspace operations
     */
    async handleOpenWorkspace() {
        console.log('[MenuBuilder] Opening workspace');
        
        // Show file dialog
        const result = await dialog.showOpenDialog({
            title: 'Open Workspace',
            filters: [
                { name: 'Workspace Files', extensions: ['alpha'] },
                { name: 'All Files', extensions: ['*'] }
            ],
            properties: ['openFile']
        });
        
        if (!result.canceled && result.filePaths.length > 0) {
            // Send to main window to load workspace
            const mainWindow = this.windowManager.getWindowsByType('main')[0];
            if (mainWindow) {
                mainWindow.webContents.send('menu:open-workspace', result.filePaths[0]);
            }
        }
    }
    
    /**
     * Handles save workspace
     */
    handleSaveWorkspace() {
        console.log('[MenuBuilder] Saving workspace');
        
        // Send to focused window
        const focusedWindow = BrowserWindow.getFocusedWindow();
        if (focusedWindow) {
            focusedWindow.webContents.send('menu:save-workspace');
        }
    }
    
    /**
     * Handles save workspace as
     */
    async handleSaveWorkspaceAs() {
        console.log('[MenuBuilder] Save workspace as');
        
        // Show save dialog
        const result = await dialog.showSaveDialog({
            title: 'Save Workspace As',
            defaultPath: 'workspace.alpha',
            filters: [
                { name: 'Workspace Files', extensions: ['alpha'] },
                { name: 'All Files', extensions: ['*'] }
            ]
        });
        
        if (!result.canceled) {
            // Send to focused window
            const focusedWindow = BrowserWindow.getFocusedWindow();
            if (focusedWindow) {
                focusedWindow.webContents.send('menu:save-workspace-as', result.filePath);
            }
        }
    }
    
    /**
     * Handles data export
     * @param {string} format - Export format (csv, json, xlsx)
     */
    async handleExport(format) {
        console.log(`[MenuBuilder] Exporting as ${format}`);
        
        // Get appropriate extension
        const extensions = {
            csv: ['csv'],
            json: ['json'],
            xlsx: ['xlsx']
        };
        
        // Show save dialog
        const result = await dialog.showSaveDialog({
            title: `Export Table as ${format.toUpperCase()}`,
            defaultPath: `export.${format}`,
            filters: [
                { name: `${format.toUpperCase()} Files`, extensions: extensions[format] },
                { name: 'All Files', extensions: ['*'] }
            ]
        });
        
        if (!result.canceled) {
            // Send to focused window
            const focusedWindow = BrowserWindow.getFocusedWindow();
            if (focusedWindow) {
                focusedWindow.webContents.send('menu:export', {
                    format,
                    filePath: result.filePath
                });
            }
        }
    }
    
    /**
     * Handles find in page
     */
    handleFind() {
        console.log('[MenuBuilder] Opening find');
        
        // Send to focused window
        const focusedWindow = BrowserWindow.getFocusedWindow();
        if (focusedWindow) {
            focusedWindow.webContents.send('menu:find');
        }
    }
    
    /**
     * Handles layout operations
     */
    handleSaveLayout() {
        console.log('[MenuBuilder] Saving layout');
        
        // Send to focused window
        const focusedWindow = BrowserWindow.getFocusedWindow();
        if (focusedWindow) {
            focusedWindow.webContents.send('menu:save-layout');
        }
    }
    
    /**
     * Handles loading a layout
     * @param {string} layoutName - Name of layout to load
     */
    handleLoadLayout(layoutName) {
        console.log(`[MenuBuilder] Loading layout: ${layoutName}`);
        
        // Send to all windows
        BrowserWindow.getAllWindows().forEach(window => {
            window.webContents.send('menu:load-layout', layoutName);
        });
    }
    
    /**
     * Handles window arrangement
     * @param {string} arrangement - Type of arrangement
     */
    handleArrangeWindows(arrangement) {
        console.log(`[MenuBuilder] Arranging windows: ${arrangement}`);
        
        // Get all windows
        const windows = BrowserWindow.getAllWindows();
        
        // Get primary display
        const { screen } = require('electron');
        const primaryDisplay = screen.getPrimaryDisplay();
        const { width, height } = primaryDisplay.workAreaSize;
        
        // Arrange based on type
        switch (arrangement) {
            case 'cascade':
                // Cascade windows
                windows.forEach((window, index) => {
                    const offset = index * 30;
                    window.setBounds({
                        x: offset,
                        y: offset,
                        width: Math.min(1200, width - offset),
                        height: Math.min(800, height - offset)
                    });
                });
                break;
                
            case 'tileHorizontal':
                // Tile windows horizontally
                const hCount = windows.length;
                const hHeight = Math.floor(height / hCount);
                windows.forEach((window, index) => {
                    window.setBounds({
                        x: 0,
                        y: index * hHeight,
                        width: width,
                        height: hHeight
                    });
                });
                break;
                
            case 'tileVertical':
                // Tile windows vertically
                const vCount = windows.length;
                const vWidth = Math.floor(width / vCount);
                windows.forEach((window, index) => {
                    window.setBounds({
                        x: index * vWidth,
                        y: 0,
                        width: vWidth,
                        height: height
                    });
                });
                break;
        }
    }
    
    /**
     * Handles showing keyboard shortcuts
     */
    handleShowShortcuts() {
        console.log('[MenuBuilder] Showing shortcuts');
        
        // Create or focus shortcuts window
        this.handleOpenTradingWindow('shortcuts');
    }
    
    /**
     * Handles checking for updates
     */
    handleCheckUpdates() {
        console.log('[MenuBuilder] Checking for updates');
        
        // Send to main process to check updates
        const focusedWindow = BrowserWindow.getFocusedWindow();
        if (focusedWindow) {
            focusedWindow.webContents.send('menu:check-updates');
        }
    }
    
    /**
     * Handles about dialog (non-macOS)
     */
    handleAbout() {
        console.log('[MenuBuilder] Showing about dialog');
        
        // Show about dialog
        dialog.showMessageBox({
            type: 'info',
            title: 'About Alpha V1 Trading Tool',
            message: 'Alpha V1 Trading Tool',
            detail: `Version: ${app.getVersion()}\nElectron: ${process.versions.electron}\nNode: ${process.versions.node}`,
            buttons: ['OK']
        });
    }
    
    /**
     * Handles data connection
     */
    handleDataConnection() {
        console.log('[MenuBuilder] Handling data connection');
        
        // Send to all windows
        BrowserWindow.getAllWindows().forEach(window => {
            window.webContents.send('menu:data-connection');
        });
    }
    
    /**
     * Handles refresh data
     */
    handleRefreshData() {
        console.log('[MenuBuilder] Refreshing data');
        
        // Send to all windows
        BrowserWindow.getAllWindows().forEach(window => {
            window.webContents.send('menu:refresh-data');
        });
    }
    
    /**
     * Handles clearing cache
     */
    async handleClearCache() {
        console.log('[MenuBuilder] Clearing cache');
        
        // Confirm with user
        const result = await dialog.showMessageBox({
            type: 'warning',
            title: 'Clear Cache',
            message: 'Are you sure you want to clear all cached data?',
            detail: 'This will remove all locally cached market data.',
            buttons: ['Cancel', 'Clear Cache'],
            defaultId: 0,
            cancelId: 0
        });
        
        if (result.response === 1) {
            // Send to main window
            BrowserWindow.getAllWindows().forEach(window => {
                window.webContents.send('menu:clear-cache');
            });
        }
    }
    
    /**
     * Handles memory test (dev only)
     */
    handleMemoryTest() {
        console.log('[MenuBuilder] Starting memory test');
        
        // Create large array to test memory
        const arrays = [];
        let count = 0;
        
        const interval = setInterval(() => {
            // Allocate 10MB
            arrays.push(new Array(10 * 1024 * 1024 / 8));
            count++;
            
            console.log(`[MenuBuilder] Allocated ${count * 10}MB`);
            
            // Stop after 1GB
            if (count >= 100) {
                clearInterval(interval);
                console.log('[MenuBuilder] Memory test complete');
            }
        }, 100);
    }
    
    /**
     * Updates menu item states dynamically
     * @param {Object} updates - Object with menu item updates
     */
    updateMenuState(updates) {
        // This would be used to enable/disable menu items based on app state
        // Implementation depends on specific requirements
        console.log('[MenuBuilder] Updating menu state:', updates);
    }
}

// Export the MenuBuilder class
module.exports = MenuBuilder;