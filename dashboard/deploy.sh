#!/bin/bash

# PR Agent Dashboard Deployment Script (Shell Version)
# Simple deployment script for production deployment

set -e

# Default values
FRONTEND_PORT=3000
BACKEND_PORT=8000
INSTALL_DIR="/opt/pr-agent-dashboard"
SERVICE_USER="pr-agent-dashboard"
UNINSTALL=false

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

# Function to show usage
show_help() {
    cat << EOF
PR Agent Dashboard Deployment Script

Usage: $0 [OPTIONS]

Options:
    -f, --frontend-port PORT    Frontend port (default: 3000)
    -b, --backend-port PORT     Backend port (default: 8000)
    -d, --install-dir DIR       Installation directory (default: /opt/pr-agent-dashboard)
    -u, --uninstall            Uninstall the dashboard
    -h, --help                 Show this help message

Examples:
    # Deploy with default ports
    sudo $0

    # Deploy with custom ports
    sudo $0 --frontend-port 8080 --backend-port 8081

    # Deploy to custom directory
    sudo $0 --install-dir /srv/pr-agent-dashboard

    # Uninstall
    sudo $0 --uninstall
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -f|--frontend-port)
            FRONTEND_PORT="$2"
            shift 2
            ;;
        -b|--backend-port)
            BACKEND_PORT="$2"
            shift 2
            ;;
        -d|--install-dir)
            INSTALL_DIR="$2"
            shift 2
            ;;
        -u|--uninstall)
            UNINSTALL=true
            shift
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Function to check if running as root
check_root() {
    if [[ $EUID -ne 0 ]]; then
        print_error "This script must be run as root (use sudo)"
        exit 1
    fi
}

