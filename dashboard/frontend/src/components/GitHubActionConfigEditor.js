import React, { useState, useEffect, useContext } from 'react';
import { 
  Server, 
  Settings, 
  Save, 
  RefreshCw, 
  GitBranch, 
  ExternalLink, 
  AlertCircle, 
  Check, 
  X, 
  Info,
  Plus,
  Trash2,
  Eye,
  EyeOff
} from 'lucide-react';
import api from '../services/api';
import { ToastContext } from '../contexts/ToastContext';

const GitHubActionConfigEditor = ({ repoId, repoData, onClose, onSave }) => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [configData, setConfigData] = useState(null);
  const [envVars, setEnvVars] = useState({});
  const [availableVars, setAvailableVars] = useState([]);
  const [showSecrets, setShowSecrets] = useState({});
  const [prStatus, setPrStatus] = useState(null);
  const { showSuccess, showError } = useContext(ToastContext);

  useEffect(() => {
    loadConfig();
    loadEnvironmentVars();
  }, [repoId]);

  const loadConfig = async () => {
    try {
      setLoading(true);
      const response = await api.get(`/api/repositories/${repoId}/github-action-config`);
      
      if (response.data.data.exists) {
        setConfigData(response.data.data);
        setEnvVars(response.data.data.env_vars || {});
      } else {
        setConfigData(response.data.data);
        // Set default values from template
        const defaultVars = {};
        response.data.data.env_vars?.forEach(envVar => {
          defaultVars[envVar.key] = envVar.default;
        });
        setEnvVars(defaultVars);
      }
    } catch (error) {
      showError('Error', 'Failed to load GitHub Action configuration');
    } finally {
      setLoading(false);
    }
  };

  const loadEnvironmentVars = async () => {
    try {
      const response = await api.get(`/api/repositories/${repoId}/github-action-config/env-vars`);
      setAvailableVars(response.data.data.env_vars || []);
    } catch (error) {
      console.error('Failed to load environment variables:', error);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      
      const response = await api.put(`/api/repositories/${repoId}/github-action-config`, {
        env_vars: envVars
      });
      
      if (response.data.data.pr_created) {
        setPrStatus({
          pr_number: response.data.data.pr_number,
          pr_url: response.data.data.pr_url,
          branch_name: response.data.data.branch_name
        });
        showSuccess('Success', 'GitHub Action configuration PR created successfully');
        if (onSave) onSave(response.data.data);
      }
    } catch (error) {
      showError('Error', error.response?.data?.detail || 'Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const updateEnvVar = (key, value) => {
    setEnvVars(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const addCustomEnvVar = () => {
    const key = prompt('Enter environment variable name:');
    if (key && key.trim()) {
      updateEnvVar(key.trim(), '');
    }
  };

  const removeEnvVar = (key) => {
    setEnvVars(prev => {
      const newVars = { ...prev };
      delete newVars[key];
      return newVars;
    });
  };

  const toggleSecretVisibility = (key) => {
    setShowSecrets(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  const getVarConfig = (key) => {
    return availableVars.find(v => v.key === key) || { 
      key, 
      label: key, 
      description: 'Custom environment variable',
      type: 'string',
      category: 'Custom'
    };
  };

  const groupVarsByCategory = () => {
    const grouped = {};
    const allKeys = [...new Set([...Object.keys(envVars), ...availableVars.map(v => v.key)])];
    
    allKeys.forEach(key => {
      const varConfig = getVarConfig(key);
      const category = varConfig.category || 'Other';
      
      if (!grouped[category]) {
        grouped[category] = [];
      }
      
      grouped[category].push({
        key,
        value: envVars[key] || '',
        config: varConfig
      });
    });
    
    return grouped;
  };

  const renderEnvVarInput = (varData) => {
    const { key, value, config } = varData;
    const isSecret = config.type === 'secret';
    const isBoolean = config.type === 'boolean';
    const isArray = config.type === 'array';
    const isCustom = !availableVars.find(v => v.key === key);

    return (
      <div key={key} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
        <div className="flex items-start justify-between mb-2">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <label className="text-sm font-medium text-gray-900 dark:text-white">
                {config.label}
              </label>
              {isCustom && (
                <span className="px-2 py-1 text-xs bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded">
                  Custom
                </span>
              )}
            </div>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              {config.description}
            </p>
          </div>
          {isCustom && (
            <button
              onClick={() => removeEnvVar(key)}
              className="text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 ml-2"
            >
              <Trash2 className="h-4 w-4" />
            </button>
          )}
        </div>

        <div className="space-y-2">
          <div className="text-xs text-gray-600 dark:text-gray-400 font-mono">
            {key}
          </div>
          
          {isBoolean ? (
            <select
              value={value}
              onChange={(e) => updateEnvVar(key, e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm"
            >
              <option value="true">true</option>
              <option value="false">false</option>
            </select>
          ) : isArray ? (
            <textarea
              value={value}
              onChange={(e) => updateEnvVar(key, e.target.value)}
              placeholder='["opened", "reopened", "ready_for_review"]'
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm font-mono"
              rows={2}
            />
          ) : (
            <div className="relative">
              <input
                type={isSecret && !showSecrets[key] ? 'password' : 'text'}
                value={value}
                onChange={(e) => updateEnvVar(key, e.target.value)}
                placeholder={config.default || `Enter ${config.label.toLowerCase()}`}
                className="w-full px-3 py-2 pr-10 border border-gray-300 dark:border-gray-600 rounded-md focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm font-mono"
              />
              {isSecret && (
                <button
                  type="button"
                  onClick={() => toggleSecretVisibility(key)}
                  className="absolute right-3 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  {showSecrets[key] ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-full max-w-4xl mx-4 max-h-[90vh] overflow-y-auto">
          <div className="flex items-center justify-center py-8">
            <RefreshCw className="h-6 w-6 text-blue-600 dark:text-blue-400 animate-spin mr-3" />
            <span className="text-gray-600 dark:text-gray-400">Loading GitHub Action configuration...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg w-full max-w-6xl mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4 z-10">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <Server className="h-6 w-6 text-blue-600 dark:text-blue-400 mr-3" />
              <div>
                <h2 className="text-xl font-semibold text-gray-900 dark:text-white">
                  GitHub Action Configuration
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  Configure environment variables for {repoData?.name} workflow
                </p>
              </div>
            </div>
            <div className="flex items-center space-x-2">
              {prStatus && (
                <div className="flex items-center bg-green-50 dark:bg-green-900/20 text-green-800 dark:text-green-200 px-3 py-1 rounded-lg border border-green-200 dark:border-green-700 mr-2">
                  <GitBranch className="h-4 w-4 mr-1" />
                  <span className="text-sm font-medium">
                    PR #{prStatus.pr_number}
                  </span>
                  <a 
                    href={prStatus.pr_url} 
                    target="_blank" 
                    rel="noopener noreferrer"
                    className="ml-1 hover:text-green-900 dark:hover:text-green-100"
                  >
                    <ExternalLink className="h-3 w-3" />
                  </a>
                </div>
              )}
              <button
                onClick={onClose}
                className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
              >
                <X className="h-6 w-6" />
              </button>
            </div>
          </div>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Status Banner */}
          {configData?.exists ? (
            <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-4">
              <div className="flex items-center">
                <Check className="h-5 w-5 text-green-600 dark:text-green-400 mr-3" />
                <div>
                  <h4 className="font-medium text-green-800 dark:text-green-200">
                    Configuration Found
                  </h4>
                  <p className="text-green-700 dark:text-green-300 text-sm">
                    GitHub Action configuration exists at <code>.github/pr_agent.yml</code>
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4">
              <div className="flex items-center">
                <AlertCircle className="h-5 w-5 text-yellow-600 dark:text-yellow-400 mr-3" />
                <div>
                  <h4 className="font-medium text-yellow-800 dark:text-yellow-200">
                    No Configuration Found
                  </h4>
                  <p className="text-yellow-700 dark:text-yellow-300 text-sm">
                    This will create a new GitHub Action configuration file
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Info Box */}
          <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg p-4">
            <div className="flex items-start">
              <Info className="h-5 w-5 text-blue-600 dark:text-blue-400 mr-3 mt-0.5 flex-shrink-0" />
              <div>
                <h4 className="font-medium text-blue-800 dark:text-blue-200 mb-2">
                  How it works
                </h4>
                <div className="text-sm text-blue-700 dark:text-blue-300 space-y-1">
                  <p>• Configure environment variables for your GitHub Actions workflow</p>
                  <p>• Changes will be submitted as a pull request for review</p>
                  <p>• Use GitHub secrets syntax like <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">${'{{ secrets.SECRET_NAME }}'}</code></p>
                  <p>• Access GitHub context with <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">${'{{ github.event_name }}'}</code></p>
                </div>
              </div>
            </div>
          </div>

          {/* Environment Variables */}
          <div className="space-y-6">
            {Object.entries(groupVarsByCategory()).map(([category, vars]) => (
              <div key={category} className="space-y-4">
                <div className="flex items-center justify-between">
                  <h3 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
                    <Settings className="h-5 w-5 mr-2 text-gray-600 dark:text-gray-400" />
                    {category}
                  </h3>
                  {category === 'Custom' && (
                    <button
                      onClick={addCustomEnvVar}
                      className="flex items-center px-3 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg transition-colors duration-200"
                    >
                      <Plus className="h-4 w-4 mr-2" />
                      Add Variable
                    </button>
                  )}
                </div>
                
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {vars.map(renderEnvVarInput)}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="sticky bottom-0 bg-white dark:bg-gray-800 border-t border-gray-200 dark:border-gray-700 px-6 py-4 z-10">
          <div className="flex justify-end space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors duration-200"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg transition-colors duration-200 flex items-center"
            >
              {saving ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  Creating PR...
                </>
              ) : (
                <>
                  <GitBranch className="h-4 w-4 mr-2" />
                  Create PR
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default GitHubActionConfigEditor; 