// electron/test-polygon-integration.js
/**
 * Test script for PolygonBridge integration
 * Run this after starting your Electron app to verify the connection
 */

const { app } = require('electron');

async function testPolygonIntegration() {
    console.log('=== Testing Polygon Integration ===\n');
    
    // Wait for app to be ready
    await app.whenReady();
    
    // Import the bridge from main
    const { polygonBridge } = require('./main');
    
    if (!polygonBridge) {
        console.error('❌ PolygonBridge not found in main.js exports');
        return;
    }
    
    // Test 1: Check initialization
    console.log('1. Checking bridge initialization...');
    const status = polygonBridge.getStatus();
    console.log('Bridge Status:', JSON.stringify(status, null, 2));
    
    if (!status.initialized) {
        console.error('❌ Bridge not initialized');
        return;
    }
    console.log('✅ Bridge initialized\n');
    
    // Test 2: Test REST API call
    console.log('2. Testing REST API call...');
    try {
        const testData = await polygonBridge.fetchPolygonData({
            endpoint: '/latest/AAPL',
            method: 'GET'
        });
        console.log('✅ REST API working:', testData);
    } catch (error) {
        console.error('❌ REST API failed:', error.message);
    }
    console.log('');
    
    // Test 3: Test WebSocket connection
    console.log('3. Testing WebSocket connection...');
    try {
        // Create a test WebSocket connection
        const testClientId = 'test-client-001';
        const ws = await polygonBridge.createWebSocketConnection(testClientId);
        
        if (ws && ws.readyState === 1) { // 1 = OPEN
            console.log('✅ WebSocket connected');
            
            // Send a test subscription
            ws.send(JSON.stringify({
                action: 'subscribe',
                symbols: ['AAPL'],
                channels: ['T']
            }));
            
            // Wait for response
            await new Promise(resolve => {
                ws.once('message', (data) => {
                    const message = JSON.parse(data.toString());
                    console.log('✅ Received WebSocket message:', message.type);
                    resolve();
                });
                
                // Timeout after 5 seconds
                setTimeout(resolve, 5000);
            });
            
            // Close test connection
            ws.close();
            polygonBridge.wsConnections.delete(testClientId);
            
        } else {
            console.error('❌ WebSocket connection failed');
        }
    } catch (error) {
        console.error('❌ WebSocket test failed:', error.message);
    }
    console.log('');
    
    // Test 4: Test IPC integration
    console.log('4. Testing IPC integration...');
    const { ipcHandler } = require('./main');
    
    if (ipcHandler) {
        // Simulate a data request event
        const testOperationId = `test-op-${Date.now()}`;
        
        // Set up response listener
        const responsePromise = new Promise((resolve) => {
            ipcHandler.once(`data-response-${testOperationId}`, (response) => {
                resolve(response);
            });
        });
        
        // Emit test request
        ipcHandler.emit('data-request', {
            operationId: testOperationId,
            source: 'polygon',
            params: {
                endpoint: '/cache/stats',
                method: 'GET'
            },
            windowId: 'test'
        });
        
        // Wait for response
        const response = await Promise.race([
            responsePromise,
            new Promise(resolve => setTimeout(() => resolve({ timeout: true }), 5000))
        ]);
        
        if (response.timeout) {
            console.error('❌ IPC request timed out');
        } else if (response.success) {
            console.log('✅ IPC integration working');
        } else {
            console.error('❌ IPC request failed:', response.error);
        }
    } else {
        console.error('❌ IPCHandler not found');
    }
    console.log('');
    
    // Test 5: Check server health
    console.log('5. Checking server health...');
    try {
        const healthResponse = await fetch(`${polygonBridge.serverUrl}/health`);
        const health = await healthResponse.json();
        console.log('✅ Server health:', health);
    } catch (error) {
        console.error('❌ Server health check failed:', error.message);
    }
    
    console.log('\n=== Integration Test Complete ===');
    
    // Final status
    const finalStatus = polygonBridge.getStatus();
    console.log('\nFinal Bridge Status:');
    console.log(`- Initialized: ${finalStatus.initialized ? '✅' : '❌'}`);
    console.log(`- WebSocket Connections: ${finalStatus.websocketConnections}`);
    console.log(`- Active Subscriptions: ${finalStatus.activeSubscriptions}`);
    console.log(`- Server Running: ${finalStatus.serverRunning ? '✅' : '❌'}`);
}

// Run tests if this file is executed directly
if (require.main === module) {
    testPolygonIntegration()
        .then(() => {
            console.log('\nTest completed');
            process.exit(0);
        })
        .catch((error) => {
            console.error('\nTest failed:', error);
            process.exit(1);
        });
}

module.exports = { testPolygonIntegration };