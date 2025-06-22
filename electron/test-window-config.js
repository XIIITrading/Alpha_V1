/**
 * Test Window Configuration
 * Run this to verify your window config is correct
 * 
 * Usage: node test-window-config.js
 * Place in: electron/test-window-config.js
 */

const path = require('path');
const fs = require('fs');

console.log('🧪 Testing Window Configuration\n');

try {
    // Load the window config
    const windowConfig = require('./config/window.config.js');
    
    console.log('✅ Window config loaded successfully\n');
    
    // Test the getWindowConfig function if it exists
    if (windowConfig.getWindowConfig) {
        const mainConfig = windowConfig.getWindowConfig('main');
        console.log('📋 Main window configuration:');
        console.log('   Title:', mainConfig.title || 'Not set');
        console.log('   Width:', mainConfig.width);
        console.log('   Height:', mainConfig.height);
        console.log('   File:', mainConfig.file || 'Not set');
        
        if (mainConfig.file) {
            const exists = fs.existsSync(mainConfig.file);
            console.log('   File exists:', exists ? '✅ YES' : '❌ NO');
            
            if (!exists) {
                console.log('\n❌ ERROR: The HTML file specified in window config does not exist!');
                console.log('   Expected at:', mainConfig.file);
                console.log('\n   Make sure src/renderer/index.html exists');
            }
        }
        
        console.log('\n📋 Preload script:');
        if (mainConfig.webPreferences && mainConfig.webPreferences.preload) {
            const preloadPath = mainConfig.webPreferences.preload;
            console.log('   Path:', preloadPath);
            console.log('   Exists:', fs.existsSync(preloadPath) ? '✅ YES' : '❌ NO');
        } else {
            console.log('   ⚠️  No preload script configured');
        }
        
    } else {
        // Fallback for simpler config structure
        console.log('📋 Window configurations found:');
        Object.keys(windowConfig.windows || {}).forEach(winType => {
            const win = windowConfig.windows[winType];
            console.log(`\n   ${winType}:`);
            console.log(`     File: ${win.file || 'Not set'}`);
            
            if (win.file) {
                const resolvedPath = path.isAbsolute(win.file) 
                    ? win.file 
                    : path.join(__dirname, win.file);
                console.log(`     Resolved: ${resolvedPath}`);
                console.log(`     Exists: ${fs.existsSync(resolvedPath) ? '✅' : '❌'}`);
            }
        });
    }
    
    console.log('\n✅ Configuration test complete');
    
} catch (error) {
    console.error('❌ Failed to load window config:', error.message);
    console.log('\nMake sure config/window.config.js exists and is valid JavaScript');
}