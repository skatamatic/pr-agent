import React, { useState, useEffect } from 'react';
import { Activity, CheckCircle, Clock, AlertCircle, Zap, GitPullRequest, TrendingUp, Server, Wifi, Database, ChevronDown, ChevronUp, Settings } from 'lucide-react';
import apiService from '../services/api';

const StatusOverview = ({ operations = [], onNavigateToConfig }) => {
  const [systemHealth, setSystemHealth] = useState(null);
  const [realtimeStatus, setRealtimeStatus] = useState(null);
  const [healthExpanded, setHealthExpanded] = useState(false);
  
  useEffect(() => {
    fetchSystemStatus();
    const interval = setInterval(fetchSystemStatus, 10000); // Update every 10 seconds
    return () => clearInterval(interval);
  }, []);
  
  const fetchSystemStatus = async () => {
    try {
      const [healthRes, statusRes] = await Promise.all([
        apiService.getSystemHealth().catch(() => ({ data: { status: 'unknown', services: {} } })),
        apiService.getRealtimeStatus().catch(() => ({ data: { operations: {}, services: {} } }))
      ]);
      
      setSystemHealth(healthRes.data);
      setRealtimeStatus(statusRes.data);
      
      // Auto-expand if there are issues
      const hasIssues = Object.values(healthRes.data.services || {}).some(service => 
        service.status && ['unhealthy', 'unreachable'].includes(service.status)
      );
      setHealthExpanded(hasIssues);
    } catch (error) {
      console.error('Failed to fetch system status:', error);
      setHealthExpanded(true); // Expand on error
    }
  };

  // Calculate status counts - use realtime data if available, otherwise fallback to operations prop
  const operationsData = realtimeStatus?.operations || {};
  const totalOperations = operationsData.total || operations.length;
  const activeOperations = operationsData.active || operations.filter(op => op.status === 'processing').length;
  const completedOperations = operationsData.completed || operations.filter(op => op.status === 'completed').length;
  const failedOperations = operationsData.failed || operations.filter(op => op.status === 'failed').length;

  // Recent operations (last 5)
  const recentOperations = realtimeStatus?.recent_operations || 
    operations
      .sort((a, b) => new Date(b.started_at || b.timestamp) - new Date(a.started_at || a.timestamp))
      .slice(0, 5);

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/20';
      case 'processing': return 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/20';
      case 'fetching_context': return 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/20';
      case 'context_completed': return 'text-green-600 bg-green-50 dark:text-green-400 dark:bg-green-900/20';
      case 'failed': return 'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-900/20';
      case 'context_failed': return 'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-900/20';
      default: return 'text-gray-600 bg-gray-50 dark:text-gray-400 dark:bg-gray-800';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return CheckCircle;
      case 'processing': return Activity;
      case 'fetching_context': return Clock;
      case 'context_completed': return CheckCircle;
      case 'failed': return AlertCircle;
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
    if (!systemHealth) return { status: 'unknown', color: 'gray', message: 'Checking system status...' };
    
    // Use overall status from backend if available, otherwise calculate
    if (systemHealth.status) {
      switch (systemHealth.status) {
        case 'healthy':
          return { 
            status: 'healthy', 
            color: 'green', 
            message: 'All systems operational',
            textColor: 'text-white'
          };
        case 'degraded':
          return { 
            status: 'warning', 
            color: 'yellow', 
            message: 'Some services have issues',
            textColor: 'text-white'
          };
        case 'unhealthy':
          return { 
            status: 'unhealthy', 
            color: 'red', 
            message: 'Critical service failures detected',
            textColor: 'text-white'
          };
        default:
          return { 
            status: 'unknown', 
            color: 'gray', 
            message: 'System status unknown',
            textColor: 'text-white'
          };
      }
    }
    
    // Fallback: Check for actual failures (not disabled services)
    const hasFailures = Object.values(systemHealth.services || {}).some(service => 
      service.status && ['unhealthy', 'unreachable', 'misconfigured', 'error'].includes(service.status)
    );
    
    // Check for disabled services as warnings
    const hasDisabledServices = Object.values(systemHealth.services || {}).some(service => 
      service.status === 'disabled'
    );
    
    if (hasFailures) {
      return { 
        status: 'unhealthy', 
        color: 'red', 
        message: 'Service issues detected',
        textColor: 'text-white'
      };
    } else if (hasDisabledServices) {
      return { 
        status: 'warning', 
        color: 'yellow', 
        message: 'Some features are disabled',
        textColor: 'text-white'
      };
    } else {
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
      case 'unhealthy': return 'bg-red-600 dark:bg-red-700';
      default: return 'bg-gray-600 dark:bg-gray-700';
    }
  };

  const renderServiceStatus = (serviceKey, serviceName, IconComponent, description) => {
    const service = systemHealth?.services?.[serviceKey];
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
      disabled: 'bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600',
      configured: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
      unhealthy: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
      unreachable: 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800',
      misconfigured: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800',
      error: 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
    };

    const statusText = {
      healthy: 'Healthy',
      disabled: 'Disabled',
      configured: 'Configured',
      unhealthy: 'Unhealthy',
      unreachable: 'Unreachable',
      misconfigured: 'Error',
      error: 'Error'
    };

    const statusIndicator = {
      healthy: 'bg-green-500 animate-pulse',
      disabled: 'bg-gray-500',
      configured: 'bg-blue-500',
      unhealthy: 'bg-red-500 animate-pulse',
      unreachable: 'bg-orange-500 animate-pulse',
      misconfigured: 'bg-red-500 animate-pulse',
      error: 'bg-red-500 animate-pulse'
    };

    const iconBg = {
      healthy: 'bg-green-100 dark:bg-green-900/30',
      disabled: 'bg-gray-100 dark:bg-gray-600',
      configured: 'bg-blue-100 dark:bg-blue-900/30',
      unhealthy: 'bg-red-100 dark:bg-red-900/30',
      unreachable: 'bg-orange-100 dark:bg-orange-900/30',
      misconfigured: 'bg-red-100 dark:bg-red-900/30',
      error: 'bg-red-100 dark:bg-red-900/30'
    };

    const iconColor = {
      healthy: 'text-green-600 dark:text-green-400',
      disabled: 'text-gray-500 dark:text-gray-400',
      configured: 'text-blue-600 dark:text-blue-400',
      unhealthy: 'text-red-600 dark:text-red-400',
      unreachable: 'text-orange-600 dark:text-orange-400',
      misconfigured: 'text-red-600 dark:text-red-400',
      error: 'text-red-600 dark:text-red-400'
    };

    const textColor = {
      healthy: 'text-green-700 dark:text-green-300',
      disabled: 'text-gray-600 dark:text-gray-400',
      configured: 'text-blue-700 dark:text-blue-300',
      unhealthy: 'text-red-700 dark:text-red-300',
      unreachable: 'text-orange-700 dark:text-orange-300',
      misconfigured: 'text-red-700 dark:text-red-300',
      error: 'text-red-700 dark:text-red-300'
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
              <span className={`text-sm font-bold ${textColor[service.status] || textColor.unhealthy}`}>
                {statusText[service.status] || 'Error'}
              </span>
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
            </div>
          </div>
        )}
      </div>

      {/* Stats Row - Single Row of 4 Cards */}
      <div className="grid grid-cols-4 gap-6">
        <div className="group bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-xl transition-all duration-300 hover:scale-105">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="bg-blue-100 dark:bg-blue-900/30 p-3 rounded-lg group-hover:bg-blue-200 dark:group-hover:bg-blue-800/40 transition-colors">
                <GitPullRequest className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
            </div>
            <div className="ml-4 flex-1">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Total Operations</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">{totalOperations}</p>
              <div className="flex items-center mt-2">
                <TrendingUp className="h-4 w-4 text-green-500 mr-1" />
                <span className="text-xs text-green-600 dark:text-green-400 font-medium">All time</span>
              </div>
            </div>
          </div>
        </div>

        <div className="group bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-xl transition-all duration-300 hover:scale-105">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="bg-blue-100 dark:bg-blue-900/30 p-3 rounded-lg group-hover:bg-blue-200 dark:group-hover:bg-blue-800/40 transition-colors">
                <Activity className="h-6 w-6 text-blue-600 dark:text-blue-400" />
              </div>
            </div>
            <div className="ml-4 flex-1">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Active</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">{activeOperations}</p>
              <div className="flex items-center mt-2">
                {activeOperations > 0 ? (
                  <>
                    <div className="w-2 h-2 bg-blue-500 rounded-full animate-pulse mr-2"></div>
                    <span className="text-xs text-blue-600 dark:text-blue-400 font-medium">Processing</span>
                  </>
                ) : (
                  <span className="text-xs text-gray-500 dark:text-gray-400">Idle</span>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="group bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-xl transition-all duration-300 hover:scale-105">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="bg-green-100 dark:bg-green-900/30 p-3 rounded-lg group-hover:bg-green-200 dark:group-hover:bg-green-800/40 transition-colors">
                <CheckCircle className="h-6 w-6 text-green-600 dark:text-green-400" />
              </div>
            </div>
            <div className="ml-4 flex-1">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Completed</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">{completedOperations}</p>
              <div className="flex items-center mt-2">
                <CheckCircle className="h-4 w-4 text-green-500 mr-1" />
                <span className="text-xs text-green-600 dark:text-green-400 font-medium">Success</span>
              </div>
            </div>
          </div>
        </div>

        <div className="group bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 p-6 hover:shadow-xl transition-all duration-300 hover:scale-105">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <div className="bg-red-100 dark:bg-red-900/30 p-3 rounded-lg group-hover:bg-red-200 dark:group-hover:bg-red-800/40 transition-colors">
                <AlertCircle className="h-6 w-6 text-red-600 dark:text-red-400" />
              </div>
            </div>
            <div className="ml-4 flex-1">
              <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">Failed</p>
              <p className="text-3xl font-bold text-gray-900 dark:text-white">{failedOperations}</p>
              <div className="flex items-center mt-2">
                {failedOperations > 0 ? (
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

      {/* Recent Operations Activity */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
        <div className="bg-blue-50 dark:bg-blue-900/20 px-6 py-5 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <Activity className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Recent Activity</h3>
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400">Last 5 operations</span>
          </div>
        </div>
        <div className="p-6">
          {recentOperations.length > 0 ? (
            <div className="space-y-3">
              {recentOperations.map((operation, index) => {
                const StatusIcon = getStatusIcon(operation.status);
                return (
                  <div key={operation.id || index} className="group bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600 hover:shadow-md transition-all duration-200">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center flex-1 min-w-0">
                        <div className={`p-2 rounded-lg mr-3 ${getStatusColor(operation.status).replace('text-', 'bg-').replace('bg-', 'bg-').split(' ')[1]}`}>
                          <StatusIcon className={`h-4 w-4 ${getStatusColor(operation.status).split(' ')[0]}`} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-semibold text-gray-900 dark:text-white truncate">
                            {operation.command || operation.operation_type || 'Unknown Operation'}
                          </p>
                          <p className="text-xs text-gray-500 dark:text-gray-400 truncate">
                            {operation.repo || 'Unknown repo'} • {formatTime(operation.started_at || operation.timestamp)}
                          </p>
                        </div>
                      </div>
                      <div className="flex items-center ml-4">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(operation.status)}`}>
                          {formatStatus(operation.status)}
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
              <h3 className="mt-2 text-sm font-medium text-gray-900 dark:text-white">No recent operations</h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Operations will appear here when PR-Agent starts working.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default StatusOverview; 