# Distribution Guide

## 🚀 Distribution Options

### Option 1: Chrome Web Store (Recommended)

**Best for**: Wide public distribution, automatic updates, user trust

#### Steps:
1. **Prepare for Submission**:
   - Convert `icon.svg` to proper PNG files (16x16, 32x32, 48x48, 128x128)
   - Test extension thoroughly
   - Create high-quality screenshots
   - Write clear store description

2. **Create Developer Account**:
   - Go to [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole)
   - Pay $5 one-time registration fee
   - Verify identity

3. **Package Extension**:
   - Run `package-extension.bat` to create clean zip file
   - Test the packaged version

4. **Submit**:
   - Upload zip file
   - Fill out store listing
   - Submit for review (1-3 days)

#### Store Listing Template:
```
Name: GitHub Bot Comment Filter

Short Description: 
Hide or show bot comments on GitHub pull requests and issues with one click

Detailed Description:
Clean up your GitHub experience by hiding bot-generated comments and suggestions. 
Perfect for focusing on human discussions in pull requests and issues.

Features:
• Hide/show bot comments with one click
• Works with GitHub Actions, PR-Agent, Dependabot, Renovate, Codecov
• Toggle button directly on GitHub pages
• Persistent settings across sessions
• Supports GitHub's light and dark themes

Simply install and visit any GitHub PR or issue to see the toggle button appear.
```

### Option 2: Manual Distribution

**Best for**: Internal teams, immediate distribution, testing

#### Package the Extension:
```bash
# Windows
package-extension.bat

# Manual method
1. Create folder with only these files:
   - manifest.json
   - content.js, content.css
   - popup.html, popup.js, popup.css
   - background.js
   - icons/ folder
2. Zip the folder
3. Share the .zip file
```

#### Installation Instructions for Users:
```
1. Download github-bot-filter-extension.zip
2. Extract to a folder
3. Open Chrome → chrome://extensions/
4. Enable "Developer mode"
5. Click "Load unpacked"
6. Select the extracted folder
7. Pin the extension for easy access
```

### Option 3: GitHub Releases

**Best for**: Open source distribution, version tracking

#### Steps:
1. **Create a Release on GitHub**:
   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

2. **Attach Extension Package**:
   - Upload `github-bot-filter-extension.zip` to release
   - Include installation instructions
   - Add changelog

3. **Update README** with installation link:
   ```markdown
   ## Installation
   Download the latest release from [GitHub Releases](link)
   ```

### Option 4: Direct Download

**Best for**: Simple sharing, immediate access

#### Host the Files:
- **GitHub Pages**: Host installation instructions
- **Your website**: Direct download link
- **Cloud storage**: Google Drive, Dropbox (public link)

## 📋 Pre-Distribution Checklist

### Technical Requirements:
- [ ] Extension works in Chrome, Edge, Brave
- [ ] All icons converted to PNG format
- [ ] No console errors on GitHub pages
- [ ] Toggle functionality works correctly
- [ ] Settings persist across browser sessions
- [ ] Dark mode styling works
- [ ] Popup interface responds correctly

### Documentation:
- [ ] README.md updated with installation instructions
- [ ] Screenshots showing extension in action
- [ ] Clear feature list and supported bots
- [ ] Troubleshooting section

### Legal/Compliance:
- [ ] No copyright issues with icons/code
- [ ] Privacy policy (if required)
- [ ] Terms of service (if required)
- [ ] Attribution for any third-party resources

## 🎯 Recommended Distribution Strategy

### Phase 1: Internal Testing (Now)
- [ ] Load unpacked extension
- [ ] Test on various GitHub repositories
- [ ] Get feedback from colleagues/friends

### Phase 2: Manual Distribution
- [ ] Package extension using provided script
- [ ] Share with PR-Agent community
- [ ] Collect feedback and bug reports

### Phase 3: Chrome Web Store
- [ ] Create proper PNG icons
- [ ] Take professional screenshots
- [ ] Submit to Chrome Web Store
- [ ] Announce public availability

## 🔧 Version Management

### Updating the Extension:

1. **Update `manifest.json` version**:
   ```json
   "version": "1.1.0"
   ```

2. **For Chrome Web Store**:
   - Upload new zip file
   - Users get automatic updates

3. **For Manual Distribution**:
   - Create new package
   - Users must manually update

### Versioning Strategy:
- **1.0.x**: Bug fixes
- **1.x.0**: New features
- **x.0.0**: Major changes

## 📈 Usage Analytics (Optional)

To track usage without violating privacy:

```javascript
// Add to background.js (optional)
chrome.runtime.onInstalled.addListener(() => {
  // Simple analytics - no personal data
  fetch('your-analytics-endpoint', {
    method: 'POST',
    body: JSON.stringify({ 
      event: 'install', 
      version: chrome.runtime.getManifest().version 
    })
  });
});
```

## 🎉 Launch Checklist

Ready to distribute when:
- [ ] Extension package created successfully
- [ ] Installation instructions tested by someone else
- [ ] No errors in Chrome DevTools
- [ ] Works on multiple GitHub repositories
- [ ] Icons display properly
- [ ] All documentation complete

Choose your distribution method and let's get this extension out there! 🚀 