# Function to check system requirements
check_requirements() {
    print_info "Checking system requirements..."
    
    # Check if systemd is available
    if ! command -v systemctl &> /dev/null; then
        print_error "systemctl not found. This script requires systemd."
        exit 1
    fi
    
    # Check required commands
    local required_commands=("python3" "npm" "nginx")
    local missing_commands=()
    
    for cmd in "${required_commands[@]}"; do
        if ! command -v "$cmd" &> /dev/null; then
            missing_commands+=("$cmd")
        fi
    done
    
    if [[ ${#missing_commands[@]} -gt 0 ]]; then
        print_error "Missing required commands: ${missing_commands[*]}"
        if [[ " ${missing_commands[@]} " =~ " nginx " ]]; then
            echo "  Install nginx: sudo apt-get install nginx (Ubuntu/Debian)"
        fi
        if [[ " ${missing_commands[@]} " =~ " npm " ]]; then
            echo "  Install Node.js and npm: https://nodejs.org/"
        fi
        exit 1
    fi
    
    # Validate ports
    if [[ $FRONTEND_PORT -lt 1024 || $FRONTEND_PORT -gt 65535 ]]; then
        print_error "Frontend port must be between 1024-65535"
        exit 1
    fi
    
    if [[ $BACKEND_PORT -lt 1024 || $BACKEND_PORT -gt 65535 ]]; then
        print_error "Backend port must be between 1024-65535"
        exit 1
    fi
    
    if [[ $FRONTEND_PORT -eq $BACKEND_PORT ]]; then
        print_error "Frontend and backend ports cannot be the same"
        exit 1
    fi
    
    print_status "System requirements satisfied"
}

# Function to create system user
create_system_user() {
    print_info "Creating system user: $SERVICE_USER"
    
    if id "$SERVICE_USER" &>/dev/null; then
        print_info "User $SERVICE_USER already exists"
    else
        useradd --system --shell /bin/false --home "$INSTALL_DIR" --create-home "$SERVICE_USER"
        print_status "Created system user: $SERVICE_USER"
    fi
}

# Function to copy files
copy_files() {
    print_info "Copying files to $INSTALL_DIR..."
    
    # Get script directory
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Create installation directory
    mkdir -p "$INSTALL_DIR"
    
    # Copy backend files
    if [[ -d "$INSTALL_DIR/backend" ]]; then
        rm -rf "$INSTALL_DIR/backend"
    fi
    cp -r "$SCRIPT_DIR/backend" "$INSTALL_DIR/"
    
    # Copy frontend files
    if [[ -d "$INSTALL_DIR/frontend" ]]; then
        rm -rf "$INSTALL_DIR/frontend"
    fi
    cp -r "$SCRIPT_DIR/frontend" "$INSTALL_DIR/"
    
    print_status "Files copied successfully"
}

# Function to configure backend
configure_backend() {
    print_info "Configuring backend..."
    
    cat > "$INSTALL_DIR/backend/settings.toml" << EOF
# Dashboard Configuration - Production Deployment
[default]
app_name = "PR-Agent Dashboard"
debug = false
log_level = "INFO"
log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

# API server settings - Accept connections from any IP
api_host = "0.0.0.0"
api_port = $BACKEND_PORT
developer_mode = false

# Database settings
database_url = "sqlite:///$INSTALL_DIR/dashboard.db"
database_echo = false

# CORS settings - Allow frontend access
cors_origins = [
    "http://localhost:$FRONTEND_PORT",
    "http://127.0.0.1:$FRONTEND_PORT",
    "http://0.0.0.0:$FRONTEND_PORT"
]

[production]
debug = false
log_level = "INFO"
developer_mode = false
api_host = "0.0.0.0"
api_port = $BACKEND_PORT
EOF
    
    print_status "Backend configured for production"
}

# Function to install Python dependencies
install_python_dependencies() {
    print_info "Installing Python dependencies..."
    
    # Create virtual environment
    if [[ -d "$INSTALL_DIR/venv" ]]; then
        rm -rf "$INSTALL_DIR/venv"
    fi
    
    python3 -m venv "$INSTALL_DIR/venv"
    
    # Install dependencies
    "$INSTALL_DIR/venv/bin/pip" install --upgrade pip
    "$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/backend/requirements.txt"
    
    print_status "Python dependencies installed"
}

# Function to build frontend
build_frontend() {
    print_info "Building frontend for production..."
    
    cd "$INSTALL_DIR/frontend"
    
    # Install npm dependencies
    npm install
    
    # Build the frontend
    export REACT_APP_API_URL="http://localhost:$BACKEND_PORT"
    export GENERATE_SOURCEMAP=false
    npm run build
    
    print_status "Frontend built successfully"
}

# Function to configure nginx
configure_nginx() {
    print_info "Configuring nginx..."
    
    cat > /etc/nginx/sites-available/pr-agent-dashboard << EOF
server {
    listen $FRONTEND_PORT;
    listen [::]:$FRONTEND_PORT;
    server_name _;
    
    # Serve built React app
    location / {
        root $INSTALL_DIR/frontend/build;
        try_files \$uri \$uri/ /index.html;
        
        # Security headers
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "no-referrer-when-downgrade" always;
        add_header Content-Security-Policy "default-src 'self' http: https: data: blob: 'unsafe-inline'" always;
    }
    
    # Proxy API requests to backend
    location /api/ {
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        
        # WebSocket support
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
    }
    
    # WebSocket endpoint
    location /ws {
        proxy_pass http://127.0.0.1:$BACKEND_PORT;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
    
    # Static files caching
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg)$ {
        root $INSTALL_DIR/frontend/build;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
EOF
    
    # Enable the site
    if [[ -L /etc/nginx/sites-enabled/pr-agent-dashboard ]]; then
        rm /etc/nginx/sites-enabled/pr-agent-dashboard
    fi
    ln -s /etc/nginx/sites-available/pr-agent-dashboard /etc/nginx/sites-enabled/
    
    # Test and reload nginx
    nginx -t
    systemctl reload nginx
    
    print_status "Nginx configured and reloaded"
}

# Function to create systemd service
create_systemd_service() {
    print_info "Creating systemd service..."
    
    cat > /etc/systemd/system/pr-agent-dashboard.service << EOF
[Unit]
Description=PR Agent Dashboard Backend
After=network.target
Wants=network.target

[Service]
Type=exec
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR/backend
Environment=PATH=$INSTALL_DIR/venv/bin
ExecStart=$INSTALL_DIR/venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port $BACKEND_PORT --workers 1
ExecReload=/bin/kill -HUP \$MAINPID
KillMode=mixed
TimeoutStopSec=5
PrivateTmp=true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    chmod 644 /etc/systemd/system/pr-agent-dashboard.service
    
    print_status "Systemd service created"
}

# Function to set permissions
set_permissions() {
    print_info "Setting file permissions..."
    
    # Change ownership to service user
    chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
    
    # Set directory permissions
    chmod -R 755 "$INSTALL_DIR"
    
    print_status "Permissions set"
}

# Function to start services
start_services() {
    print_info "Starting services..."
    
    # Reload systemd
    systemctl daemon-reload
    
    # Enable and start the service
    systemctl enable pr-agent-dashboard.service
    systemctl start pr-agent-dashboard.service
    
    # Ensure nginx is enabled and running
    systemctl enable nginx
    systemctl start nginx
    
    print_status "Services started and enabled"
}

# Function to show status
show_status() {
    echo
    echo "============================================================"
    echo "🎉 PR Agent Dashboard Deployment Complete!"
    echo "============================================================"
    
    # Get system IP
    local primary_ip
    primary_ip=$(hostname -I | awk '{print $1}')
    if [[ -z "$primary_ip" ]]; then
        primary_ip="localhost"
    fi
    
    echo "📊 Frontend URL: http://$primary_ip:$FRONTEND_PORT"
    echo "🔗 Backend API: http://$primary_ip:$BACKEND_PORT"
    echo "📚 API Documentation: http://$primary_ip:$BACKEND_PORT/docs"
    echo "📁 Installation Directory: $INSTALL_DIR"
    echo "👤 Service User: $SERVICE_USER"
    echo
    echo "🔧 Service Management:"
    echo "  Status:  sudo systemctl status pr-agent-dashboard"
    echo "  Start:   sudo systemctl start pr-agent-dashboard"
    echo "  Stop:    sudo systemctl stop pr-agent-dashboard"
    echo "  Restart: sudo systemctl restart pr-agent-dashboard"
    echo "  Logs:    sudo journalctl -u pr-agent-dashboard -f"
    echo
    echo "🌐 Network Access:"
    echo "  The dashboard is configured to accept connections from any IP address"
    echo "  Make sure your firewall allows incoming connections on the specified ports"
    echo "  Frontend port: $FRONTEND_PORT"
    echo "  Backend port: $BACKEND_PORT"
    echo
    echo "📊 Current Service Status:"
    systemctl status pr-agent-dashboard --no-pager || true
}

# Function to uninstall
uninstall_dashboard() {
    print_info "Uninstalling PR Agent Dashboard..."
    
    # Stop and disable service
    systemctl stop pr-agent-dashboard || true
    systemctl disable pr-agent-dashboard || true
    
    # Remove service file
    rm -f /etc/systemd/system/pr-agent-dashboard.service
    
    # Remove nginx config
    rm -f /etc/nginx/sites-enabled/pr-agent-dashboard
    rm -f /etc/nginx/sites-available/pr-agent-dashboard
    
    # Reload nginx
    systemctl reload nginx || true
    
    # Remove installation directory
    rm -rf "$INSTALL_DIR"
    
    # Remove system user
    userdel "$SERVICE_USER" || true
    
    # Reload systemd
    systemctl daemon-reload
    
    print_status "Dashboard uninstalled successfully"
}

# Main deployment function
deploy() {
    echo "🚀 Starting PR Agent Dashboard deployment..."
    echo "   Frontend Port: $FRONTEND_PORT"
    echo "   Backend Port: $BACKEND_PORT"
    echo "   Install Directory: $INSTALL_DIR"
    echo
    
    check_requirements
    create_system_user
    copy_files
    configure_backend
    build_frontend
    install_python_dependencies
    configure_nginx
    create_systemd_service
    set_permissions
    start_services
    show_status
}

# Main script execution
check_root

if [[ "$UNINSTALL" == true ]]; then
    uninstall_dashboard
else
    deploy
fi 