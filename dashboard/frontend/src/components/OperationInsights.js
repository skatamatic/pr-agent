import React, { useState, useEffect } from 'react';
import { X, Clock, Target, CheckCircle, AlertCircle, TrendingUp, BarChart3, FileText, Code, Activity, Key, ChevronLeft, ChevronRight } from 'lucide-react';
import { formatInsightsTime } from '../utils/timeUtils';
import apiService from '../services/api';

const OperationInsights = ({ operationId, onClose }) => {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [activeTab, setActiveTab] = useState('dev_time_analysis');
  const [hoveredPieSlice, setHoveredPieSlice] = useState(null);
  const [selectedImportanceCategory, setSelectedImportanceCategory] = useState(0);
  const [currentSuggestionIndex, setCurrentSuggestionIndex] = useState(0);

  useEffect(() => {
    fetchInsights();
  }, [operationId]);

  const fetchInsights = async () => {
    try {
      setLoading(true);
      const response = await apiService.getOperation(operationId);
      
      const data = response.data;
      setInsights(data.data.insights);
      
      // Set default tab based on available insights
      if (data.data.insights) {
        if (data.data.insights.dev_time_analysis) {
          setActiveTab('dev_time_analysis');
        } else if (data.data.insights.self_reflection) {
          setActiveTab('self_reflection');
        }
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const renderDescriptionDevTimeInsights = (descTimeData) => {
    if (!descTimeData) return null;
    
    const { change_complexity_assessment, description_quality_assessment, workflow_impact_analysis, final_assessment } = descTimeData;
    
    return (
      <div className="space-y-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border border-green-200 dark:border-green-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-2xl font-bold text-green-800 dark:text-green-400">
                  {formatInsightsTime(final_assessment?.total_developer_hours_saved)}
                </div>
                <div className="text-sm text-green-600 dark:text-green-500">Time Saved</div>

              </div>
              <Clock className="h-8 w-8 text-green-500 dark:text-green-400" />
            </div>
          </div>

          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-200 dark:border-blue-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-2xl font-bold text-blue-800 dark:text-blue-400 capitalize">
                  {change_complexity_assessment?.change_complexity_level}
                </div>
                <div className="text-sm text-blue-600 dark:text-blue-500">Complexity</div>

              </div>
              <TrendingUp className="h-8 w-8 text-blue-500 dark:text-blue-400" />
            </div>
          </div>

          <div className="bg-gradient-to-br from-purple-50 to-violet-50 dark:from-purple-900/20 dark:to-violet-900/20 border border-purple-200 dark:border-purple-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <div className="text-2xl font-bold text-purple-800 dark:text-purple-400 capitalize">
                  {final_assessment?.confidence_level}
                </div>
                <div className="text-sm text-purple-600 dark:text-purple-500">Confidence</div>

              </div>
              <div className="ml-2">
                <span className={`px-2 py-1 text-xs rounded-full font-medium ${
                  final_assessment?.confidence_level === 'high' 
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' 
                    : final_assessment?.confidence_level === 'medium' 
                    ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' 
                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                }`}>
                  {final_assessment?.confidence_level}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Key Factors */}
        {final_assessment?.key_factors && (
          <div className="bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 border border-amber-200 dark:border-amber-700 rounded-xl p-4">
            <div className="flex items-center mb-3">
              <Key className="h-5 w-5 text-amber-600 dark:text-amber-400 mr-2" />
              <h4 className="font-semibold text-amber-800 dark:text-amber-400">Key Factors</h4>
              <div className="text-xs text-amber-600 dark:text-amber-500 ml-2">
                Main considerations in time estimation
              </div>
            </div>
            <div className="space-y-2">
              {final_assessment.key_factors.map((factor, index) => (
                <div key={index} className="flex items-start">
                  <div className="w-2 h-2 bg-amber-400 dark:bg-amber-500 rounded-full mt-2 mr-3 flex-shrink-0"></div>
                  <span className="text-sm text-amber-700 dark:text-amber-300">{factor}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Change Complexity Assessment */}
        {change_complexity_assessment && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <BarChart3 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">Change Complexity Analysis</h4>
              <div className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                How difficult these changes would be to describe manually
              </div>
            </div>
            
            <div className="grid md:grid-cols-2 gap-6 mb-6">
              <div className="space-y-2">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Change Complexity Level</div>
                <div className={`inline-flex px-4 py-2 rounded-lg text-sm font-semibold ${
                  change_complexity_assessment.change_complexity_level === 'simple' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' :
                  change_complexity_assessment.change_complexity_level === 'moderate' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400' :
                  change_complexity_assessment.change_complexity_level === 'complex' ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400' :
                  'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                }`}>
                  {change_complexity_assessment.change_complexity_level}
                </div>
              </div>
              
              <div className="space-y-2">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Manual Description Time</div>
                <div className="text-xl font-bold text-gray-900 dark:text-white">
                  {formatInsightsTime(change_complexity_assessment.estimated_manual_description_time_hours)}
                </div>
              </div>
            </div>
            
            <div className="space-y-3">
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Complexity Reasoning</div>
              <div className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 leading-relaxed">
                {change_complexity_assessment.complexity_reasoning}
              </div>
            </div>
          </div>
        )}

        {/* Description Quality Assessment */}
        {description_quality_assessment && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <Target className="w-5 h-5 text-purple-600 dark:text-purple-400" />
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">Description Quality Assessment</h4>
              <div className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                How well the AI description communicates the changes
              </div>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 mb-6">
              <div className="text-center p-5 bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-900/30 rounded-xl border border-blue-200 dark:border-blue-800">
                <div className="text-3xl font-bold text-blue-600 dark:text-blue-400 mb-1">
                  {description_quality_assessment.description_quality_score || 0}/10
                </div>
                <div className="text-sm font-medium text-blue-700 dark:text-blue-300">Overall Quality</div>
              </div>
              
              <div className="text-center p-5 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-900/30 rounded-xl border border-green-200 dark:border-green-800">
                <div className="text-3xl font-bold text-green-600 dark:text-green-400 mb-1">
                  {description_quality_assessment.completeness_score || 0}/10
                </div>
                <div className="text-sm font-medium text-green-700 dark:text-green-300">Completeness</div>
              </div>
              
              <div className="text-center p-5 bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-900/30 rounded-xl border border-purple-200 dark:border-purple-800">
                <div className="text-3xl font-bold text-purple-600 dark:text-purple-400 mb-1">
                  {description_quality_assessment.clarity_score || 0}/10
                </div>
                <div className="text-sm font-medium text-purple-700 dark:text-purple-300">Clarity</div>
              </div>

              <div className="text-center p-5 bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-900/30 rounded-xl border border-orange-200 dark:border-orange-800">
                <div className="text-3xl font-bold text-orange-600 dark:text-orange-400 mb-1">
                  {description_quality_assessment.organization_score || 0}/10
                </div>
                <div className="text-sm font-medium text-orange-700 dark:text-orange-300">Organization</div>
              </div>
            </div>
            
            <div className="space-y-3">
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Quality Assessment</div>
              <div className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 leading-relaxed">
                {description_quality_assessment.quality_reasoning}
              </div>
            </div>
          </div>
        )}

        {/* Workflow Impact Analysis */}
        {workflow_impact_analysis && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <TrendingUp className="w-5 h-5 text-orange-600 dark:text-orange-400" />
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">Workflow Impact Analysis</h4>
              <div className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                How the description affects team review process
              </div>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              <div className="text-center p-4 bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-900/30 rounded-xl border border-blue-200 dark:border-blue-800">
                <div className="text-lg font-bold text-blue-600 dark:text-blue-400 mb-1">
                  {formatInsightsTime(workflow_impact_analysis.reviewer_time_reduction_hours)}
                </div>
                <div className="text-xs font-medium text-blue-700 dark:text-blue-300">Reviewer Time Saved</div>
              </div>
              
              <div className="text-center p-4 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-900/30 rounded-xl border border-green-200 dark:border-green-800">
                <div className="text-lg font-bold text-green-600 dark:text-green-400 mb-1">
                  {formatInsightsTime(workflow_impact_analysis.communication_overhead_reduction_hours)}
                </div>
                <div className="text-xs font-medium text-green-700 dark:text-green-300">Communication Overhead Saved</div>
              </div>
              
              <div className="text-center p-4 bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-900/30 rounded-xl border border-orange-200 dark:border-orange-800">
                <div className="text-lg font-bold text-orange-600 dark:text-orange-400 mb-1">
                  {formatInsightsTime(workflow_impact_analysis.context_switching_time_saved_hours)}
                </div>
                <div className="text-xs font-medium text-orange-700 dark:text-orange-300">Context Switch Time Saved</div>
              </div>
              
              <div className="text-center p-4 bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-900/30 rounded-xl border border-purple-200 dark:border-purple-800">
                <div className="text-lg font-bold text-purple-600 dark:text-purple-400 mb-1">
                  {workflow_impact_analysis.revision_cycles_avoided || 0}
                </div>
                <div className="text-xs font-medium text-purple-700 dark:text-purple-300">Revision Cycles Avoided</div>
              </div>
            </div>
            
            {workflow_impact_analysis.workflow_impact_reasoning && (
              <div className="space-y-3">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Workflow Impact Analysis</div>
                <div className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 leading-relaxed">
                  {workflow_impact_analysis.workflow_impact_reasoning}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Assumptions */}
        {final_assessment?.assumptions_made && (
          <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
            <div className="flex items-center mb-3">
              <AlertCircle className="h-4 w-4 text-gray-500 dark:text-gray-400 mr-2" />
              <h4 className="font-medium text-gray-700 dark:text-gray-300">Assumptions Made</h4>
              <div className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                Key assumptions in this time estimation
              </div>
            </div>
            <div className="space-y-2">
              {final_assessment.assumptions_made.map((assumption, index) => (
                <div key={index} className="flex items-start">
                  <div className="w-1 h-1 bg-gray-400 dark:bg-gray-500 rounded-full mt-2.5 mr-3 flex-shrink-0"></div>
                  <span className="text-sm text-gray-600 dark:text-gray-400 italic">{assumption}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderDevTimeInsights = (devTimeData) => {
    if (!devTimeData) return null;

    // Check if this is description-specific insights
    if (devTimeData.change_complexity_assessment || devTimeData.description_quality_assessment) {
      return renderDescriptionDevTimeInsights(devTimeData);
    }

    // Check if this is review guide-specific insights
    if (devTimeData.guide_quality_assessment || devTimeData.estimated_manual_scan_time_hours) {
      return renderReviewGuideDevTimeInsights(devTimeData);
    }

    const { complexity_assessment, review_quality_assessment, time_impact_analysis, final_assessment, processing_summary, individual_suggestions } = devTimeData;
    
    return (
      <div className="space-y-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-200 dark:border-blue-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-2xl font-bold text-blue-800 dark:text-blue-400">
                  {formatInsightsTime(final_assessment?.total_developer_hours_saved)}
                </div>
                <div className="text-sm text-blue-600 dark:text-blue-500">Time Saved</div>
              </div>
              <Clock className="h-8 w-8 text-blue-500 dark:text-blue-400" />
            </div>
          </div>

          <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border border-green-200 dark:border-green-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-2xl font-bold text-green-800 dark:text-green-400 capitalize">
                  {complexity_assessment?.code_complexity_level}
                </div>
                <div className="text-sm text-green-600 dark:text-green-500">Complexity</div>
              </div>
              <TrendingUp className="h-8 w-8 text-green-500 dark:text-green-400" />
            </div>
          </div>

          <div className="bg-gradient-to-br from-purple-50 to-violet-50 dark:from-purple-900/20 dark:to-violet-900/20 border border-purple-200 dark:border-purple-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <div className="text-2xl font-bold text-purple-800 dark:text-purple-400 capitalize">
                  {final_assessment?.confidence_level}
                </div>
                <div className="text-sm text-purple-600 dark:text-purple-500">Confidence</div>
              </div>
              <div className="ml-2">
                <span className={`px-2 py-1 text-xs rounded-full font-medium ${
                  final_assessment?.confidence_level === 'high' 
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' 
                    : final_assessment?.confidence_level === 'medium' 
                    ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' 
                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                }`}>
                  {final_assessment?.confidence_level}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Key Factors */}
        {final_assessment?.key_factors && (
          <div className="bg-gradient-to-br from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 border border-amber-200 dark:border-amber-700 rounded-xl p-4">
            <div className="flex items-center mb-3">
              <Key className="h-5 w-5 text-amber-600 dark:text-amber-400 mr-2" />
              <h4 className="font-semibold text-amber-800 dark:text-amber-400">Key Factors</h4>
            </div>
            <div className="space-y-2">
              {final_assessment.key_factors.map((factor, index) => (
                <div key={index} className="flex items-start">
                  <div className="w-2 h-2 bg-amber-400 dark:bg-amber-500 rounded-full mt-2 mr-3 flex-shrink-0"></div>
                  <span className="text-sm text-amber-700 dark:text-amber-300">{factor}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Code Complexity Assessment */}
        {complexity_assessment && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <BarChart3 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">Code Complexity Assessment</h4>
            </div>
            
            <div className="grid md:grid-cols-2 gap-6 mb-6">
              <div className="space-y-2">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Complexity Level</div>
                <div className={`inline-flex px-4 py-2 rounded-lg text-sm font-semibold ${
                  complexity_assessment.code_complexity_level === 'simple' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' :
                  complexity_assessment.code_complexity_level === 'moderate' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400' :
                  complexity_assessment.code_complexity_level === 'complex' ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400' :
                  'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                }`}>
                  {complexity_assessment.code_complexity_level}
                </div>
              </div>
              
              <div className="space-y-2">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Manual Review Time</div>
                <div className="text-xl font-bold text-gray-900 dark:text-white">
                  {formatInsightsTime(complexity_assessment.estimated_manual_review_time_hours)}
                </div>
              </div>
            </div>
            
            <div className="space-y-3">
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Complexity Reasoning</div>
              <div className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 leading-relaxed">
                {complexity_assessment.complexity_reasoning}
              </div>
            </div>
          </div>
        )}

        {/* Review Guide Quality Assessment - supports both guide_quality_assessment and review_quality_assessment */}
        {(devTimeData.guide_quality_assessment || review_quality_assessment) && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <Target className="w-5 h-5 text-purple-600 dark:text-purple-400" />
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">Review Guide Quality Assessment</h4>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
              <div className="text-center p-5 bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-900/30 rounded-xl border border-blue-200 dark:border-blue-800">
                <div className="text-3xl font-bold text-blue-600 dark:text-blue-400 mb-1">
                  {devTimeData.guide_quality_assessment?.review_guide_score || 
                   devTimeData.guide_quality_assessment?.quality_score ||
                   review_quality_assessment?.review_quality_score || 
                   review_quality_assessment?.quality_score || 0}/10
                </div>
                <div className="text-sm font-medium text-blue-700 dark:text-blue-300">Guide Quality Score</div>
              </div>
              
              <div className="text-center p-5 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-900/30 rounded-xl border border-green-200 dark:border-green-800">
                <div className="text-3xl font-bold text-green-600 dark:text-green-400 mb-1">
                  {devTimeData.guide_quality_assessment?.actionability_score ||
                   devTimeData.guide_quality_assessment?.actionable_feedback_count || 
                   review_quality_assessment?.actionable_feedback_count || 0}
                </div>
                <div className="text-sm font-medium text-green-700 dark:text-green-300">Actionable Items</div>
              </div>

              <div className="text-center p-5 bg-gradient-to-br from-amber-50 to-amber-100 dark:from-amber-900/20 dark:to-amber-900/30 rounded-xl border border-amber-200 dark:border-amber-800">
                <div className="text-3xl font-bold text-amber-600 dark:text-amber-400 mb-1">
                  {devTimeData.guide_quality_assessment?.false_positive_count ||
                   review_quality_assessment?.invalid_feedback_count || 0}
                </div>
                <div className="text-sm font-medium text-amber-700 dark:text-amber-300">False Positives</div>
              </div>
            </div>
            
            <div className="space-y-3">
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Quality Assessment</div>
              <div className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 leading-relaxed">
                {devTimeData.guide_quality_assessment?.guide_quality_reasoning ||
                 devTimeData.guide_quality_assessment?.quality_reasoning ||
                 review_quality_assessment?.quality_reasoning ||
                 'Quality assessment details not available'}
              </div>
            </div>
          </div>
        )}

        {/* Time Impact Analysis */}
        {time_impact_analysis && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <TrendingUp className="w-5 h-5 text-orange-600 dark:text-orange-400" />
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">Time Impact Analysis</h4>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
              <div className="text-center p-4 bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-900/30 rounded-xl border border-blue-200 dark:border-blue-800">
                <div className="text-lg font-bold text-blue-600 dark:text-blue-400 mb-1">
                  {formatInsightsTime(
                    time_impact_analysis.estimated_manual_scan_time_hours ||
                    time_impact_analysis.manual_scan_time_hours ||
                    time_impact_analysis.author_time_to_process_feedback_hours ||
                    0
                  )}
                </div>
                <div className="text-xs font-medium text-blue-700 dark:text-blue-300">Manual Scan Time</div>
              </div>
              
              <div className="text-center p-4 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-900/30 rounded-xl border border-green-200 dark:border-green-800">
                <div className="text-lg font-bold text-green-600 dark:text-green-400 mb-1">
                  {formatInsightsTime(
                    time_impact_analysis.reviewer_time_saved_hours ||
                    time_impact_analysis.human_reviewer_time_reduction_hours ||
                    0
                  )}
                </div>
                <div className="text-xs font-medium text-green-700 dark:text-green-300">Reviewer Time Saved</div>
              </div>
              
              <div className="text-center p-4 bg-gradient-to-br from-orange-50 to-orange-100 dark:from-orange-900/20 dark:to-orange-900/30 rounded-xl border border-orange-200 dark:border-orange-800">
                <div className="text-lg font-bold text-orange-600 dark:text-orange-400 mb-1">
                  {formatInsightsTime(
                    time_impact_analysis.author_processing_time_hours ||
                    time_impact_analysis.context_switching_overhead_hours ||
                    0
                  )}
                </div>
                <div className="text-xs font-medium text-orange-700 dark:text-orange-300">Author Processing</div>
              </div>
            </div>
            
            {time_impact_analysis.net_time_savings_reasoning && (
              <div className="space-y-3">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Impact Analysis</div>
                <div className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 leading-relaxed">
                  {time_impact_analysis.net_time_savings_reasoning}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Assumptions */}
        {(final_assessment?.assumptions_made || final_assessment?.assumptions) && (
          <div className="bg-gray-50 dark:bg-gray-800/50 border border-gray-200 dark:border-gray-700 rounded-xl p-4">
            <div className="flex items-center mb-3">
              <AlertCircle className="h-4 w-4 text-gray-500 dark:text-gray-400 mr-2" />
              <h4 className="font-medium text-gray-700 dark:text-gray-300">Assumptions Made</h4>
              <div className="text-xs text-gray-500 dark:text-gray-400 ml-2">
                Key assumptions in this time estimation
              </div>
            </div>
            <div className="space-y-2">
              {(final_assessment?.assumptions_made || final_assessment?.assumptions || []).map((assumption, index) => (
                <div key={index} className="flex items-start">
                  <div className="w-1 h-1 bg-gray-400 dark:bg-gray-500 rounded-full mt-2.5 mr-3 flex-shrink-0"></div>
                  <span className="text-sm text-gray-600 dark:text-gray-400 italic">{assumption}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderReviewGuideDevTimeInsights = (reviewGuideData) => {
    if (!reviewGuideData) return null;

    const { 
      complexity_assessment = {}, 
      guide_quality_assessment = {}, 
      time_impact_analysis = {}, 
      final_assessment = {},
      review_metrics = {}
    } = reviewGuideData;
    
    return (
      <div className="space-y-6">
        {/* Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-200 dark:border-blue-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-2xl font-bold text-blue-800 dark:text-blue-400">
                  {formatInsightsTime(final_assessment?.total_developer_hours_saved || review_metrics?.estimated_hours)}
                </div>
                <div className="text-sm text-blue-600 dark:text-blue-500">Time Saved</div>
                <div className="text-xs text-blue-500 dark:text-blue-400 mt-1">
                  Review Guide
                </div>
              </div>
              <Clock className="h-8 w-8 text-blue-500 dark:text-blue-400" />
            </div>
          </div>

          <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border border-green-200 dark:border-green-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-2xl font-bold text-green-800 dark:text-green-400 capitalize">
                  {complexity_assessment?.code_complexity_level}
                </div>
                <div className="text-sm text-green-600 dark:text-green-500">Complexity</div>
              </div>
              <TrendingUp className="h-8 w-8 text-green-500 dark:text-green-400" />
            </div>
          </div>

          <div className="bg-gradient-to-br from-purple-50 to-violet-50 dark:from-purple-900/20 dark:to-violet-900/20 border border-purple-200 dark:border-purple-700 rounded-xl p-4">
            <div className="flex items-center justify-between">
              <div className="flex-1">
                <div className="text-2xl font-bold text-purple-800 dark:text-purple-400 capitalize">
                  {final_assessment?.confidence_level}
                </div>
                <div className="text-sm text-purple-600 dark:text-purple-500">Confidence</div>
              </div>
              <div className="ml-2">
                <span className={`px-2 py-1 text-xs rounded-full font-medium ${
                  final_assessment?.confidence_level === 'high' 
                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' 
                    : final_assessment?.confidence_level === 'medium' 
                    ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' 
                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                }`}>
                  {final_assessment?.confidence_level}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Supplementary Tool Notice */}
        <div className="bg-gradient-to-br from-amber-50 to-yellow-50 dark:from-amber-900/20 dark:to-yellow-900/20 border border-amber-200 dark:border-amber-700 rounded-xl p-4">
          <div className="flex items-center mb-3">
            <AlertCircle className="h-5 w-5 text-amber-600 dark:text-amber-400 mr-2" />
            <h4 className="font-semibold text-amber-800 dark:text-amber-400">Review Guide Tool</h4>
          </div>
          <div className="text-sm text-amber-700 dark:text-amber-300">
            {final_assessment?.supplementary_tool_note || 
             "This tool provides high-level guidance to supplement detailed code review tools. It identifies focus areas and potential issues but doesn't provide specific fixes."}
          </div>
        </div>

        {/* Key Factors */}
        {final_assessment?.key_factors && (
          <div className="bg-gradient-to-br from-indigo-50 to-blue-50 dark:from-indigo-900/20 dark:to-blue-900/20 border border-indigo-200 dark:border-indigo-700 rounded-xl p-4">
            <div className="flex items-center mb-3">
              <Key className="h-5 w-5 text-indigo-600 dark:text-indigo-400 mr-2" />
              <h4 className="font-semibold text-indigo-800 dark:text-indigo-400">Key Assessment Factors</h4>
            </div>
            <div className="space-y-2">
              {final_assessment.key_factors.map((factor, index) => (
                <div key={index} className="flex items-start">
                  <div className="w-2 h-2 bg-indigo-400 dark:bg-indigo-500 rounded-full mt-2 mr-3 flex-shrink-0"></div>
                  <span className="text-sm text-indigo-700 dark:text-indigo-300">{factor}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Code Complexity Assessment */}
        {complexity_assessment && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <BarChart3 className="w-5 h-5 text-blue-600 dark:text-blue-400" />
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">Code Complexity Assessment</h4>
            </div>
            
            <div className="grid md:grid-cols-2 gap-6 mb-6">
              <div className="space-y-2">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Complexity Level</div>
                <div className={`inline-flex px-4 py-2 rounded-lg text-sm font-semibold ${
                  complexity_assessment.code_complexity_level === 'simple' ? 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400' :
                  complexity_assessment.code_complexity_level === 'moderate' ? 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400' :
                  complexity_assessment.code_complexity_level === 'complex' ? 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400' :
                  'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400'
                }`}>
                  {complexity_assessment.code_complexity_level}
                </div>
              </div>
              
              <div className="space-y-2">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Manual Scan Time</div>
                <div className="text-xl font-bold text-gray-900 dark:text-white">
                  {formatInsightsTime(complexity_assessment.estimated_manual_scan_time_hours)}
                </div>
              </div>
            </div>
            
            <div className="space-y-3">
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Complexity Reasoning</div>
              <div className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 leading-relaxed">
                {complexity_assessment.complexity_reasoning}
              </div>
            </div>
          </div>
        )}

        {/* Guide Quality Assessment */}
        {guide_quality_assessment && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <Target className="w-5 h-5 text-purple-600 dark:text-purple-400" />
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">Guide Quality Assessment</h4>
            </div>
            
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
              <div className="text-center p-4 bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-900/30 rounded-xl border border-blue-200 dark:border-blue-800">
                <div className="text-2xl font-bold text-blue-600 dark:text-blue-400 mb-1">
                  {guide_quality_assessment.guide_quality_score || 0}/10
                </div>
                <div className="text-xs font-medium text-blue-700 dark:text-blue-300">Guide Quality</div>
              </div>
              
              <div className="text-center p-4 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-900/30 rounded-xl border border-green-200 dark:border-green-800">
                <div className="text-2xl font-bold text-green-600 dark:text-green-400 mb-1">
                  {guide_quality_assessment.valid_issues_identified || 0}
                </div>
                <div className="text-xs font-medium text-green-700 dark:text-green-300">Valid Issues</div>
              </div>

              <div className="text-center p-4 bg-gradient-to-br from-yellow-50 to-yellow-100 dark:from-yellow-900/20 dark:to-yellow-900/30 rounded-xl border border-yellow-200 dark:border-yellow-800">
                <div className="text-2xl font-bold text-yellow-600 dark:text-yellow-400 mb-1">
                  {guide_quality_assessment.subtle_issues_count || 0}
                </div>
                <div className="text-xs font-medium text-yellow-700 dark:text-yellow-300">Subtle Issues</div>
              </div>

              <div className="text-center p-4 bg-gradient-to-br from-purple-50 to-purple-100 dark:from-purple-900/20 dark:to-purple-900/30 rounded-xl border border-purple-200 dark:border-purple-800">
                <div className="text-2xl font-bold text-purple-600 dark:text-purple-400 mb-1">
                  {guide_quality_assessment.focus_areas_provided || 0}
                </div>
                <div className="text-xs font-medium text-purple-700 dark:text-purple-300">Focus Areas</div>
              </div>
            </div>
            
            <div className="space-y-3">
              <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Quality Reasoning</div>
              <div className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 leading-relaxed">
                {guide_quality_assessment.quality_reasoning}
              </div>
            </div>
          </div>
        )}

        {/* Time Impact Analysis */}
        {time_impact_analysis && (
          <div className="bg-white dark:bg-gray-800 rounded-xl border border-gray-200 dark:border-gray-700 p-6 shadow-sm">
            <div className="flex items-center gap-3 mb-6">
              <TrendingUp className="w-5 h-5 text-orange-600 dark:text-orange-400" />
              <h4 className="text-lg font-semibold text-gray-900 dark:text-white">Time Impact Analysis</h4>
            </div>
            
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-6">
              <div className="text-center p-4 bg-gradient-to-br from-green-50 to-green-100 dark:from-green-900/20 dark:to-green-900/30 rounded-xl border border-green-200 dark:border-green-800">
                <div className="text-lg font-bold text-green-600 dark:text-green-400 mb-1">
                  {formatInsightsTime(time_impact_analysis.initial_scan_time_saved_hours)}
                </div>
                <div className="text-xs font-medium text-green-700 dark:text-green-300">Initial Scan Time Saved</div>
              </div>
              
              <div className="text-center p-4 bg-gradient-to-br from-blue-50 to-blue-100 dark:from-blue-900/20 dark:to-blue-900/30 rounded-xl border border-blue-200 dark:border-blue-800">
                <div className="text-lg font-bold text-blue-600 dark:text-blue-400 mb-1">
                  {formatInsightsTime(time_impact_analysis.issue_categorization_time_saved_hours)}
                </div>
                <div className="text-xs font-medium text-blue-700 dark:text-blue-300">Categorization Time Saved</div>
              </div>
              
              <div className="text-center p-4 bg-gradient-to-br from-amber-50 to-amber-100 dark:from-amber-900/20 dark:to-amber-900/30 rounded-xl border border-amber-200 dark:border-amber-800">
                <div className="text-lg font-bold text-amber-600 dark:text-amber-400 mb-1">
                  {formatInsightsTime(time_impact_analysis.human_investigation_still_required_hours)}
                </div>
                <div className="text-xs font-medium text-amber-700 dark:text-amber-300">Still Requires Investigation</div>
              </div>
            </div>
            
            {time_impact_analysis.net_time_savings_reasoning && (
              <div className="space-y-3">
                <div className="text-sm font-medium text-gray-600 dark:text-gray-400">Impact Analysis</div>
                <div className="text-sm text-gray-700 dark:text-gray-300 bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4 leading-relaxed">
                  {time_impact_analysis.net_time_savings_reasoning}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const renderSelfReflectionInsights = (reflectionData) => {
    if (!reflectionData) {
      return null;
    }
    
    // Check for the expected structure from PR code suggestions tool
    const suggestions = reflectionData.individual_suggestions;
    const qualityBreakdown = reflectionData.quality_breakdown;
    const scoreDistribution = reflectionData.score_distribution;
    const processingSummary = reflectionData.processing_summary;
    
    if (!suggestions || !Array.isArray(suggestions) || suggestions.length === 0) {
      return (
        <div className="space-y-6">
          <div className="bg-gradient-to-br from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20 border border-purple-200 dark:border-purple-700 rounded-xl p-6">
            <div className="text-center">
              <Activity className="h-12 w-12 text-purple-400 mx-auto mb-4" />
              <h3 className="text-lg font-semibold text-purple-800 dark:text-purple-400 mb-2">
                No Self-Reflection Data Available
              </h3>
              <p className="text-purple-600 dark:text-purple-500">
                Self-reflection analysis not found or contains no suggestions.
              </p>
              <div className="mt-4 text-left bg-purple-50 dark:bg-purple-900/20 rounded-lg p-4">
                <div className="text-xs text-purple-700 dark:text-purple-400 font-mono">
                  Debug info: {JSON.stringify(Object.keys(reflectionData), null, 2)}
                </div>
              </div>
            </div>
          </div>
        </div>
      );
    }
    
    // Process quality breakdown data
    const totalSuggestions = qualityBreakdown?.total_suggestions || suggestions.length;
    const highQualityCount = qualityBreakdown?.high_quality_suggestions || 0;
    const mediumQualityCount = qualityBreakdown?.medium_quality_suggestions || 0;
    const lowQualityCount = qualityBreakdown?.low_quality_suggestions || 0;
    
    // Process commit eligibility breakdown data
    const commitEligibilityBreakdown = reflectionData.commit_eligibility_breakdown;
    const commitEligibleCount = commitEligibilityBreakdown?.commit_eligible_suggestions || 0;
    const commitIneligibleCount = commitEligibilityBreakdown?.commit_ineligible_suggestions || 0;
    const commitEligibilityTotal = commitEligibilityBreakdown?.total_suggestions || totalSuggestions;
    
    // Process processing summary
    const successfullyAnalyzed = processingSummary?.successfully_analyzed || 0;
    const processingErrors = processingSummary?.processing_errors || 0;
    const lineValidationFailures = processingSummary?.line_validation_failures || 0;
    const duplicateCodeIssues = processingSummary?.duplicate_code_issues || 0;
    
    // Calculate success rate
    const successRate = totalSuggestions > 0 ? Math.round((successfullyAnalyzed / totalSuggestions) * 100) : 0;
    
    // Process score distribution for histogram
    const scoreDistributionArray = Array(11).fill(0); // Scores 0-10
    if (scoreDistribution && typeof scoreDistribution === 'object') {
      Object.entries(scoreDistribution).forEach(([score, count]) => {
        const scoreNum = parseInt(score);
        if (scoreNum >= 0 && scoreNum <= 10) {
          scoreDistributionArray[scoreNum] = count;
        }
      });
    }
    
    // Calculate max count for histogram scaling
    const maxCount = Math.max(...scoreDistributionArray);
    
    // Calculate average score
    const validSuggestions = suggestions.filter((s) => s.score > 0);
    const scores = validSuggestions.map((s) => s.score);
    const averageScore = scores.length > 0 ? (scores.reduce((a, b) => a + b, 0) / scores.length).toFixed(1) : '0.0';
    
    return (
      <div className="space-y-6">
        {/* Header Card */}
        <div className="bg-gradient-to-br from-purple-50 to-indigo-50 dark:from-purple-900/20 dark:to-indigo-900/20 border border-purple-200 dark:border-purple-700 rounded-xl p-6">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xl font-bold text-purple-800 dark:text-purple-400">Self-Reflection Analysis</h3>
              <p className="text-purple-600 dark:text-purple-500 mt-1">
                AI quality assessment of generated code suggestions
              </p>
              <div className="text-xs text-purple-500 dark:text-purple-400 mt-2">
                Analyzes correctness, relevance, and impact of AI feedback
              </div>
            </div>
            <div className="text-right">
              <div className="text-3xl font-bold text-purple-800 dark:text-purple-400">
                {totalSuggestions}
              </div>
              <div className="text-sm text-purple-600 dark:text-purple-500">Items Analyzed</div>
              <div className="text-xs text-purple-500 dark:text-purple-400 mt-1">
                {successRate}% success rate
              </div>
            </div>
          </div>
        </div>

        {/* Processing Statistics */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border border-green-200 dark:border-green-700 rounded-xl p-4">
            <div className="text-2xl font-bold text-green-800 dark:text-green-400">{successfullyAnalyzed}</div>
            <div className="text-sm text-green-600 dark:text-green-500">Successfully Scored</div>
            <div className="text-xs text-green-500 dark:text-green-400 mt-1">
              Suggestions that received valid importance scores
            </div>
          </div>
          
          <div className="bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 border border-blue-200 dark:border-blue-700 rounded-xl p-4">
            <div className="text-2xl font-bold text-blue-800 dark:text-blue-400">{totalSuggestions}</div>
            <div className="text-sm text-blue-600 dark:text-blue-500">Total Processed</div>
            <div className="text-xs text-blue-500 dark:text-blue-400 mt-1">
              All suggestions submitted for analysis
            </div>
          </div>
          
          <div className="bg-gradient-to-br from-red-50 to-pink-50 dark:from-red-900/20 dark:to-pink-900/20 border border-red-200 dark:border-red-700 rounded-xl p-4">
            <div className="text-2xl font-bold text-red-800 dark:text-red-400">{processingErrors}</div>
            <div className="text-sm text-red-600 dark:text-red-500">Processing Errors</div>
            <div className="text-xs text-red-500 dark:text-red-400 mt-1">
              Suggestions that failed during analysis
            </div>
          </div>
          
          <div className="bg-gradient-to-br from-amber-50 to-yellow-50 dark:from-amber-900/20 dark:to-yellow-900/20 border border-amber-200 dark:border-amber-700 rounded-xl p-4">
            <div className="text-2xl font-bold text-amber-800 dark:text-amber-400">{lineValidationFailures}</div>
            <div className="text-sm text-amber-600 dark:text-amber-500">Validation Failures</div>
            <div className="text-xs text-amber-500 dark:text-amber-400 mt-1">
              Suggestions with invalid line references
            </div>
          </div>
        </div>

        {/* Commit Eligibility Statistics */}
        <div className="bg-gradient-to-br from-indigo-50 to-purple-50 dark:from-indigo-900/20 dark:to-purple-900/20 border border-indigo-200 dark:border-indigo-700 rounded-xl p-6">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h4 className="text-lg font-semibold text-indigo-800 dark:text-indigo-400">Commit Eligibility Assessment</h4>
              <p className="text-indigo-600 dark:text-indigo-500 text-sm mt-1">
                Analysis of suggestions that can be safely applied automatically
              </p>
            </div>
            <div className="text-right">
              <div className="text-2xl font-bold text-indigo-800 dark:text-indigo-400">
                {commitEligibilityTotal > 0 ? Math.round((commitEligibleCount / commitEligibilityTotal) * 100) : 0}%
              </div>
              <div className="text-sm text-indigo-600 dark:text-indigo-500">Directly Committable</div>
            </div>
          </div>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="bg-gradient-to-br from-green-50 to-emerald-50 dark:from-green-900/20 dark:to-emerald-900/20 border border-green-200 dark:border-green-700 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xl font-bold text-green-800 dark:text-green-400">{commitEligibleCount}</div>
                  <div className="text-sm text-green-600 dark:text-green-500">Commit Eligible</div>
                  <div className="text-xs text-green-500 dark:text-green-400 mt-1">
                    Simple, localized changes safe for automatic application
                  </div>
                </div>
                <div className="w-12 h-12 bg-green-100 dark:bg-green-900/30 rounded-full flex items-center justify-center">
                  <svg className="w-6 h-6 text-green-600 dark:text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                  </svg>
                </div>
              </div>
              <div className="mt-3 text-xs text-green-600 dark:text-green-400">
                <strong>Examples:</strong> Bug fixes, style improvements, simple refactoring
              </div>
            </div>
            
            <div className="bg-gradient-to-br from-amber-50 to-yellow-50 dark:from-amber-900/20 dark:to-yellow-900/20 border border-amber-200 dark:border-amber-700 rounded-lg p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xl font-bold text-amber-800 dark:text-amber-400">{commitIneligibleCount}</div>
                  <div className="text-sm text-amber-600 dark:text-amber-500">Manual Review Required</div>
                  <div className="text-xs text-amber-500 dark:text-amber-400 mt-1">
                    Complex changes requiring developer judgment
                  </div>
                </div>
                <div className="w-12 h-12 bg-amber-100 dark:bg-amber-900/30 rounded-full flex items-center justify-center">
                  <svg className="w-6 h-6 text-amber-600 dark:text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                </div>
              </div>
              <div className="mt-3 text-xs text-amber-600 dark:text-amber-400">
                <strong>Examples:</strong> Architectural changes, API modifications, documentation
              </div>
            </div>
          </div>
        </div>

        {/* Importance Level Distribution and Suggestions Carousel */}
        <div className="space-y-8">
          {/* Header */}
          <div className="text-center">
            <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-2">Suggestion Analysis</h3>
            <p className="text-gray-600 dark:text-gray-400">
              Click on a category to view suggestions
            </p>
          </div>

          {/* Pie Chart and Carousel Side by Side */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
            {/* Interactive Pie Chart */}
            <div className="flex flex-col items-center">
              <div className="text-center mb-6">
                <h4 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">Importance Distribution</h4>
                <div className="text-sm text-gray-600 dark:text-gray-400">
                  Average Level: <span className="text-xl font-bold text-gray-900 dark:text-white">{averageScore}</span>
                </div>
              </div>
              
              <div className="relative">
                {(() => {
                  // Group suggestions into 3 categories
                  const lowCount = scoreDistributionArray.slice(0, 5).reduce((sum, count) => sum + count, 0); // 0-4
                  const mediumCount = scoreDistributionArray.slice(5, 8).reduce((sum, count) => sum + count, 0); // 5-7
                  const highCount = scoreDistributionArray.slice(8, 11).reduce((sum, count) => sum + count, 0); // 8-10
                  
                  const categories = [
                    { name: 'Low Importance', range: '0-4', count: lowCount, color: '#EF4444' },
                    { name: 'Medium Importance', range: '5-7', count: mediumCount, color: '#F59E0B' },
                    { name: 'High Importance', range: '8-10', count: highCount, color: '#10B981' }
                  ];
                  
                  const totalSuggestions = categories.reduce((sum, cat) => sum + cat.count, 0);
                  
                  if (totalSuggestions === 0) {
                    return (
                      <div className="w-64 h-64 bg-gray-100 dark:bg-gray-700 rounded-full flex items-center justify-center">
                        <span className="text-gray-500 dark:text-gray-400 text-sm font-medium">No Data</span>
                      </div>
                    );
                  }

                  // Generate pie slices
                  let currentAngle = 0;
                  const pieSlices = categories.map((category, index) => {
                    const percentage = (category.count / totalSuggestions) * 100;
                    const angle = categories.length === 1 ? 360 : (percentage / 100) * 360;
                    
                    const slice = {
                      ...category,
                      percentage,
                      startAngle: currentAngle,
                      endAngle: currentAngle + angle,
                      index
                    };
                    
                    currentAngle += angle;
                    return slice;
                  }).filter(slice => slice.count > 0);

                  // Helper function to create pie slice path
                  const createPieSlicePath = (centerX, centerY, radius, startAngle, endAngle) => {
                    const sweepAngle = endAngle - startAngle;
                    
                    if (sweepAngle >= 359.9 || sweepAngle === 360) {
                      return `M ${centerX - radius} ${centerY} 
                              A ${radius} ${radius} 0 1 1 ${centerX + radius} ${centerY} 
                              A ${radius} ${radius} 0 1 1 ${centerX - radius} ${centerY} Z`;
                    }
                    
                    const start = {
                      x: centerX + radius * Math.cos((startAngle - 90) * Math.PI / 180),
                      y: centerY + radius * Math.sin((startAngle - 90) * Math.PI / 180)
                    };
                    const end = {
                      x: centerX + radius * Math.cos((endAngle - 90) * Math.PI / 180),
                      y: centerY + radius * Math.sin((endAngle - 90) * Math.PI / 180)
                    };
                    
                    const largeArcFlag = sweepAngle <= 180 ? "0" : "1";
                    
                    return [
                      "M", centerX, centerY,
                      "L", start.x, start.y,
                      "A", radius, radius, 0, largeArcFlag, 1, end.x, end.y,
                      "Z"
                    ].join(" ");
                  };

                  return (
                    <svg width="300" height="300" className="drop-shadow-lg">
                      {pieSlices.map((slice, index) => {
                        const isHovered = hoveredPieSlice === index;
                        const isSelected = selectedImportanceCategory === index;
                        const radius = isSelected ? 120 : isHovered ? 115 : 110;
                        
                        return (
                          <g key={index}>
                            <path
                              d={createPieSlicePath(150, 150, radius, slice.startAngle, slice.endAngle)}
                              fill={slice.color}
                              stroke="white"
                              strokeWidth="2"
                              className="cursor-pointer transition-all duration-300 hover:brightness-110"
                              style={{
                                filter: isSelected ? 'drop-shadow(0 4px 8px rgba(0,0,0,0.3)) drop-shadow(0 0 12px rgba(59, 130, 246, 0.5))' : 
                                        isHovered ? 'drop-shadow(0 2px 4px rgba(0,0,0,0.2))' : 'none',
                                opacity: isSelected ? 1 : isHovered ? 0.9 : 0.8
                              }}
                              onMouseEnter={() => setHoveredPieSlice(index)}
                              onMouseLeave={() => setHoveredPieSlice(null)}
                              onClick={() => {
                                setSelectedImportanceCategory(index);
                                setCurrentSuggestionIndex(0);
                              }}
                            />
                            {slice.percentage > 10 && (
                              <text
                                x={150 + (radius - 35) * Math.cos(((slice.startAngle + slice.endAngle) / 2 - 90) * Math.PI / 180)}
                                y={150 + (radius - 35) * Math.sin(((slice.startAngle + slice.endAngle) / 2 - 90) * Math.PI / 180)}
                                textAnchor="middle"
                                dominantBaseline="middle"
                                className="fill-white text-sm font-semibold pointer-events-none"
                                style={{ textShadow: '1px 1px 2px rgba(0,0,0,0.7)' }}
                              >
                                {slice.percentage.toFixed(0)}%
                              </text>
                            )}
                          </g>
                        );
                      })}
                    </svg>
                  );
                })()}

                {/* Tooltip */}
                {hoveredPieSlice !== null && (() => {
                  const lowCount = scoreDistributionArray.slice(0, 5).reduce((sum, count) => sum + count, 0);
                  const mediumCount = scoreDistributionArray.slice(5, 8).reduce((sum, count) => sum + count, 0);
                  const highCount = scoreDistributionArray.slice(8, 11).reduce((sum, count) => sum + count, 0);
                  
                  const categories = [
                    { name: 'Low Importance', range: '0-4', count: lowCount },
                    { name: 'Medium Importance', range: '5-7', count: mediumCount },
                    { name: 'High Importance', range: '8-10', count: highCount }
                  ].filter(cat => cat.count > 0);

                  const category = categories[hoveredPieSlice];
                  if (!category) return null;

                  const totalSuggestions = categories.reduce((sum, cat) => sum + cat.count, 0);
                  const percentage = (category.count / totalSuggestions) * 100;

                  return (
                    <div 
                      className="absolute bg-gray-900 dark:bg-gray-800 text-white px-3 py-2 rounded-lg text-sm font-medium pointer-events-none z-10 shadow-lg border border-gray-700"
                      style={{
                        left: '50%',
                        top: '10px',
                        transform: 'translateX(-50%)'
                      }}
                    >
                      <div className="text-center">
                        <div className="font-semibold">{category.name}</div>
                        <div className="text-xs text-gray-300">
                          {category.count} suggestion{category.count !== 1 ? 's' : ''} ({percentage.toFixed(1)}%)
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>

              {/* Navigation Controls Below Pie Chart */}
              {(() => {
                const lowCount = scoreDistributionArray.slice(0, 5).reduce((sum, count) => sum + count, 0);
                const mediumCount = scoreDistributionArray.slice(5, 8).reduce((sum, count) => sum + count, 0);
                const highCount = scoreDistributionArray.slice(8, 11).reduce((sum, count) => sum + count, 0);
                
                const categories = [
                  { name: 'Low Importance', range: '0-4', count: lowCount },
                  { name: 'Medium Importance', range: '5-7', count: mediumCount },
                  { name: 'High Importance', range: '8-10', count: highCount }
                ].filter(cat => cat.count > 0);

                if (categories.length === 0) return null;

                return (
                  <div className="flex items-center justify-center space-x-6 mt-6">
                    <button
                      onClick={() => {
                        const newIndex = selectedImportanceCategory > 0 ? selectedImportanceCategory - 1 : categories.length - 1;
                        setSelectedImportanceCategory(newIndex);
                        setCurrentSuggestionIndex(0);
                      }}
                      className="p-3 rounded-lg bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors shadow-sm"
                      title="Previous category"
                    >
                      <ChevronLeft className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                    </button>
                    <div className="flex items-center space-x-3 bg-gray-100 dark:bg-gray-700 rounded-lg px-4 py-2">
                      <span className="text-lg font-medium text-gray-900 dark:text-white">
                        {selectedImportanceCategory + 1}
                      </span>
                      <span className="text-gray-500 dark:text-gray-400">/</span>
                      <span className="text-lg font-medium text-gray-900 dark:text-white">
                        {categories.length}
                      </span>
                    </div>
                    <button
                      onClick={() => {
                        const newIndex = selectedImportanceCategory < categories.length - 1 ? selectedImportanceCategory + 1 : 0;
                        setSelectedImportanceCategory(newIndex);
                        setCurrentSuggestionIndex(0);
                      }}
                      className="p-3 rounded-lg bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors shadow-sm"
                      title="Next category"
                    >
                      <ChevronRight className="h-5 w-5 text-gray-600 dark:text-gray-400" />
                    </button>
                  </div>
                );
              })()}

              {/* Legend */}
              <div className="flex flex-wrap justify-center gap-4 text-xs mt-6">
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-red-400 rounded-full"></div>
                  <span className="text-gray-600 dark:text-gray-400">Low (0-4)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-yellow-400 rounded-full"></div>
                  <span className="text-gray-600 dark:text-gray-400">Medium (5-7)</span>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 bg-green-400 rounded-full"></div>
                  <span className="text-gray-600 dark:text-gray-400">High (8-10)</span>
                </div>
              </div>
            </div>

            {/* Enhanced Suggestions Carousel */}
            {(() => {
              // Get filtered suggestions for selected category
              const getFilteredSuggestions = () => {
                const lowCount = scoreDistributionArray.slice(0, 5).reduce((sum, count) => sum + count, 0);
                const mediumCount = scoreDistributionArray.slice(5, 8).reduce((sum, count) => sum + count, 0);
                const highCount = scoreDistributionArray.slice(8, 11).reduce((sum, count) => sum + count, 0);
                
                const categories = [
                  { name: 'Low Importance', range: '0-4', count: lowCount, min: 0, max: 4 },
                  { name: 'Medium Importance', range: '5-7', count: mediumCount, min: 5, max: 7 },
                  { name: 'High Importance', range: '8-10', count: highCount, min: 8, max: 10 }
                ].filter(cat => cat.count > 0);

                if (!categories[selectedImportanceCategory]) return [];

                const category = categories[selectedImportanceCategory];
                return suggestions.filter(suggestion => 
                  suggestion.score >= category.min && suggestion.score <= category.max
                );
              };

              const filteredSuggestions = getFilteredSuggestions();

              if (filteredSuggestions.length === 0) {
                return (
                  <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                    <div className="p-8 text-center">
                      <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
                      <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">No Suggestions</h3>
                      <p className="text-gray-600 dark:text-gray-400">
                        No suggestions found in the selected importance category.
                      </p>
                    </div>
                  </div>
                );
              }

              return (
                <div className="bg-white dark:bg-gray-800 rounded-xl shadow-lg border border-gray-200 dark:border-gray-700 overflow-hidden">
                  {/* Carousel Header */}
                  <div className="border-b border-gray-200 dark:border-gray-700 px-6 py-4">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-white">
                          {(() => {
                            const categories = ['Low Importance', 'Medium Importance', 'High Importance'];
                            return categories[selectedImportanceCategory] || 'Suggestions';
                          })()} Suggestions
                        </h3>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                          {filteredSuggestions.length} suggestion{filteredSuggestions.length !== 1 ? 's' : ''} found
                        </p>
                      </div>
                      <div className="flex items-center space-x-3">
                        <button
                          onClick={() => setCurrentSuggestionIndex(Math.max(0, currentSuggestionIndex - 1))}
                          disabled={currentSuggestionIndex === 0}
                          className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                          title="Previous suggestion"
                        >
                          <ChevronLeft className="h-4 w-4 text-gray-600 dark:text-gray-400" />
                        </button>
                        <div className="flex items-center space-x-2 bg-gray-100 dark:bg-gray-700 rounded-lg px-3 py-1">
                          <span className="text-sm font-medium text-gray-900 dark:text-white">
                            {currentSuggestionIndex + 1}
                          </span>
                          <span className="text-gray-500 dark:text-gray-400 text-sm">/</span>
                          <span className="text-sm font-medium text-gray-900 dark:text-white">
                            {filteredSuggestions.length}
                          </span>
                        </div>
                        <button
                          onClick={() => setCurrentSuggestionIndex(Math.min(filteredSuggestions.length - 1, currentSuggestionIndex + 1))}
                          disabled={currentSuggestionIndex === filteredSuggestions.length - 1}
                          className="p-2 rounded-lg bg-gray-100 dark:bg-gray-700 border border-gray-200 dark:border-gray-600 hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
                          title="Next suggestion"
                        >
                          <ChevronRight className="h-4 w-4 text-gray-600 dark:text-gray-400" />
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Animated Carousel Content */}
                  <div className="relative overflow-hidden" style={{ minHeight: '384px' }}>
                    <div 
                      className="flex transition-transform duration-500 ease-in-out"
                      style={{ transform: `translateX(-${currentSuggestionIndex * 100}%)` }}
                    >
                      {filteredSuggestions.map((suggestion, index) => (
                        <div key={index} className="w-full flex-shrink-0 h-96 overflow-y-auto">
                          <div className="p-6">
                            <div className="space-y-4">
                              {/* Suggestion Header */}
                              <div className="flex items-center gap-3 mb-4 flex-wrap">
                                <span className={`px-3 py-1 rounded-full text-sm font-medium ${
                                  suggestion.score >= 8 
                                    ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' 
                                    : suggestion.score >= 5 
                                    ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' 
                                    : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                                }`}>
                                  Importance: {suggestion.score}/10
                                </span>
                                <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                                  suggestion.commit_eligible 
                                    ? 'bg-indigo-100 text-indigo-700 dark:bg-indigo-900/30 dark:text-indigo-400' 
                                    : 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400'
                                }`}>
                                  {suggestion.commit_eligible ? '✓ Auto-Committable' : '⚠ Manual Review'}
                                </span>
                                <span className="text-sm text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded">
                                  {suggestion.file}
                                </span>
                              </div>
                              
                              {/* Suggestion Content */}
                              <div className="bg-gray-50 dark:bg-gray-700/50 rounded-lg p-4">
                                <h4 className="text-base font-semibold text-gray-900 dark:text-white mb-3">
                                  Suggestion
                                </h4>
                                <div className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">
                                  {suggestion.suggestion_summary}
                                </div>
                              </div>
                              
                              {/* Assessment */}
                              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-4">
                                <h4 className="text-base font-semibold text-blue-900 dark:text-blue-300 mb-3">
                                  Assessment
                                </h4>
                                <div className="text-sm text-blue-800 dark:text-blue-200 leading-relaxed">
                                  {suggestion.reasoning}
                                </div>
                              </div>
                              
                              {/* Commit Eligibility */}
                              {suggestion.commit_eligibility_reason && (
                                <div className={`rounded-lg p-4 ${
                                  suggestion.commit_eligible 
                                    ? 'bg-green-50 dark:bg-green-900/20' 
                                    : 'bg-amber-50 dark:bg-amber-900/20'
                                }`}>
                                  <h4 className={`text-base font-semibold mb-3 ${
                                    suggestion.commit_eligible 
                                      ? 'text-green-900 dark:text-green-300' 
                                      : 'text-amber-900 dark:text-amber-300'
                                  }`}>
                                    Commit Eligibility {suggestion.commit_eligibility_score && `(${suggestion.commit_eligibility_score}/10)`}
                                  </h4>
                                  <div className={`text-sm leading-relaxed ${
                                    suggestion.commit_eligible 
                                      ? 'text-green-800 dark:text-green-200' 
                                      : 'text-amber-800 dark:text-amber-200'
                                  }`}>
                                    {suggestion.commit_eligibility_reason}
                                  </div>
                                </div>
                              )}
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              );
            })()}
          </div>
        </div>
      </div>
    );
  };

  if (loading) {
    return (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[9999]">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-8 shadow-2xl">
          <div className="flex items-center gap-3">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-600"></div>
            <span className="text-gray-600 dark:text-gray-400 font-medium">Loading insights...</span>
          </div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[9999]">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-8 max-w-md shadow-2xl">
          <div className="flex items-center gap-3 text-red-600 dark:text-red-400 mb-4">
            <AlertCircle className="w-6 h-6" />
            <span className="font-semibold">Failed to Load Insights</span>
          </div>
          <p className="text-gray-600 dark:text-gray-400 mb-6">{error}</p>
          <div className="flex gap-3">
            <button
              onClick={fetchInsights}
              className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors"
            >
              Retry
            </button>
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-400 dark:hover:bg-gray-500 font-medium transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    );
  }

  if (!insights || Object.keys(insights).length === 0) {
    return (
      <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[9999]">
        <div className="bg-white dark:bg-gray-800 rounded-xl p-8 max-w-md text-center shadow-2xl">
          <FileText className="w-12 h-12 text-gray-400 mx-auto mb-4" />
          <h3 className="text-lg font-semibold text-gray-900 dark:text-white mb-2">No Insights Available</h3>
          <p className="text-gray-600 dark:text-gray-400 mb-6">
            This operation doesn't have any AI insights data yet.
          </p>
          <button
            onClick={onClose}
            className="px-4 py-2 bg-gray-300 dark:bg-gray-600 text-gray-700 dark:text-gray-200 rounded-lg hover:bg-gray-400 dark:hover:bg-gray-500 font-medium transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  const availableTabs = Object.keys(insights);

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center z-[9999] p-4">
      <div className="bg-white dark:bg-gray-900 rounded-xl w-full max-w-6xl max-h-[90vh] overflow-hidden flex flex-col shadow-2xl relative z-[10000]">
        {/* Enhanced Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
          <div>
            <h2 className="text-xl font-semibold text-gray-900 dark:text-white">AI Insights</h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">Operation: {operationId}</p>
          </div>
          <button
            onClick={onClose}
            className="p-2 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg transition-colors"
          >
            <X className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          </button>
        </div>

        {/* Enhanced Tab Navigation - Using consistent pill style */}
        <div className="px-6 py-4 bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
          <div className="flex space-x-1 bg-gray-200 dark:bg-gray-700 rounded-lg p-1">
            {availableTabs.includes('dev_time_analysis') && (
              <button
                onClick={() => setActiveTab('dev_time_analysis')}
                className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'dev_time_analysis'
                    ? 'bg-white dark:bg-gray-600 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                <Clock className="w-4 h-4 mr-2" />
                {insights.dev_time_analysis && (insights.dev_time_analysis.change_complexity_assessment || insights.dev_time_analysis.description_quality_assessment) 
                  ? 'Description Time Analysis' 
                  : 'Dev Time Analysis'}
              </button>
            )}
            
            {availableTabs.includes('self_reflection') && (
              <button
                onClick={() => setActiveTab('self_reflection')}
                className={`flex items-center px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'self_reflection'
                    ? 'bg-white dark:bg-gray-600 text-purple-600 dark:text-purple-400 shadow-sm'
                    : 'text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white'
                }`}
              >
                <Activity className="w-4 h-4 mr-2" />
                Self-Reflection Analysis
              </button>
            )}
          </div>
        </div>

        {/* Enhanced Content */}
        <div className="flex-1 overflow-y-auto p-6 bg-gray-50 dark:bg-gray-900">
          {activeTab === 'dev_time_analysis' && renderDevTimeInsights(insights.dev_time_analysis)}
          {activeTab === 'self_reflection' && renderSelfReflectionInsights(insights.self_reflection)}
        </div>
      </div>
    </div>
  );
};

export default OperationInsights; 