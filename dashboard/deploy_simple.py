#!/usr/bin/env python3
"""
PR Agent Dashboard Simple Windows Deployment Script

This script deploys the PR Agent Dashboard using background processes
instead of Windows services for better reliability.
"""

import os
import sys
import subprocess
import shutil
import argparse
import json
import platform
from pathlib import Path
import tempfile
import zipfile

def check_admin():
    """Check if running with administrator privileges"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_command(cmd, shell=True, check=True, cwd=None):
    """Run a command and return the result"""
    print(f"Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=shell, check=check, cwd=cwd, 
                              capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return result
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        if e.stderr:
            print(f"Error output: {e.stderr}")
        if check:
            raise
        return e

def check_requirements():
    """Check system requirements"""
    print("Checking system requirements...")
    
    # Check Windows version
    if platform.system() != "Windows":
        raise RuntimeError("This script is for Windows only")
    
    # Check Python version
    if sys.version_info < (3, 8):
        raise RuntimeError("Python 3.8 or higher is required")
    
    # Check for Node.js
    try:
        result = run_command("node --version")
        node_version = result.stdout.strip()
        print(f"Node.js version: {node_version}")
    except:
        raise RuntimeError("Node.js is required but not found")
    
    # Check for npm
    try:
        result = run_command("npm --version")
        npm_version = result.stdout.strip()
        print(f"npm version: {npm_version}")
    except:
        raise RuntimeError("npm is required but not found")
    
    print("✓ System requirements satisfied")

def copy_files(install_dir):
    """Copy application files to installation directory"""
    print(f"Copying files to {install_dir}...")
    
    # Get current directory (where the script is located)
    current_dir = Path(__file__).parent
    
    # Create installation directory
    install_path = Path(install_dir)
    install_path.mkdir(parents=True, exist_ok=True)
    
    # Copy backend files
    backend_src = current_dir / "backend"
    backend_dst = install_path / "backend"
    if backend_src.exists():
        if backend_dst.exists():
            shutil.rmtree(backend_dst)
        shutil.copytree(backend_src, backend_dst)
    
    # Copy frontend files
    frontend_src = current_dir / "frontend"
    frontend_dst = install_path / "frontend"
    if frontend_src.exists():
        if frontend_dst.exists():
            shutil.rmtree(frontend_dst)
        shutil.copytree(frontend_src, frontend_dst)
    
    print("✓ Files copied successfully")

def configure_backend(install_dir, backend_port, frontend_port):
    """Configure backend for production"""
    print("Configuring backend for production...")
    
    backend_dir = Path(install_dir) / "backend"
    settings_file = backend_dir / "settings.toml"
    
    # Database path (use forward slashes for SQLite URL)
    db_path = str(backend_dir / "dashboard.db").replace('\\', '/')
    
    settings_content = f"""# Dashboard Configuration - Production Deployment
[default]
app_name = "PR-Agent Dashboard"
debug = false
log_level = "INFO"
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# API server settings - Accept connections from any IP
api_host = "0.0.0.0"
api_port = {backend_port}
developer_mode = false

# Database settings
database_url = "sqlite:///{db_path}"
database_echo = false

# CORS settings - Allow frontend access
cors_origins = [
    "http://localhost:{frontend_port}",
    "http://127.0.0.1:{frontend_port}",
    "http://0.0.0.0:{frontend_port}"
]

