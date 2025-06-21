import React, { useState, useEffect } from 'react';
import { Search, Download, Filter, AlertCircle, Info, AlertTriangle, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, RefreshCw, Clock, ExternalLink, X, Eye } from 'lucide-react';
import api from '../services/api';
import ViewHeader from './ViewHeader';

const LogsViewer = ({ logs = [], onRefresh }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLevels, setSelectedLevels] = useState(['error', 'warning', 'info', 'debug']);
  const [repoFilter, setRepoFilter] = useState('all');
  const [operationFilter, setOperationFilter] = useState('all');
  const [repositoryNames, setRepositoryNames] = useState([]);
  const [currentPage, setCurrentPage] = useState(1);
  const [expandedLogId, setExpandedLogId] = useState(null);
  const [operationFilterSource, setOperationFilterSource] = useState(null); // 'manual' or 'external'
  const itemsPerPage = 25;

  // Listen for operation filtering events from other components
  useEffect(() => {
    const handleFilterByOperation = (event) => {
      const { operationId } = event.detail;
      setOperationFilter(operationId);
      setOperationFilterSource('external');
      setCurrentPage(1);
    };

    window.addEventListener('filterLogsByOperation', handleFilterByOperation);
    return () => window.removeEventListener('filterLogsByOperation', handleFilterByOperation);
  }, []);

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

  // Also extract unique repo names from logs as fallback
  const uniqueRepoNames = [...new Set(logs.map(log => log.repo).filter(Boolean))];
  const allRepoNames = [...new Set([...repositoryNames, ...uniqueRepoNames])];

  // Extract unique request IDs from logs (for operation filtering)
  const uniqueOperationIds = [...new Set(logs.map(log => log.request_id).filter(Boolean))];

  const getLevelColor = (level) => {
    switch (level?.toLowerCase()) {
      case 'error': return 'text-red-600 bg-red-50 dark:text-red-400 dark:bg-red-900/20';
      case 'warning': return 'text-yellow-600 bg-yellow-50 dark:text-yellow-400 dark:bg-yellow-900/20';
      case 'info': return 'text-blue-600 bg-blue-50 dark:text-blue-400 dark:bg-blue-900/20';
      case 'debug': return 'text-gray-600 bg-gray-50 dark:text-gray-400 dark:bg-gray-800';
      default: return 'text-gray-600 bg-gray-50 dark:text-gray-400 dark:bg-gray-800';
    }
  };

  const getLevelIcon = (level) => {
    switch (level?.toLowerCase()) {
      case 'error': return AlertCircle;
      case 'warning': return AlertTriangle;
      case 'info': return Info;
      default: return Info;
    }
  };

  const toggleLevel = (level) => {
    setSelectedLevels(prev => {
      const newLevels = prev.includes(level) 
        ? prev.filter(l => l !== level)
        : [...prev, level];
      // Ensure at least one level is selected
      return newLevels.length > 0 ? newLevels : [level];
    });
    setCurrentPage(1); // Reset to first page when filter changes
  };

  // Sort logs in reverse chronological order and filter
  const filteredLogs = logs
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .filter(log => {
      const matchesSearch = !searchTerm || 
        log.message?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        log.module?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        log.function?.toLowerCase().includes(searchTerm.toLowerCase());
      
      const matchesLevel = selectedLevels.includes(log.level?.toLowerCase());
      
      // Repository filter
      const matchesRepo = repoFilter === 'all' || log.repo === repoFilter;
      
      // Operation filter - using request_id since that's how logs are linked to operations
      const matchesOperation = operationFilter === 'all' || log.request_id === operationFilter;
      
      return matchesSearch && matchesLevel && matchesRepo && matchesOperation;
    });

  // Pagination
  const totalPages = Math.ceil(filteredLogs.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedLogs = filteredLogs.slice(startIndex, startIndex + itemsPerPage);

  const exportLogs = () => {
    const logsText = filteredLogs.map(log => 
      `[${log.timestamp}] ${log.level} - ${log.message}`
    ).join('\n');
    
    const blob = new Blob([logsText], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `pr-agent-logs-${new Date().toISOString().split('T')[0]}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  const toggleExpanded = (logId) => {
    setExpandedLogId(prev => prev === logId ? null : logId);
  };

  const logLevels = [
    { key: 'error', label: 'Error', color: 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400' },
    { key: 'warning', label: 'Warning', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400' },
    { key: 'info', label: 'Info', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400' },
    { key: 'debug', label: 'Debug', color: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-400' }
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <ViewHeader 
        title={`Logs (${filteredLogs.length} entries)`}
        subtitle="View and filter system logs from PR operations"
        icon={Eye}
        onRefresh={onRefresh}
        rightComponent={
          <div className="flex items-center space-x-3">
            {/* Search */}
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400 dark:text-gray-500" />
              <input
                type="text"
                placeholder="Search logs..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(1);
                }}
                className="pl-10 pr-4 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>

            {/* Export button */}
            <button
              onClick={exportLogs}
              className="flex items-center px-3 py-2 text-sm bg-gray-600 text-white rounded-md hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:bg-gray-700 dark:hover:bg-gray-600"
            >
              <Download className="h-4 w-4 mr-1" />
              Export
            </button>
          </div>
        }
      />

      {/* Operation Filter Alert - Show when filtered externally */}
      {operationFilter !== 'all' && operationFilterSource === 'external' && (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border-2 border-blue-200 dark:border-blue-700 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                <Filter className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-200">
                  Operation-Filtered View
                </h3>
                <p className="text-sm text-blue-700 dark:text-blue-300">
                  Showing logs for operation: <span className="font-mono font-semibold">{operationFilter}</span>
                </p>
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                  Only logs related to this specific operation are displayed
                </p>
              </div>
            </div>
            <button
              onClick={() => {
                setOperationFilter('all');
                setOperationFilterSource(null);
                setCurrentPage(1);
              }}
              className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors duration-200 shadow-sm"
            >
              <X className="h-4 w-4 mr-2" />
              Clear Filter
            </button>
          </div>
        </div>
      )}

      {/* Filters */}
      <div className="flex flex-col space-y-4">

        {/* Level Filter Toggles */}
        <div className="flex items-center space-x-2">
          <Filter className="h-4 w-4 text-gray-400 dark:text-gray-500" />
          <span className="text-sm text-gray-600 dark:text-gray-400">Levels:</span>
          <div className="flex flex-wrap gap-2">
            {logLevels.map(level => (
              <button
                key={level.key}
                onClick={() => toggleLevel(level.key)}
                className={`px-3 py-1 rounded-full text-xs font-medium transition-all duration-200 ${
                  selectedLevels.includes(level.key)
                    ? level.color + ' ring-2 ring-offset-1 ring-blue-500 dark:ring-offset-gray-800'
                    : 'bg-gray-200 text-gray-600 dark:bg-gray-700 dark:text-gray-400 hover:bg-gray-300 dark:hover:bg-gray-600'
                }`}
              >
                {level.label}
              </button>
            ))}
          </div>
        </div>

        {/* Repository and Operation Filters */}
        <div className="flex flex-col sm:flex-row sm:items-center space-y-2 sm:space-y-0 sm:space-x-6">
          <div className="flex items-center space-x-2">
            <Filter className="h-4 w-4 text-gray-400 dark:text-gray-500" />
            <span className="text-sm text-gray-600 dark:text-gray-400">Repository:</span>
            <select
              value={repoFilter}
              onChange={(e) => {
                setRepoFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value="all">All Repositories</option>
              {allRepoNames.map(repo => (
                <option key={repo} value={repo}>{repo}</option>
              ))}
            </select>
          </div>
          
          <div className="flex items-center space-x-2">
            <span className="text-sm text-gray-600 dark:text-gray-400">Operation:</span>
            <select
              value={operationFilter}
              onChange={(e) => {
                setOperationFilter(e.target.value);
                setOperationFilterSource(e.target.value === 'all' ? null : 'manual');
                setCurrentPage(1);
              }}
              disabled={operationFilterSource === 'external'}
              className={`border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 ${
                operationFilterSource === 'external' ? 'opacity-50 cursor-not-allowed' : ''
              }`}
            >
              <option value="all">All Operations</option>
              {uniqueOperationIds.map(opId => (
                <option key={opId} value={opId}>{opId}</option>
              ))}
            </select>
            {operationFilter !== 'all' && operationFilterSource === 'manual' && (
              <button
                onClick={() => {
                  setOperationFilter('all');
                  setOperationFilterSource(null);
                  setCurrentPage(1);
                }}
                className="text-xs text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
              >
                Clear
              </button>
            )}
            {operationFilterSource === 'external' && (
              <span className="text-xs text-gray-500 dark:text-gray-400 italic">
                (filtered by operation view)
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Logs table */}
      <div className="bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        {paginatedLogs.length === 0 ? (
          <div className="p-8 text-center text-gray-500 dark:text-gray-400">
            {filteredLogs.length === 0 ? 'No logs found' : 'No logs on this page'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Level
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Timestamp
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Message
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Source
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800">
                {paginatedLogs.map((log, index) => {
                  const LevelIcon = getLevelIcon(log.level);
                  const logId = log.id || `${index}-${log.timestamp}`;
                  const isExpanded = expandedLogId === logId;
                  
                  return (
                    <React.Fragment key={logId}>
                      {/* Main log row */}
                      <tr 
                        className={`border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-200 cursor-pointer ${isExpanded ? 'bg-blue-50 dark:bg-blue-900/10' : ''}`}
                        onClick={() => toggleExpanded(logId)}
                      >
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <LevelIcon className="h-4 w-4 mr-2 text-gray-400 dark:text-gray-500" />
                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getLevelColor(log.level)}`}>
                              {log.level?.toUpperCase()}
                            </span>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          <div className="flex items-center">
                            <Clock className="h-3 w-3 mr-1" />
                            {formatTimestamp(log.timestamp)}
                          </div>
                        </td>
                        <td className="px-6 py-4 text-sm text-gray-900 dark:text-white">
                          <div className="max-w-md">
                            <div className={`${isExpanded ? '' : 'truncate'}`}>
                              {log.message}
                            </div>
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          <div>
                            {log.module && <div className="font-medium">{log.module}</div>}
                            {log.function && <div className="text-xs text-gray-400 dark:text-gray-500">{log.function}()</div>}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleExpanded(logId);
                            }}
                            className="flex items-center text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 transition-colors duration-200"
                          >
                            {isExpanded ? (
                              <>
                                <ChevronUp className="h-4 w-4 mr-1" />
                                Collapse
                              </>
                            ) : (
                              <>
                                <ChevronDown className="h-4 w-4 mr-1" />
                                Expand
                              </>
                            )}
                          </button>
                        </td>
                      </tr>
                      
                      {/* Expanded details row with animation */}
                      {isExpanded && (
                        <tr className="bg-blue-50 dark:bg-blue-900/10 border-b border-blue-200 dark:border-blue-800 animate-fadeIn">
                          <td colSpan="5" className="px-6 py-0">
                            <div className="overflow-hidden">
                              <div className="bg-white dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-blue-700 p-6 my-4 transform transition-all duration-300 ease-out animate-slideDown">
                              <h4 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
                                <Info className="h-5 w-5 mr-2 text-blue-600 dark:text-blue-400" />
                                Log Details
                              </h4>
                              
                              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                                {/* Left column */}
                                <div className="space-y-4">
                                  <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                      Full Message
                                    </label>
                                    <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-3 text-sm text-gray-900 dark:text-white break-words">
                                      {log.message}
                                    </div>
                                  </div>
                                  
                                  <div className="grid grid-cols-2 gap-4">
                                    <div>
                                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Level
                                      </label>
                                      <span className={`inline-flex items-center px-2 py-1 rounded text-sm font-medium ${getLevelColor(log.level)}`}>
                                        {log.level?.toUpperCase()}
                                      </span>
                                    </div>
                                    <div>
                                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Timestamp
                                      </label>
                                      <p className="text-sm text-gray-900 dark:text-white">
                                        {formatTimestamp(log.timestamp)}
                                      </p>
                                    </div>
                                  </div>
                                  
                                  {(log.module || log.function) && (
                                    <div className="grid grid-cols-2 gap-4">
                                      {log.module && (
                                        <div>
                                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                            Module
                                          </label>
                                          <p className="text-sm text-gray-900 dark:text-white font-mono bg-gray-50 dark:bg-gray-700 px-2 py-1 rounded">
                                            {log.module}
                                          </p>
                                        </div>
                                      )}
                                      {log.function && (
                                        <div>
                                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                            Function
                                          </label>
                                          <p className="text-sm text-gray-900 dark:text-white font-mono bg-gray-50 dark:bg-gray-700 px-2 py-1 rounded">
                                            {log.function}()
                                          </p>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                </div>
                                
                                {/* Right column */}
                                <div className="space-y-4">
                                  {log.status && (
                                    <div>
                                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                                        Status
                                      </label>
                                      <span className="inline-flex items-center px-3 py-1 rounded-full text-sm bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400">
                                        {log.status.replace(/_/g, ' ')}
                                      </span>
                                    </div>
                                  )}
                                  
                                  {(log.repo || log.command || log.pr_url) && (
                                    <div>
                                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                        Context Information
                                      </label>
                                      <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-3 space-y-2">
                                        {log.repo && (
                                          <div className="flex items-center text-sm">
                                            <span className="font-medium text-gray-600 dark:text-gray-400 w-20">Repo:</span>
                                            <span className="text-gray-900 dark:text-white">{log.repo}</span>
                                          </div>
                                        )}
                                        {log.command && (
                                          <div className="flex items-center text-sm">
                                            <span className="font-medium text-gray-600 dark:text-gray-400 w-20">Command:</span>
                                            <span className="text-gray-900 dark:text-white font-mono">{log.command}</span>
                                          </div>
                                        )}
                                        {log.pr_url && (
                                          <div className="flex items-center text-sm">
                                            <span className="font-medium text-gray-600 dark:text-gray-400 w-20">PR:</span>
                                            <a 
                                              href={log.pr_url} 
                                              target="_blank" 
                                              rel="noopener noreferrer" 
                                              className="text-blue-600 dark:text-blue-400 hover:underline flex items-center"
                                            >
                                              {log.pr_url}
                                              <ExternalLink className="h-3 w-3 ml-1" />
                                            </a>
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  )}
                                  
                                  {/* Additional metadata */}
                                  <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                      Metadata
                                    </label>
                                    <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-3 text-xs font-mono text-gray-600 dark:text-gray-400">
                                      <div>ID: {logId}</div>
                                      {log.line_number && <div>Line: {log.line_number}</div>}
                                      {log.thread && <div>Thread: {log.thread}</div>}
                                    </div>
                                  </div>
                                </div>
                              </div>
                              </div>
                            </div>
                          </td>
                        </tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <div className="text-sm text-gray-700 dark:text-gray-300">
            Showing {startIndex + 1} to {Math.min(startIndex + itemsPerPage, filteredLogs.length)} of {filteredLogs.length} entries
          </div>
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
              disabled={currentPage === 1}
              className="flex items-center px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
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
                    className={`px-3 py-2 text-sm rounded-md ${
                      currentPage === pageNum
                        ? 'bg-blue-600 text-white'
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
              className="flex items-center px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 rounded-md hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
              <ChevronRight className="h-4 w-4 ml-1" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default LogsViewer; 