import React, { useState, useEffect } from 'react';
import { Activity, CheckCircle, Clock, AlertCircle, RefreshCw, ExternalLink, ChevronLeft, ChevronRight, Filter, TrendingUp, Zap, Brain, GitBranch, FileText, Lightbulb } from 'lucide-react';
import api from '../services/api';
import ViewHeader from './ViewHeader';
import OperationInsights from './OperationInsights';
import { formatTimeSaved } from '../utils/timeUtils';

const OperationsList = ({ operations = [], onRefresh, onShowLogs }) => {
  const [activeTab, setActiveTab] = useState('live');
  const [liveStatusFilters, setLiveStatusFilters] = useState(['starting', 'processing', 'fetching_context', 'self_reflecting', 'publishing']);
  const [repoFilter, setRepoFilter] = useState('all');
  const [repositoryNames, setRepositoryNames] = useState([]);
  const [sortBy, setSortBy] = useState('timestamp');
  const [sortOrder, setSortOrder] = useState('desc');
  const [currentPage, setCurrentPage] = useState(1);
  const [showInsights, setShowInsights] = useState(false);
  const [selectedOperationId, setSelectedOperationId] = useState(null);
  const itemsPerPage = 25;

  // Fetch repository names for filtering
  useEffect(() => {
    const fetchRepositoryNames = async () => {
      try {
        const response = await api.getRepositoryNames({ active_only: false });
        const names = response.data.data || [];
        setRepositoryNames(names);
      } catch (error) {
        console.error('Failed to fetch repository names:', error);
      }
    };
    
    fetchRepositoryNames();
  }, []);

  // Also extract unique repo names from operations as fallback
  const uniqueRepoNames = [...new Set(operations.map(op => op.repo).filter(Boolean))];
  const allRepoNames = [...new Set([...repositoryNames, ...uniqueRepoNames])];

  const getStatusColor = (status) => {
    switch (status) {
      case 'completed': return 'text-green-600 bg-green-50 border-green-200 dark:text-green-400 dark:bg-green-900/20 dark:border-green-800';
      case 'starting': return 'text-blue-600 bg-blue-50 border-blue-200 dark:text-blue-400 dark:bg-blue-900/20 dark:border-blue-800';
      case 'processing': return 'text-purple-600 bg-purple-50 border-purple-200 dark:text-purple-400 dark:bg-purple-900/20 dark:border-purple-800';
      case 'fetching_context': return 'text-yellow-600 bg-yellow-50 border-yellow-200 dark:text-yellow-400 dark:bg-yellow-900/20 dark:border-yellow-800';
      case 'context_completed': return 'text-green-600 bg-green-50 border-green-200 dark:text-green-400 dark:bg-green-900/20 dark:border-green-800';
      case 'self_reflecting': return 'text-indigo-600 bg-indigo-50 border-indigo-200 dark:text-indigo-400 dark:bg-indigo-900/20 dark:border-indigo-800';
      case 'publishing': return 'text-cyan-600 bg-cyan-50 border-cyan-200 dark:text-cyan-400 dark:bg-cyan-900/20 dark:border-cyan-800';
      case 'preparing': return 'text-orange-600 bg-orange-50 border-orange-200 dark:text-orange-400 dark:bg-orange-900/20 dark:border-orange-800';
      case 'context_disabled': return 'text-gray-600 bg-gray-50 border-gray-200 dark:text-gray-400 dark:bg-gray-800 dark:border-gray-600';
      case 'failed': return 'text-red-600 bg-red-50 border-red-200 dark:text-red-400 dark:bg-red-900/20 dark:border-red-800';
      case 'context_failed': return 'text-red-600 bg-red-50 border-red-200 dark:text-red-400 dark:bg-red-900/20 dark:border-red-800';
      case 'skipped': return 'text-gray-600 bg-gray-50 border-gray-200 dark:text-gray-400 dark:bg-gray-800 dark:border-gray-600';
      default: return 'text-gray-600 bg-gray-50 border-gray-200 dark:text-gray-400 dark:bg-gray-800 dark:border-gray-600';
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'completed': return CheckCircle;
      case 'starting': return Activity;
      case 'processing': return Brain;
      case 'fetching_context': return Clock;
      case 'context_completed': return CheckCircle;
      case 'self_reflecting': return Zap;
      case 'publishing': return GitBranch;
      case 'preparing': return Activity;
      case 'failed': return AlertCircle;
      case 'context_failed': return AlertCircle;
      case 'skipped': return AlertCircle;
      default: return Clock;
    }
  };

  const formatStatus = (status) => {
    return status.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
  };

  const formatDuration = (startTime, endTime) => {
    if (!startTime) return 'N/A';
    const start = new Date(startTime);
    const end = endTime ? new Date(endTime) : new Date();
    const duration = Math.round((end - start) / 1000);
    
    if (duration < 60) return `${duration}s`;
    if (duration < 3600) return `${Math.round(duration / 60)}m`;
    return `${Math.round(duration / 3600)}h`;
  };

  const isLiveStatus = (status) => {
    return ['starting', 'processing', 'fetching_context', 'context_completed', 'self_reflecting', 'publishing', 'preparing'].includes(status);
  };

  // Filter operations based on active tab
  const getTabOperations = () => {
    if (activeTab === 'live') {
      return operations.filter(op => isLiveStatus(op.status));
    } else {
      return operations.filter(op => !isLiveStatus(op.status));
    }
  };

  // Apply additional filters for live tab
  const filteredOperations = getTabOperations().filter(op => {
    // Repository filter (applies to both tabs)
    const repoMatch = repoFilter === 'all' || op.repo === repoFilter;
    
    if (activeTab === 'live') {
      // For live operations, only filter by status (not by result since they're still running)
      const statusMatch = liveStatusFilters.includes(op.status);
      return statusMatch && repoMatch;
    }
    return repoMatch;
  });

  // Sort operations
  const sortedOperations = [...filteredOperations].sort((a, b) => {
    let aVal = a[sortBy];
    let bVal = b[sortBy];
    
    if (sortBy === 'timestamp') {
      aVal = new Date(a.started_at || a.timestamp);
      bVal = new Date(b.started_at || b.timestamp);
    }
    
    if (sortOrder === 'asc') {
      return aVal > bVal ? 1 : -1;
    }
    return aVal < bVal ? 1 : -1;
  });

  // Pagination
  const totalPages = Math.ceil(sortedOperations.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedOperations = sortedOperations.slice(startIndex, startIndex + itemsPerPage);

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    setCurrentPage(1);
  };

  const toggleLiveStatusFilter = (status) => {
    setLiveStatusFilters(prev => {
      const newFilters = prev.includes(status) 
        ? prev.filter(s => s !== status)
        : [...prev, status];
      // Ensure at least one filter is selected
      return newFilters.length > 0 ? newFilters : [status];
    });
    setCurrentPage(1);
  };

  const handleSortChange = (field, order) => {
    setSortBy(field);
    setSortOrder(order);
    setCurrentPage(1);
  };

  const liveStatusOptions = [
    { key: 'starting', label: 'Starting', color: 'bg-blue-500 text-white', icon: Activity },
    { key: 'processing', label: 'Processing', color: 'bg-purple-500 text-white', icon: Brain },
    { key: 'fetching_context', label: 'Fetching Context', color: 'bg-yellow-500 text-white', icon: Clock },
    { key: 'self_reflecting', label: 'Self Reflecting', color: 'bg-indigo-500 text-white', icon: Zap },
    { key: 'publishing', label: 'Publishing', color: 'bg-cyan-500 text-white', icon: GitBranch }
  ];

  const liveCount = operations.filter(op => isLiveStatus(op.status)).length;
  const completedCount = operations.filter(op => !isLiveStatus(op.status)).length;

  // Helper function to format AI metrics display
  const formatAIMetrics = (operation) => {
    // Check for multi-model data first
    if (operation.ai_models_used && typeof operation.ai_models_used === 'object') {
      const models = Object.keys(operation.ai_models_used);
      const totalInput = operation.total_input_tokens || 0;
      const totalOutput = operation.total_output_tokens || 0;
      const totalTokens = totalInput + totalOutput;
      
      if (models.length > 1) {
        return {
          type: 'multi',
          display: `${models.length} models`,
          details: `${totalTokens.toLocaleString()} tokens`,
          breakdown: operation.ai_models_used,
          totalInput,
          totalOutput
        };
      } else if (models.length === 1) {
        return {
          type: 'single',
          display: models[0],
          details: `${totalTokens.toLocaleString()} tokens`,
          totalInput,
          totalOutput
        };
      }
    }
    
    // Fallback to legacy single model data
    if (operation.model_used || operation.input_tokens || operation.output_tokens) {
      const totalTokens = (operation.input_tokens || 0) + (operation.output_tokens || 0);
      return {
        type: 'legacy',
        display: operation.model_used || 'AI Model',
        details: totalTokens > 0 ? `${totalTokens.toLocaleString()} tokens` : null,
        totalInput: operation.input_tokens || 0,
        totalOutput: operation.output_tokens || 0
      };
    }
    
    return null;
  };

  // Helper function to get current step color and display
  const getCurrentStepInfo = (step) => {
    if (!step) return null;
    
    const stepInfo = {
      'Context': { color: 'bg-yellow-100 text-yellow-800 border-yellow-300', icon: '🔍' },
      'Generating': { color: 'bg-purple-100 text-purple-800 border-purple-300', icon: '⚡' },
      'Reflecting': { color: 'bg-indigo-100 text-indigo-800 border-indigo-300', icon: '🤔' },
      'DevTime': { color: 'bg-green-100 text-green-800 border-green-300', icon: '⏱️' },
      'Publishing': { color: 'bg-blue-100 text-blue-800 border-blue-300', icon: '📝' }
    };
    
    return stepInfo[step] || { color: 'bg-gray-100 text-gray-800 border-gray-300', icon: '▶️' };
  };



  const hasInsights = (operation) => {
    return operation.insights && typeof operation.insights === 'object' && Object.keys(operation.insights).length > 0;
  };

  const handleShowInsights = (operationId) => {
    setSelectedOperationId(operationId);
    setShowInsights(true);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <ViewHeader 
        title="Operations Dashboard"
        subtitle="Monitor live and completed PR operations"
        icon={TrendingUp}
        onRefresh={onRefresh}
      />

      {/* Enhanced Tabs */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="border-b border-gray-200 dark:border-gray-700">
          <nav className="flex space-x-8 px-6" aria-label="Tabs">
            <button
              onClick={() => handleTabChange('live')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-all duration-200 ${
                activeTab === 'live'
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              <div className="flex items-center space-x-2">
                <Activity className="h-4 w-4" />
                <span>Live Operations</span>
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  activeTab === 'live' 
                    ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400' 
                    : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                }`}>
                  {liveCount}
                </span>
              </div>
            </button>
            <button
              onClick={() => handleTabChange('completed')}
              className={`py-4 px-1 border-b-2 font-medium text-sm transition-all duration-200 ${
                activeTab === 'completed'
                  ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                  : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-300'
              }`}
            >
              <div className="flex items-center space-x-2">
                <CheckCircle className="h-4 w-4" />
                <span>Completed</span>
                <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                  activeTab === 'completed' 
                    ? 'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400' 
                    : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                }`}>
                  {completedCount}
                </span>
              </div>
            </button>
          </nav>
        </div>

        {/* Full UI Sliding Content */}
        <div className="relative overflow-hidden">
          {/* Live Tab Content */}
          <div 
            className={`transition-all duration-500 ease-in-out ${
              activeTab === 'live' 
                ? 'transform translate-x-0 opacity-100' 
                : 'transform -translate-x-full opacity-0 absolute top-0 left-0 w-full'
            }`}
          >
            <div className="p-6 space-y-6">
              {/* Live Operations Filters */}
              <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/10 dark:to-indigo-900/10 rounded-lg border border-blue-200 dark:border-blue-800 p-5">
                <div className="flex items-center space-x-3 mb-4">
                  <Filter className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                  <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Filter Live Operations</h3>
                </div>
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                      Repository
                    </label>
                    <select
                      value={repoFilter}
                      onChange={(e) => {
                        setRepoFilter(e.target.value);
                        setCurrentPage(1);
                      }}
                      className="w-full sm:w-auto border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                    >
                      <option value="all">All Repositories</option>
                      {allRepoNames.map(repo => (
                        <option key={repo} value={repo}>{repo}</option>
                      ))}
                    </select>
                  </div>
                  
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                      Operation Status
                    </label>
                    <div className="flex flex-wrap gap-3">
                      {liveStatusOptions.map(option => {
                        const Icon = option.icon;
                        return (
                          <button
                            key={option.key}
                            onClick={() => toggleLiveStatusFilter(option.key)}
                            className={`flex items-center space-x-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                              liveStatusFilters.includes(option.key)
                                ? option.color + ' shadow-md transform scale-105'
                                : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600'
                            }`}
                          >
                            <Icon className="h-4 w-4" />
                            <span>{option.label}</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>

              {/* Sort and Stats */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-4 sm:space-y-0">
                <div className="flex items-center space-x-4">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Sort by:</span>
                  <select
                    value={`${sortBy}-${sortOrder}`}
                    onChange={(e) => {
                      const [field, order] = e.target.value.split('-');
                      handleSortChange(field, order);
                    }}
                    className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="timestamp-desc">Newest First</option>
                    <option value="timestamp-asc">Oldest First</option>
                    <option value="status-asc">Status A-Z</option>
                    <option value="command-asc">Command A-Z</option>
                    <option value="duration-desc">Longest Duration</option>
                    <option value="duration-asc">Shortest Duration</option>
                  </select>
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  <span className="font-medium">{filteredOperations.length}</span> live operations found
                </div>
              </div>

              {/* Live Operations Table */}
              {paginatedOperations.length === 0 ? (
                <div className="p-12 text-center">
                  <div className="mx-auto w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-4">
                    <Activity className="h-8 w-8 text-gray-400 dark:text-gray-500" />
                  </div>
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                    No live operations found
                  </h3>
                  <p className="text-gray-500 dark:text-gray-400">
                    There are currently no operations in progress. Try adjusting your filters or check back later.
                  </p>
                </div>
              ) : (
                <div className="bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                      <thead className="bg-gray-50 dark:bg-gray-900">
                        <tr>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Operation
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Status
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Current Step
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Repository
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Duration
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Started
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Actions
                          </th>
                        </tr>
                      </thead>
                      <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                        {paginatedOperations.map((operation, index) => {
                          const StatusIcon = getStatusIcon(operation.status);
                          const stepInfo = getCurrentStepInfo(operation.current_step);
                          const aiMetrics = formatAIMetrics(operation);
                          
                          return (
                            <tr key={operation.operation_id || operation.id || index} className="hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-150">
                              <td className="px-6 py-4 whitespace-nowrap">
                                <div className="flex items-center">
                                  <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg mr-3">
                                    <StatusIcon className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                                  </div>
                                  <div>
                                    <div className="text-sm font-medium text-gray-900 dark:text-white">
                                      {operation.operation_type || operation.command || operation.type || 'Unknown'}
                                    </div>
                                    {aiMetrics && (
                                      <div className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                        {aiMetrics.display} {aiMetrics.details && `• ${aiMetrics.details}`}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium border ${getStatusColor(operation.status)}`}>
                                  {formatStatus(operation.status)}
                                </span>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                {stepInfo && operation.status !== 'completed' && operation.status !== 'failed' && operation.status !== 'skipped' ? (
                                  <span className={`inline-flex items-center px-2.5 py-1.5 rounded-lg text-xs font-medium border ${stepInfo.color}`}>
                                    <span className="mr-1.5">{stepInfo.icon}</span>
                                    {operation.current_step}
                                  </span>
                                ) : (
                                  <span className="text-sm text-gray-400 dark:text-gray-500">-</span>
                                )}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <div className="text-sm text-gray-900 dark:text-white font-medium">
                                  {operation.repo || 'N/A'}
                                </div>
                                {operation.pr_url && (
                                  <div className="text-sm text-gray-500 dark:text-gray-400">
                                    PR #{operation.pr_url.split('/').pop()}
                                  </div>
                                )}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                                {operation.duration ? `${Math.round(operation.duration)}s` : formatDuration(operation.started_at || operation.timestamp, operation.completed_at)}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                {new Date(operation.started_at || operation.timestamp).toLocaleString()}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                                <div className="flex items-center space-x-3">
                                  {operation.pr_url && (
                                    <a
                                      href={operation.pr_url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="inline-flex items-center text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 transition-colors duration-150"
                                    >
                                      <ExternalLink className="h-4 w-4 mr-1" />
                                      View PR
                                    </a>
                                  )}
                                  {hasInsights(operation) && (
                                    <button
                                      onClick={() => handleShowInsights(operation.operation_id || operation.id)}
                                      className="inline-flex items-center text-purple-600 hover:text-purple-700 dark:text-purple-400 dark:hover:text-purple-300 transition-colors duration-150"
                                    >
                                      <Lightbulb className="h-4 w-4 mr-1" />
                                      AI Insights
                                    </button>
                                  )}
                                  <button
                                    onClick={() => onShowLogs && onShowLogs(operation.request_id || operation.operation_id || operation.id)}
                                    className="inline-flex items-center text-gray-600 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-150"
                                  >
                                    <FileText className="h-4 w-4 mr-1" />
                                    Show Logs
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* Completed Tab Content */}
          <div 
            className={`transition-all duration-500 ease-in-out ${
              activeTab === 'completed' 
                ? 'transform translate-x-0 opacity-100' 
                : 'transform translate-x-full opacity-0 absolute top-0 left-0 w-full'
            }`}
          >
            <div className="p-6 space-y-6">
              {/* Repository Filter for Completed */}
              <div className="bg-gradient-to-r from-gray-50 to-slate-50 dark:from-gray-900/10 dark:to-slate-900/10 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                <div className="flex items-center space-x-3 mb-3">
                  <Filter className="h-4 w-4 text-gray-600 dark:text-gray-400" />
                  <h3 className="text-sm font-medium text-gray-900 dark:text-white">Filter by Repository</h3>
                </div>
                <select
                  value={repoFilter}
                  onChange={(e) => {
                    setRepoFilter(e.target.value);
                    setCurrentPage(1);
                  }}
                  className="w-full sm:w-auto border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="all">All Repositories</option>
                  {allRepoNames.map(repo => (
                    <option key={repo} value={repo}>{repo}</option>
                  ))}
                </select>
              </div>
              
              {/* Sort and Stats for Completed */}
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between space-y-4 sm:space-y-0">
                <div className="flex items-center space-x-4">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Sort by:</span>
                  <select
                    value={`${sortBy}-${sortOrder}`}
                    onChange={(e) => {
                      const [field, order] = e.target.value.split('-');
                      handleSortChange(field, order);
                    }}
                    className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  >
                    <option value="timestamp-desc">Newest First</option>
                    <option value="timestamp-asc">Oldest First</option>
                    <option value="status-asc">Status A-Z</option>
                    <option value="command-asc">Command A-Z</option>
                    <option value="duration-desc">Longest Duration</option>
                    <option value="duration-asc">Shortest Duration</option>
                  </select>
                </div>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  <span className="font-medium">{filteredOperations.length}</span> completed operations
                </div>
              </div>

              {/* Completed Operations Table */}
              {paginatedOperations.length === 0 ? (
                <div className="p-12 text-center">
                  <div className="mx-auto w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-4">
                    <CheckCircle className="h-8 w-8 text-gray-400 dark:text-gray-500" />
                  </div>
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">
                    No completed operations found
                  </h3>
                  <p className="text-gray-500 dark:text-gray-400">
                    No completed operations match your current view.
                  </p>
                </div>
              ) : (
                <div className="bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700 rounded-xl overflow-hidden">
                  <div className="overflow-x-auto">
                    <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                      <thead className="bg-gray-50 dark:bg-gray-900">
                        <tr>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Operation
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Status
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            AI Metrics
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Repository
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Duration
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Completed
                          </th>
                          <th className="px-6 py-4 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                            Actions
                          </th>
                        </tr>
                      </thead>
                      <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                        {paginatedOperations.map((operation, index) => {
                          const StatusIcon = getStatusIcon(operation.status);
                          const aiMetrics = formatAIMetrics(operation);
                          const timeSaved = formatTimeSaved(operation.estimated_dev_hours_saved);
                          
                          return (
                            <tr key={operation.operation_id || operation.id || index} className="hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-150">
                              <td className="px-6 py-4 whitespace-nowrap">
                                <div className="flex items-center">
                                  <div className="p-2 bg-gray-100 dark:bg-gray-700 rounded-lg mr-3">
                                    <StatusIcon className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                                  </div>
                                  <div>
                                    <div className="text-sm font-medium text-gray-900 dark:text-white">
                                      {operation.operation_type || operation.command || operation.type || 'Unknown'}
                                    </div>
                                    {timeSaved && (
                                      <div className={`text-xs mt-1 flex items-center ${timeSaved.color}`}>
                                        <span className="mr-1">{timeSaved.icon}</span>
                                        {timeSaved.display}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <span className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium border ${getStatusColor(operation.status)}`}>
                                  {formatStatus(operation.status)}
                                </span>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                {aiMetrics ? (
                                  <div>
                                    <div className="text-sm font-medium text-gray-900 dark:text-white">
                                      {aiMetrics.display}
                                    </div>
                                    {aiMetrics.details && (
                                      <div className="text-xs text-gray-500 dark:text-gray-400">
                                        {aiMetrics.details}
                                      </div>
                                    )}
                                    {aiMetrics.type === 'multi' && aiMetrics.breakdown && (
                                      <div className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                                        {Object.entries(aiMetrics.breakdown).map(([model, tokens]) => (
                                          <div key={model} className="truncate">
                                            {model}: {((tokens.input_tokens || 0) + (tokens.output_tokens || 0)).toLocaleString()}
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <span className="text-sm text-gray-400 dark:text-gray-500">-</span>
                                )}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <div className="text-sm text-gray-900 dark:text-white font-medium">
                                  {operation.repo || 'N/A'}
                                </div>
                                {operation.pr_url && (
                                  <div className="text-sm text-gray-500 dark:text-gray-400">
                                    PR #{operation.pr_url.split('/').pop()}
                                  </div>
                                )}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                                {operation.duration ? `${Math.round(operation.duration)}s` : formatDuration(operation.started_at || operation.timestamp, operation.completed_at)}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                {operation.completed_at ? new Date(operation.completed_at).toLocaleString() : 'N/A'}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                                <div className="flex items-center space-x-3">
                                  {operation.pr_url && (
                                    <a
                                      href={operation.pr_url}
                                      target="_blank"
                                      rel="noopener noreferrer"
                                      className="inline-flex items-center text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300 transition-colors duration-150"
                                    >
                                      <ExternalLink className="h-4 w-4 mr-1" />
                                      View PR
                                    </a>
                                  )}
                                  {hasInsights(operation) && (
                                    <button
                                      onClick={() => handleShowInsights(operation.operation_id || operation.id)}
                                      className="inline-flex items-center text-purple-600 hover:text-purple-700 dark:text-purple-400 dark:hover:text-purple-300 transition-colors duration-150"
                                    >
                                      <Lightbulb className="h-4 w-4 mr-1" />
                                      AI Insights
                                    </button>
                                  )}
                                  <button
                                    onClick={() => onShowLogs && onShowLogs(operation.request_id || operation.operation_id || operation.id)}
                                    className="inline-flex items-center text-gray-600 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300 transition-colors duration-150"
                                  >
                                    <FileText className="h-4 w-4 mr-1" />
                                    Show Logs
                                  </button>
                                </div>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 px-6 py-4">
          <div className="flex items-center justify-between">
            <div className="text-sm text-gray-700 dark:text-gray-300">
              Showing <span className="font-medium">{startIndex + 1}</span> to <span className="font-medium">{Math.min(startIndex + itemsPerPage, sortedOperations.length)}</span> of <span className="font-medium">{sortedOperations.length}</span> entries
            </div>
            <div className="flex items-center space-x-2">
              <button
                onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
                disabled={currentPage === 1}
                className="flex items-center px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150"
              >
                <ChevronLeft className="h-4 w-4 mr-1" />
                Previous
              </button>
              
              <div className="flex items-center space-x-1">
                {[...Array(Math.min(totalPages, 7))].map((_, i) => {
                  let pageNum;
                  if (totalPages <= 7) {
                    pageNum = i + 1;
                  } else if (currentPage <= 4) {
                    pageNum = i + 1;
                  } else if (currentPage >= totalPages - 3) {
                    pageNum = totalPages - 6 + i;
                  } else {
                    pageNum = currentPage - 3 + i;
                  }
                  
                  return (
                    <button
                      key={pageNum}
                      onClick={() => setCurrentPage(pageNum)}
                      className={`px-3 py-2 text-sm rounded-md transition-colors duration-150 ${
                        currentPage === pageNum
                          ? 'bg-blue-600 text-white shadow-sm'
                          : 'border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                      }`}
                    >
                      {pageNum}
                    </button>
                  );
                })}
              </div>
              
              <button
                onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
                disabled={currentPage === totalPages}
                className="flex items-center px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150"
              >
                Next
                <ChevronRight className="h-4 w-4 ml-1" />
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* AI Insights Modal */}
      {showInsights && selectedOperationId && (
        <OperationInsights
          operationId={selectedOperationId}
          onClose={() => {
            setShowInsights(false);
            setSelectedOperationId(null);
          }}
        />
      )}
    </div>
  );
};

export default OperationsList; 