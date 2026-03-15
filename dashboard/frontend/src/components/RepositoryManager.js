import React, { useState, useEffect, useContext, useCallback, useRef } from 'react';
import DOMPurify from 'dompurify';
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
  Copy,
  FileText,
  Eye,
  Key,
  EyeOff,
  Shield,
  Server,
  ExternalLink,
  Download,
  Search
} from 'lucide-react';
import api from '../services/api';
import { ToastContext } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';
import PrAgentConfigEditor from './PrAgentConfigEditor';
import { formatTimestamp } from '../utils/timeUtils';
import GitHubActionConfigEditor from './GitHubActionConfigEditor';
import AzurePipelineConfigEditor from './AzurePipelineConfigEditor';
import SearchableSelect from './SearchableSelect';

export const getAzureRepoKey = (repo) => String(repo?.id || repo?.url || repo?.display_name || '');

export const resolveSelectedRepoKey = (repos, previousKey = '') => {
  if (!Array.isArray(repos) || repos.length === 0) return '';
  if (previousKey && repos.some((repo) => getAzureRepoKey(repo) === previousKey)) {
    return previousKey;
  }
  return getAzureRepoKey(repos[0]);
};

export const deriveAzureOrganizationFromOrgUrl = (orgUrl = '') => {
  try {
    const parsedUrl = new URL(orgUrl);
    const host = (parsedUrl.hostname || '').toLowerCase();
    const pathParts = parsedUrl.pathname.split('/').filter(Boolean);
    if (host === 'dev.azure.com') {
      return pathParts[0] || '';
    }
    if (host.endsWith('.visualstudio.com')) {
      return host.split('.')[0] || '';
    }
    return host.split('.')[0] || '';
  } catch (_) {
    return '';
  }
};

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
    azure_pat: '',
    action_runner_connection_id: null
  });
  const [actionRunnerConnections, setActionRunnerConnections] = useState([]);
  const [originalFormData, setOriginalFormData] = useState(null);
  const [errors, setErrors] = useState({});
  const [checkingHealth, setCheckingHealth] = useState(new Set());
  const [checkingConfig, setCheckingConfig] = useState(new Set());
  const [showTokens, setShowTokens] = useState({});
  const { showSuccess, showError, showWarning } = useContext(ToastContext);

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
  const [isEditingGeneral, setIsEditingGeneral] = useState({});
  const [editedGeneralData, setEditedGeneralData] = useState({});
  const [savingGeneral, setSavingGeneral] = useState(new Set());
  const [loadingBestPractices, setLoadingBestPractices] = useState(new Set());
  
  // PR-Agent config states
  const [prAgentConfigData, setPrAgentConfigData] = useState({});
  const [showPrAgentConfigEditor, setShowPrAgentConfigEditor] = useState(null);
  const [loadingPrAgentConfig, setLoadingPrAgentConfig] = useState(new Set());
  const [checkingPrStatus, setCheckingPrStatus] = useState(new Set());
  
  // GitHub Action config states
  const [githubActionConfigData, setGithubActionConfigData] = useState({});
  const [showGithubActionConfigEditor, setShowGithubActionConfigEditor] = useState(null);
  const [loadingGithubActionConfig, setLoadingGithubActionConfig] = useState(new Set());
  
  // Azure Pipeline config states
  const [azurePipelineConfigData, setAzurePipelineConfigData] = useState({});
  const [showAzurePipelineConfigEditor, setShowAzurePipelineConfigEditor] = useState(null);
  const [loadingAzurePipelineConfig, setLoadingAzurePipelineConfig] = useState(new Set());
  const [checkingGithubActionPrStatus, setCheckingGithubActionPrStatus] = useState(new Set());
  const [checkingAzurePipelinePrStatus, setCheckingAzurePipelinePrStatus] = useState(new Set());

  // Pipeline sync & policy states
  const [syncStatusData, setSyncStatusData] = useState({});
  const [policiesData, setPoliciesData] = useState({});
  const [branchesData, setBranchesData] = useState({});
  const [loadingSyncStatus, setLoadingSyncStatus] = useState(new Set());
  const [pushingYaml, setPushingYaml] = useState(new Set());
  const [syncingPipelineVariables, setSyncingPipelineVariables] = useState(new Set());
  const [verifyingAzureSetup, setVerifyingAzureSetup] = useState(new Set());
  const [autoFixingAzureSetup, setAutoFixingAzureSetup] = useState(new Set());
  const [azureSetupVerification, setAzureSetupVerification] = useState({});
  const [loadingPolicies, setLoadingPolicies] = useState(new Set());
  const [savingPolicy, setSavingPolicy] = useState(new Set());
  const [deletingPolicy, setDeletingPolicy] = useState(new Set());
  const [showAddPolicy, setShowAddPolicy] = useState({});
  const [newPolicyForm, setNewPolicyForm] = useState({});

  // Runner service states
  const [runnerServiceNames, setRunnerServiceNames] = useState({});
  const [runnerServiceStatus, setRunnerServiceStatus] = useState({});
  const [checkingRunnerService, setCheckingRunnerService] = useState(new Set());
  const [savingRunnerServiceName, setSavingRunnerServiceName] = useState(new Set());
  const [availableServices, setAvailableServices] = useState([]);
  const [loadingServices, setLoadingServices] = useState(false);
  const [serviceDropdownOpen, setServiceDropdownOpen] = useState({});

  // Azure agent service state
  const [azureAgentServiceNames, setAzureAgentServiceNames] = useState({});
  const [azureAgentServiceStatus, setAzureAgentServiceStatus] = useState({});
  const [checkingAzureAgentService, setCheckingAzureAgentService] = useState(new Set());
  const [savingAzureAgentServiceName, setSavingAzureAgentServiceName] = useState(new Set());
  const [availableAzureServices, setAvailableAzureServices] = useState([]);
  const [loadingAzureServices, setLoadingAzureServices] = useState(false);
  const [azureServiceDropdownOpen, setAzureServiceDropdownOpen] = useState({});

  // Token testing state
  const [testingTokens, setTestingTokens] = useState(new Set());
  const [tokenTestResults, setTokenTestResults] = useState({});

  // GCP runner VM provision/deprovision
  const [provisionProgressByConnection, setProvisionProgressByConnection] = useState({});
  const checkRunnerServiceRef = useRef(null);
  const consoleEndRef = useRef(null);
  const pendingTimeoutsRef = useRef(new Set());
  const [consoleAutoScrollEnabled, setConsoleAutoScrollEnabled] = useState(true);
  const [showRunnersPanel, setShowRunnersPanel] = useState(false);
  const [deletingRunner, setDeletingRunner] = useState(null);
  const [showCreateRunner, setShowCreateRunner] = useState(false);
  const [newRunnerForm, setNewRunnerForm] = useState({ provider: 'azure_devops', organization: '', project: '', display_name: '', agent_pool: '' });
  const [creatingRunner, setCreatingRunner] = useState(false);
  const [wizardStep, setWizardStep] = useState(0);
  const [wizardState, setWizardState] = useState({
    orgUrl: '',
    pat: '',
    loading: false,
    connected: false,
    repos: [],
    pools: [],
    selectedRepoKey: '',
    selectedPool: '',
    connectionId: null,
    provisioning: false,
    provisioned: false,
    skipRunner: false,
    setupPipeline: true,
    pipelineBranch: '',
    pipelineIsBlocking: false,
    pipelineSetupDone: false,
    pipelineSetupResult: null,
  });
  const [azurePatIdentity, setAzurePatIdentity] = useState({ loading: false, data: null, error: null });
  const [repoCleanupConfirmModal, setRepoCleanupConfirmModal] = useState({
    show: false,
    loading: false,
    repo: null,
    preview: null,
    error: null,
  });
  const [repoActionModal, setRepoActionModal] = useState({
    show: false,
    running: false,
    operationType: '',
    operationId: '',
    repoId: null,
    title: '',
    subtitle: '',
    status: '',
    steps: [],
    message: '',
    error: null,
  });
  const repoActionPollTimeoutRef = useRef(null);

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

  const fetchActionRunnerConnections = useCallback(() => {
    return api.getActionRunnerConnections()
      .then((res) => setActionRunnerConnections(res.data?.data || []))
      .catch(() => setActionRunnerConnections([]));
  }, []);

  useEffect(() => {
    fetchRepositories();
  }, [fetchRepositories]);

  // Load runner connections immediately so collapsed summary is accurate on first render.
  useEffect(() => {
    fetchActionRunnerConnections();
  }, [fetchActionRunnerConnections]);

  useEffect(() => {
    return () => {
      clearRepoActionPollTimeout();
    };
  }, []);

  useEffect(() => {
    const connId = formData.action_runner_connection_id || wizardState.connectionId;
    if (!connId) return undefined;
    const conn = actionRunnerConnections.find((c) => c.id === connId);
    if (!conn || !conn.gcp_instance_name || !conn.gcp_zone) return undefined;

    let cancelled = false;
    let timerId = null;

    const poll = () => {
      const selectedRepo = wizardState.repos.find((r) => getAzureRepoKey(r) === wizardState.selectedRepoKey);
      const repoUrlForStatus = (selectedRepo?.url || formData.url || '').trim();
      const patForStatus = (wizardState.pat || formData.azure_pat || '').trim();
      api.getRunnerProvisionStatus(connId, {
        pat: patForStatus || undefined,
        repoUrl: repoUrlForStatus || undefined,
      })
        .then((res) => {
          if (cancelled) return;
          const data = res.data?.data || {};
          setProvisionProgressByConnection((prev) => ({
            ...prev,
            [connId]: data,
          }));
          const isComplete = !!data.complete;
          timerId = setTimeout(poll, isComplete ? 15000 : 3000);
        })
        .catch(() => {
          if (!cancelled) timerId = setTimeout(poll, 5000);
        });
    };

    poll();
    return () => {
      cancelled = true;
      if (timerId) clearTimeout(timerId);
    };
  }, [
    formData.action_runner_connection_id,
    wizardState.connectionId,
    actionRunnerConnections,
    wizardState.repos,
    wizardState.selectedRepoKey,
    wizardState.pat,
    formData.url,
    formData.azure_pat,
  ]);

  useEffect(() => {
    if (consoleAutoScrollEnabled && consoleEndRef.current) {
      consoleEndRef.current.scrollTop = consoleEndRef.current.scrollHeight;
    }
  }, [provisionProgressByConnection, consoleAutoScrollEnabled]);

  useEffect(() => {
    // Enable auto-scroll at the beginning of a provisioning session.
    setConsoleAutoScrollEnabled(true);
  }, [formData.action_runner_connection_id, wizardState.connectionId]);

  const safeTimeout = useCallback((fn, delay) => {
    const id = setTimeout(() => {
      pendingTimeoutsRef.current.delete(id);
      fn();
    }, delay);
    pendingTimeoutsRef.current.add(id);
    return id;
  }, []);

  const copyProvisionConsole = useCallback(async (lines) => {
    try {
      const text = (lines || []).join('\n');
      await navigator.clipboard.writeText(text);
      showSuccess('Copied', 'Provisioning console output copied to clipboard.');
    } catch (error) {
      showError('Copy failed', 'Unable to copy console output to clipboard.');
    }
  }, [showSuccess, showError]);

  useEffect(() => {
    const timeouts = pendingTimeoutsRef.current;
    return () => {
      timeouts.forEach(id => clearTimeout(id));
    };
  }, []);

  const discoverAzureDevopsResources = async () => {
    const orgUrl = wizardState.orgUrl.trim();
    const pat = wizardState.pat.trim();
    if (!orgUrl || !pat) {
      showWarning('Missing details', 'Enter Azure organization URL and PAT to discover repositories.');
      return;
    }
    try {
      setWizardState((prev) => ({ ...prev, loading: true }));
      const res = await api.discoverAzureDevops({ org_url: orgUrl, pat });
      const data = res.data?.data || {};
      const repos = data.repositories || [];
      const pools = data.pools || [];
      const selectedRepoKey = resolveSelectedRepoKey(repos, wizardState.selectedRepoKey);
      const selectedPool = (wizardState.selectedPool && pools.some((p) => p.name === wizardState.selectedPool))
        ? wizardState.selectedPool
        : '';
      setWizardState((prev) => ({
        ...prev,
        loading: false,
        connected: true,
        repos,
        pools,
        selectedRepoKey,
        selectedPool,
        skipRunner: false,
      }));
      if (selectedRepoKey) {
        const selected = repos.find((r) => getAzureRepoKey(r) === selectedRepoKey);
        if (selected) {
          setFormData((prev) => ({
            ...prev,
            provider: 'azure_devops',
            name: selected.project && selected.name ? `${selected.project}/${selected.name}` : (selected.name || prev.name),
            url: selected.url || prev.url,
            azure_pat: pat,
          }));
        }
      } else {
        setFormData((prev) => ({ ...prev, provider: 'azure_devops', azure_pat: pat }));
      }
      try {
        setAzurePatIdentity({ loading: true, data: null, error: null });
        const identityResp = await api.getAzureDevopsPatIdentity({ org_url: orgUrl, pat });
        setAzurePatIdentity({
          loading: false,
          data: identityResp.data?.data || null,
          error: null,
        });
      } catch (identityErr) {
        setAzurePatIdentity({
          loading: false,
          data: null,
          error: identityErr.response?.data?.detail || identityErr.message || 'Failed to resolve PAT identity',
        });
      }
      setWizardStep(1);
      showSuccess('Azure discovery', `Found ${repos.length} repositories and ${pools.length} agent pools.`);
    } catch (error) {
      setWizardState((prev) => ({ ...prev, loading: false }));
      showError('Azure discovery failed', error.response?.data?.detail || error.message);
    }
  };

  const handleAzureDiscoveredRepoSelect = (selectedValue) => {
    setWizardState((prev) => ({ ...prev, selectedRepoKey: selectedValue }));
    setBranchesData((prev) => {
      const next = { ...prev };
      delete next.wizard;
      return next;
    });
    const selected = wizardState.repos.find((r) => getAzureRepoKey(r) === selectedValue);
    if (!selected) return;
    setFormData((prev) => ({
      ...prev,
      provider: 'azure_devops',
      name: selected.project && selected.name ? `${selected.project}/${selected.name}` : (selected.name || prev.name),
      url: selected.url || prev.url,
      azure_pat: wizardState.pat.trim() || prev.azure_pat,
    }));
  };

  const ensureAzureRunnerConnection = async (agentPoolOverride = '') => {
    const selected = wizardState.repos.find(
      (r) => getAzureRepoKey(r) === wizardState.selectedRepoKey
    );
    const parsed = parseAzureDevOpsUrl((selected?.url || formData.url || '').trim());
    const orgFromOrgUrl = deriveAzureOrganizationFromOrgUrl(wizardState.orgUrl);
    const organization = parsed.organization && parsed.organization !== 'unknown'
      ? parsed.organization
      : orgFromOrgUrl;
    if (!organization) {
      throw new Error('Unable to resolve Azure organization from repository URL or organization URL.');
    }
    const project = parsed.project && parsed.project !== 'unknown' ? parsed.project : null;
    const displayName = project ? `${organization} / ${project}` : organization;
    const payload = {
      provider: 'azure_devops',
      organization,
      project,
      display_name: displayName,
      agent_pool: agentPoolOverride || undefined,
    };
    const res = await api.createActionRunnerConnection(payload);
    const connection = res.data?.data;
    if (!connection?.id) {
      throw new Error('Failed to create or load action runner connection.');
    }
    await fetchActionRunnerConnections();
    setFormData((prev) => ({ ...prev, action_runner_connection_id: connection.id }));
    setWizardState((prev) => ({ ...prev, connectionId: connection.id }));
    return connection;
  };

  const handleAzureProvisionRunner = async () => {
    const selectedPool = wizardState.selectedPool.trim();
    if (!selectedPool) {
      showWarning('Select pool', 'Choose an Azure agent pool before provisioning.');
      return;
    }
    if (!wizardState.pat.trim()) {
      showWarning('Missing PAT', 'Connect with a PAT in Step 1 before provisioning.');
      return;
    }
    try {
      setWizardState((prev) => ({ ...prev, provisioning: true, skipRunner: false }));
      const connection = await ensureAzureRunnerConnection(selectedPool);
      const body = {
        ado_pat: wizardState.pat.trim(),
        agent_pool: selectedPool,
      };
      const res = await api.provisionRunnerVm(connection.id, body);
      const data = res.data?.data;
      if (!data?.success) {
        const msg = data?.error || res.data?.detail || 'Unknown error';
        throw new Error(msg);
      }
      setWizardState((prev) => ({ ...prev, provisioned: true, connectionId: connection.id }));
      setActionRunnerConnections((prev) => prev.map((c) => (
        c.id === connection.id
          ? { ...c, gcp_instance_name: data.instance_name, gcp_zone: data.zone, agent_pool: selectedPool }
          : c
      )));
      await fetchActionRunnerConnections();
      showSuccess('Runner VM', data.message || 'VM creation started. Watch progress below.');
    } catch (error) {
      const msg = error.response?.data?.detail || error.message;
      const isGcpNotConfigured = /GCP|configured|GCP_RUNNER/i.test(msg || '');
      showError(
        'Provision failed',
        isGcpNotConfigured
          ? 'GCP runner provisioning is not configured. Set GCP_RUNNER_PROJECT_ID (and optionally GCP_RUNNER_REGION, GCP_RUNNER_ZONE) on the backend, or use an existing self-hosted runner.'
          : msg
      );
    } finally {
      setWizardState((prev) => ({ ...prev, provisioning: false }));
    }
  };

  useEffect(() => {
    if (showAddForm) fetchActionRunnerConnections();
  }, [showAddForm, fetchActionRunnerConnections]);

  // Auto-check runner service when github-runner-install tab becomes active
  useEffect(() => {
    const activeRunnerTabs = Object.entries(repoActiveTabs).filter(([_, tab]) => tab === 'github-runner-install');
    
    activeRunnerTabs.forEach(([repoId, _]) => {
      const numericRepoId = parseInt(repoId);
      if (!checkingRunnerService.has(numericRepoId) && !runnerServiceStatus[numericRepoId]) {
        // Only auto-check if we haven't checked yet and we're not currently checking
        checkRunnerServiceRef.current?.(numericRepoId);
      }
    });
  }, [repoActiveTabs, checkingRunnerService, runnerServiceStatus]); // Trigger when active tabs change

  // Auto-check runner service when service name changes
  useEffect(() => {
    const timeouts = {};
    
    Object.entries(runnerServiceNames).forEach(([repoId, serviceName]) => {
      const numericRepoId = parseInt(repoId);
      
      // Clear any existing timeout for this repo
      if (timeouts[repoId]) {
        clearTimeout(timeouts[repoId]);
      }
      
      // Set a debounced timeout to check the service
      timeouts[repoId] = setTimeout(() => {
        if (serviceName && !checkingRunnerService.has(numericRepoId)) {
          checkRunnerServiceRef.current?.(numericRepoId);
        }
      }, 1000); // Debounce for 1 second
    });
    
    // Cleanup timeouts on unmount or dependency change
    return () => {
      Object.values(timeouts).forEach(timeout => clearTimeout(timeout));
    };
  }, [runnerServiceNames, checkingRunnerService]); // Trigger when service names change

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (!event.target.closest('.service-dropdown-container')) {
        setServiceDropdownOpen({});
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

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
        const newRepoName = formData.name;
        await api.createRepository(formData);
        showSuccess('Success', 'Repository added successfully');
        
        resetForm();
        
        // For new repositories, trigger health and config checks after a delay
        fetchRepositories().then(() => {
          safeTimeout(async () => {
            try {
              const updatedRepos = await api.getRepositories();
              const newRepo = updatedRepos.data.data.find(r => r.name === newRepoName);
              if (newRepo) {
                await checkRunnerHealth(newRepo.id);
                await checkRepositoryConfig(newRepo.id);
              }
            } catch (error) {
              console.warn('Failed to trigger initial health/config checks:', error);
            }
          }, 1000);
        });
      }
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to save repository';
      showError('Error', errorMsg);
      setErrors({ general: errorMsg });
    }
  };

  const clearRepoActionPollTimeout = () => {
    if (repoActionPollTimeoutRef.current) {
      clearTimeout(repoActionPollTimeoutRef.current);
      repoActionPollTimeoutRef.current = null;
    }
  };

  const pollRepositoryActionStatus = useCallback(async (repoId, operationType, operationId) => {
    try {
      const statusResp = operationType === 'cleanup'
        ? await api.getRepositoryCleanupStatus(repoId, operationId)
        : await api.getRepositoryActivationSyncStatus(repoId, operationId);
      const op = statusResp.data?.data || {};
      const done = op.status === 'completed' || op.status === 'failed';
      setRepoActionModal((prev) => ({
        ...prev,
        status: op.status || '',
        steps: Array.isArray(op.steps) ? op.steps : [],
        message: op.message || '',
        error: op.error || null,
        running: !done,
      }));

      if (done) {
        if (op.status === 'completed') {
          if (operationType === 'cleanup') {
            showSuccess('Repository removed', 'Cleanup completed and repository was removed from the dashboard.');
            if (expandedRepo === repoId) setExpandedRepo(null);
          } else {
            const target = !!op.result?.is_active;
            showSuccess('Repository updated', `Repository ${target ? 'activated' : 'deactivated'} and Azure check synchronized.`);
          }
        } else {
          showError('Operation failed', op.error || op.message || 'Repository operation failed.');
        }
        await fetchRepositories();
        clearRepoActionPollTimeout();
        return;
      }

      clearRepoActionPollTimeout();
      repoActionPollTimeoutRef.current = setTimeout(
        () => pollRepositoryActionStatus(repoId, operationType, operationId),
        1500
      );
    } catch (error) {
      clearRepoActionPollTimeout();
      setRepoActionModal((prev) => ({
        ...prev,
        running: false,
        status: 'failed',
        error: error.response?.data?.detail || error.message || 'Failed to poll operation status.',
      }));
      showError('Operation failed', error.response?.data?.detail || error.message || 'Failed to poll operation status.');
    }
  }, [expandedRepo, fetchRepositories, showError, showSuccess]);

  const startRepoActionModal = async (repo, operationType, startResponse) => {
    const payload = startResponse?.data?.data || {};
    const operationId = payload.operation_id;
    if (!operationId) {
      throw new Error('Operation id missing from backend response');
    }
    setRepoActionModal({
      show: true,
      running: true,
      operationType,
      operationId,
      repoId: repo.id,
      title: operationType === 'cleanup' ? 'Repository Cleanup In Progress' : 'Repository Activation Sync In Progress',
      subtitle: operationType === 'cleanup'
        ? `Cleaning up ${repo.name}. This can take a moment.`
        : `Synchronizing Azure check state for ${repo.name}.`,
      status: payload.status || 'running',
      steps: Array.isArray(payload.steps) ? payload.steps : [],
      message: '',
      error: null,
    });
    clearRepoActionPollTimeout();
    repoActionPollTimeoutRef.current = setTimeout(
      () => pollRepositoryActionStatus(repo.id, operationType, operationId),
      300
    );
  };

  const handleDelete = async (repo) => {
    try {
      setRepoCleanupConfirmModal({
        show: true,
        loading: true,
        repo,
        preview: null,
        error: null,
      });
      const previewResp = await api.getRepositoryCleanupPreview(repo.id);
      setRepoCleanupConfirmModal({
        show: true,
        loading: false,
        repo,
        preview: previewResp.data?.data || null,
        error: null,
      });
    } catch (error) {
      setRepoCleanupConfirmModal({
        show: false,
        loading: false,
        repo: null,
        preview: null,
        error: null,
      });
      showError('Delete failed', error.response?.data?.detail || 'Failed to load cleanup preview.');
    }
  };

  const confirmRepositoryCleanupDelete = async () => {
    const repo = repoCleanupConfirmModal.repo;
    if (!repo) return;
    try {
      const startResp = await api.startRepositoryCleanup(repo.id);
      setRepoCleanupConfirmModal({
        show: false,
        loading: false,
        repo: null,
        preview: null,
        error: null,
      });
      await startRepoActionModal(repo, 'cleanup', startResp);
    } catch (error) {
      showError('Delete failed', error.response?.data?.detail || 'Failed to start repository cleanup.');
    }
  };

  const handleDeleteRunner = async (conn) => {
    const label = conn.display_name || `${conn.organization}${conn.project ? '/' + conn.project : ''}`;
    const hasVm = !!(conn.gcp_instance_name && conn.gcp_zone);
    const parts = ['delete this action runner connection'];
    if (hasVm) parts.push('destroy the VM');
    if (conn.provider === 'azure_devops' && conn.agent_pool) parts.push('deregister the Azure agent');
    const msg = `This will ${parts.join(', ')}.\n\nRunner: ${label}\n${hasVm ? `VM: ${conn.gcp_instance_name} (${conn.gcp_zone})` : 'No VM provisioned'}\n\nLinked repositories will be unlinked but not deleted.\n\nContinue?`;
    if (!window.confirm(msg)) return;
    setDeletingRunner(conn.id);
    try {
      const resp = await api.deleteActionRunnerConnection(conn.id);
      const cleanup = resp?.data?.data || {};
      const agentCleanup = cleanup.azure_agent;
      const agentCleanupFailed = agentCleanup && agentCleanup.success === false;
      if (agentCleanupFailed) {
        showWarning(
          'Runner deleted with cleanup warning',
          `Connection "${label}" was deleted, but Azure agent cleanup reported an issue: ${agentCleanup.error || 'unknown error'}.`
        );
      } else {
        showSuccess('Runner deleted', `Action runner "${label}" and its resources have been cleaned up.`);
      }
      await fetchActionRunnerConnections();
      await fetchRepositories();
    } catch (error) {
      const detail = error.response?.data?.detail || error.message;
      showError('Delete failed', detail);
    } finally {
      setDeletingRunner(null);
    }
  };

  const handleCreateRunner = async () => {
    const org = newRunnerForm.organization.trim();
    if (!org) { showWarning('Missing field', 'Organization is required.'); return; }
    setCreatingRunner(true);
    try {
      const payload = {
        provider: newRunnerForm.provider,
        organization: org,
        project: newRunnerForm.project.trim() || undefined,
        display_name: newRunnerForm.display_name.trim() || undefined,
        agent_pool: newRunnerForm.agent_pool.trim() || undefined,
      };
      await api.createActionRunnerConnection(payload);
      showSuccess('Runner created', 'Action runner connection created successfully.');
      await fetchActionRunnerConnections();
      setShowCreateRunner(false);
      setNewRunnerForm({ provider: 'azure_devops', organization: '', project: '', display_name: '', agent_pool: '' });
    } catch (error) {
      const detail = error.response?.data?.detail || error.message;
      showError('Create failed', detail);
    } finally {
      setCreatingRunner(false);
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
      azure_pat: '',
      action_runner_connection_id: null
    });
    setOriginalFormData(null);
    setEditingRepo(null);
    setExpandedRepo(null);
    setShowAddForm(false);
    setErrors({});
    setRepoActiveTabs({});
    setWizardStep(0);
    setWizardState({
      orgUrl: '',
      pat: '',
      loading: false,
      connected: false,
      repos: [],
      pools: [],
      selectedRepoKey: '',
      selectedPool: '',
      connectionId: null,
      provisioning: false,
      provisioned: false,
      skipRunner: false,
      setupPipeline: false,
      pipelineBranch: '',
      pipelineIsBlocking: false,
      pipelineSetupDone: false,
      pipelineSetupResult: null,
    });
    setAzurePatIdentity({ loading: false, data: null, error: null });
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
      // Check both repository health and runner service status
      const promises = [
        api.checkRepositoryHealth(repoId)
      ];
      
      // Also check runner service if this is a GitHub repository
      const repo = repositories.find(r => r.id === repoId);
      if (repo && repo.provider === 'github') {
        promises.push(checkRunnerService(repoId));
      }
      
      await Promise.all(promises);
      showSuccess('Success', 'Health check completed');
      fetchRepositories(); // Refresh to get updated health status
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to check health';
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

  // Comprehensive refresh function that checks both health and config
  const comprehensiveRefresh = async (repoId) => {
    const isCheckingHealth = checkingHealth.has(repoId);
    const isCheckingConfig = checkingConfig.has(repoId);
    
    if (isCheckingHealth || isCheckingConfig) return;

    try {
      // Run both checks concurrently
      const promises = [];
      
      // Always check health
      promises.push(checkRunnerHealth(repoId));
      
      // Check config if repository supports it
      const repo = repositories.find(r => r.id === repoId);
      if (repo && shouldShowConfigStatus(repo)) {
        promises.push(checkRepositoryConfig(repoId));
      }

      // Check runner service if it's a GitHub repo
      if (repo && repo.provider === 'github') {
        promises.push(checkRunnerService(repoId));
      }

      await Promise.all(promises);
      
      showSuccess('Refresh Complete', 'Repository health, configuration, and services have been updated');
    } catch (error) {
      console.error('Error during comprehensive refresh:', error);
      showError('Refresh Failed', 'Some checks failed during refresh. Please try individual checks.');
    }
  };





  const shouldShowConfigStatus = (repo) => {
    // Only show config status if we have tokens configured (needed for checking)
    return getTokenStatus(repo) === 'configured';
  };

  const formatLastChecked = (timestamp) => {
    if (!timestamp) return 'Never';
    try {
      return formatTimestamp(timestamp);
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
      const repo = repositories.find((item) => item.id === repoId);
      if (!repo) {
        showError('Error', 'Repository not found');
        return;
      }
      const targetActive = !currentIsActive;
      if (repo.provider === 'azure_devops') {
        const startResp = await api.startRepositoryActivationSync(repoId, targetActive);
        await startRepoActionModal(repo, 'activation_sync', startResp);
      } else {
        await api.updateRepository(repoId, { is_active: targetActive });
        showSuccess('Success', `Repository ${targetActive ? 'activated' : 'deactivated'} successfully`);
        fetchRepositories();
      }
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Failed to update repository status';
      showError('Error', errorMsg);
    }
  };

  const isRepoActionBusy = (repoId) =>
    repoActionModal.show && repoActionModal.running && repoActionModal.repoId === repoId;

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

  // General/Authentication tab edit functions
  const startEditingGeneral = (repoId) => {
    const repo = repositories.find(r => r.id === repoId);
    if (repo) {
      setEditedGeneralData(prev => ({
        ...prev,
        [repoId]: {
          name: repo.name,
          url: repo.url,
          provider: repo.provider,
          github_token: '',
          azure_pat: ''
        }
      }));
      setIsEditingGeneral(prev => ({ ...prev, [repoId]: true }));
    }
  };

  const cancelEditingGeneral = (repoId) => {
    setIsEditingGeneral(prev => ({ ...prev, [repoId]: false }));
    setEditedGeneralData(prev => ({ ...prev, [repoId]: undefined }));
  };

  const saveGeneralChanges = async (repoId) => {
    if (!editedGeneralData[repoId]) return;
    setSavingGeneral(prev => new Set([...prev, repoId]));
    try {
      await api.updateRepository(repoId, editedGeneralData[repoId]);

      // Refresh the repositories list
      await fetchRepositories();
      
      // Exit edit mode
      setIsEditingGeneral(prev => ({ ...prev, [repoId]: false }));
      setEditedGeneralData(prev => ({ ...prev, [repoId]: undefined }));
      
      showSuccess('Repository updated successfully');
    } catch (error) {
      console.error('Failed to update repository:', error);
      showError('Failed to update repository', error.message || 'Failed to update repository');
    } finally {
      setSavingGeneral(prev => { const next = new Set(prev); next.delete(repoId); return next; });
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
        safeTimeout(() => checkPrAgentConfigPRStatus(repoId), 1000);
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

  // GitHub Action config functions
  const loadGithubActionConfig = async (repoId, forceRefresh = false) => {
    if (loadingGithubActionConfig.has(repoId) && !forceRefresh) return;
    
    try {
      setLoadingGithubActionConfig(prev => new Set([...prev, repoId]));
      const response = await api.get(`/api/repositories/${repoId}/github-action-config?force_refresh=${forceRefresh}`);
      
      const data = response.data.data;
      setGithubActionConfigData(prev => ({
        ...prev,
        [repoId]: data
      }));

      // If there's a pending PR, check its status automatically
      if (data.has_pending_pr && data.pr_number) {
        // Check PR status after a short delay to avoid overwhelming the API
        safeTimeout(() => checkGithubActionConfigPRStatus(repoId), 1000);
      }
    } catch (error) {
      console.error('Error loading GitHub Action config:', error);
      showError('Error', 'Failed to load GitHub Action configuration');
    } finally {
      setLoadingGithubActionConfig(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  const openGithubActionConfigEditor = (repoId) => {
    setShowGithubActionConfigEditor(repoId);
  };

  const closeGithubActionConfigEditor = () => {
    setShowGithubActionConfigEditor(null);
  };

  const handleGithubActionConfigSave = async (result) => {
    if (result.pr_created) {
      // Update the GitHub Action config data with PR info
      setGithubActionConfigData(prev => ({
        ...prev,
        [showGithubActionConfigEditor]: {
          ...prev[showGithubActionConfigEditor],
          has_pending_pr: true,
          pr_number: result.pr_number,
          pr_url: result.pr_url,
          branch_name: result.branch_name
        }
      }));
    }
    closeGithubActionConfigEditor();
  };

  const checkGithubActionConfigPRStatus = async (repoId) => {
    if (checkingGithubActionPrStatus.has(repoId)) return;
    
    const configData = githubActionConfigData[repoId];
    if (!configData?.pr_number) {
      console.warn('No PR number found for GitHub Action config');
      return;
    }
    
    try {
      setCheckingGithubActionPrStatus(prev => new Set([...prev, repoId]));
      
      const response = await api.post(`/api/repositories/${repoId}/github-action-config/check-pr-status`, {
        pr_number: configData.pr_number
      });
      
      const statusData = response.data.data;
      
      if (statusData.status === 'merged') {
        showSuccess('PR Merged!', 'GitHub Action config PR was merged. Configuration is now active.');
        // Update local state
        setGithubActionConfigData(prev => ({
          ...prev,
          [repoId]: {
            ...prev[repoId],
            has_pending_pr: false,
            pr_status: 'merged'
          }
        }));
        // Refresh the config data
        await loadGithubActionConfig(repoId, true);
      } else if (statusData.status === 'closed') {
        showSuccess('PR Closed', 'GitHub Action config PR was closed without merging.');
        // Update local state
        setGithubActionConfigData(prev => ({
          ...prev,
          [repoId]: {
            ...prev[repoId],
            has_pending_pr: false,
            pr_status: 'closed'
          }
        }));
      }
      // If still pending, no action needed
    } catch (error) {
      console.error('Error checking GitHub Action PR status:', error);
      showError('Error', 'Failed to check GitHub Action PR status');
    } finally {
      setCheckingGithubActionPrStatus(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  // Azure Pipeline config functions
  const loadAzurePipelineConfig = async (repoId, forceRefresh = false) => {
    if (loadingAzurePipelineConfig.has(repoId) && !forceRefresh) return;

    try {
      setLoadingAzurePipelineConfig(prev => new Set([...prev, repoId]));
      const response = await api.get(`/api/repositories/${repoId}/azure-pipeline-config?force_refresh=${forceRefresh}`);
      const configData = response.data;

      setAzurePipelineConfigData(prev => ({
        ...prev,
        [repoId]: {
          ...configData,
          error: null
        }
      }));

      // Check for pending PR status if config exists
      if (configData.pr_number) {
        checkAzurePipelineConfigPRStatus(repoId);
      }

    } catch (error) {
      console.error('Error loading Azure Pipeline config:', error);
      showError('Error', 'Failed to load Azure Pipeline configuration');
    } finally {
      setLoadingAzurePipelineConfig(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  const openAzurePipelineConfigEditor = (repoId) => {
    setShowAzurePipelineConfigEditor(repoId);
  };

  const closeAzurePipelineConfigEditor = () => {
    setShowAzurePipelineConfigEditor(null);
  };

  const handleAzurePipelineConfigSave = async (result) => {
    try {
      // Update the Azure Pipeline config data with PR info
      setAzurePipelineConfigData(prev => ({
        ...prev,
        [showAzurePipelineConfigEditor]: {
          ...prev[showAzurePipelineConfigEditor],
          pr_url: result.pr_url,
          pr_number: result.pr_number,
          pr_status: result.status || 'pending',
          has_pending_pr: true
        }
      }));
      closeAzurePipelineConfigEditor();
    } catch (error) {
      console.error('Error after Azure Pipeline config save:', error);
    }
  };

  const checkAzurePipelineConfigPRStatus = async (repoId) => {
    try {
      setCheckingAzurePipelinePrStatus(prev => new Set([...prev, repoId]));
      const configData = azurePipelineConfigData[repoId];
      if (!configData?.pr_number) {
        console.warn('No PR number found for Azure Pipeline config');
        return;
      }

      // Call the backend to check PR status - Azure DevOps uses REST API
      const response = await api.post(`/api/repositories/${repoId}/azure-pipeline-config/check-pr-status`, {
        pr_number: configData.pr_number
      });
      const result = response.data;

      if (result.status === 'merged') {
        // PR was merged - refresh config and show success
        showSuccess('PR Merged!', 'Azure Pipeline config PR was merged. Configuration is now active.');
        
        setAzurePipelineConfigData(prev => ({
          ...prev,
          [repoId]: {
            ...prev[repoId],
            has_pending_pr: false,
            pr_status: 'merged',
            exists: true
          }
        }));

        // Refresh the config data
        await loadAzurePipelineConfig(repoId, true);
      } else if (result.status === 'closed') {
        showSuccess('PR Closed', 'Azure Pipeline config PR was closed without merging.');
        
        setAzurePipelineConfigData(prev => ({
          ...prev,
          [repoId]: {
            ...prev[repoId],
            has_pending_pr: false,
            pr_status: 'closed'
          }
        }));
      }
      // If still pending, no action needed

    } catch (error) {
      console.error('Error checking Azure Pipeline config PR status:', error);
      showError('Error', 'Failed to check Azure Pipeline PR status');
    } finally {
      setCheckingAzurePipelinePrStatus(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  // ── Pipeline sync, push, branches, policy handlers ──

  const loadSyncStatus = useCallback(async (repoId) => {
    try {
      setLoadingSyncStatus(prev => new Set([...prev, repoId]));
      const resp = await api.getPipelineSyncStatus(repoId);
      const data = resp.data?.data || resp.data || {};
      setSyncStatusData(prev => ({ ...prev, [repoId]: data }));
      return data;
    } catch (err) {
      console.error('Error loading sync status:', err);
      return null;
    } finally {
      setLoadingSyncStatus(prev => { const s = new Set(prev); s.delete(repoId); return s; });
    }
  }, []);

  const handlePushYaml = async (repoId, content = null) => {
    try {
      setPushingYaml(prev => new Set([...prev, repoId]));
      const resp = await api.pushPipelineYaml(repoId, content);
      const result = resp.data?.data || resp.data || {};
      if (result.success) {
        showSuccess('Pipeline Updated', result.pipeline_created
          ? 'YAML pushed and pipeline definition created.'
          : 'Pipeline YAML pushed to default branch.');
        await loadSyncStatus(repoId);
      } else {
        showError('Push Failed', result.error || 'Unknown error');
      }
    } catch (err) {
      showError('Push Failed', err.response?.data?.detail || err.message);
    } finally {
      setPushingYaml(prev => { const s = new Set(prev); s.delete(repoId); return s; });
    }
  };

  const handleSyncPipelineVariables = async (repoId, pipelineDefinitionId = null) => {
    try {
      setSyncingPipelineVariables(prev => new Set([...prev, repoId]));
      const body = pipelineDefinitionId ? { pipeline_definition_id: pipelineDefinitionId } : {};
      const resp = await api.syncPipelineVariables(repoId, body);
      const result = resp.data?.data || resp.data || {};
      if (result.success) {
        const targeted = result.pipelines_targeted || 0;
        showSuccess('Variables synchronized', `Updated pipeline variables/secrets for ${targeted} pipeline${targeted === 1 ? '' : 's'}.`);
        await loadSyncStatus(repoId);
        return result;
      } else {
        throw new Error(result.error || 'Failed to synchronize pipeline variables/secrets');
      }
    } catch (err) {
      const message = err.response?.data?.detail || err.message;
      showError('Sync failed', message);
      throw err;
    } finally {
      setSyncingPipelineVariables(prev => { const s = new Set(prev); s.delete(repoId); return s; });
    }
  };

  const getMatchingEnabledPolicyCount = (policies, pipelineDefinitions) => {
    const enabledPolicies = (policies || []).filter((p) => p.is_enabled !== false);
    if (!enabledPolicies.length) return 0;
    const definitionIds = new Set((pipelineDefinitions || []).map((d) => String(d.id)));
    if (!definitionIds.size) return 0;
    return enabledPolicies.filter((p) => definitionIds.has(String(p.pipeline_id))).length;
  };

  const verifyAzurePipelineSetup = async (repoId, options = {}) => {
    const { silent = false } = options;
    try {
      setVerifyingAzureSetup(prev => new Set([...prev, repoId]));
      const [ss, pol] = await Promise.all([
        loadSyncStatus(repoId),
        loadPolicies(repoId),
      ]);

      const enabledPolicies = (pol?.policies || []).filter((p) => p.is_enabled !== false);
      const matchingPolicyCount = getMatchingEnabledPolicyCount(pol?.policies, ss?.pipeline_definitions);
      const checks = {
        yaml_up_to_date: ss?.sync_status === 'up_to_date',
        pipeline_definition_exists: !!ss?.pipeline_exists,
        variables_synced: !(ss?.variables_status?.missing_any),
        check_policy_exists: matchingPolicyCount > 0,
      };

      const issues = [];
      if (!checks.pipeline_definition_exists) issues.push('Pipeline definition is missing.');
      if (!checks.yaml_up_to_date) issues.push('Pipeline YAML is missing or outdated.');
      if (!checks.variables_synced) issues.push('Required pipeline variables/secrets are missing.');
      if (!checks.check_policy_exists) {
        if (enabledPolicies.length > 0) {
          issues.push('Enabled build validation policies exist, but none are linked to the current PR-Agent pipeline definition.');
        } else {
          issues.push('No enabled build validation check policy is configured.');
        }
      }

      const result = {
        checked_at: new Date().toISOString(),
        checks,
        issues,
        success: issues.length === 0,
      };
      setAzureSetupVerification(prev => ({ ...prev, [repoId]: result }));

      if (!silent) {
        if (result.success) {
          showSuccess('Setup verified', 'Azure pipeline setup looks healthy and ready.');
        } else {
          showWarning('Setup needs attention', issues.join(' '));
        }
      }
      return result;
    } catch (error) {
      if (!silent) {
        showError('Verification failed', error.response?.data?.detail || error.message || 'Failed to verify setup.');
      }
      const failed = {
        checked_at: new Date().toISOString(),
        checks: {
          yaml_up_to_date: false,
          pipeline_definition_exists: false,
          variables_synced: false,
          check_policy_exists: false,
        },
        issues: ['Unable to run verification due to an API error.'],
        success: false,
      };
      setAzureSetupVerification(prev => ({ ...prev, [repoId]: failed }));
      return failed;
    } finally {
      setVerifyingAzureSetup(prev => { const s = new Set(prev); s.delete(repoId); return s; });
    }
  };

  const autoFixAzurePipelineSetup = async (repo) => {
    const repoId = repo.id;
    try {
      setAutoFixingAzureSetup(prev => new Set([...prev, repoId]));
      let ss = await loadSyncStatus(repoId);
      if (!ss) throw new Error('Unable to load pipeline sync status');

      // 1) Fix YAML drift first (this can also create the pipeline definition)
      if (ss.sync_status === 'missing' || ss.sync_status === 'outdated') {
        const pushResp = await api.pushPipelineYaml(repoId);
        const pushData = pushResp.data?.data || pushResp.data || {};
        if (!pushData.success) {
          throw new Error(pushData.error || 'Failed to push pipeline YAML');
        }
        ss = await loadSyncStatus(repoId);
      }

      // 2) Sync required vars/secrets
      if (ss?.variables_status?.missing_any) {
        await handleSyncPipelineVariables(repoId);
        ss = await loadSyncStatus(repoId);
      }

      // 3) Ensure at least one enabled check policy exists (optional by default)
      let pol = await loadPolicies(repoId);
      let matchingPolicyCount = getMatchingEnabledPolicyCount(pol?.policies, ss?.pipeline_definitions);
      if (matchingPolicyCount === 0) {
        const defs = ss?.pipeline_definitions || [];
        const pipelineDefinitionId = defs[0]?.id;
        const branchData = branchesData[repoId] || await loadBranches(repoId);
        const defaultBranch = branchData?.default_branch
          || (branchData?.branches || []).find((b) => b.is_default)?.name
          || (branchData?.branches || [])[0]?.name;

        if (pipelineDefinitionId && defaultBranch) {
          const policyResp = await api.ensurePipelinePolicy(repoId, {
            branch: defaultBranch,
            pipeline_definition_id: pipelineDefinitionId,
            is_blocking: false,
          });
          const policyData = policyResp.data?.data || policyResp.data || {};
          if (!policyData.success) {
            throw new Error(policyData.error || 'Failed to create default optional build validation policy');
          }
          pol = await loadPolicies(repoId);
          matchingPolicyCount = getMatchingEnabledPolicyCount(pol?.policies, ss?.pipeline_definitions);
        } else {
          showWarning(
            'Auto-fix partially completed',
            'YAML and variables were fixed, but no default branch/pipeline definition was available to auto-create a check policy.'
          );
        }
      }

      const verification = await verifyAzurePipelineSetup(repoId, { silent: true });
      if (verification?.success) {
        showSuccess('Auto-fix completed', 'Azure setup is now fully configured and verified.');
      } else {
        showWarning('Auto-fix completed with remaining items', (verification?.issues || []).join(' '));
      }
    } catch (error) {
      showError('Auto-fix failed', error.response?.data?.detail || error.message || 'Failed to auto-fix Azure setup.');
    } finally {
      setAutoFixingAzureSetup(prev => { const s = new Set(prev); s.delete(repoId); return s; });
    }
  };

  const loadBranches = useCallback(async (repoId) => {
    try {
      const resp = await api.getRepoBranches(repoId);
      const data = resp.data?.data || resp.data || {};
      setBranchesData(prev => ({ ...prev, [repoId]: data }));
      return data;
    } catch (err) {
      console.error('Error loading branches:', err);
      return null;
    }
  }, []);

  const loadPolicies = useCallback(async (repoId) => {
    try {
      setLoadingPolicies(prev => new Set([...prev, repoId]));
      const resp = await api.getPipelinePolicies(repoId);
      const data = resp.data?.data || resp.data || {};
      setPoliciesData(prev => ({ ...prev, [repoId]: data }));
      return data;
    } catch (err) {
      console.error('Error loading policies:', err);
      return null;
    } finally {
      setLoadingPolicies(prev => { const s = new Set(prev); s.delete(repoId); return s; });
    }
  }, []);

  const handleAddPolicy = async (repoId) => {
    const form = newPolicyForm[repoId] || {};
    if (!form.branch || !form.pipeline_definition_id) {
      showError('Validation', 'Branch and pipeline are required');
      return;
    }
    try {
      setSavingPolicy(prev => new Set([...prev, repoId]));
      const resp = await api.ensurePipelinePolicy(repoId, {
        branch: form.branch,
        pipeline_definition_id: form.pipeline_definition_id,
        is_blocking: form.is_blocking || false,
      });
      const result = resp.data?.data || resp.data || {};
      if (result.success) {
        showSuccess('Policy Added', result.created ? 'Build validation policy created.' : 'Policy updated.');
        setShowAddPolicy(prev => ({ ...prev, [repoId]: false }));
        setNewPolicyForm(prev => ({ ...prev, [repoId]: {} }));
        await loadPolicies(repoId);
      } else {
        showError('Policy Error', result.error || 'Failed to create policy');
      }
    } catch (err) {
      showError('Policy Error', err.response?.data?.detail || err.message);
    } finally {
      setSavingPolicy(prev => { const s = new Set(prev); s.delete(repoId); return s; });
    }
  };

  const handleDeletePolicy = async (repoId, policyId) => {
    try {
      setDeletingPolicy(prev => new Set([...prev, policyId]));
      const resp = await api.deletePipelinePolicy(repoId, policyId);
      const result = resp.data?.data || resp.data || {};
      if (result.success) {
        showSuccess('Policy Removed', 'Build validation policy deleted.');
        await loadPolicies(repoId);
      } else {
        showError('Delete Failed', result.error || 'Failed to delete policy');
      }
    } catch (err) {
      showError('Delete Failed', err.response?.data?.detail || err.message);
    } finally {
      setDeletingPolicy(prev => { const s = new Set(prev); s.delete(policyId); return s; });
    }
  };

  // Load sync status for Azure DevOps repos when repo list changes
  useEffect(() => {
    repositories.filter(r => r.provider === 'azure_devops' && r.azure_pat).forEach(r => {
      if (!syncStatusData[r.id] && !loadingSyncStatus.has(r.id)) {
        loadSyncStatus(r.id);
      }
    });
  }, [repositories, syncStatusData, loadingSyncStatus, loadSyncStatus]);

  // Load branches when wizard enters Pipeline step (step 3)
  useEffect(() => {
    if (wizardStep !== 3 || branchesData.wizard) return;

    const selected = wizardState.repos.find((r) => getAzureRepoKey(r) === wizardState.selectedRepoKey);
    const repoUrl = (selected?.url || formData.url || '').trim();
    const pat = (wizardState.pat || formData.azure_pat || '').trim();
    if (!repoUrl || !pat) return;

    (async () => {
      try {
        let data = null;
        if (formData.id) {
          data = await loadBranches(formData.id);
        } else {
          const resp = await api.listAzureDevopsBranches({ repo_url: repoUrl, pat });
          data = resp.data?.data || resp.data || null;
        }
        if (data) {
          setBranchesData(prev => ({ ...prev, wizard: data }));
          if (data.default_branch && !wizardState.pipelineBranch) {
            setWizardState(prev => ({ ...prev, pipelineBranch: data.default_branch }));
          }
        }
      } catch (err) {
        showError('Branch loading failed', err.response?.data?.detail || err.message || 'Failed to load branches');
      }
    })();
  }, [
    wizardStep,
    branchesData.wizard,
    formData.id,
    formData.url,
    formData.azure_pat,
    wizardState.repos,
    wizardState.selectedRepoKey,
    wizardState.pat,
    wizardState.pipelineBranch,
    loadBranches,
    showError
  ]);

  useEffect(() => {
    if (wizardStep !== 3 || !formData.id || !wizardState.pat.trim() || !wizardState.orgUrl.trim()) return;
    let cancelled = false;
    (async () => {
      try {
        setAzurePatIdentity((prev) => ({ ...prev, loading: true }));
        const identityResp = await api.getAzureDevopsPatIdentity({
          org_url: wizardState.orgUrl.trim(),
          pat: wizardState.pat.trim(),
          repo_id: formData.id,
        });
        if (!cancelled) {
          setAzurePatIdentity({
            loading: false,
            data: identityResp.data?.data || null,
            error: null,
          });
        }
      } catch (identityErr) {
        if (!cancelled) {
          setAzurePatIdentity({
            loading: false,
            data: null,
            error: identityErr.response?.data?.detail || identityErr.message || 'Failed to resolve PAT identity',
          });
        }
      }
    })();
    return () => { cancelled = true; };
  }, [wizardStep, formData.id, wizardState.orgUrl, wizardState.pat]);

  // Get overall repository status for the main badge
  const getRepositoryStatus = (repo) => {
    // If repository is not active, show as disabled
    if (!repo.is_active) {
      return 'disabled';
    }

    // Check for errors in runner status or token issues
    if (repo.runner_status === 'error' || repo.runner_status === 'misconfigured' || repo.runner_status === 'warning') {
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

  // Helper function to parse Azure DevOps URLs correctly
  const parseAzureDevOpsUrl = (url) => {
    try {
      const urlObj = new URL(url);
      
      if (urlObj.hostname.includes('dev.azure.com')) {
        // Format: https://dev.azure.com/organization/project/_git/repo
        const pathParts = urlObj.pathname.split('/').filter(p => p);
        if (pathParts.length >= 3) {
          return {
            organization: pathParts[0],
            project: pathParts[1],
            repository: pathParts[pathParts.length - 1],
            baseUrl: `https://dev.azure.com/${pathParts[0]}`
          };
        }
      } else if (urlObj.hostname.includes('visualstudio.com')) {
        // Format: https://organization.visualstudio.com/project/_git/repo
        const pathParts = urlObj.pathname.split('/').filter(p => p);
        const organization = urlObj.hostname.split('.')[0];
        if (pathParts.length >= 2) {
          return {
            organization: organization,
            project: pathParts[0],
            repository: pathParts[pathParts.length - 1],
            baseUrl: `https://${organization}.visualstudio.com`
          };
        }
      }
      
      // Fallback to original parsing
      const pathParts = url.split('/');
      return {
        organization: pathParts[3] || 'unknown',
        project: pathParts[4] || 'unknown',
        repository: pathParts[pathParts.length - 1] || 'unknown',
        baseUrl: `${pathParts[0]}//${pathParts[2]}`
      };
    } catch (e) {
      return {
        organization: 'unknown',
        project: 'unknown', 
        repository: 'unknown',
        baseUrl: 'unknown'
      };
    }
  };

  // Runner service functions
  const getDefaultServiceName = (repo) => {
    if (!repo.name) return '';
    const parts = repo.name.split('/');
    if (parts.length === 2) {
      return `actions.runner.${parts[0]}-${parts[1]}.PRMonitor`;
    }
    return `actions.runner.${repo.name}.PRMonitor`;
  };

  const checkRunnerService = async (repoId) => {
    if (checkingRunnerService.has(repoId)) return;
    
    try {
      setCheckingRunnerService(prev => new Set([...prev, repoId]));
      
      const serviceName = runnerServiceNames[repoId] || getDefaultServiceName(repositories.find(r => r.id === repoId));
      
      const response = await api.checkRunnerService(repoId, serviceName);
      
      console.log('Runner service check response:', response.data); // Debug logging
      console.log('Service data:', response.data.data); // Debug the actual service data
      
      // Extract the actual service data from the API response wrapper
      const serviceData = response.data.data;
      
      setRunnerServiceStatus(prev => ({
        ...prev,
        [repoId]: {
          ...serviceData,
          last_checked: new Date().toISOString()
        }
      }));
      
      // Update the repository data to reflect the new runner status
      const mapServiceStatusToRunnerStatus = (serviceStatus) => {
        switch (serviceStatus) {
          case 'running':
            return 'running';
          case 'starting':
          case 'stopping':
          case 'paused':
            return 'warning';
          case 'stopped':
          case 'not_found':
          case 'error':
          default:
            return 'error';
        }
      };
      
      setRepositories(prevRepos => 
        prevRepos.map(repo => 
          repo.id === repoId 
            ? { 
                ...repo, 
                runner_status: mapServiceStatusToRunnerStatus(serviceData.status),
                runner_error: serviceData.error || (serviceData.status !== 'running' ? `Service is ${serviceData.status}` : null),
                runner_service_last_checked: new Date().toISOString()
              }
            : repo
        )
      );
      
      const status = serviceData.status || 'unknown';
      const statusDisplay = serviceData.status_display || status || 'Unknown';
      
      if (status === 'running') {
        showSuccess('Service Running', `GitHub Actions runner service is running: ${serviceName}`);
      } else if (status === 'stopped') {
        showError('Service Stopped', `GitHub Actions runner service is stopped: ${serviceName}`);
      } else if (status === 'not_found') {
        const availableServices = serviceData.available_services || [];
        let message = `Service not found: ${serviceName}`;
        if (availableServices.length > 0) {
          message += `\n\nAvailable GitHub runner services:\n${availableServices.map(s => `• ${s}`).join('\n')}`;
        } else {
          message += '\n\nNo GitHub Actions runner services detected on this system.';
        }
        showError('Service Not Found', message);
      } else if (status === 'error') {
        showError('Service Error', `Error checking service: ${serviceData.error || 'Unknown error'}`);
      } else if (status === 'starting' || status === 'stopping') {
        showWarning('Service Transitioning', `Service is ${status}: ${serviceName}`);
      } else if (status === 'paused') {
        showWarning('Service Paused', `Service is paused: ${serviceName}`);
      } else {
        const availableServices = serviceData.available_services || [];
        let message = `Service status: ${statusDisplay}`;
        if (status !== statusDisplay) {
          message += ` (${status})`;
        }
        if (availableServices.length > 0) {
          message += `\n\nAvailable services:\n${availableServices.map(s => `• ${s}`).join('\n')}`;
        }
        showError('Service Status Unknown', message);
      }
    } catch (error) {
      console.error('Error checking runner service:', error);
      showError('Error', 'Failed to check runner service status');
      setRunnerServiceStatus(prev => ({
        ...prev,
        [repoId]: {
          status: 'error',
          status_display: 'Error checking service',
          error: error.response?.data?.detail || error.message,
          last_checked: new Date().toISOString()
        }
      }));
    } finally {
      setCheckingRunnerService(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };
  checkRunnerServiceRef.current = checkRunnerService;

  const saveRunnerServiceName = async (repoId) => {
    if (savingRunnerServiceName.has(repoId)) return;
    
    try {
      setSavingRunnerServiceName(prev => new Set([...prev, repoId]));
      
      const serviceName = runnerServiceNames[repoId] || getDefaultServiceName(repositories.find(r => r.id === repoId));
      
      await api.saveRunnerServiceName(repoId, serviceName);
      
      showSuccess('Success', 'Runner service name saved successfully');
    } catch (error) {
      console.error('Error saving runner service name:', error);
      showError('Error', 'Failed to save runner service name');
    } finally {
      setSavingRunnerServiceName(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  const fetchAvailableServices = async () => {
    if (loadingServices) return;
    
    try {
      setLoadingServices(true);
      const response = await api.listRunnerServices();
      console.log('API response:', response.data); // Debug logging
      setAvailableServices(response.data.data?.github_services || []);
    } catch (error) {
      console.error('Error fetching available services:', error);
      showError('Error', 'Failed to fetch available services');
    } finally {
      setLoadingServices(false);
    }
  };

  const toggleServiceDropdown = (repoId) => {
    console.log('Toggling dropdown for repo:', repoId, 'Current state:', serviceDropdownOpen[repoId]);
    setServiceDropdownOpen(prev => ({
      ...prev,
      [repoId]: !prev[repoId]
    }));
    
    // Fetch services when opening dropdown for the first time
    if (!serviceDropdownOpen[repoId] && availableServices.length === 0) {
      console.log('Fetching available services...');
      fetchAvailableServices();
    }
  };

  // Azure agent service functions
  const getDefaultAzureAgentServiceName = (repo) => {
    try {
      const azureInfo = parseAzureDevOpsUrl(repo.url);
      return `vstsagent.${azureInfo.organization}.${azureInfo.repository}`;
    } catch (error) {
      console.warn('Could not parse Azure DevOps URL:', error);
      return `vstsagent.${repo.name.replace('/', '.')}`;
    }
  };

  const checkAzureAgentService = async (repoId) => {
    if (checkingAzureAgentService.has(repoId)) {
      return; // Already checking this service
    }

    const serviceName = azureAgentServiceNames[repoId] || getDefaultAzureAgentServiceName(repositories.find(r => r.id === repoId));
    
    try {
      setCheckingAzureAgentService(prev => new Set([...prev, repoId]));
      
      console.log(`Checking Azure agent service: ${serviceName} for repo ${repoId}`);
      
      const response = await api.checkAzureAgentService(repoId, { service_name: serviceName });
      
      setAzureAgentServiceStatus(prev => ({
        ...prev,
        [repoId]: response.data.data
      }));
      
      console.log(`Azure agent service check result for ${serviceName}:`, response.data.data);
      
    } catch (error) {
      console.error(`Error checking Azure agent service ${serviceName}:`, error);
      setAzureAgentServiceStatus(prev => ({
        ...prev,
        [repoId]: {
          status: 'error',
          status_display: 'Check Failed',
          service_name: serviceName,
          error: error.response?.data?.detail || error.message || 'Unknown error',
          exists: false
        }
      }));
    } finally {
      setCheckingAzureAgentService(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  const saveAzureAgentServiceName = async (repoId) => {
    if (savingAzureAgentServiceName.has(repoId)) {
      return; // Already saving
    }

    const serviceName = azureAgentServiceNames[repoId] || getDefaultAzureAgentServiceName(repositories.find(r => r.id === repoId));
    
    try {
      setSavingAzureAgentServiceName(prev => new Set([...prev, repoId]));
      
      await api.saveAzureAgentServiceName(repoId, { service_name: serviceName });
      
      showSuccess('Success', 'Azure agent service name saved successfully');
      
      // Automatically check the service status after saving
      safeTimeout(() => checkAzureAgentService(repoId), 500);
      
    } catch (error) {
      console.error('Error saving Azure agent service name:', error);
      showError('Error', error.response?.data?.detail || 'Failed to save Azure agent service name');
    } finally {
      setSavingAzureAgentServiceName(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
  };

  const fetchAvailableAzureServices = async () => {
    if (loadingAzureServices) {
      return; // Already loading
    }

    try {
      setLoadingAzureServices(true);
      
      // We need a repository ID to make the call, use the first available one
      const firstRepo = repositories.find(r => r.provider === 'azure_devops');
      if (!firstRepo) {
        console.warn('No Azure DevOps repositories found for service listing');
        return;
      }
      
      const response = await api.listAzureAgentServices(firstRepo.id);
      setAvailableAzureServices(response.data.data?.services || []);
      
    } catch (error) {
      console.error('Error fetching available Azure services:', error);
      setAvailableAzureServices([]);
    } finally {
      setLoadingAzureServices(false);
    }
  };

  const toggleAzureServiceDropdown = (repoId) => {
    console.log('Toggling Azure service dropdown for repo:', repoId, 'Current state:', azureServiceDropdownOpen[repoId]);
    setAzureServiceDropdownOpen(prev => ({
      ...prev,
      [repoId]: !prev[repoId]
    }));
    
    // Fetch Azure services when opening dropdown for the first time
    if (!azureServiceDropdownOpen[repoId] && availableAzureServices.length === 0) {
      console.log('Fetching available Azure services...');
      fetchAvailableAzureServices();
    }
  };

  // Token testing function
  const testToken = async (repoId) => {
    if (testingTokens.has(repoId)) {
      return; // Already testing
    }

    try {
      setTestingTokens(prev => new Set([...prev, repoId]));
      
      const response = await api.testRepositoryToken(repoId);
      
      setTokenTestResults(prev => ({
        ...prev,
        [repoId]: response.data.data
      }));
      
      if (response.data.data.success) {
        showSuccess('Token Test Successful', 'All token permissions are working correctly');
      } else {
        showError('Token Test Issues Found', 'Some permissions are missing or token is invalid');
      }
      
    } catch (error) {
      console.error('Error testing token:', error);
      setTokenTestResults(prev => ({
        ...prev,
        [repoId]: {
          success: false,
          error: error.response?.data?.detail || error.message || 'Unknown error',
          tested_at: new Date().toISOString()
        }
      }));
      showError('Token Test Failed', error.response?.data?.detail || 'Failed to test token');
    } finally {
      setTestingTokens(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoId);
        return newSet;
      });
    }
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
            className="flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 transition-colors duration-200 shadow-sm hover:shadow-md"
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
        <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-lg overflow-visible">
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
                    Provider
                  </label>
                  <select
                    value={formData.provider}
                    onChange={(e) => {
                      const provider = e.target.value;
                      setFormData((prev) => ({
                        ...prev,
                        provider,
                        action_runner_connection_id: provider === 'azure_devops' ? prev.action_runner_connection_id : null,
                      }));
                      if (provider === 'azure_devops') {
                        setWizardStep(0);
                        setWizardState({
                          orgUrl: '',
                          pat: '',
                          loading: false,
                          connected: false,
                          repos: [],
                          pools: [],
                          selectedRepoKey: '',
                          selectedPool: '',
                          connectionId: null,
                          provisioning: false,
                          provisioned: false,
                          skipRunner: false,
                        });
                      }
                    }}
                    className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-colors"
                  >
                    <option value="github">GitHub</option>
                    <option value="azure_devops">Azure DevOps</option>
                  </select>
                </div>
              </div>

              {formData.provider === 'github' && (
                <>
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
                  </div>
                  <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                    <h4 className="text-sm font-medium text-gray-900 dark:text-white mb-3 flex items-center">
                      <Key className="h-4 w-4 mr-2" />
                      Access Token Configuration
                    </h4>
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
                        {isTokenVisible('new', 'github') ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                      </button>
                    </div>
                  </div>
                </>
              )}

              {formData.provider === 'azure_devops' && (
                <div className="space-y-5">
                  <div className="grid grid-cols-5 gap-2">
                    {['Connect', 'Select Repo', 'Runner Setup', 'Pipeline Setup', 'Review'].map((label, idx) => (
                      <div key={label} className="flex items-center">
                        <div className={`h-8 w-8 rounded-full flex items-center justify-center text-xs font-semibold border ${wizardStep >= idx ? 'bg-blue-600 border-blue-600 text-white' : 'bg-white dark:bg-gray-700 border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-300'}`}>
                          {idx + 1}
                        </div>
                        <span className={`ml-2 text-xs ${wizardStep >= idx ? 'text-blue-700 dark:text-blue-300' : 'text-gray-500 dark:text-gray-400'}`}>{label}</span>
                      </div>
                    ))}
                  </div>

                  {wizardStep === 0 && (
                    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4 space-y-4">
                      <div>
                        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Step 1 - Connect to Azure DevOps</h4>
                        <p className="text-xs text-gray-600 dark:text-gray-400 mt-1">Enter org URL and PAT once. We reuse it for discovery, pool selection, and provisioning.</p>
                      </div>
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <input
                          type="url"
                          placeholder="https://mdt-software.visualstudio.com"
                          value={wizardState.orgUrl}
                          onChange={(e) => setWizardState((prev) => ({ ...prev, orgUrl: e.target.value }))}
                          className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                        />
                        <div className="relative">
                          <input
                            type={isTokenVisible('new', 'azure') ? 'text' : 'password'}
                            placeholder="Azure DevOps PAT"
                            value={wizardState.pat}
                            onChange={(e) => setWizardState((prev) => ({ ...prev, pat: e.target.value }))}
                            className="w-full px-4 py-3 pr-12 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white font-mono text-sm"
                          />
                          <button
                            type="button"
                            onClick={() => toggleTokenVisibility('new', 'azure')}
                            className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                          >
                            {isTokenVisible('new', 'azure') ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                          </button>
                        </div>
                      </div>
                      <div className="flex justify-end">
                        <button
                          type="button"
                          onClick={discoverAzureDevopsResources}
                          disabled={wizardState.loading || !wizardState.orgUrl.trim() || !wizardState.pat.trim()}
                          className="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                          {wizardState.loading ? 'Connecting…' : 'Connect & Discover'}
                        </button>
                      </div>
                    </div>
                  )}

                  {wizardStep === 1 && (() => {
                    const hasValidSelectedRepo = wizardState.repos.some(
                      (r) => getAzureRepoKey(r) === wizardState.selectedRepoKey
                    );
                    return (
                    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-4">
                      <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Step 2 - Select Repository</h4>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Discovered Repository</label>
                        <SearchableSelect
                          options={wizardState.repos.map((r) => ({
                            value: String(r.id || r.url || r.display_name),
                            label: r.display_name
                          }))}
                          value={wizardState.selectedRepoKey}
                          onChange={(val) => handleAzureDiscoveredRepoSelect(val)}
                          placeholder="Search and select repository..."
                        />
                      </div>
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Repository Name</label>
                          <input
                            type="text"
                            value={formData.name}
                            onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
                            className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                            required
                          />
                        </div>
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Repository URL</label>
                          <input
                            type="url"
                            value={formData.url}
                            onChange={(e) => setFormData((prev) => ({ ...prev, url: e.target.value }))}
                            className="w-full px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                            required
                          />
                        </div>
                      </div>
                      <div className="flex justify-between">
                        <button
                          type="button"
                          onClick={() => setWizardStep(0)}
                          className="px-4 py-2 rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300"
                        >
                          Back
                        </button>
                        <button
                          type="button"
                          onClick={() => setWizardStep(2)}
                          disabled={!hasValidSelectedRepo}
                          className="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                        >
                          Next: Runner Setup
                        </button>
                      </div>
                    </div>
                    );
                  })()}

                  {wizardStep === 2 && (
                    <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-4">
                      <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Step 3 - Runner Setup (Optional)</h4>
                      <p className="text-xs text-gray-600 dark:text-gray-400">Choose an agent pool and provision now, or skip and configure later.</p>
                      {(() => {
                        const connId = formData.action_runner_connection_id || wizardState.connectionId;
                        const progress = connId ? (provisionProgressByConnection[connId] || {}) : {};
                        const startup = progress.startup || {};
                        const milestones = startup.milestones || [];
                        const vmRunning = !!progress.vm_running;
                        const agentFound = !!progress.azure_agent?.found;
                        const agentOnline = !!progress.azure_agent?.online;
                        const totalSteps = 3 + milestones.length;
                        const doneCount =
                          (vmRunning ? 1 : 0) +
                          milestones.filter((m) => !!m.done).length +
                          (agentFound ? 1 : 0) +
                          (agentOnline ? 1 : 0);
                        const uiSetupComplete = !!progress.complete || (totalSteps > 0 && doneCount >= totalSteps);
                        const hasFailed = !!startup.failed;
                        const setupInProgress =
                          !!wizardState.provisioning ||
                          (!!connId && !uiSetupComplete && !hasFailed && (
                            !!vmRunning ||
                            milestones.length > 0 ||
                            !!startup.startup_complete ||
                            !!startup.log_available
                          ));

                        return (
                          <>
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Azure Agent Pool</label>
                        <SearchableSelect
                          options={wizardState.pools.map((p) => ({
                            value: p.name,
                            label: `${p.name}${p.is_hosted ? ' (hosted)' : ''}`
                          }))}
                          value={wizardState.selectedPool}
                          onChange={(val) => setWizardState((prev) => ({ ...prev, selectedPool: val }))}
                          placeholder="Search and select agent pool..."
                          disabled={wizardState.provisioned || wizardState.provisioning}
                        />
                      </div>

                      {(formData.action_runner_connection_id || wizardState.connectionId) && (() => {
                        const connId = formData.action_runner_connection_id || wizardState.connectionId;
                        const conn = actionRunnerConnections.find((c) => c.id === connId);
                        if (!conn) return null;
                        const hasVm = !!(conn.gcp_instance_name && conn.gcp_zone);
                        const provisionProgress = provisionProgressByConnection[connId] || {};
                        const vmRunning = !!provisionProgress.vm_running;
                        const startup = provisionProgress.startup || {};
                        const milestones = startup.milestones || [];
                        const consoleLines = startup.console_lines || [];
                        const agentFound = !!provisionProgress.azure_agent?.found;
                        const agentOnline = !!provisionProgress.azure_agent?.online;
                        const isComplete = !!provisionProgress.complete;
                        const startupComplete = !!startup.startup_complete;
                        const hasFailed = !!startup.failed;
                        const selfDestructing = !!startup.self_destructing;
                        const timedOut = !!startup.timed_out;

                        const allSteps = [
                          { label: 'VM running', done: vmRunning, active: !vmRunning },
                          ...milestones.map((m) => ({ label: m.label, done: m.done, active: false })),
                          { label: 'Agent registered in pool', done: agentFound, active: startupComplete && !agentFound },
                          { label: 'Agent online', done: agentOnline, active: agentFound && !agentOnline },
                        ];
                        const doneCount = allSteps.filter((s) => s.done).length;
                        const totalSteps = allSteps.length;
                        const overallPercent = totalSteps > 0 ? Math.round((doneCount / totalSteps) * 100) : 0;
                        // Treat setup as complete for UI flow when all visible milestones are done,
                        // even if backend aggregate completion lags briefly.
                        const uiSetupComplete = isComplete || (totalSteps > 0 && doneCount >= totalSteps);

                        return (
                          <div className={`rounded-lg border p-4 space-y-3 ${hasFailed ? 'border-red-300 dark:border-red-700 bg-red-50 dark:bg-red-900/20' : 'border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/30'}`}>
                            <div className="flex items-center justify-between">
                              <div className="text-sm font-semibold text-gray-900 dark:text-white">Provisioning Progress</div>
                              {hasFailed ? (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400">
                                  {timedOut ? 'Timed Out' : 'Failed'}{selfDestructing ? ' — VM deleting' : ''}
                                </span>
                              ) : uiSetupComplete ? (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400">Complete</span>
                              ) : (
                                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400">{overallPercent}%</span>
                              )}
                            </div>

                            {hasFailed && (
                              <div className="text-xs text-red-700 dark:text-red-400 bg-red-100 dark:bg-red-900/30 rounded p-2">
                                {selfDestructing
                                  ? 'The startup script failed and the VM is being automatically deleted to avoid cost. Check the console output below for the error.'
                                  : 'The startup script encountered an error. The VM will attempt to self-destruct. Check the console output below.'}
                              </div>
                            )}

                            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                              <div
                                className={`h-2 rounded-full transition-all duration-500 ${hasFailed ? 'bg-red-500' : isComplete ? 'bg-green-500' : 'bg-blue-500'}`}
                                style={{ width: `${overallPercent}%` }}
                              />
                            </div>

                            <div className="grid grid-cols-1 gap-1 max-h-48 overflow-y-auto pr-1">
                              {allSteps.map((step, i) => (
                                <div key={i} className="flex items-center gap-2 text-xs">
                                  {step.done ? (
                                    <svg className="w-4 h-4 text-green-500 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                                  ) : step.active ? (
                                    <svg className="w-4 h-4 text-blue-500 shrink-0 animate-spin" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>
                                  ) : (
                                    <svg className="w-4 h-4 text-gray-300 dark:text-gray-600 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="12" r="8" strokeWidth={2} /></svg>
                                  )}
                                  <span className={step.done ? 'text-green-700 dark:text-green-400' : step.active ? 'text-blue-700 dark:text-blue-300 font-medium' : 'text-gray-500 dark:text-gray-500'}>{step.label}</span>
                                </div>
                              ))}
                            </div>

                            {consoleLines.length > 0 && (
                              <details className="group" open>
                                <summary className="cursor-pointer text-xs font-medium text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 select-none">
                                  Console output ({consoleLines.length} lines)
                                </summary>
                                <div className="mt-2 flex items-center justify-between">
                                  {consoleAutoScrollEnabled ? (
                                    <span className="text-[11px] text-gray-500 dark:text-gray-400">
                                      Auto-scroll is on. Scroll the console to stop auto-follow.
                                    </span>
                                  ) : (
                                    <span className="text-[11px] text-gray-500 dark:text-gray-400">
                                      Auto-scroll paused.
                                    </span>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() => copyProvisionConsole(consoleLines)}
                                    className="inline-flex items-center px-2 py-1 rounded text-[11px] font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50 border border-blue-200 dark:border-blue-800"
                                  >
                                    <Copy className="h-3.5 w-3.5 mr-1" />
                                    Copy
                                  </button>
                                </div>
                                <div
                                  className="mt-2 bg-gray-900 rounded-md p-2 max-h-72 overflow-y-auto font-mono text-xs text-green-400 leading-relaxed scroll-smooth"
                                  ref={consoleEndRef}
                                  onWheel={() => setConsoleAutoScrollEnabled(false)}
                                  onTouchMove={() => setConsoleAutoScrollEnabled(false)}
                                >
                                  {consoleLines.map((line, i) => (
                                    <div key={i} className="whitespace-pre-wrap break-all">{line.replace(/\[pr-agent-runner-startup\]\s*/, '')}</div>
                                  ))}
                                </div>
                              </details>
                            )}

                            {!startup.log_available && vmRunning && (
                              <div className="text-xs text-gray-500 dark:text-gray-400 italic">Waiting for serial console output&hellip; (VM just started)</div>
                            )}
                            {!hasFailed && !uiSetupComplete && (
                              <div className="text-xs text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded p-2">
                                Setup is still running. Do not close, navigate away, or refresh this page until provisioning completes.
                              </div>
                            )}

                            {hasVm && (
                              <div className="text-xs text-gray-500 dark:text-gray-500">
                                VM: {conn.gcp_instance_name} &middot; {conn.gcp_zone}
                              </div>
                            )}
                          </div>
                        );
                      })()}

                      <div className="flex flex-wrap gap-2 justify-between">
                        <button
                          type="button"
                          onClick={() => setWizardStep(1)}
                          disabled={setupInProgress}
                          className="px-4 py-2 rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          Back
                        </button>
                        <div className="flex flex-wrap gap-2">
                          {!wizardState.provisioned && (
                            <button
                              type="button"
                              onClick={() => {
                                setWizardState((prev) => ({ ...prev, skipRunner: true }));
                                setWizardStep(3);
                              }}
                              disabled={setupInProgress}
                              className="px-4 py-2 rounded border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              Skip for now
                            </button>
                          )}
                          {!wizardState.provisioned && (
                            <button
                              type="button"
                              onClick={handleAzureProvisionRunner}
                              disabled={setupInProgress || !wizardState.selectedPool}
                              className="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50"
                            >
                              {setupInProgress
                                ? (wizardState.provisioning ? 'Provisioning…' : 'Setup still running…')
                                : 'Provision Runner VM'}
                            </button>
                          )}
                          {wizardState.provisioned && (() => {
                            const connId = formData.action_runner_connection_id || wizardState.connectionId;
                            const progress = provisionProgressByConnection[connId] || {};
                            const startup = progress.startup || {};
                            const milestones = startup.milestones || [];
                            const vmRunning = !!progress.vm_running;
                            const agentFound = !!progress.azure_agent?.found;
                            const agentOnline = !!progress.azure_agent?.online;
                            const allSteps = [
                              { done: vmRunning },
                              ...milestones.map((m) => ({ done: !!m.done })),
                              { done: agentFound },
                              { done: agentOnline },
                            ];
                            const doneCount = allSteps.filter((s) => s.done).length;
                            const totalSteps = allSteps.length;
                            const isComplete = !!progress.complete || (totalSteps > 0 && doneCount >= totalSteps);
                            return (
                              <button
                                type="button"
                                onClick={() => setWizardStep(3)}
                                disabled={!isComplete}
                                className={`px-4 py-2 rounded text-white transition-colors ${
                                  isComplete
                                    ? 'bg-green-600 hover:bg-green-700'
                                    : 'bg-gray-400 dark:bg-gray-600 cursor-not-allowed'
                                }`}
                              >
                                {isComplete ? 'Continue to Pipeline Setup' : 'Setup still running...'}
                              </button>
                            );
                          })()}
                        </div>
                      </div>
                          </>
                        );
                      })()}
                    </div>
                  )}

                  {wizardStep === 3 && (
                    <div className="space-y-4">
                      <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-4">
                        <h4 className="text-sm font-semibold text-gray-900 dark:text-white">Step 4 - Pipeline & Policy Setup</h4>
                        <p className="text-xs text-gray-600 dark:text-gray-400">Deploy the PR-Agent pipeline YAML and set up a build validation check so PR-Agent runs on every pull request.</p>

                        {/* Bot identity info */}
                        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                          <div className="flex items-start">
                            <Info className="h-4 w-4 text-blue-600 dark:text-blue-400 mr-2 mt-0.5 flex-shrink-0" />
                            <div className="text-xs text-blue-700 dark:text-blue-300 space-y-1">
                              <p className="font-medium">PR review identity</p>
                              {azurePatIdentity.loading ? (
                                <p>Resolving PAT identity…</p>
                              ) : azurePatIdentity.data?.identity?.display_name ? (
                                <>
                                  <p>
                                    Reviews/comments will appear as{' '}
                                    <span className="font-semibold">{azurePatIdentity.data.identity.display_name}</span>
                                    {azurePatIdentity.data.identity.unique_name ? ` (${azurePatIdentity.data.identity.unique_name})` : ''}.
                                  </p>
                                  <p>
                                    Runtime auth source:{' '}
                                    <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">
                                      {azurePatIdentity.data?.verification?.review_auth_source || 'AZURE_DEVOPS_PAT'}
                                    </code>
                                    {' '}with fallback to{' '}
                                    <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">
                                      {azurePatIdentity.data?.verification?.fallback_auth_source || 'SYSTEM_ACCESSTOKEN'}
                                    </code>.
                                  </p>
                                  {azurePatIdentity.data?.verification?.review_uses_provided_pat ? (
                                    <p className="font-medium text-green-700 dark:text-green-300">
                                      Verified: this same PAT is the one used by PR-Agent reviews in this setup.
                                    </p>
                                  ) : (
                                    <p className="font-medium text-amber-700 dark:text-amber-300">
                                      Verification warning: {azurePatIdentity.data?.verification?.reason || 'Review runtime may not be using the provided PAT yet.'}
                                    </p>
                                  )}
                                </>
                              ) : azurePatIdentity.error ? (
                                <p className="text-amber-700 dark:text-amber-300">Could not resolve PAT identity: {azurePatIdentity.error}</p>
                              ) : (
                                <p>Connect with a PAT in Step 1 to detect and display the review identity.</p>
                              )}
                            </div>
                          </div>
                        </div>

                        <label className="flex items-center space-x-3 cursor-pointer">
                          <input
                            type="checkbox"
                            checked={wizardState.setupPipeline}
                            onChange={(e) => setWizardState(prev => ({ ...prev, setupPipeline: e.target.checked }))}
                            className="rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4"
                          />
                          <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Set up AI review pipeline</span>
                        </label>

                        {wizardState.setupPipeline && (
                          <div className="space-y-3 pl-7">
                            <div>
                              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Branch to protect</label>
                              <SearchableSelect
                                options={(branchesData['wizard']?.branches || []).map(b => ({ value: b.name, label: `${b.name}${b.is_default ? ' (default)' : ''}` }))}
                                value={wizardState.pipelineBranch}
                                onChange={(val) => setWizardState(prev => ({ ...prev, pipelineBranch: val }))}
                                placeholder={branchesData['wizard'] ? 'Select branch...' : 'Loading branches...'}
                              />
                            </div>
                            <div>
                              <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Policy type</label>
                              <div className="flex items-center space-x-3">
                                <button
                                  onClick={() => setWizardState(prev => ({ ...prev, pipelineIsBlocking: false }))}
                                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                                    !wizardState.pipelineIsBlocking ? 'bg-blue-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                                  }`}
                                >Optional</button>
                                <button
                                  onClick={() => setWizardState(prev => ({ ...prev, pipelineIsBlocking: true }))}
                                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                                    wizardState.pipelineIsBlocking ? 'bg-red-600 text-white' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                                  }`}
                                >Required</button>
                              </div>
                            </div>

                            {wizardState.pipelineSetupResult && (
                              <div className={`rounded-lg p-3 text-sm ${
                                wizardState.pipelineSetupResult.success
                                  ? 'bg-green-50 dark:bg-green-900/20 text-green-700 dark:text-green-300 border border-green-200 dark:border-green-800'
                                  : 'bg-red-50 dark:bg-red-900/20 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800'
                              }`}>
                                {wizardState.pipelineSetupResult.success ? (
                                  <div className="space-y-2">
                                    {wizardState.pipelineSetupResult.yaml_pushed && <p><CheckCircle className="h-4 w-4 inline mr-1" /> Pipeline YAML deployed</p>}
                                    {wizardState.pipelineSetupResult.yaml_up_to_date && <p><CheckCircle className="h-4 w-4 inline mr-1" /> Shared pipeline YAML already up-to-date</p>}
                                    {wizardState.pipelineSetupResult.pipeline_created && <p><CheckCircle className="h-4 w-4 inline mr-1" /> Pipeline definition created</p>}
                                    {wizardState.pipelineSetupResult.shared_pipeline_repo && (
                                      <p>
                                        <CheckCircle className="h-4 w-4 inline mr-1" />
                                        Using shared pipeline repo: {wizardState.pipelineSetupResult.shared_pipeline_repo}
                                      </p>
                                    )}
                                    {wizardState.pipelineSetupResult.requires_pr_merge && (
                                      <p>
                                        <AlertCircle className="h-4 w-4 inline mr-1" />
                                        Direct push blocked; merge PR #{wizardState.pipelineSetupResult.pr_number} to finish YAML setup.
                                      </p>
                                    )}
                                    {wizardState.pipelineSetupResult.policy_created && <p><CheckCircle className="h-4 w-4 inline mr-1" /> Build validation policy added</p>}
                                    {wizardState.pipelineSetupResult.policy_updated && <p><CheckCircle className="h-4 w-4 inline mr-1" /> Build validation policy updated</p>}
                                    {wizardState.pipelineSetupResult.setup_message && <p>{wizardState.pipelineSetupResult.setup_message}</p>}
                                    {Array.isArray(wizardState.pipelineSetupResult.setup_steps) && wizardState.pipelineSetupResult.setup_steps.length > 0 && (
                                      <div className="mt-2 space-y-1.5">
                                        {wizardState.pipelineSetupResult.setup_steps.map((step) => (
                                          <div key={step.id || step.label} className="flex items-start">
                                            {step.status === 'success' ? (
                                              <CheckCircle className="h-4 w-4 mt-0.5 mr-2 flex-shrink-0" />
                                            ) : step.status === 'error' ? (
                                              <AlertCircle className="h-4 w-4 mt-0.5 mr-2 flex-shrink-0" />
                                            ) : step.status === 'in_progress' ? (
                                              <RefreshCw className="h-4 w-4 mt-0.5 mr-2 flex-shrink-0 animate-spin" />
                                            ) : (
                                              <Clock className="h-4 w-4 mt-0.5 mr-2 flex-shrink-0" />
                                            )}
                                            <div>
                                              <p>{step.label}</p>
                                              {step.detail && <p className="text-xs opacity-80">{step.detail}</p>}
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                    {Array.isArray(wizardState.pipelineSetupResult.cleanup_plan) && wizardState.pipelineSetupResult.cleanup_plan.length > 0 && (
                                      <div className="mt-2 text-xs opacity-90">
                                        <p className="font-semibold">Failure cleanup plan:</p>
                                        {wizardState.pipelineSetupResult.cleanup_plan.map((item, idx) => (
                                          <p key={`cleanup-plan-${idx}`}>- {item}</p>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ) : (
                                  <div className="space-y-2">
                                    <p>{wizardState.pipelineSetupResult.error}</p>
                                    {Array.isArray(wizardState.pipelineSetupResult.setup_steps) && wizardState.pipelineSetupResult.setup_steps.length > 0 && (
                                      <div className="space-y-1.5">
                                        {wizardState.pipelineSetupResult.setup_steps.map((step) => (
                                          <div key={step.id || step.label} className="flex items-start">
                                            {step.status === 'success' ? (
                                              <CheckCircle className="h-4 w-4 mt-0.5 mr-2 flex-shrink-0" />
                                            ) : step.status === 'error' ? (
                                              <AlertCircle className="h-4 w-4 mt-0.5 mr-2 flex-shrink-0" />
                                            ) : (
                                              <Clock className="h-4 w-4 mt-0.5 mr-2 flex-shrink-0" />
                                            )}
                                            <div>
                                              <p>{step.label}</p>
                                              {step.detail && <p className="text-xs opacity-80">{step.detail}</p>}
                                            </div>
                                          </div>
                                        ))}
                                      </div>
                                    )}
                                    {wizardState.pipelineSetupResult.cleanup?.attempted && Array.isArray(wizardState.pipelineSetupResult.cleanup.actions) && wizardState.pipelineSetupResult.cleanup.actions.length > 0 && (
                                      <div className="text-xs">
                                        <p className="font-semibold">Automatic cleanup attempted:</p>
                                        {wizardState.pipelineSetupResult.cleanup.actions.map((action, idx) => (
                                          <p key={`cleanup-action-${idx}`}>
                                            - {action.resource}: {action.success ? 'done' : 'failed'}{action.detail ? ` (${action.detail})` : ''}
                                          </p>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                )}
                              </div>
                            )}

                            {wizardState.loading && !wizardState.pipelineSetupResult && (
                              <div className="rounded-lg p-3 text-sm bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 space-y-1.5">
                                {[
                                  'Checking for shared pipeline repo',
                                  'Checking for YAML update',
                                  'Creating shared pipeline repo if needed',
                                  'Updating shared pipeline YAML if needed',
                                  'Waiting until the pipeline is available',
                                  'Setting up check for the target repository',
                                ].map((label, idx) => (
                                  <div key={`loading-step-${idx}`} className="flex items-center">
                                    {idx === 0 ? (
                                      <RefreshCw className="h-4 w-4 mr-2 flex-shrink-0 animate-spin" />
                                    ) : (
                                      <Clock className="h-4 w-4 mr-2 flex-shrink-0" />
                                    )}
                                    <span>{label}</span>
                                  </div>
                                ))}
                              </div>
                            )}

                            {!wizardState.pipelineSetupDone && (
                              <button
                                onClick={async () => {
                                  try {
                                    setWizardState(prev => ({ ...prev, loading: true }));
                                    let pushResult = {};
                                    let policyResult = {};
                                    let setupSteps = [];
                                    let cleanupPlan = [];
                                    let cleanupResult = { attempted: false, actions: [] };
                                    if (formData.id) {
                                      const pushResp = await api.pushPipelineYaml(formData.id);
                                      pushResult = pushResp.data?.data || pushResp.data || {};
                                      setupSteps = Array.isArray(pushResult.setup_steps) ? [...pushResult.setup_steps] : [];
                                      cleanupPlan = Array.isArray(pushResult.cleanup_plan) ? pushResult.cleanup_plan : [];
                                      cleanupResult = pushResult.cleanup || cleanupResult;
                                      if (!pushResult.success) {
                                        setWizardState(prev => ({
                                          ...prev,
                                          loading: false,
                                          pipelineSetupResult: {
                                            success: false,
                                            error: pushResult.error || 'Failed to push YAML',
                                            setup_steps: setupSteps,
                                            cleanup_plan: cleanupPlan,
                                            cleanup: cleanupResult,
                                          }
                                        }));
                                        return;
                                      }
                                      if (wizardState.pipelineBranch && pushResult.pipeline_id) {
                                        const polResp = await api.ensurePipelinePolicy(formData.id, {
                                          branch: wizardState.pipelineBranch,
                                          pipeline_definition_id: pushResult.pipeline_id,
                                          is_blocking: wizardState.pipelineIsBlocking,
                                        });
                                        policyResult = polResp.data?.data || polResp.data || {};
                                        setupSteps.push({
                                          id: 'setup_target_repo_check',
                                          label: 'Setting up check for the target repository',
                                          status: 'success',
                                          detail: 'Build validation policy configured.',
                                        });
                                      } else {
                                        setupSteps.push({
                                          id: 'setup_target_repo_check',
                                          label: 'Setting up check for the target repository',
                                          status: 'skipped',
                                          detail: 'Skipped until pipeline is available for policy attachment.',
                                        });
                                      }
                                    } else {
                                      const selected = wizardState.repos.find((r) => getAzureRepoKey(r) === wizardState.selectedRepoKey);
                                      const repoUrl = (selected?.url || formData.url || '').trim();
                                      const pat = (wizardState.pat || formData.azure_pat || '').trim();
                                      if (!repoUrl || !pat) {
                                        setWizardState(prev => ({
                                          ...prev,
                                          loading: false,
                                          pipelineSetupResult: { success: false, error: 'Missing repository URL or PAT. Reconnect in Step 1.' }
                                        }));
                                        return;
                                      }
                                      const setupResp = await api.setupAzureDevopsPipeline({
                                        repo_url: repoUrl,
                                        pat,
                                        branch: wizardState.pipelineBranch || '',
                                        is_blocking: wizardState.pipelineIsBlocking,
                                        action_runner_connection_id: formData.action_runner_connection_id || wizardState.connectionId || null,
                                      });
                                      const setupResult = setupResp.data?.data || setupResp.data || {};
                                      pushResult = {
                                        success: !!setupResult.success,
                                        yaml_pushed: !!setupResult.yaml_pushed,
                                        yaml_up_to_date: !!setupResult.yaml_up_to_date,
                                        pipeline_created: !!setupResult.pipeline_created,
                                        pipeline_id: setupResult.pipeline_id,
                                        shared_pipeline_repo: setupResult.shared_pipeline_repo || null,
                                        requires_pr_merge: !!setupResult.requires_pr_merge,
                                        pr_number: setupResult.pr_number || null,
                                        pr_url: setupResult.pr_url || null,
                                        branch_name: setupResult.branch_name || null,
                                        setup_message: setupResult.setup_message || null,
                                      };
                                      setupSteps = Array.isArray(setupResult.setup_steps) ? setupResult.setup_steps : [];
                                      cleanupPlan = Array.isArray(setupResult.cleanup_plan) ? setupResult.cleanup_plan : [];
                                      cleanupResult = setupResult.cleanup || cleanupResult;
                                      policyResult = {
                                        created: !!setupResult.policy_created,
                                        updated: !!setupResult.policy_updated,
                                      };
                                    }
                                    setWizardState(prev => ({
                                      ...prev,
                                      loading: false,
                                      pipelineSetupDone: true,
                                      pipelineSetupResult: {
                                        success: true,
                                        yaml_pushed: pushResult.yaml_pushed,
                                        yaml_up_to_date: pushResult.yaml_up_to_date,
                                        pipeline_created: pushResult.pipeline_created,
                                        shared_pipeline_repo: pushResult.shared_pipeline_repo || null,
                                        requires_pr_merge: pushResult.requires_pr_merge || false,
                                        pr_number: pushResult.pr_number || null,
                                        pr_url: pushResult.pr_url || null,
                                        branch_name: pushResult.branch_name || null,
                                        setup_message: pushResult.setup_message || null,
                                        setup_steps: setupSteps,
                                        cleanup_plan: cleanupPlan,
                                        cleanup: cleanupResult,
                                        policy_created: policyResult.created || false,
                                        policy_updated: policyResult.updated || false,
                                      }
                                    }));
                                  } catch (err) {
                                    const errorDetail = err.response?.data?.detail;
                                    const parsedError = typeof errorDetail === 'string'
                                      ? { message: errorDetail }
                                      : (errorDetail || {});
                                    setWizardState(prev => ({
                                      ...prev,
                                      loading: false,
                                      pipelineSetupResult: {
                                        success: false,
                                        error: parsedError.message || err.message,
                                        setup_steps: Array.isArray(parsedError.setup_steps) ? parsedError.setup_steps : [],
                                        cleanup_plan: Array.isArray(parsedError.cleanup_plan) ? parsedError.cleanup_plan : [],
                                        cleanup: parsedError.cleanup || { attempted: false, actions: [] },
                                      }
                                    }));
                                  }
                                }}
                                disabled={wizardState.loading}
                                className="flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors disabled:opacity-50"
                              >
                                {wizardState.loading ? <><RefreshCw className="h-4 w-4 mr-1.5 animate-spin" /> Setting up...</> : <><Settings className="h-4 w-4 mr-1.5" /> Set Up Pipeline & Check</>}
                              </button>
                            )}
                          </div>
                        )}
                      </div>

                      <div className="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
                        <button type="button" onClick={() => setWizardStep(2)}
                          className="px-6 py-2.5 text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                          Back
                        </button>
                        <div className="space-x-3">
                          <button type="button" onClick={() => setWizardStep(4)}
                            className="px-4 py-2 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300">
                            {wizardState.setupPipeline ? 'Skip' : 'Continue'}
                          </button>
                          {wizardState.pipelineSetupDone && (
                            <button type="button" onClick={() => setWizardStep(4)}
                              className="px-6 py-2.5 text-sm font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors shadow-sm">
                              Continue to Review
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )}

                  {wizardStep === 4 && (
                    <div className="space-y-4">
                      <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                        <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-3">Step 5 - Review & Save</h4>
                        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 text-sm">
                          <div className="text-gray-700 dark:text-gray-300"><span className="font-medium">Repository:</span> {formData.name || 'Not selected'}</div>
                          <div className="text-gray-700 dark:text-gray-300"><span className="font-medium">URL:</span> {formData.url || 'Not selected'}</div>
                          <div className="text-gray-700 dark:text-gray-300"><span className="font-medium">Pool:</span> {wizardState.selectedPool || 'Not set'}</div>
                          <div className="text-gray-700 dark:text-gray-300"><span className="font-medium">Runner setup:</span> {wizardState.skipRunner ? 'Skipped' : (formData.action_runner_connection_id ? 'Connected' : 'Not provisioned')}</div>
                        </div>
                      </div>

                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Configuration</label>
                        <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                          <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                            <input type="checkbox" checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Active</span>
                          </label>
                          <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                            <input type="checkbox" checked={formData.monitor_prs} onChange={(e) => setFormData({ ...formData, monitor_prs: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Monitor PRs</span>
                          </label>
                          <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                            <input type="checkbox" checked={formData.monitor_issues} onChange={(e) => setFormData({ ...formData, monitor_issues: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Monitor Issues</span>
                          </label>
                          <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                            <input type="checkbox" checked={formData.auto_review} onChange={(e) => setFormData({ ...formData, auto_review: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto Review</span>
                          </label>
                          <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                            <input type="checkbox" checked={formData.auto_describe} onChange={(e) => setFormData({ ...formData, auto_describe: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto Describe</span>
                          </label>
                          <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                            <input type="checkbox" checked={formData.auto_improve} onChange={(e) => setFormData({ ...formData, auto_improve: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto Improve</span>
                          </label>
                        </div>
                      </div>

                      <div className="flex justify-between pt-4 border-t border-gray-200 dark:border-gray-700">
                        <button
                          type="button"
                          onClick={() => setWizardStep(3)}
                          className="px-6 py-2.5 text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                        >
                          Back
                        </button>
                        <div className="space-x-3">
                          <button
                            type="button"
                            onClick={resetForm}
                            className="px-6 py-2.5 text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
                          >
                            Cancel
                          </button>
                          <button
                            type="submit"
                            disabled={!formData.name.trim() || !formData.url.trim() || !wizardState.pat.trim()}
                            className="px-6 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 transition-colors shadow-sm hover:shadow-md disabled:opacity-50"
                          >
                            <Plus className="h-4 w-4 mr-2 inline" />
                            Add Repository
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {formData.provider === 'github' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">Configuration</label>
                  <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
                    <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                      <input type="checkbox" checked={formData.is_active} onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Active</span>
                    </label>
                    <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                      <input type="checkbox" checked={formData.monitor_prs} onChange={(e) => setFormData({ ...formData, monitor_prs: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Monitor PRs</span>
                    </label>
                    <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                      <input type="checkbox" checked={formData.monitor_issues} onChange={(e) => setFormData({ ...formData, monitor_issues: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Monitor Issues</span>
                    </label>
                    <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                      <input type="checkbox" checked={formData.auto_review} onChange={(e) => setFormData({ ...formData, auto_review: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto Review</span>
                    </label>
                    <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                      <input type="checkbox" checked={formData.auto_describe} onChange={(e) => setFormData({ ...formData, auto_describe: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto Describe</span>
                    </label>
                    <label className="flex items-center p-3 border border-gray-200 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors cursor-pointer">
                      <input type="checkbox" checked={formData.auto_improve} onChange={(e) => setFormData({ ...formData, auto_improve: e.target.checked })} className="mr-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500 h-4 w-4" />
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300">Auto Improve</span>
                    </label>
                  </div>
                  <div className="flex justify-end space-x-3 pt-4 border-t border-gray-200 dark:border-gray-700 mt-6">
                    <button type="button" onClick={resetForm} className="px-6 py-2.5 text-sm font-medium border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-800 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                      Cancel
                    </button>
                    <button type="submit" className="px-6 py-2.5 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 transition-colors shadow-sm hover:shadow-md">
                      <Plus className="h-4 w-4 mr-2 inline" />
                      Add Repository
                    </button>
                  </div>
                </div>
              )}
            </form>
          </div>
        </div>
      )}

      {/* Action Runners Management */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm">
        <button
          type="button"
          onClick={() => { setShowRunnersPanel((p) => !p); if (!showRunnersPanel) fetchActionRunnerConnections(); }}
          className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-gray-50 dark:hover:bg-gray-700/50 transition-colors"
        >
          <div className="flex items-center gap-3">
            <Server className="h-5 w-5 text-indigo-500" />
            <div>
              <div className="text-sm font-semibold text-gray-900 dark:text-white">Action Runners</div>
              <div className="text-xs text-gray-500 dark:text-gray-400">
                {actionRunnerConnections.length} connection{actionRunnerConnections.length !== 1 ? 's' : ''} configured
              </div>
            </div>
          </div>
          {showRunnersPanel ? <ChevronDown className="h-5 w-5 text-gray-400" /> : <ChevronRight className="h-5 w-5 text-gray-400" />}
        </button>

        {showRunnersPanel && (
          <div className="border-t border-gray-200 dark:border-gray-700 px-6 py-4 space-y-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-gray-500 dark:text-gray-400">
                Self-hosted runner VMs that execute PR-Agent pipelines. Deleting a runner destroys the VM and deregisters the agent from Azure DevOps.
              </p>
              <button
                type="button"
                onClick={() => setShowCreateRunner(true)}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors shrink-0 ml-4"
              >
                <Plus className="h-3.5 w-3.5" />
                New Runner
              </button>
            </div>

            {showCreateRunner && (
              <div className="bg-gray-50 dark:bg-gray-900/40 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
                <div className="text-sm font-medium text-gray-900 dark:text-white">Create Action Runner Connection</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Provider</label>
                    <select
                      value={newRunnerForm.provider}
                      onChange={(e) => setNewRunnerForm((f) => ({ ...f, provider: e.target.value }))}
                      className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    >
                      <option value="azure_devops">Azure DevOps</option>
                      <option value="github">GitHub</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Organization *</label>
                    <input
                      type="text"
                      value={newRunnerForm.organization}
                      onChange={(e) => setNewRunnerForm((f) => ({ ...f, organization: e.target.value }))}
                      placeholder="e.g. my-org"
                      className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    />
                  </div>
                  {newRunnerForm.provider === 'azure_devops' && (
                    <div>
                      <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Project</label>
                      <input
                        type="text"
                        value={newRunnerForm.project}
                        onChange={(e) => setNewRunnerForm((f) => ({ ...f, project: e.target.value }))}
                        placeholder="e.g. MyProject"
                        className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </div>
                  )}
                  <div>
                    <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Display Name</label>
                    <input
                      type="text"
                      value={newRunnerForm.display_name}
                      onChange={(e) => setNewRunnerForm((f) => ({ ...f, display_name: e.target.value }))}
                      placeholder="Optional"
                      className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                    />
                  </div>
                  {newRunnerForm.provider === 'azure_devops' && (
                    <div>
                      <label className="block text-xs font-medium text-gray-700 dark:text-gray-300 mb-1">Agent Pool</label>
                      <input
                        type="text"
                        value={newRunnerForm.agent_pool}
                        onChange={(e) => setNewRunnerForm((f) => ({ ...f, agent_pool: e.target.value }))}
                        placeholder="e.g. PRAgent_Cloud"
                        className="w-full px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                      />
                    </div>
                  )}
                </div>
                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={() => setShowCreateRunner(false)}
                    className="px-3 py-1.5 text-xs font-medium text-gray-700 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={handleCreateRunner}
                    disabled={creatingRunner || !newRunnerForm.organization.trim()}
                    className="px-3 py-1.5 text-xs font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {creatingRunner ? 'Creating…' : 'Create'}
                  </button>
                </div>
              </div>
            )}

            {actionRunnerConnections.length === 0 ? (
              <div className="text-center py-8 text-sm text-gray-500 dark:text-gray-400">
                No action runners configured yet. Add one via the repository wizard or create one manually.
              </div>
            ) : (
              <div className="space-y-2">
                {actionRunnerConnections.map((conn) => {
                  const hasVm = !!(conn.gcp_instance_name && conn.gcp_zone);
                  const progress = provisionProgressByConnection[conn.id] || {};
                  const vmRunning = !!progress.vm_running;
                  const agentOnline = !!progress.azure_agent?.online;
                  const isDeleting = deletingRunner === conn.id;
                  const linkedRepos = repositories.filter((r) => r.action_runner_connection_id === conn.id);

                  let statusColor = 'bg-gray-400';
                  let statusLabel = 'No VM';
                  if (hasVm && agentOnline) { statusColor = 'bg-green-500'; statusLabel = 'Online'; }
                  else if (hasVm && vmRunning) { statusColor = 'bg-yellow-500'; statusLabel = 'VM Running'; }
                  else if (hasVm) { statusColor = 'bg-orange-500'; statusLabel = progress.vm_status || 'Provisioned'; }

                  return (
                    <div key={conn.id} className="flex items-center justify-between p-3 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 hover:border-gray-300 dark:hover:border-gray-600 transition-colors">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className={`w-2.5 h-2.5 rounded-full shrink-0 ${statusColor}`} title={statusLabel} />
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900 dark:text-white truncate">
                            {conn.display_name || `${conn.organization}${conn.project ? ' / ' + conn.project : ''}`}
                          </div>
                          <div className="text-xs text-gray-500 dark:text-gray-400 flex flex-wrap gap-x-3 gap-y-0.5">
                            <span>{conn.provider === 'azure_devops' ? 'Azure DevOps' : 'GitHub'}</span>
                            {conn.agent_pool && <span>Pool: {conn.agent_pool}</span>}
                            {hasVm && <span>VM: {conn.gcp_instance_name}</span>}
                            {linkedRepos.length > 0 && <span>{linkedRepos.length} repo{linkedRepos.length !== 1 ? 's' : ''} linked</span>}
                            <span className={`font-medium ${statusColor === 'bg-green-500' ? 'text-green-600 dark:text-green-400' : statusColor === 'bg-yellow-500' ? 'text-yellow-600 dark:text-yellow-400' : 'text-gray-500 dark:text-gray-400'}`}>
                              {statusLabel}
                            </span>
                          </div>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleDeleteRunner(conn)}
                        disabled={isDeleting}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50 transition-colors shrink-0 ml-3"
                        title="Delete runner, destroy VM, deregister agent"
                      >
                        {isDeleting ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
                        {isDeleting ? 'Deleting…' : 'Delete'}
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Repository List */}
      <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 shadow-sm overflow-visible">
        {repositories.length === 0 ? (
          <div className="p-12 text-center">
            <div className="mx-auto w-24 h-24 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center mb-6">
              <GitBranch className="h-12 w-12 text-gray-400" />
            </div>
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white mb-2">No repositories configured</h3>
            <p className="text-gray-500 dark:text-gray-400 mb-6 max-w-md mx-auto">Get started by adding your first repository to begin monitoring pull requests and issues.</p>
            <button
              onClick={() => setShowAddForm(true)}
              className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 transition-colors duration-200 shadow-sm hover:shadow-md"
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
                          {repo.provider === 'azure_devops' && syncStatusData[repo.id] && (
                            <>
                              <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                syncStatusData[repo.id].sync_status === 'up_to_date'
                                  ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                                  : syncStatusData[repo.id].sync_status === 'outdated'
                                    ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                                    : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                              }`}>
                                {syncStatusData[repo.id].sync_status === 'up_to_date' ? 'Pipeline: Synced'
                                  : syncStatusData[repo.id].sync_status === 'outdated' ? 'Pipeline: Outdated'
                                  : 'Pipeline: Missing'}
                              </span>
                              {policiesData[repo.id]?.policies && (
                                <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                                  policiesData[repo.id].policies.length > 0
                                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300'
                                    : 'bg-gray-100 text-gray-600 dark:bg-gray-700 dark:text-gray-400'
                                }`}>
                                  {policiesData[repo.id].policies.length > 0
                                    ? `Check: ${policiesData[repo.id].policies.length} Active`
                                    : 'Check: None'}
                                </span>
                              )}
                            </>
                          )}
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
                              {/* Comprehensive Refresh Button */}
                              {getTokenStatus(repo) === 'configured' && (
                                <button
                                  onClick={() => comprehensiveRefresh(repo.id)}
                                  disabled={checkingHealth.has(repo.id) || checkingConfig.has(repo.id)}
                                  className="flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  {(checkingHealth.has(repo.id) || checkingConfig.has(repo.id)) ? (
                                    <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                  ) : (
                                    <RefreshCw className="h-4 w-4 mr-2" />
                                  )}
                                  Refresh
                                </button>
                              )}
                              
                              {/* Active Toggle */}
                              <button
                                onClick={() => toggleRepositoryActive(repo.id, repo.is_active)}
                                disabled={isRepoActionBusy(repo.id)}
                                className={`flex items-center px-4 py-2 text-sm font-medium rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-60 disabled:cursor-not-allowed ${
                                  repo.is_active
                                    ? 'text-white bg-red-600 hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600'
                                    : 'text-white bg-green-600 hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600'
                                }`}
                              >
                                {isRepoActionBusy(repo.id) ? (
                                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                ) : repo.is_active ? (
                                  <X className="h-4 w-4 mr-2" />
                                ) : (
                                  <Check className="h-4 w-4 mr-2" />
                                )}
                                {isRepoActionBusy(repo.id)
                                  ? (repo.is_active ? 'Deactivating...' : 'Activating...')
                                  : (repo.is_active ? 'Deactivate' : 'Activate')}
                              </button>
                              

                              <button
                                onClick={() => handleDelete(repo)}
                                disabled={isRepoActionBusy(repo.id)}
                                className="flex items-center px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 dark:bg-red-500 dark:hover:bg-red-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-60 disabled:cursor-not-allowed"
                              >
                                {isRepoActionBusy(repo.id) ? (
                                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                ) : (
                                  <Trash2 className="h-4 w-4 mr-2" />
                                )}
                                {isRepoActionBusy(repo.id) ? 'Processing...' : 'Delete'}
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
                                className={`flex items-center px-4 py-2 text-sm font-medium rounded-lg transition-colors duration-200 shadow-sm ${
                                  hasChanges()
                                    ? 'text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600'
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
                          
                          {/* GitHub Action Config Tab - Only for GitHub repositories */}
                          {repo.provider === 'github' && (
                            <button
                              onClick={() => {
                                if (getTokenStatus(repo) === 'configured') {
                                  setRepoActiveTab(repo.id, 'github-action-config');
                                  // Auto-fetch GitHub Action config if not already loaded
                                  if (!githubActionConfigData[repo.id] && !loadingGithubActionConfig.has(repo.id)) {
                                    loadGithubActionConfig(repo.id);
                                  }
                                }
                              }}
                              disabled={getTokenStatus(repo) !== 'configured'}
                              className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                getTokenStatus(repo) !== 'configured'
                                  ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50'
                                  : getRepoActiveTab(repo.id) === 'github-action-config'
                                  ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                              }`}
                            >
                              <Server className="h-4 w-4 mr-2" />
                              <span>GitHub Action</span>
                            </button>
                          )}

                          {/* Azure Pipeline Config Tab - Only for Azure DevOps repositories */}
                          {repo.provider === 'azure_devops' && (
                            <button
                              onClick={() => {
                                if (getTokenStatus(repo) === 'configured') {
                                  setRepoActiveTab(repo.id, 'azure-pipeline-config');
                                  // Auto-fetch Azure Pipeline config if not already loaded
                                  if (!azurePipelineConfigData[repo.id] && !loadingAzurePipelineConfig.has(repo.id)) {
                                    loadAzurePipelineConfig(repo.id);
                                  }
                                }
                              }}
                              disabled={getTokenStatus(repo) !== 'configured'}
                              className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                getTokenStatus(repo) !== 'configured'
                                  ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50'
                                  : getRepoActiveTab(repo.id) === 'azure-pipeline-config'
                                  ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                              }`}
                            >
                              <Server className="h-4 w-4 mr-2" />
                              <span>Azure Pipeline</span>
                            </button>
                          )}

                          {/* Azure DevOps Agent Installation Tab - Only for Azure DevOps repositories */}
                          {repo.provider === 'azure_devops' && (
                            <button
                              onClick={() => {
                                if (getTokenStatus(repo) === 'configured') {
                                  setRepoActiveTab(repo.id, 'azure-agent-install');
                                }
                              }}
                              disabled={getTokenStatus(repo) !== 'configured'}
                              className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                getTokenStatus(repo) !== 'configured'
                                  ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50'
                                  : getRepoActiveTab(repo.id) === 'azure-agent-install'
                                  ? 'bg-white dark:bg-gray-700 text-green-600 dark:text-green-400 shadow-sm'
                                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                              }`}
                            >
                              <Download className="h-4 w-4 mr-2" />
                              <span>Agent Install</span>
                            </button>
                          )}

                          {/* GitHub Actions Runner Installation Tab - Only for GitHub repositories */}
                          {repo.provider === 'github' && (
                            <button
                              onClick={() => {
                                if (getTokenStatus(repo) === 'configured') {
                                  setRepoActiveTab(repo.id, 'github-runner-install');
                                }
                              }}
                              disabled={getTokenStatus(repo) !== 'configured'}
                              className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                                getTokenStatus(repo) !== 'configured'
                                  ? 'text-gray-400 dark:text-gray-500 cursor-not-allowed opacity-50'
                                  : getRepoActiveTab(repo.id) === 'github-runner-install'
                                  ? 'bg-white dark:bg-gray-700 text-green-600 dark:text-green-400 shadow-sm'
                                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
                              }`}
                            >
                              <Download className="h-4 w-4 mr-2" />
                              <span>Runner Install</span>
                            </button>
                          )}
                          
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
                              <div className={`rounded-lg p-6 border ${
                                repo.runner_status === 'running' 
                                  ? 'bg-gradient-to-r from-green-50 to-blue-50 dark:from-green-900/20 dark:to-blue-900/20 border-green-200 dark:border-green-700'
                                  : repo.runner_status === 'error' || repo.runner_status === 'stopped' || repo.runner_status === 'misconfigured'
                                  ? 'bg-gradient-to-r from-red-50 to-red-100 dark:from-red-900/20 dark:to-red-800/20 border-red-200 dark:border-red-700'
                                  : 'bg-gradient-to-r from-yellow-50 to-orange-50 dark:from-yellow-900/20 dark:to-orange-900/20 border-yellow-200 dark:border-yellow-700'
                              }`}>
                                <div className="flex items-center justify-between mb-4">
                                  <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                    <Activity className={`h-5 w-5 mr-2 ${
                                      repo.runner_status === 'running' 
                                        ? 'text-green-600 dark:text-green-400'
                                        : repo.runner_status === 'error' || repo.runner_status === 'stopped' || repo.runner_status === 'misconfigured'
                                        ? 'text-red-600 dark:text-red-400'
                                        : 'text-yellow-600 dark:text-yellow-400'
                                    }`} />
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
                                      <span className="font-medium">Last seen:</span> {formatTimestamp(repo.runner_last_seen)}
                                    </div>
                                  )}
                                  <div className="text-gray-600 dark:text-gray-400">
                                    <span className="font-medium">Type:</span> {repo.provider === 'github' ? 'GitHub Self-hosted Runner' : 'Azure DevOps Agent'}
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Health Check Actions */}
                            <div className="bg-white dark:bg-gray-800 rounded-lg p-6 border border-gray-200 dark:border-gray-700 shadow-sm">
                              <div className="flex items-center justify-between mb-4">
                                <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                  <Activity className="h-5 w-5 mr-2 text-green-600 dark:text-green-400" />
                                  Health & Status Checks
                                </h4>
                                <div className="flex items-center space-x-2">
                                  <button
                                    onClick={() => checkRunnerHealth(repo.id)}
                                    disabled={checkingHealth.has(repo.id)}
                                    className="flex items-center px-3 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    {checkingHealth.has(repo.id) ? (
                                      <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                                    ) : (
                                      <Activity className="h-4 w-4 mr-2" />
                                    )}
                                    Check Health
                                  </button>
                                </div>
                              </div>
                              
                              <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                                <div className="flex items-start">
                                  <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
                                  <div>
                                    <h6 className="font-medium text-blue-800 dark:text-blue-200 mb-2">Health Check Actions</h6>
                                    <div className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
                                      <p>• <strong>Refresh (Top-level):</strong> Comprehensive check of repository health, configuration, and services</p>
                                      <p>• <strong>Check Health:</strong> Validates tokens, API access, and repository connectivity</p>
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>

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
                                      className="flex items-center px-3 py-2 text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 dark:bg-gray-500 dark:hover:bg-gray-600 rounded-lg transition-colors duration-200 shadow-sm"
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
                                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">Base PR-Agent configuration from dashboard settings</p>
                                      <span className="inline-flex items-center px-2 py-1 rounded-full text-xs bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200">
                                        <Check className="h-3 w-3 mr-1" />
                                        Always Active
                                      </span>
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
                                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">Custom .pr_agent.toml in repository root</p>
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

                                    {/* Workflow Config */}
                                    <div className={`rounded-lg p-4 border ${
                                      repo.has_workflow_config 
                                        ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-700'
                                        : 'bg-gray-50 dark:bg-gray-700 border-gray-200 dark:border-gray-600'
                                    }`}>
                                      <div className="flex items-center mb-2">
                                        <Github className={`h-4 w-4 mr-2 ${
                                          repo.has_workflow_config 
                                            ? 'text-green-600 dark:text-green-400'
                                            : 'text-gray-400 dark:text-gray-500'
                                        }`} />
                                        <span className={`font-medium text-sm ${
                                          repo.has_workflow_config
                                            ? 'text-green-900 dark:text-green-200'
                                            : 'text-gray-600 dark:text-gray-400'
                                        }`}>GitHub Workflow</span>
                                      </div>
                                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">Environment variables from .github/workflows/pr_agent.yml</p>
                                      <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs ${
                                        repo.has_workflow_config
                                          ? 'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200'
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
                            {/* Header with Edit Button */}
                            <div className="flex items-center justify-between">
                              <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                <Key className="h-5 w-5 mr-2 text-blue-600 dark:text-blue-400" />
                                General & Authentication
                              </h4>
                              <div className="flex items-center space-x-2">
                                {!isEditingGeneral[repo.id] ? (
                                  <button
                                    onClick={() => startEditingGeneral(repo.id)}
                                    className="flex items-center px-3 py-2 text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 dark:bg-gray-500 dark:hover:bg-gray-600 rounded-lg transition-colors duration-200 shadow-sm"
                                  >
                                    <Edit className="h-4 w-4 mr-2" />
                                    Edit
                                  </button>
                                ) : (
                                  <>
                                    <button
                                      onClick={() => cancelEditingGeneral(repo.id)}
                                      className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-600 border border-gray-300 dark:border-gray-500 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-500 hover:border-gray-400 dark:hover:border-gray-400 transition-colors duration-200 shadow-sm"
                                    >
                                      <X className="h-4 w-4 mr-2" />
                                      Cancel
                                    </button>
                                    <button
                                      onClick={() => saveGeneralChanges(repo.id)}
                                      disabled={savingGeneral.has(repo.id)}
                                      className="flex items-center px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                      <Save className="h-4 w-4 mr-2" />
                                      {savingGeneral.has(repo.id) ? 'Saving...' : 'Save Changes'}
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>

                            {/* Repository Information */}
                            <div className="bg-gradient-to-r from-blue-50 to-cyan-50 dark:from-blue-900/20 dark:to-cyan-900/20 rounded-lg p-6 border border-blue-200 dark:border-blue-700">
                              <div className="flex items-center justify-between mb-4">
                                <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                  <Info className="h-5 w-5 mr-2 text-blue-600 dark:text-blue-400" />
                                  Repository Information
                                </h4>
                              </div>
                              
                              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                <div>
                                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Repository Name
                                  </label>
                                  {isEditingGeneral[repo.id] ? (
                                    <input
                                      type="text"
                                      value={editedGeneralData[repo.id]?.name || ''}
                                      onChange={(e) => setEditedGeneralData(prev => ({
                                        ...prev,
                                        [repo.id]: { ...prev[repo.id], name: e.target.value }
                                      }))}
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
                                  {isEditingGeneral[repo.id] ? (
                                    <select
                                      value={editedGeneralData[repo.id]?.provider || ''}
                                      onChange={(e) => setEditedGeneralData(prev => ({
                                        ...prev,
                                        [repo.id]: { ...prev[repo.id], provider: e.target.value }
                                      }))}
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
                                {isEditingGeneral[repo.id] ? (
                                  <input
                                    type="url"
                                    value={editedGeneralData[repo.id]?.url || ''}
                                    onChange={(e) => setEditedGeneralData(prev => ({
                                      ...prev,
                                      [repo.id]: { ...prev[repo.id], url: e.target.value }
                                    }))}
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
                                    {isEditingGeneral[repo.id] ? (
                                      <div className="relative">
                                        <input
                                          type={isTokenVisible(repo.id, 'github') ? 'text' : 'password'}
                                          value={editedGeneralData[repo.id]?.github_token || ''}
                                          onChange={(e) => setEditedGeneralData(prev => ({
                                            ...prev,
                                            [repo.id]: { ...prev[repo.id], github_token: e.target.value }
                                          }))}
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
                                    {isEditingGeneral[repo.id] ? (
                                      <div className="relative">
                                        <input
                                          type={isTokenVisible(repo.id, 'azure') ? 'text' : 'password'}
                                          value={editedGeneralData[repo.id]?.azure_pat || ''}
                                          onChange={(e) => setEditedGeneralData(prev => ({
                                            ...prev,
                                            [repo.id]: { ...prev[repo.id], azure_pat: e.target.value }
                                          }))}
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

                                {/* Token Testing Section */}
                                <div>
                                  <div className="flex items-center justify-between mb-3">
                                    <h5 className="text-sm font-medium text-gray-700 dark:text-gray-300">
                                      Token Verification
                                    </h5>
                                    <button
                                      onClick={() => testToken(repo.id)}
                                      disabled={testingTokens.has(repo.id) || (!repo.has_github_token && !repo.has_azure_pat)}
                                      className="flex items-center px-3 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                    >
                                      <RefreshCw className={`h-4 w-4 mr-2 ${testingTokens.has(repo.id) ? 'animate-spin' : ''}`} />
                                      {testingTokens.has(repo.id) ? 'Testing...' : 'Test Token'}
                                    </button>
                                  </div>

                                  {/* Token Test Results */}
                                  {tokenTestResults[repo.id] && (
                                    <div className={`rounded-lg border p-4 ${
                                      tokenTestResults[repo.id].success 
                                        ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                                        : 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                                    }`}>
                                      <div className="flex items-center justify-between mb-3">
                                        <h6 className={`font-medium text-sm flex items-center ${
                                          tokenTestResults[repo.id].success 
                                            ? 'text-green-800 dark:text-green-200'
                                            : 'text-red-800 dark:text-red-200'
                                        }`}>
                                          {tokenTestResults[repo.id].success ? (
                                            <CheckCircle className="h-4 w-4 mr-2" />
                                          ) : (
                                            <X className="h-4 w-4 mr-2" />
                                          )}
                                          Token Test Results
                                        </h6>
                                        <span className={`text-xs px-2 py-1 rounded-full ${
                                          tokenTestResults[repo.id].success 
                                            ? 'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200'
                                            : 'bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200'
                                        }`}>
                                          {tokenTestResults[repo.id].success ? 'PASSED' : 'FAILED'}
                                        </span>
                                      </div>

                                      {/* Test Results Details */}
                                      <div className={`text-sm space-y-2 ${
                                        tokenTestResults[repo.id].success 
                                          ? 'text-green-700 dark:text-green-300'
                                          : 'text-red-700 dark:text-red-300'
                                      }`}>
                                        {/* Permissions */}
                                        {tokenTestResults[repo.id].permissions && tokenTestResults[repo.id].permissions.length > 0 && (
                                          <div>
                                            <div className="font-medium mb-1">✅ Permissions Granted:</div>
                                            <ul className="list-none space-y-1 ml-2">
                                              {tokenTestResults[repo.id].permissions.map((permission, index) => (
                                                <li key={index} className="text-xs">{permission}</li>
                                              ))}
                                            </ul>
                                          </div>
                                        )}

                                        {/* Issues */}
                                        {tokenTestResults[repo.id].issues && tokenTestResults[repo.id].issues.length > 0 && (
                                          <div>
                                            <div className="font-medium mb-1">⚠️ Issues Found:</div>
                                            <ul className="list-none space-y-1 ml-2">
                                              {tokenTestResults[repo.id].issues.map((issue, index) => (
                                                <li key={index} className="text-xs">{issue}</li>
                                              ))}
                                            </ul>
                                          </div>
                                        )}

                                        {/* Error */}
                                        {tokenTestResults[repo.id].error && (
                                          <div>
                                            <div className="font-medium">Error:</div>
                                            <div className="text-xs mt-1">{tokenTestResults[repo.id].error}</div>
                                          </div>
                                        )}

                                        {/* Details */}
                                        {tokenTestResults[repo.id].details && (
                                          <div className="pt-2 border-t border-current/20">
                                            <div className="font-medium mb-1">Details:</div>
                                            <div className="text-xs space-y-1">
                                              {tokenTestResults[repo.id].details.username && (
                                                <div><strong>User:</strong> {tokenTestResults[repo.id].details.username}</div>
                                              )}
                                              {tokenTestResults[repo.id].details.organization && (
                                                <div><strong>Organization:</strong> {tokenTestResults[repo.id].details.organization}</div>
                                              )}
                                              {tokenTestResults[repo.id].details.project && (
                                                <div><strong>Project:</strong> {tokenTestResults[repo.id].details.project}</div>
                                              )}
                                              {tokenTestResults[repo.id].details.repository && (
                                                <div><strong>Repository:</strong> {tokenTestResults[repo.id].details.repository}</div>
                                              )}
                                              {tokenTestResults[repo.id].details.rate_limit_remaining && (
                                                <div><strong>Rate Limit Remaining:</strong> {tokenTestResults[repo.id].details.rate_limit_remaining}</div>
                                              )}
                                              {tokenTestResults[repo.id].tested_at && (
                                                <div><strong>Tested:</strong> {new Date(tokenTestResults[repo.id].tested_at).toLocaleString()}</div>
                                              )}
                                            </div>
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  )}

                                  {!tokenTestResults[repo.id] && !testingTokens.has(repo.id) && (
                                    <div className="text-xs text-gray-500 dark:text-gray-400">
                                      Click "Test Token" to verify your {repo.provider === 'github' ? 'GitHub' : 'Azure DevOps'} token permissions and connectivity.
                                    </div>
                                  )}
                                </div>
                              </div>
                            </div>
                          </div>
                        )}

                        {/* GitHub Action Config Tab */}
                        {getRepoActiveTab(repo.id) === 'github-action-config' && (
                          <div className="space-y-6 tab-enter">
                            <div className="space-y-6">
                              <div className="flex items-center justify-between">
                                <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                  <Server className="h-5 w-5 mr-2 text-blue-600 dark:text-blue-400" />
                                  GitHub Action Configuration
                                </h4>
                                <div className="flex items-center space-x-2">
                                  {/* PR Status Display */}
                                  {githubActionConfigData[repo.id]?.has_pending_pr && (
                                    <div className="flex items-center bg-yellow-50 dark:bg-yellow-900/20 text-yellow-800 dark:text-yellow-200 px-3 py-1 rounded-lg border border-yellow-200 dark:border-yellow-700 mr-2">
                                      <GitBranch className="h-4 w-4 mr-1" />
                                      <span className="text-sm font-medium">
                                        {checkingGithubActionPrStatus.has(repo.id) ? (
                                          <>
                                            <RefreshCw className="h-3 w-3 animate-spin inline mr-1" />
                                            Checking PR #{githubActionConfigData[repo.id].pr_number}...
                                          </>
                                        ) : (
                                          <>
                                            PR #{githubActionConfigData[repo.id].pr_number} Pending
                                          </>
                                        )}
                                      </span>
                                      <a 
                                        href={githubActionConfigData[repo.id].pr_url} 
                                        target="_blank" 
                                        rel="noopener noreferrer"
                                        className="ml-1 hover:text-yellow-900 dark:hover:text-yellow-100"
                                      >
                                        <ExternalLink className="h-3 w-3" />
                                      </a>
                                      <button
                                        onClick={() => checkGithubActionConfigPRStatus(repo.id)}
                                        disabled={checkingGithubActionPrStatus.has(repo.id)}
                                        className="ml-2 hover:text-yellow-900 dark:hover:text-yellow-100 disabled:opacity-50 disabled:cursor-not-allowed"
                                        title={checkingGithubActionPrStatus.has(repo.id) ? "Checking..." : "Check PR status"}
                                      >
                                        <RefreshCw className={`h-3 w-3 ${checkingGithubActionPrStatus.has(repo.id) ? 'animate-spin' : ''}`} />
                                      </button>
                                    </div>
                                  )}
                                  
                                  <button
                                    onClick={() => loadGithubActionConfig(repo.id, true)}
                                    disabled={loadingGithubActionConfig.has(repo.id)}
                                    className="flex items-center px-3 py-2 text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 dark:bg-gray-500 dark:hover:bg-gray-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    <RefreshCw className={`h-4 w-4 mr-2 ${loadingGithubActionConfig.has(repo.id) ? 'animate-spin' : ''}`} />
                                    {loadingGithubActionConfig.has(repo.id) ? 'Loading...' : 'Refresh'}
                                  </button>
                                  <button
                                    onClick={() => openGithubActionConfigEditor(repo.id)}
                                    className="flex items-center px-3 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 rounded-lg transition-colors duration-200 shadow-sm"
                                  >
                                    <Edit className="h-4 w-4 mr-2" />
                                    {githubActionConfigData[repo.id]?.exists ? 'Edit' : 'Create'}
                                  </button>
                                </div>
                              </div>
                              
                              {/* Loading State */}
                              {loadingGithubActionConfig.has(repo.id) ? (
                                <div className="flex items-center justify-center py-8">
                                  <RefreshCw className="h-6 w-6 text-blue-600 dark:text-blue-400 animate-spin mr-3" />
                                  <span className="text-gray-600 dark:text-gray-400">Loading GitHub Action configuration...</span>
                                </div>
                              ) : githubActionConfigData[repo.id]?.error ? (
                                <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                                  <div className="flex items-center">
                                    <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
                                    <div>
                                      <h5 className="font-medium text-red-800 dark:text-red-200">Error Loading Configuration</h5>
                                      <p className="text-red-700 dark:text-red-300 text-sm mt-1">{githubActionConfigData[repo.id].error}</p>
                                    </div>
                                  </div>
                                </div>
                              ) : githubActionConfigData[repo.id]?.exists ? (
                                /* Configuration Exists */
                                <div className="bg-white dark:bg-gray-800 rounded-lg border border-green-100 dark:border-green-700 overflow-hidden">
                                  <div className="bg-green-50 dark:bg-green-900/30 px-4 py-3 border-b border-green-100 dark:border-green-700 flex items-center justify-between">
                                    <h5 className="font-medium text-green-900 dark:text-green-200 text-sm flex items-center">
                                      <Check className="h-4 w-4 mr-2" />
                                      .github/pr_agent.yml
                                    </h5>
                                    {githubActionConfigData[repo.id]?.last_fetched && (
                                      <span className="text-xs text-green-700 dark:text-green-300">
                                        Updated: {formatTimestamp(githubActionConfigData[repo.id].last_fetched)}
                                      </span>
                                    )}
                                  </div>
                                  <div className="px-4 py-3">
                                    {githubActionConfigData[repo.id]?.env_vars && Object.keys(githubActionConfigData[repo.id].env_vars).length > 0 ? (
                                      <div className="space-y-4">
                                        <div className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                                          <strong>Environment Variables:</strong>
                                        </div>
                                        <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-4 border border-gray-200 dark:border-gray-600">
                                          <div className="font-mono text-sm font-semibold text-gray-900 dark:text-white mb-3 pb-2 border-b border-gray-200 dark:border-gray-600">
                                            [env]
                                          </div>
                                          <div className="space-y-2">
                                            {Object.entries(githubActionConfigData[repo.id].env_vars).map(([key, value]) => (
                                              <div key={key} className="flex items-start justify-between">
                                                <div className="font-mono text-xs text-gray-700 dark:text-gray-300 font-medium">
                                                  {key}
                                                </div>
                                                <div className="font-mono text-xs text-gray-600 dark:text-gray-400 ml-3 text-right max-w-xs">
                                                  {value && value !== key
                                                    ? String(value).length > 50
                                                      ? `${String(value).substring(0, 50)}...`
                                                      : String(value)
                                                    : '(set)'
                                                  }
                                                </div>
                                              </div>
                                            ))}
                                          </div>
                                        </div>
                                      </div>
                                    ) : (
                                      <div className="text-center py-4">
                                        <p className="text-gray-500 dark:text-gray-400 text-sm">
                                          No environment variables found in configuration
                                        </p>
                                      </div>
                                    )}
                                  </div>
                                </div>
                              ) : githubActionConfigData[repo.id] !== undefined ? (
                                /* No Configuration */
                                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-lg p-6 border border-blue-200 dark:border-blue-700">
                                  <div className="flex items-center mb-4">
                                    <Server className="h-6 w-6 text-blue-600 dark:text-blue-400 mr-3" />
                                    <div>
                                      <h5 className="font-medium text-blue-800 dark:text-blue-200">No Configuration Found</h5>
                                      <p className="text-blue-700 dark:text-blue-300 text-sm">
                                        Create a GitHub Action workflow to automate PR-Agent tasks
                                      </p>
                                    </div>
                                  </div>
                                  
                                  <div className="bg-blue-100 dark:bg-blue-800/30 rounded-lg p-4 mt-4">
                                    <div className="text-sm text-blue-800 dark:text-blue-200 space-y-2">
                                      <p className="font-medium">What this will create:</p>
                                      <ul className="space-y-1 ml-4">
                                        <li className="flex items-center">
                                          <Check className="h-3 w-3 mr-2 text-blue-600 dark:text-blue-400" />
                                          GitHub Actions workflow file at <code className="bg-blue-200 dark:bg-blue-700 px-1 rounded">.github/pr_agent.yml</code>
                                        </li>
                                        <li className="flex items-center">
                                          <Check className="h-3 w-3 mr-2 text-blue-600 dark:text-blue-400" />
                                          Configurable environment variables for PR-Agent
                                        </li>
                                        <li className="flex items-center">
                                          <Check className="h-3 w-3 mr-2 text-blue-600 dark:text-blue-400" />
                                          Support for GitHub secrets and context variables
                                        </li>
                                        <li className="flex items-center">
                                          <Check className="h-3 w-3 mr-2 text-blue-600 dark:text-blue-400" />
                                          Automated PR reviews, descriptions, and improvements
                                        </li>
                                      </ul>
                                    </div>
                                  </div>
                                </div>
                              ) : (
                                /* Default - Not Loaded Yet */
                                <div className="text-center py-8">
                                  <Server className="mx-auto h-12 w-12 text-gray-400 dark:text-gray-500 mb-4" />
                                  <h5 className="text-lg font-medium text-gray-900 dark:text-white mb-2">GitHub Action Configuration</h5>
                                  <p className="text-gray-500 dark:text-gray-400 mb-4">
                                    Click "Refresh" to check for GitHub Action configuration in your repository.
                                  </p>
                                </div>
                              )}
                            </div>
                          </div>
                        )}

                        {/* Best Practices Tab */}
                        {getRepoActiveTab(repo.id) === 'best-practices' && (
                          <div className="space-y-6 tab-enter">
                            <div className="space-y-6">
                              <div className="flex items-center justify-between">
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
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 dark:bg-gray-500 dark:hover:bg-gray-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
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
                                        className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-600 border border-gray-300 dark:border-gray-500 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-500 hover:border-gray-400 dark:hover:border-gray-400 transition-colors duration-200 shadow-sm"
                                      >
                                        <X className="h-4 w-4 mr-2" />
                                        Cancel
                                      </button>
                                      <button
                                        onClick={() => saveBestPractices(repo.id)}
                                        disabled={savingBestPractices[repo.id] || !editedBestPracticesContent[repo.id]?.trim()}
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
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
                                          Updated: {formatTimestamp(bestPracticesData[repo.id].last_fetched)}
                                        </span>
                                      )}
                                    </div>
                                    <div className="px-4 py-3">
                                      <div 
                                        className="prose prose-sm max-w-none best-practices-markdown"
                                        dangerouslySetInnerHTML={{
                                          __html: DOMPurify.sanitize(bestPracticesData[repo.id].content_html || 'No content available')
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
                        </div>
                        
                        {/* PR-Agent Config Tab */}
                        {getRepoActiveTab(repo.id) === 'pr-agent-config' && (
                          <div className="space-y-6 tab-enter">
                            <div className="flex items-center justify-between">
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
                                  className="flex items-center px-3 py-2 text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 dark:bg-gray-500 dark:hover:bg-gray-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  <RefreshCw className={`h-4 w-4 mr-2 ${loadingPrAgentConfig.has(repo.id) ? 'animate-spin' : ''}`} />
                                  {loadingPrAgentConfig.has(repo.id) ? 'Loading...' : 'Refresh'}
                                </button>
                                <button
                                  onClick={() => openPrAgentConfigEditor(repo.id)}
                                  className="flex items-center px-3 py-2 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600 rounded-lg transition-colors duration-200 shadow-sm"
                                >
                                  <Edit className="h-4 w-4 mr-2" />
                                  {prAgentConfigData[repo.id]?.has_config ? 'Edit' : 'Create'}
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
                                      Updated: {formatTimestamp(prAgentConfigData[repo.id].last_fetched)}
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
                        )}

                        {/* Azure Pipeline Config Tab */}
                        {getRepoActiveTab(repo.id) === 'azure-pipeline-config' && (
                          <div className="space-y-6 tab-enter">
                            {/* ── Panel A: Pipeline YAML Status ── */}
                            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
                              <div className="p-5 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                                <h4 className="text-base font-semibold text-gray-900 dark:text-white flex items-center">
                                  <FileText className="h-5 w-5 mr-2 text-blue-600 dark:text-blue-400" />
                                  Shared Pipeline YAML
                                </h4>
                                <div className="flex items-center space-x-2">
                                  <button
                                    onClick={() => { loadSyncStatus(repo.id); loadPolicies(repo.id); }}
                                    disabled={loadingSyncStatus.has(repo.id)}
                                    className="flex items-center px-3 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
                                  >
                                    <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loadingSyncStatus.has(repo.id) ? 'animate-spin' : ''}`} />
                                    Refresh
                                  </button>
                                  {syncStatusData[repo.id]?.pipelines_url && (
                                    <a href={syncStatusData[repo.id].pipelines_url} target="_blank" rel="noopener noreferrer"
                                      className="flex items-center px-3 py-1.5 text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
                                      onClick={(e) => e.stopPropagation()}>
                                      <ExternalLink className="h-3.5 w-3.5 mr-1" /> View in Azure DevOps
                                    </a>
                                  )}
                                  {syncStatusData[repo.id]?.pipeline_definitions?.[0]?.url && (
                                    <a href={syncStatusData[repo.id].pipeline_definitions[0].url} target="_blank" rel="noopener noreferrer"
                                      className="flex items-center px-3 py-1.5 text-xs font-medium text-purple-600 dark:text-purple-400 hover:underline"
                                      onClick={(e) => e.stopPropagation()}>
                                      <ExternalLink className="h-3.5 w-3.5 mr-1" /> Open Shared Pipeline
                                    </a>
                                  )}
                                </div>
                              </div>
                              <div className="p-5">
                                {loadingSyncStatus.has(repo.id) && !syncStatusData[repo.id] ? (
                                  <div className="flex items-center justify-center py-6">
                                    <RefreshCw className="h-5 w-5 animate-spin mr-2 text-blue-500" />
                                    <span className="text-sm text-gray-500">Checking sync status...</span>
                                  </div>
                                ) : syncStatusData[repo.id]?.error ? (
                                  <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
                                    <div className="flex items-start">
                                      <AlertCircle className="h-5 w-5 text-red-500 mr-2 mt-0.5 flex-shrink-0" />
                                      <p className="text-sm text-red-700 dark:text-red-300">{syncStatusData[repo.id].error}</p>
                                    </div>
                                  </div>
                                ) : syncStatusData[repo.id] ? (() => {
                                  const ss = syncStatusData[repo.id];
                                  const azureInfo = parseAzureDevOpsUrl(repo.url);
                                  const checksUrl = `${azureInfo.baseUrl}/${azureInfo.project}/_settings/repositories?repo=${encodeURIComponent(azureInfo.repository)}&_a=policies`;
                                  const verification = azureSetupVerification[repo.id];
                                  const variablesStatus = ss.variables_status || {};
                                  const variableDrift = !!variablesStatus.missing_any;
                                  const yamlDrift = ss.sync_status === 'missing' || ss.sync_status === 'outdated';
                                  const matchingPolicyCount = getMatchingEnabledPolicyCount(
                                    policiesData[repo.id]?.policies || [],
                                    ss.pipeline_definitions || []
                                  );
                                  const enabledPolicyCount = (policiesData[repo.id]?.policies || []).filter((p) => p.is_enabled !== false).length;
                                  const isBusy =
                                    pushingYaml.has(repo.id) ||
                                    syncingPipelineVariables.has(repo.id) ||
                                    autoFixingAzureSetup.has(repo.id) ||
                                    verifyingAzureSetup.has(repo.id);
                                  const missingSummary = (variablesStatus.pipelines || [])
                                    .filter((p) => p.has_missing_required)
                                    .map((p) => {
                                      const missPlain = (p.missing_plain_keys || []).length;
                                      const invalidPlain = (p.invalid_plain_keys || []).length;
                                      const missSecret = (p.missing_secret_keys || []).length;
                                      const parts = [];
                                      if (missPlain) parts.push(`${missPlain} plain`);
                                      if (invalidPlain) parts.push(`${invalidPlain} plain-empty`);
                                      if (missSecret) parts.push(`${missSecret} secret`);
                                      if (p.variables_fetch_error) parts.push('fetch error');
                                      return `${p.pipeline_name || p.pipeline_id}: ${parts.join(', ')}`;
                                    });
                                  const uiIssues = [];
                                  if (!ss.pipeline_exists) uiIssues.push('Pipeline definition is missing.');
                                  if (yamlDrift) uiIssues.push('Pipeline YAML is missing or outdated.');
                                  if (variableDrift) uiIssues.push('Required pipeline variables/secrets are missing or invalid.');
                                  if (matchingPolicyCount === 0) {
                                    if (enabledPolicyCount > 0) {
                                      uiIssues.push('Enabled check policies exist, but none target this PR-Agent pipeline.');
                                    } else {
                                      uiIssues.push('No enabled build validation check policy is configured.');
                                    }
                                  }
                                  return (
                                    <div className="space-y-4">
                                      <div className="bg-slate-50 dark:bg-slate-900/30 border border-slate-200 dark:border-slate-700 rounded-lg p-3">
                                        <div className="flex items-center justify-between mb-2">
                                          <p className="text-sm font-medium text-slate-800 dark:text-slate-100">
                                            Setup Readiness Checklist
                                          </p>
                                          {verification?.checked_at && (
                                            <span className="text-xs text-slate-500 dark:text-slate-400">
                                              Last checked: {formatLastChecked(verification.checked_at)}
                                            </span>
                                          )}
                                        </div>
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs">
                                          <div className="flex items-center">
                                            {ss.pipeline_exists ? <CheckCircle className="h-3.5 w-3.5 text-green-600 mr-1.5" /> : <X className="h-3.5 w-3.5 text-red-500 mr-1.5" />}
                                            <span className={ss.pipeline_exists ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}>Pipeline definition exists</span>
                                          </div>
                                          <div className="flex items-center">
                                            {ss.sync_status === 'up_to_date' ? <CheckCircle className="h-3.5 w-3.5 text-green-600 mr-1.5" /> : <X className="h-3.5 w-3.5 text-red-500 mr-1.5" />}
                                            <span className={ss.sync_status === 'up_to_date' ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}>Pipeline YAML up to date</span>
                                          </div>
                                          <div className="flex items-center">
                                            {!variableDrift ? <CheckCircle className="h-3.5 w-3.5 text-green-600 mr-1.5" /> : <X className="h-3.5 w-3.5 text-red-500 mr-1.5" />}
                                            <span className={!variableDrift ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}>Variables/secrets synchronized</span>
                                          </div>
                                          <div className="flex items-center">
                                            {matchingPolicyCount > 0
                                              ? <CheckCircle className="h-3.5 w-3.5 text-green-600 mr-1.5" />
                                              : <X className="h-3.5 w-3.5 text-red-500 mr-1.5" />}
                                            <span className={matchingPolicyCount > 0 ? 'text-green-700 dark:text-green-300' : 'text-red-700 dark:text-red-300'}>
                                              Build validation check policy configured
                                            </span>
                                          </div>
                                        </div>
                                      </div>
                                      {uiIssues.length > 0 && (
                                        <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-3">
                                          <div className="flex items-start justify-between gap-3">
                                            <div>
                                              <p className="text-sm font-medium text-amber-800 dark:text-amber-200 mb-1">Issues detected</p>
                                              <ul className="text-xs text-amber-800 dark:text-amber-200 space-y-1 list-disc pl-4">
                                                {uiIssues.map((issue, idx) => (
                                                  <li key={idx}>{issue}</li>
                                                ))}
                                              </ul>
                                            </div>
                                            <button
                                              onClick={() => autoFixAzurePipelineSetup(repo)}
                                              disabled={isBusy}
                                              className="shrink-0 flex items-center px-3 py-2 text-xs font-medium text-white bg-amber-600 hover:bg-amber-700 rounded-md transition-colors disabled:opacity-50"
                                            >
                                              {autoFixingAzureSetup.has(repo.id)
                                                ? <><RefreshCw className="h-3.5 w-3.5 mr-1.5 animate-spin" /> Fixing...</>
                                                : <><RefreshCw className="h-3.5 w-3.5 mr-1.5" /> Fix Issues</>}
                                            </button>
                                          </div>
                                        </div>
                                      )}
                                      <div className="text-xs text-gray-600 dark:text-gray-400 bg-gray-50 dark:bg-gray-900/30 border border-gray-200 dark:border-gray-700 rounded-md px-3 py-2">
                                        {ss.using_shared_pipeline_repo
                                          ? `Using shared pipeline repository: ${ss.shared_pipeline_repo || 'pr-agent-pipelines'}`
                                          : 'Using repository-local pipeline YAML.'}
                                      </div>
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center space-x-3">
                                          {ss.sync_status === 'up_to_date' && (
                                            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
                                              <CheckCircle className="h-4 w-4 mr-1.5" /> Up to date
                                            </span>
                                          )}
                                          {ss.sync_status === 'outdated' && (
                                            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                                              <AlertCircle className="h-4 w-4 mr-1.5" /> Outdated ({ss.diff_lines_changed} lines differ)
                                            </span>
                                          )}
                                          {ss.sync_status === 'missing' && (
                                            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300">
                                              <X className="h-4 w-4 mr-1.5" /> Missing
                                            </span>
                                          )}
                                          {ss.pipeline_exists && (
                                            <span className="text-xs text-gray-500 dark:text-gray-400">Pipeline definition exists</span>
                                          )}
                                          {variableDrift ? (
                                            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300">
                                              <AlertCircle className="h-4 w-4 mr-1.5" /> Variables/Secrets Missing
                                            </span>
                                          ) : (
                                            <span className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300">
                                              <CheckCircle className="h-4 w-4 mr-1.5" /> Variables/Secrets Synced
                                            </span>
                                          )}
                                        </div>
                                        <div />
                                      </div>
                                      {ss.remote_content && (
                                        <details className="bg-gray-50 dark:bg-gray-900/30 rounded-lg border border-gray-200 dark:border-gray-700">
                                          <summary className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 rounded-t-lg">
                                            View current shared YAML
                                          </summary>
                                          <div className="px-4 py-3 overflow-x-auto">
                                            <pre className="text-xs font-mono text-gray-600 dark:text-gray-400 whitespace-pre-wrap max-h-96 overflow-y-auto">{ss.remote_content}</pre>
                                          </div>
                                        </details>
                                      )}
                                      {ss.sync_status === 'outdated' && ss.remote_content && (
                                        <details className="bg-gray-50 dark:bg-gray-900/30 rounded-lg border border-gray-200 dark:border-gray-700">
                                          <summary className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-800 rounded-t-lg">
                                            View canonical template
                                          </summary>
                                          <div className="px-4 py-3 overflow-x-auto">
                                            <pre className="text-xs font-mono text-gray-600 dark:text-gray-400 whitespace-pre-wrap max-h-96 overflow-y-auto">{ss.canonical_content}</pre>
                                          </div>
                                        </details>
                                      )}
                                      {ss.sync_status === 'missing' && ss.canonical_content && (
                                        <details className="bg-blue-50 dark:bg-blue-900/10 rounded-lg border border-blue-200 dark:border-blue-800">
                                          <summary className="px-4 py-2 text-sm font-medium text-blue-700 dark:text-blue-300 cursor-pointer hover:bg-blue-100 dark:hover:bg-blue-900/20 rounded-t-lg">
                                            Preview template that will be deployed
                                          </summary>
                                          <div className="px-4 py-3 overflow-x-auto">
                                            <pre className="text-xs font-mono text-gray-600 dark:text-gray-400 whitespace-pre-wrap max-h-96 overflow-y-auto">{ss.canonical_content}</pre>
                                          </div>
                                        </details>
                                      )}
                                      {!!missingSummary.length && (
                                        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
                                          <p className="text-sm font-medium text-red-700 dark:text-red-300 mb-1">
                                            Missing required pipeline variables/secrets were detected:
                                          </p>
                                          <ul className="text-xs text-red-700 dark:text-red-300 space-y-1 list-disc pl-4">
                                            {missingSummary.map((item, idx) => (
                                              <li key={idx}>{item}</li>
                                            ))}
                                          </ul>
                                        </div>
                                      )}
                                    </div>
                                  );
                                })() : (
                                  <div className="text-center py-6">
                                    <Server className="mx-auto h-10 w-10 text-gray-400 dark:text-gray-500 mb-3" />
                                    <p className="text-sm text-gray-500 dark:text-gray-400">Click Refresh to check pipeline sync status.</p>
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* ── Panel B: Build Validation Policies ── */}
                            <div className="bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded-lg shadow-sm">
                              <div className="p-5 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
                                <h4 className="text-base font-semibold text-gray-900 dark:text-white flex items-center">
                                  <Shield className="h-5 w-5 mr-2 text-purple-600 dark:text-purple-400" />
                                  Build Validation Policies (Checks)
                                </h4>
                                <div className="flex items-center space-x-2">
                                  <button
                                    onClick={() => loadPolicies(repo.id)}
                                    disabled={loadingPolicies.has(repo.id)}
                                    className="flex items-center px-3 py-1.5 text-xs font-medium text-gray-600 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 rounded-md hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors disabled:opacity-50"
                                  >
                                    <RefreshCw className={`h-3.5 w-3.5 mr-1.5 ${loadingPolicies.has(repo.id) ? 'animate-spin' : ''}`} />
                                    Refresh
                                  </button>
                                  <a
                                    href={`${parseAzureDevOpsUrl(repo.url).baseUrl}/${parseAzureDevOpsUrl(repo.url).project}/_settings/repositories?repo=${encodeURIComponent(parseAzureDevOpsUrl(repo.url).repository)}&_a=policies`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center px-3 py-1.5 text-xs font-medium text-purple-600 dark:text-purple-400 hover:underline"
                                  >
                                    <ExternalLink className="h-3.5 w-3.5 mr-1.5" />
                                    Open Checks Page
                                  </a>
                                </div>
                              </div>
                              <div className="p-5">
                                {loadingPolicies.has(repo.id) && !policiesData[repo.id] ? (
                                  <div className="flex items-center justify-center py-4">
                                    <RefreshCw className="h-5 w-5 animate-spin mr-2 text-purple-500" />
                                    <span className="text-sm text-gray-500">Loading policies...</span>
                                  </div>
                                ) : policiesData[repo.id]?.error ? (
                                  <p className="text-sm text-red-600 dark:text-red-400">{policiesData[repo.id].error}</p>
                                ) : (
                                  <div className="space-y-4">
                                    {(policiesData[repo.id]?.policies || []).length > 0 ? (
                                      <div className="divide-y divide-gray-100 dark:divide-gray-700">
                                        {policiesData[repo.id].policies.map((pol) => (
                                          <div key={pol.policy_id} className="flex items-center justify-between py-3">
                                            <div className="flex items-center space-x-3">
                                              <GitBranch className="h-4 w-4 text-gray-400" />
                                              <span className="text-sm font-medium text-gray-900 dark:text-white">{pol.branch || 'all branches'}</span>
                                              <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                                                pol.is_blocking
                                                  ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300'
                                                  : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                                              }`}>
                                                {pol.is_blocking ? 'Required' : 'Optional'}
                                              </span>
                                              {!pol.is_enabled && (
                                                <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400">Disabled</span>
                                              )}
                                            </div>
                                            <button
                                              onClick={() => handleDeletePolicy(repo.id, pol.policy_id)}
                                              disabled={deletingPolicy.has(pol.policy_id)}
                                              className="text-red-500 hover:text-red-700 dark:hover:text-red-400 text-xs disabled:opacity-50"
                                            >
                                              {deletingPolicy.has(pol.policy_id) ? 'Removing...' : 'Remove'}
                                            </button>
                                          </div>
                                        ))}
                                      </div>
                                    ) : (
                                      <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-3">No build validation policies configured.</p>
                                    )}

                                    {/* Add Policy form */}
                                    {showAddPolicy[repo.id] ? (
                                      <div className="bg-gray-50 dark:bg-gray-900/30 rounded-lg p-4 space-y-3 border border-gray-200 dark:border-gray-700">
                                        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                          <div>
                                            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Branch</label>
                                            <SearchableSelect
                                              options={(branchesData[repo.id]?.branches || []).map(b => ({ value: b.name, label: `${b.name}${b.is_default ? ' (default)' : ''}` }))}
                                              value={(newPolicyForm[repo.id] || {}).branch || ''}
                                              onChange={(val) => setNewPolicyForm(prev => ({ ...prev, [repo.id]: { ...prev[repo.id], branch: val } }))}
                                              placeholder="Select branch..."
                                            />
                                          </div>
                                          <div>
                                            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Pipeline</label>
                                            <SearchableSelect
                                              options={(syncStatusData[repo.id]?.pipeline_definitions || []).map(p => ({ value: p.id, label: p.name }))}
                                              value={(newPolicyForm[repo.id] || {}).pipeline_definition_id || ''}
                                              onChange={(val) => setNewPolicyForm(prev => ({ ...prev, [repo.id]: { ...prev[repo.id], pipeline_definition_id: val } }))}
                                              placeholder="Select pipeline..."
                                            />
                                          </div>
                                          <div>
                                            <label className="block text-xs font-medium text-gray-600 dark:text-gray-400 mb-1">Type</label>
                                            <div className="flex items-center h-[42px] space-x-3">
                                              <button
                                                onClick={() => setNewPolicyForm(prev => ({ ...prev, [repo.id]: { ...prev[repo.id], is_blocking: false } }))}
                                                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                                                  !(newPolicyForm[repo.id] || {}).is_blocking
                                                    ? 'bg-blue-600 text-white'
                                                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                                                }`}
                                              >Optional</button>
                                              <button
                                                onClick={() => setNewPolicyForm(prev => ({ ...prev, [repo.id]: { ...prev[repo.id], is_blocking: true } }))}
                                                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${
                                                  (newPolicyForm[repo.id] || {}).is_blocking
                                                    ? 'bg-red-600 text-white'
                                                    : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-300'
                                                }`}
                                              >Required</button>
                                            </div>
                                          </div>
                                        </div>
                                        <div className="flex items-center justify-end space-x-2">
                                          <button
                                            onClick={() => { setShowAddPolicy(prev => ({ ...prev, [repo.id]: false })); setNewPolicyForm(prev => ({ ...prev, [repo.id]: {} })); }}
                                            className="px-3 py-1.5 text-xs text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-white"
                                          >Cancel</button>
                                          <button
                                            onClick={() => handleAddPolicy(repo.id)}
                                            disabled={savingPolicy.has(repo.id)}
                                            className="flex items-center px-4 py-1.5 text-xs font-medium text-white bg-purple-600 hover:bg-purple-700 rounded-md transition-colors disabled:opacity-50"
                                          >
                                            {savingPolicy.has(repo.id) ? <><RefreshCw className="h-3 w-3 mr-1 animate-spin" /> Saving...</> : <><Plus className="h-3 w-3 mr-1" /> Add Build Validation</>}
                                          </button>
                                        </div>
                                      </div>
                                    ) : (
                                      <button
                                        onClick={() => {
                                          setShowAddPolicy(prev => ({ ...prev, [repo.id]: true }));
                                          if (!branchesData[repo.id]) loadBranches(repo.id).then(data => {
                                            if (data?.default_branch) setNewPolicyForm(prev => ({ ...prev, [repo.id]: { ...prev[repo.id], branch: data.default_branch } }));
                                          });
                                          if (!syncStatusData[repo.id]) loadSyncStatus(repo.id);
                                        }}
                                        className="flex items-center px-3 py-2 text-sm font-medium text-purple-600 dark:text-purple-400 hover:bg-purple-50 dark:hover:bg-purple-900/20 rounded-lg transition-colors"
                                      >
                                        <Plus className="h-4 w-4 mr-1.5" /> Add Check
                                      </button>
                                    )}
                                  </div>
                                )}
                              </div>
                            </div>

                            {/* Legacy PR status section */}
                            {azurePipelineConfigData[repo.id]?.has_pending_pr && (
                              <div className="bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded-lg p-4">
                                <div className="flex items-center justify-between">
                                  <span className="text-sm text-orange-700 dark:text-orange-300">
                                    Pending config PR #{azurePipelineConfigData[repo.id].pr_number}
                                  </span>
                                  <div className="flex items-center space-x-2">
                                    <button
                                      onClick={() => checkAzurePipelineConfigPRStatus(repo.id)}
                                      disabled={checkingAzurePipelinePrStatus.has(repo.id)}
                                      className="text-xs text-orange-600 hover:text-orange-800 disabled:opacity-50"
                                    >
                                      {checkingAzurePipelinePrStatus.has(repo.id) ? 'Checking...' : 'Check Status'}
                                    </button>
                                    <a href={azurePipelineConfigData[repo.id].pr_url} target="_blank" rel="noopener noreferrer"
                                      className="text-xs text-blue-600 hover:underline">View PR</a>
                                  </div>
                                </div>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Azure DevOps Agent Installation Tab */}
                        {getRepoActiveTab(repo.id) === 'azure-agent-install' && (
                          <div className="space-y-6 tab-enter">
                            {(() => {
                              const azureInfo = parseAzureDevOpsUrl(repo.url);
                              const conn = actionRunnerConnections.find((c) => c.id === repo.action_runner_connection_id);
                              const hasCloudRunner = !!(conn && conn.gcp_instance_name && conn.gcp_zone);
                              if (!hasCloudRunner) return null;

                              const progress = provisionProgressByConnection[conn.id] || {};
                              const agent = progress.azure_agent || {};
                              const vmRunning = !!progress.vm_running;
                              let statusLabel = 'Cloud VM provisioned';
                              let statusClass = 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300';
                              if (agent.online) {
                                statusLabel = 'Cloud self-hosted runner is online';
                                statusClass = 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300';
                              } else if (agent.found) {
                                statusLabel = 'Runner registered, waiting to come online';
                                statusClass = 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300';
                              } else if (vmRunning) {
                                statusLabel = 'VM running, agent setup in progress';
                                statusClass = 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300';
                              }

                              const agentPoolsUrl = `${azureInfo.baseUrl}/_settings/agentpools`;
                              const checksUrl = `${azureInfo.baseUrl}/${azureInfo.project}/_settings/repositories?repo=${encodeURIComponent(azureInfo.repository)}&_a=policies`;

                              return (
                                <div className="space-y-4">
                                  <div className="flex items-center justify-between">
                                    <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                      <Cloud className="h-5 w-5 mr-2 text-green-600 dark:text-green-400" />
                                      Cloud Runner Status
                                    </h4>
                                    <div className="flex items-center space-x-2">
                                      <a
                                        href={agentPoolsUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors duration-200 shadow-sm"
                                      >
                                        <ExternalLink className="h-4 w-4 mr-2" />
                                        Agent Pools
                                      </a>
                                      <a
                                        href={checksUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-purple-600 hover:bg-purple-700 dark:bg-purple-500 dark:hover:bg-purple-600 rounded-lg transition-colors duration-200 shadow-sm"
                                      >
                                        <ExternalLink className="h-4 w-4 mr-2" />
                                        Checks Page
                                      </a>
                                    </div>
                                  </div>

                                  <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4 space-y-3">
                                    <span className={`inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium ${statusClass}`}>
                                      {statusLabel}
                                    </span>
                                    <div className="text-sm text-gray-700 dark:text-gray-300 grid grid-cols-1 md:grid-cols-2 gap-2">
                                      <p><span className="font-medium">Organization:</span> {azureInfo.organization}</p>
                                      <p><span className="font-medium">Project:</span> {azureInfo.project}</p>
                                      <p><span className="font-medium">Repository:</span> {azureInfo.repository}</p>
                                      <p><span className="font-medium">Agent pool:</span> {conn.agent_pool || 'Not set'}</p>
                                      <p><span className="font-medium">Connection:</span> {conn.display_name || `${conn.organization}${conn.project ? ` / ${conn.project}` : ''}`}</p>
                                      <p><span className="font-medium">VM:</span> {conn.gcp_instance_name} ({conn.gcp_zone})</p>
                                    </div>
                                    {agent.error && (
                                      <div className="text-xs text-red-700 dark:text-red-300 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded p-2">
                                        Runner status error: {agent.error}
                                      </div>
                                    )}
                                  </div>
                                </div>
                              );
                            })()}
                            {(() => {
                              const conn = actionRunnerConnections.find((c) => c.id === repo.action_runner_connection_id);
                              const hasCloudRunner = !!(conn && conn.gcp_instance_name && conn.gcp_zone);
                              if (hasCloudRunner) return null;
                              const azureInfo = parseAzureDevOpsUrl(repo.url);
                              const agentPoolsUrl = `${azureInfo.baseUrl}/_settings/agentpools`;
                              const projectSettingsUrl = `${azureInfo.baseUrl}/${azureInfo.project}/_settings/agentqueues`;
                              
                              return (
                                <>
                                  <div className="flex items-center justify-between">
                                    <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                      <Download className="h-5 w-5 mr-2 text-green-600 dark:text-green-400" />
                                      Azure DevOps Agent Management
                                    </h4>
                                    <div className="flex items-center space-x-2">
                                      <a
                                        href={agentPoolsUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors duration-200 shadow-sm"
                                      >
                                        <ExternalLink className="h-4 w-4 mr-2" />
                                        Agent Pools
                                      </a>
                                      <a
                                        href={projectSettingsUrl}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center px-3 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 rounded-lg transition-colors duration-200 shadow-sm"
                                      >
                                        <Plus className="h-4 w-4 mr-2" />
                                        Add Agent
                                      </a>
                                    </div>
                                  </div>
                                  
                                  {/* Azure DevOps Project Information */}
                                  <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                                    <div className="flex items-start">
                                      <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
                                      <div>
                                        <h6 className="font-medium text-blue-800 dark:text-blue-200 mb-2">Azure DevOps Project Info</h6>
                                        <div className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
                                          <p><span className="font-medium">Organization:</span> {azureInfo.organization}</p>
                                          <p><span className="font-medium">Project:</span> {azureInfo.project}</p>
                                          <p><span className="font-medium">Repository:</span> {azureInfo.repository}</p>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                </>
                              );
                            })()}

                            {/* Service Configuration */}
                            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-visible">
                              <div className="bg-gray-50 dark:bg-gray-900/30 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                                <h5 className="font-medium text-gray-900 dark:text-gray-200 text-sm flex items-center">
                                  <Settings className="h-4 w-4 mr-2" />
                                  Service Configuration
                                </h5>
                              </div>
                              <div className="p-4 space-y-4">
                                <div className="relative service-dropdown-container">
                                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Service Name
                                  </label>
                                  <div className="relative">
                                    <input
                                      type="text"
                                      value={azureAgentServiceNames[repo.id] || getDefaultAzureAgentServiceName(repo)}
                                      onChange={(e) => setAzureAgentServiceNames(prev => ({ ...prev, [repo.id]: e.target.value }))}
                                      className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                                      placeholder={getDefaultAzureAgentServiceName(repo)}
                                    />
                                    <button
                                      type="button"
                                      onClick={() => toggleAzureServiceDropdown(repo.id)}
                                      className="absolute inset-y-0 right-0 flex items-center px-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                                    >
                                      <ChevronDown className={`h-4 w-4 transition-transform ${azureServiceDropdownOpen[repo.id] ? 'rotate-180' : ''}`} />
                                    </button>
                                  </div>
                                  
                                  {/* Dropdown */}
                                  {azureServiceDropdownOpen[repo.id] && (
                                    <div className="absolute z-50 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-2xl max-h-60 overflow-y-auto" style={{ minWidth: '100%' }}>
                                      {loadingAzureServices ? (
                                        <div className="flex items-center justify-center py-4">
                                          <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                                          <span className="text-sm text-gray-600 dark:text-gray-400">Loading services...</span>
                                        </div>
                                      ) : availableAzureServices.length > 0 ? (
                                        <>
                                          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700">
                                            <p className="text-xs text-gray-500 dark:text-gray-400 font-medium">
                                              Available Azure Agent Services ({availableAzureServices.length})
                                            </p>
                                          </div>
                                          {availableAzureServices.map((service, index) => (
                                            <button
                                              key={index}
                                              type="button"
                                              onClick={() => {
                                                setAzureAgentServiceNames(prev => ({ ...prev, [repo.id]: service.name }));
                                                setAzureServiceDropdownOpen(prev => ({ ...prev, [repo.id]: false }));
                                              }}
                                              className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors border-b border-gray-100 dark:border-gray-700 last:border-b-0"
                                            >
                                              <div className="flex items-center justify-between">
                                                <div className="flex-1 min-w-0">
                                                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                                    {service.name}
                                                  </p>
                                                  <div className="flex items-center mt-1 space-x-3">
                                                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                                                      service.status === 'running' 
                                                        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
                                                        : service.status === 'stopped'
                                                        ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
                                                        : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                                                    }`}>
                                                      {service.status_display || 'Unknown'}
                                                    </span>
                                                    {service.display_name && service.display_name !== service.name && (
                                                      <span className="text-xs text-gray-500 dark:text-gray-400 truncate">
                                                        {service.display_name}
                                                      </span>
                                                    )}
                                                  </div>
                                                </div>
                                              </div>
                                            </button>
                                          ))}
                                        </>
                                      ) : (
                                        <div className="px-3 py-4 text-center">
                                          <Search className="h-6 w-6 text-gray-400 mx-auto mb-2" />
                                          <p className="text-sm text-gray-600 dark:text-gray-400">No Azure agent services found</p>
                                          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                                            Make sure agent services are installed and running
                                          </p>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                  
                                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    Default format: vstsagent.{'{organization}'}.{'{repository}'}
                                  </p>
                                </div>
                                <div className="flex items-center space-x-3">
                                  <button
                                    onClick={() => saveAzureAgentServiceName(repo.id)}
                                    disabled={savingAzureAgentServiceName.has(repo.id)}
                                    className="flex items-center px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    <Save className={`h-4 w-4 mr-2 ${savingAzureAgentServiceName.has(repo.id) ? 'animate-spin' : ''}`} />
                                    {savingAzureAgentServiceName.has(repo.id) ? 'Saving...' : 'Save Service Name'}
                                  </button>
                                  <button
                                    onClick={() => checkAzureAgentService(repo.id)}
                                    disabled={checkingAzureAgentService.has(repo.id)}
                                    className="flex items-center px-3 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                  >
                                    <RefreshCw className={`h-4 w-4 mr-2 ${checkingAzureAgentService.has(repo.id) ? 'animate-spin' : ''}`} />
                                    {checkingAzureAgentService.has(repo.id) ? 'Checking...' : 'Check Service'}
                                  </button>
                                </div>
                              </div>
                            </div>

                            {/* Service Status */}
                            {azureAgentServiceStatus[repo.id] && (
                              <div className={`rounded-lg border p-4 ${
                                azureAgentServiceStatus[repo.id]?.status === 'running' 
                                  ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                                  : azureAgentServiceStatus[repo.id]?.status === 'stopped'
                                  ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                                  : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
                              }`}>
                                <div className="flex items-center justify-between mb-3">
                                  <h5 className={`font-medium text-sm flex items-center ${
                                    azureAgentServiceStatus[repo.id]?.status === 'running' 
                                      ? 'text-green-800 dark:text-green-200'
                                      : azureAgentServiceStatus[repo.id]?.status === 'stopped'
                                      ? 'text-red-800 dark:text-red-200'
                                      : 'text-yellow-800 dark:text-yellow-200'
                                  }`}>
                                    {azureAgentServiceStatus[repo.id]?.status === 'running' ? (
                                      <CheckCircle className="h-4 w-4 mr-2" />
                                    ) : azureAgentServiceStatus[repo.id]?.status === 'stopped' ? (
                                      <X className="h-4 w-4 mr-2" />
                                    ) : (
                                      <AlertCircle className="h-4 w-4 mr-2" />
                                    )}
                                    Service Status: {azureAgentServiceStatus[repo.id]?.status_display || 'Unknown'}
                                  </h5>
                                  <span className={`text-xs px-2 py-1 rounded-full ${
                                    azureAgentServiceStatus[repo.id]?.status === 'running' 
                                      ? 'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200'
                                      : azureAgentServiceStatus[repo.id]?.status === 'stopped'
                                      ? 'bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200'
                                      : 'bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200'
                                  }`}>
                                    {(azureAgentServiceStatus[repo.id]?.status || 'UNKNOWN').toUpperCase()}
                                  </span>
                                </div>
                                <div className={`text-sm space-y-1 ${
                                  azureAgentServiceStatus[repo.id]?.status === 'running' 
                                    ? 'text-green-700 dark:text-green-300'
                                    : azureAgentServiceStatus[repo.id]?.status === 'stopped'
                                    ? 'text-red-700 dark:text-red-300'
                                    : 'text-yellow-700 dark:text-yellow-300'
                                }`}>
                                  <p><strong>Service Name:</strong> {azureAgentServiceStatus[repo.id]?.service_name || 'N/A'}</p>
                                  {azureAgentServiceStatus[repo.id]?.last_checked && (
                                    <p><strong>Last Checked:</strong> {formatTimestamp(azureAgentServiceStatus[repo.id].last_checked)}</p>
                                  )}
                                  {azureAgentServiceStatus[repo.id]?.error && (
                                    <p><strong>Error:</strong> {azureAgentServiceStatus[repo.id].error}</p>
                                  )}
                                </div>
                              </div>
                            )}

                            {/* Installation Steps */}
                            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                              <div className="bg-gray-50 dark:bg-gray-900/30 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                                <h5 className="font-medium text-gray-900 dark:text-gray-200 text-sm flex items-center">
                                  <Settings className="h-4 w-4 mr-2" />
                                  Agent Installation Guide
                                </h5>
                              </div>
                              <div className="p-6 space-y-6">
                                
                                {/* Step 1: Download Agent */}
                                <div className="space-y-3">
                                  <div className="flex items-center">
                                    <span className="flex items-center justify-center w-8 h-8 bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-300 rounded-full text-sm font-medium mr-3">1</span>
                                    <h6 className="font-medium text-gray-900 dark:text-white">Download Azure DevOps Agent</h6>
                                  </div>
                                  <div className="ml-11 space-y-3">
                                    <p className="text-sm text-gray-600 dark:text-gray-400">Download the Azure DevOps agent for your operating system:</p>
                                    <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-3">
                                      <p className="text-xs text-blue-700 dark:text-blue-300">
                                        💡 <strong>Latest Version:</strong> Check the{' '}
                                        <a 
                                          href="https://github.com/microsoft/azure-pipelines-agent/releases" 
                                          target="_blank" 
                                          rel="noopener noreferrer"
                                          className="underline hover:text-blue-800 dark:hover:text-blue-200"
                                        >
                                          Azure Pipelines Agent releases page
                                        </a>{' '}
                                        for the most current version (currently v3.240.1).
                                      </p>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                                      <a
                                        href="https://download.agent.dev.azure.com/agent/3.240.1/vsts-agent-win-x64-3.240.1.zip"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors border border-gray-200 dark:border-gray-600"
                                      >
                                        <Download className="h-4 w-4 text-blue-600 dark:text-blue-400 mr-2" />
                                        <span className="text-sm font-medium text-gray-900 dark:text-white">Windows x64</span>
                                      </a>
                                      <a
                                        href="https://download.agent.dev.azure.com/agent/3.240.1/vsts-agent-linux-x64-3.240.1.tar.gz"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors border border-gray-200 dark:border-gray-600"
                                      >
                                        <Download className="h-4 w-4 text-blue-600 dark:text-blue-400 mr-2" />
                                        <span className="text-sm font-medium text-gray-900 dark:text-white">Linux x64</span>
                                      </a>
                                      <a
                                        href="https://download.agent.dev.azure.com/agent/3.240.1/vsts-agent-osx-x64-3.240.1.tar.gz"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors border border-gray-200 dark:border-gray-600"
                                      >
                                        <Download className="h-4 w-4 text-blue-600 dark:text-blue-400 mr-2" />
                                        <span className="text-sm font-medium text-gray-900 dark:text-white">macOS x64</span>
                                      </a>
                                    </div>
                                  </div>
                                </div>

                                {/* Step 2: Extract and Configure */}
                                <div className="space-y-3">
                                  <div className="flex items-center">
                                    <span className="flex items-center justify-center w-8 h-8 bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-300 rounded-full text-sm font-medium mr-3">2</span>
                                    <h6 className="font-medium text-gray-900 dark:text-white">Extract and Configure Agent</h6>
                                  </div>
                                  <div className="ml-11 space-y-3">
                                    <p className="text-sm text-gray-600 dark:text-gray-400">Follow these steps to configure your agent:</p>
                                    
                                    {/* Tab-based code snippets */}
                                    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                                      <div className="flex bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                                        <button
                                          className={`px-4 py-2 text-sm font-medium border-r border-gray-200 dark:border-gray-700 ${
                                            (repoActiveTabs[`${repo.id}-extract-tab`] || 'windows') === 'windows'
                                              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400'
                                              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                                          }`}
                                          onClick={() => setRepoActiveTabs(prev => ({ ...prev, [`${repo.id}-extract-tab`]: 'windows' }))}
                                        >
                                          Windows
                                        </button>
                                        <button
                                          className={`px-4 py-2 text-sm font-medium ${
                                            (repoActiveTabs[`${repo.id}-extract-tab`] || 'windows') === 'linux'
                                              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400'
                                              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                                          }`}
                                          onClick={() => setRepoActiveTabs(prev => ({ ...prev, [`${repo.id}-extract-tab`]: 'linux' }))}
                                        >
                                          Linux/macOS
                                        </button>
                                      </div>
                                      
                                      {(repoActiveTabs[`${repo.id}-extract-tab`] || 'windows') === 'windows' ? (
                                        <div className="bg-gray-900 dark:bg-gray-800 p-4 text-sm font-mono text-green-400">
                                          <div className="space-y-1">
                                            <div># Extract the agent</div>
                                            <div>mkdir myagent</div>
                                            <div>cd myagent</div>
                                            <div># Extract the downloaded zip file</div>
                                            <div>Expand-Archive -Path vsts-agent-win-x64-*.zip -DestinationPath .</div>
                                            <div className="mt-2"># Configure the agent</div>
                                            <div>.\config.cmd</div>
                                          </div>
                                        </div>
                                      ) : (
                                        <div className="bg-gray-900 dark:bg-gray-800 p-4 text-sm font-mono text-green-400">
                                          <div className="space-y-1">
                                            <div># Extract the agent</div>
                                            <div>mkdir myagent && cd myagent</div>
                                            <div># Extract the downloaded tar.gz file</div>
                                            <div>tar zxvf ../vsts-agent-*.tar.gz</div>
                                            <div className="mt-2"># Configure the agent</div>
                                            <div>./config.sh</div>
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </div>

                                {/* Step 3: Configuration Details */}
                                <div className="space-y-3">
                                  <div className="flex items-center">
                                    <span className="flex items-center justify-center w-8 h-8 bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-300 rounded-full text-sm font-medium mr-3">3</span>
                                    <h6 className="font-medium text-gray-900 dark:text-white">Agent Configuration Parameters</h6>
                                  </div>
                                  <div className="ml-11">
                                    <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">
                                      When prompted during configuration, use these values:
                                    </p>
                                    <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
                                      <h6 className="font-medium text-yellow-800 dark:text-yellow-200 mb-3">Required Configuration Values:</h6>
                                      <div className="text-sm text-yellow-700 dark:text-yellow-300 space-y-2">
                                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                                          <div>
                                            <span className="font-medium">Server URL:</span>
                                            <div className="font-mono text-xs bg-yellow-100 dark:bg-yellow-800/30 px-2 py-1 rounded mt-1">
                                              {parseAzureDevOpsUrl(repo.url).baseUrl}
                                            </div>
                                          </div>
                                          <div>
                                            <span className="font-medium">Authentication:</span>
                                            <div className="text-xs mt-1">PAT (Personal Access Token)</div>
                                          </div>
                                          <div>
                                            <span className="font-medium">Agent Pool:</span>
                                            <div className="text-xs mt-1">Default (or create new pool)</div>
                                          </div>
                                          <div>
                                            <span className="font-medium">Agent Name:</span>
                                            <div className="font-mono text-xs bg-yellow-100 dark:bg-yellow-800/30 px-2 py-1 rounded mt-1">
                                              {parseAzureDevOpsUrl(repo.url).repository}-agent
                                            </div>
                                          </div>
                                          <div>
                                            <span className="font-medium">Work Folder:</span>
                                            <div className="text-xs mt-1">_work (use default)</div>
                                          </div>
                                          <div>
                                            <span className="font-medium">Run as Service:</span>
                                            <div className="text-xs mt-1">Y (recommended for production)</div>
                                          </div>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                </div>

                                {/* Step 4: Start Agent */}
                                <div className="space-y-3">
                                  <div className="flex items-center">
                                    <span className="flex items-center justify-center w-8 h-8 bg-blue-100 dark:bg-blue-900 text-blue-600 dark:text-blue-300 rounded-full text-sm font-medium mr-3">4</span>
                                    <h6 className="font-medium text-gray-900 dark:text-white">Start the Agent</h6>
                                  </div>
                                  <div className="ml-11 space-y-3">
                                    <p className="text-sm text-gray-600 dark:text-gray-400">Select your platform to see the commands:</p>
                                    
                                    {/* Platform-based tabs */}
                                    <div className="border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
                                      <div className="flex bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
                                        <button
                                          className={`px-4 py-2 text-sm font-medium border-r border-gray-200 dark:border-gray-700 ${
                                            (repoActiveTabs[`${repo.id}-platform-tab`] || 'windows') === 'windows'
                                              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400'
                                              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                                          }`}
                                          onClick={() => setRepoActiveTabs(prev => ({ ...prev, [`${repo.id}-platform-tab`]: 'windows' }))}
                                        >
                                          Windows
                                        </button>
                                        <button
                                          className={`px-4 py-2 text-sm font-medium ${
                                            (repoActiveTabs[`${repo.id}-platform-tab`] || 'windows') === 'linux'
                                              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400'
                                              : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-300'
                                          }`}
                                          onClick={() => setRepoActiveTabs(prev => ({ ...prev, [`${repo.id}-platform-tab`]: 'linux' }))}
                                        >
                                          Linux/macOS
                                        </button>
                                      </div>
                                      
                                      {(repoActiveTabs[`${repo.id}-platform-tab`] || 'windows') === 'windows' ? (
                                        <div className="p-4 space-y-4">
                                          {/* Interactive Mode */}
                                          <div>
                                            <h6 className="font-medium text-gray-900 dark:text-white mb-2">Interactive Mode (Development/Testing)</h6>
                                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">Agent runs in foreground, stops when terminal is closed</p>
                                            <div className="bg-gray-900 dark:bg-gray-800 rounded-lg p-3 text-sm font-mono text-green-400">
                                              <div>.\run.cmd</div>
                                            </div>
                                          </div>
                                          
                                          {/* Service Mode */}
                                          <div>
                                            <h6 className="font-medium text-gray-900 dark:text-white mb-2">Service Mode (Production)</h6>
                                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">Agent runs as a system service, starts automatically</p>
                                            <div className="bg-gray-900 dark:bg-gray-800 rounded-lg p-3 text-sm font-mono text-green-400 space-y-1">
                                              <div># Run PowerShell as Administrator</div>
                                              <div>.\svc.cmd install</div>
                                              <div>.\svc.cmd start</div>
                                              <div># Check service status</div>
                                              <div>.\svc.cmd status</div>
                                            </div>
                                          </div>
                                        </div>
                                      ) : (
                                        <div className="p-4 space-y-4">
                                          {/* Interactive Mode */}
                                          <div>
                                            <h6 className="font-medium text-gray-900 dark:text-white mb-2">Interactive Mode (Development/Testing)</h6>
                                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">Agent runs in foreground, stops when terminal is closed</p>
                                            <div className="bg-gray-900 dark:bg-gray-800 rounded-lg p-3 text-sm font-mono text-green-400">
                                              <div>./run.sh</div>
                                            </div>
                                          </div>
                                          
                                          {/* Service Mode */}
                                          <div>
                                            <h6 className="font-medium text-gray-900 dark:text-white mb-2">Service Mode (Production)</h6>
                                            <p className="text-sm text-gray-600 dark:text-gray-400 mb-3">Agent runs as a system service, starts automatically</p>
                                            <div className="bg-gray-900 dark:bg-gray-800 rounded-lg p-3 text-sm font-mono text-green-400 space-y-1">
                                              <div># Install as service</div>
                                              <div>sudo ./svc.sh install</div>
                                              <div># Start service</div>
                                              <div>sudo ./svc.sh start</div>
                                              <div># Check service status</div>
                                              <div>sudo ./svc.sh status</div>
                                            </div>
                                          </div>
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                </div>
                              </div>
                            </div>

                            {/* Quick Links */}
                            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
                              <div className="bg-gray-50 dark:bg-gray-900/30 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                                <h5 className="font-medium text-gray-900 dark:text-gray-200 text-sm flex items-center">
                                  <ExternalLink className="h-4 w-4 mr-2" />
                                  Quick Access Links
                                </h5>
                              </div>
                              <div className="p-4">
                                {(() => {
                                  const azureInfo = parseAzureDevOpsUrl(repo.url);
                                  return (
                                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3">
                                      <a
                                        href={`${azureInfo.baseUrl}/_settings/agentpools`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors border border-blue-200 dark:border-blue-800"
                                      >
                                        <Server className="h-4 w-4 text-blue-600 dark:text-blue-400 mr-2" />
                                        <span className="text-sm font-medium text-blue-900 dark:text-blue-200">Agent Pools</span>
                                      </a>
                                      <a
                                        href={`${azureInfo.baseUrl}/${azureInfo.project}/_build`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg hover:bg-green-100 dark:hover:bg-green-900/30 transition-colors border border-green-200 dark:border-green-800"
                                      >
                                        <Activity className="h-4 w-4 text-green-600 dark:text-green-400 mr-2" />
                                        <span className="text-sm font-medium text-green-900 dark:text-green-200">Pipelines</span>
                                      </a>
                                      <a
                                        href={`${azureInfo.baseUrl}/${azureInfo.project}/_settings`}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg hover:bg-purple-100 dark:hover:bg-purple-900/30 transition-colors border border-purple-200 dark:border-purple-800"
                                      >
                                        <Settings className="h-4 w-4 text-purple-600 dark:text-purple-400 mr-2" />
                                        <span className="text-sm font-medium text-purple-900 dark:text-purple-200">Project Settings</span>
                                      </a>
                                      <a
                                        href="https://docs.microsoft.com/en-us/azure/devops/pipelines/agents/"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="flex items-center p-3 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors border border-gray-200 dark:border-gray-600"
                                      >
                                        <FileText className="h-4 w-4 text-gray-600 dark:text-gray-400 mr-2" />
                                        <span className="text-sm font-medium text-gray-900 dark:text-gray-200">Documentation</span>
                                      </a>
                                    </div>
                                  );
                                })()}
                              </div>
                            </div>
                          </div>
                        )}

                        {/* GitHub Actions Runner Installation Tab */}
                        {getRepoActiveTab(repo.id) === 'github-runner-install' && (
                          <div className="space-y-6 tab-enter">
                            <div className="flex items-center justify-between">
                              <h4 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                                <Download className="h-5 w-5 mr-2 text-green-600 dark:text-green-400" />
                                GitHub Actions Runner Management
                              </h4>
                              <div className="flex items-center space-x-2">
                                {/* Only show Add Runner button if service is not found */}
                                {runnerServiceStatus[repo.id]?.status === 'not_found' && (
                                  <a
                                    href={`${repo.url}/settings/actions/runners/new`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="flex items-center px-3 py-2 text-sm font-medium text-white bg-green-600 hover:bg-green-700 dark:bg-green-500 dark:hover:bg-green-600 rounded-lg transition-colors duration-200 shadow-sm"
                                  >
                                    <ExternalLink className="h-4 w-4 mr-2" />
                                    Add Runner
                                  </a>
                                )}
                              </div>
                            </div>
                            
                            {/* Service Configuration */}
                            <div className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 overflow-visible">
                              <div className="bg-gray-50 dark:bg-gray-900/30 px-4 py-3 border-b border-gray-200 dark:border-gray-700">
                                <h5 className="font-medium text-gray-900 dark:text-gray-200 text-sm flex items-center">
                                  <Settings className="h-4 w-4 mr-2" />
                                  Service Configuration
                                </h5>
                              </div>
                              <div className="p-4 space-y-4">
                                <div className="relative service-dropdown-container">
                                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                    Service Name
                                  </label>
                                  <div className="relative">
                                    <input
                                      type="text"
                                      value={runnerServiceNames[repo.id] || getDefaultServiceName(repo)}
                                      onChange={(e) => setRunnerServiceNames(prev => ({ ...prev, [repo.id]: e.target.value }))}
                                      className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-md focus:ring-2 focus:ring-green-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                                      placeholder={getDefaultServiceName(repo)}
                                    />
                                    <button
                                      type="button"
                                      onClick={() => toggleServiceDropdown(repo.id)}
                                      className="absolute inset-y-0 right-0 flex items-center px-3 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                                    >
                                      <ChevronDown className={`h-4 w-4 transition-transform ${serviceDropdownOpen[repo.id] ? 'rotate-180' : ''}`} />
                                    </button>
                                  </div>
                                  
                                  {/* Dropdown */}
                                  {serviceDropdownOpen[repo.id] && (
                                    <div className="absolute z-50 mt-1 w-full bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-md shadow-2xl max-h-60 overflow-y-auto" style={{ minWidth: '100%' }}>
                                      {loadingServices ? (
                                        <div className="flex items-center justify-center py-4">
                                          <RefreshCw className="h-4 w-4 animate-spin mr-2" />
                                          <span className="text-sm text-gray-600 dark:text-gray-400">Loading services...</span>
                                        </div>
                                      ) : availableServices.length > 0 ? (
                                        <>
                                          <div className="px-3 py-2 border-b border-gray-200 dark:border-gray-700">
                                            <p className="text-xs text-gray-500 dark:text-gray-400 font-medium">
                                              Available GitHub Runner Services ({availableServices.length})
                                            </p>
                                          </div>
                                          {availableServices.map((service, index) => (
                                            <button
                                              key={index}
                                              type="button"
                                              onClick={() => {
                                                setRunnerServiceNames(prev => ({ ...prev, [repo.id]: service.name }));
                                                setServiceDropdownOpen(prev => ({ ...prev, [repo.id]: false }));
                                              }}
                                              className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors border-b border-gray-100 dark:border-gray-700 last:border-b-0"
                                            >
                                              <div className="flex items-center justify-between">
                                                <div className="flex-1 min-w-0">
                                                  <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                                                    {service.name}
                                                  </p>
                                                  <div className="flex items-center mt-1 space-x-3">
                                                    <span className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                                                      service.status === 'running' 
                                                        ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300'
                                                        : service.status === 'stopped'
                                                        ? 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300'
                                                        : 'bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-300'
                                                    }`}>
                                                      {service.status_display || 'Unknown'}
                                                    </span>
                                                    {service.display_name && service.display_name !== service.name && (
                                                      <span className="text-xs text-gray-500 dark:text-gray-400 truncate">
                                                        {service.display_name}
                                                      </span>
                                                    )}
                                                  </div>
                                                </div>
                                              </div>
                                            </button>
                                          ))}
                                        </>
                                      ) : (
                                        <div className="px-3 py-4 text-center">
                                          <Search className="h-6 w-6 text-gray-400 mx-auto mb-2" />
                                          <p className="text-sm text-gray-600 dark:text-gray-400">No GitHub runner services found</p>
                                          <p className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                                            Make sure runner services are installed and running
                                          </p>
                                          <p className="text-xs text-red-500 mt-1">
                                            Debug: Available services: {availableServices.length}
                                          </p>
                                        </div>
                                      )}
                                    </div>
                                  )}
                                  
                                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                                    Default format: actions.runner.{'{owner}'}.{'{repo}'}.PRMonitor
                                  </p>
                                </div>
                                <button
                                  onClick={() => saveRunnerServiceName(repo.id)}
                                  disabled={savingRunnerServiceName.has(repo.id)}
                                  className="flex items-center px-3 py-2 text-sm font-medium text-white bg-gray-600 hover:bg-gray-700 dark:bg-gray-500 dark:hover:bg-gray-600 rounded-lg transition-colors duration-200 shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                                >
                                  <Save className={`h-4 w-4 mr-2 ${savingRunnerServiceName.has(repo.id) ? 'animate-spin' : ''}`} />
                                  {savingRunnerServiceName.has(repo.id) ? 'Saving...' : 'Save Service Name'}
                                </button>
                              </div>
                            </div>

                            {/* Service Status */}
                                        {runnerServiceStatus[repo.id] && (
              <div className={`rounded-lg border p-4 ${
                runnerServiceStatus[repo.id]?.status === 'running' 
                  ? 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800'
                  : runnerServiceStatus[repo.id]?.status === 'stopped'
                  ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800'
                  : 'bg-yellow-50 dark:bg-yellow-900/20 border-yellow-200 dark:border-yellow-800'
              }`}>
                <div className="flex items-center justify-between mb-3">
                  <h5 className={`font-medium text-sm flex items-center ${
                    runnerServiceStatus[repo.id]?.status === 'running' 
                      ? 'text-green-800 dark:text-green-200'
                      : runnerServiceStatus[repo.id]?.status === 'stopped'
                      ? 'text-red-800 dark:text-red-200'
                      : 'text-yellow-800 dark:text-yellow-200'
                  }`}>
                    {runnerServiceStatus[repo.id]?.status === 'running' ? (
                      <CheckCircle className="h-4 w-4 mr-2" />
                    ) : runnerServiceStatus[repo.id]?.status === 'stopped' ? (
                      <X className="h-4 w-4 mr-2" />
                    ) : (
                      <AlertCircle className="h-4 w-4 mr-2" />
                    )}
                    Service Status: {runnerServiceStatus[repo.id]?.status_display || 'Unknown'}
                  </h5>
                  <span className={`text-xs px-2 py-1 rounded-full ${
                    runnerServiceStatus[repo.id]?.status === 'running' 
                      ? 'bg-green-200 dark:bg-green-800 text-green-800 dark:text-green-200'
                      : runnerServiceStatus[repo.id]?.status === 'stopped'
                      ? 'bg-red-200 dark:bg-red-800 text-red-800 dark:text-red-200'
                      : 'bg-yellow-200 dark:bg-yellow-800 text-yellow-800 dark:text-yellow-200'
                  }`}>
                    {(runnerServiceStatus[repo.id]?.status || 'UNKNOWN').toUpperCase()}
                  </span>
                </div>
                <div className={`text-sm space-y-1 ${
                  runnerServiceStatus[repo.id]?.status === 'running' 
                    ? 'text-green-700 dark:text-green-300'
                    : runnerServiceStatus[repo.id]?.status === 'stopped'
                    ? 'text-red-700 dark:text-red-300'
                    : 'text-yellow-700 dark:text-yellow-300'
                }`}>
                  <p><strong>Service Name:</strong> {runnerServiceStatus[repo.id]?.service_name || 'N/A'}</p>
                  {runnerServiceStatus[repo.id]?.last_checked && (
                    <p><strong>Last Checked:</strong> {formatTimestamp(runnerServiceStatus[repo.id].last_checked)}</p>
                  )}
                  {runnerServiceStatus[repo.id]?.error && (
                    <p><strong>Error:</strong> {runnerServiceStatus[repo.id].error}</p>
                  )}
                </div>
              </div>
            )}

                            {/* Instructions */}
                            <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
                              <div className="flex items-start">
                                <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
                                <div>
                                  <h6 className="font-medium text-blue-800 dark:text-blue-200 mb-2">GitHub Actions Runner Setup</h6>
                                  <div className="text-sm text-blue-700 dark:text-blue-300 space-y-2">
                                    <p>1. Click "Add Runner" to go to GitHub's runner setup page</p>
                                    <p>2. Follow GitHub's instructions to download and configure the runner</p>
                                    <p>3. Install the runner as a Windows service with the configured name</p>
                                    <p>4. Use "Check Service" to verify the service is running</p>
                                    <p>5. The service status will be integrated into repository health monitoring</p>
                                  </div>
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
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

      {/* GitHub Action Config Editor Modal */}
      {showGithubActionConfigEditor && (
        <GitHubActionConfigEditor
          repoId={showGithubActionConfigEditor}
          repoData={repositories.find(r => r.id === showGithubActionConfigEditor)}
          onClose={closeGithubActionConfigEditor}
          onSave={handleGithubActionConfigSave}
        />
      )}

      {/* Azure Pipeline Config Editor Modal */}
      {showAzurePipelineConfigEditor && (
        <AzurePipelineConfigEditor
          repoId={showAzurePipelineConfigEditor}
          repoData={repositories.find(r => r.id === showAzurePipelineConfigEditor)}
          onClose={closeAzurePipelineConfigEditor}
          onSave={handleAzurePipelineConfigSave}
        />
      )}

      {repoCleanupConfirmModal.show && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-2xl rounded-xl bg-white dark:bg-gray-900 shadow-2xl border border-gray-200 dark:border-gray-700">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">Delete Repository</h3>
              <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">
                This removes the repository from the dashboard and cleans up linked automation artifacts.
              </p>
            </div>
            <div className="px-6 py-5 space-y-4">
              {repoCleanupConfirmModal.loading ? (
                <div className="flex items-center text-sm text-gray-600 dark:text-gray-300">
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  Loading cleanup impact preview...
                </div>
              ) : (
                <>
                  <div className="text-sm text-gray-700 dark:text-gray-300">
                    Repository: <span className="font-medium">{repoCleanupConfirmModal.repo?.name}</span>
                  </div>
                  {repoCleanupConfirmModal.preview?.cleanup_scope && (
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-2 text-sm">
                      <div className="rounded border border-gray-200 dark:border-gray-700 p-2">Checks: {repoCleanupConfirmModal.preview.cleanup_scope.azure_checks ?? 0}</div>
                      <div className="rounded border border-gray-200 dark:border-gray-700 p-2">Operations: {repoCleanupConfirmModal.preview.cleanup_scope.operations ?? 0}</div>
                      <div className="rounded border border-gray-200 dark:border-gray-700 p-2">Jobs: {repoCleanupConfirmModal.preview.cleanup_scope.jobs ?? 0}</div>
                      <div className="rounded border border-gray-200 dark:border-gray-700 p-2">Logs: {repoCleanupConfirmModal.preview.cleanup_scope.logs ?? 0}</div>
                      <div className="rounded border border-gray-200 dark:border-gray-700 p-2">Notification Events: {repoCleanupConfirmModal.preview.cleanup_scope.notification_events ?? 0}</div>
                    </div>
                  )}
                  <ul className="text-sm text-gray-700 dark:text-gray-300 space-y-1">
                    <li>- Deletes this dashboard repository entry (not the target source repository).</li>
                    <li>- Removes Azure PR-Agent check/policy entries for Azure repositories.</li>
                    <li>- Cleans repository-scoped metrics/history and recalculates aggregates.</li>
                  </ul>
                  {repoCleanupConfirmModal.preview?.azure_policy_warning && (
                    <div className="rounded-md bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 p-3 text-sm text-yellow-800 dark:text-yellow-300">
                      Azure check preview warning: {repoCleanupConfirmModal.preview.azure_policy_warning}
                    </div>
                  )}
                </>
              )}
            </div>
            <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setRepoCleanupConfirmModal({ show: false, loading: false, repo: null, preview: null, error: null })}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmRepositoryCleanupDelete}
                disabled={repoCleanupConfirmModal.loading}
                className="px-4 py-2 text-sm font-medium text-white bg-red-600 hover:bg-red-700 rounded-lg disabled:opacity-60 disabled:cursor-not-allowed"
              >
                Delete and Cleanup
              </button>
            </div>
          </div>
        </div>
      )}

      {repoActionModal.show && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="w-full max-w-2xl rounded-xl bg-white dark:bg-gray-900 shadow-2xl border border-gray-200 dark:border-gray-700">
            <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{repoActionModal.title}</h3>
              <p className="text-sm text-gray-600 dark:text-gray-300 mt-1">{repoActionModal.subtitle}</p>
            </div>
            <div className="px-6 py-5 space-y-3">
              {(repoActionModal.message || repoActionModal.error) && (
                <div className={`text-sm rounded-md p-3 border ${
                  repoActionModal.error
                    ? 'bg-red-50 dark:bg-red-900/20 border-red-200 dark:border-red-800 text-red-700 dark:text-red-300'
                    : 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800 text-blue-700 dark:text-blue-300'
                }`}>
                  {repoActionModal.error || repoActionModal.message}
                </div>
              )}
              {Array.isArray(repoActionModal.steps) && repoActionModal.steps.length > 0 && (
                <div className="space-y-2">
                  {repoActionModal.steps.map((step) => {
                    const status = step.status || 'pending';
                    return (
                      <div key={step.id} className="flex items-start gap-3 rounded-md border border-gray-200 dark:border-gray-700 p-3">
                        <div className="mt-0.5">
                          {status === 'completed' ? (
                            <CheckCircle className="h-4 w-4 text-green-600" />
                          ) : status === 'error' ? (
                            <AlertCircle className="h-4 w-4 text-red-600" />
                          ) : status === 'skipped' ? (
                            <Info className="h-4 w-4 text-gray-500" />
                          ) : status === 'running' ? (
                            <RefreshCw className="h-4 w-4 text-blue-600 animate-spin" />
                          ) : (
                            <Clock className="h-4 w-4 text-gray-400" />
                          )}
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-gray-900 dark:text-white">{step.label || step.id}</div>
                          {step.detail && <div className="text-xs text-gray-600 dark:text-gray-300 mt-0.5">{step.detail}</div>}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-gray-200 dark:border-gray-700 flex items-center justify-end">
              <button
                type="button"
                disabled={repoActionModal.running}
                onClick={() => {
                  clearRepoActionPollTimeout();
                  setRepoActionModal({
                    show: false,
                    running: false,
                    operationType: '',
                    operationId: '',
                    repoId: null,
                    title: '',
                    subtitle: '',
                    status: '',
                    steps: [],
                    message: '',
                    error: null,
                  });
                }}
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 rounded-lg border border-gray-300 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {repoActionModal.running ? 'Running...' : 'Close'}
              </button>
            </div>
          </div>
        </div>
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