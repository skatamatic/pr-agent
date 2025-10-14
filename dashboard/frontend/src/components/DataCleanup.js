import React, { useState, useEffect, useContext } from 'react';
import { 
  Trash2, 
  Calendar, 
  Database, 
  AlertTriangle, 
  CheckCircle, 
  Info, 
  Shield,
  HardDrive,
  DollarSign,
  BarChart3,
  RefreshCw,
  X
} from 'lucide-react';
import api from '../services/api';
import { ToastContext } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';

const DataCleanup = () => {
  const [cleanupScope, setCleanupScope] = useState('all'); // 'all' or 'repository'
  const [selectedRepository, setSelectedRepository] = useState('');
  const [cutoffDate, setCutoffDate] = useState('');
  const [cutoffTime, setCutoffTime] = useState('00:00');
  const [dataTypes, setDataTypes] = useState({
    operations: true,
    jobs: true,
    logs: true,
    metrics: true,
    notification_events: true
  });
  const [repositories, setRepositories] = useState([]);
  const [cleanupPreview, setCleanupPreview] = useState(null);
  const [loading, setLoading] = useState(false);
  const [executing, setExecuting] = useState(false);
  const [showConfirmation, setShowConfirmation] = useState(false);
  const [confirmations, setConfirmations] = useState({
    understand: false,
    backedUp: false,
    proceed: false
  });
  
  const { showError, showSuccess } = useContext(ToastContext);

  // Load repositories on component mount
  useEffect(() => {
    fetchRepositories();
  }, []);

  const fetchRepositories = async () => {
    try {
      const response = await api.getRepositories();
      setRepositories(response.data || []);
    } catch (error) {
      showError('Failed to load repositories: ' + (error.response?.data?.detail || error.message));
    }
  };

  const handleDataTypeChange = (type) => {
    setDataTypes(prev => ({
      ...prev,
      [type]: !prev[type]
    }));
  };

  const handlePreviewCleanup = async () => {
    if (!cutoffDate) {
      showError('Please select a cutoff date');
      return;
    }

    if (cleanupScope === 'repository' && !selectedRepository) {
      showError('Please select a repository for cleanup');
      return;
    }

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
        repository: cleanupScope === 'repository' ? selectedRepository : null
      };

      const response = await api.previewCleanup(requestData);
      setCleanupPreview(response.data);
    } catch (error) {
      showError('Failed to get cleanup preview: ' + (error.response?.data?.detail || error.message));
    } finally {
      setLoading(false);
    }
  };

  const handleExecuteCleanup = async () => {
    if (!cleanupPreview) return;

    const selectedDataTypes = Object.keys(dataTypes).filter(type => dataTypes[type]);
    if (selectedDataTypes.length === 0) {
      showError('Please select at least one data type to clean');
      return;
    }

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
        repository: cleanupScope === 'repository' ? selectedRepository : null,
        data_types: selectedDataTypes
      };

      const response = await api.executeCleanup(requestData);
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
        {/* Cleanup Scope Selection */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
            <Database className="h-5 w-5 mr-2" />
            Cleanup Scope
          </h3>
          
          <div className="space-y-4">
            <div className="flex items-center space-x-3">
              <input
                type="radio"
                id="scope-all"
                name="cleanup-scope"
                value="all"
                checked={cleanupScope === 'all'}
                onChange={(e) => setCleanupScope(e.target.value)}
                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
              />
              <label htmlFor="scope-all" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                All Repositories (Global cleanup)
              </label>
            </div>
            
            <div className="flex items-center space-x-3">
              <input
                type="radio"
                id="scope-repository"
                name="cleanup-scope"
                value="repository"
                checked={cleanupScope === 'repository'}
                onChange={(e) => setCleanupScope(e.target.value)}
                className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300"
              />
              <label htmlFor="scope-repository" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Specific Repository
              </label>
            </div>
            
            {cleanupScope === 'repository' && (
              <div className="ml-7">
                <select
                  value={selectedRepository}
                  onChange={(e) => setSelectedRepository(e.target.value)}
                  className="mt-1 block w-full border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">Select a repository...</option>
                  {repositories.map((repo) => (
                    <option key={repo.id} value={repo.name}>
                      {repo.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
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
              <div>
                <label htmlFor="cutoff-date" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Date
                </label>
                <input
                  id="cutoff-date"
                  type="date"
                  value={cutoffDate}
                  onChange={(e) => setCutoffDate(e.target.value)}
                  className="w-full border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
              
              <div>
                <label htmlFor="cutoff-time" className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Time (UTC)
                </label>
                <input
                  id="cutoff-time"
                  type="time"
                  value={cutoffTime}
                  onChange={(e) => setCutoffTime(e.target.value)}
                  className="w-full border border-gray-300 dark:border-gray-600 rounded-md px-3 py-2 bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
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

        {/* Data Types Selection */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
            <BarChart3 className="h-5 w-5 mr-2" />
            Data Types to Clean
          </h3>
          
          <div className="space-y-3">
            {Object.entries(dataTypes).map(([type, checked]) => (
              <div key={type} className="flex items-center space-x-3">
                <input
                  type="checkbox"
                  id={`data-type-${type}`}
                  checked={checked}
                  onChange={() => handleDataTypeChange(type)}
                  className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                />
                <label htmlFor={`data-type-${type}`} className="text-sm font-medium text-gray-700 dark:text-gray-300">
                  {type.charAt(0).toUpperCase() + type.slice(1).replace('_', ' ')}
                </label>
              </div>
            ))}
            
            <div className="mt-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
              <div className="flex items-center">
                <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
                <span className="text-blue-800 dark:text-blue-200 text-sm">
                  Repository configurations and settings will be preserved
                </span>
              </div>
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

        {/* Cleanup Impact Preview */}
        {cleanupPreview && (
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 p-6">
            <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
              <CheckCircle className="h-5 w-5 mr-2 text-green-600" />
              Cleanup Impact Preview
            </h3>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Before Cleanup */}
              <div>
                <h4 className="text-md font-medium text-gray-900 dark:text-white mb-3">Before Cleanup:</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Operations:</span>
                    <span className="font-medium">{cleanupPreview.before_cleanup.operations.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Jobs:</span>
                    <span className="font-medium">{cleanupPreview.before_cleanup.jobs.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Logs:</span>
                    <span className="font-medium">{cleanupPreview.before_cleanup.logs.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Cost Savings:</span>
                    <span className="font-medium text-green-600">${cleanupPreview.before_cleanup.cost_savings.toFixed(2)}</span>
                  </div>
                </div>
              </div>

              {/* After Cleanup */}
              <div>
                <h4 className="text-md font-medium text-gray-900 dark:text-white mb-3">After Cleanup:</h4>
                <div className="space-y-2 text-sm">
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Operations:</span>
                    <span className="font-medium">{cleanupPreview.after_cleanup.operations.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Jobs:</span>
                    <span className="font-medium">{cleanupPreview.after_cleanup.jobs.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Logs:</span>
                    <span className="font-medium">{cleanupPreview.after_cleanup.logs.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600 dark:text-gray-400">Cost Savings:</span>
                    <span className="font-medium text-green-600">${cleanupPreview.after_cleanup.cost_savings.toFixed(2)}</span>
                  </div>
                </div>
              </div>
            </div>

            {/* Impact Summary */}
            <div className="mt-6 bg-gray-50 dark:bg-gray-700 rounded-md p-4">
              <h5 className="text-sm font-medium text-gray-900 dark:text-white mb-3">Impact Summary:</h5>
              <div className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Records to be deleted:</span>
                  <span className="font-medium text-red-600">
                    {(cleanupPreview.to_be_deleted.operations + cleanupPreview.to_be_deleted.jobs + cleanupPreview.to_be_deleted.logs).toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Cost Impact:</span>
                  <span className={`font-medium ${cleanupPreview.cost_impact < 0 ? 'text-red-600' : 'text-green-600'}`}>
                    ${cleanupPreview.cost_impact.toFixed(2)}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-600 dark:text-gray-400">Storage Freed:</span>
                  <span className="font-medium text-blue-600">
                    {cleanupPreview.storage_impact_mb.toFixed(2)} MB
                  </span>
                </div>
              </div>
            </div>

            {/* Execute Button */}
            <div className="mt-6 flex justify-center">
              <button
                onClick={() => setShowConfirmation(true)}
                className="inline-flex items-center px-6 py-3 border border-transparent text-base font-medium rounded-md text-white bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500"
              >
                <Trash2 className="h-5 w-5 mr-2" />
                Execute Cleanup
              </button>
            </div>
          </div>
        )}

        {/* Confirmation Dialog */}
        {showConfirmation && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-md w-full mx-4">
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
                    className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-md hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleExecuteCleanup}
                    disabled={!canExecute || executing}
                    className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
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
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default DataCleanup;
