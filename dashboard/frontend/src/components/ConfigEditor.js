import React, { useState, useEffect, useCallback, useContext } from 'react';
import { 
  Settings, 
  Save, 
  RotateCcw, 
  Brain, 
  Key, 
  Zap, 
  Database, 
  CheckSquare,
  AlertCircle,
  Info,
  X,
  Edit,
  Clock,
  MessageSquare,
  FileText,
  Lightbulb,
  Github,
  Gauge,
  Shield
} from 'lucide-react';
import api from '../services/api';
import { ToastContext } from '../contexts/ToastContext';
import ViewHeader from './ViewHeader';

const ConfigEditor = ({ navigationTarget = null }) => {
  const [config, setConfig] = useState(null);
  const [originalConfig, setOriginalConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);
  const [initialLoadComplete, setInitialLoadComplete] = useState(false);
  const [activeTab, setActiveTab] = useState('models');

  const [errors, setErrors] = useState({});
  const [animatingCheckbox, setAnimatingCheckbox] = useState(null);
  const [dismissedInfo, setDismissedInfo] = useState(() => {
    return localStorage.getItem('dismissedConfigInfo') === 'true';
  });
  const { showSuccess, showError } = useContext(ToastContext);

  // Available models categorized by type
  const availableModels = {
    premium: [
      'anthropic/claude-opus-4-20250514',
      'anthropic/claude-sonnet-4-20250514',
      'anthropic/claude-3-7-sonnet-20250219',
      'o1-2024-12-17',
      'o1',
      'o3-mini',
      'o3',
      'o4-mini'
    ],
    standard: [
      'anthropic/claude-3-5-sonnet-20241022',
      'anthropic/claude-3-5-haiku-20241022',
      'gpt-4o',
      'gpt-4o-mini',
      'gpt-4-turbo',
      'gpt-4'
    ],
    budget: [
      'gpt-3.5-turbo',
      'gpt-4o-mini',
      'o4-mini'
    ],
    reasoning: [
      'anthropic/claude-opus-4-20250514',
      'anthropic/claude-3-7-sonnet-20250219',
      'o1-2024-12-17',
      'o1',
      'o3-mini',
      'o3',
      'o4-mini',
      'deepseek/deepseek-reasoner'
    ]
  };

  const availableActions = [
    { key: 'pr_reviewer', label: 'Review', description: 'Automated PR reviews' },
    { key: 'pr_description', label: 'Describe', description: 'Generate PR descriptions' },
    { key: 'pr_code_suggestions', label: 'Improve', description: 'Code suggestions and improvements' },
    { key: 'pr_questions', label: 'Ask', description: 'Answer questions about the PR' },
    { key: 'pr_test', label: 'Test', description: 'Generate unit tests' },
    { key: 'pr_add_docs', label: 'Documentation', description: 'Add documentation' },
    { key: 'pr_update_changelog', label: 'Changelog', description: 'Update changelog' }
  ];

  // Check if there are any changes - only after initial load is complete and both configs are loaded
  // Use a more stable comparison to prevent flickering - start with explicit false
  const hasChanges = React.useMemo(() => {
    // Explicitly return false if any condition isn't met to prevent flickering
    if (!initialLoadComplete || loading || !config || !originalConfig || !editing) {
      return false;
    }
    
    // Additional check to ensure configs are fully populated
    if (Object.keys(config).length === 0 || Object.keys(originalConfig).length === 0) {
      return false;
    }
    
    return JSON.stringify(config) !== JSON.stringify(originalConfig);
  }, [initialLoadComplete, loading, config, originalConfig, editing]);

  useEffect(() => {
    fetchConfig();
  }, []);

  // Handle navigation target (e.g., animate checkbox)
  useEffect(() => {
    if (navigationTarget === 'context-service-enable' && config && initialLoadComplete) {
      // Wait for rendering, then scroll and animate
      setTimeout(() => {
        const element = document.getElementById('context-service-section');
        if (element) {
          // Scroll to center the element in view
          element.scrollIntoView({ 
            behavior: 'smooth', 
            block: 'center',
            inline: 'nearest'
          });

          // Animate the checkbox to draw attention
          setAnimatingCheckbox('context-enabled');
          setTimeout(() => {
            setAnimatingCheckbox(null);
          }, 2000); // Stop animation after 2 seconds
        }
      }, 100);
    }
  }, [navigationTarget, config, initialLoadComplete]);

  const fetchConfig = async () => {
    try {
      setLoading(true);
      const response = await api.getConfig();
      
      // Extract the actual config data from the API response
      let configData = response.data?.data || response.data || response;
      
      // Transform the PR-Agent config structure to match our UI expectations
      const transformedConfig = {
        // Main config section
        model: configData.config?.model || 'anthropic/claude-3-5-sonnet-20241022',
        model_reasoning: configData.config?.model_reasoning || configData.config?.model || 'anthropic/claude-3-5-sonnet-20241022',
        model_weak: configData.config?.model_weak || 'gpt-4o-mini',
        fallback_models: configData.config?.fallback_models || ['gpt-4o-mini'],
        reasoning_effort: configData.config?.reasoning_effort || 'high',
        max_model_tokens: configData.config?.max_model_tokens || 94000,
        temperature: configData.config?.temperature || 0.2,
        
        // Context service
        csharp_code_context_service: {
          enabled: configData.csharp_code_context_service?.enabled || false,
          default_depth: configData.csharp_code_context_service?.default_depth || 1,
          default_mode: configData.csharp_code_context_service?.default_mode || 'Minified',
          timeout: configData.csharp_code_context_service?.timeout || 180,
          url: configData.csharp_code_context_service?.url || ''
        },
        
        // Enabled actions
        enabled_actions: configData.enabled_actions || {
          pr_reviewer: true,
          pr_description: true,
          pr_code_suggestions: true,
          pr_questions: true,
          pr_test: false,
          pr_add_docs: false,
          pr_update_changelog: false
        },
        
        // PR Reviewer settings
        pr_reviewer: {
          num_max_findings: configData.pr_reviewer?.num_max_findings || 15,
          extra_instructions: configData.pr_reviewer?.extra_instructions || ''
        },
        
        // PR Description settings
        pr_description: {
          extra_instructions: configData.pr_description?.extra_instructions || '',
          publish_labels: configData.pr_description?.publish_labels || false,
          generate_ai_title: configData.pr_description?.generate_ai_title || false,
          enable_large_pr_handling: configData.pr_description?.enable_large_pr_handling || true
        },
        
        // PR Code Suggestions settings
        pr_code_suggestions: {
          extra_instructions: configData.pr_code_suggestions?.extra_instructions || '',
          focus_only_on_problems: configData.pr_code_suggestions?.focus_only_on_problems || false,
          suggestions_score_threshold: configData.pr_code_suggestions?.suggestions_score_threshold || 0,
          commitable_code_suggestions: configData.pr_code_suggestions?.commitable_code_suggestions || true,
          dual_publishing_score_threshold: configData.pr_code_suggestions?.dual_publishing_score_threshold || -1
        },
        
        // GitHub settings
        github: {
          bot_user: configData.github?.bot_user || 'github-actions[bot]',
          override_deployment_type: configData.github?.override_deployment_type || true,
          pr_commands: configData.github?.pr_commands || [
            '/describe --pr_description.final_update_message=false',
            '/review',
            '/improve'
          ]
        },
        
        // Best Practices settings
        best_practices: {
          content: configData.best_practices?.content || '',
          organization_name: configData.best_practices?.organization_name || '',
          max_lines_allowed: configData.best_practices?.max_lines_allowed || 800,
          enable_global_best_practices: configData.best_practices?.enable_global_best_practices || false
        },
        
        // Auto Best Practices settings
        auto_best_practices: {
          enable_auto_best_practices: configData.auto_best_practices?.enable_auto_best_practices || true,
          utilize_auto_best_practices: configData.auto_best_practices?.utilize_auto_best_practices || true,
          extra_instructions: configData.auto_best_practices?.extra_instructions || '',
          content: configData.auto_best_practices?.content || '',
          max_patterns: configData.auto_best_practices?.max_patterns || 5
        },
        
        // Dashboard settings
        dashboard: {
          URL: configData.dashboard?.URL || configData.DASHBOARD?.URL || 'http://localhost:8000/',
          ENABLED: configData.dashboard?.ENABLED !== false && configData.DASHBOARD?.ENABLED !== false,
          API_KEY: configData.dashboard?.API_KEY || configData.DASHBOARD?.API_KEY || ''
        },
        
        // Developer Time Estimation settings
        pr_dev_time_estimation: {
          enabled: configData.pr_dev_time_estimation?.enabled !== false,
          model: configData.pr_dev_time_estimation?.model || '',
          fallback_to_heuristic: configData.pr_dev_time_estimation?.fallback_to_heuristic !== false,
          estimation_timeout_seconds: configData.pr_dev_time_estimation?.estimation_timeout_seconds || 30,
          confidence_threshold: configData.pr_dev_time_estimation?.confidence_threshold || 'medium'
        },
        
        // API keys (don't expose actual values for security)
        api_keys: {
          openai: configData.api_keys?.openai ? '***' : '',
          anthropic: configData.api_keys?.anthropic ? '***' : '',
          google: configData.api_keys?.google ? '***' : ''
        }
      };
      
      setConfig(transformedConfig);
      setOriginalConfig(JSON.parse(JSON.stringify(transformedConfig))); // Deep copy
    } catch (error) {
      // Default configuration on error
      const defaultConfig = {
        model: 'anthropic/claude-sonnet-4-20250514',
        model_reasoning: 'anthropic/claude-opus-4-20250514',
        model_weak: 'o4-mini',
        fallback_models: ['o4-mini'],
        reasoning_effort: 'high',
        max_model_tokens: 94000,
        temperature: 0.2,
        csharp_code_context_service: {
          enabled: true,
          default_depth: 1,
          default_mode: 'Minified',
          timeout: 180
        },
        enabled_actions: {
          pr_reviewer: true,
          pr_description: true,
          pr_code_suggestions: true,
          pr_questions: true,
          pr_test: false,
          pr_add_docs: false,
          pr_update_changelog: false
        },
        pr_reviewer: {
          num_max_findings: 15,
          extra_instructions: ''
        },
        pr_description: {
          extra_instructions: '',
          publish_labels: false,
          generate_ai_title: false,
          enable_large_pr_handling: true
        },
        pr_code_suggestions: {
          extra_instructions: '',
          focus_only_on_problems: false,
          suggestions_score_threshold: 0,
          commitable_code_suggestions: true,
          dual_publishing_score_threshold: -1
        },
        github: {
          bot_user: 'github-actions[bot]',
          override_deployment_type: true,
          pr_commands: [
            '/describe --pr_description.final_update_message=false',
            '/review',
            '/improve'
          ]
        },
        best_practices: {
          content: '',
          organization_name: '',
          max_lines_allowed: 800,
          enable_global_best_practices: false
        },
        auto_best_practices: {
          enable_auto_best_practices: true,
          utilize_auto_best_practices: true,
          extra_instructions: '',
          content: '',
          max_patterns: 5
        },
        dashboard: {
          URL: 'http://localhost:8000/',
          ENABLED: true,
          API_KEY: ''
        },
        pr_dev_time_estimation: {
          enabled: false,
          model: '',
          fallback_to_heuristic: false,
          estimation_timeout_seconds: 30,
          confidence_threshold: 'medium'
        },
        api_keys: {
          openai: '',
          anthropic: '',
          google: ''
        }
      };
      setConfig(defaultConfig);
      setOriginalConfig(JSON.parse(JSON.stringify(defaultConfig)));
    } finally {
      setLoading(false);
      // Use a small delay to ensure state is fully settled before allowing changes detection
      setTimeout(() => {
        setInitialLoadComplete(true);
      }, 100);
    }
  };

  const saveConfig = async () => {
    try {
      setSaving(true);
      setErrors({});
      
      // Validate configuration
      const validationErrors = validateConfig(config);
      if (Object.keys(validationErrors).length > 0) {
        setErrors(validationErrors);
        showError('Validation Failed', 'Please fix the configuration errors before saving.');
        return;
      }

      const response = await api.updateConfig(config);
      setOriginalConfig(JSON.parse(JSON.stringify(config))); // Update original after successful save
      setEditing(false); // Exit edit mode on successful save
      showSuccess('Configuration Saved', 'Your configuration has been saved successfully!');
    } catch (error) {
      setErrors({ general: 'Failed to save configuration. Please try again.' });
      showError('Save Failed', 'Failed to save configuration. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const validateConfig = (config) => {
    const errors = {};
    
    if (!config.model) {
      errors.model = 'Default model is required';
    }
    
    if (config.max_model_tokens && (config.max_model_tokens < 1000 || config.max_model_tokens > 2000000)) {
      errors.max_model_tokens = 'Max tokens must be between 1,000 and 2,000,000';
    }
    
    if (config.temperature !== undefined && (config.temperature < 0 || config.temperature > 2)) {
      errors.temperature = 'Temperature must be between 0 and 2';
    }

    // Validate context service URL if service is enabled
    if (config.csharp_code_context_service?.enabled) {
      const url = config.csharp_code_context_service?.url;
      if (!url || url.trim() === '') {
        errors['csharp_code_context_service.url'] = 'Service URL is required when context service is enabled';
      } else if (url.trim()) {
        try {
          new URL(url.trim());
        } catch {
          errors['csharp_code_context_service.url'] = 'Please enter a valid URL (e.g., https://localhost:7138)';
        }
      }
    }

    // Validate time estimation settings
    if (config.pr_dev_time_estimation?.enabled) {
      const timeout = config.pr_dev_time_estimation?.estimation_timeout_seconds;
      if (timeout && (timeout < 10 || timeout > 120)) {
        errors['pr_dev_time_estimation.estimation_timeout_seconds'] = 'Timeout must be between 10 and 120 seconds';
      }
      
      const confidence = config.pr_dev_time_estimation?.confidence_threshold;
      if (confidence && !['low', 'medium', 'high'].includes(confidence)) {
        errors['pr_dev_time_estimation.confidence_threshold'] = 'Confidence threshold must be low, medium, or high';
      }
    }

    // Validate PR reviewer settings
    if (config.pr_reviewer?.num_max_findings) {
      const findings = config.pr_reviewer.num_max_findings;
      if (findings < 1 || findings > 50) {
        errors['pr_reviewer.num_max_findings'] = 'Max findings must be between 1 and 50';
      }
    }

    // Validate PR code suggestions settings
    if (config.pr_code_suggestions?.suggestions_score_threshold !== undefined) {
      const threshold = config.pr_code_suggestions.suggestions_score_threshold;
      if (threshold < 0 || threshold > 10) {
        errors['pr_code_suggestions.suggestions_score_threshold'] = 'Score threshold must be between 0 and 10';
      }
    }

    if (config.pr_code_suggestions?.dual_publishing_score_threshold !== undefined) {
      const threshold = config.pr_code_suggestions.dual_publishing_score_threshold;
      if (threshold < -1 || threshold > 10) {
        errors['pr_code_suggestions.dual_publishing_score_threshold'] = 'Dual publishing threshold must be between -1 and 10';
      }
    }

    // Validate GitHub settings
    if (config.github?.bot_user && config.github.bot_user.trim() === '') {
      errors['github.bot_user'] = 'Bot user cannot be empty';
    }

    // Validate best practices settings
    if (config.best_practices?.max_lines_allowed) {
      const maxLines = config.best_practices.max_lines_allowed;
      if (maxLines < 100 || maxLines > 2000) {
        errors['best_practices.max_lines_allowed'] = 'Max lines must be between 100 and 2000';
      }
    }

    if (config.auto_best_practices?.max_patterns) {
      const maxPatterns = config.auto_best_practices.max_patterns;
      if (maxPatterns < 1 || maxPatterns > 20) {
        errors['auto_best_practices.max_patterns'] = 'Max patterns must be between 1 and 20';
      }
    }

    // Validate dashboard settings
    if (config.dashboard?.ENABLED && config.dashboard?.URL) {
      const url = config.dashboard.URL.trim();
      if (url && url !== '') {
        try {
          new URL(url);
        } catch {
          errors['dashboard.URL'] = 'Please enter a valid URL (e.g., http://localhost:8000/)';
        }
      }
    }

    return errors;
  };

  const startEdit = () => {
    setEditing(true);
  };

  const cancelEdit = () => {
    if (originalConfig) {
      setConfig(JSON.parse(JSON.stringify(originalConfig)));
      setErrors({});
    }
    setEditing(false);
  };

  const resetToDefaults = () => {
    if (window.confirm('Are you sure you want to reset all settings to defaults? This cannot be undone.')) {
      setConfig(JSON.parse(JSON.stringify(originalConfig))); // Reset to original
      showSuccess('Configuration Reset', 'Settings have been reset to last saved state.');
    }
  };



  // Optimized updateConfig function with useCallback to prevent unnecessary re-renders
  const updateConfig = useCallback((path, value) => {
    setConfig(prev => {
      if (!prev) return prev; // Don't update if config is not loaded yet
      const newConfig = { ...prev };
      const keys = path.split('.');
      let current = newConfig;
      
      for (let i = 0; i < keys.length - 1; i++) {
        if (!current[keys[i]]) current[keys[i]] = {};
        current = current[keys[i]];
      }
      
      current[keys[keys.length - 1]] = value;
      return newConfig;
    });
    
    // Clear any related errors when the user changes a value
    setErrors(prev => {
      const newErrors = { ...prev };
      const mainKey = path.split('.')[0];
      if (newErrors[mainKey]) {
        delete newErrors[mainKey];
      }
      return newErrors;
    });
  }, []);

  // Smart checkbox styling that makes checked disabled checkboxes more obvious
  const getCheckboxClasses = useCallback((checked, disabled) => {
    const baseClasses = "h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 transition-all duration-200";
    
    if (disabled && checked) {
      // Checked but disabled - make it obvious
      return `${baseClasses} opacity-100 bg-blue-500 border-blue-500 text-white cursor-not-allowed`;
    } else if (disabled) {
      // Unchecked and disabled - make it subtle
      return `${baseClasses} opacity-40 cursor-not-allowed`;
    } else {
      // Enabled - normal styling
      return `${baseClasses} hover:border-primary-400 dark:hover:border-primary-500`;
    }
  }, []);

  const ModelSelector = useCallback(({ label, value, onChange, models, description, editing }) => (
    <div className="space-y-2">
      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
        {description && (
          <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal">{description}</span>
        )}
      </label>
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        disabled={!editing}
        className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        <option value="">Select a model...</option>
        {Object.entries(models).map(([category, modelList]) => (
          <optgroup key={category} label={category.charAt(0).toUpperCase() + category.slice(1)}>
            {modelList.map(model => (
              <option key={model} value={model}>{model}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  ), []);

  const SectionHeader = useCallback(({ title, icon: Icon, children }) => (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
      <div className="px-6 py-4 flex items-center space-x-3">
        <Icon className="h-5 w-5 text-primary-600 dark:text-primary-400" />
        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>
      </div>
      <div className="px-6 pb-6 border-t border-gray-200 dark:border-gray-700">
        {children}
      </div>
    </div>
  ), []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary-600"></div>
        <span className="ml-3 text-gray-600 dark:text-gray-300">Loading configuration...</span>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header with Edit/Save/Cancel buttons */}
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700">
        <div className="px-6 py-4 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <Settings className="h-6 w-6 text-primary-600 dark:text-primary-400" />
            <div>
              <h1 className="text-xl font-semibold text-gray-900 dark:text-white">AI Config</h1>
              <p className="text-sm text-gray-600 dark:text-gray-400">Manage AI models, performance settings, and API keys</p>
            </div>
          </div>
          
          <div className="flex items-center space-x-3">
            {!editing ? (
              <button
                onClick={startEdit}
                className="flex items-center px-4 py-2 text-sm font-medium text-blue-600 bg-blue-50 dark:bg-blue-900/30 dark:text-blue-400 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors duration-200"
              >
                <Edit className="h-4 w-4 mr-2" />
                Edit
              </button>
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
                  onClick={saveConfig}
                  disabled={saving || !hasChanges}
                  className={`flex items-center px-4 py-2 text-sm font-medium rounded-lg transition-colors duration-200 ${
                    !saving && hasChanges
                      ? 'text-white bg-blue-600 hover:bg-blue-700 shadow-sm hover:shadow-md'
                      : 'text-gray-400 bg-gray-100 dark:bg-gray-700 cursor-not-allowed'
                  }`}
                >
                  <Save className="h-4 w-4 mr-2" />
                  {saving ? 'Saving...' : 'Save Changes'}
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Configuration Info */}
      {!dismissedInfo && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
          <div className="flex items-start">
            <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2 mt-0.5 flex-shrink-0" />
            <div className="flex-1 text-blue-800 dark:text-blue-200 text-sm">
              <p className="font-medium mb-1">Configuration Hierarchy (Dynaconf)</p>
              <p>You are modifying the base configuration. Note that:</p>
              <ul className="list-disc list-inside mt-2 space-y-1 text-xs opacity-90">
                <li>Repository-specific <code className="bg-blue-100 dark:bg-blue-900/40 px-1 rounded">.pr_agent.toml</code> files can override these settings</li>
                <li>Environment variables take precedence over both base config and repository files</li>
                <li>Changes here affect the default behavior for all repositories</li>
              </ul>
            </div>
            <button
              onClick={() => {
                setDismissedInfo(true);
                localStorage.setItem('dismissedConfigInfo', 'true');
              }}
              className="ml-3 text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-200 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Error Messages */}
      {errors.general && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-md p-4">
          <div className="flex items-center">
            <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-2" />
            <span className="text-red-800 dark:text-red-200">{errors.general}</span>
          </div>
        </div>
      )}

      {/* Main Layout with Sidebar */}
      <div className="flex gap-3">
        {/* Sidebar Navigation */}
        <div className="w-48 flex-shrink-0">
          <nav className="space-y-1 sticky top-6">
              <button
                onClick={() => setActiveTab('models')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'models'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <Brain className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">AI Models</span>
              </button>
              <button
                onClick={() => setActiveTab('context')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'context'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <Database className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">Code Context</span>
              </button>
              <button
                onClick={() => setActiveTab('actions')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'actions'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <CheckSquare className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">Enabled Actions</span>
              </button>
              <button
                onClick={() => setActiveTab('pr-reviewer')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'pr-reviewer'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <MessageSquare className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">PR Reviewer</span>
              </button>
              <button
                onClick={() => setActiveTab('pr-description')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'pr-description'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <FileText className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">PR Description</span>
              </button>
              <button
                onClick={() => setActiveTab('pr-code-suggestions')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'pr-code-suggestions'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <Lightbulb className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">Code Suggestions</span>
              </button>
              <button
                onClick={() => setActiveTab('github')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'github'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <Github className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">GitHub</span>
              </button>
              <button
                onClick={() => setActiveTab('best-practices')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'best-practices'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <Shield className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">Best Practices</span>
              </button>
              <button
                onClick={() => setActiveTab('dashboard')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'dashboard'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <Gauge className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">Dashboard</span>
              </button>
              <button
                onClick={() => setActiveTab('time-estimation')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'time-estimation'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <Clock className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">Time Estimation</span>
              </button>
              <button
                onClick={() => setActiveTab('advanced')}
                className={`w-full flex items-center px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'advanced'
                    ? 'bg-blue-50 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-50 dark:hover:bg-gray-700/50'
                }`}
              >
                <Settings className="h-4 w-4 mr-3 flex-shrink-0" />
                <span className="truncate">Advanced</span>
              </button>
            </nav>
        </div>

        {/* Main Content Area */}
        <div className="flex-1 min-w-0">
          <div className="space-y-6">
        {/* AI Models Tab */}
        {activeTab === 'models' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            {/* AI Models Section */}
            <SectionHeader title="AI Models & API Keys" icon={Brain}>
              <div className="space-y-6 pt-4">
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                  <ModelSelector
                    label="Default Model"
                    value={config?.model}
                    onChange={(value) => updateConfig('model', value)}
                    models={availableModels}
                    description="Primary model for most operations"
                    editing={editing}
                  />
                  
                  <ModelSelector
                    label="Reasoning Model"
                    value={config?.model_reasoning}
                    onChange={(value) => updateConfig('model_reasoning', value)}
                    models={{ reasoning: availableModels.reasoning }}
                    description="Dedicated model for complex reasoning tasks"
                    editing={editing}
                  />
                  
                  <ModelSelector
                    label="Simple/Budget Model"
                    value={config?.model_weak}
                    onChange={(value) => updateConfig('model_weak', value)}
                    models={{ budget: availableModels.budget }}
                    description="Lightweight model for simple tasks"
                    editing={editing}
                  />
                </div>

                {/* API Keys */}
                <div className="border-t border-gray-200 dark:border-gray-700 pt-6">
                  <h4 className="text-md font-medium text-gray-900 dark:text-white mb-4 flex items-center">
                    <Key className="h-4 w-4 mr-2" />
                    API Keys
                  </h4>
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">OpenAI API Key</label>
                      <input
                        type="password"
                        value={config.api_keys?.openai || ''}
                        onChange={(e) => updateConfig('api_keys.openai', e.target.value)}
                        placeholder="sk-..."
                        disabled={!editing}
                        className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Anthropic API Key</label>
                      <input
                        type="password"
                        value={config.api_keys?.anthropic || ''}
                        onChange={(e) => updateConfig('api_keys.anthropic', e.target.value)}
                        placeholder="sk-ant-..."
                        disabled={!editing}
                        className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">Google API Key</label>
                      <input
                        type="password"
                        value={config.api_keys?.google || ''}
                        onChange={(e) => updateConfig('api_keys.google', e.target.value)}
                        placeholder="AIza..."
                        disabled={!editing}
                        className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                    </div>
                  </div>
                </div>
              </div>
            </SectionHeader>

            {/* Reasoning & Performance Section */}
            <SectionHeader title="Reasoning & Performance" icon={Zap}>
              <div className="space-y-6 pt-4">
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Reasoning Effort
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal">Higher effort = better quality, slower response</span>
                    </label>
                    <select
                      value={config.reasoning_effort || 'high'}
                      onChange={(e) => updateConfig('reasoning_effort', e.target.value)}
                      disabled={!editing}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <option value="low">Low - Fast responses</option>
                      <option value="medium">Medium - Balanced</option>
                      <option value="high">High - Best quality</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Max Model Tokens
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal">Maximum tokens per API call</span>
                    </label>
                    <input
                      type="number"
                      value={config.max_model_tokens || 94000}
                      onChange={(e) => updateConfig('max_model_tokens', parseInt(e.target.value))}
                      min="1000"
                      max="2000000"
                      disabled={!editing}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    {errors.max_model_tokens && (
                      <p className="text-sm text-red-600 dark:text-red-400 mt-1">{errors.max_model_tokens}</p>
                    )}
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Temperature
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal">0 = deterministic, 2 = very creative</span>
                    </label>
                    <input
                      type="number"
                      value={config.temperature || 0.2}
                      onChange={(e) => updateConfig('temperature', parseFloat(e.target.value))}
                      min="0"
                      max="2"
                      step="0.1"
                      disabled={!editing}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    {errors.temperature && (
                      <p className="text-sm text-red-600 dark:text-red-400 mt-1">{errors.temperature}</p>
                    )}
                  </div>
                </div>
              </div>
            </SectionHeader>
          </div>
        )}

        {/* Code Context Tab */}
        {activeTab === 'context' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            <div id="context-service-section">
              <SectionHeader title="Code Context Service" icon={Database}>
                <div className="space-y-6 pt-4">
                  <div className={`flex items-center space-x-3 p-2 rounded-md transition-all duration-500 ${
                    animatingCheckbox === 'context-enabled' 
                      ? 'bg-blue-50 dark:bg-blue-900/20 ring-2 ring-blue-200 dark:ring-blue-800' 
                      : ''
                  }`}>
                    <input
                      type="checkbox"
                      id="context-enabled"
                      checked={config.csharp_code_context_service?.enabled || false}
                      onChange={(e) => updateConfig('csharp_code_context_service.enabled', e.target.checked)}
                      disabled={!editing}
                      className={`${getCheckboxClasses(config.csharp_code_context_service?.enabled || false, !editing)} ${
                        animatingCheckbox === 'context-enabled' 
                          ? 'ring-4 ring-blue-500 ring-opacity-75 animate-pulse scale-125 shadow-lg' 
                          : ''
                      }`}
                    />
                    <label htmlFor="context-enabled" className={`text-sm font-medium transition-all duration-300 ${
                      animatingCheckbox === 'context-enabled'
                        ? 'text-blue-700 dark:text-blue-300 font-semibold'
                        : 'text-gray-700 dark:text-gray-300'
                    }`}>
                      Enable Code Context Service
                    </label>
                    <Info className="h-4 w-4 text-gray-400 dark:text-gray-500" title="Provides additional code context for better suggestions" />
                  </div>

                  {config.csharp_code_context_service?.enabled && (
                    <div className="space-y-6 pl-7">
                      <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                          Service URL
                          <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal">Base URL for the context service</span>
                        </label>
                        <input
                          type="url"
                          value={config.csharp_code_context_service?.url || ''}
                          onChange={(e) => updateConfig('csharp_code_context_service.url', e.target.value)}
                          placeholder="https://localhost:7138"
                          disabled={!editing}
                          className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                        />
                        {errors['csharp_code_context_service.url'] && (
                          <p className="text-sm text-red-600 dark:text-red-400 mt-1">{errors['csharp_code_context_service.url']}</p>
                        )}
                      </div>
                      
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Analysis Depth</label>
                          <select
                            value={config.csharp_code_context_service?.default_depth || 1}
                            onChange={(e) => updateConfig('csharp_code_context_service.default_depth', parseInt(e.target.value))}
                            disabled={!editing}
                            className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            {[1, 2, 3, 4, 5].map(depth => (
                              <option key={depth} value={depth}>Level {depth}</option>
                            ))}
                          </select>
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Analysis Mode</label>
                          <select
                            value={config.csharp_code_context_service?.default_mode || 'Minified'}
                            onChange={(e) => updateConfig('csharp_code_context_service.default_mode', e.target.value)}
                            disabled={!editing}
                            className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                          >
                            <option value="Full">Full - Complete analysis</option>
                            <option value="Minified">Minified - Optimized analysis</option>
                          </select>
                        </div>

                        <div>
                          <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Timeout (seconds)</label>
                          <input
                            type="number"
                            value={config.csharp_code_context_service?.timeout || 180}
                            onChange={(e) => updateConfig('csharp_code_context_service.timeout', parseInt(e.target.value))}
                            min="30"
                            max="600"
                            disabled={!editing}
                            className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                          />
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </SectionHeader>
            </div>
          </div>
        )}

        {/* Enabled Actions Tab */}
        {activeTab === 'actions' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            <SectionHeader title="Enabled Actions" icon={CheckSquare}>
              <div className="space-y-4 pt-4">
                <p className="text-sm text-gray-600 dark:text-gray-400">Select which PR-Agent actions are available for use:</p>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {availableActions.map(action => {
                    const isEnabled = config.enabled_actions?.[action.key] || false;
                    
                    return (
                      <div
                        key={action.key}
                        onClick={() => editing && updateConfig(`enabled_actions.${action.key}`, !isEnabled)}
                        className={`relative p-4 rounded-lg border-2 transition-all duration-300 ${
                          isEnabled
                            ? `border-green-300 dark:border-green-600 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/30 dark:to-green-800/30 ${
                                editing ? 'shadow-lg shadow-green-200/40 dark:shadow-green-400/20' : ''
                              }`
                            : `border-gray-200 dark:border-gray-700 bg-gradient-to-br from-gray-50 to-gray-100 dark:from-gray-800/50 dark:to-gray-700/50 ${
                                editing ? 'shadow-lg shadow-gray-200/40 dark:shadow-gray-400/20' : ''
                              }`
                        } ${
                          editing 
                            ? 'cursor-pointer hover:border-blue-400 dark:hover:border-blue-500 hover:shadow-2xl hover:-translate-y-1 transform shadow-lg' 
                            : 'cursor-default shadow-sm'
                        }`}
                      >
                        <div>
                          <h4 className={`text-base font-medium transition-colors ${
                            isEnabled
                              ? 'text-green-800 dark:text-green-200'
                              : 'text-gray-700 dark:text-gray-300'
                          }`}>
                            {action.label}
                          </h4>
                          <p className={`text-sm mt-1 transition-colors ${
                            isEnabled
                              ? 'text-green-600 dark:text-green-300'
                              : 'text-gray-500 dark:text-gray-400'
                          }`}>
                            {action.description}
                          </p>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </SectionHeader>
          </div>
        )}

        {/* PR Reviewer Tab */}
        {activeTab === 'pr-reviewer' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            <SectionHeader title="PR Reviewer Settings" icon={MessageSquare}>
              <div className="space-y-6 pt-4">
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
                  <div className="flex items-center">
                    <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
                    <span className="text-blue-800 dark:text-blue-200 text-sm">
                      Configure how PR-Agent performs automated code reviews. These settings control the depth and quality of review output.
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Maximum Findings per Review
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Limits the number of issues reported to prevent overwhelming reviews. Higher values provide more comprehensive feedback but may be harder to process.
                      </span>
                    </label>
                    <input
                      type="number"
                      value={config.pr_reviewer?.num_max_findings || 15}
                      onChange={(e) => updateConfig('pr_reviewer.num_max_findings', parseInt(e.target.value))}
                      min="1"
                      max="50"
                      disabled={!editing}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      Recommended: 10-20 findings for balanced reviews
                    </p>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Extra Instructions for Reviewer
                    <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                      Additional guidance for the AI reviewer. Specify what to focus on, coding standards, or areas to ignore.
                    </span>
                  </label>
                  <textarea
                    value={config.pr_reviewer?.extra_instructions || ''}
                    onChange={(e) => updateConfig('pr_reviewer.extra_instructions', e.target.value)}
                    disabled={!editing}
                    placeholder="e.g., Focus on security vulnerabilities and performance issues. Ignore minor style issues. Pay special attention to error handling and input validation."
                    rows={8}
                    className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed resize-vertical"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    These instructions will guide the AI reviewer's analysis and feedback priorities.
                  </p>
                </div>
              </div>
            </SectionHeader>
          </div>
        )}

        {/* PR Description Tab */}
        {activeTab === 'pr-description' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            <SectionHeader title="PR Description Settings" icon={FileText}>
              <div className="space-y-6 pt-4">
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
                  <div className="flex items-center">
                    <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
                    <span className="text-blue-800 dark:text-blue-200 text-sm">
                      Control how PR-Agent generates and formats pull request descriptions, including titles, labels, and handling of large PRs.
                    </span>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      id="publish-labels"
                      checked={config.pr_description?.publish_labels || false}
                      onChange={(e) => updateConfig('pr_description.publish_labels', e.target.checked)}
                      disabled={!editing}
                      className={getCheckboxClasses(config.pr_description?.publish_labels || false, !editing)}
                    />
                    <label htmlFor="publish-labels" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Publish AI-generated labels to PR
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Automatically adds semantic labels like "enhancement", "bug", "documentation" based on PR content analysis.
                      </span>
                    </label>
                  </div>

                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      id="generate-ai-title"
                      checked={config.pr_description?.generate_ai_title || false}
                      onChange={(e) => updateConfig('pr_description.generate_ai_title', e.target.checked)}
                      disabled={!editing}
                      className={getCheckboxClasses(config.pr_description?.generate_ai_title || false, !editing)}
                    />
                    <label htmlFor="generate-ai-title" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Generate AI-powered PR title
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Replaces the existing PR title with an AI-generated one that summarizes the changes. Use carefully as it overwrites manual titles.
                      </span>
                    </label>
                  </div>

                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      id="enable-large-pr-handling"
                      checked={config.pr_description?.enable_large_pr_handling !== false}
                      onChange={(e) => updateConfig('pr_description.enable_large_pr_handling', e.target.checked)}
                      disabled={!editing}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <label htmlFor="enable-large-pr-handling" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Enable special handling for large PRs
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Uses optimized processing for PRs with many files or large changes. Breaks down analysis into chunks to avoid token limits.
                      </span>
                    </label>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Extra Instructions for Description Generation
                    <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                      Customize how PR descriptions are generated. Specify format preferences, required sections, or content to emphasize.
                    </span>
                  </label>
                  <textarea
                    value={config.pr_description?.extra_instructions || ''}
                    onChange={(e) => updateConfig('pr_description.extra_instructions', e.target.value)}
                    disabled={!editing}
                    placeholder="e.g., Always include a 'Breaking Changes' section if applicable. Use technical language and include performance implications. Focus on business impact."
                    rows={8}
                    className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed resize-vertical"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    These instructions will influence the style and content of generated PR descriptions.
                  </p>
                </div>
              </div>
            </SectionHeader>
          </div>
        )}

        {/* PR Code Suggestions Tab */}
        {activeTab === 'pr-code-suggestions' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            <SectionHeader title="Code Suggestions Settings" icon={Lightbulb}>
              <div className="space-y-6 pt-4">
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
                  <div className="flex items-center">
                    <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
                    <span className="text-blue-800 dark:text-blue-200 text-sm">
                      Configure AI-powered code suggestions and improvements. Control quality thresholds, focus areas, and suggestion types.
                    </span>
                  </div>
                </div>

                <div className="space-y-4">
                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      id="focus-only-on-problems"
                      checked={config.pr_code_suggestions?.focus_only_on_problems || false}
                      onChange={(e) => updateConfig('pr_code_suggestions.focus_only_on_problems', e.target.checked)}
                      disabled={!editing}
                      className={getCheckboxClasses(config.pr_code_suggestions?.focus_only_on_problems || false, !editing)}
                    />
                    <label htmlFor="focus-only-on-problems" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Focus only on problems (not enhancements)
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        When enabled, AI will prioritize bugs, security issues, and critical problems over style improvements and optimizations.
                      </span>
                    </label>
                  </div>

                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      id="commitable-code-suggestions"
                      checked={config.pr_code_suggestions?.commitable_code_suggestions !== false}
                      onChange={(e) => updateConfig('pr_code_suggestions.commitable_code_suggestions', e.target.checked)}
                      disabled={!editing}
                      className={getCheckboxClasses(config.pr_code_suggestions?.commitable_code_suggestions !== false, !editing)}
                    />
                    <label htmlFor="commitable-code-suggestions" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Enable commitable code suggestions
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Allows developers to commit suggestions directly from PR comments. Provides one-click code improvements.
                      </span>
                    </label>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Suggestions Score Threshold
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Minimum quality score (0-10) for suggestions to be shown. Higher values mean fewer but higher-quality suggestions.
                      </span>
                    </label>
                    <input
                      type="number"
                      value={config.pr_code_suggestions?.suggestions_score_threshold || 0}
                      onChange={(e) => updateConfig('pr_code_suggestions.suggestions_score_threshold', parseInt(e.target.value))}
                      min="0"
                      max="10"
                      disabled={!editing}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      0 = Show all suggestions, 10 = Only critical improvements
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Dual Publishing Score Threshold
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Minimum score for suggestions to be made commitable. -1 disables dual publishing.
                      </span>
                    </label>
                    <input
                      type="number"
                      value={config.pr_code_suggestions?.dual_publishing_score_threshold ?? -1}
                      onChange={(e) => updateConfig('pr_code_suggestions.dual_publishing_score_threshold', parseInt(e.target.value))}
                      min="-1"
                      max="10"
                      disabled={!editing}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      -1 = Disabled, 0+ = Minimum score for commitable suggestions
                    </p>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Extra Instructions for Code Suggestions
                    <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                      Detailed instructions to guide the AI's code analysis and suggestion generation. Be specific about priorities and standards.
                    </span>
                  </label>
                  <textarea
                    value={config.pr_code_suggestions?.extra_instructions || ''}
                    onChange={(e) => updateConfig('pr_code_suggestions.extra_instructions', e.target.value)}
                    disabled={!editing}
                    placeholder="e.g., Prioritize security and performance. Focus on SOLID principles. Suggest modern async patterns. Include performance complexity analysis (O notation) when suggesting algorithmic changes."
                    rows={12}
                    className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed resize-vertical"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    These instructions are critical for getting high-quality, targeted code suggestions that match your team's standards.
                  </p>
                </div>
              </div>
            </SectionHeader>
          </div>
        )}

                 {/* Time Estimation Tab */}
         {activeTab === 'time-estimation' && (
           <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
             <SectionHeader title="Developer Time Estimation" icon={Clock}>
               <div className="space-y-6 pt-4">
                 <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
                   <div className="flex items-center">
                     <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
                     <span className="text-blue-800 dark:text-blue-200 text-sm">
                       AI-powered time estimation analyzes code complexity and review quality to estimate developer time savings. 
                       Configure the model and settings to balance cost vs. accuracy.
                     </span>
                   </div>
                 </div>

                 {/* Enable/Disable Time Estimation */}
                 <div className="flex items-center space-x-3">
                   <input
                     type="checkbox"
                     id="time-estimation-enabled"
                     checked={config.pr_dev_time_estimation?.enabled || false}
                     onChange={(e) => updateConfig('pr_dev_time_estimation.enabled', e.target.checked)}
                     disabled={!editing}
                     className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                   />
                   <label htmlFor="time-estimation-enabled" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                     Enable AI-Powered Time Estimation
                   </label>
                 </div>

                 {/* Model Selection */}
                 <div>
                   <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                     Time Estimation Model
                     <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                       Leave empty to use the same model as the tool being executed. Use a cheaper model to reduce costs.
                     </span>
                   </label>
                   <select
                     value={config.pr_dev_time_estimation?.model || ''}
                     onChange={(e) => updateConfig('pr_dev_time_estimation.model', e.target.value)}
                     disabled={!editing || !config.pr_dev_time_estimation?.enabled}
                     className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                   >
                     <option value="">Use same model as tool (recommended for accuracy)</option>
                     {Object.entries(availableModels).map(([category, modelList]) => (
                       <optgroup key={category} label={`${category.charAt(0).toUpperCase() + category.slice(1)} Models`}>
                         {modelList.map(model => (
                           <option key={model} value={model}>{model}</option>
                         ))}
                       </optgroup>
                     ))}
                   </select>
                 </div>

                 <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                   <div>
                     <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                       Confidence Threshold
                       <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                         Only use AI estimates with this confidence level or higher
                       </span>
                     </label>
                     <select
                       value={config.pr_dev_time_estimation?.confidence_threshold || 'medium'}
                       onChange={(e) => updateConfig('pr_dev_time_estimation.confidence_threshold', e.target.value)}
                       disabled={!editing || !config.pr_dev_time_estimation?.enabled}
                       className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                     >
                       <option value="low">Low - Accept all AI estimates</option>
                       <option value="medium">Medium - Balanced (recommended)</option>
                       <option value="high">High - Only high-confidence estimates</option>
                     </select>
                   </div>

                   <div>
                     <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                       Estimation Timeout (seconds)
                       <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                         Maximum time to wait for AI estimation
                       </span>
                     </label>
                     <input
                       type="number"
                       value={config.pr_dev_time_estimation?.estimation_timeout_seconds || 30}
                       onChange={(e) => updateConfig('pr_dev_time_estimation.estimation_timeout_seconds', parseInt(e.target.value))}
                       min="10"
                       max="120"
                       disabled={!editing || !config.pr_dev_time_estimation?.enabled}
                       className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                     />
                   </div>
                 </div>

                 {/* Fallback Options */}
                 <div className="flex items-center space-x-3">
                   <input
                     type="checkbox"
                     id="fallback-to-heuristic"
                     checked={config.pr_dev_time_estimation?.fallback_to_heuristic || false}
                     onChange={(e) => updateConfig('pr_dev_time_estimation.fallback_to_heuristic', e.target.checked)}
                     disabled={!editing || !config.pr_dev_time_estimation?.enabled}
                     className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                   />
                   <label htmlFor="fallback-to-heuristic" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                     Fall back to heuristic estimation if AI fails
                     <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                       If disabled, failed AI estimations will return zero time savings
                     </span>
                   </label>
                 </div>

                 {/* Cost Information */}
                 <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md p-4">
                   <div className="flex items-start">
                     <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400 mr-2 mt-0.5" />
                     <div className="text-yellow-800 dark:text-yellow-200 text-sm">
                       <p className="font-medium mb-1">Cost Considerations:</p>
                       <ul className="list-disc list-inside space-y-1 text-xs">
                         <li>Each time estimation requires an additional AI call</li>
                         <li><strong>Budget models:</strong> GPT-4o Mini, GPT-3.5 Turbo (~$0.001 per estimation)</li>
                         <li><strong>Standard models:</strong> GPT-4o, Claude 3.5 Sonnet (~$0.01 per estimation)</li>
                         <li><strong>Premium models:</strong> o1, o3, Claude Opus 4 (~$0.10+ per estimation)</li>
                         <li><strong>Reasoning models:</strong> o1, o3, Claude 3.7 Sonnet (~$0.50+ per estimation)</li>
                         <li>Using the same model as the tool provides best accuracy but highest cost</li>
                         <li>Recommended: Use budget models for cost-effective estimation</li>
                       </ul>
                     </div>
                   </div>
                 </div>
               </div>
             </SectionHeader>
           </div>
         )}

        {/* Advanced Settings Tab */}
        {activeTab === 'advanced' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            <SectionHeader title="Advanced Settings" icon={Settings}>
              <div className="space-y-6 pt-4">
                <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-md p-4">
                  <div className="flex items-center">
                    <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400 mr-2" />
                    <span className="text-yellow-800 dark:text-yellow-200 text-sm">
                      Advanced settings should only be modified by experienced users. Incorrect values may cause issues.
                    </span>
                  </div>
                </div>



                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">Verbosity Level</label>
                    <select
                      value={config.verbosity_level || 2}
                      onChange={(e) => updateConfig('verbosity_level', parseInt(e.target.value))}
                      disabled={!editing}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <option value={0}>0 - Minimal logging</option>
                      <option value={1}>1 - Standard logging</option>
                      <option value={2}>2 - Detailed logging</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">AI Timeout (seconds)</label>
                    <input
                      type="number"
                      value={config.ai_timeout || 180}
                      onChange={(e) => updateConfig('ai_timeout', parseInt(e.target.value))}
                      min="30"
                      max="600"
                      disabled={!editing}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      id="publish-output"
                      checked={config.publish_output || false}
                      onChange={(e) => updateConfig('publish_output', e.target.checked)}
                      disabled={!editing}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <label htmlFor="publish-output" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Publish Output
                    </label>
                  </div>

                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      id="enable-auto-approval"
                      checked={config.enable_auto_approval || false}
                      onChange={(e) => updateConfig('enable_auto_approval', e.target.checked)}
                      disabled={!editing}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <label htmlFor="enable-auto-approval" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Enable Auto Approval (Premium)
                    </label>
                  </div>
                </div>
              </div>
            </SectionHeader>
          </div>
        )}

        {/* GitHub Tab */}
        {activeTab === 'github' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            <SectionHeader title="GitHub Integration Settings" icon={Github}>
              <div className="space-y-6 pt-4">
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
                  <div className="flex items-center">
                    <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
                    <span className="text-blue-800 dark:text-blue-200 text-sm">
                      Configure GitHub-specific settings including bot behavior, deployment preferences, and default PR commands.
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Bot User
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        The GitHub user or bot account that will post PR-Agent comments and interactions.
                      </span>
                    </label>
                    <input
                      type="text"
                      value={config.github?.bot_user || 'github-actions[bot]'}
                      onChange={(e) => updateConfig('github.bot_user', e.target.value)}
                      disabled={!editing}
                      placeholder="github-actions[bot]"
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      Typically "github-actions[bot]" for GitHub Actions or your bot's username
                    </p>
                  </div>

                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      id="override-deployment-type"
                      checked={config.github?.override_deployment_type !== false}
                      onChange={(e) => updateConfig('github.override_deployment_type', e.target.checked)}
                      disabled={!editing}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <label htmlFor="override-deployment-type" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Override deployment type
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Allow GitHub-specific configuration to override global deployment settings for this git provider.
                      </span>
                    </label>
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Default PR Commands
                    <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                      Commands that will be automatically executed when a new PR is opened. One command per line.
                    </span>
                  </label>
                  <textarea
                    value={config.github?.pr_commands?.join('\n') || '/describe --pr_description.final_update_message=false\n/review\n/improve'}
                    onChange={(e) => updateConfig('github.pr_commands', e.target.value.split('\n').filter(cmd => cmd.trim()))}
                    disabled={!editing}
                    placeholder="/describe --pr_description.final_update_message=false&#10;/review&#10;/improve"
                    rows={6}
                    className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed resize-vertical"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Common commands: /describe (generate description), /review (code review), /improve (code suggestions)
                  </p>
                </div>
              </div>
            </SectionHeader>
          </div>
        )}

        {/* Best Practices Tab */}
        {activeTab === 'best-practices' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            <SectionHeader title="Best Practices Settings" icon={Shield}>
              <div className="space-y-6 pt-4">
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
                  <div className="flex items-center">
                    <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
                    <span className="text-blue-800 dark:text-blue-200 text-sm">
                      Configure organizational best practices and automated pattern detection to ensure code quality and consistency.
                    </span>
                  </div>
                </div>

                {/* Global Best Practices */}
                <div className="space-y-4">
                  <h4 className="text-md font-medium text-gray-900 dark:text-white">Global Best Practices</h4>
                  
                  <div className="flex items-center space-x-3">
                    <input
                      type="checkbox"
                      id="enable-global-best-practices"
                      checked={config.best_practices?.enable_global_best_practices || false}
                      onChange={(e) => updateConfig('best_practices.enable_global_best_practices', e.target.checked)}
                      disabled={!editing}
                      className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                    <label htmlFor="enable-global-best-practices" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      Enable global best practices enforcement
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Apply organization-wide coding standards and practices across all repositories.
                      </span>
                    </label>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Organization Name
                        <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                          Your organization's name for customized best practice recommendations.
                        </span>
                      </label>
                      <input
                        type="text"
                        value={config.best_practices?.organization_name || ''}
                        onChange={(e) => updateConfig('best_practices.organization_name', e.target.value)}
                        disabled={!editing}
                        placeholder="e.g., Acme Corp"
                        className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                    </div>

                    <div>
                      <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                        Max Lines Allowed
                        <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                          Maximum lines for best practices content to prevent token limit issues.
                        </span>
                      </label>
                      <input
                        type="number"
                        value={config.best_practices?.max_lines_allowed || 800}
                        onChange={(e) => updateConfig('best_practices.max_lines_allowed', parseInt(e.target.value))}
                        min="100"
                        max="2000"
                        disabled={!editing}
                        className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Best Practices Content
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Define your organization's specific coding standards, patterns, and practices that AI should enforce.
                      </span>
                    </label>
                    <textarea
                      value={config.best_practices?.content || ''}
                      onChange={(e) => updateConfig('best_practices.content', e.target.value)}
                      disabled={!editing}
                      placeholder="e.g., Always use async/await instead of .Result on async methods. Prefer dependency injection over static dependencies. Use early returns to reduce nesting..."
                      rows={8}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed resize-vertical"
                    />
                  </div>
                </div>

                {/* Auto Best Practices */}
                <div className="space-y-4 border-t border-gray-200 dark:border-gray-700 pt-6">
                  <h4 className="text-md font-medium text-gray-900 dark:text-white">Automated Best Practices</h4>
                  
                  <div className="space-y-3">
                    <div className="flex items-center space-x-3">
                      <input
                        type="checkbox"
                        id="enable-auto-best-practices"
                        checked={config.auto_best_practices?.enable_auto_best_practices !== false}
                        onChange={(e) => updateConfig('auto_best_practices.enable_auto_best_practices', e.target.checked)}
                        disabled={!editing}
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                      <label htmlFor="enable-auto-best-practices" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Enable automatic best practices detection
                        <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                          AI will automatically identify and suggest adherence to common coding best practices.
                        </span>
                      </label>
                    </div>

                    <div className="flex items-center space-x-3">
                      <input
                        type="checkbox"
                        id="utilize-auto-best-practices"
                        checked={config.auto_best_practices?.utilize_auto_best_practices !== false}
                        onChange={(e) => updateConfig('auto_best_practices.utilize_auto_best_practices', e.target.checked)}
                        disabled={!editing}
                        className="h-4 w-4 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                      <label htmlFor="utilize-auto-best-practices" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        Utilize auto-detected best practices in reviews
                        <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                          Apply automatically detected patterns and practices when reviewing code.
                        </span>
                      </label>
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Max Patterns to Detect
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Maximum number of patterns to automatically detect and apply per analysis.
                      </span>
                    </label>
                    <input
                      type="number"
                      value={config.auto_best_practices?.max_patterns || 5}
                      onChange={(e) => updateConfig('auto_best_practices.max_patterns', parseInt(e.target.value))}
                      min="1"
                      max="20"
                      disabled={!editing}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Auto Best Practices Instructions
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Additional instructions for automated best practice detection and application.
                      </span>
                    </label>
                    <textarea
                      value={config.auto_best_practices?.extra_instructions || ''}
                      onChange={(e) => updateConfig('auto_best_practices.extra_instructions', e.target.value)}
                      disabled={!editing}
                      placeholder="e.g., Focus on performance and security patterns. Prioritize SOLID principles. Look for common anti-patterns in our codebase..."
                      rows={6}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed resize-vertical"
                    />
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Auto Best Practices Content
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Specific patterns and practices content for automated detection.
                      </span>
                    </label>
                    <textarea
                      value={config.auto_best_practices?.content || ''}
                      onChange={(e) => updateConfig('auto_best_practices.content', e.target.value)}
                      disabled={!editing}
                      placeholder="e.g., Repository-specific patterns that should be automatically detected and enforced..."
                      rows={6}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed resize-vertical"
                    />
                  </div>
                </div>
              </div>
            </SectionHeader>
          </div>
        )}

        {/* Dashboard Tab */}
        {activeTab === 'dashboard' && (
          <div className="space-y-8 animate-in slide-in-from-right-4 fade-in duration-300">
            <SectionHeader title="Dashboard Settings" icon={Gauge}>
              <div className="space-y-6 pt-4">
                <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-md p-4">
                  <div className="flex items-center">
                    <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-2" />
                    <span className="text-blue-800 dark:text-blue-200 text-sm">
                      Configure the PR-Agent dashboard for monitoring AI operations, costs, and performance metrics.
                    </span>
                  </div>
                </div>

                <div className="flex items-center space-x-3">
                  <input
                    type="checkbox"
                    id="dashboard-enabled"
                    checked={config.dashboard?.ENABLED !== false}
                    onChange={(e) => updateConfig('dashboard.ENABLED', e.target.checked)}
                    disabled={!editing}
                    className={getCheckboxClasses(config.dashboard?.ENABLED !== false, !editing)}
                  />
                  <label htmlFor="dashboard-enabled" className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Enable Dashboard Integration
                    <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                      Allows PR-Agent to send metrics and logs to the dashboard for monitoring and analysis.
                    </span>
                  </label>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Dashboard URL
                    <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                      The URL where your PR-Agent dashboard is hosted. Include the protocol (http/https).
                    </span>
                  </label>
                  <input
                    type="url"
                    value={config.dashboard?.URL || 'http://localhost:8000/'}
                    onChange={(e) => updateConfig('dashboard.URL', e.target.value)}
                    disabled={!editing}
                    placeholder="http://localhost:8000/"
                    className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Default: http://localhost:8000/ for local development
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                    Dashboard API Key
                    <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                      Optional API key for authenticated dashboard access. Leave empty if authentication is not required.
                    </span>
                  </label>
                  <input
                    type="password"
                    value={config.dashboard?.API_KEY || ''}
                    onChange={(e) => updateConfig('dashboard.API_KEY', e.target.value)}
                    disabled={!editing}
                    placeholder="Enter API key (optional)"
                    className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed"
                  />
                  <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                    Keep this secure and don't share it. Used for authenticating PR-Agent with your dashboard.
                  </p>
                </div>

                <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-md p-4">
                  <div className="flex items-start">
                    <CheckSquare className="h-5 w-5 text-green-600 dark:text-green-400 mr-2 mt-0.5" />
                    <div className="text-green-800 dark:text-green-200 text-sm">
                      <p className="font-medium mb-1">Dashboard Benefits:</p>
                      <ul className="list-disc list-inside space-y-1 text-xs">
                        <li>Real-time monitoring of AI operations and costs</li>
                        <li>Performance metrics and usage analytics</li>
                        <li>Error tracking and debugging capabilities</li>
                        <li>Historical data for optimization insights</li>
                        <li>Cost management and budget tracking</li>
                      </ul>
                    </div>
                  </div>
                </div>
              </div>
            </SectionHeader>
          </div>
        )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default ConfigEditor; 