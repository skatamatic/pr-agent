# Quick Installation Guide

## Step 1: Install the Extension

### For Chrome/Edge:
1. Open your browser and go to `chrome://extensions/` (Chrome) or `edge://extensions/` (Edge)
2. Enable "Developer mode" (toggle in top right)
3. Click "Load unpacked"
4. Select the `github-bot-filter-extension` folder
5. The extension should now appear in your extensions list

### For Firefox:
1. Go to `about:debugging#/runtime/this-firefox`
2. Click "Load Temporary Add-on"
3. Select the `manifest.json` file in the extension folder

## Step 2: Pin the Extension (Recommended)
1. Click the puzzle piece icon in your browser toolbar
2. Find "GitHub Bot Comment Filter"
3. Click the pin icon to keep it visible

## Step 3: Convert Icons (Optional)
The extension uses placeholder icon files. For best appearance:

1. **Online converter**: Upload `icons/icon.svg` to an online SVG-to-PNG converter
2. **Create 4 PNG files**:
   - `icon16.png` (16x16 pixels)
   - `icon32.png` (32x32 pixels)  
   - `icon48.png` (48x48 pixels)
   - `icon128.png` (128x128 pixels)
3. Replace the placeholder files in the `icons/` folder
4. Reload the extension in `chrome://extensions/`

## Step 4: Test It Out
1. Go to any GitHub pull request or issue with bot comments
2. Look for the "🤖 Hide Bots" button in the page header
3. Click it to toggle bot comment visibility
4. Or click the extension icon in your toolbar for more options

## Troubleshooting

**Extension not loading?**
- Make sure you selected the correct folder containing `manifest.json`
- Check that Developer mode is enabled
- Look for error messages in the extensions page

**Toggle button not appearing?**
- Refresh the GitHub page
- Check that you're on a PR or Issue page (not repository home)
- Open browser console (F12) and look for any JavaScript errors

**Icons not showing properly?**
- The extension will work fine with placeholder icons
- Follow Step 3 above for proper icon display
- Make sure icon files are actually PNG format, not text files

## Usage Tips

- The extension remembers your preference (hide/show bots)
- Badge on extension icon shows ON/OFF status on GitHub pages
- Works with all major bots: GitHub Actions, PR-Agent, Dependabot, etc.
- Supports both light and dark GitHub themes
- Updates automatically when new comments are added to pages 