"""
Tests for PR Filtering Utilities
Tests the filtering logic to prevent pr-agent from running in specific scenarios

This module includes comprehensive tests for:
- PRFilterResult class functionality
- PR size calculation utilities
- Description generation filters
- No-bots termination filters
- Large PR termination filters
- Existing PR-Agent comments detection and filtering
- Integration scenarios and edge cases
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from pr_agent.algo.pr_filters import (
    PRFilterResult,
    check_pr_filters,
    calculate_total_lines_changed,
    should_skip_description_generation,
    should_terminate_job,
    should_skip_large_pr,
    check_for_existing_pr_agent_comments
)


class TestPRFilterResult:
    """Test cases for PRFilterResult class"""
    
    def test_default_initialization(self):
        """Test default initialization of PRFilterResult"""
        result = PRFilterResult()
        assert result.should_skip == False
        assert result.should_terminate == False
        assert result.reason == ""
    
    def test_custom_initialization(self):
        """Test custom initialization of PRFilterResult"""
        result = PRFilterResult(should_skip=True, should_terminate=False, reason="Test reason")
        assert result.should_skip == True
        assert result.should_terminate == False
        assert result.reason == "Test reason"
    
    def test_terminate_initialization(self):
        """Test initialization with termination"""
        result = PRFilterResult(should_terminate=True, reason="Critical error")
        assert result.should_skip == False
        assert result.should_terminate == True
        assert result.reason == "Critical error"


class TestCalculateTotalLinesChanged:
    """Test cases for calculate_total_lines_changed function"""
    
    def test_calculate_total_lines_success(self):
        """Test successful calculation of total lines changed"""
        # Mock git provider
        mock_git_provider = Mock()
        
        # Mock diff files with line counts
        mock_file1 = Mock()
        mock_file1.num_plus_lines = 10
        mock_file1.num_minus_lines = 5
        
        mock_file2 = Mock()
        mock_file2.num_plus_lines = 20
        mock_file2.num_minus_lines = 15
        
        mock_git_provider.get_diff_files.return_value = [mock_file1, mock_file2]
        
        result = calculate_total_lines_changed(mock_git_provider)
        
        # Expected: (10 + 5) + (20 + 15) = 50
        assert result == 50
        mock_git_provider.get_diff_files.assert_called_once()
    
    def test_calculate_total_lines_with_zero_counts(self):
        """Test calculation with zero line counts"""
        mock_git_provider = Mock()
        
        mock_file1 = Mock()
        mock_file1.num_plus_lines = 0
        mock_file1.num_minus_lines = 0
        
        mock_file2 = Mock()
        mock_file2.num_plus_lines = 10
        mock_file2.num_minus_lines = 0
        
        mock_git_provider.get_diff_files.return_value = [mock_file1, mock_file2]
        
        result = calculate_total_lines_changed(mock_git_provider)
        
        # Expected: (0 + 0) + (10 + 0) = 10
        assert result == 10
    
    def test_calculate_total_lines_with_negative_counts(self):
        """Test calculation with negative line counts (should be treated as 0)"""
        mock_git_provider = Mock()
        
        mock_file1 = Mock()
        mock_file1.num_plus_lines = -5  # Should be treated as 0
        mock_file1.num_minus_lines = 10
        
        mock_git_provider.get_diff_files.return_value = [mock_file1]
        
        result = calculate_total_lines_changed(mock_git_provider)
        
        # Expected: (0 + 10) = 10
        assert result == 10
    
    def test_calculate_total_lines_empty_diff(self):
        """Test calculation with empty diff"""
        mock_git_provider = Mock()
        mock_git_provider.get_diff_files.return_value = []
        
        result = calculate_total_lines_changed(mock_git_provider)
        
        assert result == 0
    
    def test_calculate_total_lines_exception(self):
        """Test calculation when git provider raises exception"""
        mock_git_provider = Mock()
        mock_git_provider.get_diff_files.side_effect = Exception("Git error")
        
        result = calculate_total_lines_changed(mock_git_provider)
        
        assert result == 0


class TestShouldSkipDescriptionGeneration:
    """Test cases for should_skip_description_generation function"""
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_skip_when_description_exists(self, mock_get_settings):
        """Test skipping when description exists and filter is enabled"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Existing description"
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True
            }
        }
        
        result = should_skip_description_generation(mock_git_provider)
        
        assert result == True
        mock_git_provider.get_pr_description_full.assert_called_once()
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_skip_when_description_empty(self, mock_get_settings):
        """Test not skipping when description is empty"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = ""
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True
            }
        }
        
        result = should_skip_description_generation(mock_git_provider)
        
        assert result == False
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_skip_when_description_whitespace_only(self, mock_get_settings):
        """Test not skipping when description is only whitespace"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "   \n\t  "
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True
            }
        }
        
        result = should_skip_description_generation(mock_git_provider)
        
        assert result == False
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_skip_when_filter_disabled(self, mock_get_settings):
        """Test not skipping when filter is disabled"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Existing description"
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": False
            }
        }
        
        result = should_skip_description_generation(mock_git_provider)
        
        assert result == False
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_skip_when_no_filters_config(self, mock_get_settings):
        """Test not skipping when no filters configured"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Existing description"
        
        mock_get_settings.return_value = {}
        
        result = should_skip_description_generation(mock_git_provider)
        
        assert result == False
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_exception_handling(self, mock_get_settings):
        """Test exception handling in description check"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.side_effect = Exception("API error")
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True
            }
        }
        
        result = should_skip_description_generation(mock_git_provider)
        
        assert result == False


class TestShouldTerminateJob:
    """Test cases for should_terminate_job function"""
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_terminate_when_no_bots_found(self, mock_get_settings):
        """Test termination when [no_bots] is found"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "This PR has [no_bots] in it"
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "terminate_on_no_bots": True
            }
        }
        
        should_terminate, reason = should_terminate_job(mock_git_provider)
        
        assert should_terminate == True
        assert "[nobots] found in PR description" in reason
        mock_git_provider.get_pr_description_full.assert_called_once()
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_terminate_case_insensitive(self, mock_get_settings):
        """Test termination with case-insensitive matching"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "This PR has [NO_BOTS] in it"
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "terminate_on_no_bots": True
            }
        }
        
        should_terminate, reason = should_terminate_job(mock_git_provider)
        
        assert should_terminate == True
        assert "[nobots] found in PR description" in reason
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_terminate_when_no_bots_not_found(self, mock_get_settings):
        """Test no termination when [no_bots] is not found"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "This PR has no special tags"
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "terminate_on_no_bots": True
            }
        }
        
        should_terminate, reason = should_terminate_job(mock_git_provider)
        
        assert should_terminate == False
        assert reason == ""
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_terminate_when_filter_disabled(self, mock_get_settings):
        """Test no termination when filter is disabled"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "This PR has [no_bots] in it"
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "terminate_on_no_bots": False
            }
        }
        
        should_terminate, reason = should_terminate_job(mock_git_provider)
        
        assert should_terminate == False
        assert reason == ""
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_exception_handling(self, mock_get_settings):
        """Test exception handling in termination check"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.side_effect = Exception("API error")
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "terminate_on_no_bots": True
            }
        }
        
        should_terminate, reason = should_terminate_job(mock_git_provider)
        
        assert should_terminate == False
        assert reason == ""


