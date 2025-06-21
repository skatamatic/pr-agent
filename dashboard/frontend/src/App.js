import React, { useState, useEffect, useContext } from 'react';
import { Activity, AlertCircle, CheckCircle, GitPullRequest, Settings, Code, FileText, BarChart3, GitBranch } from 'lucide-react';
import StatusOverview from './components/StatusOverview';
import OperationsList from './components/OperationsList';
import LogsViewer from './components/LogsViewer';
import ConfigEditor from './components/ConfigEditor';
import DeveloperView from './components/DeveloperView';
import RepositoryManager from './components/RepositoryManager';
import SettingsDropdown from './components/SettingsDropdown';
import { ThemeProvider } from './contexts/ThemeContext';
import { ToastProvider, ToastContext } from './contexts/ToastContext';
import apiService from './services/api';

function AppContent() {
  const [activeTab, setActiveTab] = useState('overview');
  const [operations, setOperations] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [developerMode, setDeveloperMode] = useState(false);
  const [lastFetchTime, setLastFetchTime] = useState(null);
  const [connectionState, setConnectionState] = useState({
    api: 'connected',
    database: 'connected',
    contextService: 'connected'
  });

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
        logsRes = await apiService.getLogs({ limit: 1000 });
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
        contextService: 'connected' // Will be updated by health checks
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

  // Initial data fetch
  useEffect(() => {
    fetchData(true);
  }, []);

  // Periodic data refresh (every 5 seconds)
  useEffect(() => {
    const interval = setInterval(() => {
      fetchData(false);
    }, 5000);

    return () => clearInterval(interval);
  }, [connectionState]); // Re-establish interval when connection state changes

  // Health check monitoring
  useEffect(() => {
    const healthCheck = async () => {
      try {
        const health = await apiService.getSystemHealth();
        
        // Update context service status
        const contextServiceStatus = health.services?.context_service?.status || 'unknown';
        setConnectionState(prev => ({
          ...prev,
          contextService: contextServiceStatus === 'healthy' ? 'connected' : 
                         contextServiceStatus === 'disabled' ? 'disabled' : 'error'
        }));

        // Handle context service state changes
        if (connectionState.contextService === 'error' && contextServiceStatus === 'healthy') {
          handleSystemRestore('Context Service');
        } else if (connectionState.contextService === 'connected' && contextServiceStatus !== 'healthy') {
          handleSystemError(new Error('Service unavailable'), 'Context Service');
        }

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
  }, [connectionState.contextService, connectionState.api]);

  const tabs = [
    { id: 'overview', name: 'Overview', icon: Activity },
    { id: 'operations', name: 'Operations', icon: BarChart3 },
    { id: 'logs', name: 'Logs', icon: FileText },
    { id: 'repositories', name: 'Repositories', icon: GitBranch },
    { id: 'config', name: 'Configuration', icon: Settings },
    ...(developerMode ? [{ id: 'developer', name: 'Developer', icon: Code }] : [])
  ];

  const refreshData = () => {
    fetchData(false);
  };

  const navigateToConfig = (sectionId) => {
    setActiveTab('config');
    // Wait for the config tab to render, then scroll to the section
    setTimeout(() => {
      const element = document.getElementById(sectionId);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
        // Optionally expand the section if it's collapsed
        const sectionHeader = element.querySelector('button');
        if (sectionHeader) {
          sectionHeader.click();
        }
      }
    }, 100);
  };

  const navigateToLogs = (operationId) => {
    setActiveTab('logs');
    // Store the operation ID for filtering in logs view
    // We'll pass this to LogsViewer via a ref or context
    setTimeout(() => {
      // Trigger filtering in logs view
      const event = new CustomEvent('filterLogsByOperation', { 
        detail: { operationId } 
      });
      window.dispatchEvent(event);
    }, 100);
  };

  const renderTabContent = () => {
    switch (activeTab) {
      case 'overview':
        return <StatusOverview operations={operations} onNavigateToConfig={navigateToConfig} />;
      case 'operations':
        return <OperationsList operations={operations} onRefresh={refreshData} onShowLogs={navigateToLogs} />;
      case 'logs':
        return <LogsViewer logs={logs} onRefresh={refreshData} />;
      case 'repositories':
        return <RepositoryManager />;
      case 'config':
        return <ConfigEditor />;
      case 'developer':
        return developerMode ? <DeveloperView onRefresh={refreshData} /> : null;
      default:
        return <StatusOverview operations={operations} onNavigateToConfig={navigateToConfig} />;
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
          <div className="flex space-x-8">
            {tabs.map((tab) => {
              const Icon = tab.icon;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
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
        <AppContent />
      </ToastProvider>
    </ThemeProvider>
  );
}

export default App; 