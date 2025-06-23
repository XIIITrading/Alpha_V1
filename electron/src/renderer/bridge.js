/**
 * Perspective Integration Bridge
 * 
 * This module handles all communication between Electron and AG-Grid.
 * It manages table creation, data updates, and view configuration.
 * 
 * Architecture:
 * - Uses AG-Grid Community for high-performance data grids
 * - Implements batching for high-frequency updates
 * - Manages multiple tables with different schemas
 * - Handles view persistence and restoration
 */

import GridManager from './GridManager.js';

// Configuration for Perspective tables
const TABLE_CONFIGS = {
    scanner: {
        name: 'Scanner Results',
        schema: {
            symbol: 'string',           // Stock symbol
            price: 'float',            // Current price
            change: 'float',           // Price change
            changePercent: 'float',    // Percentage change
            volume: 'integer',         // Volume
            relativeVolume: 'float',   // Volume vs average
            marketCap: 'float',        // Market capitalization
            float: 'float',            // Float shares
            shortFloat: 'float',       // Short float percentage
            atr: 'float',              // Average True Range
            beta: 'float',             // Beta coefficient
            rsi: 'float',              // RSI indicator
            alerts: 'integer',         // Number of alerts
            timestamp: 'datetime'      // Last update time
        },
        defaultView: {
            columns: ['symbol', 'price', 'changePercent', 'volume', 'relativeVolume'],
            sort: [['relativeVolume', 'desc']],
            filter: []
        }
    },
    
    positions: {
        name: 'Open Positions',
        schema: {
            symbol: 'string',          // Stock symbol
            side: 'string',            // LONG or SHORT
            quantity: 'integer',       // Share quantity
            entryPrice: 'float',       // Entry price
            currentPrice: 'float',     // Current price
            marketValue: 'float',      // Current market value
            unrealizedPL: 'float',     // Unrealized P&L
            unrealizedPLPercent: 'float', // Unrealized P&L %
            realizedPL: 'float',       // Realized P&L (partial fills)
            stopLoss: 'float',         // Stop loss price
            takeProfit: 'float',       // Take profit price
            duration: 'integer',       // Position duration (seconds)
            timestamp: 'datetime'      // Last update
        },
        defaultView: {
            columns: ['symbol', 'side', 'quantity', 'entryPrice', 'currentPrice', 'unrealizedPL', 'unrealizedPLPercent'],
            sort: [['unrealizedPLPercent', 'desc']],
            filter: []
        }
    },
    
    signals: {
        name: 'Trading Signals',
        schema: {
            id: 'string',              // Unique signal ID
            timestamp: 'datetime',     // Signal generation time
            symbol: 'string',          // Stock symbol
            type: 'string',            // Signal type (ENTRY, EXIT, etc.)
            direction: 'string',       // BUY or SELL
            strength: 'float',         // Signal strength (0-100)
            price: 'float',            // Trigger price
            stopLoss: 'float',         // Suggested stop loss
            takeProfit: 'float',       // Suggested take profit
            confidence: 'float',       // Confidence score
            source: 'string',          // Signal source/strategy
            status: 'string',          // ACTIVE, TRIGGERED, EXPIRED
            notes: 'string'            // Additional notes
        },
        defaultView: {
            columns: ['timestamp', 'symbol', 'type', 'direction', 'price', 'strength', 'status'],
            sort: [['timestamp', 'desc']],
            filter: [['status', '==', 'ACTIVE']]
        }
    },
    
    levels: {
        name: 'Price Levels',
        schema: {
            symbol: 'string',          // Stock symbol
            type: 'string',            // SUPPORT, RESISTANCE, PIVOT
            level: 'float',            // Price level
            strength: 'integer',       // Level strength (1-5)
            touches: 'integer',        // Number of touches
            lastTouch: 'datetime',     // Last touch time
            created: 'datetime',       // When level was identified
            timeframe: 'string',       // Timeframe (5m, 1h, 1d, etc.)
            active: 'boolean'          // Is level still active
        },
        defaultView: {
            columns: ['symbol', 'type', 'level', 'strength', 'touches', 'timeframe'],
            sort: [['symbol', 'asc'], ['level', 'desc']],
            filter: [['active', '==', true]]
        }
    }
};

/**
 * Bridge state management
 */
const BridgeState = {
    // AG-Grid Manager Instance
    gridManager: null,
    
    // Map of table name to table configuration
    tables: new Map(),
    
    // Map of tab ID to grid configuration
    viewers: new Map(),
    
    // Update queue for batching high-frequency updates
    updateQueue: new Map(),
    
    // Performance tracking
    updateCount: 0,
    lastUpdateTime: Date.now(),
    
    // Configuration passed from index.js
    config: null
};

