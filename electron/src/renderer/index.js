/**
 * Main Renderer Process Entry Point
 * 
 * This file initializes the renderer process, sets up the UI,
 * and coordinates between Electron and Perspective
 */

// The electronAPI object is injected by preload.js
// Use directly from window to avoid redeclaration conflicts

/**
 * Application state manager for the renderer
 * Keeps track of UI state, active tabs, connections, etc.
 */
const AppState = {
    // Connection status to data sources
    connectionStatus: 'disconnected', // 'disconnected', 'connecting', 'connected', 'error'
    
    // Currently active tab
    activeTab: 'scanner',
    
    // Registry of all Perspective viewers
    viewers: new Map(),
    
    // Performance metrics
    metrics: {
        fps: 0,
        memory: 0,
        updatesPerSecond: 0,
        latency: 0,
        lastUpdate: Date.now()
    },
    
    // Tab configuration
    tabs: [
        { id: 'scanner', name: 'Scanner', icon: '📊' },
        { id: 'positions', name: 'Positions', icon: '💼' },
        { id: 'signals', name: 'Signals', icon: '🎯' },
        { id: 'levels', name: 'Levels', icon: '📈' }
    ]
};

/**
 * DOM element references
 * Cached for performance to avoid repeated querySelector calls
 */
const Elements = {
    // Screens
    loading: null,
    error: null,
    app: null,
    
    // Status elements
    connectionStatus: null,
    connectionText: null,
    marketStatus: null,
    
    // Tab elements
    tabHeader: null,
    tabContent: null,
    
    // Footer metrics
    fps: null,
    memory: null,
    updatesPerSec: null,
    latency: null,
    currentTime: null,
    
    // Error display
    errorDetails: null
};

/**
 * Initialize all DOM element references
 * Called once on page load
 */
function initializeElements() {
    // Cache all frequently accessed DOM elements
    Elements.loading = document.getElementById('loading');
    Elements.error = document.getElementById('error');
    Elements.app = document.getElementById('app');
    Elements.connectionStatus = document.getElementById('connection-status');
    Elements.connectionText = document.getElementById('connection-text');
    Elements.marketStatus = document.getElementById('market-status');
    Elements.tabHeader = document.getElementById('tab-header');
    Elements.tabContent = document.getElementById('tab-content');
    Elements.fps = document.getElementById('fps');
    Elements.memory = document.getElementById('memory');
    Elements.updatesPerSec = document.getElementById('updates-per-sec');
    Elements.latency = document.getElementById('latency');
    Elements.currentTime = document.getElementById('current-time');
    Elements.errorDetails = document.getElementById('error-details');
}

/**
 * Apply platform-specific styling
 * Different platforms have different UI conventions
 */
function applyPlatformStyles() {
    // Add platform class to body for CSS styling
    document.body.classList.add(`platform-${platform.name}`);
    
    // Log platform info for debugging
    console.log(`Running on ${platform.name} (${platform.arch})`);
    console.log(`Electron: ${platform.versions.electron}`);
    console.log(`Chrome: ${platform.versions.chrome}`);
    console.log(`Node: ${platform.versions.node}`);
}

/**
 * Show error screen with details
 * @param {string} message - User-friendly error message
 * @param {Error|string} error - Detailed error information
 */
function showError(message, error) {
    console.error('Application error:', message, error);
    
    // Hide loading and app screens
    Elements.loading.style.display = 'none';
    Elements.app.classList.add('hidden');
    
    // Show error screen
    Elements.error.style.display = 'flex';
    
    // Update error message
    const errorMessage = Elements.error.querySelector('.error-message');
    errorMessage.textContent = message;
    
    // Show error details (stack trace, etc.)
    if (error) {
        Elements.errorDetails.textContent = error.stack || error.toString();
    }
    
    // Log to main process for debugging
    electronAPI.dev.log('error', message, { error: error?.toString() });
}

/**
 * Hide loading screen and show main app
 */
function showApp() {
    // Fade out loading screen
    Elements.loading.style.opacity = '0';
    
    // After fade completes, hide loading and show app
    setTimeout(() => {
        Elements.loading.style.display = 'none';
        Elements.app.classList.remove('hidden');
    }, 300);
}

/**
 * Create tabs in the header
 */
function createTabs() {
    // Clear existing tabs
    Elements.tabHeader.innerHTML = '';
    
    // Create tab buttons
    AppState.tabs.forEach(tab => {
        const button = document.createElement('button');
        button.className = 'tab';
        button.id = `tab-${tab.id}`;
        button.innerHTML = `${tab.icon} ${tab.name}`;
        
        // Mark active tab
        if (tab.id === AppState.activeTab) {
            button.classList.add('active');
        }
        
        // Handle tab clicks
        button.addEventListener('click', () => switchTab(tab.id));
        
        Elements.tabHeader.appendChild(button);
    });
}

/**
 * Switch to a different tab
 * @param {string} tabId - ID of tab to switch to
 */
