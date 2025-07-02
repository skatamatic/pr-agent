// GitHub Bot Filter - Popup Script

class PopupController {
  constructor() {
    this.elements = {};
    this.currentTab = null;
    this.init();
  }

  init() {
    this.bindElements();
    this.bindEvents();
    this.loadCurrentStatus();
  }

  bindElements() {
    this.elements = {
      filterStatus: document.getElementById('filter-status'),
      hiddenCount: document.getElementById('hidden-count'),
      toggleButton: document.getElementById('toggle-filter'),
      githubIndicator: document.getElementById('github-indicator'),
      githubStatusText: document.getElementById('github-status-text')
    };
  }

  bindEvents() {
    this.elements.toggleButton.addEventListener('click', () => {
      this.toggleFilter();
    });

    // Listen for status updates from content script
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      if (message.action === 'statusUpdate') {
        this.updateStatus(message.enabled, message.hiddenCount, true);
      }
    });
  }

  async loadCurrentStatus() {
    try {
      // Get current active tab
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      this.currentTab = tab;

      // Check if we're on GitHub
      const isGitHub = tab.url.includes('github.com');
      this.updateGitHubStatus(isGitHub);

      if (isGitHub) {
        // Get status from content script
        const response = await chrome.tabs.sendMessage(tab.id, { action: 'getStatus' });
        if (response) {
          this.updateStatus(response.enabled, response.hiddenCount, response.isGitHubPage);
        }
      } else {
        // Get stored preference even if not on GitHub
        const result = await chrome.storage.sync.get(['botFilterEnabled']);
        const enabled = result.botFilterEnabled !== false;
        this.updateStatus(enabled, 0, false);
      }
    } catch (error) {
      console.error('Error loading status:', error);
      this.updateStatus(false, 0, false);
    }
  }

  async toggleFilter() {
    if (!this.currentTab || !this.currentTab.url.includes('github.com')) {
      return;
    }

    try {
      this.elements.toggleButton.disabled = true;
      this.elements.toggleButton.innerHTML = `
        <span class="button-icon">⏳</span>
        <span class="button-text">Updating...</span>
      `;

      const response = await chrome.tabs.sendMessage(this.currentTab.id, { 
        action: 'toggleFilter' 
      });
      
      if (response && response.success) {
        // Status will be updated via message listener
        setTimeout(() => {
          this.loadCurrentStatus();
        }, 100);
      }
    } catch (error) {
      console.error('Error toggling filter:', error);
      this.loadCurrentStatus();
    }
  }

  updateStatus(enabled, hiddenCount, isActivePage) {
    // Update filter status
    this.elements.filterStatus.textContent = enabled ? 'Hiding Bots' : 'Showing Bots';
    this.elements.filterStatus.className = `status-value ${enabled ? 'enabled' : 'disabled'}`;

    // Update hidden count
    this.elements.hiddenCount.textContent = hiddenCount || 0;

    // Update toggle button
    this.elements.toggleButton.disabled = !isActivePage;
    
    if (isActivePage) {
      this.elements.toggleButton.innerHTML = `
        <span class="button-icon">${enabled ? '👁️' : '🙈'}</span>
        <span class="button-text">${enabled ? 'Show' : 'Hide'} Bots</span>
      `;
    } else {
      this.elements.toggleButton.innerHTML = `
        <span class="button-icon">ℹ️</span>
        <span class="button-text">Navigate to GitHub PR/Issue</span>
      `;
    }
  }

  updateGitHubStatus(isGitHub) {
    if (isGitHub) {
      this.elements.githubIndicator.className = 'indicator active';
      this.elements.githubStatusText.textContent = 'Active on GitHub';
    } else {
      this.elements.githubIndicator.className = 'indicator inactive';
      this.elements.githubStatusText.textContent = 'Not on GitHub';
    }
  }
}

// Initialize popup when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  new PopupController();
}); 