/**
 * Perspective Integration Bridge
 * 
 * This module handles all communication between Electron and Perspective.
 * It manages table creation, data updates, and view configuration.
 * 
 * Architecture:
 * - Uses Web Workers for Perspective to keep UI thread responsive
 * - Implements binary protocol for high-frequency updates
 * - Manages multiple tables with different schemas
 * - Handles view persistence and restoration
 */

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
    // Perspective worker instance
    worker: null,
    
    // Map of table name to Perspective table instance
    tables: new Map(),
    
    // Map of tab ID to viewer configuration
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
 * Load Perspective library and create worker
 */
async function loadPerspective() {
    console.log('Loading Perspective library... (MOCK VERSION)');
    
    try {
        // Mock the worker
        BridgeState.worker = {
            table: async (schema) => {
                console.log('Mock table created with schema:', schema);
                return {
                    update: async (data) => console.log('Mock update:', data.length, 'rows'),
                    replace: async (data) => console.log('Mock replace:', data.length, 'rows'),
                    size: async () => 0,
                    delete: () => console.log('Mock table deleted')
                };
            }
        };
        
        // Mock perspective-viewer element
        if (!customElements.get('perspective-viewer')) {
            class MockPerspectiveViewer extends HTMLElement {
                constructor() {
                    super();
                    // Don't set innerHTML here - wait for connectedCallback
                }
                
                connectedCallback() {
                    // Set content when element is added to DOM
                    this.innerHTML = '<div style="padding: 20px; color: #888; text-align: center; border: 1px dashed #444;">Mock Perspective Viewer</div>';
                }
                
                async load(table) {
                    console.log('Mock viewer loaded with table');
                    return Promise.resolve();
                }
                
                async save() {
                    return { mock: true };
                }
                
                async restore(config) {
                    console.log('Mock restore:', config);
                    return Promise.resolve();
                }
                
                notifyResize() {
                    console.log('Mock resize notification');
                }
                
                setAttribute(name, value) {
                    super.setAttribute(name, value);
                    console.log(`Mock viewer attribute: ${name} = ${value}`);
                }
            }
            customElements.define('perspective-viewer', MockPerspectiveViewer);
        }
        
        console.log('Mock Perspective loaded successfully');
        return true;
        
    } catch (error) {
        console.error('Failed to load mock Perspective:', error);
        throw error;
    }
}

/**
 * Create a Perspective table with schema
 * @param {string} tableId - Unique table identifier
 * @param {object} config - Table configuration
 */
async function createTable(tableId, config) {
    console.log(`Creating table: ${tableId}`, config);
    
    try {
        // Create table in worker with schema
        const table = await BridgeState.worker.table(config.schema);
        
        // Store table reference
        BridgeState.tables.set(tableId, {
            instance: table,
            config: config,
            rowCount: 0
        });
        
        console.log(`Table created: ${tableId}`);
        return table;
        
    } catch (error) {
        console.error(`Failed to create table ${tableId}:`, error);
        throw error;
    }
}

/**
 * Create a Perspective viewer for a table
 * @param {string} tabId - Tab identifier
 * @param {string} tableId - Table to display
 * @param {object} container - DOM container for viewer
 */
async function createViewer(tabId, tableId, container) {
    console.log(`Creating viewer for tab: ${tabId}, table: ${tableId}`);
    
    try {
        // Get table configuration
        const tableConfig = TABLE_CONFIGS[tableId];
        if (!tableConfig) {
            throw new Error(`Unknown table configuration: ${tableId}`);
        }
        
        // Create viewer element
        const viewer = document.createElement('perspective-viewer');
        viewer.setAttribute('id', `viewer-${tabId}`);
        viewer.style.width = '100%';
        viewer.style.height = '100%';
        
        // Apply dark theme
        viewer.setAttribute('theme', 'Material Dark');
        
        // Configure viewer settings
        viewer.setAttribute('editable', 'false'); // Read-only for trading data
        viewer.setAttribute('column-pivots', '[]'); // No pivoting by default
        viewer.setAttribute('row-pivots', '[]');
        viewer.setAttribute('filters', JSON.stringify(tableConfig.defaultView.filter || []));
        viewer.setAttribute('columns', JSON.stringify(tableConfig.defaultView.columns));
        viewer.setAttribute('sort', JSON.stringify(tableConfig.defaultView.sort || []));
        
        // Add to container
        container.appendChild(viewer);
        
        // Get or create table
        let table = BridgeState.tables.get(tableId);
        if (!table) {
            await createTable(tableId, tableConfig);
            table = BridgeState.tables.get(tableId);
        }
        
        // Load table into viewer
        await viewer.load(table.instance);
        
        // Store viewer reference
        BridgeState.viewers.set(tabId, {
            element: viewer,
            tableId: tableId,
            container: container
        });
        
        // Set up viewer event handlers
        setupViewerEvents(tabId, viewer);
        
        // Load saved view configuration if exists
        await loadViewerState(tabId, viewer);
        
        console.log(`Viewer created for ${tabId}`);
        
        return {
            instance: viewer,
            container: container
        };
        
    } catch (error) {
        console.error(`Failed to create viewer for ${tabId}:`, error);
        throw error;
    }
}