async function switchTab(tabId) {
    // Don't switch if already active
    if (AppState.activeTab === tabId) return;
    
    console.log(`Switching from ${AppState.activeTab} to ${tabId}`);
    
    // Update active tab state
    const previousTab = AppState.activeTab;
    AppState.activeTab = tabId;
    
    // Update tab button styles
    document.querySelectorAll('.tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.getElementById(`tab-${tabId}`).classList.add('active');
    
    // Hide all viewers
    AppState.viewers.forEach((viewer, id) => {
        viewer.container.style.display = 'none';
    });
    
    // Show active viewer
    const activeViewer = AppState.viewers.get(tabId);
    if (activeViewer) {
        activeViewer.container.style.display = 'block';
        // Notify Perspective to recalculate layout
        activeViewer.instance?.notifyResize();
    }
    
    // Save tab preference
    await electronAPI.state.save('ui.activeTab', tabId);
    
    // Log tab switch for analytics
    electronAPI.dev.log('info', 'Tab switched', { from: previousTab, to: tabId });
}

/**
 * Update connection status indicator
 * @param {string} status - Connection status
 * @param {string} [text] - Optional status text
 */
function updateConnectionStatus(status, text) {
    AppState.connectionStatus = status;
    
    // Update status dot color
    Elements.connectionStatus.className = `status-dot ${status}`;
    
    // Update status text
    if (text) {
        Elements.connectionText.textContent = text;
    } else {
        // Default text based on status
        const statusText = {
            'disconnected': 'Disconnected',
            'connecting': 'Connecting...',
            'connected': 'Connected',
            'error': 'Connection Error'
        };
        Elements.connectionText.textContent = statusText[status] || status;
    }
}

/**
 * Update market status indicator
 * @param {string} status - Market status (Open, Closed, Pre-Market, etc.)
 */
function updateMarketStatus(status) {
    Elements.marketStatus.textContent = status;
    
    // Color code based on status
    if (status === 'Open') {
        Elements.marketStatus.style.color = '#00ff00';
    } else if (status === 'Pre-Market' || status === 'After-Hours') {
        Elements.marketStatus.style.color = '#ffaa00';
    } else {
        Elements.marketStatus.style.color = '#888';
    }
}

/**
 * Update performance metrics in footer
 */
function updateMetrics() {
    // Update FPS
    Elements.fps.textContent = Math.round(AppState.metrics.fps);
    
    // Update memory usage
    Elements.memory.textContent = `${Math.round(AppState.metrics.memory)} MB`;
    
    // Update updates per second
    Elements.updatesPerSec.textContent = AppState.metrics.updatesPerSecond;
    
    // Update latency
    Elements.latency.textContent = `${AppState.metrics.latency}ms`;
    
    // Color code metrics based on performance
    if (AppState.metrics.fps < 30) {
        Elements.fps.style.color = '#ff3333';
    } else if (AppState.metrics.fps < 50) {
        Elements.fps.style.color = '#ffaa00';
    } else {
        Elements.fps.style.color = '#00ff00';
    }
}

/**
 * Calculate FPS using requestAnimationFrame
 */
function startFPSMonitor() {
    let lastTime = performance.now();
    let frames = 0;
    
    function measureFPS() {
        frames++;
        
        const currentTime = performance.now();
        const delta = currentTime - lastTime;
        
        // Update FPS every second
        if (delta >= 1000) {
            AppState.metrics.fps = Math.round((frames * 1000) / delta);
            frames = 0;
            lastTime = currentTime;
            updateMetrics();
        }
        
        requestAnimationFrame(measureFPS);
    }
    
    requestAnimationFrame(measureFPS);
}

/**
 * Update current time in footer
 */
function startClock() {
    function updateTime() {
        const now = new Date();
        const hours = now.getHours().toString().padStart(2, '0');
        const minutes = now.getMinutes().toString().padStart(2, '0');
        const seconds = now.getSeconds().toString().padStart(2, '0');
        Elements.currentTime.textContent = `${hours}:${minutes}:${seconds}`;
    }
    
    updateTime(); // Initial update
    setInterval(updateTime, 1000); // Update every second
}

/**
 * Get memory usage from main process
 */
async function updateMemoryUsage() {
    try {
        const metrics = await electronAPI.dev.getMetrics();
        AppState.metrics.memory = metrics.memory || 0;
    } catch (error) {
        console.error('Failed to get memory metrics:', error);
    }
}

/**
 * Set up IPC event listeners for data updates
 */
function setupIPCListeners() {
    // Listen for state changes from other windows
    const unsubscribeState = electronAPI.state.onChange((data) => {
        console.log('State changed:', data);
        // Handle state changes here
    });
    
    // Listen for data updates
    const unsubscribeData = electronAPI.data.onUpdate((data) => {
        // Track update rate
        AppState.metrics.updatesPerSecond++;
        
        // Forward to bridge for Perspective processing
        if (window.PerspectiveBridge) {
            window.PerspectiveBridge.handleDataUpdate(data);
        }
    });
    
    // Listen for app events
    const unsubscribeReady = electronAPI.app.on('ready', () => {
        console.log('App ready event received');
    });
    
    const unsubscribeFocus = electronAPI.app.on('focus-change', (focused) => {
        console.log('Window focus changed:', focused);
    });
    
    // Store unsubscribe functions for cleanup
    window.addEventListener('beforeunload', () => {
        unsubscribeState();
        unsubscribeData();
        unsubscribeReady();
        unsubscribeFocus();
    });
}

/**
 * Load saved UI preferences
 */
async function loadPreferences() {
    try {
        // Load active tab preference
        const savedTab = await electronAPI.state.load('ui.activeTab', 'scanner');
        if (AppState.tabs.some(tab => tab.id === savedTab)) {
            AppState.activeTab = savedTab;
        }
        
        // Load other preferences here
        console.log('Loaded preferences:', { activeTab: AppState.activeTab });
    } catch (error) {
        console.error('Failed to load preferences:', error);
    }
}

/**
 * Initialize Perspective bridge
 */
async function initializePerspective() {
    try {
        console.log('Initializing Perspective bridge...');
        
        // Update loading text
        const loadingText = Elements.loading.querySelector('.loading-subtext');
        loadingText.textContent = 'Loading Perspective tables...';
        
        // Dynamically load the bridge module
        const bridgeModule = await import('./bridge.js');
        
        // Initialize the bridge
        await bridgeModule.initialize({
            electronAPI,
            AppState,
            Elements,
            callbacks: {
                onViewerCreated: (tabId, viewer) => {
                    console.log(`Viewer created for ${tabId}`);
                    AppState.viewers.set(tabId, viewer);
                },
                onError: (error) => {
                    showError('Perspective initialization failed', error);
                },
                onReady: () => {
                    console.log('Perspective bridge ready');
                    showApp();
                }
            }
        });
        
    } catch (error) {
        showError('Failed to load Perspective module', error);
    }
}

/**
 * Main initialization function
 * Called when DOM is ready
 */
async function initialize() {
    try {
        console.log('Initializing Alpha V1 Trading Tool...');
        
        // Initialize DOM elements
        initializeElements();
        
        // Apply platform-specific styles
        applyPlatformStyles();
        
        // Load saved preferences
        await loadPreferences();
        
        // Create UI elements
        createTabs();
        
        // Set up monitoring
        startFPSMonitor();
        startClock();
        
        // Update memory usage every 5 seconds
        setInterval(updateMemoryUsage, 5000);
        updateMemoryUsage(); // Initial update
        
        // Reset update counter every second
        setInterval(() => {
            updateMetrics();
            AppState.metrics.updatesPerSecond = 0;
        }, 1000);
        
        // Set up IPC listeners
        setupIPCListeners();
        
        // Get app info
        const appInfo = await electronAPI.app.getInfo();
        console.log('App info:', appInfo);
        
        // Update initial status
        updateConnectionStatus('disconnected');
        updateMarketStatus('Loading...');
        
        // Initialize Perspective (this will show the app when ready)
        await initializePerspective();
        
    } catch (error) {
        showError('Failed to initialize application', error);
    }
}

/**
 * Handle window resize events
 */
let resizeTimeout;
window.addEventListener('resize', () => {
    // Debounce resize events
    clearTimeout(resizeTimeout);
    resizeTimeout = setTimeout(() => {
        // Resize all grids when window resizes
        if (window.PerspectiveBridge && window.PerspectiveBridge.gridManager) {
            window.PerspectiveBridge.gridManager.resizeGrids();
        }
    }, 250);
});

/**
 * Handle tab visibility changes to resize grids
 */
document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
        // Resize grids when tab becomes visible
        setTimeout(() => {
            if (window.PerspectiveBridge && window.PerspectiveBridge.gridManager) {
                window.PerspectiveBridge.gridManager.resizeGrids();
            }
        }, 100);
    }
});

