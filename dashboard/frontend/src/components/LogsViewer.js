import React, { useState, useEffect, useMemo, useRef } from 'react';
import { Search, Download, Filter, AlertCircle, Info, AlertTriangle, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, RefreshCw, Clock, ExternalLink, X, Eye, CheckCircle, XCircle, Calendar, FileText } from 'lucide-react';
import api from '../services/api';
import ViewHeader from './ViewHeader';

const LogsViewer = ({ logs = [], onRefresh, filterId = null, filterType = null, onNavigateToJob, onNavigateToOperation, onClearFilter }) => {
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedLevels, setSelectedLevels] = useState(['ERROR', 'WARNING', 'INFO', 'DEBUG']);
  const [selectedOperationType, setSelectedOperationType] = useState('all');
  const [selectedRepository, setSelectedRepository] = useState('all');
  const [showSystemLogs, setShowSystemLogs] = useState(true);
  const [expandedLogs, setExpandedLogs] = useState(new Set());
  const [expandedMessages, setExpandedMessages] = useState(new Set());
  const [currentPage, setCurrentPage] = useState(1);
  const [repositories, setRepositories] = useState([]);
  const [operationTypes, setOperationTypes] = useState([]);
  const [dateRange, setDateRange] = useState({ start: '', end: '' });
  const [showExportDropdown, setShowExportDropdown] = useState(false);
  const [showFilters, setShowFilters] = useState(false);
  const exportDropdownRef = useRef(null);
  const itemsPerPage = 30;

  // Handle external filtering (from JobsList component)
  useEffect(() => {
    if (filterId && filterType) {
      if (filterType === 'job') {
        setSelectedOperationType('all');
      } else if (filterType === 'operation') {
        // For operation filtering from JobsList, we need to filter by the specific operation_id
        // We'll add a separate operationIdFilter for this case
        setSelectedOperationType('all');
      }
      setSelectedRepository('all');
      setCurrentPage(1);
    }
  }, [filterId, filterType]);

  // Listen for operation filtering events from other components (legacy support)
  useEffect(() => {
    const handleFilterByOperation = (event) => {
      const { operationId } = event.detail;
      setSelectedOperationType('all');
      setSelectedRepository('all');
      setCurrentPage(1);
    };

    window.addEventListener('filterLogsByOperation', handleFilterByOperation);
    return () => window.removeEventListener('filterLogsByOperation', handleFilterByOperation);
  }, []);

  // Handle clicks outside export dropdown
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (exportDropdownRef.current && !exportDropdownRef.current.contains(event.target)) {
        setShowExportDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  // Fetch repository names for filtering
  useEffect(() => {
    // Temporarily disable repository names API call due to 422 errors
    // TODO: Fix the /api/repositories/names endpoint
    /*
    const fetchRepositoryNames = async () => {
      try {
        const response = await api.getRepositoryNames({ active_only: false });
        const names = response.data.data || [];
        setRepositories(names);
      } catch (error) {
        console.error('Failed to fetch repository names:', error);
      }
    };
    
    fetchRepositoryNames();
    */
  }, []);

  // Also extract unique repo names from logs as fallback
  const uniqueRepoNames = [...new Set(logs.map(log => log.repo).filter(Boolean))];
  const allRepoNames = [...new Set([...repositories, ...uniqueRepoNames])];

  // Extract unique operation types from logs
  const uniqueOperationTypes = [...new Set(logs.map(log => log.command).filter(Boolean))];
  
  // Extract unique job IDs from logs (for job filtering)
  const uniqueJobIds = [...new Set(logs.map(log => log.job_id).filter(Boolean))];

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
    const upperLevel = level.toUpperCase();
    setSelectedLevels(prev => {
      const newLevels = prev.includes(upperLevel) 
        ? prev.filter(l => l !== upperLevel)
        : [...prev, upperLevel];
      // Ensure at least one level is selected
      return newLevels.length > 0 ? newLevels : [upperLevel];
    });
    setCurrentPage(1); // Reset to first page when filter changes
  };

  // Helper function to convert local datetime to UTC for comparison
  const convertLocalToUTC = (localDateString) => {
    if (!localDateString) return null;
    // Create a date in local timezone and convert to UTC for comparison
    const localDate = new Date(localDateString);
    return localDate.toISOString();
  };

  // Sort logs in reverse chronological order and filter
  const filteredLogs = logs
    .sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp))
    .filter(log => {
      const matchesSearch = !searchTerm || 
        log.message?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        log.module?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        log.function?.toLowerCase().includes(searchTerm.toLowerCase());
      
      const matchesLevel = selectedLevels.includes(log.level?.toUpperCase());
      
      // Repository filter
      const matchesRepo = selectedRepository === 'all' || log.repo === selectedRepository;
      
      // Operation type filter - using command field for operation type
      const matchesOperationType = selectedOperationType === 'all' || log.command === selectedOperationType;
      
      // External operation filter - when filtering by specific operation_id from JobsList
      const matchesExternalOperation = !(filterId && filterType === 'operation') || 
                                      log.operation_id === filterId;
      
      // Job filter - when filtering by specific job_id from JobsList
      const matchesJob = !(filterId && filterType === 'job') || log.job_id === filterId;
      
      // Date range filter (logs are stored in UTC, convert local input to UTC for comparison)
      let matchesDateRange = true;
      if (dateRange.start || dateRange.end) {
        const logDate = new Date(log.timestamp);
        if (dateRange.start) {
          const startUTC = convertLocalToUTC(dateRange.start);
          if (startUTC && logDate < new Date(startUTC)) {
            matchesDateRange = false;
          }
        }
        if (dateRange.end && matchesDateRange) {
          // Add 23:59:59 to end date to include the entire day
          const endDate = new Date(dateRange.end);
          endDate.setHours(23, 59, 59, 999);
          const endUTC = endDate.toISOString();
          if (logDate > new Date(endUTC)) {
            matchesDateRange = false;
          }
        }
      }
      
      // System logs filter - include all system sources and message prefixes
      const isSystemLog = log.source === 'notification_system' || 
                         log.source === 'retention_system' || 
                         log.source === 'health_system' || 
                         log.message?.includes('[NOTIFICATION]') ||
                         log.message?.includes('[RETENTION]') ||
                         log.message?.includes('[HEALTH]') ||
                         log.message?.includes('[SYSTEM]');
      const matchesSystemLogFilter = showSystemLogs || !isSystemLog;
      
      return matchesSearch && matchesLevel && matchesRepo && matchesOperationType && matchesExternalOperation && matchesJob && matchesDateRange && matchesSystemLogFilter;
    });

  // Pagination
  const totalPages = Math.ceil(filteredLogs.length / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedLogs = filteredLogs.slice(startIndex, startIndex + itemsPerPage);

  // Helper to escape CSV fields
  const escapeCsvField = (field) => {
    if (field === null || field === undefined) return '';
    const str = String(field);
    // If field contains comma, newline, or quote, wrap in quotes and escape internal quotes
    if (str.includes(',') || str.includes('\n') || str.includes('"')) {
      return `"${str.replace(/"/g, '""')}"`;
    }
    return str;
  };

  // Helper to convert UTC timestamp to local time string
  const formatTimestampForExport = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  // Check if any filters are active
  const hasActiveFilters = () => {
    const allLevels = ['ERROR', 'WARNING', 'INFO', 'DEBUG'];
    return (
      searchTerm ||
      selectedLevels.length !== allLevels.length || !allLevels.every(level => selectedLevels.includes(level)) ||
      selectedOperationType !== 'all' ||
      selectedRepository !== 'all' ||
      dateRange.start ||
      dateRange.end ||
      (filterId && filterType)
    );
  };

  // Export logs as CSV
  const exportLogsToCSV = (useFilteredLogs = true) => {
    const logsToExport = useFilteredLogs ? filteredLogs : logs.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
    
    // CSV headers
    const headers = [
      'Timestamp (Local)',
      'Level',
      'Message',
      'Module',
      'Function',
      'Job ID',
      'Operation ID',
      'Repository',
      'Command',
      'Status',
      'PR URL',
      'Thread',
      'Line Number'
    ];

    // Convert logs to CSV rows
    const csvRows = [
      headers.join(','),
      ...logsToExport.map(log => [
        escapeCsvField(formatTimestampForExport(log.timestamp)),
        escapeCsvField(log.level),
        escapeCsvField(log.message),
        escapeCsvField(log.module),
        escapeCsvField(log.function),
        escapeCsvField(log.job_id),
        escapeCsvField(log.operation_id),
        escapeCsvField(log.repo),
        escapeCsvField(log.command),
        escapeCsvField(log.status),
        escapeCsvField(log.pr_url),
        escapeCsvField(log.thread),
        escapeCsvField(log.line_number)
      ].join(','))
    ];

    const csvContent = csvRows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    
    const filterSuffix = useFilteredLogs && hasActiveFilters() ? '-filtered' : '';
    const timestamp = new Date().toISOString().split('T')[0];
    a.download = `pr-agent-logs${filterSuffix}-${timestamp}.csv`;
    
    a.click();
    URL.revokeObjectURL(url);
    setShowExportDropdown(false);
  };

  const formatTimestamp = (timestamp) => {
    return new Date(timestamp).toLocaleString();
  };

  const toggleExpanded = (logId) => {
    setExpandedLogs(prev => {
      const newExpandedLogs = new Set();
      if (!prev.has(logId)) {
        // Only expand this log, collapse all others
        newExpandedLogs.add(logId);
      }
      // If logId was already expanded, return empty set (collapse all)
      return newExpandedLogs;
    });
  };

  const toggleMessageExpanded = (logId) => {
    setExpandedMessages(prev => {
      const newExpandedMessages = new Set(prev);
      if (newExpandedMessages.has(logId)) {
        newExpandedMessages.delete(logId);
      } else {
        newExpandedMessages.add(logId);
      }
      return newExpandedMessages;
    });
  };

  // Helper function to determine if a message should be collapsible
  const shouldCollapseMessage = (message) => {
    if (!message) return false;
    // Count newlines
    const lines = message.split('\n');
    if (lines.length > 5) return true;
    
    // Estimate rendered lines based on character count (assuming ~80 chars per line)
    const estimatedLines = lines.reduce((total, line) => {
      return total + Math.max(1, Math.ceil(line.length / 80));
    }, 0);
    
    return estimatedLines > 5;
  };

  // Helper function to truncate message for preview
  const getTruncatedMessage = (message) => {
    if (!message) return '';
    const lines = message.split('\n');
    
    if (lines.length <= 5) {
      // If line count is okay, check character-based truncation
      const truncateLength = 400; // ~5 lines worth of characters
      if (message.length <= truncateLength) return message;
      return message.substring(0, truncateLength) + '...';
    }
    
    // Take first 4 lines and add truncation indicator
    return lines.slice(0, 4).join('\n') + '\n...';
  };

  const logLevels = [
    { key: 'error', label: 'Error', color: 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400' },
    { key: 'warning', label: 'Warning', color: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400' },
    { key: 'info', label: 'Info', color: 'bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400' },
    { key: 'debug', label: 'Debug', color: 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-400' }
  ];

  // Get active filter summary for display
  const getActiveFilterSummary = () => {
    const filters = [];
    
    if (searchTerm) {
      filters.push(`Search: "${searchTerm}"`);
    }
    
    const allLevels = ['ERROR', 'WARNING', 'INFO', 'DEBUG'];
    if (selectedLevels.length !== allLevels.length || !allLevels.every(level => selectedLevels.includes(level))) {
      filters.push(`Levels: ${selectedLevels.join(', ')}`);
    }
    
    if (selectedOperationType !== 'all') {
      filters.push(`Operation: ${selectedOperationType}`);
    }
    
    if (selectedRepository !== 'all') {
      filters.push(`Repository: ${selectedRepository.split('/').pop()}`);
    }
    
    if (dateRange.start || dateRange.end) {
      const dateFilter = [];
      if (dateRange.start) dateFilter.push(`From: ${new Date(dateRange.start).toLocaleDateString()}`);
      if (dateRange.end) dateFilter.push(`To: ${new Date(dateRange.end).toLocaleDateString()}`);
      filters.push(`Date: ${dateFilter.join(' - ')}`);
    }
    
    if (filterId && filterType) {
      filters.push(`${filterType === 'job' ? 'Job' : 'Operation'}: ${filterId.substring(0, 8)}...`);
    }
    
    if (!showSystemLogs) {
      filters.push('Hiding system logs');
    }
    
    return filters;
  };

  // Clear all filters function
  const clearAllFilters = (event) => {
    event.stopPropagation(); // Prevent filter card from toggling
    setSelectedLevels(['ERROR', 'WARNING', 'INFO', 'DEBUG']);
    setSelectedOperationType('all');
    setSelectedRepository('all');
    setShowSystemLogs(true);
    setDateRange({ start: '', end: '' });
    setSearchTerm('');
    setCurrentPage(1);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <ViewHeader 
        title={`Logs (${filteredLogs.length} entries)`}
        subtitle="View and filter system logs from PR operations"
        icon={FileText}
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

            {/* Export button/dropdown */}
            <div className="relative" ref={exportDropdownRef}>
              {hasActiveFilters() ? (
                <>
                  <button
                    onClick={() => setShowExportDropdown(!showExportDropdown)}
                    className="flex items-center px-3 py-2 text-sm bg-gray-600 text-white rounded-md hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:bg-gray-700 dark:hover:bg-gray-600"
                  >
                    <Download className="h-4 w-4 mr-1" />
                    Export
                    <ChevronDown className="h-4 w-4 ml-1" />
                  </button>
                  
                  {showExportDropdown && (
                    <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-gray-800 rounded-md shadow-lg border border-gray-200 dark:border-gray-700 z-50">
                      <div className="py-1">
                        <button
                          onClick={() => exportLogsToCSV(true)}
                          className="flex items-center w-full px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                        >
                          <Download className="h-4 w-4 mr-2" />
                          <div className="text-left">
                            <div className="font-medium">Current Filtered Logs</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">
                              Export {filteredLogs.length} filtered entries
                            </div>
                          </div>
                        </button>
                        <button
                          onClick={() => exportLogsToCSV(false)}
                          className="flex items-center w-full px-4 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700"
                        >
                          <Download className="h-4 w-4 mr-2" />
                          <div className="text-left">
                            <div className="font-medium">All Logs</div>
                            <div className="text-xs text-gray-500 dark:text-gray-400">
                              Export all {logs.length} entries
                            </div>
                          </div>
                        </button>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                <button
                  onClick={() => exportLogsToCSV(true)}
                  className="flex items-center px-3 py-2 text-sm bg-gray-600 text-white rounded-md hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500 dark:bg-gray-700 dark:hover:bg-gray-600"
                >
                  <Download className="h-4 w-4 mr-1" />
                  Export CSV
                </button>
              )}
            </div>
          </div>
        }
      />

      {/* Job/Operation Filter Alert - Show when filtered externally */}
      {(filterId && filterType) && (
        <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border-2 border-blue-200 dark:border-blue-700 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                <Filter className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-200">
                  {filterType === 'job' ? 'Job-Filtered View' : 'Operation-Filtered View'}
                </h3>
                <p className="text-sm text-blue-700 dark:text-blue-300">
                  Showing logs for {filterType}: 
                  <span className="font-mono font-semibold ml-1">
                    {filterType === 'job' ? filterId : filterId.substring(0, 12) + '...'}
                  </span>
                </p>
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-1">
                  Only logs related to this specific {filterType} are displayed
                </p>
              </div>
            </div>
            <button
              onClick={() => {
                // Clear local filters
                setSelectedOperationType('all');
                setSelectedRepository('all');
                setDateRange({ start: '', end: '' });
                setCurrentPage(1);
                
                // Clear external filter by notifying parent
                if (onClearFilter) {
                  onClearFilter();
                }
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
      <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/10 dark:to-indigo-900/10 rounded-xl border border-blue-200 dark:border-blue-700 shadow-sm max-w-none mx-auto" style={{width: '90%'}}>
        {/* Filter Header */}
        <div
          className="p-5 cursor-pointer hover:bg-blue-100/50 dark:hover:bg-blue-900/20 transition-colors rounded-t-xl"
          onClick={() => setShowFilters(!showFilters)}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center space-x-3">
              <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                <Filter className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              </div>
              <div>
                <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100">Filter Logs</h3>
                <p className="text-sm text-blue-700 dark:text-blue-300">Filter by level, date, repository, or operation type</p>
              </div>
            </div>
            
            <div className="flex items-center space-x-4">
              {/* Active filter summary */}
              <div className="flex-1">
                {(() => {
                  const activeFilters = getActiveFilterSummary();
                  if (activeFilters.length === 0) {
                    return (
                      <span className="text-sm text-blue-600 dark:text-blue-400 font-medium">
                        No active filters
                      </span>
                    );
                  }
                  return (
                    <div className="flex flex-wrap gap-2 justify-end">
                      {activeFilters.slice(0, 2).map((filter, index) => (
                        <span
                          key={index}
                          className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-blue-200 text-blue-800 dark:bg-blue-800/40 dark:text-blue-200 border border-blue-300 dark:border-blue-600"
                        >
                          {filter}
                        </span>
                      ))}
                      {activeFilters.length > 2 && (
                        <span className="text-sm text-blue-700 dark:text-blue-300 font-medium">
                          +{activeFilters.length - 2} more
                        </span>
                      )}
                    </div>
                  );
                })()}
              </div>

              {/* Clear All Filters Button */}
              {hasActiveFilters() && (
                <button
                  onClick={clearAllFilters}
                  className="px-4 py-2 text-sm text-blue-700 dark:text-blue-300 hover:text-blue-900 dark:hover:text-blue-100 hover:bg-blue-200 dark:hover:bg-blue-800/30 rounded-lg transition-colors flex items-center space-x-2 font-medium border border-blue-300 dark:border-blue-600"
                  title="Clear all filters"
                >
                  <X className="h-4 w-4" />
                  <span>Clear All</span>
                </button>
              )}

              {/* Chevron */}
              {showFilters ? (
                <ChevronUp className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              ) : (
                <ChevronDown className="h-5 w-5 text-blue-600 dark:text-blue-400" />
              )}
            </div>
          </div>
        </div>

        {/* Expandable Filter Content */}
        {showFilters && (
          <div className="border-t border-blue-200 dark:border-blue-700 bg-white/50 dark:bg-gray-800/50 p-6 space-y-6 animate-slideDown rounded-b-xl">
            {/* Level Filter Toggles */}
            <div>
              <label className="block text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">
                Log Levels
              </label>
              <div className="flex flex-wrap gap-2">
                {logLevels.map(level => (
                  <button
                    key={level.key}
                    onClick={() => toggleLevel(level.key)}
                                          className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                      selectedLevels.includes(level.key.toUpperCase())
                        ? level.color + ' shadow-md scale-105'
                        : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 border border-gray-200 dark:border-gray-600 hover:border-blue-300 dark:hover:border-blue-500'
                    }`}
                  >
                    {level.label}
                  </button>
                ))}
              </div>
            </div>

            {/* System Logs Toggle */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                Log Types
              </label>
              <div className="flex items-center space-x-4">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    checked={showSystemLogs}
                    onChange={(e) => {
                      setShowSystemLogs(e.target.checked);
                      setCurrentPage(1);
                    }}
                    className="mr-2 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
                  />
                  <span className="text-sm text-gray-700 dark:text-gray-300">Show system logs</span>
                  <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400 ml-2">
                    <svg className="h-3 w-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
                      <path d="M10 2L15.09 8.26L22 9L16 14.74L17.18 21.02L10 17.77L2.82 21.02L4 14.74L-2 9L4.91 8.26L10 2Z"/>
                    </svg>
                    System
                  </span>
                </label>
              </div>
            </div>

            {/* Date Range Filter */}
            <div>
              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                <Calendar className="inline h-4 w-4 mr-1" />
                Date Range (Local Time)
              </label>
              <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center space-x-2">
                  <label className="text-xs text-gray-500 dark:text-gray-400">From:</label>
                  <input
                    type="datetime-local"
                    value={dateRange.start}
                    onChange={(e) => {
                      setDateRange(prev => ({ ...prev, start: e.target.value }));
                      setCurrentPage(1);
                    }}
                    className="px-3 py-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                <div className="flex items-center space-x-2">
                  <label className="text-xs text-gray-500 dark:text-gray-400">To:</label>
                  <input
                    type="datetime-local"
                    value={dateRange.end}
                    onChange={(e) => {
                      setDateRange(prev => ({ ...prev, end: e.target.value }));
                      setCurrentPage(1);
                    }}
                    className="px-3 py-1 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />
                </div>
                {(dateRange.start || dateRange.end) && (
                  <button
                    onClick={() => {
                      setDateRange({ start: '', end: '' });
                      setCurrentPage(1);
                    }}
                    className="px-2 py-1 text-xs bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400 rounded hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>

            {/* Repository Filter */}
            {allRepoNames.length > 0 && (
              <div>
                <label className="block text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">
                  Repository
                </label>
                <div className="flex flex-wrap gap-2">
                  {['all', ...allRepoNames].map((repo) => (
                    <button
                      key={repo}
                      onClick={() => {
                        setSelectedRepository(repo);
                        setCurrentPage(1);
                      }}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                        selectedRepository === repo
                          ? 'bg-blue-600 text-white shadow-md scale-105'
                          : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 border border-gray-200 dark:border-gray-600 hover:border-blue-300 dark:hover:border-blue-500'
                      }`}
                    >
                      {repo === 'all' ? 'All Repositories' : repo.split('/').pop()}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Operation Type Filter */}
            {uniqueOperationTypes.length > 0 && (
              <div>
                <label className="block text-sm font-semibold text-gray-800 dark:text-gray-200 mb-3">
                  Operation Type
                </label>
                <div className="flex flex-wrap gap-2">
                  {['all', ...uniqueOperationTypes].map((opType) => (
                    <button
                      key={opType}
                      onClick={() => {
                        setSelectedOperationType(opType);
                        setCurrentPage(1);
                      }}
                      className={`px-4 py-2 rounded-lg text-sm font-medium transition-all duration-200 ${
                        selectedOperationType === opType
                          ? 'bg-blue-600 text-white shadow-md scale-105'
                          : 'bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600 border border-gray-200 dark:border-gray-600 hover:border-blue-300 dark:hover:border-blue-500'
                      }`}
                    >
                      {opType === 'all' ? 'All Operations' : opType.charAt(0).toUpperCase() + opType.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Logs table */}
      <div className="bg-white dark:bg-gray-800 shadow-sm border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
        {paginatedLogs.length === 0 ? (
          <div className="p-8 text-center text-gray-500 dark:text-gray-400">
            {filteredLogs.length === 0 ? 'No logs found' : 'No logs on this page'}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full table-fixed">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <th className="w-24 px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Level
                  </th>
                  <th className="w-40 px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Timestamp
                  </th>
                  <th className="flex-1 px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Message
                  </th>
                  <th className="w-72 px-4 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Source
                  </th>
                  <th className="w-12 px-4 py-3 text-right"></th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800">
                {paginatedLogs.map((log, index) => {
                  const LevelIcon = getLevelIcon(log.level);
                  const logId = log.id || `${index}-${log.timestamp}`;
                  const isExpanded = expandedLogs.has(logId);
                  
                  return (
                    <React.Fragment key={logId}>
                      {/* Main log row */}
                      <tr 
                        className={`border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-all duration-200 ease-in-out cursor-pointer ${
                          isExpanded ? 'bg-blue-50 dark:bg-blue-900/10' : ''
                        }`}
                        onClick={() => toggleExpanded(logId)}
                      >
                        <td className="w-24 px-4 py-4 whitespace-nowrap">
                          <div className="flex items-center">
                            <LevelIcon className="h-4 w-4 mr-2 text-gray-400 dark:text-gray-500" />
                            <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${getLevelColor(log.level)}`}>
                              {log.level?.toUpperCase()}
                            </span>
                          </div>
                        </td>
                        <td className="w-40 px-4 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          <div className="flex items-center">
                            <Clock className="h-3 w-3 mr-1" />
                            {formatTimestamp(log.timestamp)}
                          </div>
                        </td>
                        <td className="flex-1 px-4 py-4 text-sm text-gray-900 dark:text-white">
                          <div className="truncate" title={log.message}>
                            {log.message}
                          </div>
                        </td>
                        <td className="w-72 px-4 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          <div className="truncate">
                            {log.module && <div className="font-medium truncate" title={log.module}>{log.module}</div>}
                            {log.function && <div className="text-xs text-gray-400 dark:text-gray-500 truncate" title={log.function}>{log.function}()</div>}
                          </div>
                        </td>
                        <td className="w-12 px-4 py-4 whitespace-nowrap text-sm">
                          <div className="flex justify-end">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                toggleExpanded(logId);
                              }}
                              className="flex items-center justify-center text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 transition-colors duration-200 p-1 rounded hover:bg-blue-50 dark:hover:bg-blue-900/20"
                            >
                              {isExpanded ? (
                                <ChevronUp className="h-4 w-4" />
                              ) : (
                                <ChevronDown className="h-4 w-4" />
                              )}
                            </button>
                          </div>
                        </td>
                      </tr>
                      
                      {/* Expanded details row with animation */}
                      {isExpanded && (
                        <tr className="bg-blue-50 dark:bg-blue-900/10 border-b border-blue-200 dark:border-blue-800">
                          <td colSpan="5" className="px-6 py-0">
                            <div className="overflow-hidden">
                              <div className="bg-white dark:bg-gray-800 rounded-lg border border-blue-200 dark:border-blue-700 p-6 my-4 transform animate-expand">
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
                                      {shouldCollapseMessage(log.message) ? (
                                        <div>
                                          <div className="whitespace-pre-wrap">
                                            {expandedMessages.has(logId) ? log.message : getTruncatedMessage(log.message)}
                                          </div>
                                          <button
                                            onClick={() => toggleMessageExpanded(logId)}
                                            className="mt-2 text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 text-sm font-medium flex items-center transition-colors"
                                          >
                                            {expandedMessages.has(logId) ? (
                                              <>
                                                <ChevronUp className="h-4 w-4 mr-1" />
                                                Show Less
                                              </>
                                            ) : (
                                              <>
                                                <ChevronDown className="h-4 w-4 mr-1" />
                                                Show More
                                              </>
                                            )}
                                          </button>
                                        </div>
                                      ) : (
                                        <div className="whitespace-pre-wrap">{log.message}</div>
                                      )}
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
                                  
                                  <div>
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                      Context Information
                                    </label>
                                    <div className="bg-gray-50 dark:bg-gray-700 rounded-md p-3 space-y-2">
                                      {/* Always show job and operation links when available */}
                                      {log.job_id && (
                                        <div className="flex items-center text-sm">
                                          <span className="font-medium text-gray-600 dark:text-gray-400 w-20">Job:</span>
                                          <button
                                            onClick={() => onNavigateToJob && onNavigateToJob(log.job_id)}
                                            className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 hover:underline font-mono text-sm flex items-center transition-colors"
                                          >
                                            {log.job_id}
                                            <ExternalLink className="h-3 w-3 ml-1" />
                                          </button>
                                        </div>
                                      )}
                                      {log.operation_id && (
                                        <div className="flex items-center text-sm">
                                          <span className="font-medium text-gray-600 dark:text-gray-400 w-20">Operation:</span>
                                          <button
                                            onClick={() => onNavigateToOperation && onNavigateToOperation(log.job_id, log.operation_id)}
                                            className="text-blue-600 dark:text-blue-400 hover:text-blue-700 dark:hover:text-blue-300 hover:underline font-mono text-sm flex items-center transition-colors"
                                          >
                                            {log.operation_id}
                                            <ExternalLink className="h-3 w-3 ml-1" />
                                          </button>
                                        </div>
                                      )}
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
                                      {/* Show a message if no context information is available */}
                                      {!log.job_id && !log.operation_id && !log.repo && !log.command && !log.pr_url && (
                                        <div className="flex items-center text-sm">
                                          {(log.source === 'notification_system' || 
                                            log.source === 'retention_system' || 
                                            log.source === 'health_system' || 
                                            log.source === 'dashboard_backend' || 
                                            log.message?.includes('[NOTIFICATION]') ||
                                            log.message?.includes('[RETENTION]') ||
                                            log.message?.includes('[HEALTH]') ||
                                            log.message?.includes('[SYSTEM]')) ? (
                                            <>
                                              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/20 dark:text-blue-400 mr-2">
                                                <svg className="h-3 w-3 mr-1" fill="currentColor" viewBox="0 0 20 20">
                                                  <path d="M10 2L15.09 8.26L22 9L16 14.74L17.18 21.02L10 17.77L2.82 21.02L4 14.74L-2 9L4.91 8.26L10 2Z"/>
                                                </svg>
                                                System Log
                                              </span>
                                              <span className="text-gray-500 dark:text-gray-400 italic">
                                                {log.source === 'notification_system' || log.message?.includes('[NOTIFICATION]') ? 'Notification system event' :
                                                 log.source === 'retention_system' || log.message?.includes('[RETENTION]') ? 'Backup & retention system event' :
                                                 log.source === 'health_system' || log.message?.includes('[HEALTH]') ? 'Health monitoring system event' :
                                                 log.source === 'dashboard_backend' || log.message?.includes('[SYSTEM]') ? 'Dashboard backend system event' :
                                                 'System event'}
                                              </span>
                                            </>
                                          ) : (
                                            <span className="text-gray-500 dark:text-gray-400 italic">
                                              No context information available
                                            </span>
                                          )}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                  
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