class TestShouldSkipLargePR:
    """Test cases for should_skip_large_pr function"""
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_skip_when_pr_too_large(self, mock_get_settings, mock_calculate_lines):
        """Test skipping when PR exceeds line limit"""
        mock_git_provider = Mock()
        mock_calculate_lines.return_value = 1500
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "max_lines_changed": 1000
            }
        }
        
        should_skip, reason = should_skip_large_pr(mock_git_provider)
        
        assert should_skip == True
        assert "PR too large" in reason
        assert "1500" in reason
        assert "1000" in reason
        mock_calculate_lines.assert_called_once_with(mock_git_provider)
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_skip_when_pr_within_limit(self, mock_get_settings, mock_calculate_lines):
        """Test not skipping when PR is within line limit"""
        mock_git_provider = Mock()
        mock_calculate_lines.return_value = 500
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "max_lines_changed": 1000
            }
        }
        
        should_skip, reason = should_skip_large_pr(mock_git_provider)
        
        assert should_skip == False
        assert reason == ""
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_skip_when_limit_disabled(self, mock_get_settings):
        """Test not skipping when line limit is disabled"""
        mock_git_provider = Mock()
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "max_lines_changed": 0
            }
        }
        
        should_skip, reason = should_skip_large_pr(mock_git_provider)
        
        assert should_skip == False
        assert reason == ""
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_exception_handling(self, mock_get_settings, mock_calculate_lines):
        """Test exception handling in size check"""
        mock_git_provider = Mock()
        mock_calculate_lines.side_effect = Exception("Calculation error")
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "max_lines_changed": 1000
            }
        }
        
        should_skip, reason = should_skip_large_pr(mock_git_provider)
        
        assert should_skip == False
        assert reason == ""


