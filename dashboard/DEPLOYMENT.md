# PR Agent Dashboard Deployment Guide

This guide provides comprehensive instructions for deploying the PR Agent Dashboard as a production service across different operating systems.

## 🚀 Available Deployment Scripts

| Script | Platform | Description |
|--------|----------|-------------|
| `deploy.py` | Linux | Full-featured Python deployment script |
| `deploy.sh` | Linux | Lightweight shell script alternative |
| `deploy.py` | Windows | Python deployment script for Windows |

## 📋 Prerequisites

### Linux Requirements
- **Operating System**: Ubuntu 18.04+, CentOS 7+, or any Linux with systemd
- **Python**: 3.8 or later
- **Node.js**: 16 or later
- **Nginx**: Latest stable version
- **Root Access**: Must run with `sudo`

### Windows Requirements
- **Operating System**: Windows 10/11 or Windows Server 2016+
- **Python**: 3.8 or later
- **Node.js**: 16 or later
- **Administrator Access**: Must run as Administrator

## 🔧 Installation

### Linux Deployment

#### Using Python Script (Recommended)
```bash
# Deploy with default ports (frontend: 3000, backend: 8000)
sudo python3 deploy.py

# Deploy with custom ports
sudo python3 deploy.py --frontend-port 8080 --backend-port 8081

# Deploy to custom directory
sudo python3 deploy.py --install-dir /srv/pr-agent-dashboard

# Uninstall
sudo python3 deploy.py --uninstall
```

#### Using Shell Script
```bash
# Make script executable
chmod +x deploy.sh

# Deploy with default ports
sudo ./deploy.sh

# Deploy with custom ports
sudo ./deploy.sh --frontend-port 8080 --backend-port 8081

# Deploy to custom directory
sudo ./deploy.sh --install-dir /srv/pr-agent-dashboard

# Uninstall
sudo ./deploy.sh --uninstall
```

### Windows Deployment

#### Using Python Script
```cmd
# Deploy with default ports (frontend: 3000, backend: 8000)
python deploy.py

# Deploy with custom ports
python deploy.py --frontend-port 8080 --backend-port 8081

# Deploy to custom directory
python deploy.py --install-dir "D:\Apps\PR-Agent-Dashboard"

# Uninstall
python deploy.py --uninstall

# Show help
python deploy.py --help
```

## 🏗️ What the Scripts Do

### 1. System Requirements Check
- Verifies operating system compatibility
- Checks for required dependencies (Python, Node.js, web server)
- Validates port availability and configuration

### 2. Service User Creation
- **Linux**: Creates `pr-agent-dashboard` system user
- **Windows**: Uses LocalSystem account

### 3. File Deployment
- Copies backend and frontend files to installation directory
- **Default Linux**: `/opt/pr-agent-dashboard`
- **Default Windows**: `C:\Program Files\PR-Agent-Dashboard`

### 4. Backend Configuration
- Creates production-ready `settings.toml`
- Configures database path and API settings
- Sets up CORS for frontend communication
- Configures host binding for external access (`0.0.0.0`)

### 5. Frontend Build
- Installs npm dependencies
- Builds React app for production
- Optimizes assets and removes source maps

### 6. Dependencies Installation
- Creates Python virtual environment
- Installs backend dependencies from `requirements.txt`

### 7. Web Server Configuration
- **Linux**: Configures Nginx reverse proxy
- **Windows**: Uses Python HTTP server for static files
- Sets up static file serving and API proxying
- Configures WebSocket support

### 8. Service Creation
- **Linux**: Creates systemd service
- **Windows**: Creates Windows service
- Configures automatic startup and restart policies

### 9. Security Configuration
- Sets proper file permissions
- Configures firewall rules
- Applies security headers

## 🌐 Network Configuration

### External Access
Both frontend and backend are configured to accept connections from any IP address:
- **Frontend**: Served by web server (Nginx/IIS) on specified port
- **Backend**: API server bound to `0.0.0.0` on specified port

### Firewall Configuration
The scripts automatically configure firewall rules:
- **Linux**: Uses existing firewall configuration
- **Windows**: Manual firewall configuration may be required

### Port Requirements
- **Frontend Port**: Default 3000 (configurable)
- **Backend Port**: Default 8000 (configurable)
- **Port Range**: 1024-65535
- **Validation**: Ensures ports don't conflict

## 🔧 Service Management