/**
 * Load AG-Grid and create GridManager
 */
async function loadPerspective() {
    console.log('Loading AG-Grid...');
    
    try {
        // Wait for AG-Grid to be available
        let attempts = 0;
        while (typeof agGrid === 'undefined' && attempts < 50) {
            console.log('Waiting for AG-Grid to load...');
            await new Promise(resolve => setTimeout(resolve, 100));
            attempts++;
        }
        
        if (typeof agGrid === 'undefined') {
            throw new Error('AG-Grid failed to load after 5 seconds');
        }
        
        console.log('AG-Grid is available, creating GridManager...');
        
        // Create GridManager instance
        BridgeState.gridManager = new GridManager({
            AppState: BridgeState.config.AppState,
            isDevelopment: BridgeState.config.electronAPI.isDevelopment
        });
        
        console.log('AG-Grid loaded successfully');
        return true;
        
    } catch (error) {
        console.error('Failed to load AG-Grid:', error);
        throw error;
    }
}

/**
 * Create a table configuration
 * @param {string} tableId - Unique table identifier
 * @param {object} config - Table configuration
 */
async function createTable(tableId, config) {
    console.log(`Creating table configuration: ${tableId}`);
    
    try {
        // Store table configuration
        BridgeState.tables.set(tableId, {
            config: config,
            rowCount: 0
        });
        
        console.log(`Table configuration stored: ${tableId}`);
        return true;
        
    } catch (error) {
        console.error(`Failed to create table ${tableId}:`, error);
        throw error;
    }
}

/**
 * Create an AG-Grid viewer for a table
 * @param {string} tabId - Tab identifier
 * @param {string} tableId - Table to display
 * @param {object} container - DOM container for viewer
 */
async function createViewer(tabId, tableId, container) {
    console.log(`Creating AG-Grid viewer for tab: ${tabId}, table: ${tableId}`);
    
    try {
        // Get table configuration
        const tableConfig = TABLE_CONFIGS[tableId];
        if (!tableConfig) {
            throw new Error(`Unknown table configuration: ${tableId}`);
        }
        
        // Create container div for the grid
        const gridContainer = document.createElement('div');
        gridContainer.id = `grid-container-${tabId}`;
        gridContainer.style.width = '100%';
        gridContainer.style.height = '100%';
        container.appendChild(gridContainer);
        
        // Create AG-Grid instance
        const grid = await BridgeState.gridManager.createGrid(
            tableId,
            gridContainer,
            tableConfig
        );
        
        // Store viewer reference
        BridgeState.viewers.set(tabId, {
            element: gridContainer,
            grid: grid,
            tableId: tableId,
            container: container
        });
        
        // Set up event handlers
        setupViewerEvents(tabId, gridContainer);
        
        // Load saved view configuration if exists
        await loadViewerState(tabId, gridContainer);
        
        console.log(`AG-Grid created for ${tabId}`);
        
        return {
            instance: grid,
            container: container
        };
        
    } catch (error) {
        console.error(`Failed to create AG-Grid for ${tabId}:`, error);
        throw error;
    }
}

/**
 * Set up event handlers for a viewer
 * @param {string} tabId - Tab identifier
 * @param {HTMLElement} gridContainer - Grid container element
 */
function setupViewerEvents(tabId, gridContainer) {
    // AG-Grid handles most events internally
    // Add any custom event handlers here if needed
    console.log(`Events configured for ${tabId}`);
}

/**
 * Load saved viewer state
 * @param {string} tabId - Tab identifier
 * @param {HTMLElement} gridContainer - Grid container element
 */
async function loadViewerState(tabId, gridContainer) {
    // AG-Grid state management can be implemented here
    // For now, we'll skip this as AG-Grid handles its own state well
    console.log(`State loading for ${tabId} - not implemented yet`);
}

/**
 * Update table with new data
 * @param {string} tableId - Table to update
 * @param {Array|Object} data - Data to add/update
 * @param {boolean} replace - Replace all data (true) or append (false)
 */
async function updateTable(tableId, data, replace = false) {
    try {
        // Use GridManager's update method
        BridgeState.gridManager.updateGrid(tableId, data, replace);
        
        // Track update count
        BridgeState.updateCount++;
        
    } catch (error) {
        console.error(`Failed to update table ${tableId}:`, error);
    }
}

/**
 * Handle incoming data updates from IPC
 * Implements batching for performance
 * @param {object} update - Update message from main process
 */
