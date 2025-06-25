import React, { useState, useEffect, useContext } from 'react';
import { 
  Plus, 
  Edit, 
  Trash2, 
  GitBranch, 
  Globe, 
  Settings, 
  Check, 
  X,
  AlertCircle,
  Info,
  Github,
  Cloud,
  ChevronDown,
  ChevronRight,
  Save,
  RotateCcw,
  Activity,
  RefreshCw,
  Clock,
  CheckCircle,
  FileText,
  Eye,
  ExternalLink,
  Key,
  EyeOff,
  Shield
} from 'lucide-react';
import api from '../services/api';
import { ToastContext } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';

const RepositoryManager = () => {
  const [repositories, setRepositories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [expandedRepo, setExpandedRepo] = useState(null);
  const [editingRepo, setEditingRepo] = useState(null);
  const [formData, setFormData] = useState({
    name: '',
    provider: 'github',
    url: '',
    is_active: true,
    monitor_prs: true,
    monitor_issues: false,
    auto_review: true,
    auto_describe: true,
    auto_improve: false,
    github_token: '',
    azure_pat: ''
  });
  const [originalFormData, setOriginalFormData] = useState(null);
  const [errors, setErrors] = useState({});
  const [checkingHealth, setCheckingHealth] = useState(new Set());
  const [checkingConfig, setCheckingConfig] = useState(new Set());
  const [viewingConfig, setViewingConfig] = useState(null);
  const [effectiveConfig, setEffectiveConfig] = useState(null);
  const [showTokens, setShowTokens] = useState({});
  const [expandedTokenSections, setExpandedTokenSections] = useState(new Set());
  const { showSuccess, showError } = useContext(ToastContext);

  useEffect(() => {
    fetchRepositories();
  }, []);

  const fetchRepositories = async () => {
    try {
      setLoading(true);
      const response = await api.getRepositories();
      setRepositories(response.data.data || []);
    } catch (error) {
      showError('Error', 'Failed to fetch repositories');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e, repoId = null) => {
    e.preventDefault();
    setErrors({});

    try {
      if (repoId) {
        await api.updateRepository(repoId, formData);
        showSuccess('Success', 'Repository updated successfully');
      } else {
        await api.createRepository(formData);
        showSuccess('Success', 'Repository added successfully');
      }
      
      resetForm();
      fetchRepositories();
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to save repository';
      showError('Error', errorMsg);
      setErrors({ general: errorMsg });
    }
  };

  const handleDelete = async (repo) => {
    if (window.confirm(`Are you sure you want to delete repository "${repo.name}"?\n\nThis action cannot be undone.`)) {
      try {
        await api.deleteRepository(repo.id);
        showSuccess('Success', 'Repository deleted successfully');
        // Close expanded view if this repo was expanded
        if (expandedRepo === repo.id) {
          setExpandedRepo(null);
        }
        fetchRepositories();
      } catch (error) {
        showError('Error', 'Failed to delete repository');
      }
    }
  };

  const resetForm = () => {
    setFormData({
      name: '',
      provider: 'github',
      url: '',
      is_active: true,
      monitor_prs: true,
      monitor_issues: false,
      auto_review: true,
      auto_describe: true,
      auto_improve: false,
      github_token: '',
      azure_pat: ''
    });
    setOriginalFormData(null);
    setEditingRepo(null);
    setExpandedRepo(null);
    setShowAddForm(false);
    setErrors({});
  };

  const toggleExpanded = (repoId) => {
    if (expandedRepo === repoId) {
      // If currently editing, ask for confirmation
      if (editingRepo === repoId && hasChanges()) {
        if (window.confirm('You have unsaved changes. Are you sure you want to close without saving?')) {
          setExpandedRepo(null);
          setEditingRepo(null);
          setFormData({});
          setOriginalFormData(null);
        }
      } else {
        setExpandedRepo(null);
        setEditingRepo(null);
      }
    } else {
      // Single expansion logic - only one repo can be expanded at a time
      setExpandedRepo(repoId);
      setEditingRepo(null);
      // Load repo data for read-only view
      const repo = repositories.find(r => r.id === repoId);
      if (repo) {
        const repoData = {
          name: repo.name,
          provider: repo.provider,
          url: repo.url,
          is_active: repo.is_active,
          monitor_prs: repo.monitor_prs,
          monitor_issues: repo.monitor_issues,
          auto_review: repo.auto_review,
          auto_describe: repo.auto_describe,
          auto_improve: repo.auto_improve,
          github_token: repo.github_token || '',
          azure_pat: repo.azure_pat || ''
        };
        setFormData(repoData);
        setOriginalFormData({...repoData});
      }
    }
  };

  const startEdit = (repoId) => {
    setEditingRepo(repoId);
    // formData is already loaded from toggleExpanded
  };

  const cancelEdit = () => {
    setEditingRepo(null);
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

  const checkRunnerHealth = async (repoId) => {
    setCheckingHealth(prev => new Set(prev).add(repoId));
    try {
      const response = await api.post(`/repositories/${repoId}/check-health`);
      showSuccess('Success', 'Runner health check completed');
      fetchRepositories(); // Refresh to get updated health status
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to check runner health';
      showError('Error', errorMsg);
    } finally {
      setCheckingHealth(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  const checkRepositoryConfig = async (repoId) => {
    setCheckingConfig(prev => new Set(prev).add(repoId));
    try {
      const response = await api.post(`/repositories/${repoId}/check-config`);
      showSuccess('Success', 'Configuration check completed');
      fetchRepositories(); // Refresh to get updated config status
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to check repository configuration';
      showError('Error', errorMsg);
    } finally {
      setCheckingConfig(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  const viewEffectiveConfig = async (repoId) => {
    try {
      const response = await api.get(`/repositories/${repoId}/effective-config`);
      setEffectiveConfig(response.data.data);
      setViewingConfig(repoId);
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to load effective configuration';
      showError('Error', errorMsg);
    }
  };

  const closeConfigViewer = () => {
    setViewingConfig(null);
    setEffectiveConfig(null);
  };

  const getConfigStatusIcon = (repo) => {
    if (repo.has_pr_agent_config === true) {
      return <FileText className="h-4 w-4 text-green-600" />;
    } else if (repo.has_pr_agent_config === false) {
      return <FileText className="h-4 w-4 text-gray-400" />;
    }
    return <FileText className="h-4 w-4 text-gray-300" />;
  };

  const getConfigStatusText = (repo) => {
    // Only show config status if we've actually checked
    if (repo.config_last_checked) {
      if (repo.has_pr_agent_config === true) {
        return 'Has .pr_agent.toml';
      } else if (repo.has_pr_agent_config === false) {
        return 'Uses default config';
      }
    }
    return 'Config not checked';
  };

  const shouldShowConfigStatus = (repo) => {
    // Only show config status if we have tokens configured (needed for checking)
    return getTokenStatus(repo) === 'configured';
  };

  const formatLastChecked = (timestamp) => {
    if (!timestamp) return 'Never';
    try {
      return new Date(timestamp).toLocaleString();
    } catch (e) {
      return 'Invalid date';
    }
  };

  const toggleTokenVisibility = (repoId, tokenType) => {
    const key = `${repoId}-${tokenType}`;
    setShowTokens(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const maskToken = (token) => {
    if (!token) return '';
    if (token.length <= 8) return '•'.repeat(token.length);
    return token.substring(0, 4) + '•'.repeat(Math.max(token.length - 8, 4)) + token.substring(token.length - 4);
  };

  const getTokenVisibilityKey = (repoId, tokenType) => {
    return `${repoId || 'new'}-${tokenType}`;
  };

  const isTokenVisible = (repoId, tokenType) => {
    const key = getTokenVisibilityKey(repoId, tokenType);
    return showTokens[key] || false;
  };

  const getTokenStatus = (repo) => {
    if (repo.provider === 'github') {
      return repo.github_token ? 'configured' : 'missing';
    } else if (repo.provider === 'azure_devops') {
      return repo.azure_pat ? 'configured' : 'missing';
    }
    return 'unknown';
  };

  const shouldExpandTokenSection = (repo) => {
    // Auto-expand if token is missing or if there are authentication errors
    const tokenStatus = getTokenStatus(repo);
    const hasAuthError = repo.runner_error && (
      repo.runner_error.includes('token') || 
      repo.runner_error.includes('authentication') || 
      repo.runner_error.includes('invalid') || 
      repo.runner_error.includes('expired') ||
      repo.runner_error.includes('permissions')
    );
    
    return tokenStatus === 'missing' || hasAuthError;
  };

  const toggleTokenSection = (repoId) => {
    setExpandedTokenSections(prev => {
      const newSet = new Set(prev);
      if (newSet.has(repoId)) {
        newSet.delete(repoId);
      } else {
        newSet.add(repoId);
      }
      return newSet;
    });
  };

  const isTokenSectionExpanded = (repoId) => {
    return expandedTokenSections.has(repoId) || shouldExpandTokenSection(repositories.find(r => r.id === repoId));
  };

  const getTokenStatusIcon = (status) => {
    switch (status) {
      case 'configured':
        return <Shield className="h-4 w-4 text-green-600 dark:text-green-400" />;
      case 'missing':
        return <Shield className="h-4 w-4 text-red-600 dark:text-red-400" />;
      default:
        return <Shield className="h-4 w-4 text-gray-400" />;
    }
  };

  const getTokenStatusText = (status, provider) => {
    switch (status) {
      case 'configured':
        return `${provider === 'github' ? 'GitHub token' : 'Azure PAT'} configured`;
      case 'missing':
        return `${provider === 'github' ? 'GitHub token' : 'Azure PAT'} required`;
      default:
        return 'Token status unknown';
    }
  };

  const getProviderIcon = (provider) => {
    switch (provider) {
      case 'github':
        return <Github className="h-4 w-4" />;
      case 'azure_devops':
        return <Cloud className="h-4 w-4" />;
      default:
        return <GitBranch className="h-4 w-4" />;
    }
  };

  const getProviderColor = (provider) => {
    switch (provider) {
      case 'github':
        return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
      case 'azure_devops':
        return 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200';
    }
  };

  const getRunnerStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return CheckCircle;
      case 'stopped':
        return X;
      case 'error':
        return AlertCircle;
      case 'misconfigured':
        return Settings;
      default:
        return Clock;
    }
  };

  const getRunnerStatusColor = (status) => {
    switch (status) {
      case 'running':
        return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
      case 'stopped':
        return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
      case 'error':
        return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
      case 'misconfigured':
        return 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
    }
  };

  const formatRunnerStatus = (status) => {
    switch (status) {
      case 'running':
        return 'Running';
      case 'stopped':
        return 'Stopped';
      case 'error':
        return 'Error';
      case 'misconfigured':
        return 'Config Issue';
      default:
        return 'Unknown';
    }
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
      {/* Header */}
      <ViewHeader 
        title="Repository Management"
        subtitle="Configure which repositories PR-Agent monitors and manages"
        icon={GitBranch}
        rightComponent={
          <button
            onClick={() => setShowAddForm(true)}
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors duration-200 shadow-sm hover:shadow-md"
          >
            <Plus className="h-4 w-4 mr-2" />
            Add Repository
          </button>
        }
      />

      {/* Info Card */}
      <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
        <div className="flex items-start">
          <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
          <div className="text-blue-800 dark:text-blue-200 text-sm">
            <p className="font-medium mb-1">Repository Monitoring</p>
            <p>Click on any repository to view its configuration. Use the edit button to modify settings. Only active repositories will be monitored for pull requests and issues.</p>
          </div>
        </div>
      </div>

      {/* Add Repository Form */}
      {showAddForm && (
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-lg overflow-hidden">
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/30 dark:to-indigo-900/30 px-6 py-4 border-b border-gray-200 dark:border-gray-700">
            <div className="flex items-center justify-between">
              <div className="flex items-center">
                <Plus className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Add New Repository</h3>
              </div>
              <button
                onClick={resetForm}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 p-1 rounded-md hover:bg-white/50 dark:hover:bg-gray-700/50 transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          <div className="p-6">
            {errors.general && (
              <div className="mb-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                <div className="flex items-center">
                  <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
                  <span className="text-red-800 dark:text-red-200 text-sm font-medium">{errors.general}</span>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-6">
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Repository Name
                  </label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="owner/repository-name"
                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Provider
                  </label>
                  <select
                    value={formData.provider}
                    onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                  >
                    <option value="github">GitHub</option>
                    <option value="azure_devops">Azure DevOps</option>
                  </select>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  Repository URL
                </label>
                <input
                  type="url"
                  value={formData.url}
                  onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                  placeholder="https://github.com/owner/repository-name"
                  className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                  required
                />
              </div>

              {/* Access Token Configuration */}
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-3 flex items-center">
                  <Key className="h-4 w-4 mr-2" />
                  Access Token Configuration
                </h4>
                
                <div className="space-y-4">
                  {/* GitHub Token */}
                  {formData.provider === 'github' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        GitHub Access Token
                        <span className="text-red-500 ml-1">*</span>
                      </label>
                      <div className="relative">
                        <input
                          type={isTokenVisible('new', 'github') ? 'text' : 'password'}
                          value={formData.github_token}
                          onChange={(e) => setFormData({ ...formData, github_token: e.target.value })}
                          placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                          className="w-full px-4 py-3 pr-12 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors font-mono text-sm"
                          required
                        />
                        <button
                          type="button"
                          onClick={() => toggleTokenVisibility('new', 'github')}
                          className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                        >
                          {isTokenVisible('new', 'github') ? 
                            <EyeOff className="h-4 w-4" /> : 
                            <Eye className="h-4 w-4" />
                          }
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Required for runner health checks and config detection. Needs 'repo' and 'actions:read' permissions.
                      </p>
                    </div>
                  )}

                  {/* Azure DevOps PAT */}
                  {formData.provider === 'azure_devops' && (
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Azure DevOps Personal Access Token (PAT)
                        <span className="text-red-500 ml-1">*</span>
                      </label>
                      <div className="relative">
                        <input
                          type={isTokenVisible('new', 'azure') ? 'text' : 'password'}
                          value={formData.azure_pat}
                          onChange={(e) => setFormData({ ...formData, azure_pat: e.target.value })}
                          placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                          className="w-full px-4 py-3 pr-12 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors font-mono text-sm"
                          required
                        />
                        <button
                          type="button"
                          onClick={() => toggleTokenVisibility('new', 'azure')}
                          className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                        >
                          {isTokenVisible('new', 'azure') ? 
                            <EyeOff className="h-4 w-4" /> : 
                            <Eye className="h-4 w-4" />
                          }
                        </button>
                      </div>
                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                        Required for agent health checks and config detection. Needs 'Agent Pools (read)' and 'Code (read)' permissions.
                      </p>
                    </div>
                  )}
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                  Configuration
                </label>
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                  <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.is_active}
                      onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                      className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                    />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Active</span>
                  </label>

                  <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.monitor_prs}
                      onChange={(e) => setFormData({ ...formData, monitor_prs: e.target.checked })}
                      className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                    />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Monitor PRs</span>
                  </label>

                  <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.monitor_issues}
                      onChange={(e) => setFormData({ ...formData, monitor_issues: e.target.checked })}
                      className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                    />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Monitor Issues</span>
                  </label>

                  <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.auto_review}
                      onChange={(e) => setFormData({ ...formData, auto_review: e.target.checked })}
                      className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                    />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto Review</span>
                  </label>

                  <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.auto_describe}
                      onChange={(e) => setFormData({ ...formData, auto_describe: e.target.checked })}
                      className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                    />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto Describe</span>
                  </label>

                  <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                    <input
                      type="checkbox"
                      checked={formData.auto_improve}
                      onChange={(e) => setFormData({ ...formData, auto_improve: e.target.checked })}
                      className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                    />
                    <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto Improve</span>
                  </label>
                </div>
              </div>

              <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700">
                <button
                  type="button"
                  onClick={resetForm}
                  className="px-6 py-2.5 text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors duration-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-6 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors duration-200 shadow-sm hover:shadow-md"
                >
                  <Plus className="h-4 w-4 mr-2 inline" />
                  Add Repository
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Repository List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm overflow-hidden">
        {repositories.length === 0 ? (
          <div className="p-12 text-center">
            <div className="mx-auto w-24 h-24 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-6">
              <GitBranch className="h-12 w-12 text-gray-400" />
            </div>
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">No repositories configured</h3>
            <p className="text-gray-500 dark:text-gray-400 mb-6 max-w-md mx-auto">Get started by adding your first repository to begin monitoring pull requests and issues.</p>
            <button
              onClick={() => setShowAddForm(true)}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors duration-200 shadow-sm hover:shadow-md"
            >
              <Plus className="h-4 w-4 mr-2 inline" />
              Add Repository
            </button>
          </div>
        ) : (
          <div className="divide-y divide-gray-200 dark:divide-gray-700">
            {repositories.map((repo) => (
              <div key={repo.id} className="transition-all duration-300 ease-in-out">
                {/* Repository Row */}
                <div 
                  className={`p-6 cursor-pointer transition-all duration-200 ease-in-out ${
                    expandedRepo === repo.id 
                      ? 'bg-blue-50 dark:bg-blue-900/20' 
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700/50'
                  }`}
                  onClick={() => toggleExpanded(repo.id)}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-4 flex-1 min-w-0">
                      {/* Expand/Collapse Icon */}
                      <div className="flex-shrink-0">
                        {expandedRepo === repo.id ? (
                          <ChevronDown className="h-5 w-5 text-gray-400 transform transition-all duration-300 ease-in-out rotate-0" />
                        ) : (
                          <ChevronRight className="h-5 w-5 text-gray-400 transform transition-all duration-300 ease-in-out" />
                        )}
                      </div>

                      {/* Repository Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center space-x-3">
                          <h3 className="text-lg font-semibold text-gray-900 dark:text-white truncate">
                            {repo.name}
                          </h3>
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${getProviderColor(repo.provider)}`}>
                            {getProviderIcon(repo.provider)}
                            <span className="ml-1.5 capitalize">{repo.provider.replace('_', ' ')}</span>
                          </span>
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                            repo.is_active 
                              ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
                              : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                          }`}>
                            {repo.is_active ? (
                              <><Check className="h-3 w-3 mr-1" />Active</>
                            ) : (
                              <><X className="h-3 w-3 mr-1" />Inactive</>
                            )}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center text-sm text-gray-500 dark:text-gray-400">
                          <Globe className="h-4 w-4 mr-2 flex-shrink-0" />
                          <a 
                            href={repo.url} 
                            target="_blank" 
                            rel="noopener noreferrer" 
                            className="hover:text-blue-600 dark:hover:text-blue-400 transition-colors truncate"
                            onClick={(e) => e.stopPropagation()}
                          >
                            {repo.url}
                          </a>
                        </div>
                      </div>

                      {/* Status Summary */}
                      <div className="hidden md:flex items-center space-x-4 text-sm">
                        {/* Runner Status */}
                        {repo.runner_status && (
                          <span className={`flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${getRunnerStatusColor(repo.runner_status)}`}>
                            {React.createElement(getRunnerStatusIcon(repo.runner_status), { className: "h-3 w-3 mr-1" })}
                            {formatRunnerStatus(repo.runner_status)}
                          </span>
                        )}

                        {/* Token Status - Always shown */}
                        <span className={`flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${
                          getTokenStatus(repo) === 'configured' 
                            ? 'bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-300'
                            : 'bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300'
                        }`}>
                          {getTokenStatusIcon(getTokenStatus(repo))}
                          <span className="ml-1">{getTokenStatusText(getTokenStatus(repo), repo.provider)}</span>
                        </span>

                        {/* Config Status - Only shown if tokens are configured */}
                        {shouldShowConfigStatus(repo) && (
                          <span className="flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-300">
                            {getConfigStatusIcon(repo)}
                            <span className="ml-1">{getConfigStatusText(repo)}</span>
                          </span>
                        )}
                        
                        {/* Monitoring Summary */}
                        <div className="flex items-center space-x-3 text-gray-500 dark:text-gray-400">
                          {repo.monitor_prs && (
                            <span className="flex items-center">
                              <div className="w-2 h-2 bg-blue-500 rounded-full mr-2"></div>
                              PRs
                            </span>
                          )}
                          {repo.monitor_issues && (
                            <span className="flex items-center">
                              <div className="w-2 h-2 bg-green-500 rounded-full mr-2"></div>
                              Issues
                            </span>
                          )}
                          {(repo.auto_review || repo.auto_describe || repo.auto_improve) && (
                            <span className="flex items-center">
                              <div className="w-2 h-2 bg-purple-500 rounded-full mr-2"></div>
                              Auto
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {expandedRepo === repo.id && (
                  <div className="border-t border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 rounded-b-lg">
                    <div className="p-6 space-y-6 animate-expand">
                      {/* Action Buttons */}
                      <div className="flex items-center justify-between">
                        <h4 className="text-lg font-medium text-gray-900 dark:text-white">Repository Details</h4>
                        <div className="flex items-center space-x-3">
                          {editingRepo !== repo.id ? (
                            <>
                              <button
                                onClick={() => checkRunnerHealth(repo.id)}
                                disabled={checkingHealth.has(repo.id)}
                                className="flex items-center px-4 py-2 text-sm font-medium text-green-600 bg-green-50 dark:bg-green-900/30 dark:text-green-400 rounded-lg hover:bg-green-100 dark:hover:bg-green-900/50 transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                              >
                                {checkingHealth.has(repo.id) ? (
                                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                  <Activity className="h-4 w-4 mr-2" />
                                )}
                                Check Health
                              </button>
                              {shouldShowConfigStatus(repo) && (
                                <button
                                  onClick={() => checkRepositoryConfig(repo.id)}
                                  disabled={checkingConfig.has(repo.id)}
                                  className="flex items-center px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 dark:bg-blue-900/30 dark:text-blue-400 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  {checkingConfig.has(repo.id) ? (
                                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                  ) : (
                                    <FileText className="h-4 w-4 mr-2" />
                                  )}
                                  Check Config
                                </button>
                              )}
                              {shouldShowConfigStatus(repo) && repo.has_pr_agent_config && (
                                <button
                                  onClick={() => viewEffectiveConfig(repo.id)}
                                  className="flex items-center px-4 py-2 text-sm font-medium text-purple-600 bg-purple-50 dark:bg-purple-900/30 dark:text-purple-400 rounded-lg hover:bg-purple-100 dark:hover:bg-purple-900/50 transition-colors duration-200"
                                >
                                  <Eye className="h-4 w-4 mr-2" />
                                  View Config
                                </button>
                              )}
                              <button
                                onClick={() => startEdit(repo.id)}
                                className="flex items-center px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 dark:bg-blue-900/30 dark:text-blue-400 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors duration-200"
                              >
                                <Edit className="h-4 w-4 mr-2" />
                                Edit
                              </button>
                              <button
                                onClick={() => handleDelete(repo)}
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
                                className="flex items-center px-4 py-2 text-sm font-medium text-gray-600 bg-gray-50 dark:bg-gray-700 dark:text-gray-400 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors duration-200"
                              >
                                <X className="h-4 w-4 mr-2" />
                                Cancel
                              </button>
                              <button
                                onClick={(e) => handleSubmit(e, repo.id)}
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
                      {errors.general && editingRepo === repo.id && (
                        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                          <div className="flex items-center">
                            <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
                            <span className="text-red-800 dark:text-red-200 text-sm font-medium">{errors.general}</span>
                          </div>
                        </div>
                      )}

                      {/* Runner Health Status */}
                      {repo.runner_status && (
                        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                          <div className="flex items-center justify-between mb-3">
                            <h5 className="text-sm font-medium text-gray-900 dark:text-white">Runner Health Status</h5>
                            <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${getRunnerStatusColor(repo.runner_status)}`}>
                              {React.createElement(getRunnerStatusIcon(repo.runner_status), { className: "h-3 w-3 mr-1" })}
                              {formatRunnerStatus(repo.runner_status)}
                            </span>
                          </div>
                          <div className="space-y-2 text-sm">
                            {repo.runner_error && (
                              <div className="text-red-600 dark:text-red-400">
                                <span className="font-medium">Error:</span> {repo.runner_error}
                              </div>
                            )}
                            {repo.runner_last_seen && (
                              <div className="text-gray-600 dark:text-gray-400">
                                <span className="font-medium">Last seen:</span> {new Date(repo.runner_last_seen).toLocaleString()}
                              </div>
                            )}
                            <div className="text-gray-600 dark:text-gray-400">
                              <span className="font-medium">Type:</span> {repo.provider === 'github' ? 'GitHub Self-hosted Runner' : 'Azure DevOps Agent'}
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Configuration Status - Only shown if tokens are configured */}
                      {shouldShowConfigStatus(repo) && (
                        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                          <div className="flex items-center justify-between mb-3">
                            <h5 className="text-sm font-medium text-gray-900 dark:text-white">Configuration Status</h5>
                            <div className="flex items-center space-x-2">
                              {getConfigStatusIcon(repo)}
                              <span className="text-sm font-medium text-gray-900 dark:text-white">
                                {getConfigStatusText(repo)}
                              </span>
                            </div>
                          </div>
                          <div className="space-y-2 text-sm text-gray-600 dark:text-gray-400">
                            <div>
                              <span className="font-medium">Last checked:</span> {formatLastChecked(repo.config_last_checked)}
                            </div>
                            {repo.config_last_checked && repo.has_pr_agent_config && (
                              <div className="text-green-600 dark:text-green-400">
                                <span className="font-medium">✓</span> Repository has custom .pr_agent.toml configuration
                              </div>
                            )}
                            {repo.config_last_checked && repo.has_pr_agent_config === false && (
                              <div className="text-gray-500 dark:text-gray-400">
                                <span className="font-medium">ℹ</span> Repository uses system default configuration
                              </div>
                            )}
                            {!repo.config_last_checked && (
                              <div className="text-amber-600 dark:text-amber-400">
                                <span className="font-medium">⚠</span> Configuration not yet checked. Use "Check Config" button above.
                              </div>
                            )}
                          </div>
                        </div>
                      )}

                      {/* Access Token Configuration */}
                      <div className="bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                        <div 
                          className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
                          onClick={() => toggleTokenSection(repo.id)}
                        >
                          <div className="flex items-center space-x-3">
                            <div className="flex items-center space-x-2">
                              {isTokenSectionExpanded(repo.id) ? (
                                <ChevronDown className="h-4 w-4 text-gray-400" />
                              ) : (
                                <ChevronRight className="h-4 w-4 text-gray-400" />
                              )}
                              <Key className="h-4 w-4" />
                              <h5 className="text-sm font-medium text-gray-900 dark:text-white">
                                {repo.provider === 'github' ? 'GitHub Access Token' : 'Azure DevOps Personal Access Token'}
                              </h5>
                            </div>
                            {shouldExpandTokenSection(repo) && (
                              <span className="px-2 py-1 bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 text-xs rounded-full font-medium">
                                Action Required
                              </span>
                            )}
                          </div>
                          <div className="flex items-center space-x-2">
                            {getTokenStatusIcon(getTokenStatus(repo))}
                            <span className="text-sm font-medium text-gray-900 dark:text-white">
                              {getTokenStatusText(getTokenStatus(repo), repo.provider)}
                            </span>
                          </div>
                        </div>
                        
                        {/* Collapsible Token Content */}
                        {isTokenSectionExpanded(repo.id) && (
                          <div className="px-4 pb-4 space-y-4 border-t border-gray-200 dark:border-gray-600">
                            {/* GitHub Token */}
                            {repo.provider === 'github' && (
                              <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                  GitHub Access Token
                                  <span className="text-red-500 ml-1">*</span>
                                </label>
                                {editingRepo === repo.id ? (
                                  <div className="relative">
                                    <input
                                      type={isTokenVisible(repo.id, 'github') ? 'text' : 'password'}
                                      value={formData.github_token}
                                      onChange={(e) => setFormData({ ...formData, github_token: e.target.value })}
                                      placeholder="ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                                      className="w-full px-4 py-3 pr-12 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors font-mono text-sm"
                                    />
                                    <button
                                      type="button"
                                      onClick={() => toggleTokenVisibility(repo.id, 'github')}
                                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                                    >
                                      {isTokenVisible(repo.id, 'github') ? 
                                        <EyeOff className="h-4 w-4" /> : 
                                        <Eye className="h-4 w-4" />
                                      }
                                    </button>
                                  </div>
                                ) : (
                                  <div className="px-4 py-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
                                    <div className="flex items-center justify-between">
                                      <span className="text-gray-900 dark:text-white font-mono text-sm">
                                        {repo.github_token ? (isTokenVisible(repo.id, 'github') ? repo.github_token : maskToken(repo.github_token)) : 'Not configured'}
                                      </span>
                                      {repo.github_token && (
                                        <button
                                          onClick={() => toggleTokenVisibility(repo.id, 'github')}
                                          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 ml-2"
                                        >
                                          {isTokenVisible(repo.id, 'github') ? 
                                            <EyeOff className="h-4 w-4" /> : 
                                            <Eye className="h-4 w-4" />
                                          }
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                )}
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                  Required for runner health checks and config detection. Needs 'repo' and 'actions:read' permissions.
                                </p>
                              </div>
                            )}

                            {/* Azure DevOps PAT */}
                            {repo.provider === 'azure_devops' && (
                              <div>
                                <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                  Azure DevOps Personal Access Token (PAT)
                                  <span className="text-red-500 ml-1">*</span>
                                </label>
                                {editingRepo === repo.id ? (
                                  <div className="relative">
                                    <input
                                      type={isTokenVisible(repo.id, 'azure') ? 'text' : 'password'}
                                      value={formData.azure_pat}
                                      onChange={(e) => setFormData({ ...formData, azure_pat: e.target.value })}
                                      placeholder="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                                      className="w-full px-4 py-3 pr-12 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors font-mono text-sm"
                                    />
                                    <button
                                      type="button"
                                      onClick={() => toggleTokenVisibility(repo.id, 'azure')}
                                      className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                                    >
                                      {isTokenVisible(repo.id, 'azure') ? 
                                        <EyeOff className="h-4 w-4" /> : 
                                        <Eye className="h-4 w-4" />
                                      }
                                    </button>
                                  </div>
                                ) : (
                                  <div className="px-4 py-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
                                    <div className="flex items-center justify-between">
                                      <span className="text-gray-900 dark:text-white font-mono text-sm">
                                        {repo.azure_pat ? (isTokenVisible(repo.id, 'azure') ? repo.azure_pat : maskToken(repo.azure_pat)) : 'Not configured'}
                                      </span>
                                      {repo.azure_pat && (
                                        <button
                                          onClick={() => toggleTokenVisibility(repo.id, 'azure')}
                                          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 ml-2"
                                        >
                                          {isTokenVisible(repo.id, 'azure') ? 
                                            <EyeOff className="h-4 w-4" /> : 
                                            <Eye className="h-4 w-4" />
                                          }
                                        </button>
                                      )}
                                    </div>
                                  </div>
                                )}
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                  Required for agent health checks and config detection. Needs 'Agent Pools (read)' and 'Code (read)' permissions.
                                </p>
                              </div>
                            )}

                            {/* Authentication Error Display */}
                            {repo.runner_error && shouldExpandTokenSection(repo) && (
                              <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                                <div className="flex items-start">
                                  <AlertCircle className="h-4 w-4 text-red-600 dark:text-red-400 mr-2 mt-0.5 flex-shrink-0" />
                                  <div>
                                    <span className="text-red-800 dark:text-red-200 text-sm font-medium">Authentication Error:</span>
                                    <p className="text-red-700 dark:text-red-300 text-sm mt-1">{repo.runner_error}</p>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Repository Configuration */}
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Repository Name
                          </label>
                          {editingRepo === repo.id ? (
                            <input
                              type="text"
                              value={formData.name}
                              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                              className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                            />
                          ) : (
                            <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                              <span className="text-gray-900 dark:text-white font-medium">{repo.name}</span>
                            </div>
                          )}
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                            Provider
                          </label>
                          {editingRepo === repo.id ? (
                            <select
                              value={formData.provider}
                              onChange={(e) => setFormData({ ...formData, provider: e.target.value })}
                              className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                            >
                              <option value="github">GitHub</option>
                              <option value="azure_devops">Azure DevOps</option>
                            </select>
                          ) : (
                            <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                              <div className="flex items-center">
                                {getProviderIcon(repo.provider)}
                                <span className="ml-2 text-gray-900 dark:text-white font-medium capitalize">{repo.provider.replace('_', ' ')}</span>
                              </div>
                            </div>
                          )}
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Repository URL
                        </label>
                        {editingRepo === repo.id ? (
                          <input
                            type="url"
                            value={formData.url}
                            onChange={(e) => setFormData({ ...formData, url: e.target.value })}
                            className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                          />
                        ) : (
                          <div className="px-4 py-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                            <a 
                              href={repo.url} 
                              target="_blank" 
                              rel="noopener noreferrer" 
                              className="text-blue-600 dark:text-blue-400 hover:underline font-medium"
                            >
                              {repo.url}
                            </a>
                          </div>
                        )}
                      </div>

                      {/* Configuration Options */}
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">
                          Configuration
                        </label>
                        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                          {[
                            { key: 'is_active', label: 'Active', description: 'Enable monitoring for this repository' },
                            { key: 'monitor_prs', label: 'Monitor PRs', description: 'Watch pull requests' },
                            { key: 'monitor_issues', label: 'Monitor Issues', description: 'Watch issues' },
                            { key: 'auto_review', label: 'Auto Review', description: 'Automatically review PRs' },
                            { key: 'auto_describe', label: 'Auto Describe', description: 'Generate PR descriptions' },
                            { key: 'auto_improve', label: 'Auto Improve', description: 'Suggest improvements' }
                          ].map(({ key, label, description }) => (
                            <label key={key} className={`flex items-center p-4 rounded-lg border transition-all duration-200 ${
                              editingRepo === repo.id 
                                ? 'border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-700 cursor-pointer' 
                                : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-700'
                            }`}>
                              <input
                                type="checkbox"
                                checked={formData[key]}
                                onChange={(e) => editingRepo === repo.id && setFormData({ ...formData, [key]: e.target.checked })}
                                disabled={editingRepo !== repo.id}
                                className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4 disabled:opacity-50"
                              />
                              <div>
                                <span className="text-sm font-medium text-gray-700 dark:text-gray-300">{label}</span>
                                <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{description}</p>
                              </div>
                            </label>
                          ))}
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Configuration Viewer Modal */}
      {viewingConfig && effectiveConfig && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-lg max-w-4xl w-full max-h-[90vh] overflow-hidden">
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
              <div className="flex items-center space-x-3">
                <FileText className="h-6 w-6 text-blue-600 dark:text-blue-400" />
                <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                  Effective Configuration
                </h3>
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  {repositories.find(r => r.id === viewingConfig)?.name}
                </span>
              </div>
              <button
                onClick={closeConfigViewer}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              >
                <X className="h-6 w-6" />
              </button>
            </div>
            
            <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
              {effectiveConfig.error ? (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                  <div className="flex items-center">
                    <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
                    <span className="text-red-800 dark:text-red-200 text-sm font-medium">{effectiveConfig.error}</span>
                  </div>
                </div>
              ) : (
                <div className="space-y-6">
                  {/* Override Summary */}
                  {effectiveConfig.override_keys && effectiveConfig.override_keys.length > 0 && (
                    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                      <h4 className="text-sm font-medium text-blue-900 dark:text-blue-100 mb-2">
                        Repository Overrides ({effectiveConfig.override_keys.length} settings)
                      </h4>
                      <div className="flex flex-wrap gap-2">
                        {effectiveConfig.override_keys.map((key, index) => (
                          <span key={index} className="px-2 py-1 bg-blue-100 dark:bg-blue-800 text-blue-800 dark:text-blue-200 text-xs rounded">
                            {key}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Repository Config */}
                  {effectiveConfig.repository_overrides && Object.keys(effectiveConfig.repository_overrides).length > 0 && (
                    <div>
                      <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-3 flex items-center">
                        <FileText className="h-5 w-5 mr-2 text-green-600 dark:text-green-400" />
                        Repository Configuration (.pr_agent.toml)
                      </h4>
                      <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                        <pre className="text-sm text-gray-800 dark:text-gray-200 overflow-x-auto whitespace-pre-wrap font-mono">
                          {JSON.stringify(effectiveConfig.repository_overrides, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Merged Config */}
                  <div>
                    <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-3 flex items-center">
                      <Settings className="h-5 w-5 mr-2 text-purple-600 dark:text-purple-400" />
                      Effective Configuration (Merged)
                    </h4>
                    <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                      <pre className="text-sm text-gray-800 dark:text-gray-200 overflow-x-auto whitespace-pre-wrap font-mono">
                        {JSON.stringify(effectiveConfig.merged_config, null, 2)}
                      </pre>
                    </div>
                  </div>

                  {/* System Config */}
                  <div>
                    <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-3 flex items-center">
                      <Globe className="h-5 w-5 mr-2 text-gray-600 dark:text-gray-400" />
                      System Default Configuration
                    </h4>
                    <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                      <pre className="text-sm text-gray-800 dark:text-gray-200 overflow-x-auto whitespace-pre-wrap font-mono">
                        {JSON.stringify(effectiveConfig.system_config, null, 2)}
                      </pre>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RepositoryManager; 