@echo off
echo Packaging GitHub Bot Comment Filter Extension...
echo.

REM Create a clean temporary directory
if exist "dist" rmdir /s /q "dist"
mkdir "dist"

REM Copy extension files (excluding development files)
xcopy "manifest.json" "dist\" /Y
xcopy "content.js" "dist\" /Y
xcopy "content.css" "dist\" /Y
xcopy "popup.html" "dist\" /Y
xcopy "popup.js" "dist\" /Y
xcopy "popup.css" "dist\" /Y
xcopy "background.js" "dist\" /Y
xcopy "icons\*" "dist\icons\" /Y /I

REM Create the zip file
echo Creating github-bot-filter-extension.zip...
powershell -command "Compress-Archive -Path 'dist\*' -DestinationPath 'github-bot-filter-extension.zip' -Force"

REM Clean up
rmdir /s /q "dist"

echo.
echo ✅ Extension packaged successfully!
echo 📦 File: github-bot-filter-extension.zip
echo.
echo Next steps:
echo 1. Test the .zip file by loading it in Chrome
echo 2. Share with users for manual installation
echo 3. Or upload to Chrome Web Store
echo.
pause 