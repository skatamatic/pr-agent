#!/usr/bin/env python3
"""
PR Agent Dashboard Windows Deployment Script using NSSM

This script deploys the PR Agent Dashboard using NSSM (Non-Sucking Service Manager)
to create proper Windows services.
"""

import os
import sys
import subprocess
import shutil
import argparse
import json
import platform
from pathlib import Path
import urllib.request
import zipfile
import tempfile

def check_admin():
    """Check if running with administrator privileges"""
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def run_command(cmd, shell=True, check=True, cwd=None, env=None):
    """Run a command and return the result"""
    print(f"Running: {cmd}")
    try:
        result = subprocess.run(cmd, shell=shell, check=check, cwd=cwd, env=env,
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

def download_nssm(install_dir):
    """Download and extract NSSM"""
    nssm_dir = Path(install_dir) / "nssm"
    nssm_dir.mkdir(parents=True, exist_ok=True)
    
    nssm_exe_path = nssm_dir / 'nssm.exe'
    
    # Check if NSSM already exists
    if nssm_exe_path.exists():
        print("NSSM already exists, skipping download")
        return nssm_exe_path
    
    print("Downloading NSSM (Non-Sucking Service Manager)...")
    
    # NSSM download URL
    nssm_url = "https://nssm.cc/release/nssm-2.24.zip"
    
    # Download NSSM directly to nssm directory
    nssm_zip_path = nssm_dir / "nssm.zip"
    
    try:
        print(f"Downloading from {nssm_url}...")
        urllib.request.urlretrieve(nssm_url, nssm_zip_path)
        
        # Extract NSSM
        with zipfile.ZipFile(nssm_zip_path, 'r') as zip_ref:
            zip_ref.extractall(nssm_dir)
        
        # Find the nssm.exe file (it's in a subdirectory)
        for root, dirs, files in os.walk(nssm_dir):
            if 'nssm.exe' in files:
                found_nssm_exe = Path(root) / 'nssm.exe'
                # Copy to main nssm directory for easy access
                shutil.copy2(found_nssm_exe, nssm_exe_path)
                break
        
        print("✓ NSSM downloaded and extracted")
        return nssm_exe_path
        
    finally:
        # Clean up zip file
        if nssm_zip_path.exists():
            try:
                nssm_zip_path.unlink()
            except Exception as e:
                print(f"Warning: Could not delete zip file: {e}")

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
    build_dir = frontend_dir / "build"
    
    # Set environment variables for build
    env = os.environ.copy()
    env['REACT_APP_API_URL'] = "DYNAMIC_API_URL_PLACEHOLDER"
    env['GENERATE_SOURCEMAP'] = "false"
    
    # Install npm dependencies
    run_command("npm install", cwd=frontend_dir)
    
    # Build the frontend
    run_command("npm run build", cwd=frontend_dir, env=env)
    
    # Create a dynamic configuration script
    config_script = build_dir / "config.js"
    config_content = f"""// Dynamic configuration for PR Agent Dashboard
window.REACT_APP_API_URL = window.location.protocol + '//' + window.location.hostname + ':{backend_port}';
"""
    config_script.write_text(config_content, encoding='utf-8')
    
    # Update index.html to include the config script
    index_html = build_dir / "index.html"
    if index_html.exists():
        html_content = index_html.read_text(encoding='utf-8')
        
        # Add config script before other scripts
        html_content = html_content.replace(
            '<head>',
            '<head>\n    <script src="./config.js"></script>'
        )
        
        index_html.write_text(html_content, encoding='utf-8')
    
    # Update API URL in built JavaScript files
    static_js_dir = build_dir / "static" / "js"
    if static_js_dir.exists():
        for js_file in static_js_dir.glob("*.js"):
            content = js_file.read_text(encoding='utf-8')
            # Replace the placeholder with a reference to the global variable
            content = content.replace(
                '"DYNAMIC_API_URL_PLACEHOLDER"',
                'window.REACT_APP_API_URL'
            )
            content = content.replace(
                "'DYNAMIC_API_URL_PLACEHOLDER'",
                'window.REACT_APP_API_URL'
            )
            js_file.write_text(content, encoding='utf-8')
    
    print("✓ Frontend built successfully")

def create_services_with_nssm(install_dir, backend_port, frontend_port, nssm_exe):
    """Create Windows services using NSSM"""
    print("Creating Windows services with NSSM...")
    
    venv_dir = Path(install_dir) / "venv"
    python_path = venv_dir / "Scripts" / "python.exe"
    backend_dir = Path(install_dir) / "backend"
    frontend_build_dir = Path(install_dir) / "frontend" / "build"
    logs_dir = Path(install_dir) / "logs"
    logs_dir.mkdir(exist_ok=True)
    
    # Service names
    backend_service = "PRAgentDashboard-Backend"
    frontend_service = "PRAgentDashboard-Frontend"
    
    # Create backend service
    print(f"Creating backend service: {backend_service}")
    
    # Install backend service
    run_command(f'"{nssm_exe}" install {backend_service} "{python_path}"')
    
    # Configure backend service
    run_command(f'"{nssm_exe}" set {backend_service} AppParameters "-m uvicorn main:app --host 0.0.0.0 --port {backend_port} --workers 1"')
    run_command(f'"{nssm_exe}" set {backend_service} AppDirectory "{backend_dir}"')
    run_command(f'"{nssm_exe}" set {backend_service} DisplayName "PR Agent Dashboard Backend"')
    run_command(f'"{nssm_exe}" set {backend_service} Description "Backend API service for PR Agent Dashboard"')
    run_command(f'"{nssm_exe}" set {backend_service} Start SERVICE_AUTO_START')
    run_command(f'"{nssm_exe}" set {backend_service} AppStdout "{logs_dir / "backend.log"}"')
    run_command(f'"{nssm_exe}" set {backend_service} AppStderr "{logs_dir / "backend.log"}"')
    run_command(f'"{nssm_exe}" set {backend_service} AppRotateFiles 1')
    run_command(f'"{nssm_exe}" set {backend_service} AppRotateOnline 1')
    run_command(f'"{nssm_exe}" set {backend_service} AppRotateBytes 1048576')  # 1MB
    
    print(f"✓ Backend service {backend_service} created")
    
    # Create frontend service
    print(f"Creating frontend service: {frontend_service}")
    
    # Install frontend service
    run_command(f'"{nssm_exe}" install {frontend_service} "{python_path}"')
    
    # Configure frontend service
    run_command(f'"{nssm_exe}" set {frontend_service} AppParameters "-m http.server {frontend_port} --bind 0.0.0.0"')
    run_command(f'"{nssm_exe}" set {frontend_service} AppDirectory "{frontend_build_dir}"')
    run_command(f'"{nssm_exe}" set {frontend_service} DisplayName "PR Agent Dashboard Frontend"')
    run_command(f'"{nssm_exe}" set {frontend_service} Description "Frontend web server for PR Agent Dashboard"')
    run_command(f'"{nssm_exe}" set {frontend_service} Start SERVICE_AUTO_START')
    run_command(f'"{nssm_exe}" set {frontend_service} AppStdout "{logs_dir / "frontend.log"}"')
    run_command(f'"{nssm_exe}" set {frontend_service} AppStderr "{logs_dir / "frontend.log"}"')
    run_command(f'"{nssm_exe}" set {frontend_service} AppRotateFiles 1')
    run_command(f'"{nssm_exe}" set {frontend_service} AppRotateOnline 1')
    run_command(f'"{nssm_exe}" set {frontend_service} AppRotateBytes 1048576')  # 1MB
    
    # Set dependency (frontend depends on backend)
    run_command(f'"{nssm_exe}" set {frontend_service} DependOnService {backend_service}')
    
    print(f"✓ Frontend service {frontend_service} created")
    
    return backend_service, frontend_service

def start_services(backend_service, frontend_service):
    """Start the services"""
    print("Starting services...")
    
    # Start backend service
    try:
        run_command(f'sc start {backend_service}')
        print(f"✓ Backend service {backend_service} started")
    except Exception as e:
        print(f"Warning: Could not start backend service: {e}")
    
    # Start frontend service (it will wait for backend due to dependency)
    try:
        run_command(f'sc start {frontend_service}')
        print(f"✓ Frontend service {frontend_service} started")
    except Exception as e:
        print(f"Warning: Could not start frontend service: {e}")

def create_management_scripts(install_dir, backend_service, frontend_service, nssm_exe):
    """Create management scripts"""
    print("Creating management scripts...")
    
    # Create status script
    status_script = Path(install_dir) / "status.bat"
    status_content = f'''@echo off
echo PR Agent Dashboard Service Status
echo ==================================
echo.

echo Backend Service ({backend_service}):
sc query {backend_service}
echo.

echo Frontend Service ({frontend_service}):
sc query {frontend_service}
echo.

echo Service Management:
echo   Start Backend:   sc start {backend_service}
echo   Stop Backend:    sc stop {backend_service}
echo   Start Frontend:  sc start {frontend_service}
echo   Stop Frontend:   sc stop {frontend_service}
echo   Restart Backend: sc stop {backend_service} ^&^& sc start {backend_service}
echo   Restart Frontend: sc stop {frontend_service} ^&^& sc start {frontend_service}
echo.

echo Logs:
echo   Backend:  {install_dir}\\logs\\backend.log
echo   Frontend: {install_dir}\\logs\\frontend.log
echo.

pause
'''
    
    status_script.write_text(status_content, encoding='utf-8')
    
    # Create restart script
    restart_script = Path(install_dir) / "restart.bat"
    restart_content = f'''@echo off
echo Restarting PR Agent Dashboard services...
echo.

echo Stopping services...
sc stop {frontend_service}
sc stop {backend_service}

echo Waiting for services to stop...
timeout /t 5 /nobreak > nul

echo Starting services...
sc start {backend_service}
sc start {frontend_service}

echo.
echo Services restarted.
echo.
pause
'''
    
    restart_script.write_text(restart_content, encoding='utf-8')
    
    # Create uninstall script
    uninstall_script = Path(install_dir) / "uninstall_services.bat"
    uninstall_content = f'''@echo off
echo Uninstalling PR Agent Dashboard services...
echo.

echo Stopping services...
sc stop {frontend_service}
sc stop {backend_service}

echo Removing services...
"{nssm_exe}" remove {frontend_service} confirm
"{nssm_exe}" remove {backend_service} confirm

echo.
echo Services removed.
echo.
pause
'''
    
    uninstall_script.write_text(uninstall_content, encoding='utf-8')
    
    print("✓ Management scripts created")

def uninstall_dashboard(install_dir):
    """Uninstall the dashboard"""
    print("Uninstalling PR Agent Dashboard...")
    
    install_path = Path(install_dir)
    nssm_exe = install_path / "nssm" / "nssm.exe"
    
    backend_service = "PRAgentDashboard-Backend"
    frontend_service = "PRAgentDashboard-Frontend"
    
    # Stop and remove services
    if nssm_exe.exists():
        try:
            run_command(f'sc stop {frontend_service}', check=False)
            run_command(f'sc stop {backend_service}', check=False)
            run_command(f'"{nssm_exe}" remove {frontend_service} confirm', check=False)
            run_command(f'"{nssm_exe}" remove {backend_service} confirm', check=False)
            print("✓ Services removed")
        except Exception as e:
            print(f"Warning: Could not remove services: {e}")
    
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
        description="PR Agent Dashboard Windows Deployment Script (NSSM)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy with default ports
  python deploy_nssm.py

  # Deploy with custom ports
  python deploy_nssm.py --frontend-port 8080 --backend-port 8081

  # Deploy to custom directory
  python deploy_nssm.py --install-dir "D:\\Apps\\PR-Agent-Dashboard"

  # Uninstall
  python deploy_nssm.py --uninstall

Service Management:
  sc start PRAgentDashboard-Backend
  sc start PRAgentDashboard-Frontend
  sc stop PRAgentDashboard-Backend
  sc stop PRAgentDashboard-Frontend
  sc query PRAgentDashboard-Backend
  sc query PRAgentDashboard-Frontend
        """
    )
    
    parser.add_argument('--frontend-port', type=int, default=3000,
                        help='Frontend port (default: 3000)')
    parser.add_argument('--backend-port', type=int, default=8000,
                        help='Backend port (default: 8000)')
    parser.add_argument('--install-dir', default=r"C:\Program Files\PR-Agent-Dashboard",
                        help='Installation directory (default: C:\\Program Files\\PR-Agent-Dashboard)')
    parser.add_argument('--uninstall', action='store_true',
                        help='Uninstall the dashboard')
    
    args = parser.parse_args()
    
    # Check if running as administrator
    if not check_admin():
        print("Error: This script must be run as Administrator")
        sys.exit(1)
    
    try:
        if args.uninstall:
            uninstall_dashboard(args.install_dir)
        else:
            print("PR Agent Dashboard Windows Deployment (NSSM)")
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
            
            # Download and setup NSSM
            nssm_exe = download_nssm(args.install_dir)
            
            # Create services
            backend_service, frontend_service = create_services_with_nssm(
                args.install_dir, args.backend_port, args.frontend_port, nssm_exe
            )
            
            # Create management scripts
            create_management_scripts(args.install_dir, backend_service, frontend_service, nssm_exe)
            
            # Start services
            start_services(backend_service, frontend_service)
            
            print()
            print("=" * 50)
            print("✓ PR Agent Dashboard deployed successfully!")
            print()
            print(f"Installation directory: {args.install_dir}")
            print(f"Frontend URL: http://localhost:{args.frontend_port}")
            print(f"Backend URL: http://localhost:{args.backend_port}")
            print()
            print("Windows Services:")
            print(f"  Backend:  {backend_service}")
            print(f"  Frontend: {frontend_service}")
            print()
            print("Management Scripts:")
            print(f"  Status:     {args.install_dir}\\status.bat")
            print(f"  Restart:    {args.install_dir}\\restart.bat")
            print(f"  Uninstall:  {args.install_dir}\\uninstall_services.bat")
            print()
            print("Service Management:")
            print(f"  sc start {backend_service}")
            print(f"  sc start {frontend_service}")
            print(f"  sc stop {backend_service}")
            print(f"  sc stop {frontend_service}")
            print()
            print("Logs:")
            print(f"  Backend:  {args.install_dir}\\logs\\backend.log")
            print(f"  Frontend: {args.install_dir}\\logs\\frontend.log")
            print()
            print("To uninstall:")
            print("  python deploy_nssm.py --uninstall")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 