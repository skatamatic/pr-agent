// GitHub Bot Filter - Background Service Worker

chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    // Set default preferences on first install
    chrome.storage.sync.set({
      botFilterEnabled: true
    });
    
    // Open welcome page or show notification
    console.log('GitHub Bot Filter installed successfully!');
  } else if (details.reason === 'update') {
    console.log('GitHub Bot Filter updated to version', chrome.runtime.getManifest().version);
  }
});

// Handle extension icon clicks (if no popup is defined)
chrome.action.onClicked.addListener(async (tab) => {
  // This won't be called since we have a popup defined,
  // but keeping it for future extensibility
  if (tab.url.includes('github.com')) {
    // Send message to content script to toggle
    try {
      await chrome.tabs.sendMessage(tab.id, { action: 'toggleFilter' });
    } catch (error) {
      console.error('Error sending message to tab:', error);
    }
  }
});

// Handle messages from content scripts and popup
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'statusUpdate') {
    // Forward status updates to popup if it's open
    // This is handled automatically by Chrome's messaging system
    return true;
  }
  
  // Handle any background processing if needed
  return true;
});

// Update badge based on filter status
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status === 'complete' && tab.url && tab.url.includes('github.com')) {
    // Get current filter status
    const result = await chrome.storage.sync.get(['botFilterEnabled']);
    const enabled = result.botFilterEnabled !== false;
    
    // Update extension badge
    chrome.action.setBadgeText({
      tabId: tabId,
      text: enabled ? 'ON' : 'OFF'
    });
    
    chrome.action.setBadgeBackgroundColor({
      tabId: tabId,
      color: enabled ? '#2da44e' : '#8c959f'
    });
  } else if (tab.url && !tab.url.includes('github.com')) {
    // Clear badge for non-GitHub pages
    chrome.action.setBadgeText({
      tabId: tabId,
      text: ''
    });
  }
}); 