/**
 * Set up event handlers for a viewer
 * @param {string} tabId - Tab identifier
 * @param {HTMLElement} viewer - Perspective viewer element
 */
function setupViewerEvents(tabId, viewer) {
    // Save view configuration when changed
    viewer.addEventListener('perspective-config-update', async (event) => {
        console.log(`View config updated for ${tabId}`);
        
        try {
            // Get current view configuration
            const config = await viewer.save();
            
            // Save to persistent storage
            await BridgeState.config.electronAPI.state.save(
                `perspective.views.${tabId}`,
                config
            );
        } catch (error) {
            console.error(`Failed to save view config for ${tabId}:`, error);
        }
    });
    
    // Handle selection changes
    viewer.addEventListener('perspective-select', (event) => {
        console.log(`Selection in ${tabId}:`, event.detail);
        // Could emit events to main process here
    });
    
    // Handle double-clicks (e.g., to open symbol details)
    viewer.addEventListener('perspective-click', (event) => {
        const { column_names, config, row } = event.detail;
        if (event.detail.config.x === 2) { // Double click
            console.log(`Double-click in ${tabId}:`, { column_names, row });
            // Could open symbol details window here
        }
    });
}

/**
 * Load saved viewer state
 * @param {string} tabId - Tab identifier
 * @param {HTMLElement} viewer - Perspective viewer element
 */
async function loadViewerState(tabId, viewer) {
    try {
        // Load saved view configuration
        const savedConfig = await BridgeState.config.electronAPI.state.load(
            `perspective.views.${tabId}`
        );
        
        if (savedConfig) {
            console.log(`Loading saved view config for ${tabId}`);
            await viewer.restore(savedConfig);
        }
    } catch (error) {
        console.error(`Failed to load view state for ${tabId}:`, error);
    }
}

/**
 * Update table with new data
 * @param {string} tableId - Table to update
 * @param {Array|Object} data - Data to add/update
 * @param {boolean} replace - Replace all data (true) or append (false)
 */
async function updateTable(tableId, data, replace = false) {
    const table = BridgeState.tables.get(tableId);
    if (!table) {
        console.error(`Table not found: ${tableId}`);
        return;
    }
    
    try {
        if (replace) {
            // Replace all data
            await table.instance.replace(data);
        } else {
            // Append/update data
            await table.instance.update(data);
        }
        
        // Update row count
        table.rowCount = await table.instance.size();
        
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
        
        // Apply updates
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
    
    // Sample scanner data
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
        // Add more sample data...
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
        }
    ];
    
    await updateTable('positions', positionsData, true);
}

/**
 * Public initialization function
 * Called from index.js
 */
export async function initialize(config) {
    console.log('Initializing Perspective bridge...');
    
    // Store configuration
    BridgeState.config = config;
    
    try {
        // Load Perspective library
        await loadPerspective();
        
        // Create tables
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
                viewerCount: BridgeState.viewers.size
            })
        };
        
        console.log('Perspective bridge initialized successfully');
        
        // Notify ready callback
        if (config.callbacks.onReady) {
            config.callbacks.onReady();
        }
        
    } catch (error) {
        console.error('Failed to initialize Perspective bridge:', error);
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