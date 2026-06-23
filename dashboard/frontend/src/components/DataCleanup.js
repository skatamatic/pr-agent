import React, { useState, useEffect, useContext, useCallback } from 'react';
import {
  Trash2,
  Calendar,
  Database,
  AlertTriangle,
  Info,
  Shield,
  BarChart3,
  RefreshCw,
  X,
  Clock,
  GitBranch
} from 'lucide-react';
import api from '../services/api';
import Modal from './Modal';
import { ToastContext } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';

const DataCleanup = () => {
  // Add CSS to hide native date/time picker indicators
  useEffect(() => {
    const style = document.createElement('style');
    style.textContent = `
      /* Hide native date/time picker indicators */
      .hide-date-picker::-webkit-calendar-picker-indicator,
      .hide-time-picker::-webkit-calendar-picker-indicator {
        display: none !important;
        -webkit-appearance: none !important;
        appearance: none !important;
      }

      /* Ensure the custom icons are clickable */
      .hide-date-picker,
      .hide-time-picker {
        cursor: text;
      }
    `;
    document.head.appendChild(style);

    return () => {
      document.head.removeChild(style);
    };
  }, []);

  // Custom styled date/time inputs with proper dark mode icons
  const DateTimeInput = ({ type, id, label, value, onChange, icon: Icon }) => (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type={type}
          value={value}
          onChange={onChange}
          className={`w-full border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 pr-10 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500 ${type === 'date' ? 'hide-date-picker' : 'hide-time-picker'}`}
          style={{
            colorScheme: 'dark'
          }}
        />
        <div
          className="absolute inset-y-0 right-0 flex items-center pr-3 cursor-pointer"
          onClick={() => document.getElementById(id)?.showPicker?.() || document.getElementById(id)?.click?.()}
        >
          <Icon className="h-4 w-4 text-gray-400 dark:text-gray-500 hover:text-gray-600 dark:hover:text-gray-400 transition-colors" />
        </div>
      </div>
    </div>
  );

  const [selectedScope, setSelectedScope] = useState('all'); // 'all' or repository name
  const [cutoffDate, setCutoffDate] = useState('');
  const [cutoffTime, setCutoffTime] = useState('00:00');
  const [repositories, setRepositories] = useState([]);
  const [cleanupPreview, setCleanupPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [confirmations, setConfirmations] = useState({
    understand: false,
    backedUp: false,
    proceed: false
  });
  
  const { showError, showSuccess } = useContext(ToastContext);

  const fetchRepositories = useCallback(async () => {
    try {
      const response = await api.getRepositories();
      setRepositories(response.data?.data || []);
    } catch (error) {
      showError('Failed to load repositories: ' + (error.response?.data?.detail || error.message));
    }
  }, [showError]);

  // Load repositories on component mount
  useEffect(() => {
    fetchRepositories();
  }, [fetchRepositories]);


  const handlePreviewCleanup = async () => {
    if (!cutoffDate) {
      showError('Please select a cutoff date');
      return;
    }

    // No validation needed - selectedScope is always valid

    setLoading(true);
    try {
      // Validate and construct date
      const cutoffDateTime = new Date(`${cutoffDate}T${cutoffTime}`);
      if (isNaN(cutoffDateTime.getTime())) {
        showError('Invalid date or time selected');
        return;
      }
      
      const requestData = {
        cutoff_date: cutoffDateTime.toISOString(),
        repository: selectedScope === 'all' ? null : selectedScope
      };

      const response = await api.previewCleanup(requestData);
      setCleanupPreview(response.data?.data);
      setShowPreviewModal(true);
    } catch (error) {
      showError('Failed to get cleanup preview: ' + (error.response?.data?.detail || error.message));
      setCleanupPreview(null); // Reset preview on error
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteCleanup = async () => {
    if (!cleanupPreview) return;

    setExecuting(true);
    try {
      // Validate and construct date
      const cutoffDateTime = new Date(`${cutoffDate}T${cutoffTime}`);
      if (isNaN(cutoffDateTime.getTime())) {
        showError('Invalid date or time selected');
        return;
      }

      const requestData = {
        cutoff_date: cutoffDateTime.toISOString(),
        repository: selectedScope === 'all' ? null : selectedScope,
        data_types: ['operations', 'jobs', 'logs', 'metrics', 'notification_events']
      };

      await api.executeCleanup(requestData);
      showSuccess('Data cleanup completed successfully!');
      setCleanupPreview(null);
      setShowConfirmation(false);
      setConfirmations({ understand: false, backedUp: false, proceed: false });
    } catch (error) {
      showError('Failed to execute cleanup: ' + (error.response?.data?.detail || error.message));
    } finally {
      setExecuting(false);
    }
  };

  const canExecute = confirmations.understand && confirmations.backedUp && confirmations.proceed;

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      <ViewHeader 
        title="Data Cleanup" 
        icon={Trash2}
        description="Clean up old test data to improve performance and remove inaccurate metrics"
      />
      
      <div className="max-w-4xl mx-auto p-6 space-y-8">
        {/* Repository Scope Selection */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
            <GitBranch className="h-5 w-5 mr-2" />
            Repository Scope
          </h3>

          <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
            Select the scope for data cleanup. Choose "All" for global cleanup or select a specific repository.
          </p>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
            {/* All Repositories Button */}
            <button
              onClick={() => setSelectedScope('all')}
              className={`px-4 py-3 rounded-lg border text-sm font-medium transition-all duration-200 min-w-[120px] max-w-[200px] ${
                selectedScope === 'all'
                  ? 'bg-blue-600 border-blue-600 text-white shadow-md'
                  : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
              }`}
            >
              <div className="flex flex-col items-center justify-center text-center">
                <div className="flex items-center justify-center mb-1">
                  <Database className="h-4 w-4 mr-1 flex-shrink-0" />
                  <span className="leading-tight">All Repositories</span>
                </div>
                <div className="text-xs opacity-75 leading-tight">Global cleanup</div>
              </div>
            </button>

            {/* Repository Buttons */}
            {Array.isArray(repositories) && repositories.map((repo) => (
              <button
                key={repo.id}
                onClick={() => setSelectedScope(repo.name)}
                className={`px-4 py-3 rounded-lg border text-sm font-medium transition-all duration-200 min-w-[120px] max-w-[250px] ${
                  selectedScope === repo.name
                    ? 'bg-blue-600 border-blue-600 text-white shadow-md'
                    : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-600'
                }`}
              >
                <div className="flex flex-col items-center justify-center text-center">
                  <div className="flex items-center justify-center mb-1">
                    <GitBranch className="h-4 w-4 mr-1 flex-shrink-0" />
                    <span className="leading-tight break-words">{repo.name}</span>
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Date Selection */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
            <Calendar className="h-5 w-5 mr-2" />
            Cleanup Date
          </h3>
          
          <div className="space-y-4">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Clean all data before the selected date/time
            </p>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <DateTimeInput
                type="date"
                id="cutoff-date"
                label="Date"
                value={cutoffDate}
                onChange={(e) => setCutoffDate(e.target.value)}
                icon={Calendar}
              />

              <DateTimeInput
                type="time"
                id="cutoff-time"
                label="Time (UTC)"
                value={cutoffTime}
                onChange={(e) => setCutoffTime(e.target.value)}
                icon={Clock}
              />
            </div>
            
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md p-4">
              <div className="flex items-center">
                <AlertTriangle className="h-5 w-5 text-yellow-600 dark:text-yellow-400 mr-2" />
                <span className="text-yellow-800 dark:text-yellow-200 text-sm">
                  This will permanently delete all data before the selected date/time
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Information */}
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <div className="flex items-center">
            <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 flex-shrink-0" />
            <div>
              <p className="text-blue-800 dark:text-blue-200 text-sm font-medium">
                Data Cleanup Process
              </p>
              <p className="text-blue-700 dark:text-blue-300 text-sm mt-1">
                This will permanently delete all operations, jobs, logs, metrics, and notification events older than the specified date/time.
                Repository configurations and settings will be preserved.
              </p>
            </div>
          </div>
        </div>

        {/* Preview Button */}
        <div className="flex justify-center">
          <button
            onClick={handlePreviewCleanup}
            disabled={loading || !cutoffDate}
            className="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? (
              <RefreshCw className="h-5 w-5 mr-2 animate-spin" />
            ) : (
              <BarChart3 className="h-5 w-5 mr-2" />
            )}
            {loading ? 'Generating Preview...' : 'Preview Cleanup'}
          </button>
        </div>


        {/* Confirmation Dialog */}
        {showConfirmation && (
        <Modal open onClose={() => setShowConfirmation(false)} maxWidth="max-w-md" ariaLabel="Confirmation Required">
            <div className="p-6">
                <div className="flex items-center mb-4">
                  <div className="flex-shrink-0">
                    <Shield className="h-6 w-6 text-red-600 dark:text-red-400" />
                  </div>
                  <div className="ml-3">
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                      Confirmation Required
                    </h3>
                  </div>
                </div>
                
                <div className="mb-6">
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                    To proceed with cleanup, please confirm:
                  </p>
                  
                  <div className="space-y-3">
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={confirmations.understand}
                        onChange={(e) => setConfirmations(prev => ({ ...prev, understand: e.target.checked }))}
                        className="h-4 w-4 text-red-600 focus:ring-red-500 border-gray-300 rounded"
                      />
                      <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">
                        I understand this action cannot be undone
                      </span>
                    </label>
                    
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={confirmations.backedUp}
                        onChange={(e) => setConfirmations(prev => ({ ...prev, backedUp: e.target.checked }))}
                        className="h-4 w-4 text-red-600 focus:ring-red-500 border-gray-300 rounded"
                      />
                      <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">
                        I have backed up any important data
                      </span>
                    </label>
                    
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={confirmations.proceed}
                        onChange={(e) => setConfirmations(prev => ({ ...prev, proceed: e.target.checked }))}
                        className="h-4 w-4 text-red-600 focus:ring-red-500 border-gray-300 rounded"
                      />
                      <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">
                        I want to proceed with the cleanup
                      </span>
                    </label>
                  </div>
                  
                  <div className="mt-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-3">
                    <div className="flex items-center">
                      <Info className="h-4 w-4 text-blue-600 dark:text-blue-400 mr-2" />
                      <span className="text-blue-800 dark:text-blue-200 text-xs">
                        An automatic backup will be created before cleanup begins
                      </span>
                    </div>
                  </div>
                </div>
                
                <div className="flex justify-end space-x-3">
                  <button
                    onClick={() => setShowConfirmation(false)}
                    className="btn-modal-secondary"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleExecuteCleanup}
                    disabled={!canExecute || executing}
                    className="btn-modal-danger"
                  >
                    {executing ? (
                      <>
                        <RefreshCw className="h-4 w-4 inline mr-2 animate-spin" />
                        Executing...
                      </>
                    ) : (
                      'Execute Cleanup'
                    )}
                  </button>
                </div>
              </div>
        </Modal>
        )}

        {/* Cleanup Preview Modal */}
        {showPreviewModal && cleanupPreview && (
        <Modal
          open
          onClose={() => setShowPreviewModal(false)}
          maxWidth="max-w-4xl"
          ariaLabel="Cleanup Impact Preview"
        >
              <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center">
                    <div className="flex-shrink-0">
                      <BarChart3 className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                    </div>
                    <div className="ml-3">
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                        Cleanup Impact Preview
                      </h3>
                      <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                        Review the impact before proceeding with cleanup
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={() => setShowPreviewModal(false)}
                    className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                  >
                    <X className="h-6 w-6" />
                  </button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
                  {/* Before Cleanup */}
                  <div>
                    <h4 className="text-md font-medium text-gray-900 dark:text-white mb-4 flex items-center">
                      <Database className="h-4 w-4 mr-2 text-gray-600 dark:text-gray-400" />
                      Before Cleanup
                    </h4>
                    <div className="modal-summary-panel">
                      <div className="space-y-3">
                        <div className="flex justify-between items-center">
                          <span className="text-gray-600 dark:text-gray-400">Operations:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">
                            {(cleanupPreview.before_cleanup.operations || 0).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-gray-600 dark:text-gray-400">Jobs:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">
                            {(cleanupPreview.before_cleanup.jobs || 0).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-gray-600 dark:text-gray-400">Logs:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">
                            {(cleanupPreview.before_cleanup.logs || 0).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-gray-600 dark:text-gray-400">Total Cost:</span>
                          <span className="font-semibold text-green-600 dark:text-green-400">
                            ${(cleanupPreview.before_cleanup.cost_savings || 0).toFixed(2)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* After Cleanup */}
                  <div>
                    <h4 className="text-md font-medium text-gray-900 dark:text-white mb-4 flex items-center">
                      <Database className="h-4 w-4 mr-2 text-gray-600 dark:text-gray-400" />
                      After Cleanup
                    </h4>
                    <div className="modal-summary-panel">
                      <div className="space-y-3">
                        <div className="flex justify-between items-center">
                          <span className="text-gray-600 dark:text-gray-400">Operations:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">
                            {(cleanupPreview.after_cleanup.operations || 0).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-gray-600 dark:text-gray-400">Jobs:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">
                            {(cleanupPreview.after_cleanup.jobs || 0).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-gray-600 dark:text-gray-400">Logs:</span>
                          <span className="font-semibold text-gray-900 dark:text-white">
                            {(cleanupPreview.after_cleanup.logs || 0).toLocaleString()}
                          </span>
                        </div>
                        <div className="flex justify-between items-center">
                          <span className="text-gray-600 dark:text-gray-400">Total Cost:</span>
                          <span className="font-semibold text-green-600 dark:text-green-400">
                            ${(cleanupPreview.after_cleanup.cost_savings || 0).toFixed(2)}
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Impact Summary */}
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6 mb-6">
                  <h5 className="text-md font-semibold text-red-800 dark:text-red-200 mb-4 flex items-center">
                    <AlertTriangle className="h-5 w-5 mr-2" />
                    Cleanup Impact Summary
                  </h5>
                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    <div className="text-center">
                      <div className="text-2xl font-bold text-red-600 dark:text-red-400 mb-1">
                        {((cleanupPreview.to_be_deleted.operations || 0) +
                          (cleanupPreview.to_be_deleted.jobs || 0) +
                          (cleanupPreview.to_be_deleted.logs || 0)).toLocaleString()}
                      </div>
                      <div className="text-sm text-red-700 dark:text-red-300">Records to Delete</div>
                    </div>
                    <div className="text-center">
                      <div className={`text-2xl font-bold mb-1 ${
                        (cleanupPreview.cost_impact || 0) < 0
                          ? 'text-red-600 dark:text-red-400'
                          : 'text-green-600 dark:text-green-400'
                      }`}>
                        ${(Math.abs(cleanupPreview.cost_impact || 0)).toFixed(2)}
                      </div>
                      <div className="text-sm text-red-700 dark:text-red-300">
                        {(cleanupPreview.cost_impact || 0) < 0 ? 'Cost Savings' : 'Cost Impact'}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-2xl font-bold text-blue-600 dark:text-blue-400 mb-1">
                        {(cleanupPreview.storage_impact_mb || 0).toFixed(2)} MB
                      </div>
                      <div className="text-sm text-red-700 dark:text-red-300">Storage Freed</div>
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex justify-end space-x-3">
                  <button
                    onClick={() => setShowPreviewModal(false)}
                    className="btn-modal-secondary"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => {
                      setShowPreviewModal(false);
                      setShowConfirmation(true);
                    }}
                    className="inline-flex items-center btn-modal-danger"
                  >
                    <Trash2 className="h-4 w-4 mr-2" />
                    Proceed with Cleanup
                  </button>
                </div>
              </div>
        </Modal>
        )}
      </div>
    </div>
  );
};

export default DataCleanup;
