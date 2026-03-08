import axios from 'axios';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token method
api.setAuthToken = (token) => {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common['Authorization'];
  }
};

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
      delete api.defaults.headers.common['Authorization'];
      // Redirect to login will be handled by the auth context
    } else if (error.response?.status === 203) {
      // 203 Non-Authoritative Information - treat as success for Azure DevOps APIs
      // This often occurs with cached responses from proxies/CDNs
      console.warn('Received 203 Non-Authoritative Information, treating as success:', error.response);
      return Promise.resolve(error.response);
    }
    return Promise.reject(error);
  }
);

// API endpoints
const apiService = {
  // Auth token management
  setAuthToken: (token) => {
    if (token) {
      api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      delete api.defaults.headers.common['Authorization'];
    }
  },
  
  // Generic HTTP methods
  get: (url, config = {}) => api.get(url, config),
  post: (url, data = {}, config = {}) => api.post(url, data, config),
  put: (url, data = {}, config = {}) => api.put(url, data, config),
  delete: (url, config = {}) => api.delete(url, config),
  // Jobs (new primary focus)
  getJobs: (params = {}) => api.get('/api/jobs', { params }),
  getJob: (id) => api.get(`/api/jobs/${id}`),
  getJobOperations: (jobId) => api.get(`/api/jobs/${jobId}/operations`),
  getJobDeletionPreview: (jobId) => api.get(`/api/jobs/${jobId}/deletion-preview`),
  deleteJob: (jobId) => api.delete(`/api/jobs/${jobId}`),
  
  // Data Cleanup
  previewCleanup: (data) => api.post('/api/admin/cleanup/preview', data),
  executeCleanup: (data) => api.post('/api/admin/cleanup/execute', data),
  
  // Operations (legacy support)
  getOperations: (params = {}) => api.get('/api/operations', { params }),
  getOperation: (id) => api.get(`/api/operations/${id}`),
  
  // Logs (enhanced with job/operation filtering)
  getLogs: (params = {}) => api.get('/api/logs', { params }),
  getLogsByJob: (jobId) => api.get(`/api/logs/job/${jobId}`),
  getLogsByOperation: (operationId) => api.get(`/api/logs/operation/${operationId}`),
  
  // System Health & Status
  getSystemHealth: () => api.get('/api/health'),
  getSystemStatus: () => api.get('/api/status'),
  getRealtimeStatus: () => api.get('/api/status/realtime'),
  
  // Individual Health Checks (for async monitoring)
  getHealthCheck: (service) => {
    switch (service) {
      case 'database': return api.get('/api/health/database');
      case 'pr_agent_config': return api.get('/api/health/config');
      case 'context_service': return api.get('/api/health/context');
      default: throw new Error(`Unknown service: ${service}`);
    }
  },
  
  // Production Monitoring
  getSystemAlerts: () => api.get('/api/system/alerts'),
  getSystemPerformance: () => api.get('/api/system/performance'),
  
  // Dashboard configuration
  getConfig: () => api.get('/api/config'),
  updateConfig: (config) => api.post('/api/config', { config }),
  bulkUploadConfig: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/api/config/bulk-upload', formData);
  },

  // Repository management
  getRepositories: (params = {}) => api.get('/api/repositories', { params }),
  getRepository: (id) => api.get(`/api/repositories/${id}`),
  createRepository: (data) => api.post('/api/repositories', data),
  updateRepository: (id, data) => api.put(`/api/repositories/${id}`, data),
  deleteRepository: (id) => api.delete(`/api/repositories/${id}`),
  getRepositoryNames: (params = {}) => api.get('/api/repositories/names', { params }),
  getRepositoryHealth: () => api.get('/api/repositories/health'),
  getActionRunnerConnections: () => api.get('/api/action-runner-connections'),
  createActionRunnerConnection: (data) => api.post('/api/action-runner-connections', data),
  provisionRunnerVm: (connectionId, body = null) => api.post(`/api/action-runner-connections/${connectionId}/provision`, body),
  deprovisionRunnerVm: (connectionId) => api.post(`/api/action-runner-connections/${connectionId}/deprovision`),
  
  // Repository health actions
  checkRepositoryHealth: (id) => api.post(`/api/repositories/${id}/check-health`),
  checkRepositoryConfig: (id) => api.post(`/api/repositories/${id}/check-config`),
  
  // Repository best practices
  getRepositoryBestPractices: (repoId, forceRefresh = false) => 
    api.get(`/api/repositories/${repoId}/best-practices?force_refresh=${forceRefresh}`),
  updateRepositoryBestPractices: (repoId, content) => 
    api.put(`/api/repositories/${repoId}/best-practices`, { content }),
  checkBestPracticesPrStatus: (repoId) => 
    api.post(`/api/repositories/${repoId}/best-practices/check-pr-status`),

  // Repository PR-Agent config
  getRepositoryPrAgentConfig: (repoId, forceRefresh = false) => 
    api.get(`/api/repositories/${repoId}/pr-agent-config?force_refresh=${forceRefresh}`),
  updateRepositoryPrAgentConfig: (repoId, content) => 
    api.put(`/api/repositories/${repoId}/pr-agent-config`, { content }),
  checkPrAgentConfigPrStatus: (repoId) => 
    api.post(`/api/repositories/${repoId}/pr-agent-config/check-pr-status`),

  // GitHub Action config
  getRepositoryGithubActionConfig: (repoId, forceRefresh = false) => 
    api.get(`/api/repositories/${repoId}/github-action-config?force_refresh=${forceRefresh}`),
  updateRepositoryGithubActionConfig: (repoId, envVars) => 
    api.put(`/api/repositories/${repoId}/github-action-config`, { env_vars: envVars }),
  checkGithubActionConfigPrStatus: (repoId) => 
    api.post(`/api/repositories/${repoId}/github-action-config/check-pr-status`),

  // Runner service management
  checkRunnerService: (repoId, serviceName) => 
    api.post(`/api/repositories/${repoId}/runner-service/check`, { service_name: serviceName }),
  saveRunnerServiceName: (repoId, serviceName) => 
    api.put(`/api/repositories/${repoId}/runner-service/name`, { service_name: serviceName }),
  listRunnerServices: () => 
    api.get('/api/system/runner-services'),

  // Azure agent service management
  checkAzureAgentService: (repoId, data) => 
    api.post(`/api/repositories/${repoId}/azure-agent-service/check`, data),
  saveAzureAgentServiceName: (repoId, data) => 
    api.put(`/api/repositories/${repoId}/azure-agent-service/name`, data),
  listAzureAgentServices: (repoId) => 
    api.get(`/api/repositories/${repoId}/azure-agent-service/list`),

  // Token testing
  testRepositoryToken: (repoId) => 
    api.post(`/api/repositories/${repoId}/test-token`),

  // Developer mode
  getDeveloperMode: () => api.get('/api/developer-mode'),
  
  // Developer tools (only available when developer mode is enabled)
  generateTestData: () => api.post('/api/dev/generate-test-data'),
  simulateActivity: () => api.post('/api/dev/simulate-activity'),
  failActivity: (operationId) => api.post('/api/dev/fail-activity', { operation_id: operationId }),
  succeedActivity: (operationId) => api.post('/api/dev/succeed-activity', { operation_id: operationId }),
  triggerError: () => api.post('/api/dev/trigger-error'),
  clearData: () => api.post('/api/dev/clear-data'),
  refreshJobCounts: () => api.post('/api/dev/refresh-job-counts'),
  
  // Scheduled Jobs Management
  getScheduledJobsStatus: () => api.get('/api/dev/scheduled-jobs/status'),
  triggerScheduledJob: (serviceName) => api.post(`/api/dev/scheduled-jobs/trigger/${serviceName}`, {}, { timeout: 60000 }),
  getStaleJobs: () => api.get('/api/dev/stale-jobs'),
  forceTimeoutCheck: () => api.post('/api/dev/force-timeout-check'),
  
  // Notification management
  getNotificationConfigs: () => api.get('/api/notifications/configs'),
  createNotificationConfig: (data) => api.post('/api/notifications/configs', data),
  updateNotificationConfig: (id, data) => api.put(`/api/notifications/configs/${id}`, data),
  deleteNotificationConfig: (id) => api.delete(`/api/notifications/configs/${id}`),
  testNotificationConfig: (id, testData = {}) => api.post(`/api/notifications/test/${id}`, testData),
  getNotificationEvents: (params = {}) => api.get('/api/notifications/events', { params }),
  
  // Admin management
  getRetentionConfig: () => api.get('/api/admin/retention/config'),
  updateRetentionConfig: (data) => api.post('/api/admin/retention/config', data),
  getDatabaseStats: () => api.get('/api/admin/database/stats'),
  performCleanup: (dryRun = true) => api.post(`/api/admin/database/cleanup?dry_run=${dryRun}`, {}, { 
    timeout: 180000 // 3 minutes timeout for cleanup operations
  }),
  createBackup: (compressed = true) => api.post(`/api/admin/database/backup?compressed=${compressed}`, {}, { 
    timeout: 120000 // 2 minutes timeout for backup creation
  }),
  getBackupList: () => api.get('/api/admin/database/backups'),
  getBackupDirectory: () => api.get('/api/admin/backup/directory'),
  setBackupDirectory: (directory) => api.post('/api/admin/backup/directory', { backup_directory: directory }),
  deleteBackup: (filename) => api.delete(`/api/admin/database/backups/${encodeURIComponent(filename)}`),
  deleteAllBackups: () => api.delete('/api/admin/database/backups'),
  restoreBackup: (filename) => api.post(`/api/admin/database/backups/${encodeURIComponent(filename)}/restore`, {}, { 
    timeout: 300000 // 5 minutes timeout for restore operations
  }),
  exportData: (format = 'json', tables = null) => {
    return api.post('/api/admin/database/export', { 
      format: format,
      tables: tables 
    }, { 
      responseType: 'blob',
      headers: {
        'Content-Type': 'application/json'
      }
    });
  },

  // Get detailed repository status
  getRepositoryDetailedStatus: (repoId) => {
    return api.get(`/api/repositories/${repoId}/detailed-status`);
  },

  // Get GitHub token permissions guide
  getPermissionsGuide: () => {
    return api.get('/api/repositories/permissions-guide');
  },
};

export default apiService; 