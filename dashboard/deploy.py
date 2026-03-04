#!/usr/bin/env python3
"""
PR Agent Dashboard Windows Deployment Script

This script deploys the PR Agent Dashboard as Windows services.
Run with administrator privileges.
"""

import os
import sys
import subprocess
import shutil
import argparse
import json
import urllib.request
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

def create_service_user(service_name):
    """Create a service user (on Windows, we'll use LocalSystem)"""
    print(f"Service will run as LocalSystem account")
    return "LocalSystem"

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

def create_service_script(install_dir, service_name, backend_port):
    """Create Python service script"""
    print("Creating service script...")
    
    venv_dir = Path(install_dir) / "venv"
    python_path = venv_dir / "Scripts" / "python.exe"
    backend_dir = Path(install_dir) / "backend"
    service_script = Path(install_dir) / "service.py"
    
    # Escape paths for Python
    python_path_escaped = str(python_path).replace('\\', '\\\\')
    backend_dir_escaped = str(backend_dir).replace('\\', '\\\\')
    
    service_content = f'''import os
import sys
import subprocess
import time
import win32serviceutil
import win32service
import win32event
import servicemanager

class PRAgentDashboardService(win32serviceutil.ServiceFramework):
    _svc_name_ = "{service_name}"
    _svc_display_name_ = "PR Agent Dashboard Backend"
    _svc_description_ = "Backend service for PR Agent Dashboard"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.process = None
    
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except:
                self.process.kill()
        win32event.SetEvent(self.hWaitStop)
    
    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        
        try:
            # Change to backend directory
            os.chdir(r"{backend_dir_escaped}")
            
            # Start uvicorn
            self.process = subprocess.Popen([
                r"{python_path_escaped}", "-m", "uvicorn", "main:app",
                "--host", "0.0.0.0", "--port", "{backend_port}", "--workers", "1"
            ])
            
            # Wait for stop signal
            win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
            
        except Exception as e:
            servicemanager.LogErrorMsg("Service error: " + str(e))

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(PRAgentDashboardService)
'''
    
    service_script.write_text(service_content, encoding='utf-8')
    
    # Install pywin32 for service support
    python_path = venv_dir / "Scripts" / "python.exe"
    run_command(f'"{python_path}" -m pip install pywin32')
    
    # Test that uvicorn is available
    print("Testing uvicorn availability...")
    result = run_command(f'"{python_path}" -c "import uvicorn; print(uvicorn.__version__)"', check=False)
    if result.returncode != 0:
        print(f"Warning: uvicorn not available: {result.stderr}")
    else:
        print("✓ uvicorn is available")
    
    # Check that backend main.py exists
    main_py = backend_dir / "main.py"
    if not main_py.exists():
        print(f"Warning: Backend main.py not found at {main_py}")
    else:
        print("✓ Backend main.py found")
    
    # Test the service script to ensure it loads properly
    print("Testing service script...")
    result = run_command(f'"{python_path}" -c "import sys; sys.path.insert(0, r\'{install_dir}\'); import service"', check=False)
    if result.returncode != 0:
        print(f"Warning: Service script test failed: {result.stderr}")
    else:
        print("✓ Service script test passed")
    
    # Install the service
    run_command(f'"{python_path}" "{service_script}" install')
    
    print("✓ Windows service created")

def create_frontend_service(install_dir, service_name, frontend_port):
    """Create frontend service"""
    print("Creating frontend service...")
    
    venv_dir = Path(install_dir) / "venv"
    python_path = venv_dir / "Scripts" / "python.exe"
    frontend_build_dir = Path(install_dir) / "frontend" / "build"
    frontend_service_script = Path(install_dir) / "frontend_service.py"
    
    # Escape paths for Python
    python_path_escaped = str(python_path).replace('\\', '\\\\')
    frontend_build_dir_escaped = str(frontend_build_dir).replace('\\', '\\\\')
    
    frontend_service_content = f'''import os
import sys
import subprocess
import time
import win32serviceutil
import win32service
import win32event
import servicemanager

class PRAgentDashboardFrontendService(win32serviceutil.ServiceFramework):
    _svc_name_ = "{service_name}-Frontend"
    _svc_display_name_ = "PR Agent Dashboard Frontend"
    _svc_description_ = "Frontend service for PR Agent Dashboard"
    
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.process = None
    
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except:
                self.process.kill()
        win32event.SetEvent(self.hWaitStop)
    
    def SvcDoRun(self):
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        
        try:
            # Change to frontend build directory
            os.chdir(r"{frontend_build_dir_escaped}")
            
            # Start simple HTTP server
            self.process = subprocess.Popen([
                r"{python_path_escaped}", "-m", "http.server", "{frontend_port}",
                "--bind", "0.0.0.0"
            ])
            
            # Wait for stop signal
            win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
            
        except Exception as e:
            servicemanager.LogErrorMsg("Frontend service error: " + str(e))

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(PRAgentDashboardFrontendService)
'''
    
    frontend_service_script.write_text(frontend_service_content, encoding='utf-8')
    
    # Test the frontend service script to ensure it loads properly
    print("Testing frontend service script...")
    result = run_command(f'"{python_path}" -c "import sys; sys.path.insert(0, r\'{install_dir}\'); import frontend_service"', check=False)
    if result.returncode != 0:
        print(f"Warning: Frontend service script test failed: {result.stderr}")
    else:
        print("✓ Frontend service script test passed")
    
    # Install the frontend service
    run_command(f'"{python_path}" "{frontend_service_script}" install')
    
    print("✓ Frontend service created")

