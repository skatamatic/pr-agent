import React, { useState, useEffect, useContext, useRef } from 'react';
import { Activity, Settings, Code, FileText, BarChart3, GitBranch, Bell, Database, TrendingUp, RefreshCw, Trash2 } from 'lucide-react';
import StatusOverview from './components/StatusOverview';
import JobsList from './components/JobsList';
import LogsViewer from './components/LogsViewer';
import ConfigEditor from './components/ConfigEditor';
import DeveloperView from './components/DeveloperView';
import RepositoryManager from './components/RepositoryManager';
import Notifications from './components/Notifications';
import AdminPanel from './components/AdminPanel';
import MetricsView from './components/MetricsView';
import DataCleanup from './components/DataCleanup';
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
  
  // Navigation badge counts for new data
  const [newLogsCount, setNewLogsCount] = useState(0);
  const [newJobsCount, setNewJobsCount] = useState(0);
  const fetchDataRef = useRef(null);
  const navigateToJobWithHighlightRef = useRef(null);
  const navigateToOperationWithHighlightRef = useRef(null);

  const { handleSystemError, handleSystemRestore, clearErrorState } = useContext(ToastContext);

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

    const handleWebSocketReconnected = () => {
      // Refetch data after reconnection so UI is not stale
      fetchDataRef.current?.(false);
    };

    const handleLogUpdate = (logData) => {
      // Add logs directly to the logs array for immediate display
      setLogs(prevLogs => [logData, ...prevLogs]);
      
      // Increment new logs badge count only if not currently on logs view
      setActiveTab(currentTab => {
        if (currentTab !== 'logs') {
          setNewLogsCount(prev => prev + 1);
        }
        return currentTab; // Don't change the tab, just use it for the check
      });
    };

    const handleOperationUpdate = (operationData) => {
      // Notify JobsList about operation update for live refresh
      window.dispatchEvent(new CustomEvent('operationUpdate', { detail: operationData }));
      
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
      // Notify JobsList about job update for live refresh
      window.dispatchEvent(new CustomEvent('jobUpdate', { detail: jobData }));
      
      // Increment new jobs badge count only if not currently on jobs view
      setActiveTab(currentTab => {
        if (currentTab !== 'jobs') {
          setNewJobsCount(prev => prev + 1);
        }
        return currentTab; // Don't change the tab, just use it for the check
      });
      
      // Jobs list refreshes via explicit fetches and jobUpdate events.
    };

    const handleMetricsUpdate = (metricsData) => {
      // Notify MetricsView about metrics update for live refresh
      window.dispatchEvent(new CustomEvent('metricsUpdate', { detail: metricsData }));
    };

    // Set up event listeners - remove any existing listeners first to prevent duplicates
    webSocketService.off('connected', handleWebSocketConnected);
    webSocketService.off('disconnected', handleWebSocketDisconnected);
    webSocketService.off('error', handleWebSocketError);
    webSocketService.off('log', handleLogUpdate);
    webSocketService.off('operation_update', handleOperationUpdate);
    webSocketService.off('job_update', handleJobUpdate);
    webSocketService.off('metrics_update', handleMetricsUpdate);
    
    // Now add the listeners
    webSocketService.on('connected', handleWebSocketConnected);
    webSocketService.on('disconnected', handleWebSocketDisconnected);
    webSocketService.on('error', handleWebSocketError);
    webSocketService.on('reconnected', handleWebSocketReconnected);
    webSocketService.on('log', handleLogUpdate);
    webSocketService.on('operation_update', handleOperationUpdate);
    webSocketService.on('job_update', handleJobUpdate);
    webSocketService.on('metrics_update', handleMetricsUpdate);

    // Connect WebSocket with small delay to handle React Strict Mode
    const connectTimer = setTimeout(() => {
      connectWebSocket();
    }, 100);

    // Listen for browser back/forward navigation
    const handlePopState = (event) => {
      const urlParams = new URLSearchParams(window.location.search);
      const view = urlParams.get('view') || 'overview';
      setActiveTab(view);
    };

    window.addEventListener('popstate', handlePopState);

    // Cleanup on unmount
    return () => {
      clearTimeout(connectTimer);
      webSocketService.off('connected', handleWebSocketConnected);
      webSocketService.off('disconnected', handleWebSocketDisconnected);
      webSocketService.off('error', handleWebSocketError);
      webSocketService.off('reconnected', handleWebSocketReconnected);
      webSocketService.off('log', handleLogUpdate);
      webSocketService.off('operation_update', handleOperationUpdate);
      webSocketService.off('job_update', handleJobUpdate);
      webSocketService.off('metrics_update', handleMetricsUpdate);
      webSocketService.disconnect();
      window.removeEventListener('popstate', handlePopState);
    };
  }, []); // Keep empty dependency array - handlers use functional updates to avoid stale closures

  // Smart data fetching with error handling
  const fetchData = async (showLoadingState = false) => {
    if (showLoadingState) {
      setLoading(true);
    }

    try {
      let operationsRes, logsRes;
      
      try {
        operationsRes = await apiService.getOperations({ limit: 100 });
      } catch (error) {
        console.error('Operations API Error:', error);
        handleSystemError(error, 'operations');
        operationsRes = { data: { data: { operations: [], total: 0 } } };
      }
      
      try {
        logsRes = await apiService.getLogs({ limit: 10000 });
      } catch (error) {
        console.error('Logs API Error:', error);
        handleSystemError(error, 'logs');
        logsRes = { data: { data: { logs: [], total: 0 } } };
      }

      // Check if we got valid data (axios wraps response in .data)
      const newOperations = operationsRes.data?.data?.operations || [];
      const newLogs = logsRes.data?.data?.logs || [];



      // Update connection state based on successful responses
      const newConnectionState = {
        api: 'connected',
        database: operationsRes.data?.data ? 'connected' : 'error',
        contextService: connectionState.contextService // Preserve context service state - don't reset it
      };

      // Always update the state with fresh data
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
    fetchDataRef.current?.(true);
    
    // Handle URL parameters on initial load
    const urlParams = new URLSearchParams(window.location.search);
    const jobId = urlParams.get('job');
    const operationId = urlParams.get('operation');
    
    if (jobId) {
      // Delay to ensure data is loaded first
      setTimeout(() => {
        if (operationId) {
          navigateToOperationWithHighlightRef.current?.(jobId, operationId);
        } else {
          navigateToJobWithHighlightRef.current?.(jobId);
        }
      }, 1000);
    }
  }, []);

  // Periodic data refresh (every 30 seconds as backup to WebSocket)
  useEffect(() => {
    const interval = setInterval(() => {
      // Only poll if WebSocket is not connected
      if (connectionState.websocket !== 'connected') {
        fetchDataRef.current?.(false);
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [connectionState.websocket]); // Re-establish interval when connection state changes

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
  }, [connectionState.api, handleSystemError, handleSystemRestore]); // Removed contextService dependency to prevent re-runs

  const mainTabs = [
    { id: 'overview', name: 'Overview', icon: Activity },
    { id: 'metrics', name: 'Metrics', icon: TrendingUp },
    { id: 'jobs', name: 'Jobs', icon: BarChart3 },
    { id: 'logs', name: 'Logs', icon: FileText },
    { id: 'repositories', name: 'Repositories', icon: GitBranch },
    { id: 'notifications', name: 'Notifications', icon: Bell },
    { id: 'config', name: 'AI Config', icon: Settings },
    { id: 'admin', name: 'Retention', icon: Database },
    { id: 'cleanup', name: 'Data Cleanup', icon: Trash2 }
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
    
    // Force the Jobs tab to show "ALL JOBS" first so the highlighted job is visible
    setTimeout(() => {
      const event = new CustomEvent('filterJobsByStatus', { 
        detail: { status: 'all' } 
      });
      window.dispatchEvent(event);
    }, 100);
    
    // Set highlight and clear it after 4 seconds
    setHighlightedJobId(jobId);
    setHighlightedOperationId(null);
    setTimeout(() => {
      setHighlightedJobId(null);
    }, 4000);
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
    
    // Force the Jobs tab to show "ALL JOBS" first so the highlighted job/operation is visible
    setTimeout(() => {
      const event = new CustomEvent('filterJobsByStatus', { 
        detail: { status: 'all' } 
      });
      window.dispatchEvent(event);
    }, 100);
    
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

  fetchDataRef.current = fetchData;
  navigateToJobWithHighlightRef.current = navigateToJobWithHighlight;
  navigateToOperationWithHighlightRef.current = navigateToOperationWithHighlight;

  const clearLogFilter = () => {
    setLogFilterId(null);
    setLogFilterType(null);
  };

  const handleTabChange = (tabId) => {
    // Clear highlighted states when changing tabs
    setHighlightedJobId(null);
    setHighlightedOperationId(null);
    
    // Clear badge counts when navigating to respective views
    if (tabId === 'logs') {
      setNewLogsCount(0);
    }
    if (tabId === 'jobs') {
      setNewJobsCount(0);
    }
    
    setActiveTab(tabId);
    
    // Update URL without page reload
    const url = new URL(window.location);
    url.searchParams.set('view', tabId);
    
    // Clear job and operation parameters when navigating away from jobs view
    if (tabId !== 'jobs') {
      url.searchParams.delete('job');
      url.searchParams.delete('operation');
    }
    
    window.history.pushState({ view: tabId }, '', url);
  };

  const renderTabContent = () => {
    // Simple fade animation for all transitions
    let transitionClass = 'view-fade-enter';

    const content = (() => {
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
        case 'cleanup':
          return <DataCleanup />;
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
    })();

    return (
      <div key={activeTab} className={transitionClass}>
        {content}
      </div>
    );
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
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900 flex">
      {/* Left Sidebar - Fixed and Floating */}
      <div className="fixed left-0 top-0 bottom-0 w-64 bg-gray-100 dark:bg-gray-900 border-r border-gray-200 dark:border-gray-700 shadow-lg flex flex-col z-10 overflow-visible">
        {/* Sidebar Header */}
        <div className="px-6 py-6 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <div className="flex items-center space-x-3">
            {/* Logo/Icon */}
            <div className="relative">
              <div className="p-3 bg-gradient-to-br from-blue-500 to-blue-600 dark:from-blue-600 dark:to-blue-700 rounded-xl shadow-lg">
                <Activity className="h-7 w-7 text-white" />
              </div>
              <div className="absolute -top-1 -right-1 w-3 h-3 bg-green-500 rounded-full border-2 border-white dark:border-gray-800 animate-pulse"></div>
            </div>
            
            {/* Title */}
            <div>
              <h1 className="text-xl font-bold text-gray-900 dark:text-white">
                PR-Agent
              </h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Dashboard
              </p>
            </div>
          </div>
        </div>

        {/* Navigation - Scrollable middle section */}
        <nav className="flex-1 overflow-y-auto overflow-x-visible px-4 py-6 flex flex-col relative">
          <div className="space-y-1">
            {mainTabs.map((tab) => {
              const Icon = tab.icon;
              
              // Check if this tab has new activity to show notification badge
              const hasNewActivity = () => {
                if (tab.id === 'logs' && newLogsCount > 0 && activeTab !== 'logs') {
                  return true;
                }
                if (tab.id === 'jobs' && newJobsCount > 0 && activeTab !== 'jobs') {
                  return true;
                }
                return false;
              };
              
              const showNotificationBadge = hasNewActivity();
              
              return (
                <button
                  key={tab.id}
                  onClick={() => handleTabChange(tab.id)}
                  className={`w-full flex items-center justify-between px-3 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 group ${
                    activeTab === tab.id
                      ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 shadow-sm'
                      : 'text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-200 hover:bg-white dark:hover:bg-gray-800 hover:shadow-sm'
                  }`}
                >
                  <div className="flex items-center">
                    <Icon className={`h-5 w-5 mr-3 transition-transform duration-200 ${
                      activeTab === tab.id ? 'scale-110' : 'group-hover:scale-105'
                    }`} />
                    {tab.name}
                  </div>
                  
                  {/* Simple notification badge */}
                  {showNotificationBadge && (
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
                  )}
                </button>
              );
            })}
          </div>

          {/* Spacer to push developer and settings to bottom */}
          <div className="flex-1"></div>

          <div className="space-y-1">
            {/* Developer Tab (if enabled) - moved to bottom */}
            {developerTab && (
              <button
                onClick={() => handleTabChange(developerTab.id)}
                className={`w-full flex items-center px-3 py-2.5 text-sm font-medium rounded-lg transition-all duration-200 group ${
                  activeTab === developerTab.id
                    ? 'bg-emerald-50 dark:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 shadow-sm'
                    : 'text-emerald-600 hover:text-emerald-700 dark:text-emerald-400 dark:hover:text-emerald-300 hover:bg-white dark:hover:bg-gray-800 hover:shadow-sm'
                }`}
              >
                <developerTab.icon className={`h-5 w-5 mr-3 transition-transform duration-200 ${
                  activeTab === developerTab.id ? 'scale-110' : 'group-hover:scale-105'
                }`} />
                {developerTab.name}
              </button>
            )}

            {/* Settings - moved to bottom */}
            <SettingsDropdown />
          </div>
        </nav>

        {/* Sidebar Footer - Always visible at bottom */}
        <div className="p-4 border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
          <div className="flex items-center space-x-2 text-xs mb-2">
            <div className={`w-2 h-2 rounded-full ${
              connectionState.api === 'connected' 
                ? 'bg-green-500 animate-pulse' 
                : 'bg-red-500'
            }`}></div>
            <span className={`font-medium ${
              connectionState.api === 'connected' 
                ? 'text-green-600 dark:text-green-400' 
                : 'text-red-600 dark:text-red-400'
            }`}>
              {connectionState.api === 'connected' ? 'Connected' : 'Disconnected'}
            </span>
          </div>
          {lastFetchTime && (
            <div className="text-xs text-gray-500 dark:text-gray-400 flex items-center space-x-1">
              <RefreshCw className="h-3 w-3" />
              <span>Updated: {lastFetchTime.toLocaleTimeString()}</span>
            </div>
          )}
        </div>
      </div>

      {/* Main Content Area - With left margin for sidebar */}
      <div className="flex-1 ml-64 flex flex-col min-h-screen">
        {/* Main Content - Full height without header */}
        <main className="flex-1 p-6 bg-gray-100 dark:bg-gray-900">
          <div className="max-w-6xl mx-auto">
            {renderTabContent()}
          </div>
        </main>
      </div>
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