### Linux (systemd)
```bash
# Service status
sudo systemctl status pr-agent-dashboard

# Start service
sudo systemctl start pr-agent-dashboard

# Stop service
sudo systemctl stop pr-agent-dashboard

# Restart service
sudo systemctl restart pr-agent-dashboard

# View logs
sudo journalctl -u pr-agent-dashboard -f

# Enable/disable auto-start
sudo systemctl enable pr-agent-dashboard
sudo systemctl disable pr-agent-dashboard
```

### Windows Services
```cmd
# Service status
sc query PRAgentDashboard

# Start services
sc start PRAgentDashboard
sc start PRAgentDashboard-Frontend

# Stop services
sc stop PRAgentDashboard
sc stop PRAgentDashboard-Frontend

# View logs (Event Viewer)
eventvwr.msc

# Set startup type
sc config PRAgentDashboard start= auto
sc config PRAgentDashboard-Frontend start= auto
```

## 📊 Access URLs

After successful deployment, access the dashboard at:

- **Frontend**: `http://your-server-ip:frontend-port`
- **Backend API**: `http://your-server-ip:backend-port`
- **API Documentation**: `http://your-server-ip:backend-port/docs`

## 🔍 Troubleshooting

### Common Issues

#### Linux
1. **Permission Denied**: Ensure running with `sudo`
2. **Port Already in Use**: Check with `netstat -tlnp | grep :port`
3. **Service Won't Start**: Check logs with `journalctl -u pr-agent-dashboard`
4. **Nginx Issues**: Test config with `nginx -t`

#### Windows
1. **Access Denied**: Ensure running as Administrator
2. **IIS Not Available**: Enable IIS features as prompted
3. **Service Won't Start**: Check Windows Event Viewer
4. **Port Conflicts**: Use `netstat -an | findstr :port`

### Log Locations

#### Linux
- **Service Logs**: `journalctl -u pr-agent-dashboard`
- **Nginx Logs**: `/var/log/nginx/`
- **Application Logs**: Check systemd journal

#### Windows
- **Service Logs**: Windows Event Viewer → Application
- **IIS Logs**: `C:\inetpub\logs\LogFiles\`
- **Application Logs**: Event Viewer → Windows Logs → Application

## 🔄 Updates and Maintenance

### Updating the Dashboard
1. Stop the service
2. Backup configuration files
3. Run deployment script again
4. Service will be updated with new code

### Backup Important Files
- Database: `dashboard.db`
- Configuration: `settings.toml`
- Custom configurations in installation directory

## 🛡️ Security Considerations

### Default Security Features
- Dedicated service user with minimal privileges
- Firewall rules for required ports only
- Security headers configured
- Static file caching enabled

### Additional Security Recommendations
- Use HTTPS in production (configure SSL certificates)
- Implement reverse proxy authentication
- Regular security updates
- Monitor logs for suspicious activity
- Use strong passwords for service accounts

## 📚 Architecture Overview

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Web Browser   │    │   Web Server    │    │   Backend API   │
│                 │    │  (Nginx/IIS)    │    │   (FastAPI)     │
│                 │◄──►│                 │◄──►│                 │
│                 │    │  Static Files   │    │  Database       │
│                 │    │  Reverse Proxy  │    │  Business Logic │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Components
- **Frontend**: React SPA served by web server
- **Backend**: FastAPI application with SQLite database
- **Web Server**: Nginx (Linux) or IIS (Windows)
- **Database**: SQLite file database
- **Service**: systemd (Linux) or Windows Service

## 🆘 Support

For deployment issues:
1. Check this documentation
2. Review service logs
3. Verify system requirements
4. Check network connectivity
5. Ensure proper permissions

## 📝 Configuration Files

### Backend Settings (`settings.toml`)
```toml
[default]
app_name = "PR-Agent Dashboard"
debug = false
log_level = "INFO"
api_host = "0.0.0.0"
api_port = 8000
developer_mode = false
database_url = "sqlite:///path/to/dashboard.db"
cors_origins = ["http://localhost:3000"]
```

### Nginx Configuration (Linux)
- Location: `/etc/nginx/sites-available/pr-agent-dashboard`
- Features: Static file serving, API proxy, WebSocket support
- Security: Headers, caching, request filtering

### IIS Configuration (Windows)
- Location: `web.config` files in site directories
- Features: URL rewrite, static files, reverse proxy
- Security: MIME types, security headers

This completes the comprehensive deployment guide for the PR Agent Dashboard across all supported platforms. 