def set_permissions(install_dir):
    """Set file permissions"""
    print("Setting file permissions...")
    
    # On Windows, we'll use icacls to set permissions
    try:
        # Give full control to SYSTEM and Administrators
        run_command(f'icacls "{install_dir}" /grant "SYSTEM:F" /T')
        run_command(f'icacls "{install_dir}" /grant "Administrators:F" /T')
        print("✓ Permissions set")
    except Exception as e:
        print(f"Warning: Could not set permissions: {e}")

def start_services(service_name):
    """Start and enable services"""
    print("Starting services...")
    
    # Wait a moment for services to be fully registered
    import time
    time.sleep(2)
    
    # Check if services are installed first
    backend_service = service_name
    frontend_service = f"{service_name}-Frontend"
    
    print(f"Checking if services are installed...")
    backend_installed = run_command(f'sc query "{backend_service}"', check=False).returncode == 0
    frontend_installed = run_command(f'sc query "{frontend_service}"', check=False).returncode == 0
    
    if not backend_installed:
        print(f"Error: Backend service {backend_service} is not installed")
        return
    
    if not frontend_installed:
        print(f"Error: Frontend service {frontend_service} is not installed")
        return
    
    print(f"✓ Services are installed")
    
    # Configure services to start automatically
    run_command(f'sc config "{backend_service}" start= auto')
    run_command(f'sc config "{frontend_service}" start= auto')
    
    # Start backend service
    print(f"Starting backend service {backend_service}...")
    result = run_command(f'sc start "{backend_service}"', check=False)
    if result.returncode == 0:
        print(f"✓ Backend service {backend_service} started")
    else:
        print(f"Warning: Could not start backend service: {result.stderr}")
        # Try to get more details about the error
        run_command(f'sc query "{backend_service}"', check=False)
    
    # Start frontend service
    print(f"Starting frontend service {frontend_service}...")
    result = run_command(f'sc start "{frontend_service}"', check=False)
    if result.returncode == 0:
        print(f"✓ Frontend service {frontend_service} started")
    else:
        print(f"Warning: Could not start frontend service: {result.stderr}")
        # Try to get more details about the error
        run_command(f'sc query "{frontend_service}"', check=False)
    
    print("✓ Service startup completed")

def uninstall_dashboard(install_dir, service_name):
    """Uninstall the dashboard"""
    print("Uninstalling PR Agent Dashboard...")
    
    # Stop and remove services
    try:
        run_command(f'sc stop "{service_name}"', check=False)
        run_command(f'sc delete "{service_name}"', check=False)
        print(f"✓ Backend service {service_name} removed")
    except Exception as e:
        print(f"Warning: Could not remove backend service: {e}")
    
    try:
        run_command(f'sc stop "{service_name}-Frontend"', check=False)
        run_command(f'sc delete "{service_name}-Frontend"', check=False)
        print(f"✓ Frontend service {service_name}-Frontend removed")
    except Exception as e:
        print(f"Warning: Could not remove frontend service: {e}")
    
    # Remove installation directory
    install_path = Path(install_dir)
    if install_path.exists():
        try:
            shutil.rmtree(install_path)
            print(f"✓ Installation directory {install_dir} removed")
        except Exception as e:
            print(f"Warning: Could not remove installation directory: {e}")
    
    print("✓ Dashboard uninstalled successfully")

def main():
    parser = argparse.ArgumentParser(
        description="PR Agent Dashboard Windows Deployment Script",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deploy with default ports
  python deploy.py

  # Deploy with custom ports
  python deploy.py --frontend-port 8080 --backend-port 8081

  # Deploy to custom directory
  python deploy.py --install-dir "D:\\Apps\\PR-Agent-Dashboard"

  # Uninstall
  python deploy.py --uninstall

Requirements:
  - Windows 10/11 or Windows Server 2016+
  - Python 3.8+
  - Node.js 16+
  - Run as Administrator
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
    
    service_name = "PRAgentDashboard"
    
    try:
        if args.uninstall:
            uninstall_dashboard(args.install_dir, service_name)
        else:
            print("PR Agent Dashboard Windows Deployment")
            print("=" * 40)
            print(f"Frontend port: {args.frontend_port}")
            print(f"Backend port: {args.backend_port}")
            print(f"Installation directory: {args.install_dir}")
            print()
            
            check_requirements()
            create_service_user(service_name)
            copy_files(args.install_dir)
            configure_backend(args.install_dir, args.backend_port, args.frontend_port)
            install_python_dependencies(args.install_dir)
            build_frontend(args.install_dir, args.backend_port, args.frontend_port)
            create_service_script(args.install_dir, service_name, args.backend_port)
            create_frontend_service(args.install_dir, service_name, args.frontend_port)
            set_permissions(args.install_dir)
            start_services(service_name)
            
            print()
            print("=" * 40)
            print("✓ PR Agent Dashboard deployed successfully!")
            print()
            print(f"Frontend URL: http://localhost:{args.frontend_port}")
            print(f"Backend URL: http://localhost:{args.backend_port}")
            print()
            print("Service Management:")
            print(f"  Start Backend:  sc start {service_name}")
            print(f"  Stop Backend:   sc stop {service_name}")
            print(f"  Start Frontend: sc start {service_name}-Frontend")
            print(f"  Stop Frontend:  sc stop {service_name}-Frontend")
            print()
            print("Debug Commands:")
            print(f"  Check Backend Status:  sc query {service_name}")
            print(f"  Check Frontend Status: sc query {service_name}-Frontend")
            print(f"  View Event Logs:       eventvwr.msc")
            print()
            print("To uninstall:")
            print("  python deploy.py --uninstall")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main() 