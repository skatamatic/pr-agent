// GitHub Bot Comment Filter - Content Script

class GitHubBotFilter {
  constructor() {
    this.isEnabled = true;
    this.hiddenCommentsCount = 0;
    this.observer = null;
    this.init();
  }

  async init() {
    // Load user preferences
    const result = await chrome.storage.sync.get(['botFilterEnabled']);
    this.isEnabled = result.botFilterEnabled !== false; // Default to true

    // Apply filter on page load
    this.applyFilter();

    // Watch for dynamic content changes (GitHub uses AJAX)
    this.setupObserver();

    // Listen for messages from popup
    chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
      if (request.action === 'toggleFilter') {
        this.toggleFilter();
        sendResponse({ success: true, hiddenCount: this.hiddenCommentsCount });
      } else if (request.action === 'getStatus') {
        sendResponse({ 
          enabled: this.isEnabled, 
          hiddenCount: this.hiddenCommentsCount,
          isGitHubPage: this.isGitHubPage()
        });
      }
    });

    // Add toggle button to GitHub interface
    this.addToggleButton();
  }

  isGitHubPage() {
    return window.location.hostname === 'github.com' && 
           (window.location.pathname.includes('/pull/') || 
            window.location.pathname.includes('/issues/'));
  }

  setupObserver() {
    // Watch for new comments being added dynamically
    this.observer = new MutationObserver((mutations) => {
      let shouldReapply = false;
      mutations.forEach((mutation) => {
        if (mutation.addedNodes.length > 0) {
          mutation.addedNodes.forEach((node) => {
            if (node.nodeType === Node.ELEMENT_NODE && 
                (node.classList?.contains('js-comment-container') ||
                 node.querySelector?.('.js-comment-container'))) {
              shouldReapply = true;
            }
          });
        }
      });
      
      if (shouldReapply) {
        setTimeout(() => this.applyFilter(), 100);
      }
    });

    this.observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }

  getBotSelectors() {
    return [
      // GitHub Actions bot
      '[data-hovercard-type="user"][data-hovercard-url*="github-actions%5Bbot%5D"]',
      '[data-hovercard-type="user"][data-hovercard-url*="github-actions[bot]"]',
      
      // General bot patterns
      '[data-hovercard-url*="%5Bbot%5D"]',
      '[data-hovercard-url*="[bot]"]',
      
      // PR-Agent specific
      'a[href*="/codiumai-pr-agent-pro"]',
      'a[href*="/codiumai-pr-agent"]',
      
      // Other common bots
      '[data-hovercard-url*="dependabot"]',
      '[data-hovercard-url*="renovate"]',
      '[data-hovercard-url*="codecov"]',
      
      // Bot user types
      '.Timeline-Item .author[data-hovercard-type="user"] img[alt*="[bot]"]'
    ];
  }

  findBotComments() {
    const botComments = [];
    const selectors = this.getBotSelectors();
    
    selectors.forEach(selector => {
      const botElements = document.querySelectorAll(selector);
      botElements.forEach(element => {
        // Find the comment container
        const commentContainer = element.closest('.js-comment-container') || 
                                element.closest('.TimelineItem') ||
                                element.closest('.timeline-comment-wrapper');
        
        if (commentContainer && !botComments.includes(commentContainer)) {
          botComments.push(commentContainer);
        }
      });
    });

    // Also check for bot comments by looking at usernames in comment headers
    const commentHeaders = document.querySelectorAll('.timeline-comment-header .author, .discussion-item-header .author');
    commentHeaders.forEach(header => {
      const username = header.textContent.trim();
      if (username.includes('[bot]') || username.includes('bot')) {
        const commentContainer = header.closest('.js-comment-container') || 
                                header.closest('.TimelineItem') ||
                                header.closest('.timeline-comment-wrapper');
        if (commentContainer && !botComments.includes(commentContainer)) {
          botComments.push(commentContainer);
        }
      }
    });

    return botComments;
  }

  applyFilter() {
    const botComments = this.findBotComments();
    
    botComments.forEach(comment => {
      if (this.isEnabled) {
        comment.style.display = 'none';
        comment.setAttribute('data-bot-filter-hidden', 'true');
      } else {
        comment.style.display = '';
        comment.removeAttribute('data-bot-filter-hidden');
      }
    });

    this.hiddenCommentsCount = this.isEnabled ? botComments.length : 0;
    this.updateToggleButton();
    
    // Send update to popup if it's open
    chrome.runtime.sendMessage({
      action: 'statusUpdate',
      hiddenCount: this.hiddenCommentsCount,
      enabled: this.isEnabled
    }).catch(() => {}); // Ignore errors if popup is closed
  }

  async toggleFilter() {
    this.isEnabled = !this.isEnabled;
    
    // Save preference
    await chrome.storage.sync.set({ botFilterEnabled: this.isEnabled });
    
    this.applyFilter();
  }

  addToggleButton() {
    if (!this.isGitHubPage()) return;

    // Remove existing button if any
    const existingButton = document.getElementById('bot-filter-toggle');
    if (existingButton) existingButton.remove();

    // Create toggle button
    const button = document.createElement('button');
    button.id = 'bot-filter-toggle';
    button.className = 'btn btn-sm';
    button.setAttribute('type', 'button');
    button.style.cssText = `
      margin-left: 8px;
      background: var(--button-default-bgColor-rest, #f6f8fa);
      border: 1px solid var(--button-default-borderColor-rest, #d0d7de);
      color: var(--button-default-fgColor-rest, #24292f);
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
    `;
    
    button.addEventListener('click', () => this.toggleFilter());
    button.addEventListener('mouseenter', () => {
      button.style.backgroundColor = 'var(--button-default-bgColor-hover, #f3f4f6)';
      button.style.borderColor = 'var(--button-default-borderColor-hover, #d0d7de)';
    });
    button.addEventListener('mouseleave', () => {
      button.style.backgroundColor = 'var(--button-default-bgColor-rest, #f6f8fa)';
      button.style.borderColor = 'var(--button-default-borderColor-rest, #d0d7de)';
    });

    // Find a good place to insert the button
    const insertionPoints = [
      '.gh-header-actions', // PR/Issue header actions
      '.discussion-sidebar-item:first-child', // Sidebar
      '.timeline-comment-actions' // Comment actions
    ];

    for (const selector of insertionPoints) {
      const container = document.querySelector(selector);
      if (container) {
        container.appendChild(button);
        break;
      }
    }

    this.updateToggleButton();
  }

  updateToggleButton() {
    const button = document.getElementById('bot-filter-toggle');
    if (!button) return;

    const hiddenText = this.hiddenCommentsCount > 0 ? ` (${this.hiddenCommentsCount})` : '';
    button.textContent = this.isEnabled ? 
      `🤖 Show Bots${hiddenText}` : 
      `🤖 Hide Bots`;
    
    button.title = this.isEnabled ? 
      `Currently hiding ${this.hiddenCommentsCount} bot comments. Click to show them.` :
      'Click to hide bot comments';
  }
}

// Initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => new GitHubBotFilter());
} else {
  new GitHubBotFilter();
} 