class TestCheckPRFilters:
    """Test cases for check_pr_filters function"""
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_filters_configured(self, mock_get_settings, mock_calculate_lines):
        """Test when no filters are configured"""
        mock_git_provider = Mock()
        mock_get_settings.return_value = {}
        
        result = check_pr_filters(mock_git_provider, "describe")
        
        assert result.should_skip == False
        assert result.should_terminate == False
        assert result.reason == ""
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_all_filters_pass(self, mock_get_settings, mock_calculate_lines):
        """Test when all filters pass - using review command to avoid description skip"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal PR description"
        mock_calculate_lines.return_value = 500
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        result = check_pr_filters(mock_git_provider, "review")
        
        assert result.should_skip == False
        assert result.should_terminate == False
        assert result.reason == ""
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_skip_describe_when_description_exists(self, mock_get_settings, mock_calculate_lines):
        """Test skipping describe command when description exists"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Existing description"
        mock_calculate_lines.return_value = 500
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        result = check_pr_filters(mock_git_provider, "describe")
        
        assert result.should_skip == True
        assert result.should_terminate == False
        assert "PR description already exists" in result.reason
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_skip_describe_when_not_describe_command(self, mock_get_settings, mock_calculate_lines):
        """Test not skipping when command is not describe"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Existing description"
        mock_calculate_lines.return_value = 500
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        result = check_pr_filters(mock_git_provider, "review")
        
        assert result.should_skip == False
        assert result.should_terminate == False
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_terminate_on_no_bots(self, mock_get_settings, mock_calculate_lines):
        """Test termination when [no_bots] is found - using review command to avoid description skip"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "This PR has [no_bots] in it"
        mock_calculate_lines.return_value = 500
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        result = check_pr_filters(mock_git_provider, "review")
        
        assert result.should_skip == False
        assert result.should_terminate == True
        assert "[nobots] found" in result.reason
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_terminate_large_pr(self, mock_get_settings, mock_calculate_lines):
        """Test terminating when PR is too large - using review command to avoid description skip"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal description"
        mock_calculate_lines.return_value = 1500

        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }

        result = check_pr_filters(mock_git_provider, "review")

        assert result.should_skip == False
        assert result.should_terminate == True
        assert "PR too large" in result.reason
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_terminate_on_description_fetch_error(self, mock_get_settings):
        """Test termination when description fetch fails"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.side_effect = Exception("API error")
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        result = check_pr_filters(mock_git_provider, "describe")
        
        assert result.should_skip == False
        assert result.should_terminate == True
        assert "Failed to retrieve PR description" in result.reason
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_terminate_on_line_calculation_error(self, mock_get_settings, mock_calculate_lines):
        """Test terminating when line calculation fails - using review command to avoid description skip"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal description"
        mock_calculate_lines.side_effect = Exception("Calculation error")

        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }

        result = check_pr_filters(mock_git_provider, "review")

        assert result.should_skip == False
        assert result.should_terminate == True
        assert "Failed to calculate PR size" in result.reason
    
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_terminate_on_critical_error(self, mock_get_settings):
        """Test termination on critical error in filter processing"""
        mock_git_provider = Mock()
        mock_get_settings.side_effect = Exception("Critical error")
        
        result = check_pr_filters(mock_git_provider, "describe")
        
        assert result.should_skip == False
        assert result.should_terminate == True
        assert "Critical error in PR filter processing" in result.reason
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_priority_order_terminate_over_skip(self, mock_get_settings, mock_calculate_lines):
        """Test that termination takes priority over skipping - using review command to avoid description skip"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "This PR has [no_bots] and is large"
        mock_calculate_lines.return_value = 1500
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        result = check_pr_filters(mock_git_provider, "review")
        
        # Should terminate due to [no_bots], not skip due to size
        assert result.should_skip == False
        assert result.should_terminate == True
        assert "[nobots] found" in result.reason


