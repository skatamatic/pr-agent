#!/usr/bin/env node
/**
 * Test runner script for dashboard frontend tests
 */
const { spawn } = require('child_process');
const path = require('path');

function runTests() {
  console.log('🧪 Running Dashboard Frontend Tests...');
  console.log('='.repeat(50));
  
  // Change to frontend directory
  const frontendDir = path.dirname(__filename);
  process.chdir(frontendDir);
  
  return new Promise((resolve, reject) => {
    const testProcess = spawn('npm', ['test', '--', '--watchAll=false', '--verbose'], {
      stdio: 'inherit',
      shell: true
    });
    
    testProcess.on('close', (code) => {
      if (code === 0) {
        console.log('\n✅ All tests passed!');
        resolve(true);
      } else {
        console.log(`\n❌ Tests failed with exit code ${code}`);
        resolve(false);
      }
    });
    
    testProcess.on('error', (error) => {
      console.error(`\n❌ Error running tests: ${error}`);
      reject(error);
    });
  });
}

if (require.main === module) {
  runTests()
    .then(success => process.exit(success ? 0 : 1))
    .catch(error => {
      console.error('Test runner error:', error);
      process.exit(1);
    });
}

module.exports = { runTests };

