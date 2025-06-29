import React, { useState, useEffect, useContext, useRef } from 'react';
import { 
  Play, 
  CheckCircle, 
  XCircle, 
  Clock, 
  ChevronDown, 
  ChevronRight,
  ChevronUp,
  ExternalLink,
  AlertTriangle,
  Activity,
  Database,
  GitBranch,
  User,
  Calendar,
  Zap,
  FileText,
  RefreshCw,
  Filter,
  X,
  Brain,
  DollarSign,
  TrendingUp,
  BarChart3
} from 'lucide-react';
import api from '../services/api';
import { ToastContext } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';
import RunningIndicator from './RunningIndicator';

const JobsList = ({ onShowLogs, refreshTrigger, highlightedJobId, highlightedOperationId }) => {
  const [jobs, setJobs] = useState([]);
  const [allJobs, setAllJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedJobs, setExpandedJobs] = useState(new Set());
  const [selectedFilters, setSelectedFilters] = useState({
    status: 'running', // Default to running jobs
    jobType: 'all',
    repository: 'all'
  });
  const [currentPage, setCurrentPage] = useState(1);
  const [lastRefreshTrigger, setLastRefreshTrigger] = useState(null);
  const { showError } = useContext(ToastContext);
  const highlightedJobRef = useRef(null);
  const highlightedOperationRef = useRef(null);

  const jobsPerPage = 10;

  // Available status options for tabs
  const statusTabs = [
    { id: 'running', label: 'Running', icon: Play },
    { id: 'completed', label: 'Completed', icon: CheckCircle },
    { id: 'failed', label: 'Failed', icon: XCircle },
    { id: 'cancelled', label: 'Cancelled', icon: AlertTriangle },
    { id: 'all', label: 'All Jobs', icon: BarChart3 }
  ];

  // Initial data fetch
  useEffect(() => {
    fetchAllJobs();
  }, []);

  // Handle manual refresh triggers only (not automatic periodic updates)
  useEffect(() => {
    if (refreshTrigger && refreshTrigger !== lastRefreshTrigger) {
      setLastRefreshTrigger(refreshTrigger);
      fetchAllJobs();
    }
  }, [refreshTrigger, lastRefreshTrigger]);

  // Set up periodic refresh that preserves UI state
  useEffect(() => {
    const intervalId = setInterval(() => {
      fetchAllJobsPreservingState();
    }, 5000);

    return () => clearInterval(intervalId);
  }, []);

  // Client-side filtering when filters change - instant, no loading
  useEffect(() => {
    applyClientSideFilters();
  }, [selectedFilters, allJobs]);

  // Clean up expanded jobs when jobs list changes
  useEffect(() => {
    if (jobs.length > 0) {
      const currentJobIds = new Set(jobs.map(job => job.job_id));
      const validExpandedJobs = new Set();
      
      expandedJobs.forEach(jobId => {
        if (currentJobIds.has(jobId)) {
          validExpandedJobs.add(jobId);
        }
      });
      
      if (validExpandedJobs.size !== expandedJobs.size) {
        setExpandedJobs(validExpandedJobs);
      }
    }
  }, [jobs]);

  // Listen for external filter events from status cards (convert to tab selection)
  useEffect(() => {
    const handleStatusFilter = (event) => {
      const { status } = event.detail;
      setSelectedFilters(prev => ({
        ...prev,
        status: status || 'all'
      }));
      setCurrentPage(1); // Reset to first page when filtering
    };

    // Listen for job expansion events
    const handleExpandJob = (event) => {
      const { jobId } = event.detail;
      setExpandedJobs(prev => new Set([...prev, jobId]));
    };

    // Listen for real-time job updates
    const handleLiveJobUpdate = (event) => {
      const jobData = event.detail;
      setJobs(prevJobs => {
        const existingIndex = prevJobs.findIndex(job => job.job_id === jobData.job_id);
        if (existingIndex >= 0) {
          // Update existing job without changing order to prevent scrolling
          const newJobs = [...prevJobs];
          newJobs[existingIndex] = { ...newJobs[existingIndex], ...jobData };
          return newJobs;
        } else {
          // Check if new job matches current filters before adding
          const matchesCurrentFilter = selectedFilters.status === 'all' || 
            selectedFilters.status === jobData.status ||
            (selectedFilters.status === 'running' && ['running', 'pending'].includes(jobData.status));
          
          if (matchesCurrentFilter) {
            // Add new job to the beginning, but don't change current view if user is scrolled down
            return [jobData, ...prevJobs];
          }
          return prevJobs;
        }
      });
      
      // Also update allJobs for accurate tab counts
      setAllJobs(prevAllJobs => {
        const existingIndex = prevAllJobs.findIndex(job => job.job_id === jobData.job_id);
        if (existingIndex >= 0) {
          const newAllJobs = [...prevAllJobs];
          newAllJobs[existingIndex] = { ...newAllJobs[existingIndex], ...jobData };
          return newAllJobs;
        } else {
          return [jobData, ...prevAllJobs];
        }
      });
    };

    // Listen for real-time operation updates
    const handleLiveOperationUpdate = (event) => {
      const operationData = event.detail;
      setJobs(prevJobs => {
        return prevJobs.map(job => {
          if (job.job_id === operationData.job_id) {
            // Update the operations array within the job without changing job order
            const updatedOperations = job.operations ? [...job.operations] : [];
            const existingOpIndex = updatedOperations.findIndex(op => op.operation_id === operationData.operation_id);
            
            if (existingOpIndex >= 0) {
              updatedOperations[existingOpIndex] = { ...updatedOperations[existingOpIndex], ...operationData };
            } else {
              updatedOperations.unshift(operationData); // Add new operation to beginning
            }
            
            return { ...job, operations: updatedOperations };
          }
          return job;
        });
      });
      
      // Also update allJobs
      setAllJobs(prevAllJobs => {
        return prevAllJobs.map(job => {
          if (job.job_id === operationData.job_id) {
            const updatedOperations = job.operations ? [...job.operations] : [];
            const existingOpIndex = updatedOperations.findIndex(op => op.operation_id === operationData.operation_id);
            
            if (existingOpIndex >= 0) {
              updatedOperations[existingOpIndex] = { ...updatedOperations[existingOpIndex], ...operationData };
            } else {
              updatedOperations.unshift(operationData);
            }
            
            return { ...job, operations: updatedOperations };
          }
          return job;
        });
      });
    };

    window.addEventListener('filterJobsByStatus', handleStatusFilter);
    window.addEventListener('expandJob', handleExpandJob);
    window.addEventListener('jobUpdate', handleLiveJobUpdate);
    window.addEventListener('operationUpdate', handleLiveOperationUpdate);
    
    return () => {
      window.removeEventListener('filterJobsByStatus', handleStatusFilter);
      window.removeEventListener('expandJob', handleExpandJob);
      window.removeEventListener('jobUpdate', handleLiveJobUpdate);
      window.removeEventListener('operationUpdate', handleLiveOperationUpdate);
    };
  }, [selectedFilters]);

  const fetchAllJobs = async () => {
    try {
      setLoading(true);
      
      // Fetch ALL jobs with operations - single request for everything
      const response = await api.getJobs({
        limit: 100,
        include_operations: true
      });
      const fetchedJobs = response.data?.data || [];
      setAllJobs(fetchedJobs);
      
      // Apply client-side filtering immediately
      applyClientSideFilters(fetchedJobs);
    } catch (error) {
      console.error('Failed to fetch jobs:', error);
      showError('Failed to Load Jobs', 'Unable to fetch jobs data');
      setJobs([]);
      setAllJobs([]);
    } finally {
      setLoading(false);
    }
  };

  const fetchAllJobsPreservingState = async () => {
    try {
      // Fetch ALL jobs without showing loading state to preserve UI
      const response = await api.getJobs({
        limit: 100,
        include_operations: true
      });
      const fetchedJobs = response.data?.data || [];
      setAllJobs(fetchedJobs);
      
      // Client-side filtering will be triggered by allJobs useEffect
    } catch (error) {
      // Silently handle errors during background refresh to avoid UI disruption
      console.error('Background refresh failed:', error);
    }
  };

  const applyClientSideFilters = (jobsToFilter = allJobs) => {
    if (!jobsToFilter || jobsToFilter.length === 0) {
      setJobs([]);
      return;
    }

    let filteredJobs = [...jobsToFilter];

    // Apply status filter
    if (selectedFilters.status !== 'all') {
      filteredJobs = filteredJobs.filter(job => {
        if (selectedFilters.status === 'running') {
          return ['running', 'pending'].includes(job.status);
        }
        return job.status === selectedFilters.status;
      });
    }

    // Apply job type filter
    if (selectedFilters.jobType !== 'all') {
      filteredJobs = filteredJobs.filter(job => job.job_type === selectedFilters.jobType);
    }

    // Apply repository filter
    if (selectedFilters.repository !== 'all') {
      filteredJobs = filteredJobs.filter(job => job.repository === selectedFilters.repository);
    }

    setJobs(filteredJobs);
  };

  const toggleJobExpansion = (jobId) => {
    // Single expansion logic - only one job can be expanded at a time
    if (expandedJobs.has(jobId)) {
      // Collapse if already expanded
      setExpandedJobs(new Set());
    } else {
      // Expand only this job
      setExpandedJobs(new Set([jobId]));
    }
  };

  const getJobStatusIcon = (status) => {
    const getStatusText = (status) => {
      switch (status) {
        case 'running': return 'Job is currently running';
        case 'completed': return 'Job completed successfully';
        case 'failed': return 'Job failed to complete';
        case 'cancelled': return 'Job was cancelled';
        default: return 'Job status pending';
      }
    };

    switch (status) {
      case 'running':
        return (
          <div className="flex items-center justify-center h-4 w-4" title={getStatusText(status)}>
            <div className="h-3 w-3 bg-blue-600 rounded-full animate-simple-pulse"></div>
          </div>
        );
      case 'completed':
        return <CheckCircle className="h-4 w-4 text-green-500" title={getStatusText(status)} />;
      case 'failed':
        return <XCircle className="h-4 w-4 text-red-500" title={getStatusText(status)} />;
      case 'cancelled':
        return <AlertTriangle className="h-4 w-4 text-yellow-500" title={getStatusText(status)} />;
      default:
        return <Clock className="h-4 w-4 text-gray-500" title={getStatusText(status)} />;
    }
  };

  const getOperationStatusIcon = (status) => {
    switch (status) {
      case 'starting':
      case 'processing':
      case 'fetching_context':
      case 'preparing':
      case 'self_reflecting':
      case 'publishing':
        return (
          <div className="flex items-center justify-center h-3 w-3">
            <div className="h-2 w-2 bg-blue-600 rounded-full animate-simple-pulse"></div>
          </div>
        );
      case 'completed':
      case 'context_completed':
        return <CheckCircle className="h-3 w-3 text-green-500" />;
      case 'failed':
      case 'context_failed':
        return <XCircle className="h-3 w-3 text-red-500" />;
      case 'skipped':
      case 'context_disabled':
        return <AlertTriangle className="h-3 w-3 text-yellow-500" />;
      default:
        return <Clock className="h-3 w-3 text-gray-500" />;
    }
  };

  const getJobTypeIcon = (jobType) => {
    const getJobTypeText = (jobType) => {
      switch (jobType) {
        case 'webhook': return 'Triggered by webhook event';
        case 'cli': return 'Started from command line interface';
        case 'manual': return 'Manually triggered by user';
        case 'api': return 'Started via API call';
        default: return 'Job trigger source unknown';
      }
    };

    switch (jobType) {
      case 'webhook':
        return <Zap className="h-4 w-4 text-gray-600 dark:text-gray-300" title={getJobTypeText(jobType)} />;
      case 'cli':
        return <Database className="h-4 w-4 text-gray-600 dark:text-gray-300" title={getJobTypeText(jobType)} />;
      case 'manual':
        return <User className="h-4 w-4 text-gray-600 dark:text-gray-300" title={getJobTypeText(jobType)} />;
      case 'api':
        return <RefreshCw className="h-4 w-4 text-gray-600 dark:text-gray-300" title={getJobTypeText(jobType)} />;
      default:
        return <Activity className="h-4 w-4 text-gray-600 dark:text-gray-300" title={getJobTypeText(jobType)} />;
    }
  };

  const formatDuration = (duration) => {
    if (!duration) return 'N/A';
    const seconds = Math.round(duration);
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    return new Date(timestamp).toLocaleString();
  };

  const formatCurrency = (amount) => {
    if (!amount) return null;
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 4
    }).format(amount);
  };

  const formatTokens = (tokens) => {
    if (!tokens) return null;
    return new Intl.NumberFormat('en-US').format(tokens);
  };

  const formatHours = (hours) => {
    if (!hours) return null;
    return `${hours.toFixed(1)}h`;
  };

  const getUniqueValues = (field) => {
    const values = new Set();
    jobs.forEach(job => {
      const value = job[field];
      if (value) values.add(value);
    });
    return Array.from(values);
  };

  // Get all possible values for a field (from all jobs, not just filtered)
  const getAllPossibleValues = (field) => {
    const values = new Set();
    jobs.forEach(job => {
      const value = job[field];
      if (value) values.add(value);
    });
    return Array.from(values);
  };

  // Check if a filter value would have results
  const hasResultsForFilter = (field, value, currentFilters) => {
    if (value === 'all') return true;
    
    return jobs.some(job => {
      const matchesStatus = currentFilters.status === 'all' || job.status === currentFilters.status;
      const matchesJobType = currentFilters.jobType === 'all' || job.job_type === currentFilters.jobType;
      const matchesRepository = currentFilters.repository === 'all' || job.repository === currentFilters.repository;
      
      // Override the field we're checking
      if (field === 'status') {
        return value === job.status && matchesJobType && matchesRepository;
      } else if (field === 'job_type') {
        return value === job.job_type && matchesStatus && matchesRepository;
      } else if (field === 'repository') {
        return value === job.repository && matchesStatus && matchesJobType;
      }
      
      return false;
    });
  };

  // Apply client-side filtering
  const filteredJobs = jobs.filter(job => {
    const matchesStatus = selectedFilters.status === 'all' || job.status === selectedFilters.status;
    const matchesJobType = selectedFilters.jobType === 'all' || job.job_type === selectedFilters.jobType;
    const matchesRepository = selectedFilters.repository === 'all' || job.repository === selectedFilters.repository;
    
    return matchesStatus && matchesJobType && matchesRepository;
  });

  // Pagination logic
  const totalPages = Math.ceil(filteredJobs.length / jobsPerPage);
  const startIndex = (currentPage - 1) * jobsPerPage;
  const paginatedJobs = filteredJobs.slice(startIndex, startIndex + jobsPerPage);

  // Auto-expand job when highlighting and handle navigation
  useEffect(() => {
    if (highlightedJobId && jobs.length > 0) {
      // First check if job is in current filtered list
      let jobIndex = filteredJobs.findIndex(job => job.job_id === highlightedJobId);
      
      // If not in filtered list, clear filters first
      if (jobIndex === -1 && filteredJobs.length < jobs.length) {
        setSelectedFilters({
          status: 'all',
          jobType: 'all',
          repository: 'all'
        });
        return; // Exit and let the effect run again with cleared filters
      }
      
      // Job is in the filtered list, proceed with navigation
      if (jobIndex !== -1) {
        const targetPage = Math.floor(jobIndex / jobsPerPage) + 1;
        if (targetPage !== currentPage) {
          setCurrentPage(targetPage);
        }
        
        // Expand only this job (single expansion)
        setExpandedJobs(new Set([highlightedJobId]));
        
        // Scroll to job after a brief delay to ensure DOM is updated
        setTimeout(() => {
          if (highlightedJobRef.current) {
            highlightedJobRef.current.scrollIntoView({
              behavior: 'smooth',
              block: 'center'
            });
          }
        }, 300);
      }
    }
  }, [highlightedJobId, filteredJobs, jobs, currentPage, jobsPerPage]);

  // Handle operation navigation - need to find the job first, then navigate to operation
  useEffect(() => {
    if (highlightedOperationId && jobs.length > 0) {
      // First, find which job contains this operation
      let jobWithOperation = jobs.find(job => 
        job.operations && job.operations.some(op => op.operation_id === highlightedOperationId)
      );
      
      if (!jobWithOperation) return;
      
      // Check if the job is in the current filtered list
      let jobIndex = filteredJobs.findIndex(job => job.job_id === jobWithOperation.job_id);
      
      // If not in filtered list, clear filters first
      if (jobIndex === -1 && filteredJobs.length < jobs.length) {
        setSelectedFilters({
          status: 'all',
          jobType: 'all',
          repository: 'all'
        });
        return; // Exit and let the effect run again with cleared filters
      }
      
      // Job is in filtered list, proceed with navigation
      if (jobIndex !== -1) {
        const targetPage = Math.floor(jobIndex / jobsPerPage) + 1;
        
        // Navigate to correct page if needed
        if (targetPage !== currentPage) {
          setCurrentPage(targetPage);
          // Wait for page change to complete
          setTimeout(() => {
            // Expand the job
            setExpandedJobs(new Set([jobWithOperation.job_id]));
            // Then scroll to operation after expansion
            setTimeout(() => {
              if (highlightedOperationRef.current) {
                highlightedOperationRef.current.scrollIntoView({
                  behavior: 'smooth',
                  block: 'center'
                });
              }
            }, 500); // Wait for expansion animation
          }, 300); // Wait for page change
        } else {
          // Same page, just expand and scroll
          setExpandedJobs(new Set([jobWithOperation.job_id]));
          setTimeout(() => {
            if (highlightedOperationRef.current) {
              highlightedOperationRef.current.scrollIntoView({
                behavior: 'smooth',
                block: 'center'
              });
            }
          }, 500); // Wait for expansion animation
        }
      }
    }
  }, [highlightedOperationId, filteredJobs, jobs, currentPage, jobsPerPage]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        <span className="ml-3 text-gray-600 dark:text-gray-300">Loading jobs...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ViewHeader
        title="Jobs"
        subtitle="Monitor PR-Agent job execution and operations"
        icon={BarChart3}
      />

      {/* Status Tabs Navigation */}
      <div className="flex space-x-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
        {statusTabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = selectedFilters.status === tab.id;
          const jobCount = tab.id === 'all' ? allJobs.length : allJobs.filter(job => job.status === tab.id).length;
          
          return (
            <button
              key={tab.id}
              onClick={() => {
                setSelectedFilters(prev => ({ ...prev, status: tab.id }));
                setCurrentPage(1);
              }}
              className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4 mr-2" />
              {tab.label}
              {jobCount > 0 && (
                <span className={`ml-2 px-2 py-0.5 text-xs rounded-full ${
                  isActive 
                    ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
                    : 'bg-gray-200 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
                }`}>
                  {jobCount}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Additional Filters */}
      {(getAllPossibleValues('job_type').length > 0 || getAllPossibleValues('repository').length > 0) && (
        <div className="flex flex-wrap gap-4 items-center bg-gray-50 dark:bg-gray-800/50 p-4 rounded-lg border border-gray-200 dark:border-gray-700">
          {/* Job Type Filter */}
          {getAllPossibleValues('job_type').length > 0 && (
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Type:</label>
              <select
                value={selectedFilters.jobType}
                onChange={(e) => {
                  setSelectedFilters(prev => ({ ...prev, jobType: e.target.value }));
                  setCurrentPage(1);
                }}
                className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="all">All Types</option>
                {getAllPossibleValues('job_type').map(type => (
                  <option key={type} value={type}>
                    {type.charAt(0).toUpperCase() + type.slice(1)}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Repository Filter */}
          {getAllPossibleValues('repository').length > 0 && (
            <div className="flex items-center space-x-2">
              <label className="text-sm font-medium text-gray-700 dark:text-gray-300">Repository:</label>
              <select
                value={selectedFilters.repository}
                onChange={(e) => {
                  setSelectedFilters(prev => ({ ...prev, repository: e.target.value }));
                  setCurrentPage(1);
                }}
                className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                <option value="all">All Repositories</option>
                {getAllPossibleValues('repository').map(repo => (
                  <option key={repo} value={repo}>
                    {repo.split('/').pop()}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Clear Filters Button */}
          {(selectedFilters.jobType !== 'all' || selectedFilters.repository !== 'all') && (
            <button
              onClick={() => {
                setSelectedFilters(prev => ({ ...prev, jobType: 'all', repository: 'all' }));
                setCurrentPage(1);
              }}
              className="flex items-center px-3 py-1 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-700 rounded-md transition-colors"
            >
              <X className="h-3 w-3 mr-1" />
              Clear Filters
            </button>
          )}
        </div>
      )}

      {/* Jobs List */}
      <div className="space-y-4">
        {paginatedJobs.length === 0 ? (
          <div className="text-center py-12">
            <Activity className="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
            <p className="text-gray-500 dark:text-gray-400">No jobs found matching the selected filters.</p>
          </div>
        ) : (
          paginatedJobs.map((job) => (
            <div
              key={job.job_id}
              ref={highlightedJobId === job.job_id ? highlightedJobRef : null}
              className={`bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 transition-all duration-300 ease-in-out hover:shadow-lg ${
                highlightedJobId === job.job_id ? 'animate-highlight-job ring-2 ring-blue-500 ring-opacity-75' : ''
              }`}
            >
              {/* Clickable Job Card Area */}
              <div 
                className={`cursor-pointer transition-all duration-200 ease-in-out ${
                  expandedJobs.has(job.job_id)
                    ? 'bg-blue-50 dark:bg-blue-900/20'
                    : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
                onClick={() => toggleJobExpansion(job.job_id)}
              >
                {/* Job Header */}
                <div className="p-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-3">
                      <div className="flex items-center justify-center">
                        {expandedJobs.has(job.job_id) ? (
                          <ChevronDown className="h-5 w-5 text-gray-600 dark:text-gray-300 transform transition-all duration-300 ease-in-out" />
                        ) : (
                          <ChevronRight className="h-5 w-5 text-gray-600 dark:text-gray-300 transform transition-all duration-300 ease-in-out" />
                        )}
                      </div>
                      {getJobStatusIcon(job.status)}
                      {getJobTypeIcon(job.job_type)}
                      <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                          {job.repository || 'Unknown Repository'}
                        </h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          {job.job_type} • Started {formatTimestamp(job.started_at)}
                        </p>
                      </div>
                    </div>
                    
                    <div className="flex items-center space-x-4">
                      {/* Job Stats */}
                      <div className="flex items-center space-x-4 text-sm text-gray-500 dark:text-gray-400">
                        <span>{job.operations_count || 0} operations</span>
                        <span>{job.total_logs || 0} logs</span>
                        {job.duration && <span>{formatDuration(job.duration)}</span>}
                      </div>
                      
                      {/* Action Buttons */}
                      <div className="flex items-center space-x-2" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => onShowLogs(job.job_id, 'job')}
                          className="inline-flex items-center px-3 py-1 border border-gray-300 dark:border-gray-600 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                        >
                          <FileText className="h-3 w-3 mr-1" />
                          Logs
                        </button>
                        {job.pr_url && (
                          <a
                            href={job.pr_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center px-3 py-1 border border-gray-300 dark:border-gray-600 rounded-md text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                          >
                            <ExternalLink className="h-3 w-3 mr-1" />
                            PR
                          </a>
                        )}
                      </div>
                    </div>
                  </div>
                  
                  {/* Job Details */}
                  {job.trigger_user && (
                    <div className="mt-2 flex items-center text-sm text-gray-500 dark:text-gray-400">
                      <User className="h-3 w-3 mr-1" />
                      Triggered by {job.trigger_user}
                    </div>
                  )}
                </div>
              </div>

              {/* Expanded Operations */}
              {expandedJobs.has(job.job_id) && job.operations && job.operations.length > 0 && (
                <div className="border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900 animate-expand">
                  <div className="p-4">
                    <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-3">
                      Operations ({job.operations.length})
                    </h4>
                    <div className="space-y-2">
                      {job.operations.map((operation) => {
                        // Check if operation has AI metrics
                        const hasAiMetrics = operation.model_used || operation.input_tokens || operation.output_tokens || operation.estimated_dev_hours_saved;
                        
                        return (
                          <div
                            key={operation.operation_id}
                            ref={highlightedOperationId === operation.operation_id ? highlightedOperationRef : null}
                            className={`p-3 bg-white dark:bg-gray-800 rounded-md border border-gray-200 dark:border-gray-700 ${
                              highlightedOperationId === operation.operation_id ? 'animate-highlight-operation ring-2 ring-blue-500 ring-opacity-75' : ''
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <div className="flex items-center space-x-3">
                                {getOperationStatusIcon(operation.status)}
                                <div>
                                  <p className="text-sm font-medium text-gray-900 dark:text-white">
                                    {operation.operation_type || operation.command || 'Unknown Operation'}
                                  </p>
                                  <p className="text-xs text-gray-500 dark:text-gray-400">
                                    {formatTimestamp(operation.started_at)}
                                    {operation.duration && ` • ${formatDuration(operation.duration)}`}
                                  </p>
                                </div>
                              </div>
                              
                              <div className="flex items-center space-x-4">
                                {/* AI Metrics Display - moved to header */}
                                {hasAiMetrics && (
                                  <div className="flex items-center space-x-4 text-xs">
                                    {operation.model_used && (
                                      <div className="flex items-center space-x-1 text-blue-600 dark:text-blue-400">
                                        <Brain className="h-3 w-3" />
                                        <span>{operation.model_used}</span>
                                      </div>
                                    )}
                                    
                                    {(operation.input_tokens || operation.output_tokens) && (
                                      <div className="flex items-center space-x-1 text-purple-600 dark:text-purple-400">
                                        <Zap className="h-3 w-3" />
                                        <span>
                                          {formatTokens(operation.input_tokens || 0)}
                                          {operation.output_tokens && `+${formatTokens(operation.output_tokens)}`} tokens
                                        </span>
                                      </div>
                                    )}
                                    
                                    {operation.estimated_dev_hours_saved && (
                                      <div className="flex items-center space-x-1 text-green-600 dark:text-green-400">
                                        <TrendingUp className="h-3 w-3" />
                                        <span>{formatHours(operation.estimated_dev_hours_saved)} saved</span>
                                      </div>
                                    )}
                                  </div>
                                )}
                                
                                <button
                                  onClick={() => onShowLogs(operation.operation_id, 'operation')}
                                  className="inline-flex items-center px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                                >
                                  <FileText className="h-3 w-3 mr-1" />
                                  Logs
                                </button>
                              </div>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between bg-white dark:bg-gray-800 px-4 py-3 border border-gray-200 dark:border-gray-700 rounded-lg">
          <div className="flex items-center text-sm text-gray-500 dark:text-gray-400">
            Showing {startIndex + 1}-{Math.min(startIndex + jobsPerPage, filteredJobs.length)} of {filteredJobs.length} jobs
          </div>
          
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
              disabled={currentPage === 1}
              className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Previous
            </button>
            
            <div className="flex items-center space-x-1">
              {(() => {
                const maxVisiblePages = 5;
                const pages = [];
                
                if (totalPages <= maxVisiblePages) {
                  // Show all pages if total is small
                  for (let i = 1; i <= totalPages; i++) {
                    pages.push(i);
                  }
                } else {
                  // Show pages around current page
                  const start = Math.max(1, currentPage - 2);
                  const end = Math.min(totalPages, currentPage + 2);
                  
                  if (start > 1) {
                    pages.push(1);
                    if (start > 2) pages.push('...');
                  }
                  
                  for (let i = start; i <= end; i++) {
                    pages.push(i);
                  }
                  
                  if (end < totalPages) {
                    if (end < totalPages - 1) pages.push('...');
                    pages.push(totalPages);
                  }
                }
                
                return pages.map((page, index) => (
                  page === '...' ? (
                    <span key={`ellipsis-${index}`} className="px-3 py-1 text-sm text-gray-500 dark:text-gray-400">
                      ...
                    </span>
                  ) : (
                    <button
                      key={page}
                      onClick={() => setCurrentPage(page)}
                      className={`px-3 py-1 text-sm rounded-md transition-colors ${
                        currentPage === page
                          ? 'bg-primary-600 text-white'
                          : 'text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700'
                      }`}
                    >
                      {page}
                    </button>
                  )
                ));
              })()}
            </div>
            
            <button
              onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
              disabled={currentPage === totalPages}
              className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded-md text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default JobsList; 