class TestIntegrationScenarios:
    """Integration test scenarios for PR filters"""
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_real_world_scenario_1(self, mock_get_settings, mock_calculate_lines):
        """Test real-world scenario: Normal PR with all filters enabled"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "This PR adds new feature X"
        mock_calculate_lines.return_value = 200
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        # Test describe command - should skip due to existing description
        result = check_pr_filters(mock_git_provider, "describe")
        assert result.should_skip == True
        assert "PR description already exists" in result.reason
        
        # Test review command - should pass
        result = check_pr_filters(mock_git_provider, "review")
        assert result.should_skip == False
        assert result.should_terminate == False
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_real_world_scenario_2(self, mock_get_settings, mock_calculate_lines):
        """Test real-world scenario: PR with [no_bots] tag"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "This PR has [no_bots] tag"
        mock_calculate_lines.return_value = 50
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        # Should terminate for review and improve commands (describe would skip due to description)
        for command in ["review", "improve"]:
            result = check_pr_filters(mock_git_provider, command)
            assert result.should_terminate == True
            assert "[nobots] found" in result.reason
        
        # For describe command, it should skip due to description existence, not terminate
        result = check_pr_filters(mock_git_provider, "describe")
        assert result.should_skip == True
        assert "PR description already exists" in result.reason
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_real_world_scenario_3(self, mock_get_settings, mock_calculate_lines):
        """Test real-world scenario: Large PR without description"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = ""
        mock_calculate_lines.return_value = 2000
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        # Should terminate due to size
        result = check_pr_filters(mock_git_provider, "describe")
        assert result.should_terminate == True
        assert "PR too large" in result.reason
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_edge_case_whitespace_description(self, mock_get_settings, mock_calculate_lines):
        """Test edge case: Description with only whitespace"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "   \n\t  \n  "
        mock_calculate_lines.return_value = 100
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        # Should not skip describe (whitespace-only description is treated as empty)
        result = check_pr_filters(mock_git_provider, "describe")
        assert result.should_skip == False
        assert result.should_terminate == False
    
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_edge_case_none_description(self, mock_get_settings, mock_calculate_lines):
        """Test edge case: None description"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = None
        mock_calculate_lines.return_value = 100
        
        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
        
        # Should not skip describe (None description is treated as empty)
        result = check_pr_filters(mock_git_provider, "describe")
        assert result.should_skip == False
        assert result.should_terminate == False


class TestCheckForExistingPRAgentComments:
    """Test cases for check_for_existing_pr_agent_comments function"""

    def test_detect_existing_review_header(self):
        """Test detecting existing PR-Agent review header"""
        mock_git_provider = Mock()
        mock_comment = Mock()
        mock_comment.body = "PR Reviewer Guide 🔍\n\nSome review content here..."
        mock_git_provider.get_issue_comments.return_value = [mock_comment]

        result = check_for_existing_pr_agent_comments(mock_git_provider)

        assert result == True
        mock_git_provider.get_issue_comments.assert_called_once()

    def test_detect_review_header_with_different_content(self):
        """Test detecting review header with different following content"""
        mock_git_provider = Mock()
        mock_comment = Mock()
        mock_comment.body = "PR Reviewer Guide 🔍\n\n## Code Suggestions\n\nSome suggestions..."
        mock_git_provider.get_issue_comments.return_value = [mock_comment]

        result = check_for_existing_pr_agent_comments(mock_git_provider)

        assert result == True

    def test_no_existing_comments(self):
        """Test when no PR-Agent comments exist"""
        mock_git_provider = Mock()
        mock_comment1 = Mock()
        mock_comment1.body = "This is a regular comment"
        mock_comment2 = Mock()
        mock_comment2.body = "Another comment"
        mock_git_provider.get_issue_comments.return_value = [mock_comment1, mock_comment2]

        result = check_for_existing_pr_agent_comments(mock_git_provider)

        assert result == False

    def test_empty_comments_list(self):
        """Test when there are no comments at all"""
        mock_git_provider = Mock()
        mock_git_provider.get_issue_comments.return_value = []

        result = check_for_existing_pr_agent_comments(mock_git_provider)

        assert result == False

    def test_comment_without_body_attribute(self):
        """Test handling comments without body attribute"""
        mock_git_provider = Mock()
        mock_comment = Mock()
        del mock_comment.body  # Remove body attribute
        mock_comment.__str__ = Mock(return_value="PR Reviewer Guide 🔍")
        mock_git_provider.get_issue_comments.return_value = [mock_comment]

        result = check_for_existing_pr_agent_comments(mock_git_provider)

        assert result == True

    def test_exception_in_get_issue_comments(self):
        """Test exception handling when fetching comments fails"""
        mock_git_provider = Mock()
        mock_git_provider.get_issue_comments.side_effect = Exception("API error")

        result = check_for_existing_pr_agent_comments(mock_git_provider)

        assert result == False

    def test_empty_comment_body(self):
        """Test handling empty comment bodies"""
        mock_git_provider = Mock()
        mock_comment1 = Mock()
        mock_comment1.body = ""
        mock_comment2 = Mock()
        mock_comment2.body = None
        mock_git_provider.get_issue_comments.return_value = [mock_comment1, mock_comment2]

        result = check_for_existing_pr_agent_comments(mock_git_provider)

        assert result == False

    def test_multiple_comments_with_header(self):
        """Test finding header among multiple comments"""
        mock_git_provider = Mock()

        mock_comment1 = Mock()
        mock_comment1.body = "Regular comment"

        mock_comment2 = Mock()
        mock_comment2.body = "PR Reviewer Guide 🔍\n\nReview content"

        mock_comment3 = Mock()
        mock_comment3.body = "Another regular comment"

        mock_git_provider.get_issue_comments.return_value = [mock_comment1, mock_comment2, mock_comment3]

        result = check_for_existing_pr_agent_comments(mock_git_provider)

        assert result == True

    def test_case_insensitive_header_matching(self):
        """Any case of 'PR Reviewer Guide' substring matches (see pr_filters implementation)."""
        mock_git_provider = Mock()
        mock_comment = Mock()
        mock_comment.body = "pr reviewer guide 🔍"  # lowercase
        mock_git_provider.get_issue_comments.return_value = [mock_comment]

        result = check_for_existing_pr_agent_comments(mock_git_provider)

        assert result is True

    def test_partial_header_match_not_sufficient(self):
        """Strings that do not contain the contiguous marker 'pr reviewer guide' are ignored."""
        mock_git_provider = Mock()

        test_comments = [
            "Reviewer Guide 🔍",  # missing leading 'pr '
            "PR Reviewer 🔍",  # missing 'guide'
            "Guide 🔍",
            "Notes about pull request review standards",
        ]

        for comment_body in test_comments:
            mock_comment = Mock()
            mock_comment.body = comment_body
            mock_git_provider.get_issue_comments.return_value = [mock_comment]

            result = check_for_existing_pr_agent_comments(mock_git_provider)
            assert result is False, f"Should not match partial header: {comment_body}"


class TestSkipIfReviewSuggestionsExist:
    """Test cases for the skip_if_review_suggestions_exist filter"""

    @patch('pr_agent.algo.pr_filters.check_for_existing_pr_agent_comments')
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_skip_when_existing_comments_found(self, mock_get_settings, mock_calculate_lines, mock_check_comments):
        """Test skipping when existing PR-Agent comments are found"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal description"
        mock_calculate_lines.return_value = 500
        mock_check_comments.return_value = True

        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_review_suggestions_exist": True,
                "terminate_on_no_bots": False,
                "max_lines_changed": 1000
            }
        }

        result = check_pr_filters(mock_git_provider, "review")

        assert result.should_skip == True
        assert result.should_terminate == False
        assert "PR-Agent has already processed this PR" in result.reason
        mock_check_comments.assert_called_once_with(mock_git_provider)

    @patch('pr_agent.algo.pr_filters.check_for_existing_pr_agent_comments')
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_no_skip_when_no_existing_comments(self, mock_get_settings, mock_calculate_lines, mock_check_comments):
        """Test not skipping when no existing PR-Agent comments are found"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal description"
        mock_calculate_lines.return_value = 500
        mock_check_comments.return_value = False

        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_review_suggestions_exist": True,
                "terminate_on_no_bots": False,
                "max_lines_changed": 1000
            }
        }

        result = check_pr_filters(mock_git_provider, "review")

        assert result.should_skip == False
        assert result.should_terminate == False
        assert result.reason == ""
        mock_check_comments.assert_called_once_with(mock_git_provider)

    @patch('pr_agent.algo.pr_filters.check_for_existing_pr_agent_comments')
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_skip_applies_to_all_commands(self, mock_get_settings, mock_calculate_lines, mock_check_comments):
        """Test that the existing comments filter applies to all commands"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal description"
        mock_calculate_lines.return_value = 500
        mock_check_comments.return_value = True

        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_review_suggestions_exist": True,
                "terminate_on_no_bots": False,
                "max_lines_changed": 1000
            }
        }

        # Test with different commands
        for command in ["review", "describe", "improve", "ask"]:
            result = check_pr_filters(mock_git_provider, command)
            assert result.should_skip == True, f"Should skip command: {command}"
            assert "PR-Agent has already processed this PR" in result.reason

    @patch('pr_agent.algo.pr_filters.check_for_existing_pr_agent_comments')
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_filter_disabled_when_setting_false(self, mock_get_settings, mock_calculate_lines, mock_check_comments):
        """Test that filter is not applied when setting is False"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal description"
        mock_calculate_lines.return_value = 500
        mock_check_comments.return_value = True

        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_review_suggestions_exist": False,  # Disabled
                "terminate_on_no_bots": False,
                "max_lines_changed": 1000
            }
        }

        result = check_pr_filters(mock_git_provider, "review")

        # Should not check for existing comments at all
        mock_check_comments.assert_not_called()
        assert result.should_skip == False
        assert result.should_terminate == False

    @patch('pr_agent.algo.pr_filters.check_for_existing_pr_agent_comments')
    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_exception_in_existing_comments_check(self, mock_get_settings, mock_calculate_lines, mock_check_comments):
        """Test exception handling when checking for existing comments fails - should skip conservatively"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal description"
        mock_calculate_lines.return_value = 500
        mock_check_comments.side_effect = Exception("Comment check failed")

        mock_get_settings.return_value = {
            "pr_filters": {
                "skip_if_review_suggestions_exist": True,
                "terminate_on_no_bots": False,
                "max_lines_changed": 1000
            }
        }

        result = check_pr_filters(mock_git_provider, "review")

        assert result.should_skip == True
        assert result.should_terminate == False
        assert "Failed to check for existing PR-Agent comments" in result.reason


