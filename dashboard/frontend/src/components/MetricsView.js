import React, { useState, useEffect, useRef, useCallback } from 'react';
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
  Crown,
  Star,
  Wallet,
  ChevronLeft,
  ChevronRight,
  Play,
  Pause,
  ArrowUp,
  ArrowDown,
  GitBranch,
  FolderGit2
} from 'lucide-react';
import apiService from '../services/api';
import ViewHeader from './ViewHeader';

// Move AnimatedMetric outside of MetricsView to prevent remounting on every render
const AnimatedMetric = ({ value, formatter, className = "", duration = 1500, integer = false }) => {
  const [displayValue, setDisplayValue] = useState(value);
  const [isAnimating, setIsAnimating] = useState(false);
  const animationRef = useRef(null);
  const startTimeRef = useRef(null);
  const lastValueRef = useRef(value);
  const mountedRef = useRef(false);

  // Easing function for smooth animation (ease-out cubic)
  const easeOutCubic = (t) => 1 - Math.pow(1 - t, 3);

  const targetValueRef = useRef(value);
  const durationRef = useRef(duration);
  
  // Update refs when props change
  targetValueRef.current = value;
  durationRef.current = duration;

  const animateValue = useCallback((currentTime) => {
    if (startTimeRef.current === null) {
      startTimeRef.current = currentTime;
    }

    const elapsed = currentTime - startTimeRef.current;
    const progress = Math.min(elapsed / durationRef.current, 1);
    const easedProgress = easeOutCubic(progress);
    
    // Calculate current animated value
    const startValue = lastValueRef.current;
    const targetValue = targetValueRef.current;
    const currentValue = startValue + (targetValue - startValue) * easedProgress;
    
    // For integer metrics, only show whole numbers during animation
    setDisplayValue(integer ? Math.round(currentValue) : currentValue);

    if (progress < 1) {
      animationRef.current = requestAnimationFrame(animateValue);
    } else {
      setIsAnimating(false);
      setDisplayValue(targetValueRef.current); // Ensure final value is exact
      lastValueRef.current = targetValueRef.current; // Update the last known value
      startTimeRef.current = null;
    }
  }, []); // No dependencies since we use refs

  useEffect(() => {
    // Don't animate on initial mount
    if (!mountedRef.current) {
      mountedRef.current = true;
      lastValueRef.current = value;
      setDisplayValue(value);
      return;
    }

    // Check if value actually changed
    if (value === lastValueRef.current) {
      return;
    }

    // Calculate difference for animation decision
    const valueDiff = Math.abs(value - lastValueRef.current);
    const shouldAnimate = valueDiff > 0.01; // Avoid animating tiny differences
    
    if (shouldAnimate) {
      setIsAnimating(true);
      startTimeRef.current = null;
      
      // Cancel any existing animation
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
      
      // Start new animation - DON'T update lastValueRef yet, let animation complete
      animationRef.current = requestAnimationFrame(animateValue);
    } else {
      // For very small changes, just set directly
      setDisplayValue(value);
      lastValueRef.current = value;
    }

    // Cleanup function
    return () => {
      if (animationRef.current) {
        cancelAnimationFrame(animationRef.current);
      }
    };
  }, [value]); // Only depend on value changes

  return (
    <span 
      className={`transition-all duration-300 ${isAnimating ? 'scale-105' : 'scale-100'} ${className}`}
      style={{
        textShadow: isAnimating ? '0 0 12px rgba(34, 197, 94, 0.4)' : 'none',
        filter: isAnimating ? 'brightness(1.1)' : 'brightness(1)',
      }}
    >
      {formatter ? formatter(displayValue) : (integer ? Math.round(displayValue) : displayValue)}
    </span>
  );
};

