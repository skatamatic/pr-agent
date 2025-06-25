import React, { useState, useEffect } from 'react';
import { 
  TrendingUp,
  DollarSign, 
  Clock, 
  Cpu, 
  BarChart3, 
  Settings, 
  RefreshCw, 
  Save,
  AlertCircle,
  Brain,
  Calculator,
  Zap,
  Target
} from 'lucide-react';
import apiService from '../services/api';
import ViewHeader from './ViewHeader';

const MetricsView = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [metricsData, setMetricsData] = useState(null);
  const [config, setConfig] = useState(null);
  const [availableModels, setAvailableModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);

  // Config form state
  const [editableConfig, setEditableConfig] = useState({
    developer_hourly_rate: 75,
    hours_multiplier: 1.0,
    model_costs: {}
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      const [summaryRes, configRes] = await Promise.all([
        apiService.get('/api/metrics/summary'),
        apiService.get('/api/metrics/config')
      ]);

      const summary = summaryRes.data?.data || summaryRes.data;
      const configData = configRes.data?.data || configRes.data;

      // Use the same model structure as AI Config
      const availableModels = [
        // Premium models
        'anthropic/claude-opus-4-20250514',
        'anthropic/claude-sonnet-4-20250514',
        'anthropic/claude-3-7-sonnet-20250219',
        'o1-2024-12-17',
        'o1',
        'o3-mini',
        'o3',
        'o4-mini',
        // Standard models
        'anthropic/claude-3-5-sonnet-20241022',
        'anthropic/claude-3-5-haiku-20241022',
        'gpt-4o',
        'gpt-4o-mini',
        'gpt-4-turbo',
        'gpt-4',
        // Budget models
        'gpt-3.5-turbo'
      ];

      setMetricsData(summary);
      setConfig(configData);
      setAvailableModels(availableModels);
      setEditableConfig({
        developer_hourly_rate: configData.developer_hourly_rate || 75,
        hours_multiplier: configData.hours_multiplier || 1.0,
        model_costs: configData.model_costs || {}
      });
      setLastUpdated(new Date());
    } catch (err) {
      console.error('Error fetching metrics:', err);
      setError('Failed to load metrics data');
    } finally {
      setLoading(false);
    }
  };

  const handleRecalculate = async () => {
    try {
      setLoading(true);
      await apiService.post('/api/metrics/recalculate');
      await fetchData();
    } catch (err) {
      console.error('Error recalculating metrics:', err);
      setError('Failed to recalculate metrics');
    } finally {
      setLoading(false);
    }
  };

  const handleSaveConfig = async () => {
    try {
      setSaving(true);
      await apiService.post('/api/metrics/config', editableConfig);
      await fetchData(); // Refresh to get updated calculations
    } catch (err) {
      console.error('Error saving config:', err);
      setError('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 4
    }).format(amount || 0);
  };

  const formatNumber = (num) => {
    return new Intl.NumberFormat('en-US').format(num || 0);
  };

  const formatHours = (hours) => {
    return `${(hours || 0).toFixed(1)}h`;
  };

  // Get models that are either in current config or available in AI config
  const getRelevantModels = () => {
    const configModels = Object.keys(editableConfig.model_costs || {});
    const usedModels = Object.keys(metricsData?.model_breakdown || {});
    
    // If we have AI config models, prioritize them
    if (availableModels.length > 0) {
      // Prioritize AI config models, then add any used models or configured models not in AI config
      const allModels = [...new Set([...availableModels, ...usedModels, ...configModels])];
      return allModels.filter(Boolean);
    }
    
    // Fallback: if no AI config models loaded yet, show existing config and used models
    const fallbackModels = [...new Set([...configModels, ...usedModels])];
    return fallbackModels.filter(Boolean);
  };

  const hasData = metricsData && (metricsData.total_operations > 0 || Object.keys(metricsData.model_breakdown || {}).length > 0);

  const tabs = [
    { id: 'overview', name: 'Overview', icon: BarChart3 },
    { id: 'models', name: 'Model Breakdown', icon: Cpu },
    { id: 'configuration', name: 'Configuration', icon: Settings }
  ];

  const renderTabContent = () => {
    if (!hasData && activeTab !== 'configuration') {
      return (
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-8 text-center">
          <Brain className="h-12 w-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-2">No Metrics Data Available</h3>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            AI metrics will appear here once PR-Agent operations with AI models are processed.
          </p>
          <button
            onClick={handleRecalculate}
            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg inline-flex items-center"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Check for Data
          </button>
        </div>
      );
    }

    switch (activeTab) {
      case 'overview':
        return renderOverviewTab();
      case 'models':
        return renderModelsTab();
      case 'configuration':
        return renderConfigurationTab();
      default:
        return renderOverviewTab();
    }
  };

  const renderOverviewTab = () => (
    <div className="space-y-6">
      {/* Prominent Net Savings Card */}
      <div className="flex justify-center">
        <div className="w-full max-w-4xl bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-xl shadow-sm border-2 border-green-200 dark:border-green-700 p-8">
          <div className="text-center">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 dark:bg-green-900/40 rounded-full mb-4">
              <TrendingUp className="h-8 w-8 text-green-600 dark:text-green-400" />
            </div>
            <h3 className="text-lg font-medium text-gray-700 dark:text-gray-300 mb-2">Net Savings</h3>
            <p className={`text-5xl font-bold mb-2 ${
              metricsData.total_savings > 0 
                ? 'text-green-600 dark:text-green-400' 
                : 'text-red-600 dark:text-red-400'
            }`}>
              {formatCurrency(metricsData.total_savings)}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Developer savings minus AI costs
            </p>
          </div>
        </div>
      </div>

      {/* Summary Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Total Operations */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center">
            <div className="p-3 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <BarChart3 className="h-6 w-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Total Operations</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {formatNumber(metricsData.total_operations)}
              </p>
            </div>
          </div>
        </div>

        {/* Token Cost */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center">
            <div className="p-3 bg-red-100 dark:bg-red-900/30 rounded-lg">
              <DollarSign className="h-6 w-6 text-red-600 dark:text-red-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Token Costs</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {formatCurrency(metricsData.total_token_cost)}
              </p>
            </div>
          </div>
        </div>

        {/* Dev Hours Saved */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center">
            <div className="p-3 bg-green-100 dark:bg-green-900/30 rounded-lg">
              <Clock className="h-6 w-6 text-green-600 dark:text-green-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Dev Hours Saved</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                {formatHours(metricsData.total_dev_hours_saved)}
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4 flex items-center">
          <Target className="h-5 w-5 mr-2" />
          Key Metrics
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center">
            <p className="text-2xl font-bold text-blue-600 dark:text-blue-400">
              {formatNumber(metricsData.total_input_tokens + metricsData.total_output_tokens)}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">Total Tokens</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
              {Object.keys(metricsData.model_breakdown || {}).length}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">Models Used</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-orange-600 dark:text-orange-400">
              {formatCurrency(metricsData.total_dev_cost_saved)}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">Dev Cost Saved</p>
          </div>
          <div className="text-center">
            <p className="text-2xl font-bold text-indigo-600 dark:text-indigo-400">
              {metricsData.total_operations > 0 ? formatCurrency(metricsData.total_token_cost / metricsData.total_operations) : '$0.00'}
            </p>
            <p className="text-sm text-gray-600 dark:text-gray-400">Avg Cost/Op</p>
          </div>
        </div>
      </div>
    </div>
  );

  const renderModelsTab = () => (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700">
      <div className="px-6 py-4 border-b border-gray-200 dark:border-gray-700">
        <h3 className="text-lg font-medium text-gray-900 dark:text-white flex items-center">
          <Cpu className="h-5 w-5 mr-2" />
          Model Usage Breakdown
        </h3>
      </div>
      <div className="p-6">
        {Object.keys(metricsData?.model_breakdown || {}).length === 0 ? (
          <p className="text-gray-500 dark:text-gray-400 text-center py-8">
            No model usage data available
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
              <thead className="bg-gray-50 dark:bg-gray-900">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Model
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Operations
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Input Tokens
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Output Tokens
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Total Cost
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Dev Hours
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                    Cost/Op
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                {Object.entries(metricsData.model_breakdown).map(([modelName, data]) => (
                  <tr key={modelName} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900 dark:text-white">
                      <div className="flex items-center">
                        <Zap className="h-4 w-4 text-blue-500 mr-2" />
                        {modelName}
                      </div>
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {formatNumber(data.operations_count)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {formatNumber(data.input_tokens)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {formatNumber(data.output_tokens)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {formatCurrency(data.total_cost)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {formatHours(data.estimated_dev_hours)}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                      {formatCurrency(data.cost_per_operation)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );

  const renderConfigurationTab = () => (
    <div className="space-y-6">
      {/* Basic Settings */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4 flex items-center">
          <Settings className="h-5 w-5 mr-2" />
          Basic Settings
        </h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Developer Hourly Rate (USD)
            </label>
            <input
              type="number"
              value={editableConfig.developer_hourly_rate}
              onChange={(e) => setEditableConfig(prev => ({
                ...prev,
                developer_hourly_rate: parseFloat(e.target.value) || 0
              }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
              Hours Multiplier
            </label>
            <input
              type="number"
              step="0.1"
              value={editableConfig.hours_multiplier}
              onChange={(e) => setEditableConfig(prev => ({
                ...prev,
                hours_multiplier: parseFloat(e.target.value) || 0
              }))}
              className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
        </div>
      </div>

      {/* Model Costs */}
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
        <h3 className="text-lg font-medium text-gray-900 dark:text-white mb-4 flex items-center">
          <Calculator className="h-5 w-5 mr-2" />
          Model Costs (per 1K tokens)
        </h3>
        <div className="space-y-4">
          {getRelevantModels().map((model) => {
            const costs = editableConfig.model_costs[model] || { input: 0, output: 0 };
            return (
              <div key={model} className="grid grid-cols-1 md:grid-cols-3 gap-4 p-4 bg-gray-50 dark:bg-gray-900 rounded-lg">
                <div className="font-medium text-gray-900 dark:text-white flex items-center">
                  <Zap className="h-4 w-4 text-blue-500 mr-2" />
                  {model}
                </div>
                <div>
                  <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Input Cost</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={costs.input || 0}
                    onChange={(e) => setEditableConfig(prev => ({
                      ...prev,
                      model_costs: {
                        ...prev.model_costs,
                        [model]: {
                          ...prev.model_costs[model],
                          input: parseFloat(e.target.value) || 0
                        }
                      }
                    }))}
                    className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-500 dark:text-gray-400 mb-1">Output Cost</label>
                  <input
                    type="number"
                    step="0.0001"
                    value={costs.output || 0}
                    onChange={(e) => setEditableConfig(prev => ({
                      ...prev,
                      model_costs: {
                        ...prev.model_costs,
                        [model]: {
                          ...prev.model_costs[model],
                          output: parseFloat(e.target.value) || 0
                        }
                      }
                    }))}
                    className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                  />
                </div>
              </div>
            );
          })}
        </div>
        
        {/* Save Button */}
        <div className="flex justify-end mt-6">
          <button
            onClick={handleSaveConfig}
            disabled={saving}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-white px-6 py-2 rounded-lg flex items-center"
          >
            {saving ? (
              <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            Save Configuration
          </button>
        </div>
      </div>
    </div>
  );

  if (loading && !metricsData) {
    return (
      <div className="space-y-6">
        <ViewHeader 
          title="AI/LLM Metrics"
          subtitle="Track AI model usage, costs, and developer productivity savings"
          icon={TrendingUp}
        />
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600"></div>
          <span className="ml-3 text-gray-600 dark:text-gray-400">Loading metrics...</span>
        </div>
      </div>
    );
  }

  if (error && !metricsData) {
    return (
      <div className="space-y-6">
        <ViewHeader 
          title="AI/LLM Metrics"
          subtitle="Track AI model usage, costs, and developer productivity savings"
          icon={TrendingUp}
          onRefresh={fetchData}
        />
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-center">
            <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
            <span className="text-red-800 dark:text-red-200">{error}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <ViewHeader 
        title="AI/LLM Metrics"
        subtitle={`Track AI model usage, costs, and developer productivity savings${lastUpdated ? ` • Last updated: ${lastUpdated.toLocaleTimeString()}` : ''}`}
        icon={TrendingUp}
        onRefresh={fetchData}
        rightComponent={
          <button
            onClick={handleRecalculate}
            disabled={loading}
            className="flex items-center px-4 py-2 text-sm bg-gray-600 text-white rounded-lg hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-gray-500 transition-colors duration-200 shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Recalculate
          </button>
        }
      />

      {/* Tab Navigation */}
      <div className="flex space-x-1 bg-gray-100 dark:bg-gray-800 rounded-lg p-1">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                activeTab === tab.id
                  ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                  : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white'
              }`}
            >
              <Icon className="h-4 w-4 mr-2" />
              {tab.name}
            </button>
          );
        })}
      </div>

      {/* Tab Content */}
      {renderTabContent()}

      {/* Error Display */}
      {error && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-4">
          <div className="flex items-center">
            <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400 mr-3" />
            <span className="text-red-800 dark:text-red-200">{error}</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default MetricsView; 