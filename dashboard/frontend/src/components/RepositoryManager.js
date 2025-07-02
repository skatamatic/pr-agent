import React, { useState, useEffect, useContext, useCallback } from 'react';
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
  Activity,
  RefreshCw,
  Clock,
  CheckCircle,
  FileText,
  Eye,
  Key,
  EyeOff,
  Shield,
  Server,
  ExternalLink
} from 'lucide-react';
import api from '../services/api';
import { ToastContext } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';
import PrAgentConfigEditor from './PrAgentConfigEditor';

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
  const [showTokens, setShowTokens] = useState({});
  const [expandedTokenSections, setExpandedTokenSections] = useState(new Set());
  const { showSuccess, showError } = useContext(ToastContext);

  const [repoActiveTabs, setRepoActiveTabs] = useState({});
  const [effectiveConfigModal, setEffectiveConfigModal] = useState({
    show: false,
    loading: false,
    data: null,
    error: null,
    repoId: null
  });
  const [dismissedInfo, setDismissedInfo] = useState(() => {
    return localStorage.getItem('dismissedRepositoryInfo') === 'true';
  });
  const [bestPracticesData, setBestPracticesData] = useState({});
  const [isEditingBestPractices, setIsEditingBestPractices] = useState({});
  const [editedBestPracticesContent, setEditedBestPracticesContent] = useState({});
  const [savingBestPractices, setSavingBestPractices] = useState({});
  const [loadingBestPractices, setLoadingBestPractices] = useState(new Set());
  
  // PR-Agent config states
  const [prAgentConfigData, setPrAgentConfigData] = useState({});
  const [showPrAgentConfigEditor, setShowPrAgentConfigEditor] = useState(null);
  const [loadingPrAgentConfig, setLoadingPrAgentConfig] = useState(new Set());
  const [checkingPrStatus, setCheckingPrStatus] = useState(new Set());

  const fetchRepositories = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.getRepositories();
      setRepositories(response.data.data || []);
    } catch (error) {
      showError('Error', 'Failed to fetch repositories');
    } finally {
      setLoading(false);
    }
  }, [showError]);

  useEffect(() => {
    fetchRepositories();
  }, [fetchRepositories]);

  // Inject custom CSS for best practices markdown styling
  useEffect(() => {
    if (!document.getElementById('best-practices-styles')) {
      const style = document.createElement('style');
      style.id = 'best-practices-styles';
      style.textContent = `
        .best-practices-markdown * {
          color: #374151 !important;
        }
        .best-practices-markdown h1,
        .best-practices-markdown h2,
        .best-practices-markdown h3,
        .best-practices-markdown h4,
        .best-practices-markdown h5,
        .best-practices-markdown h6 {
          color: #111827 !important;
          font-weight: 600 !important;
          margin-top: 1.5em !important;
          margin-bottom: 0.5em !important;
        }
        .best-practices-markdown p,
        .best-practices-markdown li {
          color: #4b5563 !important;
          line-height: 1.6 !important;
        }
        .best-practices-markdown code {
          background-color: #f3f4f6 !important;
          color: #7c3aed !important;
          padding: 0.125rem 0.25rem !important;
          border-radius: 0.25rem !important;
          font-size: 0.875em !important;
        }
        .best-practices-markdown pre {
          background-color: #f8fafc !important;
          color: #1f2937 !important;
          padding: 1rem !important;
          border-radius: 0.5rem !important;
          overflow-x: auto !important;
          border: 1px solid #e5e7eb !important;
        }
        .best-practices-markdown pre code {
          background-color: transparent !important;
          color: #1f2937 !important;
          padding: 0 !important;
        }
        .best-practices-markdown blockquote {
          border-left: 4px solid #a855f7 !important;
          padding: 1rem !important;
          margin: 1rem 0 !important;
          color: #6b7280 !important;
          font-style: italic !important;
          background-color: #f9fafb !important;
          border-radius: 0.25rem !important;
        }
        .best-practices-markdown a {
          color: #7c3aed !important;
          text-decoration: none !important;
        }
        .best-practices-markdown a:hover {
          text-decoration: underline !important;
        }
        .best-practices-markdown strong {
          color: #111827 !important;
          font-weight: 600 !important;
        }
        
        /* Dark theme overrides */
        .dark .best-practices-markdown * {
          color: #d1d5db !important;
        }
        .dark .best-practices-markdown h1,
        .dark .best-practices-markdown h2,
        .dark .best-practices-markdown h3,
        .dark .best-practices-markdown h4,
        .dark .best-practices-markdown h5,
        .dark .best-practices-markdown h6 {
          color: #f9fafb !important;
        }
        .dark .best-practices-markdown p,
        .dark .best-practices-markdown li {
          color: #d1d5db !important;
        }
        .dark .best-practices-markdown code {
          background-color: #374151 !important;
          color: #c084fc !important;
        }
        .dark .best-practices-markdown pre {
          background-color: #111827 !important;
          color: #f3f4f6 !important;
        }
        .dark .best-practices-markdown pre code {
          color: #f3f4f6 !important;
        }
        .dark .best-practices-markdown blockquote {
          border-left-color: #8b5cf6 !important;
          color: #9ca3af !important;
          background-color: #374151 !important;
        }
        .dark .best-practices-markdown a {
          color: #c084fc !important;
        }
        .dark .best-practices-markdown strong {
          color: #f9fafb !important;
        }
      `;
      document.head.appendChild(style);
    }
  }, []);

  const handleSubmit = async (e, repoId = null) => {
    e.preventDefault();
    setErrors({});

    // Check if this is a token update (existing repo with token changes)
    const isTokenUpdate = repoId && originalFormData && (
      formData.github_token !== originalFormData.github_token ||
      formData.azure_pat !== originalFormData.azure_pat
    );

    try {
      if (repoId) {
        if (isTokenUpdate) {
          showSuccess('Validating...', 'Validating access token and updating repository...');
        }
        
        await api.updateRepository(repoId, formData);
        showSuccess('Success', 'Repository updated successfully');
        
        // If token was updated, automatically trigger health and config checks
        if (isTokenUpdate) {
          showSuccess('Checking Health...', 'Validating token and checking repository health...');
          
          try {
            // Check repository health to validate token
            await checkRunnerHealth(repoId);
            
            // Check repository configuration
            showSuccess('Fetching Config...', 'Fetching pr_agent.toml configuration...');
            await checkRepositoryConfig(repoId);
            
            showSuccess('Complete', 'Token validated and repository updated successfully');
          } catch (healthError) {
            showError('Warning', 'Repository updated but health/config check failed. Please verify your token has the correct permissions.');
          }
        }
      } else {
        await api.createRepository(formData);
        showSuccess('Success', 'Repository added successfully');
        
        // For new repositories, also trigger health and config checks
        fetchRepositories().then(() => {
          // Find the newly created repository and trigger checks
          setTimeout(async () => {
            const updatedRepos = await api.getRepositories();
            const newRepo = updatedRepos.data.data.find(r => r.name === formData.name);
            if (newRepo) {
              try {
                await checkRunnerHealth(newRepo.id);
                await checkRepositoryConfig(newRepo.id);
              } catch (error) {
                console.warn('Failed to trigger initial health/config checks:', error);
              }
            }
          }, 1000);
        });
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
    setRepoActiveTabs({});
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
        
        // Auto-fetch best practices if token is configured and not already loaded
        if (getTokenStatus(repo) === 'configured' && 
            !bestPracticesData[repoId] && 
            !loadingBestPractices.has(repoId)) {
          loadBestPractices(repoId);
        }
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
      await api.checkRepositoryHealth(repoId);
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
      await api.checkRepositoryConfig(repoId);
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





  const getConfigStatusIcon = (repo) => {
    const hasToml = repo.has_pr_agent_config === true;
    const hasWorkflow = repo.has_workflow_config === true;
    
    if (hasToml || hasWorkflow) {
      return <FileText className="h-4 w-4 text-green-600" />;
    } else if (repo.config_last_checked) {
      return <FileText className="h-4 w-4 text-gray-400" />;
    }
    return <FileText className="h-4 w-4 text-gray-300" />;
  };

  const getConfigStatusText = (repo) => {
    // Only show config status if we've actually checked
    if (repo.config_last_checked) {
      const hasToml = repo.has_pr_agent_config === true;
      const hasWorkflow = repo.has_workflow_config === true;
      
      if (hasToml && hasWorkflow) {
        return 'Has .pr_agent.toml + workflow';
      } else if (hasToml) {
        return 'Has .pr_agent.toml';
      } else if (hasWorkflow) {
        return 'Has workflow config';
      } else {
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



  const getTokenVisibilityKey = (repoId, tokenType) => {
    return `${repoId || 'new'}-${tokenType}`;
  };

  const isTokenVisible = (repoId, tokenType) => {
    const key = getTokenVisibilityKey(repoId, tokenType);
    return showTokens[key] || false;
  };

  const getTokenStatus = (repo) => {
    // Use the token status indicators from the backend instead of actual token values
    const hasToken = repo.provider === 'github' ? repo.has_github_token : repo.has_azure_pat;
    
    if (!hasToken) {
      return 'missing';
    }
    
    // Check runner health for token validation
    if (repo.runner_error && (
      repo.runner_error.includes('token') || 
      repo.runner_error.includes('authentication') || 
      repo.runner_error.includes('invalid') || 
      repo.runner_error.includes('expired') ||
      repo.runner_error.includes('permissions')
    )) {
      return 'invalid';
    }
    
    return 'configured';
  };

  const shouldExpandTokenSection = (repo) => {
    // Auto-expand if token is missing or invalid
    const tokenStatus = getTokenStatus(repo);
    return tokenStatus === 'missing' || tokenStatus === 'invalid';
  };



  const getTokenStatusIcon = (status) => {
    switch (status) {
      case 'configured':
        return <Shield className="h-4 w-4 text-green-600 dark:text-green-400" />;
      case 'invalid':
        return <Shield className="h-4 w-4 text-red-600 dark:text-red-400" />;
      case 'missing':
        return <Shield className="h-4 w-4 text-orange-600 dark:text-orange-400" />;
      default:
        return <Shield className="h-4 w-4 text-gray-400" />;
    }
  };

  const getTokenStatusText = (status, provider) => {
    const tokenName = provider === 'github' ? 'GitHub token' : 'Azure PAT';
    switch (status) {
      case 'configured':
        return `${tokenName} configured`;
      case 'invalid':
        return `${tokenName} invalid or expired`;
      case 'missing':
        return `${tokenName} required`;
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

  const getRepoActiveTab = (repoId) => {
    const repo = repositories.find(r => r.id === repoId);
    const hasToken = repo && getTokenStatus(repo) === 'configured';
    const currentTab = repoActiveTabs[repoId];
    
    // If no token, force authentication tab
    if (!hasToken) {
      return 'authentication';
    }
    
    // Otherwise return current tab or default to status
    return currentTab || 'status';
  };

  const setRepoActiveTab = (repoId, tab) => {
    setRepoActiveTabs(prev => ({
      ...prev,
      [repoId]: tab
    }));
  };

  const toggleRepositoryActive = async (repoId, currentIsActive) => {
    try {
      await api.updateRepository(repoId, { is_active: !currentIsActive });
      showSuccess('Success', `Repository ${!currentIsActive ? 'activated' : 'deactivated'} successfully`);
      fetchRepositories(); // Refresh to get updated status
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to update repository status';
      showError('Error', errorMsg);
    }
  };

  const loadEffectiveConfig = async (repoId) => {
    try {
      setEffectiveConfigModal(prev => ({
        ...prev,
        show: true,
        loading: true,
        error: null,
        repoId: repoId,
        data: null
      }));
      
      const response = await api.get(`/api/repositories/${repoId}/effective-config`);
      setEffectiveConfigModal(prev => ({
        ...prev,
        loading: false,
        data: response.data.data
      }));
    } catch (error) {
      console.error('Failed to load effective config:', error);
      const errorMsg = error.response?.data?.detail || 'Failed to load effective configuration';
      setEffectiveConfigModal(prev => ({
        ...prev,
        loading: false,
        error: errorMsg
      }));
    }
  };

  const loadBestPractices = async (repoId, forceRefresh = false) => {
    setLoadingBestPractices(prev => new Set([...prev, repoId]));
    
    try {
      const response = await api.get(`/api/repositories/${repoId}/best-practices?force_refresh=${forceRefresh}`);
      setBestPracticesData(prev => ({
        ...prev,
        [repoId]: {
          ...response.data.data,
          error: null
        }
      }));
    } catch (error) {
      console.error('Failed to load best practices:', error);
      const errorMsg = error.response?.data?.detail || 'Failed to load best practices';
      setBestPracticesData(prev => ({
        ...prev,
        [repoId]: {
          exists: false,
          content: null,
          error: errorMsg
        }
      }));
    } finally {
      setLoadingBestPractices(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  const startEditingBestPractices = (repoId) => {
    const currentContent = bestPracticesData[repoId]?.content || '';
    setEditedBestPracticesContent(prev => ({
      ...prev,
      [repoId]: currentContent
    }));
    setIsEditingBestPractices(prev => ({
      ...prev,
      [repoId]: true
    }));
  };

  const cancelEditingBestPractices = (repoId) => {
    setIsEditingBestPractices(prev => ({
      ...prev,
      [repoId]: false
    }));
    setEditedBestPracticesContent(prev => ({
      ...prev,
      [repoId]: ''
    }));
  };

  const saveBestPractices = async (repoId) => {
    const content = editedBestPracticesContent[repoId];
    if (!content || !content.trim()) {
      showError('Content cannot be empty');
      return;
    }

    setSavingBestPractices(prev => ({
      ...prev,
      [repoId]: true
    }));

    try {
      const response = await api.put(`/api/repositories/${repoId}/best-practices`, {
        content: content.trim()
      });

      const prData = response.data.data;
      showSuccess(
        'Best Practices PR Created!', 
        `${prData.action === 'created_new_pr' ? 'Created' : 'Updated'} PR #${prData.pr_number} - ${prData.action === 'created_new_pr' ? 'Review and merge to activate' : 'Added new commit to existing PR'}`
      );

      // Update best practices data with PR info
      setBestPracticesData(prev => ({
        ...prev,
        [repoId]: {
          ...prev[repoId],
          has_pending_pr: true,
          pr_url: prData.pr_url,
          pr_number: prData.pr_number,
          pr_status: 'pending'
        }
      }));

      // Exit edit mode
      setIsEditingBestPractices(prev => ({
        ...prev,
        [repoId]: false
      }));
      setEditedBestPracticesContent(prev => ({
        ...prev,
        [repoId]: ''
      }));

    } catch (error) {
      console.error('Error saving best practices:', error);
      showError('Failed to save', error.response?.data?.detail || 'Failed to create/update best practices PR');
    } finally {
      setSavingBestPractices(prev => ({
        ...prev,
        [repoId]: false
      }));
    }
  };

  const checkPRStatus = async (repoId) => {
    try {
      const response = await api.post(`/api/repositories/${repoId}/best-practices/check-pr-status`);
      const statusData = response.data.data;
      
      if (statusData.status === 'merged') {
        showSuccess('PR Merged!', 'Best practices PR was merged. Content updated.');
        // Refresh the best practices data
        await loadBestPractices(repoId, true);
      } else if (statusData.status === 'closed') {
        showSuccess('PR Closed', 'Best practices PR was closed without merging.');
        // Update local state
        setBestPracticesData(prev => ({
          ...prev,
          [repoId]: {
            ...prev[repoId],
            has_pending_pr: false,
            pr_status: 'closed'
          }
        }));
      }
    } catch (error) {
      console.error('Error checking PR status:', error);
    }
  };

  // PR-Agent Configuration Functions
  const loadPrAgentConfig = async (repoId, forceRefresh = false) => {
    if (loadingPrAgentConfig.has(repoId) && !forceRefresh) {
      return;
    }

    try {
      setLoadingPrAgentConfig(prev => new Set([...prev, repoId]));
      
      const response = await api.getRepositoryPrAgentConfig(repoId, forceRefresh);
      const data = response.data?.data || {};
      
      setPrAgentConfigData(prev => ({
        ...prev,
        [repoId]: data
      }));

      // If there's a pending PR, check its status automatically
      if (data.pr_status === 'pending') {
        // Check PR status after a short delay to avoid overwhelming the API
        setTimeout(() => {
          checkPrAgentConfigPRStatus(repoId);
        }, 1000);
      }
      
    } catch (error) {
      console.error('Error loading PR-Agent config:', error);
      showError('Error', 'Failed to load PR-Agent configuration');
    } finally {
      setLoadingPrAgentConfig(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  const openPrAgentConfigEditor = (repoId) => {
    setShowPrAgentConfigEditor(repoId);
    loadPrAgentConfig(repoId);
  };

  const closePrAgentConfigEditor = () => {
    setShowPrAgentConfigEditor(null);
  };

  const handlePrAgentConfigSave = async (result) => {
    if (result && showPrAgentConfigEditor) {
      // Refresh the PR-Agent config data
      await loadPrAgentConfig(showPrAgentConfigEditor, true);
      
      // Update the repository data to reflect the new PR status
      setRepositories(prev => prev.map(repo => 
        repo.id === showPrAgentConfigEditor 
          ? { 
              ...repo, 
              pr_agent_config_pr_status: result.status,
              pr_agent_config_pr_url: result.pr_url,
              pr_agent_config_pr_number: result.pr_number,
              has_pr_agent_config: true
            }
          : repo
      ));
      
      // Dialog is closed automatically by the PrAgentConfigEditor
    }
  };

  const checkPrAgentConfigPRStatus = async (repoId) => {
    try {
      setCheckingPrStatus(prev => new Set([...prev, repoId]));
      
      const response = await api.checkPrAgentConfigPrStatus(repoId);
      const statusData = response.data.data;
      
      if (statusData.status === 'merged') {
        showSuccess('PR Merged!', 'PR-Agent config PR was merged. Configuration updated.');
        // Refresh the PR-Agent config data
        await loadPrAgentConfig(repoId, true);
        // Clear PR status from repositories state
        setRepositories(prev => prev.map(repo => 
          repo.id === repoId
            ? { 
                ...repo, 
                pr_agent_config_pr_status: null,
                pr_agent_config_pr_url: null,
                pr_agent_config_pr_number: null,
                has_pr_agent_config: true
              }
            : repo
        ));
      } else if (statusData.status === 'closed') {
        showSuccess('PR Closed', 'PR-Agent config PR was closed without merging.');
        // Update local state
        setPrAgentConfigData(prev => ({
          ...prev,
          [repoId]: {
            ...prev[repoId],
            has_pending_pr: false,
            pr_status: 'closed'
          }
        }));
        // Clear PR status from repositories state
        setRepositories(prev => prev.map(repo => 
          repo.id === repoId
            ? { 
                ...repo, 
                pr_agent_config_pr_status: null,
                pr_agent_config_pr_url: null,
                pr_agent_config_pr_number: null
              }
            : repo
        ));
      }
    } catch (error) {
      console.error('Error checking PR-Agent config PR status:', error);
      showError('Error', 'Failed to check PR status');
    } finally {
      setCheckingPrStatus(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  // Get overall repository status for the main badge
  const getRepositoryStatus = (repo) => {
    // If repository is not active, show as disabled
    if (!repo.is_active) {
      return 'disabled';
    }

    // Check for errors in runner status or token issues
    if (repo.runner_status === 'error' || repo.runner_status === 'misconfigured') {
      return 'error';
    }

    // Check token status
    const tokenStatus = getTokenStatus(repo);
    if (tokenStatus === 'invalid' || tokenStatus === 'missing') {
      return 'error';
    }

    // If active and no errors, show as running
    return 'running';
  };

  const getRepositoryStatusColor = (status) => {
    switch (status) {
      case 'running':
        return 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
      case 'disabled':
        return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
      case 'error':
        return 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300';
      default:
        return 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300';
    }
  };

  const getRepositoryStatusIcon = (status) => {
    switch (status) {
      case 'running':
        return Check;
      case 'disabled':
        return X;
      case 'error':
        return AlertCircle;
      default:
        return Clock;
    }
  };

  const formatRepositoryStatus = (status) => {
    switch (status) {
      case 'running':
        return 'Running';
      case 'disabled':
        return 'Disabled';
      case 'error':
        return 'Error';
      default:
        return 'Unknown';
    }
  };

  // Sort repositories by status (running first, then disabled, then error) and then by name
  const sortRepositories = (repos) => {
    return [...repos].sort((a, b) => {
      const statusA = getRepositoryStatus(a);
      const statusB = getRepositoryStatus(b);
      
      // Define status priority (lower number = higher priority)
      const statusPriority = {
        'running': 1,
        'disabled': 2,
        'error': 3
      };
      
      const priorityA = statusPriority[statusA] || 4;
      const priorityB = statusPriority[statusB] || 4;
      
      // First sort by status priority
      if (priorityA !== priorityB) {
        return priorityA - priorityB;
      }
      
      // Then sort by repository name alphabetically
      return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
    });
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <ViewHeader 
          title="Repository Management"
          subtitle="Configure which repositories PR-Agent monitors and manages"
          icon={GitBranch}
        />
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-3 text-gray-600 dark:text-gray-400">Loading repositories...</span>
        </div>
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
      {!dismissedInfo && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
          <div className="flex items-start">
            <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
            <div className="flex-1 text-blue-800 dark:text-blue-200 text-sm">
              <p className="font-medium mb-1">Repository Monitoring</p>
              <p>Click on any repository to view its configuration. Use the edit button to modify settings. Only active repositories will be monitored for pull requests and issues.</p>
            </div>
            <button
              onClick={() => {
                setDismissedInfo(true);
                localStorage.setItem('dismissedRepositoryInfo', 'true');
              }}
              className="ml-3 text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

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
            {sortRepositories(repositories).map((repo) => (
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
                          <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${getRepositoryStatusColor(getRepositoryStatus(repo))}`}>
                            {React.createElement(getRepositoryStatusIcon(getRepositoryStatus(repo)), { className: "h-3 w-3 mr-1" })}
                            {formatRepositoryStatus(getRepositoryStatus(repo))}
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
                        <h4 className="text-lg font-medium text-gray-900 dark:text-white">Repository Management</h4>
                        <div className="flex items-center space-x-3">
                          {editingRepo !== repo.id ? (
                            <>
                              {/* Active Toggle */}
                              <button
                                onClick={() => toggleRepositoryActive(repo.id, repo.is_active)}
                                className={`flex items-center px-4 py-2 text-sm font-medium rounded-lg transition-colors duration-200 ${
                                  repo.is_active
                                    ? 'text-orange-600 bg-orange-50 dark:bg-orange-900/30 dark:text-orange-400 hover:bg-orange-100 dark:hover:bg-orange-900/50'
                                    : 'text-green-600 bg-green-50 dark:bg-green-900/30 dark:text-green-400 hover:bg-green-100 dark:hover:bg-green-900/50'
                                }`}
                              >
                                {repo.is_active ? (
                                  <X className="h-4 w-4 mr-2" />
                                ) : (
                                  <Check className="h-4 w-4 mr-2" />
                                )}
                                {repo.is_active ? 'Deactivate' : 'Activate'}
                              </button>
                              
                              <button
                                onClick={() => checkRunnerHealth(repo.id)}
                                disabled={checkingHealth.has(repo.id)}
                                className="flex items-center px-4 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
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
                                  className="flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  {checkingConfig.has(repo.id) ? (
                                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                  ) : (
                                    <FileText className="h-4 w-4 mr-2" />
                                  )}
                                  Check Config
                                </button>
                              )}


                              <button
                                onClick={() => startEdit(repo.id)}
                                className="flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors duration-200 shadow-sm"
                              >
                                <Edit className="h-4 w-4 mr-2" />
                                Edit
                              </button>
                              <button
                                onClick={() => handleDelete(repo)}
                                className="flex items-center px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600 rounded-lg transition-colors duration-200 shadow-sm"
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

                      {/* Tab Navigation */}
                      <div className="bg-gray-50 dark:bg-gray-900 rounded-lg p-1">
                        <div className="flex space-x-1">
                          {/* Status & Health Tab - Disabled if no auth token */}
                          <button
                            onClick={() => getTokenStatus(repo) === 'configured' && setRepoActiveTab(repo.id, 'status')}
                            disabled={getTokenStatus(repo) !== 'configured'}
                            className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                              getTokenStatus(repo) !== 'configured'
                                ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50'
                                : getRepoActiveTab(repo.id) === 'status'
                                ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                            }`}
                          >
                            <Activity className="h-4 w-4 mr-2" />
                            <span>Status</span>
                          </button>
                          
                          {/* Authentication & General Tab - Always accessible */}
                          <button
                            onClick={() => setRepoActiveTab(repo.id, 'authentication')}
                            className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                              getRepoActiveTab(repo.id) === 'authentication'
                                ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                            }`}
                          >
                            <Key className="h-4 w-4 mr-2" />
                            <span>General</span>
                          </button>
                          
                          {/* Features Tab - Disabled if no auth token */}
                          <button
                            onClick={() => getTokenStatus(repo) === 'configured' && setRepoActiveTab(repo.id, 'features')}
                            disabled={getTokenStatus(repo) !== 'configured'}
                            className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                              getTokenStatus(repo) !== 'configured'
                                ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50'
                                : getRepoActiveTab(repo.id) === 'features'
                                ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                            }`}
                          >
                            <Settings className="h-4 w-4 mr-2" />
                            <span>Features</span>
                          </button>
                          
                          {/* Best Practices Tab - Disabled if no auth token */}
                          <button
                            onClick={() => {
                              if (getTokenStatus(repo) === 'configured') {
                                setRepoActiveTab(repo.id, 'best-practices');
                                // Auto-fetch best practices if not already loaded
                                if (!bestPracticesData[repo.id] && !loadingBestPractices.has(repo.id)) {
                                  loadBestPractices(repo.id);
                                }
                              }
                            }}
                            disabled={getTokenStatus(repo) !== 'configured'}
                            className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                              getTokenStatus(repo) !== 'configured'
                                ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50'
                                : getRepoActiveTab(repo.id) === 'best-practices'
                                ? 'bg-white dark:bg-gray-700 text-purple-600 dark:text-purple-400 shadow-sm'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                            }`}
                          >
                            <Shield className="h-4 w-4 mr-2" />
                            <span>Best Practices</span>
                          </button>

                          {/* PR-Agent Config Tab - Disabled if no auth token */}
                          <button
                            onClick={() => {
                              if (getTokenStatus(repo) === 'configured') {
                                setRepoActiveTab(repo.id, 'pr-agent-config');
                                // Auto-fetch PR-Agent config if not already loaded
                                if (!prAgentConfigData[repo.id] && !loadingPrAgentConfig.has(repo.id)) {
                                  loadPrAgentConfig(repo.id);
                                }
                              }
                            }}
                            disabled={getTokenStatus(repo) !== 'configured'}
                            className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                              getTokenStatus(repo) !== 'configured'
                                ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50'
                                : getRepoActiveTab(repo.id) === 'pr-agent-config'
                                ? 'bg-white dark:bg-gray-700 text-indigo-600 dark:text-indigo-400 shadow-sm'
                                : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                            }`}
                          >
                            <Settings className="h-4 w-4 mr-2" />
                            <span>PR-Agent Config</span>
                          </button>
                        </div>
                      </div>

                      {/* Tab Content */}
                      <div className="space-y-6">
                        {/* Status & Health Tab */}
                        {getRepoActiveTab(repo.id) === 'status' && (
                          <div className="space-y-6 tab-enter">
                            {/* Runner Health Status */}
                            {repo.runner_status && (
                              <div className="bg-gradient-to-r from-green-50 to-blue-50 dark:from-green-900/20 dark:to-blue-900/20 rounded-lg p-6 border border-green-200 dark:border-green-700">
                                <div className="flex items-center justify-between mb-4">
                                  <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                    <Activity className="h-5 w-5 mr-2 text-green-600 dark:text-green-400" />
                                    Runner Health Status
                                  </h4>
                                  <span className={`inline-flex items-center px-3 py-1 rounded-full text-sm font-medium ${getRunnerStatusColor(repo.runner_status)}`}>
                                    {React.createElement(getRunnerStatusIcon(repo.runner_status), { className: "h-4 w-4 mr-1" })}
                                    {formatRunnerStatus(repo.runner_status)}
                                  </span>
                                </div>
                                <div className="space-y-3 text-sm">
                                  {repo.runner_error && (
                                    <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                                      <div className="text-red-600 dark:text-red-400">
                                        <span className="font-medium">Error:</span> {repo.runner_error}
                                      </div>
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

                            {/* Enhanced Configuration Status */}
                            {shouldShowConfigStatus(repo) && (
                              <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700 shadow-sm">
                                <div className="flex items-center justify-between mb-4">
                                  <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                    <FileText className="h-5 w-5 mr-2 text-purple-600 dark:text-purple-400" />
                                    Configuration Status
                                  </h4>
                                  <div className="flex items-center justify-end">
                                    <button
                                      onClick={() => loadEffectiveConfig(repo.id)}
                                      className="flex items-center px-3 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 dark:bg-purple-500 dark:hover:bg-purple-600 rounded-lg transition-colors duration-200 shadow-sm"
                                    >
                                      <Eye className="h-4 w-4 mr-2" />
                                      View Effective Config
                                    </button>
                                  </div>
                                </div>
                                
                                <div className="space-y-4">
                                  {/* Configuration Summary */}
                                  <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                                    {/* System Default */}
                                    <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-4 border border-green-200 dark:border-green-700">
                                      <div className="flex items-center mb-2">
                                        <Settings className="h-4 w-4 text-green-600 dark:text-green-400 mr-2" />
                                        <span className="font-medium text-green-900 dark:text-green-200 text-sm">System Default</span>
                                      </div>
                                      <p className="text-xs text-gray-600 dark:text-gray-400">Base PR-Agent configuration from dashboard settings</p>
                                      <div className="mt-2">
                                        <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200">
                                          <Check className="h-3 w-3 mr-1" />
                                          Always Active
                                        </span>
                                      </div>
                                    </div>

                                    {/* Repository Config */}
                                    <div className={`rounded-lg p-4 border ${
                                      repo.has_pr_agent_config 
                                        ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700'
                                        : 'bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600'
                                    }`}>
                                      <div className="flex items-center mb-2">
                                        <FileText className={`h-4 w-4 mr-2 ${
                                          repo.has_pr_agent_config 
                                            ? 'text-green-600 dark:text-green-400'
                                            : 'text-gray-400 dark:text-gray-500'
                                        }`} />
                                        <span className={`font-medium text-sm ${
                                          repo.has_pr_agent_config
                                            ? 'text-green-900 dark:text-green-200'
                                            : 'text-gray-600 dark:text-gray-400'
                                        }`}>Repository Config</span>
                                      </div>
                                      <p className="text-xs text-gray-600 dark:text-gray-400">Custom .pr_agent.toml in repository root</p>
                                      <div className="mt-2">
                                        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs ${
                                          repo.has_pr_agent_config
                                            ? 'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200'
                                            : 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-400'
                                        }`}>
                                          {repo.has_pr_agent_config ? (
                                            <>
                                              <Check className="h-3 w-3 mr-1" />
                                              {repo.effective_config?.override_keys?.length 
                                                ? `${repo.effective_config.override_keys.length} overrides`
                                                : 'Active'
                                              }
                                            </>
                                          ) : (
                                            <>
                                              <X className="h-3 w-3 mr-1" />
                                              Not Found
                                            </>
                                          )}
                                        </span>
                                      </div>
                                    </div>

                                    {/* Workflow Config */}
                                    <div className={`rounded-lg p-4 border ${
                                      repo.has_workflow_config 
                                        ? 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-700'
                                        : 'bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600'
                                    }`}>
                                      <div className="flex items-center mb-2">
                                        <Github className={`h-4 w-4 mr-2 ${
                                          repo.has_workflow_config 
                                            ? 'text-blue-600 dark:text-blue-400'
                                            : 'text-gray-400 dark:text-gray-500'
                                        }`} />
                                        <span className={`font-medium text-sm ${
                                          repo.has_workflow_config
                                            ? 'text-blue-900 dark:text-blue-200'
                                            : 'text-gray-600 dark:text-gray-400'
                                        }`}>GitHub Workflow</span>
                                      </div>
                                      <p className="text-xs text-gray-600 dark:text-gray-400">Environment variables from .github/workflows/pr_agent.yml</p>
                                      <div className="mt-2">
                                        <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs ${
                                          repo.has_workflow_config
                                            ? 'bg-blue-200 dark:bg-blue-800 text-blue-800 dark:text-blue-200'
                                            : 'bg-gray-200 dark:bg-gray-600 text-gray-600 dark:text-gray-400'
                                        }`}>
                                          {repo.has_workflow_config ? (
                                            <>
                                              <Check className="h-3 w-3 mr-1" />
                                              {repo.effective_config?.workflow_config?.configuration_overrides 
                                                ? `${Object.keys(repo.effective_config.workflow_config.configuration_overrides).length} env vars`
                                                : 'Active'
                                              }
                                            </>
                                          ) : (
                                            <>
                                              <X className="h-3 w-3 mr-1" />
                                              Not Found
                                            </>
                                          )}
                                        </span>
                                      </div>
                                    </div>

                                  </div>

                                  {/* Configuration Priority Info */}
                                  <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4">
                                    <div className="flex items-start">
                                      <Info className="h-4 w-4 text-amber-600 dark:text-amber-400 mr-2 mt-0.5 flex-shrink-0" />
                                      <div className="text-sm">
                                        <p className="font-medium text-amber-800 dark:text-amber-200 mb-1">Configuration Priority</p>
                                        <p className="text-amber-700 dark:text-amber-300">
                                          Settings are applied in this order: <span className="font-mono">System Default</span> → 
                                          <span className="font-mono"> .pr_agent.toml</span> → 
                                          <span className="font-mono"> GitHub Workflow Env</span>. 
                                          Later sources override earlier ones.
                                        </p>
                                      </div>
                                    </div>
                                  </div>

                                  {/* Basic Status */}
                                  <div className="text-sm text-gray-600 dark:text-gray-400 pt-2 border-t border-gray-200 dark:border-gray-700">
                                    <span className="font-medium">Last checked:</span> {formatLastChecked(repo.config_last_checked)}
                                  </div>

                                  {/* Configuration Not Checked */}
                                  {!repo.config_last_checked && (
                                    <div className="text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3 flex items-center">
                                      <AlertCircle className="h-4 w-4 mr-2 flex-shrink-0" />
                                      <span className="font-medium">Configuration not yet checked. Use "Check Config" button above.</span>
                                    </div>
                                  )}
                                </div>
                              </div>
                            )}
                          </div>
                        )}



                        {/* Authentication & General Tab */}
                        {getRepoActiveTab(repo.id) === 'authentication' && (
                          <div className="space-y-6 tab-enter">
                            {/* Repository Information */}
                            <div className="bg-gradient-to-r from-blue-50 to-cyan-50 dark:from-blue-900/20 dark:to-cyan-900/20 rounded-lg p-6 border border-blue-200 dark:border-blue-700">
                              <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-4 flex items-center">
                                <Info className="h-5 w-5 mr-2 text-blue-600 dark:text-blue-400" />
                                Repository Information
                              </h4>
                              
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
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
                                    <div className="px-4 py-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
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
                                    <div className="px-4 py-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
                                      <div className="flex items-center">
                                        {getProviderIcon(repo.provider)}
                                        <span className="ml-2 text-gray-900 dark:text-white font-medium capitalize">{repo.provider.replace('_', ' ')}</span>
                                      </div>
                                    </div>
                                  )}
                                </div>
                              </div>

                              <div className="mt-4">
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
                                  <div className="px-4 py-3 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-600">
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
                            </div>

                            {/* Access Token Configuration */}
                            <div className="bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20 rounded-lg p-6 border border-purple-200 dark:border-purple-700">
                              <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-4 flex items-center">
                                <Key className="h-5 w-5 mr-2 text-purple-600 dark:text-purple-400" />
                                Access Token Configuration
                              </h4>
                              
                              <div className="space-y-4">
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
                                            {repo.has_github_token ? '••••••••••••••••••••••••••••••••••••••••' : 'Not configured'}
                                          </span>
                                          {repo.has_github_token && (
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
                                            {repo.has_azure_pat ? '••••••••••••••••••••••••••••••••••••••••••••••••••••' : 'Not configured'}
                                          </span>
                                          {repo.has_azure_pat && (
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
                                  <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
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
                            </div>
                          </div>
                        )}

                        {/* Features Tab (renamed from Configuration) */}
                        {getRepoActiveTab(repo.id) === 'features' && (
                          <div className="space-y-6 tab-enter">
                            <div className="bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-lg p-6 border border-green-200 dark:border-green-700">
                              <h4 className="text-lg font-medium text-gray-900 dark:text-white mb-4 flex items-center">
                                <Settings className="h-5 w-5 mr-2 text-green-600 dark:text-green-400" />
                                Feature Configuration
                              </h4>
                              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {[
                                  { key: 'monitor_prs', label: 'Monitor PRs', description: 'Watch pull requests' },
                                  { key: 'monitor_issues', label: 'Monitor Issues', description: 'Watch issues' },
                                  { key: 'auto_review', label: 'Auto Review', description: 'Automatically review PRs' },
                                  { key: 'auto_describe', label: 'Auto Describe', description: 'Generate PR descriptions' },
                                  { key: 'auto_improve', label: 'Auto Improve', description: 'Suggest improvements' }
                                ].map(({ key, label, description }) => {
                                  const isEnabled = formData[key];
                                  const isEditing = editingRepo === repo.id;
                                  
                                  return (
                                    <div
                                      key={key}
                                      onClick={() => isEditing && setFormData({ ...formData, [key]: !formData[key] })}
                                      className={`relative p-4 rounded-lg border-2 transition-all duration-300 ${
                                        isEnabled
                                          ? `border-green-300 dark:border-green-600 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/30 dark:to-green-800/30 ${
                                              isEditing ? 'shadow-lg shadow-green-200/40 dark:shadow-green-400/20' : ''
                                            }`
                                          : `border-gray-200 dark:border-gray-700 bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800/50 dark:to-gray-700/50 ${
                                              isEditing ? 'shadow-lg shadow-gray-200/40 dark:shadow-gray-400/20' : ''
                                            }`
                                      } ${
                                        isEditing 
                                          ? 'cursor-pointer hover:border-blue-400 dark:hover:border-blue-500 hover:shadow-2xl hover:-translate-y-1 transform shadow-lg' 
                                          : 'cursor-default shadow-sm'
                                      }`}
                                    >


                                      {/* Feature Info */}
                                      <div>
                                        <h4 className={`text-base font-medium transition-colors ${
                                          isEnabled
                                            ? 'text-green-800 dark:text-green-200'
                                            : 'text-gray-700 dark:text-gray-300'
                                        }`}>
                                          {label}
                                        </h4>
                                        <p className={`text-sm mt-1 transition-colors ${
                                          isEnabled
                                            ? 'text-green-600 dark:text-green-300'
                                            : 'text-gray-500 dark:text-gray-400'
                                        }`}>
                                          {description}
                                        </p>
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* Best Practices Tab */}
                        {getRepoActiveTab(repo.id) === 'best-practices' && (
                          <div className="space-y-6 tab-enter">
                            <div className="bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20 rounded-lg p-6 border border-purple-200 dark:border-purple-700">
                              <div className="flex items-center justify-between mb-6">
                                <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                  <Shield className="h-5 w-5 mr-2 text-purple-600 dark:text-purple-400" />
                                  Repository Best Practices
                                </h4>
                                <div className="flex items-center space-x-2">
                                  {/* PR Status Display */}
                                  {bestPracticesData[repo.id]?.has_pending_pr && (
                                    <div className="flex items-center bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 px-3 py-1 rounded-lg border border-yellow-200 dark:border-yellow-700 mr-2">
                                      <GitBranch className="h-4 w-4 mr-1" />
                                      <span className="text-sm font-medium">
                                        PR #{bestPracticesData[repo.id].pr_number} Pending
                                      </span>
                                      <a 
                                        href={bestPracticesData[repo.id].pr_url} 
                                        target="_blank" 
                                        rel="noopener noreferrer"
                                        className="ml-1 hover:text-yellow-900 dark:hover:text-yellow-100"
                                      >
                                        <ExternalLink className="h-3 w-3" />
                                      </a>
                                      <button
                                        onClick={() => checkPRStatus(repo.id)}
                                        className="ml-2 hover:text-yellow-900 dark:hover:text-yellow-100"
                                        title="Check PR status"
                                      >
                                        <RefreshCw className="h-3 w-3" />
                                      </button>
                                    </div>
                                  )}
                                  
                                  {!isEditingBestPractices[repo.id] && (
                                    <>
                                      <button
                                        onClick={() => loadBestPractices(repo.id, true)}
                                        disabled={loadingBestPractices.has(repo.id)}
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 dark:bg-purple-500 dark:hover:bg-purple-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                      >
                                        <RefreshCw className={`h-4 w-4 mr-2 ${loadingBestPractices.has(repo.id) ? 'animate-spin' : ''}`} />
                                        {loadingBestPractices.has(repo.id) ? 'Loading...' : 'Refresh'}
                                      </button>
                                      <button
                                        onClick={() => startEditingBestPractices(repo.id)}
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 rounded-lg transition-colors duration-200 shadow-sm"
                                      >
                                        <Edit className="h-4 w-4 mr-2" />
                                        {bestPracticesData[repo.id]?.exists ? 'Edit' : 'Create'}
                                      </button>
                                    </>
                                  )}
                                  
                                  {isEditingBestPractices[repo.id] && (
                                    <>
                                      <button
                                        onClick={() => cancelEditingBestPractices(repo.id)}
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 dark:bg-gray-500 dark:hover:bg-gray-600 rounded-lg transition-colors duration-200 shadow-sm"
                                      >
                                        <X className="h-4 w-4 mr-2" />
                                        Cancel
                                      </button>
                                      <button
                                        onClick={() => saveBestPractices(repo.id)}
                                        disabled={savingBestPractices[repo.id] || !editedBestPracticesContent[repo.id]?.trim()}
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700 transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                                      >
                                        <GitBranch className={`h-4 w-4 mr-2 ${savingBestPractices[repo.id] ? 'animate-spin' : ''}`} />
                                        {savingBestPractices[repo.id] ? 'Creating PR...' : 'Create PR'}
                                      </button>
                                    </>
                                  )}
                                </div>
                              </div>
                              
                              {/* Edit Mode */}
                              {isEditingBestPractices[repo.id] ? (
                                <div className="space-y-4">
                                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                                    <div className="flex items-start">
                                      <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
                                      <div>
                                        <h6 className="font-medium text-blue-800 dark:text-blue-200 mb-2">Creating/Updating via Pull Request</h6>
                                        <div className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
                                          <p>• Changes will be submitted as a pull request for review</p>
                                          <p>• PR-Agent will automatically enforce practices once the PR is merged</p>
                                          <p>• Further edits will add commits to the same PR branch</p>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                  
                                  <div className="bg-white dark:bg-gray-800 rounded-lg border border-purple-100 dark:border-purple-700 overflow-hidden">
                                    <div className="bg-purple-50 dark:bg-purple-900/30 px-4 py-3 border-b border-purple-100 dark:border-purple-700">
                                      <h5 className="font-medium text-purple-900 dark:text-purple-200 text-sm flex items-center">
                                        <Edit className="h-4 w-4 mr-2" />
                                        Editing: best_practices.md
                                      </h5>
                                    </div>
                                    <div className="p-4">
                                      <textarea
                                        value={editedBestPracticesContent[repo.id] || ''}
                                        onChange={(e) => setEditedBestPracticesContent(prev => ({
                                          ...prev,
                                          [repo.id]: e.target.value
                                        }))}
                                        placeholder="# Best Practices&#10;&#10;## Coding Standards&#10;- Use clear, descriptive variable names&#10;- Write unit tests for all functions&#10;- Follow consistent formatting&#10;&#10;## Code Review Guidelines&#10;- All PRs require at least one review&#10;- Test coverage must be above 80%&#10;&#10;## Documentation&#10;- Update README for any API changes&#10;- Add inline comments for complex logic"
                                        className="w-full h-96 px-4 py-3 border border-gray-200 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-purple-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono text-sm resize-none"
                                      />
                                      <p className="text-xs text-gray-500 dark:text-gray-400 mt-2">
                                        Use Markdown formatting. Define your coding standards, style guides, and development practices.
                                      </p>
                                    </div>
                                  </div>
                                </div>
                              ) : (
                                /* View Mode */
                                loadingBestPractices.has(repo.id) ? (
                                  <div className="flex items-center justify-center py-8">
                                    <RefreshCw className="h-6 w-6 text-purple-600 dark:text-purple-400 animate-spin mr-3" />
                                    <span className="text-gray-600 dark:text-gray-400">Loading best practices...</span>
                                  </div>
                                ) : bestPracticesData[repo.id]?.error ? (
                                  <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                                    <div className="flex items-center">
                                      <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
                                      <div>
                                        <h5 className="font-medium text-red-800 dark:text-red-200">Error Loading Best Practices</h5>
                                        <p className="text-red-700 dark:text-red-300 text-sm mt-1">{bestPracticesData[repo.id].error}</p>
                                      </div>
                                    </div>
                                  </div>
                                ) : bestPracticesData[repo.id]?.exists ? (
                                  <div className="bg-white dark:bg-gray-800 rounded-lg border border-purple-100 dark:border-purple-700 overflow-hidden">
                                    <div className="bg-purple-50 dark:bg-purple-900/30 px-4 py-3 border-b border-purple-100 dark:border-purple-700 flex items-center justify-between">
                                      <h5 className="font-medium text-purple-900 dark:text-purple-200 text-sm flex items-center">
                                        <FileText className="h-4 w-4 mr-2" />
                                        best_practices.md
                                      </h5>
                                      {bestPracticesData[repo.id].last_fetched && (
                                        <span className="text-xs text-purple-700 dark:text-purple-300">
                                          Updated: {new Date(bestPracticesData[repo.id].last_fetched).toLocaleString()}
                                        </span>
                                      )}
                                    </div>
                                    <div className="px-4 py-3">
                                      <div 
                                        className="prose prose-sm max-w-none best-practices-markdown"
                                        dangerouslySetInnerHTML={{
                                          __html: bestPracticesData[repo.id].content_html || 'No content available'
                                        }}
                                      />
                                    </div>
                                  </div>
                                ) : bestPracticesData[repo.id] !== undefined ? (
                                  <div className="text-center py-8">
                                    <Shield className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500 mb-4" />
                                    <h5 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No Best Practices Found</h5>
                                    <p className="text-gray-500 dark:text-gray-400 mb-4">
                                      Create a <code className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-sm">best_practices.md</code> file to define coding standards and guidelines.
                                    </p>
                                    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 text-left max-w-2xl mx-auto">
                                      <div className="flex items-start">
                                        <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
                                        <div>
                                          <h6 className="font-medium text-blue-800 dark:text-blue-200 mb-2">How Best Practices Work</h6>
                                          <div className="text-sm text-blue-700 dark:text-blue-300 space-y-2">
                                            <p>• Click "Create" to add a <code>best_practices.md</code> file via pull request</p>
                                            <p>• Define coding standards, style guides, and development practices</p>
                                            <p>• PR-Agent will automatically check code against these practices</p>
                                            <p>• Violations will be flagged as "best practice" suggestions</p>
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                ) : (
                                  <div className="text-center py-8">
                                    <Shield className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500 mb-4" />
                                    <h5 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Best Practices</h5>
                                    <p className="text-gray-500 dark:text-gray-400 mb-4">
                                      Click "Refresh" to check for a best_practices.md file in your repository.
                                    </p>
                                  </div>
                                )
                              )}
                            </div>
                          </div>
                        )}

                        {/* PR-Agent Config Tab */}
                        {getRepoActiveTab(repo.id) === 'pr-agent-config' && (
                          <div className="space-y-6 tab-enter">
                            <div className="bg-gradient-to-r from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 rounded-lg p-6 border border-indigo-200 dark:border-indigo-700">
                              <div className="flex items-center justify-between mb-6">
                                <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                  <Settings className="h-5 w-5 mr-2 text-indigo-600 dark:text-indigo-400" />
                                  PR-Agent Configuration
                                </h4>
                                <div className="flex items-center space-x-2">
                                  {/* PR Status Display */}
                                  {prAgentConfigData[repo.id]?.pr_status === 'pending' && prAgentConfigData[repo.id]?.pr_url && (
                                    <div className="flex items-center bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 px-3 py-1 rounded-lg border border-yellow-200 dark:border-yellow-700 mr-2">
                                      <GitBranch className="h-4 w-4 mr-1" />
                                      <span className="text-sm font-medium">
                                        {checkingPrStatus.has(repo.id) ? (
                                          <>
                                            <RefreshCw className="h-3 w-3 animate-spin inline mr-1" />
                                            Checking PR #{prAgentConfigData[repo.id].pr_number}...
                                          </>
                                        ) : (
                                          <>
                                            PR #{prAgentConfigData[repo.id].pr_number} Pending
                                          </>
                                        )}
                                      </span>
                                      <a 
                                        href={prAgentConfigData[repo.id].pr_url} 
                                        target="_blank" 
                                        rel="noopener noreferrer"
                                        className="ml-1 hover:text-yellow-900 dark:hover:text-yellow-100"
                                      >
                                        <ExternalLink className="h-3 w-3" />
                                      </a>
                                      <button
                                        onClick={() => checkPrAgentConfigPRStatus(repo.id)}
                                        disabled={checkingPrStatus.has(repo.id)}
                                        className="ml-2 hover:text-yellow-900 dark:hover:text-yellow-100 disabled:opacity-50 disabled:cursor-not-allowed"
                                        title={checkingPrStatus.has(repo.id) ? "Checking..." : "Check PR status"}
                                      >
                                        <RefreshCw className={`h-3 w-3 ${checkingPrStatus.has(repo.id) ? 'animate-spin' : ''}`} />
                                      </button>
                                    </div>
                                  )}
                                  
                                  <button
                                    onClick={() => loadPrAgentConfig(repo.id, true)}
                                    disabled={loadingPrAgentConfig.has(repo.id)}
                                    className="flex items-center px-3 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    <RefreshCw className={`h-4 w-4 mr-2 ${loadingPrAgentConfig.has(repo.id) ? 'animate-spin' : ''}`} />
                                    {loadingPrAgentConfig.has(repo.id) ? 'Loading...' : 'Refresh'}
                                  </button>
                                  <button
                                    onClick={() => openPrAgentConfigEditor(repo.id)}
                                    className="flex items-center px-3 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 dark:bg-purple-500 dark:hover:bg-purple-600 rounded-lg transition-colors duration-200 shadow-sm"
                                  >
                                    <Edit className="h-4 w-4 mr-2" />
                                    {prAgentConfigData[repo.id]?.has_config ? 'Edit Config' : 'Create Config'}
                                  </button>
                                </div>
                              </div>
                              
                              {/* Config Status */}
                              {loadingPrAgentConfig.has(repo.id) ? (
                                <div className="flex items-center justify-center py-8">
                                  <RefreshCw className="h-6 w-6 text-indigo-600 dark:text-indigo-400 animate-spin mr-3" />
                                  <span className="text-gray-600 dark:text-gray-400">Loading PR-Agent configuration...</span>
                                </div>
                              ) : prAgentConfigData[repo.id]?.parse_error ? (
                                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                                  <div className="flex items-center">
                                    <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
                                    <div>
                                      <h5 className="font-medium text-red-800 dark:text-red-200">Configuration Parse Error</h5>
                                      <p className="text-red-700 dark:text-red-300 text-sm mt-1">{prAgentConfigData[repo.id].parse_error}</p>
                                      <p className="text-red-600 dark:text-red-400 text-xs mt-2">Please fix the TOML syntax to resolve this error.</p>
                                    </div>
                                  </div>
                                </div>
                              ) : prAgentConfigData[repo.id]?.has_config ? (
                                <div className="bg-white dark:bg-gray-800 rounded-lg border border-indigo-100 dark:border-indigo-700 overflow-hidden">
                                  <div className="bg-indigo-50 dark:bg-indigo-900/30 px-4 py-3 border-b border-indigo-100 dark:border-indigo-700 flex items-center justify-between">
                                    <h5 className="font-medium text-indigo-900 dark:text-indigo-200 text-sm flex items-center">
                                      <FileText className="h-4 w-4 mr-2" />
                                      .pr_agent.toml
                                    </h5>
                                    {prAgentConfigData[repo.id].last_fetched && (
                                      <span className="text-xs text-indigo-700 dark:text-indigo-300">
                                        Updated: {new Date(prAgentConfigData[repo.id].last_fetched).toLocaleString()}
                                      </span>
                                    )}
                                  </div>
                                  <div className="px-4 py-3">
                                                        {prAgentConfigData[repo.id].parsed_config ? (
                      <div className="space-y-4">
                        <div className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                          <strong>Overridden Settings:</strong>
                        </div>
                        <div className="space-y-3">
                          {Object.entries(prAgentConfigData[repo.id].parsed_config).map(([section, settings]) => (
                            <div key={section} className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                              <div className="font-mono text-sm font-semibold text-gray-900 dark:text-white mb-3 pb-2 border-b border-gray-200 dark:border-gray-600">
                                [{section}]
                              </div>
                              <div className="space-y-2">
                                {Object.entries(settings || {}).map(([key, value]) => (
                                  <div key={key} className="flex items-start justify-between">
                                    <div className="font-mono text-xs text-gray-700 dark:text-gray-300 font-medium">
                                      {key}
                                    </div>
                                    <div className="font-mono text-xs text-gray-600 dark:text-gray-400 ml-3 text-right max-w-xs">
                                      {Array.isArray(value) 
                                        ? `[${value.join(', ')}]`
                                        : typeof value === 'object'
                                          ? JSON.stringify(value)
                                          : String(value).length > 50
                                            ? `${String(value).substring(0, 50)}...`
                                            : String(value)
                                      }
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ) : (
                                      <div className="bg-gray-50 dark:bg-gray-700 rounded p-3">
                                        <pre className="text-xs text-gray-700 dark:text-gray-300 font-mono whitespace-pre-wrap">
                                          {prAgentConfigData[repo.id].content || 'No content available'}
                                        </pre>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ) : prAgentConfigData[repo.id] !== undefined ? (
                                <div className="text-center py-8">
                                  <Settings className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500 mb-4" />
                                  <h5 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No Configuration Override Found</h5>
                                  <p className="text-gray-500 dark:text-gray-400 mb-4">
                                    Create a <code className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-sm">.pr_agent.toml</code> file to override global settings for this repository.
                                  </p>
                                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 text-left max-w-2xl mx-auto">
                                    <div className="flex items-start">
                                      <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
                                      <div>
                                        <h6 className="font-medium text-blue-800 dark:text-blue-200 mb-2">How Repository Configuration Works</h6>
                                        <div className="text-sm text-blue-700 dark:text-blue-300 space-y-2">
                                          <p>• Click "Create Config" to add repository-specific settings</p>
                                          <p>• Override any global PR-Agent setting for this repository</p>
                                          <p>• Configure models, thresholds, prompts, and behavior</p>
                                          <p>• Changes are deployed via pull request for review</p>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                </div>
                              ) : (
                                <div className="text-center py-8">
                                  <Settings className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500 mb-4" />
                                  <h5 className="text-lg font-medium text-gray-900 dark:text-white mb-2">PR-Agent Configuration</h5>
                                  <p className="text-gray-500 dark:text-gray-400 mb-4">
                                    Click "Refresh" to check for a .pr_agent.toml file in your repository.
                                  </p>
                                </div>
                              )}
                            </div>
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

      {/* PR-Agent Config Editor Modal */}
      {showPrAgentConfigEditor && (
        <PrAgentConfigEditor
          repositoryId={showPrAgentConfigEditor}
          repositoryName={repositories.find(r => r.id === showPrAgentConfigEditor)?.name || 'Repository'}
          isOpen={true}
          onClose={closePrAgentConfigEditor}
          onSave={handlePrAgentConfigSave}
        />
      )}

      {/* Effective Configuration Modal */}
      {effectiveConfigModal.show && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
          <div className="bg-white dark:bg-gray-800 rounded-xl shadow-2xl max-w-6xl w-full max-h-[90vh] overflow-hidden">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700 bg-gradient-to-r from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20">
              <div className="flex items-center">
                <FileText className="h-6 w-6 text-purple-600 dark:text-purple-400 mr-3" />
                <div>
                  <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                    Effective Configuration
                  </h2>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
                    {effectiveConfigModal.data?.repository && `Repository: ${effectiveConfigModal.data.repository}`}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setEffectiveConfigModal(prev => ({ ...prev, show: false }))}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
              >
                <X className="h-6 w-6" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-6 overflow-y-auto max-h-[calc(90vh-120px)]">
              {effectiveConfigModal.loading ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <RefreshCw className="h-8 w-8 text-purple-600 dark:text-purple-400 animate-spin mb-4" />
                  <p className="text-gray-600 dark:text-gray-400">Loading effective configuration...</p>
                </div>
              ) : effectiveConfigModal.error ? (
                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-6">
                  <div className="flex items-center">
                    <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
                    <div>
                      <h3 className="font-medium text-red-800 dark:text-red-200">Error Loading Configuration</h3>
                      <p className="text-red-700 dark:text-red-300 mt-1">{effectiveConfigModal.error}</p>
                    </div>
                  </div>
                </div>
              ) : effectiveConfigModal.data ? (
                <div className="space-y-6">
                  {/* Configuration Priority Explanation */}
                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                    <div className="flex items-start">
                      <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
                      <div>
                        <h3 className="font-medium text-blue-800 dark:text-blue-200 mb-2">Configuration Priority Order</h3>
                        <div className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
                          <div className="flex items-center">
                            <span className="bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded font-mono text-xs mr-2">1</span>
                            <span>System Default Configuration (from dashboard settings)</span>
                          </div>
                          <div className="flex items-center">
                            <span className="bg-green-100 dark:bg-green-700 px-2 py-1 rounded font-mono text-xs mr-2">2</span>
                            <span>Repository Configuration (.pr_agent.toml in repository root)</span>
                          </div>
                          <div className="flex items-center">
                            <span className="bg-blue-100 dark:bg-blue-700 px-2 py-1 rounded font-mono text-xs mr-2">3</span>
                            <span>GitHub Workflow Environment Variables (.github/workflows/pr_agent.yml)</span>
                          </div>
                          <p className="text-xs mt-2 italic">Higher priority sources override settings from lower priority sources. Only overridden values are shown below.</p>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Environment Variables Section */}
                  {effectiveConfigModal.data.workflow_config?.configuration_overrides && Object.keys(effectiveConfigModal.data.workflow_config.configuration_overrides).length > 0 && (
                    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-6">
                      <div className="flex items-center mb-4">
                        <Github className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3" />
                        <h3 className="text-lg font-medium text-blue-900 dark:text-blue-200">Environment Variables</h3>
                        <span className="ml-2 bg-blue-200 dark:bg-blue-700 text-blue-800 dark:text-blue-200 px-2 py-1 rounded-full text-xs">Highest Priority</span>
                      </div>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                        {Object.entries(effectiveConfigModal.data.workflow_config.configuration_overrides).map(([envKey, envInfo]) => (
                          <div key={envKey} className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-blue-100 dark:border-blue-700">
                            <div className="flex items-start justify-between mb-2">
                              <span className="font-mono text-sm font-medium text-blue-700 dark:text-blue-300">{envKey}</span>
                              {envInfo.is_secret && (
                                <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-yellow-100 dark:bg-yellow-900/30 text-yellow-800 dark:text-yellow-200 ml-2">
                                  <Shield className="h-3 w-3 mr-1" />
                                  Secret: {envInfo.secret_name}
                                </span>
                              )}
                            </div>
                            <div className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                              <span className="font-medium">Value:</span> 
                              <span className="ml-2 font-mono bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-xs">
                                {envInfo.is_secret ? '[SECRET]' : envInfo.value}
                              </span>
                            </div>
                            {envInfo.config_path && (
                              <div className="text-xs text-gray-500 dark:text-gray-400">
                                <span className="font-medium">Maps to:</span> <code className="bg-gray-100 dark:bg-gray-700 px-1 rounded">{envInfo.config_path}</code>
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Repository Configuration Section */}
                  {effectiveConfigModal.data.repository_config && (
                    <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-6">
                      <div className="flex items-center mb-4">
                        <FileText className="h-5 w-5 text-green-600 dark:text-green-400 mr-3" />
                        <h3 className="text-lg font-medium text-green-900 dark:text-green-200">Repository Configuration</h3>
                        <span className="ml-2 bg-green-200 dark:bg-green-700 text-green-800 dark:text-green-200 px-2 py-1 rounded-full text-xs">Medium Priority</span>
                      </div>
                      {effectiveConfigModal.data.override_keys && effectiveConfigModal.data.override_keys.length > 0 && (
                        <div className="mb-4">
                          <h4 className="font-medium text-green-800 dark:text-green-200 mb-2">Overridden Keys:</h4>
                          <div className="flex flex-wrap gap-2">
                            {effectiveConfigModal.data.override_keys.map((key, index) => (
                              <span key={index} className="bg-green-100 dark:bg-green-800 text-green-800 dark:text-green-200 px-2 py-1 rounded-full text-xs font-mono">
                                {key}
                              </span>
                            ))}
                          </div>
                        </div>
                      )}
                      <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-green-100 dark:border-green-700">
                        <h4 className="font-medium text-green-800 dark:text-green-200 mb-3">Configuration from .pr_agent.toml:</h4>
                        <pre className="text-sm text-gray-800 dark:text-gray-200 overflow-x-auto whitespace-pre-wrap font-mono bg-gray-50 dark:bg-gray-900 p-3 rounded border max-h-64 overflow-y-auto">
                          {JSON.stringify(effectiveConfigModal.data.repository_config, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* Runner Configuration Section */}
                  {effectiveConfigModal.data.workflow_config?.runner_config && (
                    <div className="bg-gray-50 dark:bg-gray-900/20 border border-gray-200 dark:border-gray-700 rounded-lg p-6">
                      <div className="flex items-center mb-4">
                        <Server className="h-5 w-5 text-gray-600 dark:text-gray-400 mr-3" />
                        <h3 className="text-lg font-medium text-gray-900 dark:text-gray-200">Runner Configuration</h3>
                      </div>
                      <div className="bg-white dark:bg-gray-800 rounded-lg p-4 border border-gray-200 dark:border-gray-700">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                          <div>
                            <span className="font-medium text-gray-700 dark:text-gray-300">Runs on:</span>
                            <span className="ml-2 font-mono bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded text-xs">
                              {Array.isArray(effectiveConfigModal.data.workflow_config.runner_config.runs_on) 
                                ? effectiveConfigModal.data.workflow_config.runner_config.runs_on.join(', ')
                                : effectiveConfigModal.data.workflow_config.runner_config.runs_on
                              }
                            </span>
                          </div>
                          {effectiveConfigModal.data.workflow_config.runner_config.is_self_hosted && (
                            <div className="flex items-center">
                              <Server className="h-4 w-4 text-green-600 dark:text-green-400 mr-2" />
                              <span className="text-green-700 dark:text-green-300 font-medium">Self-hosted Runner</span>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* No Configuration Found Messages */}
                  {!effectiveConfigModal.data.workflow_config?.configuration_overrides && !effectiveConfigModal.data.repository_config && (
                    <div className="text-center py-8">
                      <Settings className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500 mb-4" />
                      <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">Using Default Configuration</h3>
                      <p className="text-gray-500 dark:text-gray-400">This repository is using the system default configuration with no overrides.</p>
                    </div>
                  )}
                </div>
              ) : null}
            </div>

            {/* Modal Footer */}
            <div className="flex justify-end p-6 border-t border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
              <button
                onClick={() => setEffectiveConfigModal(prev => ({ ...prev, show: false }))}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default RepositoryManager; 