const MetricsView = () => {
  const [activeTab, setActiveTab] = useState('overview');
  const [metricsData, setMetricsData] = useState({
    total_jobs: 0,
    total_operations: 0,
    total_input_tokens: 0,
    total_output_tokens: 0,
    total_token_cost: 0,
    total_dev_hours_saved: 0,
    total_dev_cost_saved: 0,
    total_savings: 0,
    model_breakdown: {}
  });
  const [operationData, setOperationData] = useState(null);
  const [repositoryData, setRepositoryData] = useState(null);
  const [config, setConfig] = useState(null);
  const [availableModels, setAvailableModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [activeModelTab, setActiveModelTab] = useState('premium');
  const [currentModelIndex, setCurrentModelIndex] = useState(0);
  const [currentOperationIndex, setCurrentOperationIndex] = useState(0);
  const [currentRepositoryIndex, setCurrentRepositoryIndex] = useState(0);
  const [hoveredPieSlice, setHoveredPieSlice] = useState(null);
  

  
  // Auto-refresh interval refs and state
  const autoRefreshIntervalRef = useRef(null);
  const lastDataChangeRef = useRef(Date.now());
  const currentIntervalRef = useRef(1000); // Start with 1 second
  const isRestartingRef = useRef(false);

  // Config form state
  const [editableConfig, setEditableConfig] = useState({
    developer_hourly_rate: 75,
    hours_multiplier: 1.0,
    model_costs: {}
  });

  // Adaptive polling interval calculation
  const getPollingInterval = () => {
    const timeSinceLastChange = Date.now() - lastDataChangeRef.current;
    
    if (timeSinceLastChange < 10000) {
      // Less than 10 seconds since last change: poll every 1 second
      return 1000;
    } else if (timeSinceLastChange < 30000) {
      // 10-30 seconds since last change: poll every 5 seconds
      return 5000;
    } else {
      // More than 30 seconds since last change: poll every 30 seconds
      return 30000;
    }
  };

  // Throttled refresh function - prevents spam by limiting to once every 5 seconds
  const lastRefreshRef = useRef(0);
  const handleThrottledMetricsUpdate = useCallback(async () => {
    const now = Date.now();
    // Only allow refresh if 5 seconds have passed since last refresh
    if (now - lastRefreshRef.current < 5000) {
      return;
    }
    lastRefreshRef.current = now;
    
    try {
      // Only fetch data, don't force recalculate on every update
      await fetchData();
    } catch (error) {
      console.error('MetricsView: Event-based refresh failed:', error);
    }
  }, []);

  // Restart the polling interval with adaptive timing
  const restartAdaptivePolling = useCallback(() => {
    // Prevent recursion during restart
    if (isRestartingRef.current) {
      return;
    }
    isRestartingRef.current = true;
    
    // Clear existing interval
    if (autoRefreshIntervalRef.current) {
      clearInterval(autoRefreshIntervalRef.current);
    }
    
    const newInterval = getPollingInterval();
    currentIntervalRef.current = newInterval;
    
    autoRefreshIntervalRef.current = setInterval(() => {
      handleThrottledMetricsUpdate();
      
      // Check if we need to adjust polling interval
      const requiredInterval = getPollingInterval();
      if (requiredInterval !== currentIntervalRef.current && !isRestartingRef.current) {
        restartAdaptivePolling();
      }
    }, newInterval);
    
    isRestartingRef.current = false;
  }, [handleThrottledMetricsUpdate]);

  // Handle new activity - reset to fast polling
  const handleNewActivity = useCallback(() => {
    lastDataChangeRef.current = Date.now();
    restartAdaptivePolling();
    handleThrottledMetricsUpdate();
  }, [handleThrottledMetricsUpdate, restartAdaptivePolling]);

  useEffect(() => {
    // Initial data load
    fetchData();

    // Listen for WebSocket events that indicate new activity
    const handleJobUpdate = () => handleNewActivity();
    const handleOperationUpdate = () => handleNewActivity();
    const handleWebSocketMetricsUpdate = () => handleThrottledMetricsUpdate();

    // Add event listeners for real-time updates
    window.addEventListener('jobUpdate', handleJobUpdate);
    window.addEventListener('operationUpdate', handleOperationUpdate);
    window.addEventListener('metricsUpdate', handleWebSocketMetricsUpdate);
    
    // Start adaptive polling
    restartAdaptivePolling();
    
    return () => {
      // Remove event listeners
      window.removeEventListener('jobUpdate', handleJobUpdate);
      window.removeEventListener('operationUpdate', handleOperationUpdate);
      window.removeEventListener('metricsUpdate', handleWebSocketMetricsUpdate);
      
      // Clear interval
      if (autoRefreshIntervalRef.current) {
        clearInterval(autoRefreshIntervalRef.current);
        autoRefreshIntervalRef.current = null;
      }
    };
  }, [handleNewActivity, handleThrottledMetricsUpdate, restartAdaptivePolling]);

  const fetchData = async () => {
    
    try {
      // Only show loading spinner on initial load, not on refresh
      if (metricsData.total_operations === 0 && !operationData && !repositoryData) {
        setLoading(true);
      }
      
      setError(null);
      
      // Store previous data to detect changes
      const previousMetrics = JSON.stringify(metricsData);
      const previousOperations = JSON.stringify(operationData);
      const previousRepositories = JSON.stringify(repositoryData);
      
      const [summaryRes, configRes, operationRes, repositoryRes] = await Promise.all([
        apiService.get('/api/metrics/summary'),
        apiService.get('/api/metrics/config'),
        apiService.get('/api/metrics/operations'),
        apiService.get('/api/metrics/repositories')
      ]);

      const summary = summaryRes.data?.data || summaryRes.data;
      const configData = configRes.data?.data || configRes.data;
      const operationBreakdown = operationRes.data?.data || operationRes.data;
      const repositoryBreakdown = repositoryRes.data?.data || repositoryRes.data;

      // Check if data actually changed
      const newMetrics = JSON.stringify(summary);
      const newOperations = JSON.stringify(operationBreakdown);
      const newRepositories = JSON.stringify(repositoryBreakdown);
      
      const dataChanged = (
        newMetrics !== previousMetrics ||
        newOperations !== previousOperations ||
        newRepositories !== previousRepositories
      );
      
      if (dataChanged) {
        lastDataChangeRef.current = Date.now();
      }

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

      // Apply the new data
      setMetricsData(summary);
      setOperationData(operationBreakdown);
      setRepositoryData(repositoryBreakdown);
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

  // Note: handleRefresh removed since we have auto-refresh now

  const handleRecalculate = async () => {
    try {
      setLoading(true);
      await apiService.post('/api/metrics/recalculate');
      // fetchData will be called automatically via WebSocket events, no need to duplicate
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
      // Trigger immediate refresh after config change
      await fetchData();
    } catch (err) {
      console.error('Error saving config:', err);
      setError('Failed to save configuration');
    } finally {
      setSaving(false);
    }
  };

  const formatCurrency = (amount) => {
    const value = amount || 0;
    let decimals;
    
    if (value >= 10) {
      decimals = 2;
    } else if (value >= 1) {
      decimals = 3;
    } else {
      decimals = 4;
    }
    
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    }).format(value);
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

  const hasData = metricsData.total_operations > 0 || Object.keys(metricsData.model_breakdown || {}).length > 0;

  const tabs = [
    { id: 'overview', name: 'Overview', icon: BarChart3 },
    { id: 'models', name: 'Model Breakdown', icon: Cpu },
    { id: 'operations', name: 'Operation Breakdown', icon: Zap },
    { id: 'repositories', name: 'Repository Breakdown', icon: GitBranch },
    { id: 'configuration', name: 'Configuration', icon: Settings }
  ];

  const renderTabContent = () => {
    if (!hasData && activeTab !== 'configuration') {
      return (
        <div className="text-center py-12">
          <Brain className="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400">AI metrics will appear here once PR-Agent operations with AI models are processed.</p>
        </div>
      );
    }

    const content = (() => {
      switch (activeTab) {
        case 'overview':
          return renderOverviewTab();
        case 'models':
          return renderModelsTab();
        case 'operations':
          return renderOperationsTab();
        case 'repositories':
          return renderRepositoriesTab();
        case 'configuration':
          return renderConfigurationTab();
        default:
          return renderOverviewTab();
      }
    })();

    return <div className="tab-enter">{content}</div>;
  };

  const renderOverviewTab = () => (
    <div className="space-y-6">
      {/* Prominent Net Savings & Dev Time Card */}
      <div className="flex justify-center">
        <div className="w-full max-w-4xl bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-xl shadow-sm border-2 border-green-200 dark:border-green-700 p-8">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            {/* Net Dev Time Saved */}
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 dark:bg-green-900/40 rounded-full mb-4">
                <Clock className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <h3 className="text-lg font-medium text-gray-700 dark:text-gray-300 mb-2">Net Dev Time Saved</h3>
              <p className={`text-4xl font-bold mb-2 ${
                metricsData.total_dev_hours_saved > 0 
                  ? 'text-green-600 dark:text-green-400' 
                  : 'text-gray-600 dark:text-gray-400'
              }`}>
                <AnimatedMetric 
                  value={metricsData.total_dev_hours_saved} 
                  formatter={formatHours}
                  duration={2000}
                />
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Time saved through AI automation
              </p>
            </div>

            {/* Net Savings */}
            <div className="text-center">
              <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 dark:bg-green-900/40 rounded-full mb-4">
                <TrendingUp className="h-8 w-8 text-green-600 dark:text-green-400" />
              </div>
              <h3 className="text-lg font-medium text-gray-700 dark:text-gray-300 mb-2">Net Savings</h3>
              <p className={`text-4xl font-bold mb-2 ${
                metricsData.total_savings > 0 
                  ? 'text-green-600 dark:text-green-400' 
                  : 'text-red-600 dark:text-red-400'
              }`}>
                <AnimatedMetric 
                  value={metricsData.total_savings} 
                  formatter={formatCurrency}
                  duration={2500}
                />
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Developer savings minus AI costs
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Enhanced Summary Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* Total Jobs */}
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 rounded-xl shadow-lg border-2 border-blue-200 dark:border-blue-700 p-8 h-48 flex flex-col items-center justify-center text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-blue-100 dark:bg-blue-900/40 rounded-full mb-3">
            <BarChart3 className="h-7 w-7 text-blue-600 dark:text-blue-400" />
          </div>
          <h3 className="text-lg font-semibold text-blue-900 dark:text-blue-100 mb-2">Total Jobs</h3>
          <p className="text-4xl font-bold text-blue-800 dark:text-blue-200 mb-2">
            <AnimatedMetric 
              value={metricsData.total_jobs} 
              formatter={formatNumber}
              duration={1200}
              integer={true}
            />
          </p>
          <p className="text-xs text-blue-700 dark:text-blue-300">
            AI jobs processed
          </p>
        </div>

        {/* Total Operations */}
        <div className="bg-gradient-to-br from-purple-50 to-pink-50 dark:from-purple-900/20 dark:to-pink-900/20 rounded-xl shadow-lg border-2 border-purple-200 dark:border-purple-700 p-8 h-48 flex flex-col items-center justify-center text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-purple-100 dark:bg-purple-900/40 rounded-full mb-3">
            <Cpu className="h-7 w-7 text-purple-600 dark:text-purple-400" />
          </div>
          <h3 className="text-lg font-semibold text-purple-900 dark:text-purple-100 mb-2">Total Operations</h3>
          <p className="text-4xl font-bold text-purple-800 dark:text-purple-200 mb-2">
            <AnimatedMetric 
              value={metricsData.total_operations} 
              formatter={formatNumber}
              duration={1400}
              integer={true}
            />
          </p>
          <p className="text-xs text-purple-700 dark:text-purple-300">
            AI operations executed
          </p>
        </div>

        {/* Token Cost */}
        <div className="bg-gradient-to-br from-orange-50 to-red-50 dark:from-orange-900/20 dark:to-red-900/20 rounded-xl shadow-lg border-2 border-orange-200 dark:border-orange-700 p-8 h-48 flex flex-col items-center justify-center text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-orange-100 dark:bg-orange-900/40 rounded-full mb-3">
            <DollarSign className="h-7 w-7 text-orange-600 dark:text-orange-400" />
          </div>
          <h3 className="text-lg font-semibold text-orange-900 dark:text-orange-100 mb-2">Token Costs</h3>
          <p className="text-4xl font-bold text-orange-800 dark:text-orange-200 mb-2">
            <AnimatedMetric 
              value={metricsData.total_token_cost} 
              formatter={formatCurrency}
              duration={1600}
            />
          </p>
          <p className="text-xs text-orange-700 dark:text-orange-300">
            Total AI model costs
          </p>
        </div>
      </div>

      {/* Key Metrics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        {/* Total Input Tokens */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center">
            <div className="p-3 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
              <Calculator className="h-6 w-6 text-blue-600 dark:text-blue-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Input Tokens</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                <AnimatedMetric 
                  value={metricsData.total_input_tokens} 
                  formatter={formatNumber}
                  duration={800}
                  integer={true}
                />
              </p>
            </div>
          </div>
        </div>

        {/* Total Output Tokens */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center">
            <div className="p-3 bg-cyan-100 dark:bg-cyan-900/30 rounded-lg">
              <Calculator className="h-6 w-6 text-cyan-600 dark:text-cyan-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Output Tokens</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                <AnimatedMetric 
                  value={metricsData.total_output_tokens} 
                  formatter={formatNumber}
                  duration={900}
                  integer={true}
                />
              </p>
            </div>
          </div>
        </div>

        {/* Models Used */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center">
            <div className="p-3 bg-purple-100 dark:bg-purple-900/30 rounded-lg">
              <Brain className="h-6 w-6 text-purple-600 dark:text-purple-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Models Used</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                <AnimatedMetric 
                  value={Object.keys(metricsData.model_breakdown || {}).length} 
                  duration={1000}
                  integer={true}
                />
              </p>
            </div>
          </div>
        </div>

        {/* Average Cost per Operation */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
          <div className="flex items-center">
            <div className="p-3 bg-indigo-100 dark:bg-indigo-900/30 rounded-lg">
              <Zap className="h-6 w-6 text-indigo-600 dark:text-indigo-400" />
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-600 dark:text-gray-400">Avg Cost/Op</p>
              <p className="text-2xl font-bold text-gray-900 dark:text-white">
                <AnimatedMetric 
                  value={metricsData.total_operations > 0 ? metricsData.total_token_cost / metricsData.total_operations : 0} 
                  formatter={formatCurrency}
                  duration={1100}
                />
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );

  // Helper functions for pie chart and carousel
  const generatePieSlices = (sortedModels, totals) => {
    let currentAngle = 0;
    const colors = [
      '#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
      '#06B6D4', '#F97316', '#84CC16', '#EC4899', '#6366F1'
    ];

    return sortedModels.map(([modelName, data], index) => {
      const percentage = totals.cost > 0 ? (data.total_cost / totals.cost) * 100 : 0;
      const angle = (percentage / 100) * 360;
      const slice = {
        modelName,
        data,
        percentage,
        startAngle: currentAngle,
        endAngle: currentAngle + angle,
        color: colors[index % colors.length],
        index
      };
      currentAngle += angle;
      return slice;
    });
  };

  const createPieSlicePath = (centerX, centerY, radius, startAngle, endAngle) => {
    // Handle full circle case (single data point)
    if (endAngle - startAngle >= 360) {
      return `M ${centerX - radius} ${centerY} A ${radius} ${radius} 0 1 1 ${centerX + radius} ${centerY} A ${radius} ${radius} 0 1 1 ${centerX - radius} ${centerY}`;
    }
    
    const start = {
      x: centerX + radius * Math.cos((startAngle - 90) * Math.PI / 180),
      y: centerY + radius * Math.sin((startAngle - 90) * Math.PI / 180)
    };
    const end = {
      x: centerX + radius * Math.cos((endAngle - 90) * Math.PI / 180),
      y: centerY + radius * Math.sin((endAngle - 90) * Math.PI / 180)
    };
    
    const largeArcFlag = endAngle - startAngle <= 180 ? "0" : "1";
    
    return [
      "M", centerX, centerY,
      "L", start.x, start.y,
      "A", radius, radius, 0, largeArcFlag, 1, end.x, end.y,
      "Z"
    ].join(" ");
  };

  const getModelTier = (model) => {
    const cleanName = model.replace('anthropic/', '').replace('openai/', '');
    if (model.includes('claude-opus-4') || model.includes('claude-sonnet-4') || model.includes('o1') || model.includes('o3') || model.includes('o4')) {
      return { tier: 'premium', icon: '💎', name: cleanName, color: 'from-amber-50 to-yellow-50 dark:from-amber-900/20 dark:to-yellow-900/20 border-amber-200 dark:border-amber-700' };
    }
    if ((model.includes('claude-3-5') || model.includes('gpt-4')) && !model.includes('claude-opus-4') && !model.includes('claude-sonnet-4')) {
      return { tier: 'standard', icon: '⚡', name: cleanName, color: 'from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border-blue-200 dark:border-blue-700' };
    }
    if (model.includes('gpt-3.5') || model.includes('mini')) {
      return { tier: 'budget', icon: '💚', name: cleanName, color: 'from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border-green-200 dark:border-green-700' };
    }
    return { tier: 'other', icon: '🔧', name: cleanName, color: 'from-gray-50 to-slate-50 dark:from-gray-900/20 dark:to-slate-900/20 border-gray-200 dark:border-gray-700' };
  };

  const getOperationType = (operation) => {
    const operationMap = {
      'review': { icon: '🔍', name: 'Review', description: 'AI-powered code review' },
      'describe': { icon: '📝', name: 'Describe', description: 'PR description generation' },
      'improve': { icon: '🚀', name: 'Improve', description: 'Code improvement suggestions' },
      'test': { icon: '🧪', name: 'Test', description: 'Test generation and analysis' },
      'add_docs': { icon: '📚', name: 'Add Docs', description: 'Documentation generation' },
      'update_changelog': { icon: '📋', name: 'Changelog', description: 'Changelog updates' },
      'similar_issue': { icon: '🔗', name: 'Similar Issue', description: 'Similar issue detection' },
      'fetching_context': { icon: '📡', name: 'Fetch Context', description: 'Context data retrieval' },
      'processing_pr': { icon: '⚙️', name: 'Process PR', description: 'PR data processing' },
      'self_reflecting': { icon: '🤔', name: 'Self Reflect', description: 'AI self-reflection process' },
      'publishing_results': { icon: '📤', name: 'Publish', description: 'Results publication' },
      'starting': { icon: '🚀', name: 'Starting', description: 'Operation initialization' },
      'finalizing': { icon: '✅', name: 'Finalizing', description: 'Operation completion' },
      'cleanup': { icon: '🧹', name: 'Cleanup', description: 'Resource cleanup' },
      'unknown': { icon: '❓', name: 'Unknown', description: 'Unknown operation type' }
    };
    
    return operationMap[operation] || operationMap['unknown'];
  };

  const generateOperationPieSlices = (sortedOperations, totals) => {
    const colors = [
      '#3B82F6', '#10B981', '#8B5CF6', '#F59E0B', '#06B6D4', 
      '#EF4444', '#84CC16', '#6B7280', '#F97316', '#EC4899'
    ];
    
    let currentAngle = 0;
    return sortedOperations.map(([operationName, data], index) => {
      const percentage = totals.cost > 0 ? (data.total_cost / totals.cost) * 100 : 0;
      const sweepAngle = (percentage / 100) * 360;
      
      const slice = {
        operationName,
        data,
        startAngle: currentAngle,
        endAngle: currentAngle + sweepAngle,
        percentage,
        color: colors[index % colors.length]
      };
      
      currentAngle += sweepAngle;
      return slice;
    });
  };

  const getRepositoryType = (repository) => {
    // Extract repository name from full path if needed
    const repoName = repository.split('/').pop() || repository;
    
    // Default repository info - you could customize this based on actual repo names
    return {
      icon: FolderGit2,
      name: repoName === 'unknown' ? 'Unknown Repository' : repoName,
      description: `Repository: ${repository}`
    };
  };

  const generateRepositoryPieSlices = (sortedRepositories, totals) => {
    const colors = [
      '#3B82F6', '#10B981', '#8B5CF6', '#F59E0B', '#06B6D4', 
      '#EF4444', '#84CC16', '#6B7280', '#F97316', '#EC4899',
      '#F43F5E', '#06B6D4', '#8B5CF6', '#F59E0B', '#84CC16'
    ];
    
    let currentAngle = 0;
    return sortedRepositories.map(([repositoryName, data], index) => {
      const percentage = totals.cost > 0 ? (data.total_cost / totals.cost) * 100 : 0;
      const sweepAngle = (percentage / 100) * 360;
      
      const slice = {
        repositoryName,
        data,
        startAngle: currentAngle,
        endAngle: currentAngle + sweepAngle,
        percentage,
        color: colors[index % colors.length]
      };
      
      currentAngle += sweepAngle;
      return slice;
    });
  };

  const renderModelsTab = () => {
    const modelBreakdown = metricsData?.model_breakdown || {};
    const modelEntries = Object.entries(modelBreakdown);
    
    if (modelEntries.length === 0) {
      return (
        <div className="text-center py-12">
          <Cpu className="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400">Model breakdown will appear here once AI operations are processed.</p>
        </div>
      );
    }

    // Sort models by total cost (descending)
    const sortedModels = modelEntries.sort(([, a], [, b]) => (b.total_cost || 0) - (a.total_cost || 0));
    
    // Calculate totals for percentage calculations
    const totals = modelEntries.reduce((acc, [, data]) => ({
      operations: acc.operations + (data.operations_count || 0),
      inputTokens: acc.inputTokens + (data.input_tokens || 0),
      outputTokens: acc.outputTokens + (data.output_tokens || 0),
      cost: acc.cost + (data.total_cost || 0),
      hours: acc.hours + (data.estimated_dev_hours || 0)
    }), { operations: 0, inputTokens: 0, outputTokens: 0, cost: 0, hours: 0 });

    const pieSlices = generatePieSlices(sortedModels, totals);
    const currentModel = sortedModels[currentModelIndex];

    const handlePieSliceClick = (sliceIndex) => {
      setCurrentModelIndex(sliceIndex);
    };

    const handleCarouselNav = (direction) => {
      if (direction === 'prev') {
        setCurrentModelIndex(prev => prev > 0 ? prev - 1 : sortedModels.length - 1);
      } else {
        setCurrentModelIndex(prev => prev < sortedModels.length - 1 ? prev + 1 : 0);
      }
    };

    return (
      <div className="space-y-8">

        {/* Pie Chart and Carousel Side by Side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Interactive Pie Chart */}
          <div className="flex flex-col items-center">
            <div className="text-center mb-6">
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Cost Distribution</h3>
              <p className="text-gray-600 dark:text-gray-400">Click on a slice to view model details</p>
            </div>
            
            <div className="relative">
                              <svg width="442" height="442" className="drop-shadow-lg">
                {pieSlices.map((slice, index) => {
                  const isHovered = hoveredPieSlice === index;
                  const isSelected = currentModelIndex === index;
                                      const radius = isHovered ? 173 : isSelected ? 166 : 159;
                  
                  return (
                    <g key={slice.modelName}>
                      <path
                        d={createPieSlicePath(221, 221, radius, slice.startAngle, slice.endAngle)}
                        fill={slice.color}
                        stroke="white"
                        strokeWidth="1"
                        className="cursor-pointer transition-all duration-300 hover:brightness-110"
                        style={{
                          filter: isSelected ? 'drop-shadow(0 4px 8px rgba(0,0,0,0.3)) drop-shadow(0 0 12px rgba(59, 130, 246, 0.5))' : 
                                  isHovered ? 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))' : 'none',
                          opacity: isSelected ? 1 : isHovered ? 0.75 : 0.6
                        }}
                        onMouseEnter={() => setHoveredPieSlice(index)}
                        onMouseLeave={() => setHoveredPieSlice(null)}
                        onClick={() => handlePieSliceClick(index)}
                      />
                      {slice.percentage > 8 && (
                        <text
                          x={221 + (radius - 30) * Math.cos(((slice.startAngle + slice.endAngle) / 2 - 90) * Math.PI / 180)}
                          y={221 + (radius - 30) * Math.sin(((slice.startAngle + slice.endAngle) / 2 - 90) * Math.PI / 180)}
                          textAnchor="middle"
                          dominantBaseline="middle"
                          className="fill-white text-sm font-semibold pointer-events-none"
                          style={{ textShadow: '1px 1px 2px rgba(0,0,0,0.7)' }}
                        >
                          {slice.percentage.toFixed(1)}%
                        </text>
                      )}
                    </g>
                  );
                })}
              </svg>

              {/* Tooltip */}
              {hoveredPieSlice !== null && (
                <div 
                  className="absolute bg-gray-900 text-white px-3 py-2 rounded-lg text-sm font-medium pointer-events-none z-10 shadow-lg"
                  style={{
                    left: '50%',
                    top: '10px',
                    transform: 'translateX(-50%)'
                  }}
                >
                  {pieSlices[hoveredPieSlice]?.modelName.replace('anthropic/', '').replace('openai/', '')}
                  <div className="text-xs text-gray-300">
                    {formatCurrency(pieSlices[hoveredPieSlice]?.data.total_cost)} ({pieSlices[hoveredPieSlice]?.percentage.toFixed(1)}%)
                  </div>
                </div>
              )}
            </div>

            {/* Navigation Controls Below Pie Chart */}
            {currentModel && (
              <div className="flex items-center justify-center space-x-6 mt-6">
                <button
                  onClick={() => handleCarouselNav('prev')}
                  className="p-3 rounded-lg bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors shadow-sm"
                  title="Previous model"
                >
                  <ChevronLeft className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                </button>
                <div className="flex items-center space-x-3 bg-gray-100 dark:bg-gray-700 rounded-lg px-4 py-2">
                  <span className="text-lg font-medium text-gray-900 dark:text-white">
                    {currentModelIndex + 1}
                  </span>
                  <span className="text-gray-500 dark:text-gray-400">/</span>
                  <span className="text-lg font-medium text-gray-900 dark:text-white">
                    {sortedModels.length}
                  </span>
                </div>
                <button
                  onClick={() => handleCarouselNav('next')}
                  className="p-3 rounded-lg bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors shadow-sm"
                  title="Next model"
                >
                  <ChevronRight className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                </button>
              </div>
            )}
          </div>

          {/* Enhanced Model Carousel */}
          {currentModel && (
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              {/* Carousel Content with Animation */}
              <div className="relative overflow-hidden" style={{ minHeight: 'fit-content' }}>
                <div 
                  className="flex transition-transform duration-500 ease-in-out"
                  style={{ transform: `translateX(-${currentModelIndex * 100}%)` }}
                >
                  {sortedModels.map(([modelName, data], index) => {
                    const modelTier = getModelTier(modelName);
                    return (
                      <div key={modelName} className="w-full flex-shrink-0 p-6 flex flex-col">
                        {/* Model Header */}
                        <div className="flex items-center space-x-3 mb-4">
                          <div className="text-2xl">{modelTier.icon}</div>
                          <div className="flex-1">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                              {modelName.replace('anthropic/', '').replace('openai/', '')}
                            </h3>
                            <div className="flex items-center space-x-3 text-xs text-gray-600 dark:text-gray-400 mt-1">
                              <span className="capitalize font-medium">{modelTier.tier} tier</span>
                              <span className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 px-2 py-0.5 rounded-full">
                                #{index + 1} by cost
                              </span>
                              <span className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 px-2 py-0.5 rounded-full">
                                {((data.total_cost / totals.cost) * 100).toFixed(1)}%
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Cost vs Savings Highlight */}
                        <div className="text-center mb-4 p-4 bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-lg border border-green-200 dark:border-green-700">
                          <div className="text-xs font-semibold text-green-700 dark:text-green-300 mb-2 uppercase tracking-wide">
                            Financial Impact
                          </div>
                          {(() => {
                            const devCostSaved = (data.estimated_dev_hours || 0) * (config?.developer_hourly_rate || 75) * (config?.hours_multiplier || 1.0);
                            const netSavings = devCostSaved - (data.total_cost || 0);
                            return (
                              <>
                                <div className="grid grid-cols-2 gap-3 mb-2">
                                  <div>
                                    <div className="text-sm font-semibold text-red-600 dark:text-red-400">Cost</div>
                                    <div className="text-lg font-bold text-red-700 dark:text-red-300">
                                      {formatCurrency(data.total_cost)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-sm font-semibold text-green-600 dark:text-green-400">Saved</div>
                                    <div className="text-lg font-bold text-green-700 dark:text-green-300">
                                      {formatCurrency(devCostSaved)}
                                    </div>
                                  </div>
                                </div>
                                <div className="pt-2 border-t border-green-200 dark:border-green-700">
                                  <div className="text-xs text-green-600 dark:text-green-400 mb-1">Net Savings</div>
                                  <div className={`text-xl font-bold ${netSavings >= 0 ? 'text-green-800 dark:text-green-200' : 'text-red-800 dark:text-red-200'}`}>
                                    {formatCurrency(Math.abs(netSavings))} {netSavings >= 0 ? 'saved' : 'loss'}
                                  </div>
                                  <div className="text-xs text-green-500 dark:text-green-300 opacity-80">
                                    ROI: {data.total_cost > 0 ? (((devCostSaved - data.total_cost) / data.total_cost * 100).toFixed(0)) : '∞'}%
                                  </div>
                                </div>
                              </>
                            );
                          })()}
                        </div>

                        {/* Compact Stats Grid */}
                        <div className="grid grid-cols-2 gap-3 mb-4 flex-1">
                          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 border border-blue-200 dark:border-blue-700">
                            <div className="flex items-center justify-between mb-1">
                              <BarChart3 className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                              <span className="text-xs font-medium text-blue-700 dark:text-blue-300">Operations</span>
                            </div>
                            <div className="text-lg font-bold text-blue-800 dark:text-blue-200">
                              {formatNumber(data.operations_count)}
                            </div>
                            <div className="text-xs text-blue-600 dark:text-blue-400">
                              {((data.operations_count / totals.operations) * 100).toFixed(1)}% of total
                            </div>
                          </div>
                          
                          <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3 border border-purple-200 dark:border-purple-700">
                            <div className="flex items-center justify-between mb-1">
                              <Clock className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                              <span className="text-xs font-medium text-purple-700 dark:text-purple-300">Dev Hours</span>
                            </div>
                            <div className="text-lg font-bold text-purple-800 dark:text-purple-200">
                              {formatHours(data.estimated_dev_hours)}
                            </div>
                            <div className="text-xs text-purple-600 dark:text-purple-400">
                              {((data.estimated_dev_hours / totals.hours) * 100).toFixed(1)}% of total
                            </div>
                          </div>
                          
                          <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3 border border-orange-200 dark:border-orange-700">
                            <div className="flex items-center justify-between mb-1">
                              <ArrowUp className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                              <span className="text-xs font-medium text-orange-700 dark:text-orange-300">Input</span>
                            </div>
                            <div className="text-lg font-bold text-orange-800 dark:text-orange-200">
                              {formatNumber(data.input_tokens)}
                            </div>
                            <div className="text-xs text-orange-600 dark:text-orange-400">
                              {formatNumber(Math.round(data.input_tokens / data.operations_count))} avg/op
                            </div>
                          </div>
                          
                          <div className="bg-pink-50 dark:bg-pink-900/20 rounded-lg p-3 border border-pink-200 dark:border-pink-700">
                            <div className="flex items-center justify-between mb-1">
                              <ArrowDown className="h-4 w-4 text-pink-600 dark:text-pink-400" />
                              <span className="text-xs font-medium text-pink-700 dark:text-pink-300">Output</span>
                            </div>
                            <div className="text-lg font-bold text-pink-800 dark:text-pink-200">
                              {formatNumber(data.output_tokens)}
                            </div>
                            <div className="text-xs text-pink-600 dark:text-pink-400">
                              {formatNumber(Math.round(data.output_tokens / data.operations_count))} avg/op
                            </div>
                          </div>
                        </div>

                        {/* Compact Efficiency Metrics */}
                        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-700">
                          <div className="flex items-center mb-2">
                            <TrendingUp className="h-4 w-4 text-gray-600 dark:text-gray-400 mr-2" />
                            <span className="text-xs font-semibold text-gray-900 dark:text-white">Efficiency</span>
                          </div>
                          <div className="space-y-1 text-xs">
                            <div className="flex justify-between items-center">
                              <span className="text-gray-600 dark:text-gray-400">Cost/1K tokens</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {data.input_tokens + data.output_tokens > 0 ? 
                                  formatCurrency(data.total_cost / ((data.input_tokens + data.output_tokens) / 1000)) : '$0.00'}
                              </span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-gray-600 dark:text-gray-400">Hours saved/$</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {data.total_cost > 0 ? formatHours(data.estimated_dev_hours / data.total_cost) : '0h'}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>


      </div>
    );
  };

  const renderOperationsTab = () => {
    const operationBreakdown = operationData?.operation_breakdown || {};
    const operationEntries = Object.entries(operationBreakdown);
    
    if (operationEntries.length === 0) {
      return (
        <div className="text-center py-12">
          <Zap className="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400">Operation breakdown will appear here once AI operations are processed.</p>
        </div>
      );
    }

    // Sort operations by total cost (descending)
    const sortedOperations = operationEntries.sort(([, a], [, b]) => (b.total_cost || 0) - (a.total_cost || 0));
    
    // Calculate totals for percentage calculations
    const totals = operationEntries.reduce((acc, [, data]) => ({
      operations: acc.operations + (data.operations_count || 0),
      inputTokens: acc.inputTokens + (data.input_tokens || 0),
      outputTokens: acc.outputTokens + (data.output_tokens || 0),
      cost: acc.cost + (data.total_cost || 0),
      hours: acc.hours + (data.estimated_dev_hours || 0)
    }), { operations: 0, inputTokens: 0, outputTokens: 0, cost: 0, hours: 0 });

    const pieSlices = generateOperationPieSlices(sortedOperations, totals);
    const currentOperation = sortedOperations[currentOperationIndex];

    const handleOperationPieSliceClick = (sliceIndex) => {
      setCurrentOperationIndex(sliceIndex);
    };

    const handleOperationCarouselNav = (direction) => {
      if (direction === 'prev') {
        setCurrentOperationIndex(prev => prev > 0 ? prev - 1 : sortedOperations.length - 1);
      } else {
        setCurrentOperationIndex(prev => prev < sortedOperations.length - 1 ? prev + 1 : 0);
      }
    };

    return (
      <div className="space-y-8">

        {/* Pie Chart and Carousel Side by Side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Interactive Pie Chart */}
          <div className="flex flex-col items-center">
            <div className="text-center mb-6">
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Cost Distribution by Operation</h3>
              <p className="text-gray-600 dark:text-gray-400">Click on a slice to view operation details</p>
            </div>
            
            <div className="relative">
              <svg width="442" height="442" className="drop-shadow-lg">
                {pieSlices.map((slice, index) => {
                  const isHovered = hoveredPieSlice === index;
                  const isSelected = currentOperationIndex === index;
                  const radius = isHovered ? 173 : isSelected ? 166 : 159;
                  
                  return (
                    <g key={slice.operationName}>
                      <path
                        d={createPieSlicePath(221, 221, radius, slice.startAngle, slice.endAngle)}
                        fill={slice.color}
                        stroke="white"
                        strokeWidth="1"
                        className="cursor-pointer transition-all duration-300 hover:brightness-110"
                        style={{
                          filter: isSelected ? 'drop-shadow(0 4px 8px rgba(0,0,0,0.3)) drop-shadow(0 0 12px rgba(59, 130, 246, 0.5))' : 
                                  isHovered ? 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))' : 'none',
                          opacity: isSelected ? 1 : isHovered ? 0.75 : 0.6
                        }}
                        onMouseEnter={() => setHoveredPieSlice(index)}
                        onMouseLeave={() => setHoveredPieSlice(null)}
                        onClick={() => handleOperationPieSliceClick(index)}
                      />
                      {slice.percentage > 8 && (
                        <text
                          x={221 + (radius - 30) * Math.cos(((slice.startAngle + slice.endAngle) / 2 - 90) * Math.PI / 180)}
                          y={221 + (radius - 30) * Math.sin(((slice.startAngle + slice.endAngle) / 2 - 90) * Math.PI / 180)}
                          textAnchor="middle"
                          dominantBaseline="middle"
                          className="fill-white text-sm font-semibold pointer-events-none"
                          style={{ textShadow: '1px 1px 2px rgba(0,0,0,0.7)' }}
                        >
                          {slice.percentage.toFixed(1)}%
                        </text>
                      )}
                    </g>
                  );
                })}
              </svg>

              {/* Tooltip */}
              {hoveredPieSlice !== null && (
                <div 
                  className="absolute bg-gray-900 text-white px-3 py-2 rounded-lg text-sm font-medium pointer-events-none z-10 shadow-lg"
                  style={{
                    left: '50%',
                    top: '10px',
                    transform: 'translateX(-50%)'
                  }}
                >
                  {getOperationType(pieSlices[hoveredPieSlice]?.operationName).name}
                  <div className="text-xs text-gray-300">
                    {formatCurrency(pieSlices[hoveredPieSlice]?.data.total_cost)} ({pieSlices[hoveredPieSlice]?.percentage.toFixed(1)}%)
                  </div>
                </div>
              )}
            </div>

            {/* Navigation Controls Below Pie Chart */}
            {currentOperation && (
              <div className="flex items-center justify-center space-x-6 mt-6">
                <button
                  onClick={() => handleOperationCarouselNav('prev')}
                  className="p-3 rounded-lg bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors shadow-sm"
                  title="Previous operation"
                >
                  <ChevronLeft className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                </button>
                <div className="flex items-center space-x-3 bg-gray-100 dark:bg-gray-700 rounded-lg px-4 py-2">
                  <span className="text-lg font-medium text-gray-900 dark:text-white">
                    {currentOperationIndex + 1}
                  </span>
                  <span className="text-gray-500 dark:text-gray-400">/</span>
                  <span className="text-lg font-medium text-gray-900 dark:text-white">
                    {sortedOperations.length}
                  </span>
                </div>
                <button
                  onClick={() => handleOperationCarouselNav('next')}
                  className="p-3 rounded-lg bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors shadow-sm"
                  title="Next operation"
                >
                  <ChevronRight className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                </button>
              </div>
            )}
          </div>

          {/* Enhanced Operation Carousel */}
          {currentOperation && (
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              {/* Carousel Content with Animation */}
              <div className="relative overflow-hidden" style={{ minHeight: 'fit-content' }}>
                <div 
                  className="flex transition-transform duration-500 ease-in-out"
                  style={{ transform: `translateX(-${currentOperationIndex * 100}%)` }}
                >
                  {sortedOperations.map(([operationName, data], index) => {
                    const operationType = getOperationType(operationName);
                    return (
                      <div key={operationName} className="w-full flex-shrink-0 p-6 flex flex-col">
                        {/* Operation Header */}
                        <div className="flex items-center space-x-3 mb-4">
                          <div className="text-2xl">{operationType.icon}</div>
                          <div className="flex-1">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                              {operationType.name}
                            </h3>
                            <div className="flex items-center space-x-3 text-xs text-gray-600 dark:text-gray-400 mt-1">
                              <span className="text-gray-500 dark:text-gray-400">{operationType.description}</span>
                            </div>
                            <div className="flex items-center space-x-3 text-xs text-gray-600 dark:text-gray-400 mt-1">
                              <span className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 px-2 py-0.5 rounded-full">
                                #{index + 1} by cost
                              </span>
                              <span className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 px-2 py-0.5 rounded-full">
                                {((data.total_cost / totals.cost) * 100).toFixed(1)}%
                              </span>
                              <span className="bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200 px-2 py-0.5 rounded-full">
                                {data.success_rate}% success
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Cost vs Savings Highlight */}
                        <div className="text-center mb-4 p-4 bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-lg border border-green-200 dark:border-green-700">
                          <div className="text-xs font-semibold text-green-700 dark:text-green-300 mb-2 uppercase tracking-wide">
                            Financial Impact
                          </div>
                          {(() => {
                            const devCostSaved = (data.estimated_dev_hours || 0) * (config?.developer_hourly_rate || 75) * (config?.hours_multiplier || 1.0);
                            const netSavings = devCostSaved - (data.total_cost || 0);
                            return (
                              <>
                                <div className="grid grid-cols-2 gap-3 mb-2">
                                  <div>
                                    <div className="text-sm font-semibold text-red-600 dark:text-red-400">Cost</div>
                                    <div className="text-lg font-bold text-red-700 dark:text-red-300">
                                      {formatCurrency(data.total_cost)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-sm font-semibold text-green-600 dark:text-green-400">Saved</div>
                                    <div className="text-lg font-bold text-green-700 dark:text-green-300">
                                      {formatCurrency(devCostSaved)}
                                    </div>
                                  </div>
                                </div>
                                <div className="pt-2 border-t border-green-200 dark:border-green-700">
                                  <div className="text-xs text-green-600 dark:text-green-400 mb-1">Net Savings</div>
                                  <div className={`text-xl font-bold ${netSavings >= 0 ? 'text-green-800 dark:text-green-200' : 'text-red-800 dark:text-red-200'}`}>
                                    {formatCurrency(Math.abs(netSavings))} {netSavings >= 0 ? 'saved' : 'loss'}
                                  </div>
                                  <div className="text-xs text-green-500 dark:text-green-300 opacity-80">
                                    ROI: {data.total_cost > 0 ? (((devCostSaved - data.total_cost) / data.total_cost * 100).toFixed(0)) : '∞'}%
                                  </div>
                                </div>
                              </>
                            );
                          })()}
                        </div>

                        {/* Stats Grid */}
                        <div className="grid grid-cols-2 gap-3 mb-4 flex-1">
                          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 border border-blue-200 dark:border-blue-700">
                            <div className="flex items-center justify-between mb-1">
                              <BarChart3 className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                              <span className="text-xs font-medium text-blue-700 dark:text-blue-300">Operations</span>
                            </div>
                            <div className="text-lg font-bold text-blue-800 dark:text-blue-200">
                              {formatNumber(data.operations_count)}
                            </div>
                            <div className="text-xs text-blue-600 dark:text-blue-400">
                              {((data.operations_count / totals.operations) * 100).toFixed(1)}% of total
                            </div>
                          </div>
                          
                          <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3 border border-purple-200 dark:border-purple-700">
                            <div className="flex items-center justify-between mb-1">
                              <Clock className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                              <span className="text-xs font-medium text-purple-700 dark:text-purple-300">Dev Hours</span>
                            </div>
                            <div className="text-lg font-bold text-purple-800 dark:text-purple-200">
                              {formatHours(data.estimated_dev_hours)}
                            </div>
                            <div className="text-xs text-purple-600 dark:text-purple-400">
                              {formatHours(data.avg_dev_hours)} avg/op
                            </div>
                          </div>
                          
                          <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3 border border-orange-200 dark:border-orange-700">
                            <div className="flex items-center justify-between mb-1">
                              <ArrowUp className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                              <span className="text-xs font-medium text-orange-700 dark:text-orange-300">Input</span>
                            </div>
                            <div className="text-lg font-bold text-orange-800 dark:text-orange-200">
                              {formatNumber(data.input_tokens)}
                            </div>
                            <div className="text-xs text-orange-600 dark:text-orange-400">
                              {formatNumber(data.avg_input_tokens)} avg/op
                            </div>
                          </div>
                          
                          <div className="bg-pink-50 dark:bg-pink-900/20 rounded-lg p-3 border border-pink-200 dark:border-pink-700">
                            <div className="flex items-center justify-between mb-1">
                              <ArrowDown className="h-4 w-4 text-pink-600 dark:text-pink-400" />
                              <span className="text-xs font-medium text-pink-700 dark:text-pink-300">Output</span>
                            </div>
                            <div className="text-lg font-bold text-pink-800 dark:text-pink-200">
                              {formatNumber(data.output_tokens)}
                            </div>
                            <div className="text-xs text-pink-600 dark:text-pink-400">
                              {formatNumber(data.avg_output_tokens)} avg/op
                            </div>
                          </div>
                        </div>

                        {/* Performance Metrics */}
                        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-700">
                          <div className="flex items-center mb-2">
                            <TrendingUp className="h-4 w-4 text-gray-600 dark:text-gray-400 mr-2" />
                            <span className="text-xs font-semibold text-gray-900 dark:text-white">Performance</span>
                          </div>
                          <div className="space-y-1 text-xs">
                            <div className="flex justify-between items-center">
                              <span className="text-gray-600 dark:text-gray-400">Avg Duration</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {data.avg_duration ? `${data.avg_duration}s` : 'N/A'}
                              </span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-gray-600 dark:text-gray-400">Models Used</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {data.models_used ? data.models_used.length : 0}
                              </span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-gray-600 dark:text-gray-400">Cost/1K tokens</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {data.input_tokens + data.output_tokens > 0 ? 
                                  formatCurrency(data.total_cost / ((data.input_tokens + data.output_tokens) / 1000)) : '$0.00'}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>


      </div>
    );
  };

  const renderRepositoriesTab = () => {
    const repositoryBreakdown = repositoryData?.repository_breakdown || {};
    const repositoryEntries = Object.entries(repositoryBreakdown);
    
    if (repositoryEntries.length === 0) {
      return (
        <div className="text-center py-12">
          <Star className="h-12 w-12 text-gray-400 dark:text-gray-500 mx-auto mb-4" />
          <p className="text-gray-500 dark:text-gray-400">Repository breakdown will appear here once AI operations are processed.</p>
        </div>
      );
    }

    // Sort repositories by total cost (descending)
    const sortedRepositories = repositoryEntries.sort(([, a], [, b]) => (b.total_cost || 0) - (a.total_cost || 0));
    
    // Calculate totals for percentage calculations
    const totals = repositoryEntries.reduce((acc, [, data]) => ({
      operations: acc.operations + (data.operations_count || 0),
      inputTokens: acc.inputTokens + (data.input_tokens || 0),
      outputTokens: acc.outputTokens + (data.output_tokens || 0),
      cost: acc.cost + (data.total_cost || 0),
      hours: acc.hours + (data.estimated_dev_hours || 0),
      jobs: acc.jobs + (data.unique_jobs_count || 0)
    }), { operations: 0, inputTokens: 0, outputTokens: 0, cost: 0, hours: 0, jobs: 0 });

    const pieSlices = generateRepositoryPieSlices(sortedRepositories, totals);
    const currentRepository = sortedRepositories[currentRepositoryIndex];

    const handleRepositoryPieSliceClick = (sliceIndex) => {
      setCurrentRepositoryIndex(sliceIndex);
    };

    const handleRepositoryCarouselNav = (direction) => {
      if (direction === 'prev') {
        setCurrentRepositoryIndex(prev => prev > 0 ? prev - 1 : sortedRepositories.length - 1);
      } else {
        setCurrentRepositoryIndex(prev => prev < sortedRepositories.length - 1 ? prev + 1 : 0);
      }
    };

    return (
      <div className="space-y-8">

        {/* Pie Chart and Carousel Side by Side */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
          {/* Interactive Pie Chart */}
          <div className="flex flex-col items-center">
            <div className="text-center mb-6">
              <h3 className="text-2xl font-bold text-gray-900 dark:text-white mb-2">Cost Distribution by Repository</h3>
              <p className="text-gray-600 dark:text-gray-400">Click on a slice to view repository details</p>
            </div>
            
            <div className="relative">
              <svg width="442" height="442" className="drop-shadow-lg">
                {pieSlices.map((slice, index) => {
                  const isHovered = hoveredPieSlice === index;
                  const isSelected = currentRepositoryIndex === index;
                  const radius = isHovered ? 173 : isSelected ? 166 : 159;
                  
                  return (
                    <g key={slice.repositoryName}>
                      <path
                        d={createPieSlicePath(221, 221, radius, slice.startAngle, slice.endAngle)}
                        fill={slice.color}
                        stroke="white"
                        strokeWidth="1"
                        className="cursor-pointer transition-all duration-300 hover:brightness-110"
                        style={{
                          filter: isSelected ? 'drop-shadow(0 4px 8px rgba(0,0,0,0.3)) drop-shadow(0 0 12px rgba(59, 130, 246, 0.5))' : 
                                  isHovered ? 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))' : 'none',
                          opacity: isSelected ? 1 : isHovered ? 0.75 : 0.6
                        }}
                        onMouseEnter={() => setHoveredPieSlice(index)}
                        onMouseLeave={() => setHoveredPieSlice(null)}
                        onClick={() => handleRepositoryPieSliceClick(index)}
                      />
                      {slice.percentage > 8 && (
                        <text
                          x={221 + (radius - 30) * Math.cos(((slice.startAngle + slice.endAngle) / 2 - 90) * Math.PI / 180)}
                          y={221 + (radius - 30) * Math.sin(((slice.startAngle + slice.endAngle) / 2 - 90) * Math.PI / 180)}
                          textAnchor="middle"
                          dominantBaseline="middle"
                          className="fill-white text-sm font-semibold pointer-events-none"
                          style={{ textShadow: '1px 1px 2px rgba(0,0,0,0.7)' }}
                        >
                          {slice.percentage.toFixed(1)}%
                        </text>
                      )}
                    </g>
                  );
                })}
              </svg>

              {/* Tooltip */}
              {hoveredPieSlice !== null && (
                <div 
                  className="absolute bg-gray-900 text-white px-3 py-2 rounded-lg text-sm font-medium pointer-events-none z-10 shadow-lg"
                  style={{
                    left: '50%',
                    top: '10px',
                    transform: 'translateX(-50%)'
                  }}
                >
                  {getRepositoryType(pieSlices[hoveredPieSlice]?.repositoryName).name}
                  <div className="text-xs text-gray-300">
                    {formatCurrency(pieSlices[hoveredPieSlice]?.data.total_cost)} ({pieSlices[hoveredPieSlice]?.percentage.toFixed(1)}%)
                  </div>
                </div>
              )}
            </div>

            {/* Navigation Controls Below Pie Chart */}
            {currentRepository && (
              <div className="flex items-center justify-center space-x-6 mt-6">
                <button
                  onClick={() => handleRepositoryCarouselNav('prev')}
                  className="p-3 rounded-lg bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors shadow-sm"
                  title="Previous repository"
                >
                  <ChevronLeft className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                </button>
                <div className="flex items-center space-x-3 bg-gray-100 dark:bg-gray-700 rounded-lg px-4 py-2">
                  <span className="text-lg font-medium text-gray-900 dark:text-white">
                    {currentRepositoryIndex + 1}
                  </span>
                  <span className="text-gray-500 dark:text-gray-400">/</span>
                  <span className="text-lg font-medium text-gray-900 dark:text-white">
                    {sortedRepositories.length}
                  </span>
                </div>
                <button
                  onClick={() => handleRepositoryCarouselNav('next')}
                  className="p-3 rounded-lg bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-50 dark:hover:bg-gray-600 transition-colors shadow-sm"
                  title="Next repository"
                >
                  <ChevronRight className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                </button>
              </div>
            )}
          </div>

          {/* Enhanced Repository Carousel */}
          {currentRepository && (
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
              {/* Carousel Content with Animation */}
              <div className="relative overflow-hidden" style={{ minHeight: 'fit-content' }}>
                <div 
                  className="flex transition-transform duration-500 ease-in-out"
                  style={{ transform: `translateX(-${currentRepositoryIndex * 100}%)` }}
                >
                  {sortedRepositories.map(([repositoryName, data], index) => {
                    const repositoryType = getRepositoryType(repositoryName);
                    return (
                      <div key={repositoryName} className="w-full flex-shrink-0 p-6 flex flex-col">
                        {/* Repository Header */}
                        <div className="flex items-center space-x-3 mb-4">
                          <div className="text-blue-600 dark:text-blue-400">
                            {React.createElement(repositoryType.icon, { className: "h-8 w-8" })}
                          </div>
                          <div className="flex-1">
                            <h3 className="text-lg font-bold text-gray-900 dark:text-white">
                              {repositoryType.name}
                            </h3>
                            <div className="flex items-center space-x-3 text-xs text-gray-600 dark:text-gray-400 mt-1">
                              <span className="text-gray-500 dark:text-gray-400">{repositoryType.description}</span>
                            </div>
                            <div className="flex items-center space-x-3 text-xs text-gray-600 dark:text-gray-400 mt-1">
                              <span className="bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-200 px-2 py-0.5 rounded-full">
                                #{index + 1} by cost
                              </span>
                              <span className="bg-green-100 dark:bg-green-900/30 text-green-800 dark:text-green-200 px-2 py-0.5 rounded-full">
                                {((data.total_cost / totals.cost) * 100).toFixed(1)}%
                              </span>
                              <span className="bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200 px-2 py-0.5 rounded-full">
                                {data.success_rate}% success
                              </span>
                            </div>
                          </div>
                        </div>

                        {/* Cost vs Savings Highlight */}
                        <div className="text-center mb-4 p-4 bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 rounded-lg border border-green-200 dark:border-green-700">
                          <div className="text-xs font-semibold text-green-700 dark:text-green-300 mb-2 uppercase tracking-wide">
                            Financial Impact
                          </div>
                          {(() => {
                            const devCostSaved = (data.estimated_dev_hours || 0) * (config?.developer_hourly_rate || 75) * (config?.hours_multiplier || 1.0);
                            const netSavings = devCostSaved - (data.total_cost || 0);
                            return (
                              <>
                                <div className="grid grid-cols-2 gap-3 mb-2">
                                  <div>
                                    <div className="text-sm font-semibold text-red-600 dark:text-red-400">Cost</div>
                                    <div className="text-lg font-bold text-red-700 dark:text-red-300">
                                      {formatCurrency(data.total_cost)}
                                    </div>
                                  </div>
                                  <div>
                                    <div className="text-sm font-semibold text-green-600 dark:text-green-400">Saved</div>
                                    <div className="text-lg font-bold text-green-700 dark:text-green-300">
                                      {formatCurrency(devCostSaved)}
                                    </div>
                                  </div>
                                </div>
                                <div className="pt-2 border-t border-green-200 dark:border-green-700">
                                  <div className="text-xs text-green-600 dark:text-green-400 mb-1">Net Savings</div>
                                  <div className={`text-xl font-bold ${netSavings >= 0 ? 'text-green-800 dark:text-green-200' : 'text-red-800 dark:text-red-200'}`}>
                                    {formatCurrency(Math.abs(netSavings))} {netSavings >= 0 ? 'saved' : 'loss'}
                                  </div>
                                  <div className="text-xs text-green-500 dark:text-green-300 opacity-80">
                                    ROI: {data.total_cost > 0 ? (((devCostSaved - data.total_cost) / data.total_cost * 100).toFixed(0)) : '∞'}%
                                  </div>
                                </div>
                              </>
                            );
                          })()}
                        </div>

                        {/* Stats Grid */}
                        <div className="grid grid-cols-2 gap-3 mb-4 flex-1">
                          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 border border-blue-200 dark:border-blue-700">
                            <div className="flex items-center justify-between mb-1">
                              <BarChart3 className="h-4 w-4 text-blue-600 dark:text-blue-400" />
                              <span className="text-xs font-medium text-blue-700 dark:text-blue-300">Operations</span>
                            </div>
                            <div className="text-lg font-bold text-blue-800 dark:text-blue-200">
                              {formatNumber(data.operations_count)}
                            </div>
                            <div className="text-xs text-blue-600 dark:text-blue-400">
                              {data.ops_per_job} ops/job
                            </div>
                          </div>
                          
                          <div className="bg-purple-50 dark:bg-purple-900/20 rounded-lg p-3 border border-purple-200 dark:border-purple-700">
                            <div className="flex items-center justify-between mb-1">
                              <Clock className="h-4 w-4 text-purple-600 dark:text-purple-400" />
                              <span className="text-xs font-medium text-purple-700 dark:text-purple-300">Dev Hours</span>
                            </div>
                            <div className="text-lg font-bold text-purple-800 dark:text-purple-200">
                              {formatHours(data.estimated_dev_hours)}
                            </div>
                            <div className="text-xs text-purple-600 dark:text-purple-400">
                              {formatHours(data.avg_dev_hours)} avg/op
                            </div>
                          </div>
                          
                          <div className="bg-orange-50 dark:bg-orange-900/20 rounded-lg p-3 border border-orange-200 dark:border-orange-700">
                            <div className="flex items-center justify-between mb-1">
                              <ArrowUp className="h-4 w-4 text-orange-600 dark:text-orange-400" />
                              <span className="text-xs font-medium text-orange-700 dark:text-orange-300">Jobs</span>
                            </div>
                            <div className="text-lg font-bold text-orange-800 dark:text-orange-200">
                              {formatNumber(data.unique_jobs_count)}
                            </div>
                            <div className="text-xs text-orange-600 dark:text-orange-400">
                              {((data.unique_jobs_count / totals.jobs) * 100).toFixed(1)}% of total
                            </div>
                          </div>
                          
                          <div className="bg-pink-50 dark:bg-pink-900/20 rounded-lg p-3 border border-pink-200 dark:border-pink-700">
                            <div className="flex items-center justify-between mb-1">
                              <Zap className="h-4 w-4 text-pink-600 dark:text-pink-400" />
                              <span className="text-xs font-medium text-pink-700 dark:text-pink-300">Op Types</span>
                            </div>
                            <div className="text-lg font-bold text-pink-800 dark:text-pink-200">
                              {data.operation_types ? data.operation_types.length : 0}
                            </div>
                            <div className="text-xs text-pink-600 dark:text-pink-400">
                              {data.models_used ? data.models_used.length : 0} models
                            </div>
                          </div>
                        </div>

                        {/* Performance Metrics */}
                        <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 border border-gray-200 dark:border-gray-700">
                          <div className="flex items-center mb-2">
                            <TrendingUp className="h-4 w-4 text-gray-600 dark:text-gray-400 mr-2" />
                            <span className="text-xs font-semibold text-gray-900 dark:text-white">Performance</span>
                          </div>
                          <div className="space-y-1 text-xs">
                            <div className="flex justify-between items-center">
                              <span className="text-gray-600 dark:text-gray-400">Avg Duration</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {data.avg_duration ? `${data.avg_duration}s` : 'N/A'}
                              </span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-gray-600 dark:text-gray-400">Cost/operation</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {formatCurrency(data.cost_per_operation || 0)}
                              </span>
                            </div>
                            <div className="flex justify-between items-center">
                              <span className="text-gray-600 dark:text-gray-400">Tokens/op</span>
                              <span className="font-medium text-gray-900 dark:text-white">
                                {formatNumber((data.avg_input_tokens || 0) + (data.avg_output_tokens || 0))}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}
        </div>


      </div>
    );
  };

  const renderConfigurationTab = () => {
    const models = getRelevantModels();
    const categories = {
      premium: {
        name: 'Premium Models',
        icon: Crown,
        models: models.filter(m => 
          m.includes('claude-opus-4') || m.includes('claude-sonnet-4') || m.includes('o1') || m.includes('o3') || m.includes('o4')
        )
      },
      standard: {
        name: 'Standard Models', 
        icon: Star,
        models: models.filter(m => 
          (m.includes('claude-3-5') || m.includes('gpt-4')) && !m.includes('claude-opus-4') && !m.includes('claude-sonnet-4')
        )
      },
      budget: {
        name: 'Budget Models',
        icon: Wallet, 
        models: models.filter(m => 
          m.includes('gpt-3.5') || m.includes('mini')
        )
      },
      other: {
        name: 'Other Models',
        icon: Zap,
        models: models.filter(m => 
          !m.includes('claude-opus-4') && !m.includes('claude-sonnet-4') && !m.includes('o1') && !m.includes('o3') && !m.includes('o4') &&
          !m.includes('claude-3-5') && !m.includes('gpt-4') && !m.includes('gpt-3.5') && !m.includes('mini')
        )
      }
    };
    
    // Filter out empty categories
    const availableCategories = Object.entries(categories).filter(([, category]) => category.models.length > 0);

    return (
      <div className="space-y-8">

        {/* Enhanced Basic Settings */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="bg-gradient-to-r from-gray-50 to-gray-100 dark:from-gray-800 dark:to-gray-700 px-6 py-4 border-b border-gray-200 dark:border-gray-600">
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center">
              <Settings className="h-6 w-6 mr-3 text-blue-600 dark:text-blue-400" />
              Economic Parameters
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Configure the baseline values used for calculating developer productivity and cost savings
            </p>
          </div>
          <div className="p-6">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Developer Hourly Rate */}
              <div className="space-y-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
                    <DollarSign className="h-5 w-5 text-blue-600 dark:text-blue-400" />
                  </div>
                  <div>
                    <label className="block text-lg font-medium text-gray-900 dark:text-white">
                      Developer Hourly Rate
                    </label>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      Average cost per developer hour in your organization
                    </p>
                  </div>
                </div>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <span className="text-gray-500 text-lg">$</span>
                  </div>
                  <input
                    type="number"
                    value={editableConfig.developer_hourly_rate}
                    onChange={(e) => setEditableConfig(prev => ({
                      ...prev,
                      developer_hourly_rate: parseFloat(e.target.value) || 0
                    }))}
                    className="w-full pl-8 pr-4 py-3 text-lg border-2 border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                    placeholder="75"
                  />
                  <div className="absolute inset-y-0 right-0 pr-12 flex items-center pointer-events-none">
                    <span className="text-gray-500 text-sm">/hour</span>
                  </div>
                </div>
                <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3">
                  <p className="text-sm text-blue-800 dark:text-blue-200">
                    <strong>Tip:</strong> Include salary, benefits, overhead, and infrastructure costs for accurate calculations.
                  </p>
                </div>
              </div>

              {/* Hours Multiplier */}
              <div className="space-y-4">
                <div className="flex items-center space-x-3">
                  <div className="p-2 bg-green-100 dark:bg-green-900/30 rounded-lg">
                    <Clock className="h-5 w-5 text-green-600 dark:text-green-400" />
                  </div>
                  <div>
                    <label className="block text-lg font-medium text-gray-900 dark:text-white">
                      Hours Multiplier
                    </label>
                    <p className="text-sm text-gray-600 dark:text-gray-400">
                      Adjustment factor for AI-estimated time savings
                    </p>
                  </div>
                </div>
                <div className="relative">
                  <input
                    type="number"
                    step="0.1"
                    min="0.1"
                    max="5.0"
                    value={editableConfig.hours_multiplier}
                    onChange={(e) => setEditableConfig(prev => ({
                      ...prev,
                      hours_multiplier: parseFloat(e.target.value) || 0
                    }))}
                    className="w-full px-4 py-3 text-lg border-2 border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-green-500 focus:border-green-500 transition-colors"
                    placeholder="1.0"
                  />
                  <div className="absolute inset-y-0 right-0 pr-12 flex items-center pointer-events-none">
                    <span className="text-gray-500 text-sm">×</span>
                  </div>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between text-sm">
                    <span className="text-gray-600 dark:text-gray-400">Conservative (0.5×)</span>
                    <span className="text-gray-600 dark:text-gray-400">Optimistic (2.0×)</span>
                  </div>
                  <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
                    <div 
                      className="bg-gradient-to-r from-green-400 to-green-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${Math.min(100, (editableConfig.hours_multiplier / 2.0) * 100)}%` }}
                    ></div>
                  </div>
                </div>
                <div className="bg-green-50 dark:bg-green-900/20 rounded-lg p-3">
                  <p className="text-sm text-green-800 dark:text-green-200">
                    <strong>Current:</strong> AI estimates × {editableConfig.hours_multiplier} = Actual time saved
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Simple Model Costs */}
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
          <div className="bg-gradient-to-r from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 px-6 py-4 border-b border-gray-200 dark:border-gray-600">
            <h3 className="text-xl font-semibold text-gray-900 dark:text-white flex items-center">
              <Calculator className="h-6 w-6 mr-3 text-blue-600 dark:text-blue-400" />
              Model Pricing Configuration
            </h3>
            <p className="text-sm text-gray-600 dark:text-gray-400 mt-1">
              Set per-1K token costs for accurate usage calculations • Costs in USD
            </p>
          </div>

          {/* Model Category Tabs */}
          <div className="flex border-b border-gray-200 dark:border-gray-600 bg-gray-50 dark:bg-gray-900">
            {availableCategories.map(([key, category]) => {
              const Icon = category.icon;
              return (
                <button
                  key={key}
                  onClick={() => setActiveModelTab(key)}
                  className={`flex items-center px-6 py-3 text-sm font-medium transition-colors border-b-2 ${
                    activeModelTab === key
                      ? 'text-blue-600 dark:text-blue-400 border-blue-600 dark:border-blue-400 bg-white dark:bg-gray-800'
                      : 'text-gray-600 dark:text-gray-400 border-transparent hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700'
                  }`}
                >
                  <Icon className="h-4 w-4 mr-2" />
                  {category.name}
                  <span className="ml-2 px-2 py-0.5 bg-gray-200 dark:bg-gray-600 rounded-full text-xs">
                    {category.models.length}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Model Category Content */}
          <div className="p-6">
            {availableCategories.map(([key, category]) => {
              if (activeModelTab !== key) return null;
              
              return (
                <div key={key} className="space-y-4">
                  {category.models.map((model) => {
                    const costs = editableConfig.model_costs[model] || { input: 0, output: 0 };
                    const modelData = metricsData?.model_breakdown?.[model];
                    
                    return (
                      <div key={model} className="bg-gray-50 dark:bg-gray-900 rounded-lg border border-gray-200 dark:border-gray-700 p-4">
                        <div className="grid grid-cols-1 lg:grid-cols-4 gap-6 items-center">
                          {/* Model Info */}
                          <div className="lg:col-span-1">
                            <div className="flex items-center space-x-2 mb-2">
                              <Zap className="h-4 w-4 text-blue-500" />
                              <span className="font-semibold text-gray-900 dark:text-white">
                                {model.replace('anthropic/', '').replace('openai/', '')}
                              </span>
                            </div>
                            {modelData && (
                              <div className="text-sm text-gray-600 dark:text-gray-400 space-y-1">
                                <div>{formatNumber(modelData.operations_count)} operations</div>
                                <div>{formatCurrency(modelData.total_cost)} spent</div>
                              </div>
                            )}
                          </div>

                          {/* Input Cost */}
                          <div className="space-y-2">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                              Input Cost (per 1K tokens)
                            </label>
                            <div className="relative">
                              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <span className="text-gray-500 text-sm">$</span>
                              </div>
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
                                className="w-full pl-6 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                placeholder="0.0000"
                              />
                            </div>
                          </div>

                          {/* Output Cost */}
                          <div className="space-y-2">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                              Output Cost (per 1K tokens)
                            </label>
                            <div className="relative">
                              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                                <span className="text-gray-500 text-sm">$</span>
                              </div>
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
                                className="w-full pl-6 pr-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                                placeholder="0.0000"
                              />
                            </div>
                          </div>

                          {/* Cost Summary */}
                          <div className="space-y-2">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                              Summary
                            </label>
                            <div className="bg-white dark:bg-gray-700 rounded-lg p-3 border border-gray-200 dark:border-gray-600">
                              <div className="text-sm font-medium text-gray-900 dark:text-white mb-1">
                                Avg: {formatCurrency((costs.input + costs.output) / 2)}
                              </div>
                              <div className="text-xs text-gray-500 dark:text-gray-400">
                                per 1K tokens
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
          
          {/* Enhanced Save Section */}
          <div className="bg-gray-50 dark:bg-gray-900 px-6 py-4 border-t border-gray-200 dark:border-gray-600">
            <div className="flex items-center justify-between">
              <div className="text-sm text-gray-600 dark:text-gray-400">
                Changes will recalculate all cost metrics and savings estimates
              </div>
              <button
                onClick={handleSaveConfig}
                disabled={saving}
                className="bg-gradient-to-r from-blue-600 to-indigo-600 hover:from-blue-700 hover:to-indigo-700 disabled:opacity-50 text-white px-8 py-3 rounded-lg flex items-center font-semibold shadow-lg hover:shadow-xl transition-all duration-200 transform hover:-translate-y-0.5"
              >
                {saving ? (
                  <RefreshCw className="h-5 w-5 mr-2 animate-spin" />
                ) : (
                  <Save className="h-5 w-5 mr-2" />
                )}
                Save Configuration
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (loading && !hasData) {
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

  if (error && !hasData) {
    return (
      <div className="space-y-6">
        <ViewHeader 
          title="AI/LLM Metrics"
          subtitle="Track AI model usage, costs, and developer productivity savings"
          icon={TrendingUp}
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