[production]
debug = false
log_level = "INFO"
developer_mode = false
api_host = "0.0.0.0"
api_port = {backend_port}
"""
    
    settings_file.write_text(settings_content, encoding='utf-8')
    print("✓ Backend configured for production")

def install_python_dependencies(install_dir):
    """Install Python dependencies"""
    print("Installing Python dependencies...")
    
    backend_dir = Path(install_dir) / "backend"
    venv_dir = Path(install_dir) / "venv"
    requirements_file = backend_dir / "requirements.txt"
    
    # Create virtual environment
    if venv_dir.exists():
        shutil.rmtree(venv_dir)
    
    run_command(f'python -m venv "{venv_dir}"')
    
    # Install dependencies
    python_path = venv_dir / "Scripts" / "python.exe"
    run_command(f'"{python_path}" -m pip install --upgrade pip')
    run_command(f'"{python_path}" -m pip install -r "{requirements_file}"')
    
    print("✓ Python dependencies installed")

def build_frontend(install_dir, backend_port, frontend_port):
    """Build frontend for production"""
    print("Building frontend for production...")
    
    frontend_dir = Path(install_dir) / "frontend"
    
    # Set environment variables
    env = os.environ.copy()
    env['REACT_APP_API_URL'] = f"http://localhost:{backend_port}"
    env['GENERATE_SOURCEMAP'] = "false"
    
    # Install npm dependencies
    run_command("npm install", cwd=frontend_dir)
    
    # Build the frontend
    run_command("npm run build", cwd=frontend_dir)
    
    # Update API URL in built files for external access
    build_dir = frontend_dir / "build"
    static_js_dir = build_dir / "static" / "js"
    
    if static_js_dir.exists():
        for js_file in static_js_dir.glob("*.js"):
            content = js_file.read_text(encoding='utf-8')
            content = content.replace(
                f"http://localhost:{backend_port}",
                f"window.location.protocol + '//' + window.location.hostname + ':{backend_port}'"
            )
            js_file.write_text(content, encoding='utf-8')
    
    print("✓ Frontend built successfully")

def create_management_scripts(install_dir, backend_port, frontend_port):
    """Create management scripts for starting/stopping the dashboard"""
    print("Creating management scripts...")
    
    venv_dir = Path(install_dir) / "venv"
    python_path = venv_dir / "Scripts" / "python.exe"
    backend_dir = Path(install_dir) / "backend"
    frontend_build_dir = Path(install_dir) / "frontend" / "build"
    
    # Create start script
    start_script = Path(install_dir) / "start.bat"
    start_content = f'''@echo off
echo Starting PR Agent Dashboard...
echo.

REM Create logs directory
if not exist "{install_dir}\\logs" mkdir "{install_dir}\\logs"

REM Start backend
echo Starting backend on port {backend_port}...
cd /d "{backend_dir}"
start "PR-Agent Backend" "{python_path}" -m uvicorn main:app --host 0.0.0.0 --port {backend_port} --workers 1 > "{install_dir}\\logs\\backend.log" 2>&1

REM Wait a moment for backend to start
timeout /t 3 /nobreak > nul

REM Start frontend
echo Starting frontend on port {frontend_port}...
cd /d "{frontend_build_dir}"
start "PR-Agent Frontend" "{python_path}" -m http.server {frontend_port} --bind 0.0.0.0 > "{install_dir}\\logs\\frontend.log" 2>&1

echo.
echo PR Agent Dashboard is starting...
echo Frontend: http://localhost:{frontend_port}
echo Backend:  http://localhost:{backend_port}
echo.
echo Press any key to continue...
pause > nul
'''
    
    start_script.write_text(start_content, encoding='utf-8')
    
    # Create stop script
    stop_script = Path(install_dir) / "stop.bat"
    stop_content = f'''@echo off
echo Stopping PR Agent Dashboard...
echo.

REM Stop backend process
echo Stopping backend...
taskkill /f /im python.exe /fi "WINDOWTITLE eq PR-Agent Backend*" > nul 2>&1

REM Stop frontend process
echo Stopping frontend...
taskkill /f /im python.exe /fi "WINDOWTITLE eq PR-Agent Frontend*" > nul 2>&1

echo.
echo PR Agent Dashboard stopped.
echo.
echo Press any key to continue...
pause > nul
'''
    
    stop_script.write_text(stop_content, encoding='utf-8')
    
    # Create status script
    status_script = Path(install_dir) / "status.bat"
    status_content = f'''@echo off
echo PR Agent Dashboard Status
echo =========================
echo.

REM Check if backend is running
echo Checking backend (port {backend_port})...
netstat -an | findstr ":{backend_port}" > nul
if %errorlevel% equ 0 (
    echo Backend: RUNNING
) else (
    echo Backend: STOPPED
)

REM Check if frontend is running
echo Checking frontend (port {frontend_port})...
netstat -an | findstr ":{frontend_port}" > nul
if %errorlevel% equ 0 (
    echo Frontend: RUNNING
) else (
    echo Frontend: STOPPED
)

echo.
echo URLs:
echo Frontend: http://localhost:{frontend_port}
echo Backend:  http://localhost:{backend_port}
echo.
echo Press any key to continue...
pause > nul
'''
    
    status_script.write_text(status_content, encoding='utf-8')
    
    # Create startup shortcut script
    startup_script = Path(install_dir) / "add_to_startup.bat"
    startup_content = f'''@echo off
echo Adding PR Agent Dashboard to Windows startup...
echo.

REM Get startup folder
set "startup_folder=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"

REM Create shortcut
echo Creating startup shortcut...
powershell -Command "$WshShell = New-Object -comObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%startup_folder%\\PR-Agent Dashboard.lnk'); $Shortcut.TargetPath = '{start_script}'; $Shortcut.WorkingDirectory = '{install_dir}'; $Shortcut.Save()"

if exist "%startup_folder%\\PR-Agent Dashboard.lnk" (
    echo ✓ Startup shortcut created successfully
    echo Dashboard will now start automatically when Windows boots
) else (
    echo ✗ Failed to create startup shortcut
)

echo.
echo Press any key to continue...
pause > nul
'''
    
    startup_script.write_text(startup_content, encoding='utf-8')
    
    # Create remove from startup script
    remove_startup_script = Path(install_dir) / "remove_from_startup.bat"
    remove_startup_content = f'''@echo off
echo Removing PR Agent Dashboard from Windows startup...
echo.

REM Get startup folder
set "startup_folder=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs\\Startup"

REM Remove shortcut
if exist "%startup_folder%\\PR-Agent Dashboard.lnk" (
    del "%startup_folder%\\PR-Agent Dashboard.lnk"
    echo ✓ Startup shortcut removed successfully
) else (
    echo Dashboard was not in startup folder
)

echo.
echo Press any key to continue...
pause > nul
'''
    
    remove_startup_script.write_text(remove_startup_content, encoding='utf-8')
    
    print("✓ Management scripts created")

def uninstall_dashboard(install_dir):
    """Uninstall the dashboard"""
    print("Uninstalling PR Agent Dashboard...")
    
    install_path = Path(install_dir)
    
    # Try to stop processes first
    try:
        stop_script = install_path / "stop.bat"
        if stop_script.exists():
            run_command(f'"{stop_script}"', check=False)
    except:
        pass
    
    # Remove from startup
    try:
        remove_startup_script = install_path / "remove_from_startup.bat"
        if remove_startup_script.exists():
            run_command(f'"{remove_startup_script}"', check=False)
    except:
        pass
    
    # Remove installation directory
    if install_path.exists():
        try:
            shutil.rmtree(install_path)
            print(f"✓ Installation directory {install_dir} removed")
        except Exception as e:
            print(f"Warning: Could not remove installation directory: {e}")
    
    print("✓ Dashboard uninstalled successfully")

def main():
    parser = argparse.ArgumentParser(
        description="PR Agent Dashboard Simple Windows Deployment Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy with default ports
  python deploy_simple.py

  # Deploy with custom ports
  python deploy_simple.py --frontend-port 8080 --backend-port 8081

  # Deploy to custom directory
  python deploy_simple.py --install-dir "D:\\Apps\\PR-Agent-Dashboard"

  # Uninstall
  python deploy_simple.py --uninstall

Management:
  After installation, use these scripts in the installation directory:
  - start.bat: Start the dashboard
  - stop.bat: Stop the dashboard
  - status.bat: Check if dashboard is running
  - add_to_startup.bat: Add to Windows startup
  - remove_from_startup.bat: Remove from Windows startup
        """
    )
    
    parser.add_argument('--frontend-port', type=int, default=3000,
                        help='Frontend port (default: 3000)')
    parser.add_argument('--backend-port', type=int, default=8000,
                        help='Backend port (default: 8000)')
    parser.add_argument('--install-dir', default=r"C:\PR-Agent-Dashboard",
                        help='Installation directory (default: C:\\PR-Agent-Dashboard)')
    parser.add_argument('--uninstall', action='store_true',
                        help='Uninstall the dashboard')
    
    args = parser.parse_args()
    
    try:
        if args.uninstall:
            uninstall_dashboard(args.install_dir)
        else:
            print("PR Agent Dashboard Simple Windows Deployment")
            print("=" * 50)
            print(f"Frontend port: {args.frontend_port}")
            print(f"Backend port: {args.backend_port}")
            print(f"Installation directory: {args.install_dir}")
            print()
            
            check_requirements()
            copy_files(args.install_dir)
            configure_backend(args.install_dir, args.backend_port, args.frontend_port)
            install_python_dependencies(args.install_dir)
            build_frontend(args.install_dir, args.backend_port, args.frontend_port)
            create_management_scripts(args.install_dir, args.backend_port, args.frontend_port)
            
            print()
            print("=" * 50)
            print("✓ PR Agent Dashboard deployed successfully!")
            print()
            print(f"Installation directory: {args.install_dir}")
            print(f"Frontend URL: http://localhost:{args.frontend_port}")
            print(f"Backend URL: http://localhost:{args.backend_port}")
            print()
            print("Management Scripts:")
            print(f"  Start:      {args.install_dir}\\start.bat")
            print(f"  Stop:       {args.install_dir}\\stop.bat")
            print(f"  Status:     {args.install_dir}\\status.bat")
            print(f"  Add to startup: {args.install_dir}\\add_to_startup.bat")
            print()
            print("Quick Start:")
            print(f"  1. Run: {args.install_dir}\\start.bat")
            print(f"  2. Open: http://localhost:{args.frontend_port}")
            print()
            print("To uninstall:")
            print("  python deploy_simple.py --uninstall")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 