class TestLargePRTermination:
    """Test cases for the updated large PR filter (now terminates instead of skips)"""

    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_terminate_on_large_pr(self, mock_get_settings, mock_calculate_lines):
        """Test that large PRs now terminate instead of skip"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal description"
        mock_calculate_lines.return_value = 1500

        mock_get_settings.return_value = {
            "pr_filters": {
                "max_lines_changed": 1000,
                "terminate_on_no_bots": False
            }
        }

        result = check_pr_filters(mock_git_provider, "review")

        assert result.should_skip == False
        assert result.should_terminate == True
        assert "PR too large" in result.reason
        assert "1500" in result.reason
        assert "1000" in result.reason

    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_priority_terminate_over_skip(self, mock_get_settings, mock_calculate_lines):
        """Test that termination has priority over skipping"""
        mock_git_provider = Mock()
        # PR has [no_bots] AND is large
        mock_git_provider.get_pr_description_full.return_value = "This PR has [no_bots] and is large"
        mock_calculate_lines.return_value = 1500

        mock_get_settings.return_value = {
            "pr_filters": {
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }

        result = check_pr_filters(mock_git_provider, "review")

        # Should terminate due to [no_bots], not due to size
        assert result.should_skip == False
        assert result.should_terminate == True
        assert "[nobots] found" in result.reason
        assert "PR too large" not in result.reason

    @patch('pr_agent.algo.pr_filters.calculate_total_lines_changed')
    @patch('pr_agent.algo.pr_filters.get_settings')
    def test_large_pr_with_comment_posting(self, mock_get_settings, mock_calculate_lines):
        """Test that large PR termination includes comment posting requirement"""
        mock_git_provider = Mock()
        mock_git_provider.get_pr_description_full.return_value = "Normal description"
        mock_calculate_lines.return_value = 2000

        mock_get_settings.return_value = {
            "pr_filters": {
                "max_lines_changed": 1000,
                "terminate_on_no_bots": False
            }
        }

        result = check_pr_filters(mock_git_provider, "review")

        assert result.should_terminate == True
        # The reason should indicate this terminates the entire job
        assert "PR too large" in result.reason