/**
 * Start initialization when DOM is ready
 */
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initialize);
} else {
    // DOM is already ready
    initialize();
}

/**
 * Handle keyboard shortcuts
 */
document.addEventListener('keydown', async (event) => {
    // Ctrl/Cmd + number to switch tabs
    if ((event.ctrlKey || event.metaKey) && event.key >= '1' && event.key <= '4') {
        const tabIndex = parseInt(event.key) - 1;
        if (tabIndex < AppState.tabs.length) {
            await switchTab(AppState.tabs[tabIndex].id);
        }
    }
    
    // Ctrl/Cmd + N for new window
    if ((event.ctrlKey || event.metaKey) && event.key === 'n') {
        await electronAPI.window.create('scanner');
    }
    
    // F11 for fullscreen
    if (event.key === 'F11') {
        // This would be handled by the main process
        electronAPI.app.toggleFullscreen();
    }
});

/**
 * Handle window unload
 */
window.addEventListener('beforeunload', () => {
    console.log('Window closing, cleaning up...');
    
    // Save any pending state
    electronAPI.state.save('ui.lastClosed', Date.now());
    
    // Clean up Perspective viewers
    AppState.viewers.forEach(viewer => {
        if (viewer.instance?.delete) {
            viewer.instance.delete();
        }
    });
});