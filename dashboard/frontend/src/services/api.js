import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor for adding auth token if needed
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor for handling errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('auth_token');
      // Redirect to login if needed
    }
    return Promise.reject(error);
  }
);

// API endpoints
const apiService = {
  // Operations
  getOperations: (params = {}) => api.get('/api/operations', { params }),
  getOperation: (id) => api.get(`/api/operations/${id}`),
  
  // Logs
  getLogs: (params = {}) => api.get('/api/logs', { params }),
  getLogsByOperation: (operationId) => api.get(`/api/logs/operation/${operationId}`),
  
  // System Health & Status
  getSystemHealth: () => api.get('/api/health'),
  getSystemStatus: () => api.get('/api/status'),
  getRealtimeStatus: () => api.get('/api/status/realtime'),
  
  // Production Monitoring
  getSystemAlerts: () => api.get('/api/system/alerts'),
  getSystemPerformance: () => api.get('/api/system/performance'),
  
  // Dashboard configuration
  getConfig: () => api.get('/api/config'),
  updateConfig: (config) => api.post('/api/config', { config }),
  getAvailableModels: () => api.get('/api/config/models'),
  
  // Repository management
  getRepositories: (params = {}) => api.get('/api/repositories', { params }),
  getRepository: (id) => api.get(`/api/repositories/${id}`),
  createRepository: (data) => api.post('/api/repositories', data),
  updateRepository: (id, data) => api.put(`/api/repositories/${id}`, data),
  deleteRepository: (id) => api.delete(`/api/repositories/${id}`),
  getRepositoryNames: (params = {}) => api.get('/api/repositories/names', { params }),
  
  // Developer mode
  getDeveloperMode: () => api.get('/api/developer-mode'),
  
  // Developer tools (only available when developer mode is enabled)
  generateTestData: () => api.post('/api/dev/generate-test-data'),
  simulateActivity: () => api.post('/api/dev/simulate-activity'),
  failActivity: (operationId) => api.post('/api/dev/fail-activity', { operation_id: operationId }),
  succeedActivity: (operationId) => api.post('/api/dev/succeed-activity', { operation_id: operationId }),
  triggerError: () => api.post('/api/dev/trigger-error'),
  clearData: () => api.post('/api/dev/clear-data'),
};

export default apiService; 