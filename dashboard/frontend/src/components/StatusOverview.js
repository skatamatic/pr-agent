import React, { useState, useEffect } from 'react';
import { Activity, CheckCircle, Clock, AlertCircle, Zap, GitPullRequest, TrendingUp, Server, Wifi, Database, ChevronDown, ChevronUp, Settings, GitBranch, Key, Shield, ExternalLink } from 'lucide-react';
import apiService from '../services/api';

const StatusOverview = ({ operations = [], onNavigateToConfig, onNavigateToJob, onNavigateToJobs }) => {
  const [systemHealth, setSystemHealth] = useState(null);
  const [realtimeStatus, setRealtimeStatus] = useState(null);
  const [recentJobs, setRecentJobs] = useState([]);
  const [healthExpanded, setHealthExpanded] = useState(false);
  const [individualServiceHealth, setIndividualServiceHealth] = useState({
    database: { status: 'checking', timestamp: null, isChecking: false, message: 'Initial check...' },
    pr_agent_config: { status: 'checking', timestamp: null, isChecking: false, message: 'Initial check...' },
    context_service: { status: 'checking', timestamp: null, isChecking: false, message: 'Initial check...' },
    repositories: { status: 'checking', timestamp: null, isChecking: false, message: 'Initial check...' }
  });
  const [repositoryDetails, setRepositoryDetails] = useState([]);
  
  useEffect(() => {
    fetchSystemStatus();
    fetchRecentJobs();
    fetchIndividualHealthChecks();
    fetchRepositoryDetails();
    
    const interval = setInterval(() => {
      fetchSystemStatus();
      fetchRecentJobs();
      fetchRepositoryDetails();
    }, 10000); // Update every 10 seconds
    
    const healthInterval = setInterval(() => {
      fetchIndividualHealthChecks();
    }, 15000); // Check individual services every 15 seconds
    
    return () => {
      clearInterval(interval);
      clearInterval(healthInterval);
    };
  }, []);

  const fetchRepositoryDetails = async () => {
    try {
      const response = await apiService.getRepositories();
      setRepositoryDetails(response.data?.data || []);
    } catch (error) {
      console.error('Failed to fetch repository details:', error);
      setRepositoryDetails([]);
    }
  };
  
  const fetchSystemStatus = async () => {
    try {
      const [healthRes, statusRes] = await Promise.all([
        apiService.getSystemHealth().catch(() => ({ data: { status: 'unknown', services: {} } })),
        apiService.getRealtimeStatus().catch(() => ({ data: { operations: {}, services: {} } }))
      ]);
      
      setSystemHealth(healthRes.data);
      setRealtimeStatus(statusRes.data);
      
      // Auto-expand if there are critical issues (errors, not just warnings)
      const hasErrors = Object.values(healthRes.data.services || {}).some(service => 
        service.status && ['unhealthy', 'unreachable', 'misconfigured', 'error'].includes(service.status)
      );
      if (hasErrors) {
        setHealthExpanded(true);
      }
    } catch (error) {
      console.error('Failed to fetch system status:', error);
      setHealthExpanded(true); // Expand on error
    }
  };

  const fetchRecentJobs = async () => {
    try {
      // Fetch a larger sample for better statistics, but only show 5 in recent activity
      const response = await apiService.getJobs({ limit: 50, include_operations: true });
      const allJobs = response.data?.data || [];
      setRecentJobs(allJobs);
    } catch (error) {
      console.error('Failed to fetch recent jobs:', error);
      setRecentJobs([]);
    }
  };

  const fetchIndividualHealthChecks = async () => {
    // Check each service independently without blocking on failures
    const services = ['database', 'pr_agent_config', 'context_service', 'repositories'];
    
    // Set all services to checking state (but preserve their last known status)
    services.forEach(service => {
      setIndividualServiceHealth(prev => ({
        ...prev,
        [service]: {
          ...prev[service],
          isChecking: true
        }
      }));
    });
    
    // Run each health check independently
    services.forEach(async (service) => {
      try {
        let result;
        if (service === 'repositories') {
          // Use the new repositories health API
          result = await apiService.get('/repositories/health');
          result = { data: { health: result.data } }; // Normalize structure
        } else {
          result = await apiService.getHealthCheck(service);
        }
        console.log(`SUCCESS: ${service} health check:`, JSON.stringify(result.data.health, null, 2));
        setIndividualServiceHealth(prev => {
          console.log(`BEFORE UPDATE ${service}:`, JSON.stringify(prev[service], null, 2));
          const newState = {
            ...prev,
            [service]: {
              ...result.data.health,
              timestamp: new Date().toISOString(),
              isChecking: false
            }
          };
          console.log(`AFTER UPDATE ${service}:`, JSON.stringify(newState[service], null, 2));
          return newState;
        });
      } catch (error) {
        console.error(`ERROR: ${service} health check failed:`, error);
        console.error(`ERROR details for ${service}:`, error.response?.data, error.response?.status);
        setIndividualServiceHealth(prev => {
          console.log(`ERROR - BEFORE UPDATE ${service}:`, prev[service]);
          // Always set to error when health check fails - don't preserve old errors
          const newStatus = 'error';
          
          // Auto-expand if this is an error status
          setHealthExpanded(true);
          
          const newState = {
            ...prev,
            [service]: {
              error: `Health check failed: ${error.message}`,
              timestamp: new Date().toISOString(),
              isChecking: false,
              status: newStatus,
              message: `Health check failed: ${error.message}`
            }
          };
          console.log(`ERROR - AFTER UPDATE ${service}:`, newState[service]);
          return newState;
        });
      }
    });
  };

  // Calculate job statistics from recent jobs data
  const totalJobs = recentJobs.length > 0 ? recentJobs.length : (realtimeStatus?.jobs?.total || 0);
  const runningJobs = recentJobs.filter(job => job.status === 'running').length;
  const completedJobs = recentJobs.filter(job => job.status === 'completed').length;
  const failedJobs = recentJobs.filter(job => job.status === 'failed').length;
  
  // Fallback to operation counts if no job data available (for backward compatibility)
  const operationsData = realtimeStatus?.operations || {};
  const totalOperations = operationsData.total || operations.length;
  const activeOperations = operationsData.active || operations.filter(op => op.status === 'processing').length;
  const completedOperations = operationsData.completed || operations.filter(op => op.status === 'completed').length;
  const failedOperations = operationsData.failed || operations.filter(op => op.status === 'failed').length;

  // Use recent jobs for display (limit to 5 most recent)
  const displayJobs = recentJobs.length > 0 ? recentJobs.slice(0, 5) : 
    realtimeStatus?.recent_operations || 
    operations
      .sort((a, b) => new Date(b.started_at || b.timestamp) - new Date(a.started_at || a.timestamp))
      .slice(0, 5);

  const getStatusColor = (status) => {
    switch (status) {
      // Job statuses
      case 'running': return 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/20';
      case 'completed': return 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/20';
      case 'failed': return 'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-900/20';
      case 'cancelled': return 'text-yellow-600 bg-yellow-50 dark:text-yellow-400 dark:bg-yellow-900/20';
      // Operation statuses (fallback)
      case 'processing': return 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/20';
      case 'fetching_context': return 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/20';
      case 'context_completed': return 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/20';
      case 'context_failed': return 'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-900/20';
      default: return 'text-gray-600 bg-gray-50 dark:text-gray-400 dark:bg-gray-800';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      // Job statuses
      case 'running': return Activity;
      case 'completed': return CheckCircle;
      case 'failed': return AlertCircle;
      case 'cancelled': return Clock;
      // Operation statuses (fallback)
      case 'processing': return Activity;
      case 'fetching_context': return Clock;
      case 'context_completed': return CheckCircle;
      case 'context_failed': return AlertCircle;
      default: return Clock;
    }
  };

  const formatStatus = (status) => {
    return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return 'Unknown time';
    const date = new Date(timestamp);
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
    return `${Math.floor(diffMins / 1440)}d ago`;
  };

  // Helper functions for system health
  const getSystemHealthStatus = () => {
    // Combine backend health data with individual service health checks
    const allServices = {
      ...(systemHealth?.services || {}),
      ...individualServiceHealth
    };
    
    // Count different types of issues for more detailed reporting
    const errorServices = Object.values(allServices).filter(service => 
      service.status && ['unhealthy', 'unreachable', 'misconfigured', 'error'].includes(service.status)
    );
    
    const disabledServices = Object.values(allServices).filter(service => 
      service.status === 'disabled'
    );
    
    const checkingServices = Object.values(allServices).filter(service => 
      service.status === 'checking'
    );
    
    const connectedServices = Object.values(allServices).filter(service => 
      service.status && ['healthy', 'connected', 'configured'].includes(service.status)
    );
    
    // Prioritize errors first
    if (errorServices.length > 0) {
      return { 
        status: 'error', 
        color: 'red', 
        message: `${errorServices.length} service${errorServices.length > 1 ? 's' : ''} experiencing issues`,
        textColor: 'text-white'
      };
    } 
    // Then warnings for disabled services (only if no errors)
    else if (disabledServices.length > 0) {
      return { 
        status: 'warning', 
        color: 'yellow', 
        message: `${disabledServices.length} service${disabledServices.length > 1 ? 's are' : ' is'} disabled`,
        textColor: 'text-white'
      };
    } 
    // Then checking status
    else if (checkingServices.length > 0) {
      return { 
        status: 'checking', 
        color: 'blue', 
        message: 'Checking system status...',
        textColor: 'text-white'
      };
    } 
    // Finally healthy status
    else {
      return { 
        status: 'healthy', 
        color: 'green', 
        message: 'All systems operational',
        textColor: 'text-white'
      };
    }
  };

  const getHealthBgColor = (status) => {
    switch (status) {
      case 'healthy': return 'bg-green-600 dark:bg-green-700';
      case 'warning': return 'bg-yellow-600 dark:bg-yellow-700';
      case 'degraded': return 'bg-yellow-600 dark:bg-yellow-700';
      case 'error': return 'bg-red-600 dark:bg-red-700';
      case 'unhealthy': return 'bg-red-600 dark:bg-red-700';
      case 'checking': return 'bg-blue-600 dark:bg-blue-700';
      default: return 'bg-gray-600 dark:bg-gray-700';
    }
  };

  const analyzeTokenIssues = () => {
    const tokenIssues = {
      missingTokens: [],
      invalidTokens: [],
      totalRepos: repositoryDetails.length,
      healthyRepos: 0
    };

    repositoryDetails.forEach(repo => {
      const hasRequiredToken = repo.provider === 'github' ? repo.github_token : repo.azure_pat;
      const hasAuthError = repo.runner_error && (
        repo.runner_error.includes('token') || 
        repo.runner_error.includes('authentication') || 
        repo.runner_error.includes('invalid') || 
        repo.runner_error.includes('expired') ||
        repo.runner_error.includes('permissions') ||
        repo.runner_error.includes('unauthorized')
      );

      if (!hasRequiredToken) {
        tokenIssues.missingTokens.push(repo);
      } else if (hasAuthError) {
        tokenIssues.invalidTokens.push(repo);
      } else {
        tokenIssues.healthyRepos++;
      }
    });

    return tokenIssues;
  };

  const handleNavigateToRepositories = () => {
    // Navigate to repositories view - you may need to pass this as a prop
    if (onNavigateToConfig) {
      onNavigateToConfig('repositories');
    } else {
      // Fallback navigation method
      window.location.hash = '#repositories';
    }
  };

  const renderRepositoryStatus = (serviceName, IconComponent, description) => {
    const repoHealth = individualServiceHealth['repositories'];
    const tokenIssues = analyzeTokenIssues();
    console.log('REPO HEALTH:', JSON.stringify(repoHealth, null, 2));
    console.log('TOKEN ISSUES:', JSON.stringify(tokenIssues, null, 2));
    
    // Default state if no data
    if (!repoHealth || !repoHealth.data) {
      // If we have repository details but no health data, show token-based analysis
      if (repositoryDetails.length > 0) {
        const hasTokenIssues = tokenIssues.missingTokens.length > 0 || tokenIssues.invalidTokens.length > 0;
        
        if (hasTokenIssues) {
          return (
            <div className="bg-red-50 dark:bg-red-900/20 rounded-lg p-4 border border-red-200 dark:border-red-800 hover:shadow-md transition-all duration-200">
              <div className="flex items-center justify-between">
                <div className="flex items-center">
                  <div className="bg-red-100 dark:bg-red-900/30 p-2 rounded-lg mr-3">
                    <Shield className="h-4 w-4 text-red-600 dark:text-red-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">{serviceName}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
                    <div className="text-xs text-red-600 dark:text-red-400 mt-1 space-y-0.5">
                      {tokenIssues.missingTokens.length > 0 && (
                        <p>• {tokenIssues.missingTokens.length} repo(s) missing access tokens</p>
                      )}
                      {tokenIssues.invalidTokens.length > 0 && (
                        <p>• {tokenIssues.invalidTokens.length} repo(s) with invalid tokens</p>
                      )}
                    </div>
                  </div>
                </div>
                <div className="flex items-center space-x-3">
                  <button
                    onClick={handleNavigateToRepositories}
                    className="flex items-center px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-300 bg-red-100 dark:bg-red-900/30 rounded-md hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
                  >
                    <Key className="h-3 w-3 mr-1" />
                    Configure Tokens
                  </button>
                  <div className="flex items-center">
                    <div className="w-2 h-2 bg-red-500 rounded-full mr-2 animate-pulse"></div>
                    <span className="text-sm font-bold text-red-700 dark:text-red-300">Token Issues</span>
                  </div>
                </div>
              </div>
            </div>
          );
        }
      }
      
      return (
        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="bg-gray-100 dark:bg-gray-600 p-2 rounded-lg mr-3">
                <IconComponent className="h-4 w-4 text-gray-500 dark:text-gray-400" />
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">{serviceName}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
              </div>
            </div>
            <div className="flex items-center">
              <div className="w-2 h-2 bg-gray-500 rounded-full mr-2"></div>
              <span className="text-sm font-bold text-gray-500 dark:text-gray-400">Unknown</span>
            </div>
          </div>
        </div>
      );
    }

    const data = repoHealth.data;
    const total = data.total_repos || 0;
    const healthy = data.healthy_repos || 0;
    const unhealthy = data.unhealthy_repos || 0;
    const errorRepos = data.error_repos || [];

    // Enhanced analysis using token issues
    const hasTokenIssues = tokenIssues.missingTokens.length > 0 || tokenIssues.invalidTokens.length > 0;
    
    // Determine status with token awareness
    let status, message, errorDetails, showTokenButton = false;
    if (total === 0) {
      status = 'warning';
      message = 'No repositories configured';
    } else if (hasTokenIssues) {
      status = 'error';
      showTokenButton = true;
      if (tokenIssues.missingTokens.length > 0 && tokenIssues.invalidTokens.length > 0) {
        message = `${tokenIssues.missingTokens.length + tokenIssues.invalidTokens.length}/${total} repos need token configuration`;
        errorDetails = `${tokenIssues.missingTokens.length} missing, ${tokenIssues.invalidTokens.length} invalid tokens`;
      } else if (tokenIssues.missingTokens.length > 0) {
        message = `${tokenIssues.missingTokens.length}/${total} repos missing access tokens`;
        errorDetails = `Configure ${tokenIssues.missingTokens.map(r => r.provider).join(', ')} tokens`;
      } else {
        message = `${tokenIssues.invalidTokens.length}/${total} repos have invalid tokens`;
        errorDetails = 'Check token permissions and expiration';
      }
    } else if (unhealthy === 0) {
      status = 'connected';
      message = `All ${healthy}/${total} repositories healthy`;
    } else {
      status = 'error';
      message = `${healthy}/${total} repositories healthy`;
      const errorNames = errorRepos.slice(0, 3).map(r => r.name).join(', ');
      errorDetails = `Issues with: ${errorNames}${errorRepos.length > 3 ? ` and ${errorRepos.length - 3} more` : ''}`;
    }

    const statusColors = {
      connected: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
      warning: 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800',
      error: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
      checking: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
    };

    const statusText = {
      connected: 'Healthy',
      warning: 'Warning',
      error: hasTokenIssues ? 'Token Issues' : 'Issues',
      checking: 'Checking...'
    };

    const statusIndicator = {
      connected: 'bg-green-500',
      warning: 'bg-yellow-500 animate-pulse',
      error: 'bg-red-500 animate-pulse',
      checking: 'bg-blue-500 animate-pulse'
    };

    const iconBg = {
      connected: 'bg-green-100 dark:bg-green-900/30',
      warning: 'bg-yellow-100 dark:bg-yellow-900/30',
      error: 'bg-red-100 dark:bg-red-900/30',
      checking: 'bg-blue-100 dark:bg-blue-900/30'
    };

    const iconColor = {
      connected: 'text-green-600 dark:text-green-400',
      warning: 'text-yellow-600 dark:text-yellow-400',
      error: 'text-red-600 dark:text-red-400',
      checking: 'text-blue-600 dark:text-blue-400'
    };

    const textColor = {
      connected: 'text-green-700 dark:text-green-300',
      warning: 'text-yellow-700 dark:text-yellow-300',
      error: 'text-red-700 dark:text-red-300',
      checking: 'text-blue-700 dark:text-blue-300'
    };

    return (
      <div className={`rounded-lg p-4 border hover:shadow-md transition-all duration-200 ${statusColors[status] || statusColors.error}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <div className={`p-2 rounded-lg mr-3 ${iconBg[status] || iconBg.error}`}>
              {hasTokenIssues ? (
                <Shield className={`h-4 w-4 ${iconColor[status] || iconColor.error}`} />
              ) : (
                <IconComponent className={`h-4 w-4 ${iconColor[status] || iconColor.error}`} />
              )}
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">{serviceName}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
              {errorDetails && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1">{errorDetails}</p>
              )}
            </div>
          </div>
          <div className="flex items-center space-x-3">
            {showTokenButton && (
              <button
                onClick={handleNavigateToRepositories}
                className="flex items-center px-3 py-1.5 text-xs font-medium text-red-700 dark:text-red-300 bg-red-100 dark:bg-red-900/30 rounded-md hover:bg-red-200 dark:hover:bg-red-900/50 transition-colors"
              >
                <Key className="h-3 w-3 mr-1" />
                Configure Tokens
              </button>
            )}
            <div className="flex items-center">
              <div className={`w-2 h-2 rounded-full mr-2 ${statusIndicator[status] || statusIndicator.error}`}></div>
              <div className="flex flex-col">
                <span className={`text-sm font-bold ${textColor[status] || textColor.error}`}>
                  {statusText[status] || 'Error'}
                </span>
                {repoHealth.isChecking && status !== 'checking' && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 font-normal animate-pulse">
                    checking...
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const renderServiceStatus = (serviceKey, serviceName, IconComponent, description) => {
    // Special handling for repositories service
    if (serviceKey === 'repositories') {
      return renderRepositoryStatus(serviceName, IconComponent, description);
    }
    
    // Prioritize individual health check data over backend health data
    const service = individualServiceHealth[serviceKey] || systemHealth?.services?.[serviceKey];
    console.log(`RENDER ${serviceKey}:`, JSON.stringify(service, null, 2));
    
    if (!service) {
      return (
        <div key={serviceKey} className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className="bg-gray-100 dark:bg-gray-600 p-2 rounded-lg mr-3">
                <IconComponent className="h-4 w-4 text-gray-500 dark:text-gray-400" />
              </div>
              <div>
                <p className="text-sm font-semibold text-gray-900 dark:text-white">{serviceName}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
              </div>
            </div>
            <div className="flex items-center">
              <div className="w-2 h-2 bg-gray-500 rounded-full mr-2"></div>
              <span className="text-sm font-bold text-gray-500 dark:text-gray-400">Unknown</span>
            </div>
          </div>
        </div>
      );
    }

    const statusColors = {
      healthy: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
      connected: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
      disabled: 'bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600',
      configured: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
      unhealthy: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
      unreachable: 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800',
      misconfigured: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
      error: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
      checking: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800'
    };

    const statusText = {
      healthy: 'Healthy',
      connected: 'Connected',
      disabled: 'Disabled',
      configured: 'Configured',
      unhealthy: 'Unhealthy',
      unreachable: 'Unreachable',
      misconfigured: 'Error',
      error: 'Error',
      checking: 'Checking...'
    };

    const statusIndicator = {
      healthy: 'bg-green-500 animate-pulse',
      connected: 'bg-green-500',
      disabled: 'bg-gray-500',
      configured: 'bg-blue-500',
      unhealthy: 'bg-red-500 animate-pulse',
      unreachable: 'bg-orange-500 animate-pulse',
      misconfigured: 'bg-red-500 animate-pulse',
      error: 'bg-red-500 animate-pulse',
      checking: 'bg-blue-500 animate-pulse'
    };

    const iconBg = {
      healthy: 'bg-green-100 dark:bg-green-900/30',
      connected: 'bg-green-100 dark:bg-green-900/30',
      disabled: 'bg-gray-100 dark:bg-gray-600',
      configured: 'bg-blue-100 dark:bg-blue-900/30',
      unhealthy: 'bg-red-100 dark:bg-red-900/30',
      unreachable: 'bg-orange-100 dark:bg-orange-900/30',
      misconfigured: 'bg-red-100 dark:bg-red-900/30',
      error: 'bg-red-100 dark:bg-red-900/30',
      checking: 'bg-blue-100 dark:bg-blue-900/30'
    };

    const iconColor = {
      healthy: 'text-green-600 dark:text-green-400',
      connected: 'text-green-600 dark:text-green-400',
      disabled: 'text-gray-500 dark:text-gray-400',
      configured: 'text-blue-600 dark:text-blue-400',
      unhealthy: 'text-red-600 dark:text-red-400',
      unreachable: 'text-orange-600 dark:text-orange-400',
      misconfigured: 'text-red-600 dark:text-red-400',
      error: 'text-red-600 dark:text-red-400',
      checking: 'text-blue-600 dark:text-blue-400'
    };

    const textColor = {
      healthy: 'text-green-700 dark:text-green-300',
      connected: 'text-green-700 dark:text-green-300',
      disabled: 'text-gray-600 dark:text-gray-400',
      configured: 'text-blue-700 dark:text-blue-300',
      unhealthy: 'text-red-700 dark:text-red-300',
      unreachable: 'text-orange-700 dark:text-orange-300',
      misconfigured: 'text-red-700 dark:text-red-300',
      error: 'text-red-700 dark:text-red-300',
      checking: 'text-blue-700 dark:text-blue-300'
    };

    return (
      <div key={serviceKey} className={`rounded-lg p-4 border hover:shadow-md transition-all duration-200 ${statusColors[service.status] || statusColors.unhealthy}`}>
        <div className="flex items-center justify-between">
          <div className="flex items-center">
            <div className={`p-2 rounded-lg mr-3 ${iconBg[service.status] || iconBg.unhealthy}`}>
              <IconComponent className={`h-4 w-4 ${iconColor[service.status] || iconColor.unhealthy}`} />
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-white">{serviceName}</p>
              <p className="text-xs text-gray-500 dark:text-gray-400">{description}</p>
              {service.error && (
                <p className="text-xs text-red-600 dark:text-red-400 mt-1">{service.error}</p>
              )}
            </div>
          </div>
          <div className="flex items-center space-x-3">
            {/* Add shortcut button for disabled context service */}
            {serviceKey === 'context_service' && service.status === 'disabled' && onNavigateToConfig && (
              <button
                onClick={() => onNavigateToConfig('context-service-section')}
                className="flex items-center px-3 py-1 text-xs bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors duration-200"
              >
                <Settings className="h-3 w-3 mr-1" />
                Enable
              </button>
            )}
            <div className="flex items-center">
              <div className={`w-2 h-2 rounded-full mr-2 ${statusIndicator[service.status] || statusIndicator.unhealthy}`}></div>
              <div className="flex flex-col">
                <span className={`text-sm font-bold ${textColor[service.status] || textColor.unhealthy}`}>
                  {statusText[service.status] || 'Error'}
                </span>
                {service.isChecking && service.status !== 'checking' && (
                  <span className="text-xs text-gray-500 dark:text-gray-400 font-normal animate-pulse">
                    checking...
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  };

  const healthStatus = getSystemHealthStatus();

  return (
    <div className="space-y-6">
      {/* Expandable System Health Header */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div 
          className={`${getHealthBgColor(healthStatus.status)} cursor-pointer transition-all duration-300 hover:shadow-lg`}
          onClick={() => setHealthExpanded(!healthExpanded)}
        >
          <div className="px-6 py-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <div className="bg-white/20 p-3 rounded-lg mr-4">
                  <Server className={`h-6 w-6 ${healthStatus.textColor}`} />
                </div>
                <div>
                  <h2 className={`text-xl font-bold ${healthStatus.textColor}`}>System Health</h2>
                  <p className={`${healthStatus.textColor} opacity-90`}>{healthStatus.message}</p>
                </div>
              </div>
              <div className="flex items-center">
                <div className={`w-3 h-3 bg-white/80 rounded-full mr-3 ${healthStatus.status === 'healthy' ? 'animate-pulse' : ''}`}></div>
                <span className={`text-sm font-semibold ${healthStatus.textColor} mr-4 uppercase tracking-wide`}>
                  {healthStatus.status}
                </span>
                {healthExpanded ? (
                  <ChevronUp className={`h-5 w-5 ${healthStatus.textColor}`} />
                ) : (
                  <ChevronDown className={`h-5 w-5 ${healthStatus.textColor}`} />
                )}
              </div>
            </div>
          </div>
        </div>
        
        {/* Expandable Content */}
        {healthExpanded && (
          <div className="p-6 border-t border-gray-200 dark:border-gray-700">
            <div className="space-y-4">
              {renderServiceStatus('database', 'Database', Database, 'SQLite storage')}
              {renderServiceStatus('pr_agent_config', 'PR-Agent Config', Server, 'Configuration file')}
              {renderServiceStatus('context_service', 'Context Service', Wifi, 'Code context API')}
              {renderServiceStatus('repositories', 'Repository Runners', GitBranch, 'GitHub/Azure DevOps agents')}
            </div>
          </div>
        )}
      </div>

      {/* Stats Row - Single Row of 4 Cards */}
      <div className="grid grid-cols-4 gap-6">
        {/* Total Jobs Card */}
        <div 
          className="group bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-xl transition-all duration-300 hover:scale-105 cursor-pointer"
          onClick={() => onNavigateToJobs && onNavigateToJobs()}
        >
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="bg-blue-100 dark:bg-blue-900/30 p-3 rounded-lg group-hover:bg-blue-200 dark:group-hover:bg-blue-800/40 transition-colors">
                <GitPullRequest className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
            </div>
            <div className="ml-4 flex-1">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Total Jobs</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">{totalJobs}</p>
              <div className="flex items-center mt-2">
                <TrendingUp className="h-4 w-4 text-green-500 mr-1" />
                <span className="text-xs text-green-600 dark:text-green-400 font-medium">All time</span>
              </div>
            </div>
          </div>
        </div>

        {/* Active Jobs Card */}
        <div 
          className="group bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-xl transition-all duration-300 hover:scale-105 cursor-pointer"
          onClick={() => onNavigateToJobs && onNavigateToJobs('running')}
        >
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="bg-blue-100 dark:bg-blue-900/30 p-3 rounded-lg group-hover:bg-blue-200 dark:group-hover:bg-blue-800/40 transition-colors">
                <Activity className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
            </div>
            <div className="ml-4 flex-1">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Active</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">{runningJobs}</p>
              <div className="flex items-center mt-2">
                {runningJobs > 0 ? (
                  <>
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse mr-2"></div>
                    <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">Running</span>
                  </>
                ) : (
                  <span className="text-xs text-gray-500 dark:text-gray-400">Idle</span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Completed Jobs Card */}
        <div 
          className="group bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-xl transition-all duration-300 hover:scale-105 cursor-pointer"
          onClick={() => onNavigateToJobs && onNavigateToJobs('completed')}
        >
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="bg-green-100 dark:bg-green-900/30 p-3 rounded-lg group-hover:bg-green-200 dark:group-hover:bg-green-800/40 transition-colors">
                <CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400" />
              </div>
            </div>
            <div className="ml-4 flex-1">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Completed</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">{completedJobs}</p>
              <div className="flex items-center mt-2">
                <CheckCircle className="h-4 w-4 text-green-500 mr-1" />
                <span className="text-xs text-green-600 dark:text-green-400 font-medium">Success</span>
              </div>
            </div>
          </div>
        </div>

        {/* Failed Jobs Card */}
        <div 
          className="group bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-xl transition-all duration-300 hover:scale-105 cursor-pointer"
          onClick={() => onNavigateToJobs && onNavigateToJobs('failed')}
        >
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="bg-red-100 dark:bg-red-900/30 p-3 rounded-lg group-hover:bg-red-200 dark:group-hover:bg-red-800/40 transition-colors">
                <AlertCircle className="h-6 w-6 text-red-600 dark:text-red-400" />
              </div>
            </div>
            <div className="ml-4 flex-1">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Failed</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">{failedJobs}</p>
              <div className="flex items-center mt-2">
                {failedJobs > 0 ? (
                  <>
                    <AlertCircle className="h-4 w-4 text-red-500 mr-1" />
                    <span className="text-xs text-red-600 dark:text-red-400 font-medium">Needs attention</span>
                  </>
                ) : (
                  <span className="text-xs text-gray-500 dark:text-gray-400">All good</span>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Recent Jobs Activity */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="bg-blue-50 dark:bg-blue-900/20 px-6 py-5 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <Activity className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Activity</h3>
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400">Last 5 jobs</span>
          </div>
        </div>
        <div className="p-6">
          {displayJobs.length > 0 ? (
            <div className="space-y-3">
              {displayJobs.map((job, index) => {
                const StatusIcon = getStatusIcon(job.status);
                const isJob = job.job_id; // Check if this is a job or legacy operation
                return (
                  <div 
                    key={job.job_id || job.id || index} 
                    className="group bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600 hover:shadow-md transition-all duration-200 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                    onClick={() => {
                      if (isJob && onNavigateToJob) {
                        onNavigateToJob(job.job_id);
                      }
                    }}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center flex-1 min-w-0">
                        <div className={`p-2 rounded-lg mr-3 ${getStatusColor(job.status).replace('text-', 'bg-').replace('bg-', 'bg-').split(' ')[1]}`}>
                          <StatusIcon className={`h-4 w-4 ${getStatusColor(job.status).split(' ')[0]}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                            {isJob ? 
                              `${job.job_type} job - ${job.repository || 'Unknown repo'}` :
                              job.command || job.operation_type || 'Unknown Operation'
                            }
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                            {isJob ? 
                              `${job.operations_count || 0} operations • ${formatTime(job.started_at)}` :
                              `${job.repo || 'Unknown repo'} • ${formatTime(job.started_at || job.timestamp)}`
                            }
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center ml-4">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(job.status)}`}>
                          {formatStatus(job.status)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="text-center py-8">
              <Activity className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500" />
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-white">No recent activity</h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Jobs will appear here when PR-Agent starts working.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StatusOverview; 