# GitHub Bot Comment Filter

A browser extension that allows you to hide or show bot-generated comments and suggestions on GitHub pull requests and issues.

## Features

- 🤖 **Hide Bot Comments**: Automatically hide comments from GitHub Actions, PR-Agent, Dependabot, Renovate, Codecov, and other bots
- 🔄 **Toggle Control**: Easy toggle button directly on GitHub pages and in extension popup
- 💾 **Persistent Settings**: Remembers your preference across browser sessions
- 🎯 **Smart Detection**: Identifies bots by username patterns, user types, and specific bot accounts
- 🌓 **Dark Mode**: Supports GitHub's dark theme
- ⚡ **Real-time Updates**: Works with GitHub's dynamic content loading

## Supported Bots

- GitHub Actions (`github-actions[bot]`)
- PR-Agent (`codiumai-pr-agent`, `codiumai-pr-agent-pro`)
- Dependabot (`dependabot[bot]`)
- Renovate (`renovate[bot]`)
- Codecov (`codecov[bot]`)
- Any username containing `[bot]`
- Custom bot patterns

## Installation

### Chrome/Edge (Chromium-based browsers)

1. **Download the Extension**
   - Clone or download this repository
   - Navigate to the `github-bot-filter-extension` directory

2. **Load the Extension**
   - Open Chrome/Edge and go to `chrome://extensions/` (or `edge://extensions/`)
   - Enable "Developer mode" in the top right
   - Click "Load unpacked"
   - Select the `github-bot-filter-extension` folder

3. **Pin the Extension** (Optional)
   - Click the extensions icon in the toolbar
   - Pin "GitHub Bot Comment Filter" for easy access

### Firefox

1. **Temporary Installation** (for development)
   - Go to `about:debugging#/runtime/this-firefox`
   - Click "Load Temporary Add-on"
   - Select the `manifest.json` file

2. **Permanent Installation**
   - Package the extension as a `.xpi` file
   - Install through Firefox Add-ons

## Usage

### Method 1: Toggle Button on GitHub

1. Navigate to any GitHub pull request or issue
2. Look for the "🤖 Hide Bots" or "🤖 Show Bots" button in the page header
3. Click to toggle bot comment visibility
4. The button shows the count of hidden comments when active

### Method 2: Extension Popup

1. Click the extension icon in your browser toolbar
2. Use the "Toggle Filter" button in the popup
3. View status and hidden comment count
4. The popup shows whether you're on a GitHub page

## How It Works

The extension uses several techniques to identify bot comments:

1. **Username Patterns**: Looks for `[bot]` in usernames
2. **Hovercard URLs**: Checks GitHub's user hovercard data
3. **User Types**: Identifies accounts marked as "Bot" type
4. **Specific Accounts**: Targets known bot account names
5. **Dynamic Detection**: Monitors page changes for new comments

## Development

### Project Structure

```
github-bot-filter-extension/
├── manifest.json          # Extension manifest
├── content.js            # Main content script
├── content.css           # Content script styles
├── popup.html            # Extension popup interface
├── popup.js              # Popup functionality
├── popup.css             # Popup styles
├── background.js         # Background service worker
├── icons/                # Extension icons
│   └── icon.svg         # Main icon file
└── README.md            # This file
```

### Building Icons

The extension needs icon files in multiple sizes. You can convert the SVG to PNG:

```bash
# Using ImageMagick (if available)
convert icon.svg -resize 16x16 icon16.png
convert icon.svg -resize 32x32 icon32.png
convert icon.svg -resize 48x48 icon48.png
convert icon.svg -resize 128x128 icon128.png
```

Or use online tools to convert the SVG to the required PNG sizes.

### Testing

1. Load the extension in developer mode
2. Navigate to GitHub PRs/issues with bot comments
3. Test toggle functionality
4. Check console for any errors
5. Verify settings persist across page reloads

## Customization

### Adding New Bot Patterns

Edit the `getBotSelectors()` method in `content.js`:

```javascript
getBotSelectors() {
  return [
    // Add your custom selectors here
    '[data-hovercard-url*="your-bot-name"]',
    'a[href*="/your-bot-username"]',
    // ... existing patterns
  ];
}
```

### Styling the Toggle Button

Modify `content.css` to customize the appearance:

```css
#bot-filter-toggle {
  /* Your custom styles */
  background: your-color !important;
  border: your-border !important;
}
```

## Privacy

This extension:
- ✅ Only runs on GitHub.com
- ✅ Stores preferences locally using Chrome storage API
- ✅ Does not collect or transmit any personal data
- ✅ Does not modify or access repository content
- ✅ Only hides/shows existing comments visually

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly on various GitHub pages
5. Submit a pull request

## License

This project is part of the PR-Agent ecosystem. Please refer to the main project license.

## Support

For issues, questions, or feature requests:
- Open an issue in the main PR-Agent repository
- Include browser version and extension version
- Provide steps to reproduce any problems

## Changelog

### v1.0.0
- Initial release
- Basic bot comment filtering
- Toggle functionality
- Popup interface
- Settings persistence
- Dark mode support 