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
  Clock
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
        
        // PR Code Suggestions settings
        pr_code_suggestions: {
          extra_instructions: configData.pr_code_suggestions?.extra_instructions || ''
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
        pr_code_suggestions: {
          extra_instructions: ''
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

      {/* Tab Navigation */}
      <div className="flex space-x-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1 mb-8">
        <button
          onClick={() => setActiveTab('models')}
          className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'models'
              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          <Brain className="h-4 w-4 mr-2" />
          AI Models
        </button>
        <button
          onClick={() => setActiveTab('context')}
          className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'context'
              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          <Database className="h-4 w-4 mr-2" />
          Code Context
        </button>
        <button
          onClick={() => setActiveTab('actions')}
          className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'actions'
              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          <CheckSquare className="h-4 w-4 mr-2" />
          Enabled Actions
        </button>
        <button
          onClick={() => setActiveTab('time-estimation')}
          className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'time-estimation'
              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          <Clock className="h-4 w-4 mr-2" />
          Time Estimation
        </button>
        <button
          onClick={() => setActiveTab('advanced')}
          className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
            activeTab === 'advanced'
              ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
              : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
          }`}
        >
          <Settings className="h-4 w-4 mr-2" />
          Advanced
        </button>
      </div>

      {/* Tab Content */}
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
                      className={`h-5 w-5 text-primary-600 focus:ring-primary-500 border-gray-300 dark:border-gray-600 rounded dark:bg-gray-800 transition-all duration-300 disabled:opacity-50 disabled:cursor-not-allowed ${
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

                {/* PR Code Suggestions Extra Instructions */}
                {config.enabled_actions?.pr_code_suggestions && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                      Code Suggestions Extra Instructions
                      <span className="text-xs text-gray-500 dark:text-gray-400 block font-normal mt-1">
                        Optional instructions to guide the AI model for code suggestions. Use bullet points or numbered lists for clarity.
                      </span>
                    </label>
                    <textarea
                      value={config.pr_code_suggestions?.extra_instructions || ''}
                      onChange={(e) => updateConfig('pr_code_suggestions.extra_instructions', e.target.value)}
                      disabled={!editing}
                      placeholder="e.g., - Focus on performance optimizations&#10;- Ignore style-only suggestions&#10;- Emphasize security best practices&#10;- Avoid suggesting changes to test files&#10;- Prioritize readability over brevity"
                      rows={20}
                      className="w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-white rounded-md px-3 py-2 focus:outline-none focus:ring-2 focus:ring-primary-500 disabled:opacity-50 disabled:cursor-not-allowed resize-vertical"
                    />
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
                      These instructions will be included in the AI prompt when generating code suggestions.
                    </p>
                  </div>
                )}

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
      </div>
    </div>
  );
};

export default ConfigEditor; 