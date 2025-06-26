"""
Developer Time Estimation Service
Uses AI to accurately estimate developer time savings from code reviews and other PR-Agent operations
"""
import json
import copy
from typing import Dict, Any, Optional
from jinja2 import Environment, StrictUndefined

from pr_agent.algo.utils import load_yaml
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger


class DevTimeEstimator:
    """Service for estimating developer time savings using AI analysis"""
    
    def __init__(self, ai_handler, token_handler):
        self.ai_handler = ai_handler
        self.token_handler = token_handler
    
    async def estimate_review_time_savings(self, 
                                         diff: str,
                                         ai_review_content: str, 
                                         language: str,
                                         files_changed: int,
                                         lines_added: int,
                                         lines_deleted: int,
                                         model: str = None) -> Dict[str, Any]:
        """
        Estimate developer time savings from an AI-generated code review
        
        Args:
            diff: The code diff that was reviewed
            ai_review_content: The AI-generated review content
            language: Primary programming language
            files_changed: Number of files changed
            lines_added: Lines of code added
            lines_deleted: Lines of code deleted
            model: AI model to use for estimation
            
        Returns:
            Dict containing detailed time estimation analysis
        """
        try:
            # Prepare variables for the prompt
            variables = {
                'diff': diff,
                'ai_review_content': ai_review_content,
                'language': language,
                'files_changed': files_changed,
                'lines_added': lines_added,
                'lines_deleted': lines_deleted,
                'review_type': 'code_review'
            }
            
            # Render the prompts
            environment = Environment(undefined=StrictUndefined)
            system_prompt = environment.from_string(
                get_settings().pr_dev_time_estimation_prompt.system
            ).render(variables)
            user_prompt = environment.from_string(
                get_settings().pr_dev_time_estimation_prompt.user
            ).render(variables)
            
            # Get AI estimation
            if model is None:
                model = get_settings().config.model
                
            # Use configured time estimation model if available
            estimation_model = get_settings().get("pr_dev_time_estimation.model", "")
            if estimation_model:
                model = estimation_model
            
            # Check if time estimation is enabled
            if not get_settings().get("pr_dev_time_estimation.enabled", True):
                get_logger().debug("AI time estimation is disabled, using fallback")
                return self._get_fallback_estimation(files_changed, lines_added + lines_deleted)
            
            # Get timeout setting
            timeout_seconds = get_settings().get("pr_dev_time_estimation.estimation_timeout_seconds", 30)
            
            # Track token usage for time estimation calls
            from pr_agent.algo.token_handler import TokenUsageTracker
            estimation_token_tracker = TokenUsageTracker()
            
            try:
                response, finish_reason, token_usage = await self.ai_handler.chat_completion(
                    model=model,
                    temperature=0.2,  # Lower temperature for more consistent estimates
                    system=system_prompt,
                    user=user_prompt,
                    timeout=timeout_seconds
                )
                
                # Track token usage from successful estimation call
                estimation_token_tracker.add_usage(token_usage, call_failed=False)
                
                totals = estimation_token_tracker.get_totals()
                get_logger().debug(f"Time estimation AI call - Input: {totals['input_tokens']}, "
                                 f"Output: {totals['output_tokens']}, Model: {model}")
                
            except Exception as e:
                # Track failed estimation call
                estimation_token_tracker.add_usage(None, call_failed=True)
                get_logger().warning(f"Time estimation AI call failed: {e}")
                raise
            
            # Parse the structured response
            estimation_data = self._parse_estimation_response(response)
            
            # Check confidence threshold
            confidence_threshold = get_settings().get("pr_dev_time_estimation.confidence_threshold", "medium")
            if estimation_data and 'final_assessment' in estimation_data:
                confidence = estimation_data['final_assessment'].get('confidence_level', 'low')
                
                # Define confidence hierarchy
                confidence_levels = {'low': 1, 'medium': 2, 'high': 3}
                threshold_level = confidence_levels.get(confidence_threshold, 2)
                actual_level = confidence_levels.get(confidence, 1)
                
                if actual_level < threshold_level:
                    get_logger().info(f"AI estimation confidence ({confidence}) below threshold ({confidence_threshold}), using fallback")
                    return self._get_fallback_estimation(files_changed, lines_added + lines_deleted)
            
            # Add metadata
            estimation_data['metadata'] = {
                'model_used': model,
                'estimation_version': '1.0',
                'input_metrics': {
                    'diff_length': len(diff),
                    'review_length': len(ai_review_content),
                    'files_changed': files_changed,
                    'lines_added': lines_added,
                    'lines_deleted': lines_deleted,
                    'language': language
                }
            }
            
            return estimation_data
            
        except Exception as e:
            get_logger().error(f"Failed to estimate developer time savings: {e}")
            
            # Check if fallback to heuristic is enabled
            if get_settings().get("pr_dev_time_estimation.fallback_to_heuristic", True):
                return self._get_fallback_estimation(files_changed, lines_added + lines_deleted)
            else:
                # Return a minimal estimate if fallback is disabled
                return {
                    'final_assessment': {
                        'total_developer_hours_saved': 0.0,
                        'confidence_level': 'low',
                        'key_factors': ['AI estimation failed and fallback disabled'],
                        'assumptions_made': ['No time savings estimated due to estimation failure']
                    },
                    'metadata': {
                        'model_used': 'failed',
                        'estimation_version': '1.0',
                        'estimation_type': 'review',
                        'error': str(e)
                    }
                }
    
    async def estimate_description_time_savings(self,
                                              diff: str,
                                              ai_description_content: str,
                                              language: str,
                                              files_changed: int,
                                              lines_added: int,
                                              lines_deleted: int,
                                              model: str = None) -> Dict[str, Any]:
        """
        Estimate developer time savings from an AI-generated PR description
        """
        try:
            # Simplified estimation for descriptions - they generally save less time than reviews
            base_time = 0.25  # 15 minutes base time to write a good PR description
            
            # Scale by complexity
            complexity_multiplier = 1.0
            if files_changed > 10:
                complexity_multiplier = 1.5
            elif files_changed > 5:
                complexity_multiplier = 1.2
            
            total_lines = lines_added + lines_deleted
            if total_lines > 500:
                complexity_multiplier *= 1.3
            elif total_lines > 200:
                complexity_multiplier *= 1.1
            
            estimated_savings = base_time * complexity_multiplier
            
            return {
                'final_assessment': {
                    'total_developer_hours_saved': round(min(estimated_savings, 1.0), 2),
                    'confidence_level': 'medium',
                    'key_factors': ['PR description generation', 'Documentation time savings'],
                    'assumptions_made': ['Developer would spend 15-30 minutes writing description manually']
                },
                'metadata': {
                    'model_used': model or 'heuristic',
                    'estimation_version': '1.0',
                    'estimation_type': 'description'
                }
            }
            
        except Exception as e:
            get_logger().error(f"Failed to estimate description time savings: {e}")
            return self._get_fallback_estimation(files_changed, lines_added + lines_deleted, operation_type='description')
    
    async def estimate_suggestions_time_savings(self,
                                              diff: str,
                                              ai_suggestions_content: str,
                                              language: str,
                                              files_changed: int,
                                              lines_added: int,
                                              lines_deleted: int,
                                              suggestions_count: int = 0,
                                              model: str = None) -> Dict[str, Any]:
        """
        Estimate developer time savings from AI-generated code suggestions
        """
        try:
            # Base time for finding and implementing improvements manually
            base_time = 1.0  # 1 hour base for thorough code improvement analysis
            
            # Scale by suggestions quality and quantity
            if suggestions_count > 0:
                suggestion_multiplier = min(suggestions_count * 0.2, 2.0)  # Cap at 2x
            else:
                suggestion_multiplier = 1.0
            
            # Scale by code complexity
            total_lines = lines_added + lines_deleted
            if total_lines > 1000:
                complexity_multiplier = 2.0
            elif total_lines > 500:
                complexity_multiplier = 1.5
            elif total_lines > 200:
                complexity_multiplier = 1.2
            else:
                complexity_multiplier = 1.0
            
            estimated_savings = base_time * suggestion_multiplier * complexity_multiplier
            
            return {
                'final_assessment': {
                    'total_developer_hours_saved': round(min(estimated_savings, 4.0), 2),
                    'confidence_level': 'medium',
                    'key_factors': ['Code improvement analysis', 'Suggestion implementation time'],
                    'assumptions_made': ['Developer would spend 1-4 hours on manual code improvement']
                },
                'metadata': {
                    'model_used': model or 'heuristic',
                    'estimation_version': '1.0',
                    'estimation_type': 'suggestions',
                    'suggestions_count': suggestions_count
                }
            }
            
        except Exception as e:
            get_logger().error(f"Failed to estimate suggestions time savings: {e}")
            return self._get_fallback_estimation(files_changed, lines_added + lines_deleted, operation_type='suggestions')
    
    def _parse_estimation_response(self, response: str) -> Dict[str, Any]:
        """Parse the AI response into structured data"""
        try:
            # Try to extract JSON from the response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            else:
                # Fallback: try to parse as YAML
                return load_yaml(response)
                
        except Exception as e:
            get_logger().warning(f"Failed to parse estimation response: {e}")
            # Return a basic structure if parsing fails
            return {
                'final_assessment': {
                    'total_developer_hours_saved': 0.5,
                    'confidence_level': 'low',
                    'key_factors': ['Parsing failed - using fallback'],
                    'assumptions_made': ['Unable to parse AI response']
                }
            }
    
    def _get_fallback_estimation(self, files_changed: int, total_lines: int, operation_type: str = 'review') -> Dict[str, Any]:
        """Provide a fallback estimation when AI estimation fails"""
        
        if operation_type == 'description':
            base_hours = 0.25
            max_hours = 1.0
        elif operation_type == 'suggestions':
            base_hours = 1.0
            max_hours = 4.0
        else:  # review
            base_hours = 0.5
            max_hours = 3.0
        
        # Simple scaling
        if files_changed > 20:
            multiplier = 2.0
        elif files_changed > 10:
            multiplier = 1.5
        elif files_changed > 5:
            multiplier = 1.2
        else:
            multiplier = 1.0
        
        if total_lines > 1000:
            multiplier *= 1.5
        elif total_lines > 500:
            multiplier *= 1.2
        
        estimated_hours = min(base_hours * multiplier, max_hours)
        
        return {
            'final_assessment': {
                'total_developer_hours_saved': round(estimated_hours, 2),
                'confidence_level': 'low',
                'key_factors': ['Fallback estimation due to AI failure'],
                'assumptions_made': ['Using simple heuristic-based calculation']
            },
            'metadata': {
                'model_used': 'fallback_heuristic',
                'estimation_version': '1.0',
                'estimation_type': operation_type
            }
        } 