function handleDataUpdate(update) {
    const { type, table, data, options = {} } = update;
    
    // Add to update queue for batching
    if (!BridgeState.updateQueue.has(table)) {
        BridgeState.updateQueue.set(table, []);
    }
    
    BridgeState.updateQueue.get(table).push({
        type,
        data,
        options,
        timestamp: Date.now()
    });
    
    // Process queue on next frame
    scheduleUpdateProcessing();
}

/**
 * Process batched updates
 * Uses requestAnimationFrame for smooth updates
 */
let updateScheduled = false;
function scheduleUpdateProcessing() {
    if (updateScheduled) return;
    
    updateScheduled = true;
    requestAnimationFrame(async () => {
        updateScheduled = false;
        await processUpdateQueue();
    });
}

/**
 * Process all queued updates
 */
async function processUpdateQueue() {
    const startTime = performance.now();
    
    for (const [tableId, updates] of BridgeState.updateQueue) {
        if (updates.length === 0) continue;
        
        // Combine updates for efficiency
        const combinedData = [];
        let shouldReplace = false;
        
        for (const update of updates) {
            if (update.type === 'replace') {
                shouldReplace = true;
                combinedData.length = 0; // Clear previous updates
                combinedData.push(...(Array.isArray(update.data) ? update.data : [update.data]));
            } else {
                combinedData.push(...(Array.isArray(update.data) ? update.data : [update.data]));
            }
        }
        
        // Apply updates through GridManager
        await updateTable(tableId, combinedData, shouldReplace);
        
        // Clear processed updates
        updates.length = 0;
    }
    
    // Track latency
    const latency = performance.now() - startTime;
    if (BridgeState.config) {
        BridgeState.config.AppState.metrics.latency = Math.round(latency);
    }
}

/**
 * Create all viewers for tabs
 */
async function createAllViewers() {
    const { AppState, Elements, callbacks } = BridgeState.config;
    
    // Create a viewer for each tab
    for (const tab of AppState.tabs) {
        try {
            // Create container div
            const container = document.createElement('div');
            container.id = `viewer-container-${tab.id}`;
            container.style.width = '100%';
            container.style.height = '100%';
            container.style.display = tab.id === AppState.activeTab ? 'block' : 'none';
            
            // Add to tab content
            Elements.tabContent.appendChild(container);
            
            // Create viewer
            const viewer = await createViewer(tab.id, tab.id, container);
            
            // Notify callback
            if (callbacks.onViewerCreated) {
                callbacks.onViewerCreated(tab.id, viewer);
            }
            
        } catch (error) {
            console.error(`Failed to create viewer for ${tab.id}:`, error);
        }
    }
}

/**
 * Initialize sample data for testing
 * In production, this would come from the data feed
 */
