import React, { useState, useEffect } from 'react';
import { 
  Database, 
  HardDrive, 
  Calendar, 
  Settings, 
  Download, 
  Upload, 
  Trash2, 
  AlertTriangle,
  CheckCircle,
  Clock,
  BarChart3,
  Shield,
  Archive,
  RefreshCw,
  FileText,
  Info,
  RotateCcw
} from 'lucide-react';
import apiService from '../services/api';
import { useToast } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';

const AdminPanel = () => {
  const [activeSection, setActiveSection] = useState('retention');
  const [retentionConfig, setRetentionConfig] = useState({
    max_database_size_mb: 500,
    max_jobs: 1000,
    max_logs: 10000,
    max_operations: 5000,
    max_notification_events: 1000,
    job_retention_days: 30,
    log_retention_days: 14,
    operation_retention_days: 30,
    notification_event_retention_days: 7,
    cleanup_strategy: 'hybrid', // Match backend default
    auto_cleanup_enabled: true,
    backup_before_cleanup: true,
    cleanup_schedule_hours: 24,
    // Backup settings
    auto_backup_enabled: false,
    backup_schedule_hours: 168, // weekly
    backup_compression: true,
    max_backup_files: 10 // retention count for auto backups
  });
  const [databaseStats, setDatabaseStats] = useState(null);
  const [backupList, setBackupList] = useState([]);
  const [backupDirectory, setBackupDirectory] = useState('');
  const [cleanupResults, setCleanupResults] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  
  // Pagination state for backups
  const [currentPage, setCurrentPage] = useState(1);
  const [backupsPerPage] = useState(10);
  
  // Deletion state
  const [deletingBackup, setDeletingBackup] = useState('');
  
  // Restoration state
  const [restoringBackup, setRestoringBackup] = useState('');

  const { showSuccess, showError } = useToast();

  useEffect(() => {
    loadRetentionConfig();
    loadDatabaseStats();
    loadBackupList();
    loadBackupDirectory();
  }, []);

  const loadRetentionConfig = async () => {
    try {
      const response = await apiService.getRetentionConfig();
      if (response.data?.data) {
        setRetentionConfig(response.data.data);
      }
    } catch (error) {
      console.error('Failed to load retention config:', error);
      showError('Failed to load retention configuration');
    }
  };

  const loadDatabaseStats = async () => {
    try {
      const response = await apiService.getDatabaseStats();
      if (response.data?.data) {
        setDatabaseStats(response.data.data);
      }
    } catch (error) {
      console.error('Failed to load database stats:', error);
      showError('Failed to load database statistics');
    }
  };

  const loadBackupList = async () => {
    try {
      const response = await apiService.getBackupList();
      if (response.data?.data) {
        setBackupList(response.data.data);
      }
    } catch (error) {
      console.error('Failed to load backup list:', error);
      showError('Failed to load backup list');
    }
  };

  const loadBackupDirectory = async () => {
    try {
      const response = await apiService.getBackupDirectory();
      if (response.data?.data?.backup_directory) {
        setBackupDirectory(response.data.data.backup_directory);
      }
    } catch (error) {
      console.error('Failed to load backup directory:', error);
    }
  };

  const handleConfigChange = (key, value) => {
    setRetentionConfig(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const saveRetentionConfig = async () => {
    setSaving(true);
    try {
      await apiService.updateRetentionConfig(retentionConfig);
      showSuccess('Configuration Saved', 'Retention configuration saved successfully');
    } catch (error) {
      console.error('Failed to save retention config:', error);
      showError('Save Failed', 'Failed to save retention configuration');
    }
    setSaving(false);
  };

  const performCleanup = async (dryRun = true) => {
    setLoading(true);
    try {
      const response = await apiService.performCleanup(dryRun);
      if (response.data?.data) {
        const results = response.data.data;
        setCleanupResults(results);
        
        const action = dryRun ? 'Cleanup simulation' : 'Database cleanup';
        showSuccess(action, `${action} completed successfully`);
        
        // Refresh stats after actual cleanup
        if (!dryRun) {
          await loadDatabaseStats();
        }
      }
    } catch (error) {
      console.error('Failed to perform cleanup:', error);
      showError('Cleanup Failed', 'Failed to perform database cleanup');
    }
    setLoading(false);
  };

  const createBackup = async (compressed = true) => {
    setLoading(true);
    try {
      const response = await apiService.createBackup(compressed);
      if (response.data) {
        showSuccess('Backup Created', 'Database backup created successfully');
        await loadBackupList();
      }
    } catch (error) {
      console.error('Failed to create backup:', error);
      showError('Backup Failed', 'Failed to create database backup');
    }
    setLoading(false);
  };

  const exportData = async (format = 'json') => {
    setLoading(true);
    try {
      const response = await apiService.exportData(format);
      
      // Handle blob response for download
      if (response.data instanceof Blob) {
        const url = window.URL.createObjectURL(response.data);
        const link = document.createElement('a');
        link.href = url;
        link.download = `dashboard_export_${new Date().toISOString().slice(0, 19).replace(/:/g, '-')}.${format}`;
        document.body.appendChild(link);
        link.click();
        link.remove();
        window.URL.revokeObjectURL(url);
        showSuccess('Data Exported', `Data export (${format}) downloaded successfully`);
      } else {
        showSuccess('Data Exported', `Data export (${format}) completed successfully`);
      }
    } catch (error) {
      console.error('Failed to export data:', error);
      showError('Export Failed', 'Failed to export database data');
    }
    setLoading(false);
  };

  const formatBytes = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  const formatDate = (dateString) => {
    return new Date(dateString).toLocaleString();
  };

  const deleteBackup = async (filename) => {
    if (!window.confirm(`Are you sure you want to delete backup "${filename}"?`)) {
      return;
    }
    
    setDeletingBackup(filename);
    try {
      await apiService.deleteBackup(filename);
      showSuccess('Backup Deleted', 'Backup deleted successfully');
      await loadBackupList();
      // Reset page if no items on current page
      const newBackupCount = backupList.length - 1;
      const maxPage = Math.ceil(newBackupCount / backupsPerPage);
      if (currentPage > maxPage && maxPage > 0) {
        setCurrentPage(maxPage);
      }
    } catch (error) {
      console.error('Failed to delete backup:', error);
      showError('Delete Failed', 'Failed to delete backup');
    }
    setDeletingBackup('');
  };

  const deleteAllBackups = async () => {
    if (!window.confirm('Are you sure you want to delete ALL backups? This action cannot be undone.')) {
      return;
    }
    
    setLoading(true);
    try {
      const response = await apiService.deleteAllBackups();
      if (response.data?.data) {
        const result = response.data.data;
        showSuccess('Backups Deleted', `Deleted ${result.deleted_count} backup files (${result.total_size_mb} MB)`);
        await loadBackupList();
        setCurrentPage(1);
      }
    } catch (error) {
      console.error('Failed to delete all backups:', error);
      showError('Delete Failed', 'Failed to delete all backups');
    }
    setLoading(false);
  };

  const restoreBackup = async (filename) => {
    if (!window.confirm(
      `Are you sure you want to restore from backup "${filename}"?\n\n` +
      `This will:\n` +
      `• Create a safety backup of the current database\n` +
      `• Replace all current data with the backup data\n` +
      `• This action cannot be undone!\n\n` +
      `Continue with restoration?`
    )) {
      return;
    }
    
    setRestoringBackup(filename);
    try {
      const response = await apiService.restoreBackup(filename);
      if (response.data?.data) {
        const result = response.data.data;
        showSuccess('Database Restored', 
          `Database restored from ${filename}. Safety backup created: ${result.safety_backup?.split('/').pop()}`
        );
        await loadBackupList();
        await loadDatabaseStats(); // Refresh stats after restore
      }
    } catch (error) {
      console.error('Failed to restore backup:', error);
      const errorMessage = error.response?.data?.detail || 'Failed to restore backup';
      showError('Restore Failed', errorMessage);
    }
    setRestoringBackup('');
  };

  // Pagination helpers
  const indexOfLastBackup = currentPage * backupsPerPage;
  const indexOfFirstBackup = indexOfLastBackup - backupsPerPage;
  const currentBackups = backupList.slice(indexOfFirstBackup, indexOfLastBackup);
  const totalPages = Math.ceil(backupList.length / backupsPerPage);

  const paginate = (pageNumber) => setCurrentPage(pageNumber);

  const getUsageColor = (current, max) => {
    const percentage = (current / max) * 100;
    if (percentage >= 90) return 'text-red-600 dark:text-red-400';
    if (percentage >= 75) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-green-600 dark:text-green-400';
  };

  const getUsageBarColor = (current, max) => {
    const percentage = (current / max) * 100;
    if (percentage >= 90) return 'bg-red-500';
    if (percentage >= 75) return 'bg-yellow-500';
    return 'bg-green-500';
  };

  const sections = [
    { id: 'retention', name: 'Retention Policy', icon: Calendar },
    { id: 'database', name: 'Database Stats', icon: Database },
    { id: 'backup', name: 'Backup & Export', icon: Archive }
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <ViewHeader
        title="Retention"
        subtitle="Database retention, backup management, and storage administration"
        icon={Database}
      />

      {/* Section Navigation */}
      <div className="flex space-x-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
        {[
          { id: 'retention', name: 'Retention', icon: Calendar },
          { id: 'database', name: 'Stats', icon: BarChart3 },
          { id: 'backup', name: 'Backup & Export', icon: Archive }
        ].map((section) => {
          const Icon = section.icon;
          return (
            <button
              key={section.id}
              onClick={() => setActiveSection(section.id)}
              className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                activeSection === section.id
                  ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4 mr-2" />
              {section.name}
            </button>
          );
        })}
      </div>

      {/* Retention Policy Section */}
      {activeSection === 'retention' && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                Retention Configuration
              </h2>
              <p className="text-gray-600 dark:text-gray-400">
                Configure database retention policies to manage storage and performance
              </p>
            </div>

            <div className="p-6 space-y-6">
              {/* Cleanup Strategy - Move to top */}
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Cleanup Strategy</h3>
                <div className="space-y-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Strategy
                    </label>
                    <select
                      value={retentionConfig.cleanup_strategy}
                      onChange={(e) => handleConfigChange('cleanup_strategy', e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                               bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    >
                      <option value="time">Time-based (delete old records)</option>
                      <option value="count">Count-based (keep most recent)</option>
                      <option value="hybrid">Hybrid (time + count limits)</option>
                    </select>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      {retentionConfig.cleanup_strategy === 'time' && 'Delete records older than specified days'}
                      {retentionConfig.cleanup_strategy === 'count' && 'Keep only the most recent N records'}
                      {retentionConfig.cleanup_strategy === 'hybrid' && 'Apply both time and count limits'}
                    </p>
                  </div>
                </div>
              </div>

              {/* Time-based Settings - Show for time or hybrid */}
              {(retentionConfig.cleanup_strategy === 'time' || retentionConfig.cleanup_strategy === 'hybrid') && (
                <div>
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                    Time-based Retention
                    <span className="text-sm font-normal text-gray-500 dark:text-gray-400 ml-2">
                      (Delete records older than N days)
                    </span>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Job Retention (days)
                      </label>
                      <input
                        type="number"
                        value={retentionConfig.job_retention_days}
                        onChange={(e) => handleConfigChange('job_retention_days', parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        min="1"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Log Retention (days)
                      </label>
                      <input
                        type="number"
                        value={retentionConfig.log_retention_days}
                        onChange={(e) => handleConfigChange('log_retention_days', parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        min="1"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Operation Retention (days)
                      </label>
                      <input
                        type="number"
                        value={retentionConfig.operation_retention_days}
                        onChange={(e) => handleConfigChange('operation_retention_days', parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        min="1"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Notification Event Retention (days)
                      </label>
                      <input
                        type="number"
                        value={retentionConfig.notification_event_retention_days}
                        onChange={(e) => handleConfigChange('notification_event_retention_days', parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        min="1"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* Count-based Settings - Show for count or hybrid */}
              {(retentionConfig.cleanup_strategy === 'count' || retentionConfig.cleanup_strategy === 'hybrid') && (
                <div>
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">
                    Count-based Limits
                    <span className="text-sm font-normal text-gray-500 dark:text-gray-400 ml-2">
                      (Keep only the most recent N records)
                    </span>
                  </h3>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Max Jobs
                      </label>
                      <input
                        type="number"
                        value={retentionConfig.max_jobs}
                        onChange={(e) => handleConfigChange('max_jobs', parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        min="1"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Max Logs
                      </label>
                      <input
                        type="number"
                        value={retentionConfig.max_logs}
                        onChange={(e) => handleConfigChange('max_logs', parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        min="1"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Max Operations
                      </label>
                      <input
                        type="number"
                        value={retentionConfig.max_operations}
                        onChange={(e) => handleConfigChange('max_operations', parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        min="1"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Max Notification Events
                      </label>
                      <input
                        type="number"
                        value={retentionConfig.max_notification_events}
                        onChange={(e) => handleConfigChange('max_notification_events', parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        min="1"
                      />
                    </div>
                  </div>
                </div>
              )}

              {/* General Settings */}
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">General Settings</h3>
                <div className="space-y-4">

                  <div className="flex items-center space-x-4">
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={retentionConfig.auto_cleanup_enabled}
                        onChange={(e) => handleConfigChange('auto_cleanup_enabled', e.target.checked)}
                        className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                      />
                      <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">
                        Enable automatic cleanup
                      </span>
                    </label>

                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={retentionConfig.backup_before_cleanup}
                        onChange={(e) => handleConfigChange('backup_before_cleanup', e.target.checked)}
                        className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                      />
                      <span className="ml-2 text-sm text-gray-700 dark:text-gray-300">
                        Backup before cleanup
                      </span>
                    </label>
                  </div>

                  {retentionConfig.auto_cleanup_enabled && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Cleanup Schedule (hours)
                      </label>
                      <input
                        type="number"
                        value={retentionConfig.cleanup_schedule_hours}
                        onChange={(e) => handleConfigChange('cleanup_schedule_hours', parseInt(e.target.value))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                 bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        min="1"
                        max="168"
                      />
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Run cleanup every N hours (1-168)
                      </p>
                    </div>
                  )}
                </div>
              </div>

              {/* Save Button */}
              <div className="flex justify-end pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  onClick={saveRetentionConfig}
                  disabled={saving}
                  className="px-6 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 
                           text-white rounded-lg font-medium transition-colors flex items-center"
                >
                  {saving ? (
                    <>
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    <>
                      <Settings className="h-4 w-4 mr-2" />
                      Save Configuration
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Database Stats Section */}
      {activeSection === 'database' && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                    Database Statistics
                  </h2>
                  <p className="text-gray-600 dark:text-gray-400">
                    Current database usage and performance metrics
                  </p>
                </div>
                <button
                  onClick={loadDatabaseStats}
                  className="px-4 py-2 text-blue-600 hover:text-blue-700 dark:text-blue-400 
                           dark:hover:text-blue-300 font-medium flex items-center"
                >
                  <RefreshCw className="h-4 w-4 mr-2" />
                  Refresh
                </button>
              </div>
            </div>

            <div className="p-6">
              {databaseStats ? (
                <div className="space-y-6">
                  {/* Overview Cards */}
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                    <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Database Size</p>
                          <p className="text-2xl font-bold text-gray-900 dark:text-white">
                            {formatBytes(databaseStats.size_bytes)}
                          </p>
                        </div>
                        <HardDrive className="h-8 w-8 text-blue-600 dark:text-blue-400" />
                      </div>
                    </div>

                    <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Total Jobs</p>
                          <p className="text-2xl font-bold text-gray-900 dark:text-white">
                            {databaseStats.jobs_count?.toLocaleString()}
                          </p>
                        </div>
                        <BarChart3 className="h-8 w-8 text-green-600 dark:text-green-400" />
                      </div>
                    </div>

                    <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Total Logs</p>
                          <p className="text-2xl font-bold text-gray-900 dark:text-white">
                            {databaseStats.logs_count?.toLocaleString()}
                          </p>
                        </div>
                        <FileText className="h-8 w-8 text-yellow-600 dark:text-yellow-400" />
                      </div>
                    </div>

                    <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                      <div className="flex items-center justify-between">
                        <div>
                          <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Operations</p>
                          <p className="text-2xl font-bold text-gray-900 dark:text-white">
                            {databaseStats.operations_count?.toLocaleString()}
                          </p>
                        </div>
                        <Settings className="h-8 w-8 text-purple-600 dark:text-purple-400" />
                      </div>
                    </div>
                  </div>

                  {/* Usage Bars */}
                  <div className="space-y-4">
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white">Usage vs Limits</h3>
                    
                    <div className="space-y-3">
                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-700 dark:text-gray-300">Jobs</span>
                          <span className={getUsageColor(databaseStats.jobs_count, retentionConfig.max_jobs)}>
                            {databaseStats.jobs_count} / {retentionConfig.max_jobs}
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                          <div 
                            className={`h-2 rounded-full ${getUsageBarColor(databaseStats.jobs_count, retentionConfig.max_jobs)}`}
                            style={{ width: `${Math.min((databaseStats.jobs_count / retentionConfig.max_jobs) * 100, 100)}%` }}
                          ></div>
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-700 dark:text-gray-300">Logs</span>
                          <span className={getUsageColor(databaseStats.logs_count, retentionConfig.max_logs)}>
                            {databaseStats.logs_count} / {retentionConfig.max_logs}
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                          <div 
                            className={`h-2 rounded-full ${getUsageBarColor(databaseStats.logs_count, retentionConfig.max_logs)}`}
                            style={{ width: `${Math.min((databaseStats.logs_count / retentionConfig.max_logs) * 100, 100)}%` }}
                          ></div>
                        </div>
                      </div>

                      <div>
                        <div className="flex justify-between text-sm mb-1">
                          <span className="text-gray-700 dark:text-gray-300">Operations</span>
                          <span className={getUsageColor(databaseStats.operations_count, retentionConfig.max_operations)}>
                            {databaseStats.operations_count} / {retentionConfig.max_operations}
                          </span>
                        </div>
                        <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                          <div 
                            className={`h-2 rounded-full ${getUsageBarColor(databaseStats.operations_count, retentionConfig.max_operations)}`}
                            style={{ width: `${Math.min((databaseStats.operations_count / retentionConfig.max_operations) * 100, 100)}%` }}
                          ></div>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Cleanup Actions */}
                  <div className="pt-4 border-t border-gray-200 dark:border-gray-700">
                    <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Cleanup Actions</h3>
                    <div className="flex flex-wrap gap-3 mb-4">
                      <button
                        onClick={() => performCleanup(true)}
                        disabled={loading}
                        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 
                                 text-white rounded-lg font-medium transition-colors flex items-center"
                      >
                        {loading ? (
                          <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Info className="h-4 w-4 mr-2" />
                        )}
                        Simulate Cleanup
                      </button>

                      <button
                        onClick={() => performCleanup(false)}
                        disabled={loading}
                        className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 
                                 text-white rounded-lg font-medium transition-colors flex items-center"
                      >
                        {loading ? (
                          <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4 mr-2" />
                        )}
                        Perform Cleanup
                      </button>
                    </div>

                    {/* Cleanup Results */}
                    {cleanupResults && (
                      <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                        <h4 className="text-md font-medium text-gray-900 dark:text-white mb-3">
                          {cleanupResults.dry_run ? 'Cleanup Simulation Results' : 'Cleanup Results'}
                        </h4>
                        <div className="space-y-2">
                          <div className="flex justify-between">
                            <span className="text-gray-600 dark:text-gray-400">Total Records:</span>
                            <span className="font-medium text-gray-900 dark:text-white">
                              {cleanupResults.total_deleted} {cleanupResults.dry_run ? 'would be deleted' : 'deleted'}
                            </span>
                          </div>
                          {cleanupResults.space_reclaimed_mb > 0 && (
                            <div className="flex justify-between">
                              <span className="text-gray-600 dark:text-gray-400">Space Reclaimed:</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {cleanupResults.space_reclaimed_mb} MB
                              </span>
                            </div>
                          )}
                          {Object.keys(cleanupResults.tables_processed).length > 0 && (
                            <div>
                              <span className="text-gray-600 dark:text-gray-400">Tables Affected:</span>
                              <div className="mt-1 space-y-1">
                                {Object.entries(cleanupResults.tables_processed).map(([table, count]) => (
                                  <div key={table} className="flex justify-between text-sm">
                                    <span className="text-gray-500 dark:text-gray-400">{table}:</span>
                                    <span className="text-gray-700 dark:text-gray-300">{count} records</span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}
                          {cleanupResults.errors?.length > 0 && (
                            <div className="text-red-600 dark:text-red-400">
                              <span className="font-medium">Errors:</span>
                              <ul className="mt-1 text-sm">
                                {cleanupResults.errors.map((error, index) => (
                                  <li key={index}>• {error}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="text-center py-8">
                  <Database className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                  <p className="text-gray-500 dark:text-gray-400">Loading database statistics...</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Backup & Export Section */}
      {activeSection === 'backup' && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
            <div className="p-6 border-b border-gray-200 dark:border-gray-700">
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">
                Backup & Export
              </h2>
              <p className="text-gray-600 dark:text-gray-400">
                Create backups and export database data
              </p>
            </div>

            <div className="p-6 space-y-6">
              {/* Backup Directory Configuration */}
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Backup Configuration</h3>
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4">
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Backup Directory
                  </label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={backupDirectory}
                      onChange={(e) => setBackupDirectory(e.target.value)}
                      placeholder="/path/to/backup/directory"
                      className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                               bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                    />
                    <button
                      onClick={async () => {
                        try {
                          await apiService.setBackupDirectory(backupDirectory);
                          showSuccess('Backup Directory Updated', 'Backup directory updated successfully');
                        } catch (error) {
                          showError('Update Failed', 'Failed to update backup directory');
                        }
                      }}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-md font-medium"
                    >
                      Update
                    </button>
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Directory where database backups will be stored. Can be a local path or network drive (e.g., \\server\share\backups)
                  </p>
                  <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
                    <strong>Examples:</strong>
                    <br />• Windows: <code className="bg-gray-200 dark:bg-gray-600 px-1 rounded">C:\backups\pr-agent</code>
                    <br />• Linux/Mac: <code className="bg-gray-200 dark:bg-gray-600 px-1 rounded">/var/backups/pr-agent</code>
                    <br />• Network: <code className="bg-gray-200 dark:bg-gray-600 px-1 rounded">\\server\backups\pr-agent</code>
                  </div>
                </div>
              </div>

              {/* Backup Scheduling */}
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Automatic Backups</h3>
                <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 space-y-4">
                  <div className="flex items-center space-x-4">
                    <label className="flex items-center">
                      <input
                        type="checkbox"
                        checked={retentionConfig.auto_backup_enabled}
                        onChange={(e) => handleConfigChange('auto_backup_enabled', e.target.checked)}
                        className="mr-2 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300">Enable automatic backups</span>
                    </label>
                  </div>
                  
                  <div className="text-xs text-gray-500 dark:text-gray-400">
                    When enabled, the system will automatically create compressed database backups according to the schedule below. 
                    Automatic backups are marked as "Automatic" type in the backup list. 
                    <strong>Click "Save Backup Settings" below to activate automatic backups.</strong>
                  </div>
                  
                  {retentionConfig.auto_backup_enabled && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Backup Frequency
                        </label>
                        <select
                          value={retentionConfig.backup_schedule_hours}
                          onChange={(e) => handleConfigChange('backup_schedule_hours', parseInt(e.target.value))}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                   bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                        >
                          <option value={24}>Daily (24 hours)</option>
                          <option value={72}>Every 3 days</option>
                          <option value={168}>Weekly (7 days)</option>
                          <option value={336}>Bi-weekly (14 days)</option>
                          <option value={720}>Monthly (30 days)</option>
                        </select>
                      </div>
                      
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Max Backup Files
                        </label>
                        <input
                          type="number"
                          value={retentionConfig.max_backup_files}
                          onChange={(e) => handleConfigChange('max_backup_files', parseInt(e.target.value))}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md 
                                   bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
                          min="1"
                          max="50"
                        />
                      </div>
                      
                      <div className="md:col-span-2">
                        <label className="flex items-center">
                          <input
                            type="checkbox"
                            checked={retentionConfig.backup_compression}
                            onChange={(e) => handleConfigChange('backup_compression', e.target.checked)}
                            className="mr-2 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500"
                          />
                          <span className="text-sm text-gray-700 dark:text-gray-300">Compress backups to save space</span>
                        </label>
                      </div>
                    </div>
                  )}
                  
                  {/* Save Button for Backup Configuration */}
                  <div className="flex justify-end pt-4 border-t border-gray-200 dark:border-gray-700">
                    <button
                      onClick={saveRetentionConfig}
                      disabled={saving}
                      className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 
                               text-white rounded-lg font-medium transition-colors flex items-center"
                    >
                      {saving ? (
                        <>
                          <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                          Saving...
                        </>
                      ) : (
                        <>
                          <Settings className="h-4 w-4 mr-2" />
                          Save Backup Settings
                        </>
                      )}
                    </button>
                  </div>
                </div>
              </div>

              {/* Manual Backup Actions */}
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Manual Backup</h3>
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => createBackup(true)}
                    disabled={loading}
                    className="px-4 py-2 bg-green-600 hover:bg-green-700 disabled:bg-green-400 
                             text-white rounded-lg font-medium transition-colors flex items-center"
                  >
                    {loading ? (
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Archive className="h-4 w-4 mr-2" />
                    )}
                    Compressed Backup
                  </button>

                  <button
                    onClick={() => createBackup(false)}
                    disabled={loading}
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 
                             text-white rounded-lg font-medium transition-colors flex items-center"
                  >
                    {loading ? (
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Download className="h-4 w-4 mr-2" />
                    )}
                    Standard Backup
                  </button>
                </div>
              </div>

              {/* Export Actions */}
              <div>
                <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4">Export Data</h3>
                <div className="flex flex-wrap gap-3">
                  <button
                    onClick={() => exportData('json')}
                    disabled={loading}
                    className="px-4 py-2 bg-purple-600 hover:bg-purple-700 disabled:bg-purple-400 
                             text-white rounded-lg font-medium transition-colors flex items-center"
                  >
                    {loading ? (
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <FileText className="h-4 w-4 mr-2" />
                    )}
                    Export as JSON
                  </button>

                  <button
                    onClick={() => exportData('csv')}
                    disabled={loading}
                    className="px-4 py-2 bg-orange-600 hover:bg-orange-700 disabled:bg-orange-400 
                             text-white rounded-lg font-medium transition-colors flex items-center"
                  >
                    {loading ? (
                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                    ) : (
                      <Upload className="h-4 w-4 mr-2" />
                    )}
                    Export as CSV
                  </button>
                </div>
              </div>

              {/* Backup List */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white">
                    Available Backups ({backupList.length})
                  </h3>
                  <div className="flex items-center gap-2">
                    {backupList.length > 0 && (
                      <button
                        onClick={deleteAllBackups}
                        disabled={loading}
                        className="px-3 py-1 text-red-600 hover:text-red-700 dark:text-red-400 
                                 dark:hover:text-red-300 font-medium flex items-center text-sm disabled:opacity-50"
                      >
                        <Trash2 className="h-4 w-4 mr-1" />
                        Delete All
                      </button>
                    )}
                    <button
                      onClick={loadBackupList}
                      className="px-3 py-1 text-blue-600 hover:text-blue-700 dark:text-blue-400 
                               dark:hover:text-blue-300 font-medium flex items-center text-sm"
                    >
                      <RefreshCw className="h-4 w-4 mr-1" />
                      Refresh
                    </button>
                  </div>
                </div>
                
                <div className="text-sm text-gray-600 dark:text-gray-400 mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                  <strong>Restore Feature:</strong> Click the <RotateCcw className="h-4 w-4 inline mx-1" /> icon to restore from any backup. 
                  A safety backup of your current database will be automatically created before restoration. 
                  Safety backups are marked with a yellow "Safety" badge.
                </div>

                {backupList.length > 0 ? (
                  <>
                    <div className="overflow-hidden border border-gray-200 dark:border-gray-700 rounded-lg">
                      <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                        <thead className="bg-gray-50 dark:bg-gray-700">
                          <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                              Filename
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                              Size
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                              Created
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                              Type
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                              Format
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                              Actions
                            </th>
                          </tr>
                        </thead>
                        <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                          {currentBackups.map((backup, index) => (
                            <tr key={index}>
                              <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                                <div className="max-w-xs truncate" title={backup.filename}>
                                  {backup.filename}
                                </div>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                {formatBytes(backup.size)}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                {formatDate(backup.created_at)}
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                                  backup.type === 'auto'
                                    ? 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200'
                                    : backup.type === 'safety'
                                    ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200'
                                    : 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200'
                                }`}>
                                  {backup.type === 'auto' ? 'Automatic' : 
                                   backup.type === 'safety' ? 'Safety' : 'Manual'}
                                </span>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap">
                                <span className={`inline-flex px-2 py-1 text-xs font-semibold rounded-full ${
                                  backup.compressed 
                                    ? 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200'
                                    : 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200'
                                }`}>
                                  {backup.compressed ? 'Compressed' : 'Standard'}
                                </span>
                              </td>
                              <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                <div className="flex items-center space-x-2">
                                  <button
                                    onClick={() => restoreBackup(backup.filename)}
                                    disabled={restoringBackup === backup.filename || deletingBackup === backup.filename}
                                    className="text-green-600 hover:text-green-700 dark:text-green-400 
                                             dark:hover:text-green-300 disabled:opacity-50 flex items-center"
                                    title="Restore from this backup"
                                  >
                                    {restoringBackup === backup.filename ? (
                                      <RefreshCw className="h-4 w-4 animate-spin" />
                                    ) : (
                                      <RotateCcw className="h-4 w-4" />
                                    )}
                                  </button>
                                  
                                  <button
                                    onClick={() => deleteBackup(backup.filename)}
                                    disabled={deletingBackup === backup.filename || restoringBackup === backup.filename}
                                    className="text-red-600 hover:text-red-700 dark:text-red-400 
                                             dark:hover:text-red-300 disabled:opacity-50 flex items-center"
                                    title="Delete backup"
                                  >
                                    {deletingBackup === backup.filename ? (
                                      <RefreshCw className="h-4 w-4 animate-spin" />
                                    ) : (
                                      <Trash2 className="h-4 w-4" />
                                    )}
                                  </button>
                                </div>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    
                    {/* Pagination */}
                    {totalPages > 1 && (
                      <div className="flex items-center justify-between mt-4">
                        <div className="text-sm text-gray-500 dark:text-gray-400">
                          Showing {indexOfFirstBackup + 1} to {Math.min(indexOfLastBackup, backupList.length)} of {backupList.length} backups
                        </div>
                        <div className="flex items-center space-x-2">
                          <button
                            onClick={() => paginate(currentPage - 1)}
                            disabled={currentPage === 1}
                            className="px-3 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 
                                     text-gray-700 dark:text-gray-300 rounded-md disabled:opacity-50 disabled:cursor-not-allowed
                                     hover:bg-gray-50 dark:hover:bg-gray-700"
                          >
                            Previous
                          </button>
                          
                          {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
                            <button
                              key={page}
                              onClick={() => paginate(page)}
                              className={`px-3 py-1 text-sm rounded-md ${
                                currentPage === page
                                  ? 'bg-blue-600 text-white'
                                  : 'bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700'
                              }`}
                            >
                              {page}
                            </button>
                          ))}
                          
                          <button
                            onClick={() => paginate(currentPage + 1)}
                            disabled={currentPage === totalPages}
                            className="px-3 py-1 text-sm bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 
                                     text-gray-700 dark:text-gray-300 rounded-md disabled:opacity-50 disabled:cursor-not-allowed
                                     hover:bg-gray-50 dark:hover:bg-gray-700"
                          >
                            Next
                          </button>
                        </div>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-center py-8 border border-gray-200 dark:border-gray-700 rounded-lg">
                    <Archive className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                    <p className="text-gray-500 dark:text-gray-400">No backups available</p>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPanel; 