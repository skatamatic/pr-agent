import React, { useState, useEffect, useContext } from 'react';
import { Activity, AlertCircle, CheckCircle, GitPullRequest, Settings, Code, FileText, BarChart3, GitBranch, Bell, Shield, Database, TrendingUp, RefreshCw } from 'lucide-react';
import StatusOverview from './components/StatusOverview';
import JobsList from './components/JobsList';
import LogsViewer from './components/LogsViewer';
import ConfigEditor from './components/ConfigEditor';
import DeveloperView from './components/DeveloperView';
import RepositoryManager from './components/RepositoryManager';
import Notifications from './components/Notifications';
import AdminPanel from './components/AdminPanel';
import MetricsView from './components/MetricsView';
import SettingsDropdown from './components/SettingsDropdown';
import Login from './components/Login';
import { ThemeProvider } from './contexts/ThemeContext';
import { ToastProvider, ToastContext } from './contexts/ToastContext';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import apiService from './services/api';
import webSocketService from './services/websocket';

function AppContent() {
  const { isAuthenticated, loading: authLoading } = useAuth();

  if (authLoading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="flex items-center space-x-3">
          <RefreshCw className="h-6 w-6 animate-spin text-blue-600 dark:text-blue-400" />
          <span className="text-gray-600 dark:text-gray-400">Loading...</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Login />;
  }

  return <Dashboard />;
}

