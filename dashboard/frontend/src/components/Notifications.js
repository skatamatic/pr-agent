import React, { useState, useEffect } from 'react';
import { useToast } from '../contexts/ToastContext';
import { 
  Bell, 
  Plus, 
  Edit, 
  Trash2, 
  Settings, 
  Check, 
  X,
  AlertCircle,
  ChevronDown,
  ChevronRight,
  Save,
  Eye,
  EyeOff,
  Mail,
  MessageSquare,
  TestTube,
  RefreshCw
} from 'lucide-react';
import api from '../services/api';
import ViewHeader from './ViewHeader';

const Notifications = () => {
  const [configs, setConfigs] = useState([]);
  const [events, setEvents] = useState([]);
  const [repositories, setRepositories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [expandedConfig, setExpandedConfig] = useState(null);
  const [editingConfig, setEditingConfig] = useState(null);
  const [activeTab, setActiveTab] = useState('configs');
  const [testingConfig, setTestingConfig] = useState(null);
  const { showToast } = useToast();

  // Form state
  const [formData, setFormData] = useState({
    service_type: 'TEAMS',
    name: '',
    enabled: true,
    webhook_url: '',
    channel: '',
    smtp_server: '',
    smtp_port: 587,
    email_username: '',
    email_password: '',
    recipient_emails: [],
    event_types: ['NEW_JOB', 'JOB_FAILURE'],
    repository_filter: []
  });

  const [originalFormData, setOriginalFormData] = useState(null);
  const [errors, setErrors] = useState({});
  const [newEmail, setNewEmail] = useState('');
  const [showPasswords, setShowPasswords] = useState({});

  // Pagination state for events
  const [eventsPage, setEventsPage] = useState(1);
  const [eventsTotal, setEventsTotal] = useState(0);
  const [eventsPerPage] = useState(20);
  const [eventTypeFilter, setEventTypeFilter] = useState('');
  const [repositoryFilter, setRepositoryFilter] = useState('');

  const eventTypeOptions = [
    { value: 'NEW_JOB', label: 'New Job Created', description: 'When a new PR analysis job starts' },
    { value: 'JOB_FAILURE', label: 'Job Failure', description: 'When a job fails or encounters errors' },
    { value: 'JOB_SUCCESS', label: 'Job Success', description: 'When a job completes successfully' },
    { value: 'SYSTEM_HEALTH_CHANGE', label: 'System Health Change', description: 'When system health status changes' },
    { value: 'HIGH_ERROR_RATE', label: 'High Error Rate', description: 'When error rate exceeds threshold' }
  ];

  useEffect(() => {
    loadConfigs();
    loadEvents();
    loadRepositories();
  }, []);

  // Reload events when filters change
  useEffect(() => {
    if (activeTab === 'events') {
      loadEvents(1);
    }
  }, [eventTypeFilter, repositoryFilter, activeTab]);

  const loadConfigs = async () => {
    try {
      const response = await api.getNotificationConfigs();
      setConfigs(response.data.data || []);
    } catch (error) {
      showToast('Failed to load notification configurations', 'error');
      console.error('Error loading configs:', error);
    }
  };

  const loadRepositories = async () => {
    try {
      const response = await api.get('/api/repositories');
      setRepositories(response.data.data || []);
    } catch (error) {
      console.error('Error loading repositories:', error);
      // Don't show error toast for this as it's not critical
    }
  };

  const loadEvents = async (page = 1) => {
    try {
      const offset = (page - 1) * eventsPerPage;
      const response = await api.getNotificationEvents({ 
        limit: eventsPerPage,
        offset: offset,
        event_type: eventTypeFilter || undefined,
        repository: repositoryFilter || undefined
      });
      setEvents(response.data.data || []);
      setEventsTotal(response.data.total || 0);
      setEventsPage(page);
    } catch (error) {
      showToast('Failed to load notification events', 'error');
      console.error('Error loading events:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = async (e, configId = null) => {
    e.preventDefault();
    setErrors({});

    try {
      const configData = { ...formData };
      
      if (configId) {
        await api.updateNotificationConfig(configId, configData);
        showToast('Notification configuration updated successfully', 'success');
      } else {
        await api.createNotificationConfig(configData);
        showToast('Notification configuration created successfully', 'success');
      }
      
      resetForm();
      loadConfigs();
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to save notification configuration';
      showToast('Failed to save notification configuration', 'error');
      setErrors({ general: errorMsg });
      console.error('Error saving config:', error);
    }
  };

  const handleDeleteConfig = async (config) => {
    if (!window.confirm(`Are you sure you want to delete "${config.name}"?\n\nThis action cannot be undone.`)) {
      return;
    }

    try {
      await api.deleteNotificationConfig(config.id);
      showToast('Notification configuration deleted successfully', 'success');
      // Close expanded view if this config was expanded
      if (expandedConfig === config.id) {
        setExpandedConfig(null);
      }
      loadConfigs();
    } catch (error) {
      showToast('Failed to delete notification configuration', 'error');
      console.error('Error deleting config:', error);
    }
  };

  const handleTestConfig = async (configId) => {
    setTestingConfig(configId);
    try {
      await api.testNotificationConfig(configId, {
        title: 'Test Notification',
        message: 'This is a test notification from PR Agent Dashboard',
        job_id: 'test-job-' + Date.now(),
        repository: 'test/repository',
        status: 'success'
      });
      showToast('Test notification sent successfully', 'success');
      loadConfigs(); // Reload to get updated test status
    } catch (error) {
      showToast('Failed to send test notification', 'error');
      console.error('Error testing config:', error);
    } finally {
      setTestingConfig(null);
    }
  };

  const resetForm = () => {
    setFormData({
      service_type: 'TEAMS',
      name: '',
      enabled: true,
      webhook_url: '',
      channel: '',
      smtp_server: '',
      smtp_port: 587,
      email_username: '',
      email_password: '',
      recipient_emails: [],
      event_types: ['NEW_JOB', 'JOB_FAILURE'],
      repository_filter: []
    });
    setOriginalFormData(null);
    setEditingConfig(null);
    setExpandedConfig(null);
    setShowAddForm(false);
    setErrors({});
    setNewEmail('');
  };

  const toggleExpanded = (configId) => {
    if (expandedConfig === configId) {
      // If currently editing, ask for confirmation
      if (editingConfig === configId && hasChanges()) {
        if (window.confirm('You have unsaved changes. Are you sure you want to close without saving?')) {
          setExpandedConfig(null);
          setEditingConfig(null);
          setFormData({});
          setOriginalFormData(null);
        }
      } else {
        setExpandedConfig(null);
        setEditingConfig(null);
      }
    } else {
      // Single expansion logic - only one config can be expanded at a time
      setExpandedConfig(configId);
      setEditingConfig(null);
      // Load config data for read-only view
      const config = configs.find(c => c.id === configId);
      if (config) {
        const configData = {
          service_type: config.service_type,
          name: config.name,
          enabled: config.enabled,
          webhook_url: config.webhook_url || '',
          channel: config.channel || '',
          smtp_server: config.smtp_server || '',
          smtp_port: config.smtp_port || 587,
          email_username: config.email_username || '',
          email_password: config.email_password || '',
          recipient_emails: config.recipient_emails || [],
          event_types: config.event_types || [],
          repository_filter: config.repository_filter || []
        };
        setFormData(configData);
        setOriginalFormData({...configData});
      }
    }
  };

  const startEdit = (configId) => {
    setEditingConfig(configId);
    // formData is already loaded from toggleExpanded
  };

  const cancelEdit = () => {
    setEditingConfig(null);
    // Restore original form data
    if (originalFormData) {
      setFormData({...originalFormData});
    }
    setErrors({});
  };

  const hasChanges = () => {
    if (!originalFormData) return false;
    return JSON.stringify(formData) !== JSON.stringify(originalFormData);
  };

  const addEmail = () => {
    if (newEmail && !formData.recipient_emails.includes(newEmail)) {
      setFormData(prev => ({
        ...prev,
        recipient_emails: [...prev.recipient_emails, newEmail]
      }));
      setNewEmail('');
    }
  };

  const removeEmail = (email) => {
    setFormData(prev => ({
      ...prev,
      recipient_emails: prev.recipient_emails.filter(e => e !== email)
    }));
  };



  const handleEventTypeChange = (eventType) => {
    setFormData(prev => ({
      ...prev,
      event_types: prev.event_types.includes(eventType)
        ? prev.event_types.filter(type => type !== eventType)
        : [...prev.event_types, eventType]
    }));
  };

  const handleRepositoryFilterChange = (repoName) => {
    setFormData(prev => ({
      ...prev,
      repository_filter: prev.repository_filter.includes(repoName)
        ? prev.repository_filter.filter(repo => repo !== repoName)
        : [...prev.repository_filter, repoName]
    }));
  };

  const handleAllRepositoriesToggle = () => {
    setFormData(prev => ({
      ...prev,
      repository_filter: prev.repository_filter.length === repositories.length ? [] : repositories.map(r => r.name)
    }));
  };

  const togglePasswordVisibility = (configId) => {
    setShowPasswords(prev => ({
      ...prev,
      [configId]: !prev[configId]
    }));
  };

  const getServiceIcon = (serviceType) => {
    switch (serviceType?.toUpperCase()) {
      case 'TEAMS':
        return '🔔';
      case 'SLACK':
        return '💬';
      case 'EMAIL':
        return '📧';
      case 'DISCORD':
        return '🎮';
      default:
        return '📢';
    }
  };

  const getStatusBadge = (status) => {
    const statusConfig = {
      success: 'bg-green-100 text-green-800 dark:bg-green-900/20 dark:text-green-400',
      error: 'bg-red-100 text-red-800 dark:bg-red-900/20 dark:text-red-400',
      pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/20 dark:text-yellow-400'
    };

    return (
      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
        statusConfig[status] || statusConfig.pending
      }`}>
        {status?.toUpperCase() || 'PENDING'}
      </span>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <ViewHeader 
        title="Notification Settings"
        subtitle="Configure notification channels for PR Agent events"
        icon={Bell}
        rightComponent={
          activeTab === 'configs' ? (
            <button
              onClick={() => setShowAddForm(true)}
              className="flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 dark:bg-blue-700 rounded-lg hover:bg-blue-700 dark:hover:bg-blue-600 transition-colors duration-200 shadow-sm hover:shadow-md"
            >
              <Plus className="h-4 w-4 mr-2" />
              Add Configuration
            </button>
          ) : null
        }
      />

      {/* Tab Navigation */}
      <div className="flex space-x-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
        <button
          onClick={() => setActiveTab('configs')}
          className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'configs'
              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          <Settings className="h-4 w-4 mr-2" />
          Configurations
        </button>
        <button
          onClick={() => setActiveTab('events')}
          className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'events'
              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          <Bell className="h-4 w-4 mr-2" />
          Events
        </button>
      </div>

      {/* Configuration Form Modal */}
      {showAddForm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 dark:bg-black dark:bg-opacity-70 flex items-center justify-center z-[9999] p-4">
          <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl max-w-2xl w-full max-h-[90vh] overflow-y-auto border border-gray-200 dark:border-gray-700">
            <div className="p-6">
              <div className="flex justify-between items-center mb-6">
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                  Add Notification Configuration
                </h2>
                <button
                  onClick={resetForm}
                  className="text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 transition-colors duration-200"
                >
                  <span className="text-2xl">×</span>
                </button>
              </div>

              <form onSubmit={(e) => handleSaveConfig(e)} className="space-y-6">
                {/* Basic Settings */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Service Type
                    </label>
                    <select
                      value={formData.service_type}
                      onChange={(e) => setFormData(prev => ({ ...prev, service_type: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      required
                    >
                      <option value="TEAMS">Microsoft Teams</option>
                      <option value="SLACK">Slack</option>
                      <option value="EMAIL">Email</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Configuration Name
                    </label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                      className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      placeholder="e.g., Dev Team Notifications"
                      required
                    />
                  </div>
                </div>

                {/* Service-specific Configuration */}
                {(formData.service_type === 'TEAMS' || formData.service_type === 'SLACK') && (
                  <div className="space-y-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Webhook URL
                      </label>
                      <input
                        type="url"
                        value={formData.webhook_url}
                        onChange={(e) => setFormData(prev => ({ ...prev, webhook_url: e.target.value }))}
                        className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                        placeholder="https://..."
                        required
                      />
                    </div>

                    {formData.service_type === 'SLACK' && (
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Channel (optional)
                        </label>
                        <input
                          type="text"
                          value={formData.channel}
                          onChange={(e) => setFormData(prev => ({ ...prev, channel: e.target.value }))}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="#general"
                        />
                      </div>
                    )}
                  </div>
                )}

                {formData.service_type === 'EMAIL' && (
                  <div className="space-y-4">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          SMTP Server
                        </label>
                        <input
                          type="text"
                          value={formData.smtp_server}
                          onChange={(e) => setFormData(prev => ({ ...prev, smtp_server: e.target.value }))}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="smtp.gmail.com"
                          required
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          SMTP Port
                        </label>
                        <input
                          type="number"
                          value={formData.smtp_port}
                          onChange={(e) => setFormData(prev => ({ ...prev, smtp_port: parseInt(e.target.value) }))}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          required
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Username
                        </label>
                        <input
                          type="text"
                          value={formData.email_username}
                          onChange={(e) => setFormData(prev => ({ ...prev, email_username: e.target.value }))}
                          className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          required
                        />
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Password
                        </label>
                        <div className="relative">
                          <input
                            type={showPasswords[formData.id] ? 'text' : 'password'}
                            value={formData.email_password}
                            onChange={(e) => setFormData(prev => ({ ...prev, email_password: e.target.value }))}
                            className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                            required
                          />
                          <button
                            type="button"
                            onClick={() => togglePasswordVisibility(formData.id)}
                            className="absolute inset-y-0 right-0 pr-3 flex items-center text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                          >
                            {showPasswords[formData.id] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Recipient Emails */}
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Recipient Emails
                      </label>
                      <div className="flex gap-2 mb-2">
                        <input
                          type="email"
                          value={newEmail}
                          onChange={(e) => setNewEmail(e.target.value)}
                          className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                          placeholder="user@example.com"
                          onKeyPress={(e) => e.key === 'Enter' && (e.preventDefault(), addEmail())}
                        />
                        <button
                          type="button"
                          onClick={addEmail}
                          className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600 text-white rounded-lg transition-colors duration-200"
                        >
                          Add
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {formData.recipient_emails.map((email, index) => (
                          <span
                            key={index}
                            className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 px-3 py-1 rounded-full text-sm flex items-center gap-2"
                          >
                            {email}
                            <button
                              type="button"
                              onClick={() => removeEmail(email)}
                              className="text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300"
                            >
                              ×
                            </button>
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Event Types */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                    Event Types to Monitor
                  </label>
                  <div className="space-y-2">
                    {eventTypeOptions.map((option) => (
                      <label key={option.value} className="flex items-start gap-3 p-3 border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700/50 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.event_types.includes(option.value)}
                          onChange={() => handleEventTypeChange(option.value)}
                          className="mt-1 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700"
                        />
                        <div>
                          <div className="font-medium text-gray-900 dark:text-white">{option.label}</div>
                          <div className="text-sm text-gray-600 dark:text-gray-400">{option.description}</div>
                        </div>
                      </label>
                    ))}
                  </div>
                </div>

                {/* Repository Filter */}
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Repository Filter (optional)
                  </label>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                    Select specific repositories to monitor, or leave all unchecked to receive notifications for all repositories.
                  </p>
                  
                  {repositories.length > 0 ? (
                    <div className="space-y-3">
                      {/* All Repositories Toggle */}
                      <label className="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700/50 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={formData.repository_filter.length === repositories.length}
                          onChange={handleAllRepositoriesToggle}
                          className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700"
                        />
                        <div>
                          <div className="font-medium text-gray-900 dark:text-white">All Repositories</div>
                          <div className="text-sm text-gray-600 dark:text-gray-400">Monitor all {repositories.length} repositories</div>
                        </div>
                      </label>
                      
                      {/* Individual Repository Toggles */}
                      <div className="space-y-2 max-h-48 overflow-y-auto">
                        {repositories.map((repo) => (
                          <label key={repo.id} className="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-700/50 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer">
                            <input
                              type="checkbox"
                              checked={formData.repository_filter.includes(repo.name)}
                              onChange={() => handleRepositoryFilterChange(repo.name)}
                              className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700"
                            />
                            <div className="flex-1">
                              <div className="font-medium text-gray-900 dark:text-white">{repo.name}</div>
                              <div className="text-sm text-gray-600 dark:text-gray-400 flex items-center gap-2">
                                <span className="capitalize">{repo.provider.replace('_', ' ')}</span>
                                {repo.is_active && <span className="text-green-600 dark:text-green-400">• Active</span>}
                              </div>
                            </div>
                          </label>
                        ))}
                      </div>
                    </div>
                  ) : (
                    <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                      <p>No repositories configured yet.</p>
                      <p className="text-sm mt-1">Add repositories in the Repository Manager first.</p>
                    </div>
                  )}
                </div>

                {/* Enable/Disable */}
                <div className="flex items-center gap-3">
                  <input
                    type="checkbox"
                    id="enabled"
                    checked={formData.enabled}
                    onChange={(e) => setFormData(prev => ({ ...prev, enabled: e.target.checked }))}
                    className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700"
                  />
                  <label htmlFor="enabled" className="font-medium text-gray-900 dark:text-white">
                    Enable this configuration
                  </label>
                </div>

                {/* Form Actions */}
                <div className="flex justify-end gap-3 pt-4 border-t border-gray-200 dark:border-gray-600">
                  <button
                    type="button"
                    onClick={resetForm}
                    className="px-4 py-2 text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg font-medium transition-colors duration-200"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 bg-blue-600 hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600 text-white rounded-lg font-medium transition-colors duration-200"
                  >
                    {formData.id ? 'Update Configuration' : 'Create Configuration'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Content Tabs */}
      {activeTab === 'configs' && (
        <div className="space-y-4 tab-enter">
          {configs.length === 0 ? (
            <div className="text-center py-12 bg-gray-50 dark:bg-gray-900 rounded-lg">
              <div className="text-4xl mb-4">🔔</div>
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No notification configurations</h3>
              <p className="text-gray-600 dark:text-gray-400 mb-4">Get started by creating your first notification configuration.</p>
              <button
                onClick={() => setShowAddForm(true)}
                className="bg-blue-600 hover:bg-blue-700 dark:bg-blue-700 dark:hover:bg-blue-600 text-white px-4 py-2 rounded-lg font-medium transition-colors duration-200"
              >
                Add Configuration
              </button>
            </div>
          ) : (
            <div className="space-y-4">
              {configs.map((config) => (
                <div key={config.id} 
                     className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden transition-all duration-300 ease-in-out hover:shadow-lg">
                  
                  {/* Configuration Header - Clickable */}
                  <div 
                    className={`p-6 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors duration-200 ${
                      expandedConfig === config.id ? 'bg-blue-50 dark:bg-blue-900/20' : ''
                    }`}
                    onClick={() => toggleExpanded(config.id)}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center space-x-4">
                        <div className="flex items-center space-x-2">
                          {expandedConfig === config.id ? (
                            <ChevronDown className="h-5 w-5 text-gray-400 transform transition-all duration-300 ease-in-out" />
                          ) : (
                            <ChevronRight className="h-5 w-5 text-gray-400 transform transition-all duration-300 ease-in-out" />
                          )}
                          <div className="text-2xl">{getServiceIcon(config.service_type)}</div>
                        </div>
                        
                        <div className="flex-1">
                          <div className="flex items-center gap-3">
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{config.name}</h3>
                            <span className="px-2.5 py-1 bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-full text-xs font-medium">
                              {config.service_type}
                            </span>
                            {!config.enabled && (
                              <span className="px-2.5 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 rounded-full text-xs font-medium">
                                Disabled
                              </span>
                            )}
                            {config.enabled && (
                              <span className="px-2.5 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300 rounded-full text-xs font-medium">
                                Active
                              </span>
                            )}
                          </div>
                          
                          <div className="flex items-center space-x-4 mt-2 text-sm text-gray-500 dark:text-gray-400">
                            <span>{config.event_types?.length || 0} events</span>
                            {config.repository_filter?.length > 0 && (
                              <span>{config.repository_filter.length} repos</span>
                            )}
                            {config.last_test && (
                              <div className="flex items-center gap-2">
                                <span>Last test:</span>
                                {getStatusBadge(config.test_status)}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>

                      <div className="flex items-center space-x-2" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => handleTestConfig(config.id)}
                          disabled={testingConfig === config.id}
                          className="flex items-center px-3 py-1.5 text-sm font-medium text-purple-600 bg-purple-50 dark:bg-purple-900/30 dark:text-purple-400 rounded-lg hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors duration-200 disabled:opacity-50"
                        >
                          {testingConfig === config.id ? (
                            <RefreshCw className="h-4 w-4 mr-1 animate-spin" />
                          ) : (
                            <TestTube className="h-4 w-4 mr-1" />
                          )}
                          Test
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {expandedConfig === config.id && (
                    <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 rounded-b-lg">
                      <div className="p-6 space-y-6 animate-expand">
                        {/* Action Buttons */}
                        <div className="flex items-center justify-between">
                          <h4 className="text-lg font-medium text-gray-900 dark:text-white">Configuration Details</h4>
                          <div className="flex items-center space-x-3">
                            {editingConfig !== config.id ? (
                              <>
                                <button
                                  onClick={() => startEdit(config.id)}
                                  className="flex items-center px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 dark:bg-blue-900/30 dark:text-blue-400 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors duration-200"
                                >
                                  <Edit className="h-4 w-4 mr-2" />
                                  Edit
                                </button>
                                <button
                                  onClick={() => handleDeleteConfig(config)}
                                  className="flex items-center px-4 py-2 text-sm font-medium text-red-600 bg-red-50 dark:bg-red-900/30 dark:text-red-400 rounded-lg hover:bg-red-100 dark:hover:bg-red-900/50 transition-colors duration-200"
                                >
                                  <Trash2 className="h-4 w-4 mr-2" />
                                  Delete
                                </button>
                              </>
                            ) : (
                              <>
                                <button
                                  onClick={cancelEdit}
                                  className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-600 border border-gray-300 dark:border-gray-500 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-500 hover:border-gray-400 dark:hover:border-gray-400 transition-colors duration-200 shadow-sm"
                                >
                                  <X className="h-4 w-4 mr-2" />
                                  Cancel
                                </button>
                                <button
                                  onClick={(e) => handleSaveConfig(e, config.id)}
                                  disabled={!hasChanges()}
                                  className={`flex items-center px-4 py-2 text-sm font-medium rounded-lg transition-colors duration-200 ${
                                    hasChanges()
                                      ? 'text-white bg-blue-600 hover:bg-blue-700 shadow-sm hover:shadow-md'
                                      : 'text-gray-400 bg-gray-100 dark:bg-gray-700 cursor-not-allowed'
                                  }`}
                                >
                                  <Save className="h-4 w-4 mr-2" />
                                  Save Changes
                                </button>
                              </>
                            )}
                          </div>
                        </div>

                        {/* Error Message */}
                        {errors.general && editingConfig === config.id && (
                          <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                            <div className="flex items-center">
                              <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
                              <span className="text-red-800 dark:text-red-200 text-sm font-medium">{errors.general}</span>
                            </div>
                          </div>
                        )}

                        {/* Configuration Fields */}
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                          {/* Basic Information */}
                          <div className="space-y-4">
                            <h5 className="text-sm font-medium text-gray-900 dark:text-white">Basic Information</h5>
                            
                            {/* Name */}
                            <div>
                              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Configuration Name
                              </label>
                              {editingConfig === config.id ? (
                                <input
                                  type="text"
                                  value={formData.name}
                                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                                  className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                                />
                              ) : (
                                <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                                  <span className="text-gray-900 dark:text-white font-medium">{config.name}</span>
                                </div>
                              )}
                            </div>

                            {/* Service Type */}
                            <div>
                              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Service Type
                              </label>
                              {editingConfig === config.id ? (
                                <select
                                  value={formData.service_type}
                                  onChange={(e) => setFormData({ ...formData, service_type: e.target.value })}
                                  className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                                >
                                  <option value="TEAMS">Microsoft Teams</option>
                                  <option value="SLACK">Slack</option>
                                  <option value="EMAIL">Email</option>
                                  <option value="DISCORD">Discord</option>
                                </select>
                              ) : (
                                <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                                  <div className="flex items-center">
                                    <span className="mr-2">{getServiceIcon(config.service_type)}</span>
                                    <span className="text-gray-900 dark:text-white font-medium">{config.service_type}</span>
                                  </div>
                                </div>
                              )}
                            </div>

                            {/* Enabled Status */}
                            <div>
                              <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Status
                              </label>
                              {editingConfig === config.id ? (
                                <label className="flex items-center p-4 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer transition-all duration-200">
                                  <input
                                    type="checkbox"
                                    checked={formData.enabled}
                                    onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                                    className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                                  />
                                  <div>
                                    <div className="text-sm font-medium text-gray-900 dark:text-white">Enable Configuration</div>
                                    <div className="text-xs text-gray-500 dark:text-gray-400">When enabled, notifications will be sent through this configuration</div>
                                  </div>
                                </label>
                              ) : (
                                <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                                  <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                                    config.enabled 
                                      ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                                      : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                                  }`}>
                                    {config.enabled ? 'Enabled' : 'Disabled'}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>

                          {/* Service Configuration */}
                          <div className="space-y-4">
                            <h5 className="text-sm font-medium text-gray-900 dark:text-white">Service Configuration</h5>
                            
                            {/* Service-specific fields */}
                            {((editingConfig === config.id ? formData.service_type : config.service_type) === 'EMAIL') && (
                              <>
                                <div>
                                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    SMTP Server
                                  </label>
                                  {editingConfig === config.id ? (
                                    <input
                                      type="text"
                                      value={formData.smtp_server}
                                      onChange={(e) => setFormData({ ...formData, smtp_server: e.target.value })}
                                      className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                                      placeholder="smtp.gmail.com"
                                    />
                                  ) : (
                                    <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                                      <span className="text-gray-900 dark:text-white">{config.smtp_server || 'Not configured'}</span>
                                    </div>
                                  )}
                                </div>

                                <div>
                                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Username & Password
                                  </label>
                                  {editingConfig === config.id ? (
                                    <div className="grid grid-cols-2 gap-4">
                                      <input
                                        type="text"
                                        value={formData.email_username}
                                        onChange={(e) => setFormData({ ...formData, email_username: e.target.value })}
                                        className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                                        placeholder="username@domain.com"
                                      />
                                      <div className="relative">
                                        <input
                                          type={showPasswords[config.id] ? 'text' : 'password'}
                                          value={formData.email_password}
                                          onChange={(e) => setFormData({ ...formData, email_password: e.target.value })}
                                          className="w-full px-4 py-3 pr-12 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                                          placeholder="password"
                                        />
                                        <button
                                          type="button"
                                          onClick={() => togglePasswordVisibility(config.id)}
                                          className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                                        >
                                          {showPasswords[config.id] ? 
                                            <EyeOff className="h-4 w-4" /> : 
                                            <Eye className="h-4 w-4" />
                                          }
                                        </button>
                                      </div>
                                    </div>
                                  ) : (
                                    <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                                      <div className="space-y-1">
                                        <div><span className="font-medium">Username:</span> {config.email_username || 'Not configured'}</div>
                                        <div><span className="font-medium">Password:</span> {config.email_password ? '••••••••' : 'Not configured'}</div>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </>
                            )}

                            {/* Webhook URL for non-email services */}
                            {((editingConfig === config.id ? formData.service_type : config.service_type) !== 'EMAIL') && (
                              <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                  Webhook URL
                                </label>
                                {editingConfig === config.id ? (
                                  <input
                                    type="url"
                                    value={formData.webhook_url}
                                    onChange={(e) => setFormData({ ...formData, webhook_url: e.target.value })}
                                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                                    placeholder="https://hooks.slack.com/services/..."
                                  />
                                ) : (
                                  <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                                    <span className="text-gray-900 dark:text-white break-all">
                                      {config.webhook_url ? 
                                        (config.webhook_url.length > 60 ? 
                                          config.webhook_url.substring(0, 60) + '...' : 
                                          config.webhook_url
                                        ) : 
                                        'Not configured'
                                      }
                                    </span>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        </div>

                        {/* Event Types */}
                        <div>
                          <label className="block text-sm font-medium text-gray-900 dark:text-white mb-3">
                            Event Types to Monitor
                          </label>
                          {editingConfig === config.id ? (
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                              {eventTypeOptions.map((option) => (
                                <label key={option.value} className="flex items-start gap-3 p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer transition-colors">
                                  <input
                                    type="checkbox"
                                    checked={formData.event_types.includes(option.value)}
                                    onChange={() => handleEventTypeChange(option.value)}
                                    className="mt-1 h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded"
                                  />
                                  <div>
                                    <div className="font-medium text-gray-900 dark:text-white">{option.label}</div>
                                    <div className="text-sm text-gray-600 dark:text-gray-400">{option.description}</div>
                                  </div>
                                </label>
                              ))}
                            </div>
                          ) : (
                            <div className="flex flex-wrap gap-2">
                              {config.event_types?.map((eventType) => {
                                const option = eventTypeOptions.find(opt => opt.value === eventType);
                                return (
                                  <span key={eventType} className="px-3 py-1 bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 rounded-full text-sm font-medium">
                                    {option?.label || eventType}
                                  </span>
                                );
                              }) || (
                                <span className="text-gray-500 dark:text-gray-400 italic">No events configured</span>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Repository Filter */}
                        <div>
                          <label className="block text-sm font-medium text-gray-900 dark:text-white mb-3">
                            Repository Filter
                          </label>
                          {editingConfig === config.id ? (
                            <div>
                              <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                                Select specific repositories to monitor, or leave all unchecked to receive notifications for all repositories.
                              </p>
                              
                              {repositories.length > 0 ? (
                                <div className="space-y-3">
                                  {/* All Repositories Toggle */}
                                  <label className="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer">
                                    <input
                                      type="checkbox"
                                      checked={formData.repository_filter.length === repositories.length}
                                      onChange={handleAllRepositoriesToggle}
                                      className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded"
                                    />
                                    <div>
                                      <div className="font-medium text-gray-900 dark:text-white">All Repositories</div>
                                      <div className="text-sm text-gray-600 dark:text-gray-400">Monitor all {repositories.length} repositories</div>
                                    </div>
                                  </label>
                                  
                                  {/* Individual Repository Toggles */}
                                  <div className="space-y-2 max-h-48 overflow-y-auto">
                                    {repositories.map((repo) => (
                                      <label key={repo.id} className="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer">
                                        <input
                                          type="checkbox"
                                          checked={formData.repository_filter.includes(repo.name)}
                                          onChange={() => handleRepositoryFilterChange(repo.name)}
                                          className="h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 dark:border-gray-600 rounded"
                                        />
                                        <div className="flex-1">
                                          <div className="font-medium text-gray-900 dark:text-white">{repo.name}</div>
                                          <div className="text-sm text-gray-600 dark:text-gray-400 flex items-center gap-2">
                                            <span className="capitalize">{repo.provider.replace('_', ' ')}</span>
                                            {repo.is_active && <span className="text-green-600 dark:text-green-400">• Active</span>}
                                          </div>
                                        </div>
                                      </label>
                                    ))}
                                  </div>
                                </div>
                              ) : (
                                <div className="text-center py-8 text-gray-500 dark:text-gray-400">
                                  <p>No repositories configured yet.</p>
                                  <p className="text-sm mt-1">Add repositories in the Repository Manager first.</p>
                                </div>
                              )}
                            </div>
                          ) : (
                            <div>
                              {config.repository_filter?.length > 0 ? (
                                <div className="flex flex-wrap gap-2">
                                  {config.repository_filter.map((repo, index) => (
                                    <span key={index} className="px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-300 rounded-full text-sm font-medium">
                                      {repo}
                                    </span>
                                  ))}
                                </div>
                              ) : (
                                <span className="text-gray-500 dark:text-gray-400 italic">All repositories</span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'events' && (
        <div className="space-y-4 tab-enter">
          {/* Filters */}
          <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4">
            <div className="flex flex-wrap gap-4">
              <div className="flex-1 min-w-48">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Event Type
                </label>
                <select
                  value={eventTypeFilter}
                  onChange={(e) => setEventTypeFilter(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                >
                  <option value="">All Event Types</option>
                  {eventTypeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex-1 min-w-48">
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                  Repository
                </label>
                <input
                  type="text"
                  value={repositoryFilter}
                  onChange={(e) => setRepositoryFilter(e.target.value)}
                  placeholder="Filter by repository..."
                  className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              </div>
              <div className="flex items-end">
                <button
                  onClick={() => {
                    setEventTypeFilter('');
                    setRepositoryFilter('');
                  }}
                  className="px-4 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-700 rounded-lg font-medium transition-colors duration-200"
                >
                  Clear Filters
                </button>
              </div>
            </div>
          </div>

          {events.length === 0 ? (
            <div className="text-center py-12 bg-gray-50 dark:bg-gray-900 rounded-lg">
              <div className="mx-auto w-16 h-16 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-4">
                <Bell className="h-8 w-8 text-gray-400 dark:text-gray-500" />
              </div>
              <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No notification events</h3>
              <p className="text-gray-600 dark:text-gray-400">
                {eventTypeFilter || repositoryFilter 
                  ? 'No events match your current filters.' 
                  : 'Notification events will appear here once they are triggered.'}
              </p>
            </div>
          ) : (
            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                  <thead className="bg-gray-50 dark:bg-gray-900">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Event Type
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Repository
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Timestamp
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                        Services
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                    {events.map((event) => (
                      <tr key={event.id} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                        <td className="px-6 py-4 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900 dark:text-white">{event.event_type}</div>
                          <div className="text-sm text-gray-500 dark:text-gray-400">
                            {event.event_data?.title || 'No title'}
                          </div>
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-900 dark:text-white">
                          {event.repositories?.join(', ') || 'All'}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {new Date(event.timestamp).toLocaleString()}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap">
                          {getStatusBadge(event.processed ? 'success' : 'pending')}
                        </td>
                        <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                          {event.sent_to_services?.length || 0} services
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              
              {/* Pagination Controls */}
              {eventsTotal > eventsPerPage && (
                <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex items-center justify-between">
                  <div className="text-sm text-gray-500 dark:text-gray-400">
                    Showing {((eventsPage - 1) * eventsPerPage) + 1} to {Math.min(eventsPage * eventsPerPage, eventsTotal)} of {eventsTotal} events
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => loadEvents(eventsPage - 1)}
                      disabled={eventsPage === 1}
                      className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Previous
                    </button>
                    <span className="text-sm text-gray-600 dark:text-gray-400">
                      Page {eventsPage} of {Math.ceil(eventsTotal / eventsPerPage)}
                    </span>
                    <button
                      onClick={() => loadEvents(eventsPage + 1)}
                      disabled={eventsPage >= Math.ceil(eventsTotal / eventsPerPage)}
                      className="px-3 py-1 text-sm border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Next
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default Notifications; 