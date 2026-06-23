import React, { useState, useEffect, useContext, useRef, useMemo } from 'react';
import { 
  Settings, 
  Save, 
  Brain, 
  X,
  MessageSquare,
  FileText,
  Lightbulb,
  Info,
  GitBranch,
  ExternalLink,
  Database,
  Github,
  Gauge,
  Clock,
  Zap,
  RotateCcw,
  Shield
} from 'lucide-react';
import api from '../services/api';
import { ToastContext } from '../contexts/ToastContext';
import ModelCombobox from './ModelCombobox';
import ModelMultiCombobox from './ModelMultiCombobox';
import { useAvailableModels } from '../hooks/useAvailableModels';
import { buildModelCapabilityMap, getModelCapability, capabilityLockMessage } from '../utils/modelCapabilities';
import Modal from './Modal';

const PrAgentConfigEditor = ({ 
  repositoryId, 
  repositoryName, 
  isOpen, 
  onClose, 
  onSave 
}) => {
  const [overrides, setOverrides] = useState({});
  const [originalOverrides, setOriginalOverrides] = useState({});
  const [globalConfigData, setGlobalConfigData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState('models');
  const [prStatus, setPrStatus] = useState(null);
  const [hasExistingConfig, setHasExistingConfig] = useState(false);
  const fetchConfigsRef = useRef(null);
  const { showSuccess, showError } = useContext(ToastContext);
  const { providers: availableProviders } = useAvailableModels();
  const capabilityMap = useMemo(() => buildModelCapabilityMap(availableProviders), [availableProviders]);

  const BOOLEAN_OPT_OUT_DEFAULT_KEYS = new Set([
    'azure_devops_config.auto_describe',
    'azure_devops_config.auto_review',
    'azure_devops_config.auto_improve',
    'github_action_config.auto_describe',
    'github_action_config.auto_review',
    'github_action_config.auto_improve',
    'config.publish_output',
    'config.publish_output_progress',
    'config.use_repo_settings_file',
    'config.use_wiki_settings_file',
    'config.use_global_settings_file',
    'pr_description.publish_description',
    'pr_description.enable_large_pr_handling',
  ]);

  const isBooleanEnabled = (fieldKey, value) => {
    if (BOOLEAN_OPT_OUT_DEFAULT_KEYS.has(fieldKey)) {
      return value !== false;
    }
    return Boolean(value);
  };

  const configSections = {
    models: {
      title: 'AI Models',
      icon: Brain,
      fields: [
        { key: 'config.model', label: 'Primary Model', type: 'model', description: 'Main AI model for most operations' },
        { key: 'config.model_reasoning', label: 'Reasoning Model', type: 'model', description: 'AI model for complex reasoning tasks' },
        { key: 'config.model_weak', label: 'Weak Model', type: 'model', description: 'Lightweight model for simple tasks (used for PR descriptions)' },
        { key: 'config.temperature', label: 'Temperature', type: 'number', min: 0, max: 2, step: 0.1, description: 'Creativity level (0 = focused, 2 = creative)', requiresCapability: 'supports_temperature' },
        { key: 'config.max_model_tokens', label: 'Max Model Tokens', type: 'number', min: 1000, max: 200000, description: 'Maximum tokens per request' },
        { key: 'config.reasoning_effort', label: 'Reasoning Effort', type: 'select', options: { effort: ['low', 'medium', 'high'] }, description: 'Reasoning intensity for complex tasks', requiresCapability: 'supports_reasoning_effort' }
      ]
    },
    context: {
      title: 'Code Context',
      icon: Database,
      fields: [
        { key: 'csharp_code_context_service.enabled', label: 'Enable Context Service', type: 'boolean', description: 'Provides additional code context for better suggestions' },
        { key: 'csharp_code_context_service.url', label: 'Service URL', type: 'text', description: 'Base URL for the context service', placeholder: 'https://localhost:7138' },
        { key: 'csharp_code_context_service.username', label: 'Context Service Username', type: 'text', description: 'Login username for context service', placeholder: 'Leave blank to use global' },
        { key: 'csharp_code_context_service.password', label: 'Context Service Password', type: 'password', description: 'Login password for context service', placeholder: 'Leave blank to use global' },
        { key: 'csharp_code_context_service.default_depth', label: 'Analysis Depth', type: 'select', options: { depth: [1, 2, 3, 4, 5] }, description: 'Depth of code analysis' },
        { key: 'csharp_code_context_service.default_mode', label: 'Analysis Mode', type: 'select', options: { mode: ['Full', 'Minified'] }, description: 'Mode of code analysis' },
        { key: 'csharp_code_context_service.timeout', label: 'Timeout (seconds)', type: 'number', min: 30, max: 600, description: 'Service timeout in seconds' }
      ]
    },
    reviewer: {
      title: 'PR Reviewer',
      icon: MessageSquare,
      fields: [
        { key: 'pr_reviewer.num_max_findings', label: 'Max Findings', type: 'number', min: 1, max: 50, description: 'Maximum number of review findings' },
        { key: 'pr_reviewer.extra_instructions', label: 'Extra Instructions', type: 'textarea', description: 'Additional instructions for code review' },
        { key: 'pr_reviewer.model', label: 'Override Model', type: 'model', description: 'Specific model for code review (optional)' }
      ]
    },
    suggestions: {
      title: 'Code Suggestions',
      icon: Lightbulb,
      fields: [
        { key: 'pr_code_suggestions.suggestions_score_threshold', label: 'Score Threshold', type: 'number', min: 0, max: 10, description: 'Minimum score for suggestions' },
        { key: 'pr_code_suggestions.commit_eligibility_threshold', label: 'Commit Threshold', type: 'number', min: 0, max: 10, step: 1, description: 'Threshold for commitable suggestions (0-10)' },
        { key: 'pr_code_suggestions.commitable_code_suggestions', label: 'Commitable Suggestions', type: 'boolean', description: 'Allow direct commits of suggestions' },
        { key: 'pr_code_suggestions.focus_only_on_problems', label: 'Focus Only on Problems', type: 'boolean', description: 'Only suggest fixes for actual problems' },
        { key: 'pr_code_suggestions.dual_publishing_score_threshold', label: 'Dual Publishing Threshold', type: 'number', min: -1, max: 10, description: 'Threshold for dual publishing (-1 to disable)' },
        { key: 'pr_code_suggestions.extra_instructions', label: 'Extra Instructions', type: 'textarea', description: 'Additional instructions for code suggestions' },
        { key: 'pr_code_suggestions.model', label: 'Override Model', type: 'model', description: 'Specific model for code suggestions (optional)' }
      ]
    },
    description: {
      title: 'PR Description',
      icon: FileText,
      fields: [
        { key: 'azure_devops_config.auto_describe', label: 'Auto-generate on new PR (Azure DevOps)', type: 'boolean', description: 'Run /describe automatically when a pipeline is triggered for a new PR' },
        { key: 'github_action_config.auto_describe', label: 'Auto-generate on new PR (GitHub Actions)', type: 'boolean', description: 'Run /describe automatically when GitHub Actions processes a new PR' },
        { key: 'config.publish_output', label: 'Publish to PR', type: 'boolean', description: 'Write generated description to the pull request (required for descriptions to appear)' },
        { key: 'pr_description.publish_description', label: 'Enable description publishing', type: 'boolean', description: 'Describe-specific publish gate (also requires Publish to PR)' },
        { key: 'pr_description.publish_description_as_comment', label: 'Publish as comment', type: 'boolean', description: 'Post description as a PR comment instead of updating the PR description field' },
        { key: 'pr_filters.skip_if_description_exists', label: 'Skip if description exists', type: 'boolean', description: 'Skip /describe when the PR body already contains text' },
        { key: 'pr_description.publish_labels', label: 'Publish Labels', type: 'boolean', description: 'Automatically publish PR labels' },
        { key: 'pr_description.generate_ai_title', label: 'Generate AI Title', type: 'boolean', description: 'Generate PR title using AI' },
        { key: 'pr_description.enable_large_pr_handling', label: 'Large PR Handling', type: 'boolean', description: 'Special handling for large PRs' },
        { key: 'pr_description.extra_instructions', label: 'Extra Instructions', type: 'textarea', description: 'Additional instructions for PR description' }
      ]
    },
    github: {
      title: 'GitHub Settings',
      icon: Github,
      fields: [
        { key: 'github.bot_user', label: 'Bot User', type: 'text', description: 'GitHub bot username', placeholder: 'github-actions[bot]' },
        { key: 'github.override_deployment_type', label: 'Override Deployment Type', type: 'boolean', description: 'Override automatic deployment type detection' }
      ]
    },
    timeEstimation: {
      title: 'Time Estimation',
      icon: Clock,
      fields: [
        { key: 'pr_dev_time_estimation.enabled', label: 'Enable Time Estimation', type: 'boolean', description: 'Enable development time estimation' },
        { key: 'pr_dev_time_estimation.model', label: 'Override Model', type: 'model', description: 'Specific model for time estimation (optional)' },
        { key: 'pr_dev_time_estimation.extra_instructions', label: 'Extra Instructions', type: 'textarea', description: 'Additional instructions for time estimation' }
      ]
    },
    advanced: {
      title: 'Advanced Settings',
      icon: Zap,
      fields: [
        { key: 'config.fallback_models', label: 'Fallback Models', type: 'multiselect', description: 'Fallback models when primary fails' },
        { key: 'config.custom_model_max_tokens', label: 'Custom Model Max Tokens', type: 'number', min: -1, max: 2000000, description: 'Token limit for unknown models (-1 = auto)' },
        { key: 'config.repo_settings_branch', label: 'Repo Settings Branch', type: 'text', placeholder: 'e.g. master (empty = auto)', description: 'Branch to load .pr_agent.toml and best_practices.md from. Empty uses PR source → target → default → main/master.' },
        { key: 'config.use_repo_settings_file', label: 'Use Repo Settings File', type: 'boolean', description: 'Use repository-specific .pr_agent.toml settings file' },
        { key: 'config.use_wiki_settings_file', label: 'Use Wiki Settings File', type: 'boolean', description: 'Use wiki-based settings file when available' },
        { key: 'config.use_global_settings_file', label: 'Use Global Settings File', type: 'boolean', description: 'Use organization-wide global settings file' },
        { key: 'config.verbosity_level', label: 'Verbosity Level', type: 'select', options: { level: [0, 1, 2] }, description: 'Logging verbosity level' },
        { key: 'config.ai_timeout', label: 'AI Timeout (seconds)', type: 'number', min: 30, max: 600, description: 'Timeout for AI model requests' },
        { key: 'config.publish_output_progress', label: 'Publish Output Progress', type: 'boolean', description: 'Publish progress updates during long operations' },
        { key: 'config.enable_auto_approval', label: 'Enable Auto Approval', type: 'boolean', description: 'Enable auto-approval of PRs under certain conditions' },
        { key: 'config.log_level', label: 'Log Level', type: 'select', options: { level: ['DEBUG', 'INFO', 'WARNING', 'ERROR'] }, description: 'Application log level' },
        { key: 'config.response_language', label: 'Response Language', type: 'text', placeholder: 'en-US', description: 'Locale for PR responses (ISO 3166/639, e.g. en-US)' },
        { key: 'config.git_provider', label: 'Git Provider', type: 'select', options: { provider: ['github', 'gitlab', 'bitbucket', 'azure', 'gitea'] }, description: 'Default git provider for CLI mode' }
      ]
    },
    dashboard: {
      title: 'Dashboard Integration',
      icon: Gauge,
      fields: [
        { key: 'dashboard.enabled', label: 'Enable Dashboard Integration', type: 'boolean', description: 'Enable integration with PR-Agent dashboard' },
        { key: 'dashboard.url', label: 'Dashboard URL', type: 'text', description: 'Dashboard URL used by PR-Agent dashboard integration' },
        { key: 'dashboard.api_key', label: 'Dashboard API Key', type: 'password', description: 'API key for dashboard authentication' }
      ]
    },
    pr_filters: {
      title: 'PR Filters',
      icon: Shield,
      fields: [
        { key: 'pr_filters.terminate_on_no_bots', label: 'Terminate on [no_bots]', type: 'boolean', description: 'Terminate entire job if [no_bots] found in PR description' },
        { key: 'pr_filters.max_lines_changed', label: 'Max lines changed', type: 'number', min: 0, max: 100000, description: 'Skip PRs exceeding this many lines changed (0 = disabled)' },
        { key: 'pr_filters.skip_if_review_suggestions_exist', label: 'Skip ALL tools if PR-Agent has processed PR', type: 'boolean', description: 'Skip ALL tools if PR-Agent has already processed this PR (detects "PR Reviewer Guide 🔍" header)' }
      ]
    }
  };

  // Load data when modal opens
  useEffect(() => {
    if (isOpen) {
      fetchConfigsRef.current?.();
    }
  }, [isOpen, repositoryId]);

  const fetchConfigs = async () => {
    setLoading(true);
    try {
      // Fetch both global config and repository-specific overrides
      const [globalResponse, repoResponse] = await Promise.all([
        api.getConfig(),
        api.getRepositoryPrAgentConfig(repositoryId, false)
      ]);

      const globalData = globalResponse.data?.data || globalResponse.data || globalResponse;
      setGlobalConfigData(globalData);

      // Parse existing repository overrides
      const repoData = repoResponse.data?.data || {};
      const existingOverrides = repoData.parsed_config || {};
      const hasConfig = Object.keys(existingOverrides).length > 0 || repoData.content;
      
      setOverrides(existingOverrides);
      setOriginalOverrides(JSON.parse(JSON.stringify(existingOverrides)));
      setHasExistingConfig(hasConfig);
      
      // Set PR status
      setPrStatus({
        status: repoData.pr_status,
        url: repoData.pr_url,
        number: repoData.pr_number
      });

    } catch (error) {
      console.error('Error fetching config:', error);
      showError('Failed to load configuration');
    } finally {
      setLoading(false);
    }
  };

  fetchConfigsRef.current = fetchConfigs;

  // Helper functions
  const getGlobalValue = (path) => {
    if (!globalConfigData) return undefined;
    const keys = path.split('.');
    let value = globalConfigData;
    for (const key of keys) {
      if (value?.[key] !== undefined) {
        value = value[key];
      } else {
        return undefined;
      }
    }
    return value;
  };

  const getOverrideValue = (path) => {
    const keys = path.split('.');
    let value = overrides;
    for (const key of keys) {
      if (value?.[key] !== undefined) {
        value = value[key];
      } else {
        return undefined;
      }
    }
    return value;
  };

  const isOverridden = (path) => {
    return getOverrideValue(path) !== undefined;
  };

  const getCurrentValue = (path) => {
    const overrideValue = getOverrideValue(path);
    return overrideValue !== undefined ? overrideValue : getGlobalValue(path);
  };

  const updateOverride = (path, value) => {
    const keys = path.split('.');
    const newOverrides = { ...overrides };
    
    // Navigate to the right location
    let current = newOverrides;
    for (let i = 0; i < keys.length - 1; i++) {
      if (!current[keys[i]]) current[keys[i]] = {};
      current = current[keys[i]];
    }
    
    // Set or remove the value
    const globalValue = getGlobalValue(path);
    if (value === undefined || value === null || value === '' || value === globalValue) {
      // Remove override if value matches global or is empty
      delete current[keys[keys.length - 1]];
      
      // Clean up empty parent objects
      let parent = newOverrides;
      let parentKeys = keys.slice(0, -1);
      for (let i = parentKeys.length - 1; i >= 0; i--) {
        if (parent[parentKeys[i]] && Object.keys(parent[parentKeys[i]]).length === 0) {
          delete parent[parentKeys[i]];
        }
        parent = newOverrides;
        for (let j = 0; j < i; j++) {
          parent = parent[parentKeys[j]] || {};
        }
      }
    } else {
      current[keys[keys.length - 1]] = value;
    }
    
    setOverrides(newOverrides);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // Validate PR filters configuration
      if (overrides.pr_filters?.max_lines_changed !== undefined) {
        const maxLines = overrides.pr_filters.max_lines_changed;
        if (maxLines < 0 || maxLines > 100000) {
          showError('Max lines changed must be between 0 and 100,000');
          setSaving(false);
          return;
        }
      }
      
      // Convert overrides to TOML format
      const tomlContent = generateTomlFromOverrides(overrides);
      
      const response = await api.updateRepositoryPrAgentConfig(repositoryId, tomlContent);

      if (response.data?.data) {
        setPrStatus({
          status: 'pending',
          url: response.data.data.pr_url,
          number: response.data.data.pr_number
        });
      }

      setOriginalOverrides(JSON.parse(JSON.stringify(overrides)));
      showSuccess('Configuration saved and PR created successfully!');
      
      // Pass result data to parent and close dialog
      if (onSave) {
        onSave(response.data?.data);
      }
      onClose();
    } catch (error) {
      console.error('Error saving config:', error);
      showError(error.response?.data?.detail || 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const generateTomlFromOverrides = (overrides) => {
    if (!overrides || Object.keys(overrides).length === 0) {
      return '# No overrides set - using global configuration\n';
    }

    let toml = `# Repository-specific PR-Agent configuration for ${repositoryName}\n`;
    toml += '# This file overrides global settings\n\n';

    Object.keys(overrides).forEach(section => {
      if (overrides[section] && Object.keys(overrides[section]).length > 0) {
        toml += `[${section}]\n`;
        Object.keys(overrides[section]).forEach(key => {
          const value = overrides[section][key];
          if (typeof value === 'string') {
            toml += `${key} = "${value}"\n`;
          } else if (typeof value === 'boolean') {
            toml += `${key} = ${value}\n`;
          } else if (typeof value === 'number') {
            toml += `${key} = ${value}\n`;
          } else if (Array.isArray(value)) {
            toml += `${key} = [${value.map(v => `"${v}"`).join(', ')}]\n`;
          }
        });
        toml += '\n';
      }
    });

    return toml;
  };

  const hasChanges = () => {
    return JSON.stringify(overrides) !== JSON.stringify(originalOverrides);
  };

  const cancelEdit = () => {
    // Revert any changes and close modal
    setOverrides(JSON.parse(JSON.stringify(originalOverrides)));
    onClose();
  };

  // Revert field to global default
  const revertField = (fieldKey) => {
    updateOverride(fieldKey, undefined);
  };

  // Render field component
  const renderField = (field) => {
    const currentValue = getCurrentValue(field.key);
    const isFieldOverridden = isOverridden(field.key);
    const booleanEnabled = field.type === 'boolean' ? isBooleanEnabled(field.key, currentValue) : Boolean(currentValue);

    // Determine whether this parameter is unsupported by the active primary model.
    const activeModel = getCurrentValue('config.model');
    let isLocked = false;
    let lockMessage = '';
    if (field.requiresCapability && activeModel) {
      const supported = getModelCapability(capabilityMap, activeModel, field.requiresCapability);
      if (supported === false) {
        isLocked = true;
        lockMessage = capabilityLockMessage(field.requiresCapability, activeModel);
      }
    }

    const fieldClasses = `w-full rounded-lg px-3 py-2 transition-all duration-200 ${
      isLocked
        ? 'bg-gray-100 dark:bg-gray-800/60 border border-gray-300 dark:border-gray-700 text-gray-400 dark:text-gray-500 cursor-not-allowed'
        : isFieldOverridden
        ? 'bg-blue-50 dark:bg-gray-700 border-2 border-blue-300 dark:border-blue-500/50 focus:border-blue-500 dark:focus:border-blue-400 text-gray-900 dark:text-gray-100'
        : 'bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 focus:border-gray-500 dark:focus:border-gray-400 text-gray-900 dark:text-gray-100'
    } focus:outline-none focus:ring-0`;

    let fieldElement;
    
    switch (field.type) {
      case 'model':
        fieldElement = (
          <ModelCombobox
            label=""
            value={currentValue || ''}
            onChange={(value) => updateOverride(field.key, value || undefined)}
            description=""
            disabled={false}
            allowEmpty={field.label.includes('Override')}
            emptyLabel={
              field.key.includes('model') && field.label.includes('Override')
                ? 'Use default model'
                : 'Use global default'
            }
            showRefresh={false}
            className=""
          />
        );
        break;

      case 'multiselect':
        fieldElement = (
          <ModelMultiCombobox
            label=""
            value={Array.isArray(currentValue) ? currentValue : []}
            onChange={(value) => updateOverride(field.key, value.length ? value : undefined)}
            description=""
            disabled={false}
          />
        );
        break;

      case 'select':
        fieldElement = (
          <select
            value={currentValue || ''}
            onChange={(e) => updateOverride(field.key, e.target.value)}
            disabled={isLocked}
            className={fieldClasses}
          >
            <option value="">
              {field.key.includes('model') && field.label.includes('Override') 
                ? 'Use default model' 
                : 'Use global default'}
            </option>
            {field.options && (() => {
              // Handle model options grouped by provider
              const firstValue = Object.values(field.options)[0];
              if (Array.isArray(firstValue) && firstValue.length > 0 && !field.options.effort && !field.options.depth && !field.options.mode && !field.options.level) {
                return Object.entries(field.options).map(([category, models]) => (
                  <optgroup key={category} label={category}>
                    {models.map(model => (
                      <option key={model} value={model}>{model}</option>
                    ))}
                  </optgroup>
                ));
              }
              
              // Handle simple arrays (effort, depth, mode, level)
              if (field.options.effort) {
                return field.options.effort.map(effort => (
                  <option key={effort} value={effort}>{effort.charAt(0).toUpperCase() + effort.slice(1)}</option>
                ));
              }
              
              if (field.options.depth) {
                return field.options.depth.map(depth => (
                  <option key={depth} value={depth}>Level {depth}</option>
                ));
              }
              
              if (field.options.mode) {
                return field.options.mode.map(mode => (
                  <option key={mode} value={mode}>{mode}</option>
                ));
              }
              
              if (field.options.level) {
                return field.options.level.map(level => (
                  <option key={level} value={level}>Level {level}</option>
                ));
              }

              if (field.options.provider) {
                return field.options.provider.map(provider => (
                  <option key={provider} value={provider}>{provider}</option>
                ));
              }
              
              return null;
            })()}
          </select>
        );
        break;
      
      case 'boolean':
        fieldElement = (
          <div className="flex items-center space-x-3">
            <button
              type="button"
              onClick={() => updateOverride(field.key, booleanEnabled ? false : true)}
              className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-offset-2 ${
                booleanEnabled
                  ? isFieldOverridden 
                    ? 'bg-blue-600 dark:bg-blue-500 focus:ring-blue-500' 
                    : 'bg-green-600 dark:bg-green-500 focus:ring-green-500'
                  : 'bg-gray-200 dark:bg-gray-700 focus:ring-gray-500'
              } ${
                isFieldOverridden
                  ? 'ring-2 ring-blue-300 dark:ring-blue-500/50'
                  : ''
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                  booleanEnabled ? 'translate-x-5' : 'translate-x-0'
                }`}
              />
            </button>
            <span className={`text-sm ${isFieldOverridden ? 'font-medium text-blue-700 dark:text-blue-300' : 'text-gray-700 dark:text-gray-300'}`}>
              {booleanEnabled ? 'Enabled' : 'Disabled'}
            </span>
          </div>
        );
        break;
      
      case 'number':
        fieldElement = (
          <input
            type="number"
            value={currentValue || ''}
            onChange={(e) => updateOverride(field.key, parseFloat(e.target.value))}
            min={field.min}
            max={field.max}
            step={field.step}
            disabled={isLocked}
            placeholder="Use global default"
            className={fieldClasses}
          />
        );
        break;
      
      case 'textarea':
        fieldElement = (
          <textarea
            value={currentValue || ''}
            onChange={(e) => updateOverride(field.key, e.target.value)}
            placeholder="Use global default"
            rows={9}
            className={`${fieldClasses} resize-vertical`}
          />
        );
        break;
      
      case 'password':
        fieldElement = (
          <input
            type="password"
            value={currentValue || ''}
            onChange={(e) => updateOverride(field.key, e.target.value)}
            placeholder="Use global default"
            className={fieldClasses}
          />
        );
        break;
      
      default:
        fieldElement = (
          <input
            type="text"
            value={currentValue || ''}
            onChange={(e) => updateOverride(field.key, e.target.value)}
            placeholder={field.placeholder || 'Use global default'}
            className={fieldClasses}
          />
        );
    }

    return (
      <div key={field.key} className={`space-y-2 ${isFieldOverridden ? 'relative p-4 bg-blue-50/50 dark:bg-blue-900/5 rounded-lg border border-blue-200/50 dark:border-blue-800/30' : ''}`}>
        <div className="flex items-center justify-between">
          <label className={`flex items-center gap-1.5 text-sm font-medium transition-colors ${
            isLocked
              ? 'text-gray-400 dark:text-gray-500'
              : isFieldOverridden
              ? 'text-blue-800 dark:text-blue-200 font-semibold'
              : 'text-gray-700 dark:text-gray-300'
          }`}>
            {field.label}
            {isLocked && (
              <span title={lockMessage} className="inline-flex items-center text-amber-500 dark:text-amber-400 cursor-help">
                <Info className="h-3.5 w-3.5" />
              </span>
            )}
          </label>
          {!isLocked && isFieldOverridden && (
            <div className="flex items-center space-x-2">
              <span className="inline-flex items-center px-2 py-1 rounded-full text-xs font-medium bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200">
                Overridden
              </span>
              <button
                onClick={() => revertField(field.key)}
                className="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium text-gray-600 dark:text-gray-400 hover:text-blue-700 dark:hover:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-900/20 transition-colors"
                title="Revert to global default"
              >
                <RotateCcw className="h-3 w-3 mr-1" />
                Revert
              </button>
            </div>
          )}
        </div>
        
        <div className="relative">
          {fieldElement}
        </div>
        
        <div className="text-xs">
          {isLocked ? (
            <p className="text-amber-600 dark:text-amber-400">{lockMessage}</p>
          ) : (
            <p className="text-gray-500 dark:text-gray-400">{field.description}</p>
          )}
        </div>
      </div>
    );
  };

  if (!isOpen) return null;

  return (
    <Modal isOpen={isOpen} onClose={cancelEdit} maxWidth="max-w-6xl" panelClassName="max-h-[90vh] overflow-hidden flex flex-col" ariaLabel={`PR-Agent Config: ${repositoryName}`}>
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-3">
            <Settings className="h-6 w-6 text-gray-500 dark:text-gray-400" />
            <div>
              <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                PR-Agent Config: {repositoryName}
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Repository-specific configuration overrides
              </p>
            </div>
          </div>
          
          <div className="flex items-center space-x-3">
            <button
              onClick={cancelEdit}
              className="flex items-center px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors"
            >
              <X className="h-4 w-4 mr-2" />
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || (!hasChanges() && hasExistingConfig)}
              className={`flex items-center px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                !saving && (hasChanges() || !hasExistingConfig)
                  ? 'text-white bg-blue-600 hover:bg-blue-700'
                  : 'text-gray-400 bg-gray-200 dark:bg-gray-700 cursor-not-allowed'
              }`}
            >
              <Save className="h-4 w-4 mr-2" />
              {saving ? 'Creating PR...' : hasExistingConfig ? 'Save & Update PR' : 'Create Config & PR'}
            </button>
          </div>
        </div>

        {/* Info Banner */}
        <div className="px-6 py-4 bg-gray-50 dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-start space-x-3">
            <Info className="h-5 w-5 text-gray-500 dark:text-gray-400 mt-0.5 flex-shrink-0" />
            <div className="text-gray-700 dark:text-gray-300 text-sm">
              <p className="font-medium">Repository Configuration Overrides</p>
              <p className="mt-1">
                Only override settings that should differ from global defaults. 
                <span className="font-medium text-blue-600 dark:text-blue-400"> Highlighted fields are overridden</span>. Use the revert button to restore defaults.
              </p>
            </div>
          </div>
        </div>

        {/* PR Status */}
        {prStatus?.status === 'pending' && (
          <div className="px-6 py-3 bg-orange-50 dark:bg-orange-900/10 border-b border-orange-100 dark:border-orange-900/20">
            <div className="flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <GitBranch className="h-4 w-4 text-orange-500 dark:text-orange-400" />
                <span className="text-sm text-orange-700 dark:text-orange-300">
                  Pending PR #{prStatus.number} - Changes will take effect when merged
                </span>
              </div>
              {prStatus.url && (
                <a
                  href={prStatus.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center text-sm text-orange-600 dark:text-orange-400 hover:text-orange-800 dark:hover:text-orange-200"
                >
                  View PR <ExternalLink className="h-3 w-3 ml-1" />
                </a>
              )}
            </div>
          </div>
        )}

        {loading ? (
          <div className="flex-1 flex items-center justify-center py-12">
            <div className="text-center">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-gray-400 mx-auto mb-4"></div>
              <p className="text-gray-600 dark:text-gray-300 font-medium">Loading configuration...</p>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">Fetching global settings and repository overrides</p>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex overflow-hidden">
            {/* Sidebar Navigation */}
            <div className="w-64 bg-gray-50 dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 p-4">
              <nav className="space-y-1">
                {Object.entries(configSections).map(([key, section]) => (
                  <button
                    key={key}
                    onClick={() => setActiveTab(key)}
                    className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                      activeTab === key
                        ? 'bg-white dark:bg-gray-700 text-gray-900 dark:text-white shadow-sm'
                        : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700'
                    }`}
                  >
                    <section.icon className="h-4 w-4 mr-3 flex-shrink-0" />
                    <span className="truncate">{section.title}</span>
                  </button>
                ))}
              </nav>
            </div>

            {/* Main Content */}
            <div className="flex-1 overflow-y-auto p-6">
              <div className="max-w-3xl">
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
                  <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center space-x-3">
                    {React.createElement(configSections[activeTab].icon, { className: "h-5 w-5 text-gray-500 dark:text-gray-400" })}
                    <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                      {configSections[activeTab].title}
                    </h3>
                  </div>

                  <div className="px-6 py-6">
                    <div className="space-y-6">
                      {configSections[activeTab].fields.map(field => renderField(field))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
    </Modal>
  );
};

export default PrAgentConfigEditor; 