function Dashboard() {
  const [activeTab, setActiveTab] = useState(() => {
    // Get tab from URL on initial load
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get('view') || 'overview';
  });
  const [jobs, setJobs] = useState([]);
  const [operations, setOperations] = useState([]); // Keep for legacy compatibility
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [developerMode, setDeveloperMode] = useState(false);
  const [lastFetchTime, setLastFetchTime] = useState(null);
  const [manualRefreshTrigger, setManualRefreshTrigger] = useState(null);
  const [logFilterId, setLogFilterId] = useState(null);
  const [logFilterType, setLogFilterType] = useState(null);
  const [highlightedJobId, setHighlightedJobId] = useState(null);
  const [highlightedOperationId, setHighlightedOperationId] = useState(null);
  const [connectionState, setConnectionState] = useState({
    api: 'connected',
    database: 'connected',
    contextService: 'unknown',
    websocket: 'disconnected'
  });
  const [configNavigationTarget, setConfigNavigationTarget] = useState(null);

  const { handleApiError, handleApiSuccess, handleSystemError, handleSystemRestore, clearErrorState } = useContext(ToastContext);

  // Check developer mode on startup
  useEffect(() => {
    const checkDeveloperMode = async () => {
      try {
        const response = await apiService.getDeveloperMode();
        const enabled = response.data?.enabled ?? response.enabled ?? false;
        setDeveloperMode(enabled);
      } catch (error) {

        setDeveloperMode(false);
      }
    };
    
    checkDeveloperMode();
  }, []);

  // WebSocket connection and real-time updates
  useEffect(() => {
    const connectWebSocket = async () => {
      try {
        await webSocketService.connect();
        setConnectionState(prev => ({ ...prev, websocket: 'connected' }));
      } catch (error) {
        console.error('Failed to connect WebSocket:', error);
        setConnectionState(prev => ({ ...prev, websocket: 'error' }));
      }
    };

    // WebSocket event handlers
    const handleWebSocketConnected = () => {
      setConnectionState(prev => ({ ...prev, websocket: 'connected' }));
    };

    const handleWebSocketDisconnected = () => {
      setConnectionState(prev => ({ ...prev, websocket: 'disconnected' }));
    };

    const handleWebSocketError = (error) => {
      setConnectionState(prev => ({ ...prev, websocket: 'error' }));
    };

    const handleLogUpdate = (logData) => {
      setLogs(prevLogs => {
        // Add new log to the beginning of the array
        const newLogs = [logData, ...prevLogs];
        // Keep only the latest 1000 logs to prevent memory issues
        return newLogs.slice(0, 1000);
      });
    };

    const handleOperationUpdate = (operationData) => {
      setOperations(prevOperations => {
        const existingIndex = prevOperations.findIndex(op => op.id === operationData.id);
        if (existingIndex >= 0) {
          // Update existing operation
          const newOperations = [...prevOperations];
          newOperations[existingIndex] = { ...newOperations[existingIndex], ...operationData };
          return newOperations;
        } else {
          // Add new operation
          return [operationData, ...prevOperations];
        }
      });
    };

    const handleJobUpdate = (jobData) => {
      setJobs(prevJobs => {
        const existingIndex = prevJobs.findIndex(job => job.id === jobData.id);
        if (existingIndex >= 0) {
          // Update existing job
          const newJobs = [...prevJobs];
          newJobs[existingIndex] = { ...newJobs[existingIndex], ...jobData };
          return newJobs;
        } else {
          // Add new job
          return [jobData, ...prevJobs];
        }
      });
    };

    // Set up event listeners
    webSocketService.on('connected', handleWebSocketConnected);
    webSocketService.on('disconnected', handleWebSocketDisconnected);
    webSocketService.on('error', handleWebSocketError);
    webSocketService.on('log', handleLogUpdate);
    webSocketService.on('operation_update', handleOperationUpdate);
    webSocketService.on('job_update', handleJobUpdate);

    // Connect WebSocket
    connectWebSocket();

    // Listen for browser back/forward navigation
    const handlePopState = (event) => {
      const urlParams = new URLSearchParams(window.location.search);
      const view = urlParams.get('view') || 'overview';
      setActiveTab(view);
    };

    window.addEventListener('popstate', handlePopState);

    // Cleanup on unmount
    return () => {
      webSocketService.off('connected', handleWebSocketConnected);
      webSocketService.off('disconnected', handleWebSocketDisconnected);
      webSocketService.off('error', handleWebSocketError);
      webSocketService.off('log', handleLogUpdate);
      webSocketService.off('operation_update', handleOperationUpdate);
      webSocketService.off('job_update', handleJobUpdate);
      webSocketService.disconnect();
      window.removeEventListener('popstate', handlePopState);
    };
  }, []);

  // Smart data fetching with error handling
  const fetchData = async (showLoadingState = false) => {
    if (showLoadingState) {
      setLoading(true);
    }

    try {
      let jobsRes, operationsRes, logsRes;
      
      try {
        jobsRes = await apiService.getJobs({ limit: 100, include_operations: true });
      } catch (error) {
        console.error('Jobs API Error:', error);
        handleSystemError(error, 'jobs');
        jobsRes = { data: { data: [] } };
      }
      
      try {
        operationsRes = await apiService.getOperations({ limit: 100 });
      } catch (error) {
        console.error('Operations API Error:', error);
        handleSystemError(error, 'operations');
        operationsRes = { data: { data: { operations: [], total: 0 } } };
      }
      
      try {
        logsRes = await apiService.getLogs({ limit: 1000 });
      } catch (error) {
        console.error('Logs API Error:', error);
        handleSystemError(error, 'logs');
        logsRes = { data: { data: { logs: [], total: 0 } } };
      }

      // Check if we got valid data (axios wraps response in .data)
      const newJobs = jobsRes.data?.data || [];
      const newOperations = operationsRes.data?.data?.operations || [];
      const newLogs = logsRes.data?.data?.logs || [];



      // Update connection state based on successful responses
      const newConnectionState = {
        api: 'connected',
        database: operationsRes.data?.data ? 'connected' : 'error',
        contextService: connectionState.contextService // Preserve context service state - don't reset it
      };

      // Always update the state with fresh data
      setJobs(newJobs);
      setOperations(newOperations);
      setLogs(newLogs);

      // Handle connection restoration
      if (connectionState.api === 'error') {
        handleSystemRestore('API');
      }
      if (connectionState.database === 'error' && newConnectionState.database === 'connected') {
        handleSystemRestore('Database');
      }

      setConnectionState(newConnectionState);
      setLastFetchTime(new Date());

      // Clear any lingering error states on successful fetch
      clearErrorState('api_operations');
      clearErrorState('api_logs');
      clearErrorState('system_api');
      clearErrorState('system_database');

    } catch (error) {
      
      // Only show error on rising edge (first failure)
      if (connectionState.api === 'connected') {
        handleSystemError(error, 'API');
      }
      
      setConnectionState(prev => ({
        ...prev,
        api: 'error',
        database: 'error'
      }));
    } finally {
      if (showLoadingState) {
        setLoading(false);
      }
    }
  };

  // Initial data fetch and URL parameter handling
  useEffect(() => {
    fetchData(true);
    
    // Handle URL parameters on initial load
    const urlParams = new URLSearchParams(window.location.search);
    const jobId = urlParams.get('job');
    const operationId = urlParams.get('operation');
    
    if (jobId) {
      // Delay to ensure data is loaded first
      setTimeout(() => {
        if (operationId) {
          navigateToOperationWithHighlight(jobId, operationId);
        } else {
          navigateToJobWithHighlight(jobId);
        }
      }, 1000);
    }
  }, []);

  // Periodic data refresh (every 30 seconds as backup to WebSocket)
  useEffect(() => {
    const interval = setInterval(() => {
      // Only poll if WebSocket is not connected
      if (connectionState.websocket !== 'connected') {
        fetchData(false);
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [connectionState]); // Re-establish interval when connection state changes

  // Health check monitoring
  useEffect(() => {
    const healthCheck = async () => {
      try {
        const health = await apiService.getSystemHealth();
        
        // Update context service status
        const contextServiceStatus = health.services?.context_service?.status || 'unknown';
        const newContextServiceState = contextServiceStatus === 'healthy' ? 'connected' : 
                                     contextServiceStatus === 'disabled' ? 'disabled' : 'error';
        
        setConnectionState(prev => {
          const previousContextState = prev.contextService;
          
          // Handle context service state changes with explicit logic
          if (previousContextState === 'error' && newContextServiceState === 'connected') {
            handleSystemRestore('Context Service');
          } else if (previousContextState === 'connected' && newContextServiceState === 'error') {
            // Only show error if service went from connected to error (not disabled)
            handleSystemError(new Error('Service unavailable'), 'Context Service');
          }
          // NEVER show errors for disabled services or transitions to disabled
          
          return {
            ...prev,
            contextService: newContextServiceState
          };
        });

      } catch (error) {
        // Health check failure - only report if connection was previously good
        if (connectionState.api === 'connected') {
          handleSystemError(error, 'Health Check');
        }
      }
    };

    // Run health check every 30 seconds
    const healthInterval = setInterval(healthCheck, 30000);
    healthCheck(); // Run immediately

    return () => clearInterval(healthInterval);
  }, [connectionState.api]); // Removed contextService dependency to prevent re-runs

  const mainTabs = [
    { id: 'overview', name: 'Overview', icon: Activity },
    { id: 'metrics', name: 'Metrics', icon: TrendingUp },
    { id: 'jobs', name: 'Jobs', icon: BarChart3 },
    { id: 'logs', name: 'Logs', icon: FileText },
    { id: 'repositories', name: 'Repositories', icon: GitBranch },
    { id: 'notifications', name: 'Notifications', icon: Bell },
    { id: 'config', name: 'AI Config', icon: Settings },
    { id: 'admin', name: 'Retention', icon: Database }
  ];

  const developerTab = developerMode ? { id: 'developer', name: 'Developer', icon: Code } : null;

  const refreshData = () => {
    fetchData(false);
    setManualRefreshTrigger(new Date());
  };

  const navigateToConfig = (target) => {
    // Special handling for repositories
    if (target === 'repositories') {
      handleTabChange('repositories');
      return;
    }
    
    handleTabChange('config');
    
    // Enhanced navigation for context service enable
    if (target === 'context-service-section') {
      setConfigNavigationTarget('context-service-enable');
      // Clear the navigation target after a delay to allow re-triggering
      setTimeout(() => {
        setConfigNavigationTarget(null);
      }, 3000);
    } else {
      // Legacy navigation for other sections
      setTimeout(() => {
        const element = document.getElementById(target);
        if (element) {
          element.scrollIntoView({ behavior: 'smooth', block: 'start' });
          // Optionally expand the section if it's collapsed
          const sectionHeader = element.querySelector('button');
          if (sectionHeader) {
            sectionHeader.click();
          }
        }
      }, 100);
    }
  };

  const navigateToLogs = (filterId, filterType = 'operation') => {
    handleTabChange('logs');
    // Set the filter for the logs view
    setLogFilterId(filterId);
    setLogFilterType(filterType);
    
    // Legacy support - trigger event for old components
    if (filterType === 'operation') {
      setTimeout(() => {
        const event = new CustomEvent('filterLogsByOperation', { 
          detail: { operationId: filterId } 
        });
        window.dispatchEvent(event);
      }, 100);
    }
  };

  const navigateToJob = (jobId) => {
    handleTabChange('jobs');
    // Clear any existing log filters
    setLogFilterId(null);
    setLogFilterType(null);
    
    // TODO: In the future, we could add job selection/highlighting in the jobs view
    // For now, just navigate to the jobs tab where the user can find the job
  };

  const navigateToJobWithHighlight = (jobId) => {
    handleTabChange('jobs');
    setLogFilterId(null);
    setLogFilterType(null);
    
    // Update URL with job parameter
    const url = new URL(window.location);
    url.searchParams.set('view', 'jobs');
    url.searchParams.set('job', jobId);
    url.searchParams.delete('operation'); // Remove operation if present
    window.history.pushState({ view: 'jobs', job: jobId }, '', url);
    
    // Set highlight and clear it after 3 seconds
    setHighlightedJobId(jobId);
    setHighlightedOperationId(null);
    setTimeout(() => {
      setHighlightedJobId(null);
    }, 3000);
  };

  const navigateToJobs = (statusFilter = null) => {
    handleTabChange('jobs');
    setLogFilterId(null);
    setLogFilterType(null);
    setHighlightedJobId(null);
    setHighlightedOperationId(null);
    
    // If a status filter is provided, trigger it after the component loads
    if (statusFilter) {
      setTimeout(() => {
        const event = new CustomEvent('filterJobsByStatus', { 
          detail: { status: statusFilter } 
        });
        window.dispatchEvent(event);
      }, 100);
    }
  };

  const navigateToOperationWithHighlight = (jobId, operationId) => {
    handleTabChange('jobs');
    setLogFilterId(null);
    setLogFilterType(null);
    
    // Update URL with job and operation parameters
    const url = new URL(window.location);
    url.searchParams.set('view', 'jobs');
    url.searchParams.set('job', jobId);
    url.searchParams.set('operation', operationId);
    window.history.pushState({ view: 'jobs', job: jobId, operation: operationId }, '', url);
    
    // Clear any existing highlights
    setHighlightedJobId(null);
    setHighlightedOperationId(null);
    
    // After navigation and page change, set ONLY the operation highlight (not the job)
    setTimeout(() => {
      setHighlightedOperationId(operationId);
      
      // Ensure the job is expanded to show the operation (without highlighting the job)
      const event = new CustomEvent('expandJob', { 
        detail: { jobId } 
      });
      window.dispatchEvent(event);
    }, 200);
    
    // Clear operation highlight after animation
    setTimeout(() => {
      setHighlightedOperationId(null);
    }, 4000);
  };

  const clearLogFilter = () => {
    setLogFilterId(null);
    setLogFilterType(null);
  };

  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
    
    // Update URL without page reload
    const url = new URL(window.location);
    url.searchParams.set('view', tabId);
    window.history.pushState({ view: tabId }, '', url);
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return <StatusOverview 
          operations={operations} 
          onNavigateToConfig={navigateToConfig} 
          onNavigateToJob={navigateToJobWithHighlight}
          onNavigateToJobs={navigateToJobs}
        />;
      case 'jobs':
        return <JobsList 
          onShowLogs={navigateToLogs} 
          refreshTrigger={manualRefreshTrigger}
          highlightedJobId={highlightedJobId}
          highlightedOperationId={highlightedOperationId}
        />;
      case 'logs':
        return <LogsViewer 
          logs={logs} 
          onRefresh={refreshData} 
          filterId={logFilterId}
          filterType={logFilterType}
          onNavigateToJob={navigateToJobWithHighlight}
          onNavigateToOperation={navigateToOperationWithHighlight}
          onClearFilter={clearLogFilter}
        />;
      case 'repositories':
        return <RepositoryManager />;
      case 'metrics':
        return <MetricsView />;
      case 'notifications':
        return <Notifications />;
      case 'admin':
        return <AdminPanel />;
      case 'config':
        return <ConfigEditor navigationTarget={configNavigationTarget} />;
      case 'developer':
        return developerMode ? <DeveloperView onRefresh={refreshData} /> : null;
      default:
        return <StatusOverview 
          operations={operations} 
          onNavigateToConfig={navigateToConfig} 
          onNavigateToJobs={navigateToJobs}
        />;
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex items-center justify-center">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600 mx-auto mb-4"></div>
          <p className="text-gray-600 dark:text-gray-400">Loading dashboard...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header */}
      <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center py-6">
            <div className="flex items-center">
              <Activity className="h-8 w-8 text-blue-600 dark:text-blue-400 mr-3" />
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">PR-Agent Dashboard</h1>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Monitor operations and logs • {connectionState.api === 'connected' ? 'Connected' : 'Disconnected'}
                  {lastFetchTime && (
                    <span className="ml-2">
                      Last updated: {lastFetchTime.toLocaleTimeString()}
                    </span>
                  )}
                </p>
              </div>
            </div>
            <SettingsDropdown />
          </div>
        </div>
      </header>

      {/* Navigation */}
      <nav className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between">
            {/* Main Navigation Tabs */}
            <div className="flex space-x-8">
              {mainTabs.map((tab) => {
                const Icon = tab.icon;
                return (
                  <button
                    key={tab.id}
                    onClick={() => handleTabChange(tab.id)}
                    className={`flex items-center px-1 py-4 border-b-2 font-medium text-sm transition-colors duration-200 ${
                      activeTab === tab.id
                        ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                        : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
                    }`}
                  >
                    <Icon className="h-4 w-4 mr-2" />
                    {tab.name}
                  </button>
                );
              })}
            </div>

            {/* Developer Tab (Right Aligned) */}
            {developerTab && (
              <div className="flex">
                <button
                  onClick={() => handleTabChange(developerTab.id)}
                  className={`flex items-center px-3 py-4 border-b-2 font-medium text-sm transition-colors duration-200 ${
                    activeTab === developerTab.id
                      ? 'border-emerald-500 text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-900/20'
                      : 'border-transparent text-emerald-600 hover:text-emerald-700 hover:border-emerald-300 dark:text-emerald-400 dark:hover:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-900/10'
                  }`}
                >
                  <developerTab.icon className="h-4 w-4 mr-2" />
                  {developerTab.name}
                </button>
              </div>
            )}
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {renderTabContent()}
      </main>
    </div>
  );
}

function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <AuthProvider>
          <AppContent />
        </AuthProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}

export default App; 