async function loadSampleData() {
    console.log('Loading sample data...');
    
    // Sample scanner data with all required fields
    const scannerData = [
        {
            symbol: 'AAPL',
            price: 182.45,
            change: 2.35,
            changePercent: 1.31,
            volume: 45234567,
            relativeVolume: 1.85,
            marketCap: 2834000000000,
            float: 15500000000,
            shortFloat: 0.89,
            atr: 3.45,
            beta: 1.21,
            rsi: 65.4,
            alerts: 3,
            timestamp: new Date()
        },
        {
            symbol: 'MSFT',
            price: 415.23,
            change: -1.87,
            changePercent: -0.45,
            volume: 23456789,
            relativeVolume: 0.92,
            marketCap: 3089000000000,
            float: 7450000000,
            shortFloat: 0.67,
            atr: 5.23,
            beta: 0.89,
            rsi: 48.2,
            alerts: 1,
            timestamp: new Date()
        },
        {
            symbol: 'GOOGL',
            price: 142.58,
            change: 3.12,
            changePercent: 2.24,
            volume: 32145678,
            relativeVolume: 2.1,
            marketCap: 1823000000000,
            float: 11200000000,
            shortFloat: 1.23,
            atr: 2.89,
            beta: 1.15,
            rsi: 71.3,
            alerts: 5,
            timestamp: new Date()
        },
        {
            symbol: 'TSLA',
            price: 238.92,
            change: -5.43,
            changePercent: -2.22,
            volume: 98765432,
            relativeVolume: 1.67,
            marketCap: 759000000000,
            float: 2710000000,
            shortFloat: 3.45,
            atr: 8.92,
            beta: 1.89,
            rsi: 38.7,
            alerts: 2,
            timestamp: new Date()
        },
        {
            symbol: 'NVDA',
            price: 485.67,
            change: 12.34,
            changePercent: 2.61,
            volume: 67890123,
            relativeVolume: 3.2,
            marketCap: 1193000000000,
            float: 2460000000,
            shortFloat: 1.89,
            atr: 11.23,
            beta: 1.67,
            rsi: 72.5,
            alerts: 4,
            timestamp: new Date()
        }
    ];
    
    await updateTable('scanner', scannerData, true);
    
    // Sample positions data
    const positionsData = [
        {
            symbol: 'AAPL',
            side: 'LONG',
            quantity: 100,
            entryPrice: 180.10,
            currentPrice: 182.45,
            marketValue: 18245,
            unrealizedPL: 235,
            unrealizedPLPercent: 1.31,
            realizedPL: 0,
            stopLoss: 178.00,
            takeProfit: 185.00,
            duration: 3600,
            timestamp: new Date()
        },
        {
            symbol: 'TSLA',
            side: 'SHORT',
            quantity: 50,
            entryPrice: 245.00,
            currentPrice: 238.92,
            marketValue: 11946,
            unrealizedPL: 304,
            unrealizedPLPercent: 2.48,
            realizedPL: 0,
            stopLoss: 250.00,
            takeProfit: 230.00,
            duration: 7200,
            timestamp: new Date()
        }
    ];
    
    await updateTable('positions', positionsData, true);
    
    // Sample signals data
    const signalsData = [
        {
            id: 'sig-001',
            timestamp: new Date(),
            symbol: 'NVDA',
            type: 'ENTRY',
            direction: 'BUY',
            strength: 85,
            price: 485.50,
            stopLoss: 478.00,
            takeProfit: 498.00,
            confidence: 0.89,
            source: 'Momentum Scanner',
            status: 'ACTIVE',
            notes: 'Strong breakout on volume'
        },
        {
            id: 'sig-002',
            timestamp: new Date(Date.now() - 300000), // 5 minutes ago
            symbol: 'AMD',
            type: 'ENTRY',
            direction: 'BUY',
            strength: 72,
            price: 122.30,
            stopLoss: 120.00,
            takeProfit: 126.00,
            confidence: 0.76,
            source: 'Pattern Recognition',
            status: 'ACTIVE',
            notes: 'Bull flag formation'
        }
    ];
    
    await updateTable('signals', signalsData, true);
    
    // Sample levels data
    const levelsData = [
        {
            symbol: 'SPY',
            type: 'SUPPORT',
            level: 428.50,
            strength: 4,
            touches: 5,
            lastTouch: new Date(Date.now() - 3600000), // 1 hour ago
            created: new Date(Date.now() - 86400000), // 1 day ago
            timeframe: '1h',
            active: true
        },
        {
            symbol: 'SPY',
            type: 'RESISTANCE',
            level: 432.75,
            strength: 5,
            touches: 7,
            lastTouch: new Date(Date.now() - 1800000), // 30 minutes ago
            created: new Date(Date.now() - 172800000), // 2 days ago
            timeframe: '4h',
            active: true
        }
    ];
    
    await updateTable('levels', levelsData, true);
}

/**
 * Public initialization function
 * Called from index.js
 */
export async function initialize(config) {
    console.log('Initializing AG-Grid bridge...');
    
    // Store configuration
    BridgeState.config = config;
    
    try {
        // Load AG-Grid
        await loadPerspective();
        
        // Create table configurations
        for (const [tableId, tableConfig] of Object.entries(TABLE_CONFIGS)) {
            await createTable(tableId, tableConfig);
        }
        
        // Create viewers
        await createAllViewers();
        
        // Load sample data for testing
        if (config.electronAPI.isDevelopment) {
            await loadSampleData();
        }
        
        // Expose bridge API to window for debugging
        window.PerspectiveBridge = {
            handleDataUpdate,
            updateTable,
            getTables: () => BridgeState.tables,
            getViewers: () => BridgeState.viewers,
            getMetrics: () => ({
                updateCount: BridgeState.updateCount,
                tableCount: BridgeState.tables.size,
                viewerCount: BridgeState.viewers.size,
                // Add GridManager metrics
                ...BridgeState.gridManager?.getMetrics()
            }),
            // Add GridManager reference for debugging
            gridManager: BridgeState.gridManager
        };
        
        console.log('AG-Grid bridge initialized successfully');
        
        // Notify ready callback
        if (config.callbacks.onReady) {
            config.callbacks.onReady();
        }
        
    } catch (error) {
        console.error('Failed to initialize AG-Grid bridge:', error);
        if (config.callbacks.onError) {
            config.callbacks.onError(error);
        }
        throw error;
    }
}

/**
 * Export individual functions for testing
 */
export {
    createTable,
    createViewer,
    updateTable,
    handleDataUpdate
};