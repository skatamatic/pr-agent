import React, { useState, useEffect, useRef } from 'react';
import { X, Download, Save, FileText, ExternalLink, AlertCircle, Check, Copy, Eye, EyeOff } from 'lucide-react';
import api from '../services/api';

const AzurePipelineConfigEditor = ({ repoId, repoData, onClose, onSave }) => {
  const [configContent, setConfigContent] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState(null);
  const [template, setTemplate] = useState('');
  const [envVars, setEnvVars] = useState({});
  const [showEnvVars, setShowEnvVars] = useState(false);
  const [copiedVar, setCopiedVar] = useState(null);
  const loadConfigAndTemplateRef = useRef(null);

  useEffect(() => {
    loadConfigAndTemplateRef.current?.();
  }, [repoId]);

  const loadConfigAndTemplate = async () => {
    try {
      setIsLoading(true);
      setError(null);

      // Load existing config and template in parallel
      const [configResponse, templateResponse, envVarsResponse] = await Promise.all([
        api.get(`/api/repositories/${repoId}/azure-pipeline-config`),
        api.get(`/api/repositories/${repoId}/azure-pipeline-config/template`),
        api.get(`/api/repositories/${repoId}/azure-pipeline-config/env-vars`)
      ]);

      const configData = configResponse.data;
      const templateData = templateResponse.data;
      const envVarsData = envVarsResponse.data;

      // Set the content to existing config or template
      if (configData && configData.exists && configData.content) {
        setConfigContent(configData.content);
      } else if (templateData && templateData.template) {
        setConfigContent(templateData.template);
      }

      setTemplate(templateData?.template || '');
      setEnvVars(envVarsData?.variables || {});

    } catch (error) {
      console.error('Error loading Azure Pipeline config:', error);
      setError(`Failed to load configuration: ${error.response?.data?.detail || error.message}`);
    } finally {
      setIsLoading(false);
    }
  };

  loadConfigAndTemplateRef.current = loadConfigAndTemplate;

  const handleSave = async () => {
    if (!configContent.trim()) {
      setError('Configuration content cannot be empty');
      return;
    }

    try {
      setIsSaving(true);
      setError(null);

      const response = await api.put(`/api/repositories/${repoId}/azure-pipeline-config`, {
        content: configContent
      });

      const result = response.data;
      
      if (onSave) {
        onSave(result);
      }

    } catch (error) {
      console.error('Error saving Azure Pipeline config:', error);
      setError(`Failed to save configuration: ${error.response?.data?.detail || error.message}`);
    } finally {
      setIsSaving(false);
    }
  };

  const copyToClipboard = async (text, varName) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedVar(varName);
      setTimeout(() => setCopiedVar(null), 2000);
    } catch (err) {
      console.error('Failed to copy text: ', err);
    }
  };

  const resetToTemplate = () => {
    setConfigContent(template);
    setError(null);
  };

  const downloadConfig = () => {
    const blob = new Blob([configContent], { type: 'text/yaml' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'azure-pipelines.yml';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (isLoading) {
    return (
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
        <div className="bg-white dark:bg-gray-800 rounded-lg p-6 w-4/5 max-w-4xl max-h-[90vh] overflow-auto">
          <div className="flex items-center justify-center py-8">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
            <span className="ml-3 text-gray-600 dark:text-gray-400">Loading Azure Pipeline configuration...</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow-xl w-[95%] max-w-6xl max-h-[95vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center">
            <FileText className="h-6 w-6 text-blue-600 dark:text-blue-400 mr-3" />
            <div>
              <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                Azure Pipeline Configuration
              </h3>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                {repoData?.name} • Configure azure-pipelines.yml for PR-Agent automation
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
          >
            <X className="h-6 w-6" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden flex">
          {/* Main Editor */}
          <div className="flex-1 flex flex-col">
            {/* Toolbar */}
            <div className="flex items-center justify-between p-4 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50">
              <div className="flex items-center space-x-2">
                <button
                  onClick={resetToTemplate}
                  className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                >
                  <FileText className="h-4 w-4 mr-2" />
                  Reset to Template
                </button>
                <button
                  onClick={downloadConfig}
                  className="flex items-center px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
                >
                  <Download className="h-4 w-4 mr-2" />
                  Download
                </button>
                <button
                  onClick={() => setShowEnvVars(!showEnvVars)}
                  className="flex items-center px-3 py-2 text-sm font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-lg hover:bg-blue-100 dark:hover:bg-blue-900/30 transition-colors"
                >
                  {showEnvVars ? <EyeOff className="h-4 w-4 mr-2" /> : <Eye className="h-4 w-4 mr-2" />}
                  {showEnvVars ? 'Hide' : 'Show'} Environment Variables
                </button>
              </div>
              <div className="flex items-center space-x-2">
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  azure-pipelines.yml
                </span>
              </div>
            </div>

            {/* Error Display */}
            {error && (
              <div className="p-4 bg-red-50 dark:bg-red-900/20 border-b border-red-200 dark:border-red-800">
                <div className="flex items-start">
                  <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3 mt-0.5 flex-shrink-0" />
                  <div>
                    <h4 className="text-sm font-medium text-red-800 dark:text-red-200">Error</h4>
                    <p className="text-sm text-red-700 dark:text-red-300 mt-1">{error}</p>
                  </div>
                </div>
              </div>
            )}

            {/* Editor */}
            <div className="flex-1 p-4">
              <textarea
                value={configContent}
                onChange={(e) => setConfigContent(e.target.value)}
                className="w-full h-full min-h-[400px] font-mono text-sm border border-gray-300 dark:border-gray-600 rounded-lg p-4 focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-900 text-gray-900 dark:text-white resize-none"
                placeholder="Enter your Azure Pipeline configuration here..."
                spellCheck={false}
              />
            </div>
          </div>

          {/* Environment Variables Panel */}
          {showEnvVars && (
            <div className="w-96 border-l border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-900/50 flex flex-col">
              <div className="p-4 border-b border-gray-200 dark:border-gray-700">
                <h4 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                  Environment Variables
                </h4>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Add these variables to your Azure Pipeline configuration
                </p>
              </div>
              <div className="flex-1 overflow-auto p-4 space-y-3">
                {Object.entries(envVars).length > 0 ? (
                  Object.entries(envVars).map(([key, config]) => (
                    <div key={key} className="bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 p-3">
                      <div className="flex items-center justify-between mb-2">
                        <code className="text-xs font-mono text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 px-2 py-1 rounded">
                          {key}
                        </code>
                        <button
                          onClick={() => copyToClipboard(key, key)}
                          className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
                        >
                          {copiedVar === key ? (
                            <Check className="h-4 w-4 text-green-500" />
                          ) : (
                            <Copy className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                      <p className="text-xs text-gray-600 dark:text-gray-400 mb-2">
                        {config.description || 'No description available'}
                      </p>
                      {config.default && (
                        <div className="text-xs text-gray-500 dark:text-gray-500">
                          Default: <code className="bg-gray-100 dark:bg-gray-700 px-1 py-0.5 rounded">{config.default}</code>
                        </div>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="text-center py-8">
                    <AlertCircle className="h-8 w-8 text-gray-400 mx-auto mb-2" />
                    <p className="text-sm text-gray-500 dark:text-gray-400">
                      No environment variables configured
                    </p>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center space-x-4">
            {(() => {
              // Parse Azure DevOps URL correctly
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
                        baseUrl: `https://${organization}.visualstudio.com`
                      };
                    }
                  }
                  
                  // Fallback
                  return { baseUrl: url.replace('/_git/', '/_build').replace(/\/[^/]*$/, '') };
                } catch (e) {
                  return { baseUrl: url };
                }
              };

              const azureInfo = parseAzureDevOpsUrl(repoData?.url || '');
              const pipelinesUrl = `${azureInfo.baseUrl}/${azureInfo.project || ''}/_build`.replace('//_build', '/_build');
              
              return (
                <a
                  href={pipelinesUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center text-sm text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300 transition-colors"
                >
                  <ExternalLink className="h-4 w-4 mr-2" />
                  View Azure Pipelines
                </a>
              );
            })()}
          </div>
          <div className="flex items-center space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-gray-700 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={isSaving || !configContent.trim()}
              className="flex items-center px-4 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600 rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Save className={`h-4 w-4 mr-2 ${isSaving ? 'animate-spin' : ''}`} />
              {isSaving ? 'Creating PR...' : 'Save & Create PR'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AzurePipelineConfigEditor; 