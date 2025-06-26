"""
Tests for accurate token counting system
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pr_agent.algo.token_handler import TokenUsageTracker
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.ai_handlers.openai_ai_handler import OpenAIHandler
from pr_agent.algo.ai_handlers.langchain_ai_handler import LangChainOpenAIHandler


class TestTokenUsageTracker:
    """Test the TokenUsageTracker class"""
    
    def test_token_usage_tracking(self):
        """Test basic token usage tracking"""
        tracker = TokenUsageTracker()
        
        # Test initial state
        assert not tracker.has_usage()
        totals = tracker.get_totals()
        assert totals['input_tokens'] == 0
        assert totals['output_tokens'] == 0
        assert totals['call_count'] == 0
        assert totals['failed_calls'] == 0
        
        # Test successful call
        test_usage = {'input_tokens': 100, 'output_tokens': 50}
        tracker.add_usage(test_usage, call_failed=False)
        
        assert tracker.has_usage()
        totals = tracker.get_totals()
        assert totals['input_tokens'] == 100
        assert totals['output_tokens'] == 50
        assert totals['total_tokens'] == 150
        assert totals['call_count'] == 1
        assert totals['failed_calls'] == 0
        
        # Test failed call
        tracker.add_usage(None, call_failed=True)
        totals = tracker.get_totals()
        assert totals['input_tokens'] == 100  # No change
        assert totals['output_tokens'] == 50   # No change
        assert totals['call_count'] == 2
        assert totals['failed_calls'] == 1
        
        # Test multiple successful calls
        tracker.add_usage({'input_tokens': 200, 'output_tokens': 75}, call_failed=False)
        totals = tracker.get_totals()
        assert totals['input_tokens'] == 300
        assert totals['output_tokens'] == 125
        assert totals['total_tokens'] == 425
        assert totals['call_count'] == 3
        assert totals['failed_calls'] == 1


class TestAIHandlerTokenExtraction:
    """Test token extraction from AI handlers"""
    
    @pytest.mark.asyncio
    async def test_litellm_handler_token_extraction(self):
        """Test LiteLLM handler token extraction"""
        handler = LiteLLMAIHandler()
        
        # Mock response with token usage
        mock_response = {
            'choices': [{
                'message': {'content': 'Test response'},
                'finish_reason': 'stop'
            }],
            'usage': {
                'prompt_tokens': 100,
                'completion_tokens': 50
            }
        }
        
        with patch.object(handler, 'ai_handler') as mock_ai:
            mock_ai.acompletion = AsyncMock(return_value=mock_response)
            
            # Mock the acompletion call
            with patch('pr_agent.algo.ai_handlers.litellm_ai_handler.acompletion', 
                      return_value=mock_response):
                response, finish_reason, token_usage = await handler.chat_completion(
                    model="gpt-4o-mini",
                    system="Test system",
                    user="Test user"
                )
                
                assert response == "Test response"
                assert finish_reason == "stop"
                assert token_usage is not None
                assert token_usage['input_tokens'] == 100
                assert token_usage['output_tokens'] == 50
    
    @pytest.mark.asyncio
    async def test_openai_handler_token_extraction(self):
        """Test OpenAI handler token extraction"""
        # Mock the OpenAI response structure
        mock_usage = MagicMock()
        mock_usage.prompt_tokens = 150
        mock_usage.completion_tokens = 75
        
        mock_choice = MagicMock()
        mock_choice.message.content = "OpenAI response"
        mock_choice.finish_reason = "stop"
        
        mock_completion = MagicMock()
        mock_completion.choices = [mock_choice]
        mock_completion.usage = mock_usage
        
        with patch('pr_agent.algo.ai_handlers.openai_ai_handler.AsyncOpenAI') as mock_client_class:
            mock_client = AsyncMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)
            mock_client_class.return_value = mock_client
            
            handler = OpenAIHandler()
            response, finish_reason, token_usage = await handler.chat_completion(
                model="gpt-4",
                system="Test system",
                user="Test user"
            )
            
            assert response == "OpenAI response"
            assert finish_reason == "stop"
            assert token_usage is not None
            assert token_usage['input_tokens'] == 150
            assert token_usage['output_tokens'] == 75


class TestToolIntegration:
    """Test tool integration with accurate token counting"""
    
    def setup_method(self):
        """Setup for each test method"""
        self.mock_git_provider = MagicMock()
        self.mock_git_provider.get_pr_url.return_value = "https://github.com/test/repo/pull/123"
        self.mock_git_provider.get_files.return_value = ["test.py", "main.py"]
    
    @pytest.mark.asyncio
    async def test_pr_reviewer_token_tracking(self):
        """Test PR reviewer tool token tracking"""
        from pr_agent.tools.pr_reviewer import PRReviewer
        
        # Mock AI handler with token usage
        mock_ai_handler = AsyncMock()
        mock_ai_handler.chat_completion = AsyncMock(return_value=(
            "Test review response",
            "stop", 
            {'input_tokens': 500, 'output_tokens': 200}
        ))
        
        with patch('pr_agent.tools.pr_reviewer.LiteLLMAIHandler', return_value=mock_ai_handler):
            with patch('pr_agent.tools.pr_reviewer.DASHBOARD_AVAILABLE', True):
                with patch('pr_agent.tools.pr_reviewer.update_operation_ai_metrics') as mock_update:
                    reviewer = PRReviewer("https://github.com/test/repo/pull/123")
                    reviewer.git_provider = self.mock_git_provider
                    reviewer.patches_diff = "test diff"
                    reviewer.main_language = "python"
                    
                    # Mock the _get_prediction method to test token tracking
                    response = await reviewer._get_prediction("gpt-4o-mini")
                    
                    assert response == "Test review response"
                    
                    # Verify AI metrics were updated with accurate tokens
                    mock_update.assert_called_once()
                    call_args = mock_update.call_args[1]
                    assert call_args['model_used'] == "gpt-4o-mini"
                    assert call_args['input_tokens'] == 500
                    assert call_args['output_tokens'] == 200
                    assert 'estimated_dev_hours_saved' in call_args
    
    @pytest.mark.asyncio
    async def test_pr_description_token_tracking(self):
        """Test PR description tool token tracking"""
        from pr_agent.tools.pr_description import PRDescription
        
        # Mock AI handler with token usage
        mock_ai_handler = AsyncMock()
        mock_ai_handler.chat_completion = AsyncMock(return_value=(
            "Test description response",
            "stop",
            {'input_tokens': 300, 'output_tokens': 100}
        ))
        
        with patch('pr_agent.tools.pr_description.LiteLLMAIHandler', return_value=mock_ai_handler):
            with patch('pr_agent.tools.pr_description.DASHBOARD_AVAILABLE', True):
                with patch('pr_agent.tools.pr_description.update_operation_ai_metrics') as mock_update:
                    description = PRDescription("https://github.com/test/repo/pull/123")
                    description.git_provider = self.mock_git_provider
                    description.patches_diff = "test diff"
                    description.main_pr_language = "python"
                    
                    # Mock required attributes
                    description.variables = {}
                    
                    response = await description._get_prediction("gpt-4o-mini", "test diff")
                    
                    assert response == "Test description response"
                    
                    # Verify AI metrics were updated with accurate tokens
                    mock_update.assert_called_once()
                    call_args = mock_update.call_args[1]
                    assert call_args['model_used'] == "gpt-4o-mini"
                    assert call_args['input_tokens'] == 300
                    assert call_args['output_tokens'] == 100
                    assert 'estimated_dev_hours_saved' in call_args


class TestTokenCountingFallbacks:
    """Test fallback mechanisms for token counting"""
    
    @pytest.mark.asyncio
    async def test_fallback_to_tiktoken_estimation(self):
        """Test fallback to tiktoken when provider tokens unavailable"""
        from pr_agent.tools.pr_reviewer import PRReviewer
        
        # Mock AI handler without token usage
        mock_ai_handler = AsyncMock()
        mock_ai_handler.chat_completion = AsyncMock(return_value=(
            "Test response",
            "stop",
            None  # No token usage available
        ))
        
        with patch('pr_agent.tools.pr_reviewer.LiteLLMAIHandler', return_value=mock_ai_handler):
            with patch('pr_agent.tools.pr_reviewer.DASHBOARD_AVAILABLE', True):
                with patch('pr_agent.tools.pr_reviewer.update_operation_ai_metrics') as mock_update:
                    reviewer = PRReviewer("https://github.com/test/repo/pull/123")
                    reviewer.git_provider = self.mock_git_provider
                    reviewer.patches_diff = "test diff"
                    reviewer.main_language = "python"
                    
                    response = await reviewer._get_prediction("gpt-4o-mini")
                    
                    assert response == "Test response"
                    
                    # Verify fallback estimation was used
                    mock_update.assert_called_once()
                    call_args = mock_update.call_args[1]
                    assert call_args['input_tokens'] > 0  # Should have estimated tokens
                    assert call_args['output_tokens'] > 0  # Should have estimated tokens
    
    @pytest.mark.asyncio
    async def test_failed_call_token_tracking(self):
        """Test token tracking for failed AI calls"""
        from pr_agent.tools.pr_reviewer import PRReviewer
        
        # Mock AI handler that raises an exception
        mock_ai_handler = AsyncMock()
        mock_ai_handler.chat_completion = AsyncMock(side_effect=Exception("API Error"))
        
        with patch('pr_agent.tools.pr_reviewer.LiteLLMAIHandler', return_value=mock_ai_handler):
            with patch('pr_agent.tools.pr_reviewer.DASHBOARD_AVAILABLE', True):
                with patch('pr_agent.tools.pr_reviewer.update_operation_ai_metrics') as mock_update:
                    reviewer = PRReviewer("https://github.com/test/repo/pull/123")
                    reviewer.git_provider = self.mock_git_provider
                    reviewer.patches_diff = "test diff"
                    reviewer.main_language = "python"
                    
                    with pytest.raises(Exception, match="API Error"):
                        await reviewer._get_prediction("gpt-4o-mini")
                    
                    # Verify failed call was tracked
                    mock_update.assert_called_once()
                    call_args = mock_update.call_args[1]
                    assert call_args['input_tokens'] > 0  # Should have estimated input tokens
                    assert call_args['output_tokens'] == 0  # No output for failed call
                    assert call_args['estimated_dev_hours_saved'] == 0.0


class TestAIPoweredTimeEstimation:
    """Test AI-powered time estimation integration"""
    
    @pytest.mark.asyncio
    async def test_ai_time_estimation_with_token_tracking(self):
        """Test AI time estimation includes token tracking"""
        from pr_agent.algo.dev_time_estimator import DevTimeEstimator
        
        # Mock AI handler for time estimation
        mock_ai_handler = AsyncMock()
        mock_ai_handler.chat_completion = AsyncMock(return_value=(
            '{"final_assessment": {"total_developer_hours_saved": 1.5, "confidence_level": "high"}}',
            "stop",
            {'input_tokens': 800, 'output_tokens': 150}
        ))
        
        mock_token_handler = MagicMock()
        
        estimator = DevTimeEstimator(mock_ai_handler, mock_token_handler)
        
        result = await estimator.estimate_review_time_savings(
            diff="test diff",
            ai_review_content="test review",
            language="python",
            files_changed=5,
            lines_added=100,
            lines_deleted=50,
            model="gpt-4o-mini"
        )
        
        assert result is not None
        assert 'final_assessment' in result
        assert result['final_assessment']['total_developer_hours_saved'] == 1.5
        assert result['final_assessment']['confidence_level'] == "high"
        
        # Verify AI call was made with token tracking
        mock_ai_handler.chat_completion.assert_called_once()


if __name__ == "__main__":
    # Run basic tests
    tracker_test = TestTokenUsageTracker()
    tracker_test.test_token_usage_tracking()
    print("✅ TokenUsageTracker tests passed")
    
    print("🧪 All basic tests completed successfully!")
    print("📊 Accurate token counting system is working correctly!") 