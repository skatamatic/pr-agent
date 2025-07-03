class WebSocketService {
  constructor() {
    this.ws = null;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 10;
    this.reconnectDelay = 1000;
    this.listeners = new Map();
    this.isConnecting = false;
    this.reconnectTimeout = null;
    this.shouldReconnect = true;
    this.heartbeatInterval = null;
    this.lastPingTime = null;
  }

  connect(url = 'ws://localhost:8000/ws') {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      return Promise.resolve();
    }

    if (this.isConnecting) {
      return Promise.resolve();
    }

    // Clean up any existing connection before creating new one
    if (this.ws && this.ws.readyState !== WebSocket.CLOSED) {
      this.ws.close();
      this.ws = null;
    }

    this.isConnecting = true;

    return new Promise((resolve, reject) => {
      try {
        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
          console.log('WebSocket connected');
          this.reconnectAttempts = 0;
          this.isConnecting = false;
          this.shouldReconnect = true;
          this.startHeartbeat();
          this.emit('connected');
          resolve();
        };

        this.ws.onmessage = (event) => {
          try {
            const message = JSON.parse(event.data);
            this.handleMessage(message);
          } catch (error) {
            console.error('Error parsing WebSocket message:', error);
          }
        };

        this.ws.onclose = (event) => {
          console.log('WebSocket disconnected:', event.code, event.reason);
          this.isConnecting = false;
          this.stopHeartbeat();
          this.emit('disconnected');
          
          // Attempt reconnection if not a normal close and we should reconnect
          if (this.shouldReconnect && event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect();
          } else if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.warn('Max reconnection attempts reached, giving up');
            this.emit('max_reconnect_attempts_reached');
          }
        };

        this.ws.onerror = (error) => {
          console.error('WebSocket error:', error);
          console.error('WebSocket state when error occurred:', this.ws ? this.ws.readyState : 'null');
          this.isConnecting = false;
          this.emit('error', error);
          reject(error);
        };

      } catch (error) {
        this.isConnecting = false;
        reject(error);
      }
    });
  }

  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts || !this.shouldReconnect) {
      console.log('Max reconnection attempts reached or reconnection disabled');
      return;
    }

    // Clear any existing reconnect timeout
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
    }

    this.reconnectAttempts++;
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 30000); // Cap at 30 seconds
    
    console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
    
    this.reconnectTimeout = setTimeout(() => {
      if (this.shouldReconnect) {
        this.connect().catch(error => {
          console.error('Reconnection failed:', error);
          // If connection fails, schedule another attempt
          if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.scheduleReconnect();
          }
        });
      }
    }, delay);
  }

  handleMessage(message) {
    const { type, data } = message;
    
    switch (type) {
      case 'welcome':
        console.log('WebSocket welcome:', message.message);
        break;
      case 'ping':
        // Handle keepalive ping and update last ping time
        this.lastPingTime = Date.now();
        break;
      case 'log':
        this.emit('log', data);
        break;
      case 'logs_batch':
        // Handle batch logs - emit individual log events for each log
        if (data && Array.isArray(data)) {
          data.forEach(logInfo => {
            // Emit a log event for each log in the batch
            this.emit('log', { id: logInfo.id, message: logInfo.message });
          });
        }
        break;
      case 'operation_update':
        this.emit('operation_update', data);
        break;
      case 'operation_step_update':
        // Handle step updates as operation updates
        this.emit('operation_update', data);
        break;
      case 'job_update':
        this.emit('job_update', data);
        break;
              case 'metrics_update':
          this.emit('metrics_update', data);
          break;
      case 'system_status':
        this.emit('system_status', data);
        break;
      case 'notification_event':
        this.emit('notification_event', data);
        break;
      case 'backup_restore_progress':
        this.emit('backup_restore_progress', message);
        break;
      case 'backup_restore_complete':
        this.emit('backup_restore_complete', message);
        break;
      default:
        console.log('Unknown WebSocket message type:', type, data);
    }
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  off(event, callback) {
    if (this.listeners.has(event)) {
      const callbacks = this.listeners.get(event);
      const index = callbacks.indexOf(callback);
      if (index > -1) {
        callbacks.splice(index, 1);
      }
    }
  }

  emit(event, data) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach(callback => {
        try {
          callback(data);
        } catch (error) {
          console.error('Error in WebSocket event callback:', error);
        }
      });
    }
  }

  send(message) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      try {
        this.ws.send(JSON.stringify(message));
      } catch (error) {
        console.error('Failed to send WebSocket message:', error);
        // Connection might be broken, trigger reconnection
        if (this.shouldReconnect) {
          this.forceReconnect();
        }
      }
    } else {
      console.warn('WebSocket not connected, cannot send message:', message);
      // Try to reconnect if we should
      if (this.shouldReconnect && !this.isConnecting) {
        this.forceReconnect();
      }
    }
  }

  disconnect() {
    this.shouldReconnect = false;
    this.isConnecting = false;
    
    // Clear reconnect timeout
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    
    this.stopHeartbeat();
    
    if (this.ws) {
      // Set onclose to null to prevent reconnection logic from triggering
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close(1000, 'Manual disconnect');
      this.ws = null;
    }
    
    // Don't clear listeners as they might be needed for reconnection
    // this.listeners.clear();
  }

  isConnected() {
    return this.ws && this.ws.readyState === WebSocket.OPEN;
  }

  startHeartbeat() {
    this.stopHeartbeat();
    this.lastPingTime = Date.now();
    
    // Check for missed pings every 45 seconds (server sends pings every 30 seconds)
    this.heartbeatInterval = setInterval(() => {
      if (this.isConnected()) {
        const timeSinceLastPing = Date.now() - (this.lastPingTime || Date.now());
        if (timeSinceLastPing > 45000) { // 45 seconds
          console.warn('No ping received for 45 seconds, assuming connection is dead');
          this.ws.close(1006, 'Connection timeout');
        }
      }
    }, 15000); // Check every 15 seconds
  }

  stopHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  forceReconnect() {
    console.log('Forcing reconnection...');
    if (this.ws) {
      this.ws.close(1000, 'Force reconnect');
    }
    this.reconnectAttempts = 0;
    this.shouldReconnect = true;
    this.connect();
  }
}

// Create singleton instance
const webSocketService = new WebSocketService();

export default webSocketService; 