#!/usr/bin/env python3
"""
Simple startup script for the PR Agent Dashboard
Starts both the backend API and frontend development server
"""

import subprocess
import sys
import os
import time
import signal
from pathlib import Path
import threading
import queue

def check_dependencies():
    """Check if required dependencies are available"""
    try:
        import uvicorn
        import fastapi
    except ImportError:
        print("❌ Backend dependencies not found. Please run:")
        print("   cd dashboard/backend && pip install -r requirements.txt")
        return False
    
    # Check if npm is available (try both npm and npm.cmd for Windows)
    npm_commands = ["npm", "npm.cmd"]
    npm_found = False
    
    for npm_cmd in npm_commands:
        try:
            subprocess.run([npm_cmd, "--version"], capture_output=True, check=True)
            npm_found = True
            break
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    
    if not npm_found:
        print("❌ npm not found. Please install Node.js and npm")
        return False
    
    return True

def monitor_process(process, name, restart_queue):
    """Monitor a process and handle restarts appropriately"""
    while True:
        return_code = process.wait()
        
        # For backend with hot-reload, exit code 0 usually means a successful restart
        # Exit codes like 3 might indicate a restart request
        if name == "backend" and return_code in [0, 3]:
            print(f"🔄 Backend restarted (exit code: {return_code})")
            # Don't treat this as a failure, uvicorn --reload handles restarts
            continue
        else:
            print(f"❌ {name} process stopped with exit code: {return_code}")
            restart_queue.put(('stop_all', name, return_code))
            break

def start_backend():
    """Start the FastAPI backend server"""
    print("🚀 Starting backend server...")
    backend_dir = Path(__file__).parent / "backend"
    
    # Change to backend directory and start uvicorn
    env = os.environ.copy()
    env["PYTHONPATH"] = str(backend_dir)
    
    return subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"],
        cwd=backend_dir,
        env=env
    )

def get_npm_command():
    """Get the correct npm command for the platform"""
    npm_commands = ["npm", "npm.cmd"]
    for npm_cmd in npm_commands:
        try:
            subprocess.run([npm_cmd, "--version"], capture_output=True, check=True)
            return npm_cmd
        except (subprocess.CalledProcessError, FileNotFoundError):
            continue
    return "npm"  # fallback

def start_frontend():
    """Start the React frontend development server"""
    print("🎨 Starting frontend server...")
    frontend_dir = Path(__file__).parent / "frontend"
    npm_cmd = get_npm_command()
    
    # Check if node_modules exists
    if not (frontend_dir / "node_modules").exists():
        print("📦 Installing frontend dependencies...")
        subprocess.run([npm_cmd, "install"], cwd=frontend_dir, check=True)
    
    # Set environment variables to fix webpack dev server issues
    env = os.environ.copy()
    env["DANGEROUSLY_DISABLE_HOST_CHECK"] = "true"
    env["REACT_APP_API_URL"] = "http://localhost:8000"
    
    return subprocess.Popen(
        [npm_cmd, "start"],
        cwd=frontend_dir,
        env=env
    )

def main():
    """Main startup function"""
    print("🔧 PR Agent Dashboard Startup")
    print("=" * 40)
    
    if not check_dependencies():
        sys.exit(1)
    
    processes = {}
    threads = {}
    restart_queue = queue.Queue()
    
    try:
        # Start backend
        backend_process = start_backend()
        processes['backend'] = backend_process
        time.sleep(3)  # Give backend time to start
        
        # Start frontend  
        frontend_process = start_frontend()
        processes['frontend'] = frontend_process
        
        # Start monitoring threads (only for frontend, backend handles its own restarts)
        threads['frontend'] = threading.Thread(
            target=monitor_process, 
            args=(frontend_process, 'frontend', restart_queue),
            daemon=True
        )
        threads['frontend'].start()
        
        print("\n✅ Dashboard started successfully!")
        print("📊 Frontend: http://localhost:3000")
        print("🔗 Backend API: http://localhost:8000")
        print("📚 API Docs: http://localhost:8000/docs")
        print("\n💡 Hot-reload is enabled for both frontend and backend")
        print("   - Backend changes will auto-restart the server")
        print("   - Frontend changes will auto-refresh the browser")
        print("\nPress Ctrl+C to stop all services")
        
        # Main loop - only exit on explicit shutdown or frontend issues
        while True:
            try:
                # Check for restart signals (non-blocking)
                action, process_name, exit_code = restart_queue.get(timeout=1)
                if action == 'stop_all':
                    if process_name == 'frontend':
                        print(f"❌ Frontend stopped unexpectedly (exit code: {exit_code})")
                        break
                    # Ignore backend restarts as they're handled by uvicorn --reload
            except queue.Empty:
                # Check if backend is still responsive (but don't restart it)
                if processes['backend'].poll() is not None:
                    # Backend died for real, this is a problem
                    return_code = processes['backend'].poll()
                    if return_code not in [0, 3]:  # Not a normal restart
                        print(f"❌ Backend stopped unexpectedly (exit code: {return_code})")
                        break
                continue
    
    except KeyboardInterrupt:
        print("\n🛑 Shutting down dashboard...")
    
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
    
    finally:
        # Terminate all processes
        for name, process in processes.items():
            try:
                if process.poll() is None:  # Process is still running
                    print(f"🛑 Stopping {name}...")
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        print(f"⚡ Force killing {name}...")
                        process.kill()
            except Exception as e:
                print(f"⚠️  Error stopping {name}: {e}")
        
        print("✅ Dashboard stopped")

if __name__ == "__main__":
    main() 