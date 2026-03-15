import os
import base64
import difflib
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List
from datetime import datetime
from urllib.parse import quote
import logging
from jinja2.sandbox import SandboxedEnvironment

logger = logging.getLogger(__name__)

class AzurePipelineConfigService:
    """Service for managing Azure DevOps Pipeline configuration files"""

    AIOHTTP_TIMEOUT = aiohttp.ClientTimeout(total=30)
    SHARED_PIPELINE_REPO_NAME = os.getenv("PR_AGENT_AZDO_SHARED_PIPELINE_REPO", "pr-agent-pipelines")

    def __init__(self):
        pass

    @staticmethod
    def _build_headers(token: str) -> dict:
        """Build Azure DevOps API auth headers."""
        return {
            'Authorization': f'Basic {base64.b64encode(f":{token}".encode()).decode()}',
            'Content-Type': 'application/json'
        }

    def _validate_and_parse(self, repo_data: Dict[str, Any]) -> tuple:
        """Validate repo_data and parse Azure DevOps URL. Returns (org, project, repo, token) or raises ValueError."""
        provider = repo_data.get('provider', '')
        if provider != 'azure_devops':
            raise ValueError('Not an Azure DevOps repository')

        token = repo_data.get('azure_pat', '')
        if not token or not token.strip():
            raise ValueError('Azure DevOps PAT is required')

        org_info = self._parse_azure_repo_url(repo_data.get('url', ''))
        if not org_info['success']:
            raise ValueError(org_info['error'])

        organization = quote(org_info['organization'], safe='')
        project = quote(org_info['project'], safe='')
        repository = quote(org_info['repository'], safe='')

        return organization, project, repository, token

    @staticmethod
    def _new_shared_setup_steps() -> List[Dict[str, str]]:
        """Create canonical setup step list for shared pipeline provisioning."""
        return [
            {"id": "check_shared_pipeline_repo", "label": "Checking for shared pipeline repo", "status": "pending", "detail": ""},
            {"id": "check_yaml_update", "label": "Checking for YAML update", "status": "pending", "detail": ""},
            {"id": "create_shared_pipeline_repo", "label": "Creating shared pipeline repo if needed", "status": "pending", "detail": ""},
            {"id": "update_shared_yaml", "label": "Updating shared pipeline YAML if needed", "status": "pending", "detail": ""},
            {"id": "wait_pipeline_available", "label": "Waiting until the pipeline is available", "status": "pending", "detail": ""},
        ]

    @staticmethod
    def _set_step(steps: List[Dict[str, str]], step_id: str, status: str, detail: str = "") -> None:
        """Update status/detail for a specific setup step id."""
        for step in steps:
            if step.get("id") == step_id:
                step["status"] = status
                if detail:
                    step["detail"] = detail
                return

    @staticmethod
    def _shared_cleanup_plan() -> List[str]:
        """Declarative rollback policy for shared setup failures."""
        return [
            "If this run created a new shared pipeline repo and setup later fails, delete that repo.",
            "If this run created a new shared pipeline definition and setup later fails, delete that pipeline.",
            "Never delete pre-existing shared repos or pipelines that existed before this run.",
        ]

    async def check_azure_pipeline_config(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check if repository has Azure DevOps Pipeline configuration"""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'exists': False, 'error': str(e)}
            
            # Check for pipeline definitions via Azure DevOps API
            pipeline_info = await self._check_pipeline_definitions(organization, project, repository, token)
            
            # Check for azure-pipelines.yml file in repository
            yaml_file_info = await self._get_file_content(organization, project, repository, 'azure-pipelines.yml', token)
            
            return {
                'exists': pipeline_info['has_pipelines'] or yaml_file_info['exists'],
                'pipeline_definitions': pipeline_info,
                'yaml_file': yaml_file_info,
                'organization': organization,
                'project': project,
                'repository': repository,
                'project_url': f"https://dev.azure.com/{organization}/{project}",
                'pipelines_url': f"https://dev.azure.com/{organization}/{project}/_build"
            }
            
        except Exception as e:
            logger.error(f"Error checking Azure Pipeline config: {e}")
            return {
                'exists': False,
                'error': f'Failed to check Pipeline configuration: {str(e)}'
            }

    async def _get_file_content(self, organization: str, project: str, repository: str, path: str, token: str) -> Dict[str, Any]:
        """Get file content from Azure DevOps repository"""
        try:
            headers = self._build_headers(token)
            
            # Get file content via Azure DevOps REST API
            url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/items?path={path}&api-version=7.1-preview.1"
            
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        content = await response.text()
                        return {
                            'exists': True,
                            'content': content,
                            'path': path
                        }
                    elif response.status == 404:
                        return {
                            'exists': False,
                            'error': 'File not found'
                        }
                    elif response.status in (203, 401):
                        return {
                            'exists': False,
                            'error': 'Authentication failed. Check your Azure DevOps PAT.'
                        }
                    else:
                        return {
                            'exists': False,
                            'error': f'Azure DevOps API error: {response.status}'
                        }
                        
        except Exception as e:
            logger.error(f"Error fetching file content: {e}")
            return {
                'exists': False,
                'error': f'Failed to fetch file: {str(e)}'
            }

    async def _check_pipeline_definitions(self, organization: str, project: str, repository: str, token: str) -> Dict[str, Any]:
        """Check for pipeline definitions in Azure DevOps project"""
        try:
            headers = self._build_headers(token)
            
            # Get build definitions (pipelines) for the project
            url = f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions?api-version=7.1-preview.7"
            
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        definitions = data.get('value', [])
                        
                        # Filter pipelines that use this repository
                        repo_pipelines = []
                        for definition in definitions:
                            # Check if this pipeline uses our repository
                            repo_info = definition.get('repository', {})
                            if repo_info.get('name') == repository or repo_info.get('id') == repository:
                                repo_pipelines.append({
                                    'id': definition.get('id'),
                                    'name': definition.get('name'),
                                    'path': definition.get('path', '\\'),
                                    'type': definition.get('type', 'build'),
                                    'url': definition.get('_links', {}).get('web', {}).get('href', ''),
                                    'queue_status': definition.get('queueStatus', 'enabled'),
                                    'trigger_info': self._extract_trigger_info(definition)
                                })
                        
                        return {
                            'has_pipelines': len(repo_pipelines) > 0,
                            'pipeline_count': len(repo_pipelines),
                            'pipelines': repo_pipelines
                        }
                    else:
                        return {
                            'has_pipelines': False,
                            'error': f'Azure DevOps API error: {response.status}'
                        }
                        
        except Exception as e:
            logger.error(f"Error checking pipeline definitions: {e}")
            return {
                'has_pipelines': False,
                'error': f'Failed to check pipelines: {str(e)}'
            }

    def _extract_trigger_info(self, definition: Dict[str, Any]) -> Dict[str, Any]:
        """Extract trigger information from pipeline definition"""
        try:
            triggers = definition.get('triggers', [])
            trigger_info = {
                'has_pr_trigger': False,
                'has_ci_trigger': False,
                'pr_branches': [],
                'ci_branches': []
            }
            
            for trigger in triggers:
                trigger_type = trigger.get('triggerType')
                if trigger_type == 'pullRequest':
                    trigger_info['has_pr_trigger'] = True
                    branch_filters = trigger.get('branchFilters', [])
                    trigger_info['pr_branches'] = [
                        f.lstrip('+') for f in branch_filters
                        if isinstance(f, str) and f.startswith('+')
                    ]
                elif trigger_type == 'continuousIntegration':
                    trigger_info['has_ci_trigger'] = True
                    branch_filters = trigger.get('branchFilters', [])
                    trigger_info['ci_branches'] = [
                        f.lstrip('+') for f in branch_filters
                        if isinstance(f, str) and f.startswith('+')
                    ]
            
            return trigger_info
        except Exception as e:
            logger.debug(f"Error extracting trigger info: {e}")
            return {'has_pr_trigger': False, 'has_ci_trigger': False}

    def _parse_azure_repo_url(self, url: str) -> Dict[str, Any]:
        """Parse Azure DevOps repository URL to extract organization, project, and repository"""
        try:
            # Azure DevOps URLs: https://dev.azure.com/org/project/_git/repo
            # Legacy: https://org.visualstudio.com/project/_git/repo
            
            if 'dev.azure.com' in url:
                # Modern format
                parts = url.rstrip('/').split('/')
                if len(parts) >= 6 and '_git' in parts:
                    git_index = parts.index('_git')
                    organization = parts[git_index - 2]
                    project = parts[git_index - 1]
                    repository = parts[git_index + 1] if git_index + 1 < len(parts) else ''
                    
                    return {
                        'success': True,
                        'organization': organization,
                        'project': project,
                        'repository': repository
                    }
            elif 'visualstudio.com' in url:
                # Legacy format
                parts = url.rstrip('/').split('/')
                if len(parts) >= 5 and '_git' in parts:
                    git_index = parts.index('_git')
                    organization = parts[2].split('.')[0]  # Extract from subdomain
                    project = parts[git_index - 1]
                    repository = parts[git_index + 1] if git_index + 1 < len(parts) else ''
                    
                    return {
                        'success': True,
                        'organization': organization,
                        'project': project,
                        'repository': repository
                    }
            
            return {
                'success': False,
                'error': 'Invalid Azure DevOps repository URL format'
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to parse repository URL: {str(e)}'
            }

    async def create_azure_pipeline_config_pr(self, repo_data: Dict[str, Any], config_content: str, db_session=None) -> Dict[str, Any]:
        """Create a PR with Azure Pipeline configuration"""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'success': False, 'error': str(e)}
            
            # Create the PR using Azure DevOps REST API
            pr_result = await self._create_config_pr(organization, project, repository, token, config_content)
            
            # If PR was created successfully and we have a database session, save the PR info
            if pr_result['success'] and db_session:
                try:
                    from models import RepositoryDB
                    db_repo = db_session.query(RepositoryDB).filter(RepositoryDB.id == repo_data.get('id')).first()
                    if db_repo:
                        db_repo.azure_pipeline_config_pr_url = pr_result['pr_url']
                        db_repo.azure_pipeline_config_pr_number = pr_result['pr_number']
                        db_repo.azure_pipeline_config_pr_branch = pr_result['branch_name']
                        db_repo.azure_pipeline_config_pr_status = 'pending'
                        db_session.commit()
                        logger.info(f"Saved Azure Pipeline config PR info for repository {repo_data.get('name')}")
                except Exception as db_error:
                    logger.error(f"Failed to save PR info to database: {db_error}")
                    # Don't fail the whole operation if just the database save fails
            
            return pr_result
            
        except Exception as e:
            logger.error(f"Error creating Azure Pipeline config PR: {e}")
            return {
                'success': False,
                'error': f'Failed to create PR: {str(e)}'
            }

    async def _create_config_pr(self, organization: str, project: str, repository: str, token: str, config_content: str) -> Dict[str, Any]:
        """Create a pull request with the Azure Pipeline configuration"""
        try:
            headers = self._build_headers(token)
            
            # Generate branch name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            branch_name = f"pr-agent-dashboard/azure-pipeline-config-{timestamp}"
            
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                # Get repository info
                repo_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}?api-version=7.0"
                async with session.get(repo_url, headers=headers) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        return {
                            'success': False,
                            'error': f"Failed to get repository info: {error_data.get('message', 'Unknown error')}"
                        }
                    repo_info = await response.json()
                    default_branch = repo_info.get('defaultBranch', 'refs/heads/main').replace('refs/heads/', '')
                
                # Get the latest commit of the default branch
                refs_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/refs?filter=heads/{default_branch}&api-version=7.0"
                async with session.get(refs_url, headers=headers) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        return {
                            'success': False,
                            'error': f"Failed to get branch info: {error_data.get('message', 'Unknown error')}"
                        }
                    refs_data = await response.json()
                    if not refs_data.get('value'):
                        return {
                            'success': False,
                            'error': f"Branch {default_branch} not found"
                        }
                    latest_commit_id = refs_data['value'][0]['objectId']
                
                # Create new branch
                create_ref_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/refs?api-version=7.0"
                branch_data = [{
                    "name": f"refs/heads/{branch_name}",
                    "oldObjectId": "0000000000000000000000000000000000000000",
                    "newObjectId": latest_commit_id
                }]
                
                async with session.post(create_ref_url, headers=headers, json=branch_data) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        return {
                            'success': False,
                            'error': f"Failed to create branch: {error_data.get('message', 'Unknown error')}"
                        }
                
                # After branch is created successfully, try push + PR with cleanup on failure
                try:
                    # Create or update file
                    file_path = 'azure-pipelines.yml'
                    
                    # Check if file exists
                    existing_file_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/items?path={file_path}&version={latest_commit_id}&api-version=7.0"
                    existing_file = None
                    async with session.get(existing_file_url, headers=headers) as response:
                        if response.status == 200:
                            existing_file = await response.text()
                    
                    # Create push with file changes
                    push_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/pushes?api-version=7.0"
                    
                    # Prepare file change
                    change_type = "edit" if existing_file else "add"
                    file_change = {
                        "changeType": change_type,
                        "item": {
                            "path": f"/{file_path}"
                        },
                        "newContent": {
                            "content": config_content,
                            "contentType": "rawtext"
                        }
                    }
                    
                    push_data = {
                        "refUpdates": [{
                            "name": f"refs/heads/{branch_name}",
                            "oldObjectId": latest_commit_id,
                            "newObjectId": "0000000000000000000000000000000000000000"  # Will be calculated by server
                        }],
                        "commits": [{
                            "comment": "Update Azure Pipeline configuration for PR-Agent\n\nThis commit was created automatically via PR Agent Dashboard",
                            "changes": [file_change]
                        }]
                    }
                    
                    async with session.post(push_url, headers=headers, json=push_data) as response:
                        if response.status != 200:
                            error_data = await response.json()
                            raise RuntimeError(f"Failed to create/update file: {error_data.get('message', 'Unknown error')}")
                    
                    # Create pull request
                    pr_data = {
                        "sourceRefName": f"refs/heads/{branch_name}",
                        "targetRefName": f"refs/heads/{default_branch}",
                        "title": "Update Azure Pipeline configuration for PR-Agent",
                        "description": "This PR updates the Azure Pipeline configuration for PR-Agent.\n\nThis PR was created automatically via PR Agent Dashboard.\n\nPlease review the changes and merge when ready."
                    }
                    
                    pr_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/pullrequests?api-version=7.0"
                    async with session.post(pr_url, headers=headers, json=pr_data) as response:
                        if response.status != 201:
                            error_data = await response.json()
                            raise RuntimeError(f"Failed to create pull request: {error_data.get('message', 'Unknown error')}")
                        
                        pr_info = await response.json()
                        return {
                            'success': True,
                            'pr_number': pr_info['pullRequestId'],
                            'pr_url': f"https://dev.azure.com/{organization}/{project}/_git/{repository}/pullrequest/{pr_info['pullRequestId']}",
                            'branch_name': branch_name
                        }

                except Exception as push_pr_error:
                    # Clean up the orphaned branch
                    try:
                        delete_ref_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/refs?api-version=7.0"
                        delete_ref_body = [{"name": f"refs/heads/{branch_name}", "oldObjectId": latest_commit_id, "newObjectId": "0000000000000000000000000000000000000000"}]
                        async with session.post(delete_ref_url, headers=headers, json=delete_ref_body) as del_resp:
                            if del_resp.status in (200, 201):
                                logger.info("Cleaned up orphaned branch %s", branch_name)
                    except Exception as cleanup_err:
                        logger.warning("Failed to clean up orphaned branch %s: %s", branch_name, cleanup_err)
                    raise push_pr_error
                    
        except Exception as e:
            logger.error(f"Error creating config PR: {e}")
            return {
                'success': False,
                'error': f'Failed to create PR: {str(e)}'
            }

    async def check_pr_status(self, repo_data: Dict[str, Any], pr_number: int) -> Dict[str, Any]:
        """Check the status of an Azure DevOps pull request"""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'success': False, 'error': str(e)}
            
            headers = self._build_headers(token)
            
            pr_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/pullrequests/{pr_number}?api-version=7.0"
            
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                async with session.get(pr_url, headers=headers) as response:
                    if response.status == 200:
                        pr_data = await response.json()
                        status = pr_data.get('status', '').lower()
                        
                        # Map Azure DevOps status to our standard format
                        mapped_status = 'pending'
                        if status == 'completed':
                            mapped_status = 'merged'
                        elif status == 'abandoned':
                            mapped_status = 'closed'
                        elif status == 'active':
                            mapped_status = 'active'
                        
                        return {
                            'success': True,
                            'pr_number': pr_data['pullRequestId'],
                            'pr_url': f"https://dev.azure.com/{organization}/{project}/_git/{repository}/pullrequest/{pr_data['pullRequestId']}",
                            'status': mapped_status,
                            'state': status,
                            'title': pr_data['title'],
                            'updated_at': pr_data.get('lastMergeCommit', {}).get('committer', {}).get('date', '')
                        }
                    elif response.status == 404:
                        return {
                            'success': False,
                            'error': 'Pull request not found'
                        }
                    else:
                        error_data = await response.json()
                        return {
                            'success': False,
                            'error': f"Azure DevOps API error: {error_data.get('message', f'HTTP {response.status}')}"
                        }
                        
        except Exception as e:
            logger.error(f"Error checking PR status: {e}")
            return {
                'success': False,
                'error': f'Failed to check PR status: {str(e)}'
            }

    def get_default_config_template(self) -> str:
        """Get the default Azure Pipeline configuration template"""
        return """# Azure Pipeline configuration for PR-Agent
# This pipeline runs PR-Agent tools on pull requests

# Opt out of CI triggers
trigger: none

# Configure PR trigger
pr:
  branches:
    include:
    - '*'
  autoCancel: true
  drafts: false

variables:
  - group: pr_agent

pool:
  vmImage: 'ubuntu-latest'

steps:
- script: |
    echo "Running PR Agent pipeline step"
    
    # Construct PR_URL
    PR_URL="${SYSTEM_COLLECTIONURI}${SYSTEM_TEAMPROJECT}/_git/${BUILD_REPOSITORY_NAME}/pullrequest/${SYSTEM_PULLREQUEST_PULLREQUESTID}"
    echo "PR_URL=$PR_URL"
    
    # Extract organization URL from System.CollectionUri  
    ORG_URL=$(echo "$(System.CollectionUri)" | sed 's/\\/$//') # Remove trailing slash if present
    echo "Organization URL: $ORG_URL"
    
    # Set environment variables for PR-Agent
    export azure_devops__org="$ORG_URL"
    export config__git_provider="azure"
    export azure_devops__pat="$(azure_devops_pat)"
    export openai__key="$(OPENAI_KEY)"
{%- for key, value in env_vars.items() %}
{%- if key not in ['azure_devops__org', 'config__git_provider', 'azure_devops__pat', 'openai__key'] %}
    export {{ key }}="{{ value }}"
{%- endif %}
{%- endfor %}
    
    # Install PR-Agent if not using Docker container
    pip install pr-agent-ai
    
    # Run PR-Agent commands
    pr-agent --pr_url="$PR_URL" describe
    pr-agent --pr_url="$PR_URL" review  
    pr-agent --pr_url="$PR_URL" improve
  displayName: 'Run PR-Agent'
  env:
    azure_devops_pat: $(azure_devops_pat)
    OPENAI_KEY: $(OPENAI_KEY)
{%- for key, value in env_vars.items() %}
{%- if key not in ['azure_devops_pat', 'OPENAI_KEY'] %}
    {{ key }}: {{ value }}
{%- endif %}
{%- endfor %}
"""

    def get_azure_pipeline_env_vars(self) -> List[Dict[str, Any]]:
        """Get list of available environment variables for Azure Pipeline configuration"""
        return [
            {
                "key": "azure_devops_pat",
                "label": "Azure DevOps PAT",
                "description": "Azure DevOps Personal Access Token",
                "type": "secret",
                "category": "Authentication",
                "required": True,
                "secret_name": "azure_devops_pat"
            },
            {
                "key": "OPENAI_KEY", 
                "label": "OpenAI API Key",
                "description": "API key for OpenAI services",
                "type": "secret",
                "category": "AI Services",
                "required": True,
                "secret_name": "OPENAI_KEY"
            },
            {
                "key": "ANTHROPIC_KEY",
                "label": "Anthropic API Key", 
                "description": "API key for Anthropic Claude services",
                "type": "secret",
                "category": "AI Services",
                "required": False,
                "secret_name": "ANTHROPIC_KEY"
            },
            {
                "key": "config__git_provider",
                "label": "Git Provider",
                "description": "Specify the git provider (should be 'azure')",
                "type": "string",
                "category": "Configuration",
                "default": "azure",
                "required": True
            },
            {
                "key": "pr_reviewer__require_tests_review",
                "label": "Require Tests Review",
                "description": "Whether to require test file reviews",
                "type": "boolean", 
                "category": "PR Review",
                "default": "true",
                "required": False
            },
            {
                "key": "pr_code_suggestions__num_code_suggestions",
                "label": "Number of Code Suggestions",
                "description": "Maximum number of code suggestions to provide",
                "type": "integer",
                "category": "Code Suggestions",
                "default": "4",
                "required": False
            },
            {
                "key": "pr_description__publish_description_as_comment",
                "label": "Publish Description as Comment",
                "description": "Whether to publish PR description as a comment",
                "type": "boolean",
                "category": "PR Description", 
                "default": "false",
                "required": False
            },
            {
                "key": "verbosity_level",
                "label": "Verbosity Level",
                "description": "Logging verbosity level (0-2)",
                "type": "integer",
                "category": "Debugging",
                "default": "0",
                "required": False
            }
        ]

    def get_default_env_vars(self) -> Dict[str, str]:
        """Get default environment variables for Azure Pipeline"""
        return {
            "azure_devops_pat": "$(azure_devops_pat)",
            "OPENAI_KEY": "$(OPENAI_KEY)",
            "config__git_provider": "azure"
        }

    def generate_yaml_config(self, env_vars: Dict[str, Any]) -> str:
        """Generate YAML config from environment variables"""
        try:
            # Get the default template
            template_str = self.get_default_config_template()
            
            # If no custom env vars provided, use defaults
            if not env_vars:
                env_vars = self.get_default_env_vars()
            
            # Create Jinja template and render with environment variables
            env = SandboxedEnvironment()
            template = env.from_string(template_str)
            return template.render(env_vars=env_vars)
            
        except Exception as e:
            logger.error(f"Error generating YAML config: {e}")
            # Return template with default env vars on error
            try:
                env = SandboxedEnvironment()
                template = env.from_string(self.get_default_config_template())
                return template.render(env_vars=self.get_default_env_vars())
            except Exception as e2:
                logger.error(f"Fallback template render failed: {e2}")
                # Final fallback - return simple template without variables
                return """# Azure Pipeline configuration for PR-Agent
trigger: none

pr:
  branches:
    include:
    - '*'

variables:
  - group: pr_agent

pool:
  vmImage: 'ubuntu-latest'

steps:
- script: |
    PR_URL="${SYSTEM_COLLECTIONURI}${SYSTEM_TEAMPROJECT}/_git/${BUILD_REPOSITORY_NAME}/pullrequest/${SYSTEM_PULLREQUEST_PULLREQUESTID}"
    export azure_devops__org="$(System.CollectionUri | sed 's/\\/$//') "
    export config__git_provider="azure"
    pip install pr-agent-ai
    pr-agent --pr_url="$PR_URL" describe
    pr-agent --pr_url="$PR_URL" review
    pr-agent --pr_url="$PR_URL" improve
  displayName: 'Run PR-Agent'
  env:
    azure_devops_pat: $(azure_devops_pat)
    OPENAI_KEY: $(OPENAI_KEY)
"""

    # ──────────────────────────────────────────────────────────────
    #  Template selection & sync status
    # ──────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_pipeline_image_tag(pr_agent_image: str) -> str:
        """Normalize configured image to :latest for pipeline YAML usage."""
        image = (pr_agent_image or "").strip()
        if not image:
            return ""
        if "@sha256:" in image:
            return image
        last_slash = image.rfind("/")
        last_colon = image.rfind(":")
        if last_colon > last_slash:
            return f"{image[:last_colon]}:latest"
        return f"{image}:latest"

    def get_docker_pipeline_template(self, pool_name: str = "PRAgent_Cloud", pr_agent_image: str = "",
                                      gcs_bucket: str = "", gcs_prefix: str = "",
                                      dashboard_url: str = "") -> str:
        """Return the Docker-based pipeline YAML with pool name filled in.

        Non-secret backend config (image, GCS bucket, dashboard URL) is baked
        into the YAML variables so the pipeline does not depend on the VM env
        file being readable by the agent process.
        """
        configured_image = self._normalize_pipeline_image_tag(pr_agent_image)
        escaped_image = configured_image.replace("'", "''")

        extra_vars = ""
        if escaped_image:
            extra_vars += f"- name: PR_AGENT_IMAGE\n  value: '{escaped_image}'\n"
        if gcs_bucket:
            extra_vars += f"- name: PR_AGENT_CONFIG_GCS_BUCKET\n  value: '{gcs_bucket}'\n"
        if gcs_prefix:
            extra_vars += f"- name: PR_AGENT_CONFIG_GCS_PREFIX\n  value: '{gcs_prefix}'\n"
        if dashboard_url:
            extra_vars += f"- name: DASHBOARD_URL\n  value: '{dashboard_url}'\n"
        return f"""# PR-Agent on a self-hosted runner using Docker
# Auto-managed by PR-Agent Dashboard - do not edit manually
trigger: none

pr:
  branches:
    include: ['*']

pool:
  name: '{pool_name}'
  demands:
  - agent.os -equals Linux

variables:
- name: PYTHONUTF8
  value: 1
{extra_vars}

stages:
- stage: pr_agent
  displayName: 'PR-Agent'

  jobs:
  - job: run_agent
    displayName: 'Run PR-Agent tools'
    timeoutInMinutes: 45

    steps:
    - checkout: self
      clean: true
      persistCredentials: true
      displayName: 'Checkout'

    - bash: |
        set -e
        # Save pipeline-level variables (baked by dashboard) before sourcing VM env.
        _PIPELINE_IMAGE="${{PR_AGENT_IMAGE_OVERRIDE:-}}"
        _PIPELINE_GCS_BUCKET="${{PR_AGENT_CONFIG_GCS_BUCKET:-}}"
        _PIPELINE_GCS_PREFIX="${{PR_AGENT_CONFIG_GCS_PREFIX:-}}"
        _PIPELINE_DASHBOARD_URL="${{DASHBOARD_URL:-}}"

        # Source VM env (best-effort, may not be readable by agent user).
        source /opt/pr-agent-runner/env 2>/dev/null || true

        # Pipeline variables take precedence over VM env; fall back to VM values.
        IMAGE="${{_PIPELINE_IMAGE:-${{GCP_RUNNER_PR_AGENT_IMAGE:-}}}}"
        case "$IMAGE" in
          '$('*')') IMAGE="" ;;
        esac
        if [ -z "$IMAGE" ]; then
          echo "##vso[task.logissue type=error]No PR-Agent image found. Set PR_AGENT_IMAGE pipeline variable or re-provision the runner."
          exit 1
        fi
        if echo "$IMAGE" | grep -q '[A-Z]'; then
          echo "##vso[task.logissue type=error]Invalid PR-Agent image '$IMAGE'. Docker image names must be lowercase."
          exit 1
        fi

        if echo "$IMAGE" | grep -q "docker.pkg.dev"; then
          REGISTRY=$(echo "$IMAGE" | cut -d/ -f1)
          TOKEN=$(curl -s -H "Metadata-Flavor: Google" \\
            "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \\
            | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
          echo "$TOKEN" | docker login -u oauth2accesstoken --password-stdin "https://$REGISTRY"
        fi

        docker pull "$IMAGE"

        echo "##vso[task.setvariable variable=RESOLVED_IMAGE]$IMAGE"
        echo "##vso[task.setvariable variable=VM_GCS_BUCKET]${{_PIPELINE_GCS_BUCKET:-${{PR_AGENT_CONFIG_GCS_BUCKET:-}}}}"
        echo "##vso[task.setvariable variable=VM_GCS_PREFIX]${{_PIPELINE_GCS_PREFIX:-${{PR_AGENT_CONFIG_GCS_PREFIX:-}}}}"
        echo "##vso[task.setvariable variable=VM_DASHBOARD_URL]${{_PIPELINE_DASHBOARD_URL:-${{DASHBOARD_URL:-}}}}"
      displayName: 'Pull image & load VM config'
      env:
        PR_AGENT_IMAGE_OVERRIDE: $(PR_AGENT_IMAGE)

    - bash: |
        docker run --rm \\
          --network=host \\
          --entrypoint python3 \\
          -v "${{SOURCE_DIR}}:${{SOURCE_DIR}}" \\
          -w "${{SOURCE_DIR}}" \\
          -e BUILD_REASON \\
          -e SYSTEM_PULLREQUEST_PULLREQUESTID \\
          -e SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI \\
          -e SYSTEM_TEAMPROJECT \\
          -e BUILD_REPOSITORY_NAME \\
          -e SYSTEM_COLLECTIONURI \\
          -e AZURE_DEVOPS_PAT \\
          -e SYSTEM_ACCESSTOKEN \\
          -e DASHBOARD_URL \\
          -e DASHBOARD_API_KEY \\
          -e PR_AGENT_CONFIG_GCS_BUCKET \\
          -e PR_AGENT_CONFIG_GCS_PREFIX \\
          -e PYTHONUTF8=1 \\
          "${{RESOLVED_IMAGE}}" \\
          -m pr_agent.servers.azuredevops_pipeline_runner
      displayName: 'Execute PR-Agent'
      env:
        SOURCE_DIR: $(Build.SourcesDirectory)
        RESOLVED_IMAGE: $(RESOLVED_IMAGE)
        BUILD_REASON: $(Build.Reason)
        SYSTEM_PULLREQUEST_PULLREQUESTID: $(System.PullRequest.PullRequestId)
        SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI: $(System.PullRequest.SourceRepositoryUri)
        SYSTEM_TEAMPROJECT: $(System.TeamProject)
        BUILD_REPOSITORY_NAME: $(Build.Repository.Name)
        SYSTEM_COLLECTIONURI: $(System.CollectionUri)
        AZURE_DEVOPS_PAT: $(AZURE_DEVOPS_PAT)
        SYSTEM_ACCESSTOKEN: $(System.AccessToken)
        DASHBOARD_URL: $(VM_DASHBOARD_URL)
        DASHBOARD_API_KEY: $(DASHBOARD_API_KEY)
        PR_AGENT_CONFIG_GCS_BUCKET: $(VM_GCS_BUCKET)
        PR_AGENT_CONFIG_GCS_PREFIX: $(VM_GCS_PREFIX)
"""

    def get_canonical_template(self, repo_data: Dict[str, Any], db_session=None) -> str:
        """Select the right pipeline template based on runner configuration."""
        pool_name = None
        uses_docker = False
        configured_image = ""

        if db_session:
            try:
                from models import ActionRunnerConnectionDB, RepositoryDB
                conn_id = repo_data.get('action_runner_connection_id')
                if not conn_id:
                    db_repo = db_session.query(RepositoryDB).filter(
                        RepositoryDB.id == repo_data.get('id')
                    ).first()
                    if db_repo:
                        conn_id = db_repo.action_runner_connection_id
                if conn_id:
                    conn = db_session.query(ActionRunnerConnectionDB).filter(
                        ActionRunnerConnectionDB.id == conn_id
                    ).first()
                    if conn and conn.agent_pool:
                        pool_name = conn.agent_pool
            except Exception as e:
                logger.debug(f"Could not look up runner connection: {e}")

        try:
            from config import settings
            configured_image = (getattr(settings, 'gcp_runner_pr_agent_image', '') or '').strip()
            if configured_image:
                uses_docker = True
        except Exception:
            pass

        gcs_bucket = ""
        gcs_prefix = ""
        dashboard_url = ""
        try:
            from config import settings as _s
            gcs_bucket = (getattr(_s, 'pr_agent_config_gcs_bucket', '') or '').strip()
            gcs_prefix = (getattr(_s, 'pr_agent_config_gcs_prefix', '') or '').strip()
            dashboard_url = (getattr(_s, 'backend_base_url', '') or '').strip()
        except Exception:
            pass

        if uses_docker and pool_name:
            return self.get_docker_pipeline_template(pool_name, configured_image,
                                                     gcs_bucket, gcs_prefix,
                                                     dashboard_url)
        elif uses_docker:
            return self.get_docker_pipeline_template(pr_agent_image=configured_image,
                                                     gcs_bucket=gcs_bucket, gcs_prefix=gcs_prefix,
                                                     dashboard_url=dashboard_url)
        else:
            return self.generate_yaml_config(self.get_default_env_vars())

    @staticmethod
    def _normalize_yaml(content: str) -> str:
        """Strip comments, blank lines, trailing whitespace for comparison."""
        lines = []
        for line in content.splitlines():
            stripped = line.rstrip()
            if stripped and not stripped.lstrip().startswith('#'):
                lines.append(stripped)
        return '\n'.join(lines)

    async def get_sync_status(self, repo_data: Dict[str, Any], db_session=None) -> Dict[str, Any]:
        """Compare deployed pipeline YAML against canonical template."""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'error': str(e)}

            use_shared = os.getenv("PR_AGENT_AZDO_USE_SHARED_PIPELINE_REPO", "true").strip().lower() in ("1", "true", "yes", "on")
            canonical = self.get_canonical_template(repo_data, db_session)
            headers = self._build_headers(token)
            expected_plain_vars = self._get_expected_pipeline_plain_variables()
            required_plain_keys = list(expected_plain_vars.keys())
            required_secret_keys = ["AZURE_DEVOPS_PAT", "DASHBOARD_API_KEY"]

            if use_shared:
                shared_repo = self.SHARED_PIPELINE_REPO_NAME
                async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                    # Resolve shared repository details.
                    repo_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{shared_repo}?api-version=7.0"
                    async with session.get(repo_url, headers=headers) as repo_resp:
                        if repo_resp.status == 404:
                            return {
                                'yaml_exists': False,
                                'pipeline_exists': False,
                                'sync_status': 'missing',
                                'remote_content': None,
                                'canonical_content': canonical,
                                'diff_lines_changed': 0,
                                'pipeline_definitions': [],
                                'organization': organization,
                                'project': project,
                                'repository': repository,
                                'shared_pipeline_repo': shared_repo,
                                'using_shared_pipeline_repo': True,
                                'pipelines_url': f"https://dev.azure.com/{organization}/{project}/_build",
                                'variables_status': {
                                    'required_plain_keys': required_plain_keys,
                                    'required_secret_keys': required_secret_keys,
                                    'missing_any': True,
                                    'pipelines_checked': 0,
                                    'pipelines': [],
                                },
                                'needs_update': True,
                            }
                        if repo_resp.status != 200:
                            msg = await repo_resp.text()
                            return {'error': f"Failed to resolve shared pipeline repository: {msg}"}
                        shared_repo_info = await repo_resp.json()

                    shared_repo_id = shared_repo_info.get("id")
                    shared_repo_web_url = shared_repo_info.get("webUrl")
                    if not shared_repo_id:
                        return {'error': 'Shared pipeline repository id was not found'}

                    yaml_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{shared_repo}/items?path=azure-pipelines.yml&api-version=7.1-preview.1"
                    remote = None
                    async with session.get(yaml_url, headers=headers) as yaml_resp:
                        if yaml_resp.status == 200:
                            remote = await yaml_resp.text()
                        elif yaml_resp.status != 404:
                            msg = await yaml_resp.text()
                            return {'error': f"Failed to read shared pipeline YAML: {msg}"}

                    defs_url = f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions?api-version=7.1-preview.7"
                    shared_defs = []
                    async with session.get(defs_url, headers=headers) as defs_resp:
                        if defs_resp.status == 200:
                            defs = (await defs_resp.json()).get("value", [])
                            for d in defs:
                                r = d.get("repository", {})
                                if (r.get("name") == shared_repo or r.get("id") == shared_repo_id) and \
                                   d.get("process", {}).get("yamlFilename", "") == "azure-pipelines.yml":
                                    shared_defs.append({
                                        'id': d.get('id'),
                                        'name': d.get('name'),
                                        'path': d.get('path', '\\'),
                                        'type': d.get('type', 'build'),
                                        'url': d.get('_links', {}).get('web', {}).get('href', ''),
                                        'queue_status': d.get('queueStatus', 'enabled'),
                                        'trigger_info': self._extract_trigger_info(d),
                                    })
                    variables_status = await self._collect_pipeline_variables_status(
                        session=session,
                        headers=headers,
                        organization=organization,
                        project=project,
                        pipeline_defs=shared_defs,
                        required_plain_keys=required_plain_keys,
                        required_secret_keys=required_secret_keys,
                    )

                if remote is None:
                    needs_update = True
                    return {
                        'yaml_exists': False,
                        'pipeline_exists': len(shared_defs) > 0,
                        'sync_status': 'missing',
                        'remote_content': None,
                        'canonical_content': canonical,
                        'diff_lines_changed': 0,
                        'pipeline_definitions': shared_defs,
                        'organization': organization,
                        'project': project,
                        'repository': repository,
                        'shared_pipeline_repo': shared_repo,
                        'shared_pipeline_repo_url': shared_repo_web_url,
                        'using_shared_pipeline_repo': True,
                        'pipelines_url': f"https://dev.azure.com/{organization}/{project}/_build",
                        'variables_status': variables_status,
                        'needs_update': needs_update,
                    }

                norm_remote = self._normalize_yaml(remote)
                norm_canonical = self._normalize_yaml(canonical)
                if norm_remote == norm_canonical:
                    sync_status = 'up_to_date'
                    diff_count = 0
                else:
                    sync_status = 'outdated'
                    diff = list(difflib.unified_diff(
                        norm_remote.splitlines(), norm_canonical.splitlines(), lineterm=''
                    ))
                    diff_count = sum(1 for l in diff if (l.startswith('+') or l.startswith('-')) and not l.startswith('---') and not l.startswith('+++'))

                needs_update = (sync_status != 'up_to_date') or bool(variables_status.get('missing_any'))
                return {
                    'yaml_exists': True,
                    'pipeline_exists': len(shared_defs) > 0,
                    'sync_status': sync_status,
                    'remote_content': remote,
                    'canonical_content': canonical,
                    'diff_lines_changed': diff_count,
                    'pipeline_definitions': shared_defs,
                    'organization': organization,
                    'project': project,
                    'repository': repository,
                    'shared_pipeline_repo': shared_repo,
                    'shared_pipeline_repo_url': shared_repo_web_url,
                    'using_shared_pipeline_repo': True,
                    'pipelines_url': f"https://dev.azure.com/{organization}/{project}/_build",
                    'variables_status': variables_status,
                    'needs_update': needs_update,
                }

            yaml_file = await self._get_file_content(
                organization, project, repository, 'azure-pipelines.yml', token
            )
            pipeline_info = await self._check_pipeline_definitions(
                organization, project, repository, token
            )

            if not yaml_file['exists']:
                if yaml_file.get('error') and yaml_file['error'] != 'File not found':
                    return {'error': f"Failed to check YAML file: {yaml_file['error']}"}
                variables_status = {
                    'required_plain_keys': required_plain_keys,
                    'required_secret_keys': required_secret_keys,
                    'missing_any': True,
                    'pipelines_checked': 0,
                    'pipelines': [],
                }
                return {
                    'yaml_exists': False,
                    'pipeline_exists': pipeline_info.get('has_pipelines', False),
                    'sync_status': 'missing',
                    'remote_content': None,
                    'canonical_content': canonical,
                    'diff_lines_changed': 0,
                    'pipeline_definitions': pipeline_info.get('pipelines', []),
                    'organization': organization,
                    'project': project,
                    'repository': repository,
                    'using_shared_pipeline_repo': False,
                    'pipelines_url': f"https://dev.azure.com/{organization}/{project}/_build",
                    'variables_status': variables_status,
                    'needs_update': True,
                }

            remote = yaml_file['content']
            norm_remote = self._normalize_yaml(remote)
            norm_canonical = self._normalize_yaml(canonical)

            if norm_remote == norm_canonical:
                sync_status = 'up_to_date'
                diff_count = 0
            else:
                sync_status = 'outdated'
                diff = list(difflib.unified_diff(
                    norm_remote.splitlines(), norm_canonical.splitlines(), lineterm=''
                ))
                diff_count = sum(1 for l in diff if (l.startswith('+') or l.startswith('-')) and not l.startswith('---') and not l.startswith('+++'))

            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                variables_status = await self._collect_pipeline_variables_status(
                    session=session,
                    headers=headers,
                    organization=organization,
                    project=project,
                    pipeline_defs=pipeline_info.get('pipelines', []),
                    required_plain_keys=required_plain_keys,
                    required_secret_keys=required_secret_keys,
                )

            needs_update = (sync_status != 'up_to_date') or bool(variables_status.get('missing_any'))
            return {
                'yaml_exists': True,
                'pipeline_exists': pipeline_info.get('has_pipelines', False),
                'sync_status': sync_status,
                'remote_content': remote,
                'canonical_content': canonical,
                'diff_lines_changed': diff_count,
                'pipeline_definitions': pipeline_info.get('pipelines', []),
                'organization': organization,
                'project': project,
                'repository': repository,
                'using_shared_pipeline_repo': False,
                'pipelines_url': f"https://dev.azure.com/{organization}/{project}/_build",
                'variables_status': variables_status,
                'needs_update': needs_update,
            }

        except Exception as e:
            logger.error(f"Error getting sync status: {e}")
            return {'error': f'Failed to get sync status: {str(e)}'}

    # ──────────────────────────────────────────────────────────────
    #  Direct push (no PR)
    # ──────────────────────────────────────────────────────────────

    async def push_yaml_direct(self, repo_data: Dict[str, Any], content: str = None, db_session=None) -> Dict[str, Any]:
        """Push azure-pipelines.yml directly to the default branch and ensure a pipeline definition exists."""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'success': False, 'error': str(e)}

            if not content:
                content = self.get_canonical_template(repo_data, db_session)

            # Preferred scalable path: shared repo + shared pipeline definition.
            # This avoids per-repo branch policy issues and keeps one canonical pipeline YAML.
            try_shared_first = os.getenv("PR_AGENT_AZDO_USE_SHARED_PIPELINE_REPO", "true").strip().lower() in ("1", "true", "yes", "on")
            if try_shared_first:
                shared_result = await self._ensure_shared_pipeline_definition(organization, project, token, content, repo_data)
                if shared_result.get("success"):
                    return {
                        "success": True,
                        "yaml_pushed": bool(shared_result.get("yaml_pushed")),
                        "yaml_up_to_date": bool(shared_result.get("yaml_up_to_date")),
                        "pipeline_created": bool(shared_result.get("pipeline_created")),
                        "pipeline_id": shared_result.get("pipeline_id"),
                        "shared_pipeline_repo": shared_result.get("shared_repo_name"),
                        "shared_pipeline_repo_url": shared_result.get("shared_repo_web_url"),
                        "setup_steps": shared_result.get("setup_steps", []),
                        "cleanup_plan": shared_result.get("cleanup_plan", []),
                        "cleanup": shared_result.get("cleanup", {"attempted": False, "actions": []}),
                        "secret_variables": shared_result.get("secret_variables"),
                        "pipeline_create_error": None,
                    }
                logger.warning("Shared pipeline setup failed; falling back to direct repo push path: %s", shared_result.get("error"))

            headers = self._build_headers(token)

            yaml_pushed = False
            pipeline_created = False
            pipeline_id = None
            push_blocked_by_policy = False
            push_block_error = None

            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                # Get repo info for default branch
                repo_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}?api-version=7.0"
                async with session.get(repo_url, headers=headers) as resp:
                    if resp.status != 200:
                        try:
                            err = await resp.json()
                            msg = err.get('message', str(resp.status))
                        except Exception:
                            msg = await resp.text() or str(resp.status)
                        return {'success': False, 'error': f"Failed to get repo info: {msg}"}
                    repo_info = await resp.json()
                    default_branch = repo_info.get('defaultBranch', 'refs/heads/main').replace('refs/heads/', '')
                    repo_guid = repo_info.get('id', '')
                    if not repo_guid:
                        return {'success': False, 'error': 'Could not resolve repository GUID'}

                # Get latest commit on default branch
                refs_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/refs?filter=heads/{default_branch}&api-version=7.0"
                async with session.get(refs_url, headers=headers) as resp:
                    if resp.status != 200:
                        return {'success': False, 'error': 'Failed to get branch ref'}
                    refs_data = await resp.json()
                    if not refs_data.get('value'):
                        return {'success': False, 'error': f'Branch {default_branch} not found'}
                    latest_commit = refs_data['value'][0]['objectId']

                # Check if file already exists
                file_check_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/items?path=azure-pipelines.yml&api-version=7.1-preview.1"
                async with session.get(file_check_url, headers=headers) as resp:
                    change_type = "edit" if resp.status == 200 else "add"

                # Push directly to default branch
                push_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/pushes?api-version=7.0"
                push_data = {
                    "refUpdates": [{
                        "name": f"refs/heads/{default_branch}",
                        "oldObjectId": latest_commit
                    }],
                    "commits": [{
                        "comment": "Update Azure Pipeline configuration for PR-Agent\n\nAuto-managed by PR-Agent Dashboard",
                        "changes": [{
                            "changeType": change_type,
                            "item": {"path": "/azure-pipelines.yml"},
                            "newContent": {"content": content, "contentType": "rawtext"}
                        }]
                    }]
                }
                async with session.post(push_url, headers=headers, json=push_data) as resp:
                    if resp.status in (200, 201):
                        yaml_pushed = True
                    else:
                        try:
                            err = await resp.json()
                            msg = err.get('message', str(resp.status))
                        except Exception:
                            msg = await resp.text() or str(resp.status)
                        msg_l = (msg or "").lower()
                        if "tf402455" in msg_l or "must use a pull request" in msg_l:
                            # Branch is protected from direct pushes.
                            # Continue and try to reuse an existing shared PR-Agent pipeline definition.
                            push_blocked_by_policy = True
                            push_block_error = msg
                            logger.info("Push blocked by branch policy for %s/%s/%s; attempting shared pipeline reuse.",
                                        organization, project, repository)
                        else:
                            return {'success': False, 'error': f"Push failed: {msg}"}

                # Ensure a pipeline definition exists for this repo
                defs_url = f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions?api-version=7.1-preview.7"
                async with session.get(defs_url, headers=headers) as resp:
                    if resp.status == 200:
                        defs = (await resp.json()).get('value', [])
                        for d in defs:
                            r = d.get('repository', {})
                            if (r.get('name') == repository or r.get('id') == repository) and \
                               d.get('process', {}).get('yamlFilename', '') == 'azure-pipelines.yml':
                                pipeline_id = d['id']
                                break

                if not pipeline_id:
                    create_url = f"https://dev.azure.com/{organization}/{project}/_apis/pipelines?api-version=7.0"
                    create_body = {
                        "name": f"PR-Agent ({repository})",
                        "folder": "\\",
                        "configuration": {
                            "type": "yaml",
                            "path": "/azure-pipelines.yml",
                            "repository": {
                                "id": repo_guid,
                                "type": "azureReposGit"
                            }
                        }
                    }
                    async with session.post(create_url, headers=headers, json=create_body) as resp:
                        if resp.status in (200, 201):
                            pipe_data = await resp.json()
                            pipeline_id = pipe_data.get('id')
                            pipeline_created = True
                        else:
                            try:
                                err = await resp.json()
                                pipe_err = err.get('message', str(resp.status))
                            except Exception:
                                pipe_err = await resp.text() or str(resp.status)
                            logger.warning(f"Pipeline definition creation returned {resp.status}: {pipe_err}")

                # If direct push is blocked and repo-specific pipeline is missing, try to reuse
                # an existing PR-Agent pipeline definition from the project.
                if push_blocked_by_policy and not pipeline_id:
                    try:
                        defs_url = f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions?api-version=7.1-preview.7"
                        async with session.get(defs_url, headers=headers) as resp:
                            if resp.status == 200:
                                defs = (await resp.json()).get('value', [])
                                shared = next(
                                    (
                                        d for d in defs
                                        if "pr-agent" in (d.get("name") or "").lower()
                                    ),
                                    None,
                                )
                                if shared:
                                    pipeline_id = shared.get("id")
                                    logger.info("Reusing shared PR-Agent pipeline definition %s for %s/%s/%s",
                                                pipeline_id, organization, project, repository)
                    except Exception as e:
                        logger.warning("Shared pipeline discovery failed: %s", e)

            secret_set_result: Optional[Dict[str, Any]] = None
            if pipeline_id:
                dashboard_api_key = ""
                try:
                    from config import settings as _s
                    dashboard_api_key = (getattr(_s, 'dashboard_api_key', '') or '').strip()
                except Exception:
                    dashboard_api_key = ""
                variables_to_set: Dict[str, Any] = {
                    "AZURE_DEVOPS_PAT": {"value": repo_data.get("azure_pat", ""), "is_secret": True},
                    "DASHBOARD_API_KEY": {"value": dashboard_api_key, "is_secret": True},
                }
                for k, v in self._get_expected_pipeline_plain_variables().items():
                    variables_to_set[k] = {"value": v, "is_secret": False}
                secret_set_result = await self._set_pipeline_definition_variables(
                    organization=organization,
                    project=project,
                    token=token,
                    pipeline_id=pipeline_id,
                    variables_to_set=variables_to_set,
                )

            if push_blocked_by_policy and not pipeline_id:
                # Fall back to PR flow so protected branches can still be updated safely.
                pr_result = await self._create_config_pr(organization, project, repository, token, content)
                if pr_result.get('success'):
                    return {
                        'success': True,
                        'requires_pr_merge': True,
                        'message': (
                            f"Direct push is blocked by branch policy. Created PR #{pr_result.get('pr_number')} "
                            "to add/update azure-pipelines.yml. Merge that PR, then click setup again to attach policy."
                        ),
                        'yaml_pushed': False,
                        'pipeline_created': False,
                        'pipeline_id': None,
                        'pr_number': pr_result.get('pr_number'),
                        'pr_url': pr_result.get('pr_url'),
                        'branch_name': pr_result.get('branch_name'),
                        'push_blocked_by_policy': True,
                        'push_error': push_block_error,
                    }
                return {
                    'success': False,
                    'error': (
                        "Push blocked by branch policy and no reusable PR-Agent pipeline definition was found. "
                        "Automatic PR creation also failed. Create one shared PR-Agent pipeline in this project "
                        "(in any repo), or create/merge azure-pipelines.yml via PR, then retry."
                    ),
                    'push_blocked_by_policy': True,
                    'push_error': push_block_error,
                    'pr_creation_error': pr_result.get('error'),
                }

            has_pipeline = bool(pipeline_created or pipeline_id)
            secret_ok = bool(not secret_set_result or secret_set_result.get('success'))
            return {
                'success': bool(has_pipeline and secret_ok),
                'yaml_pushed': yaml_pushed,
                'pipeline_created': pipeline_created,
                'pipeline_id': pipeline_id,
                'push_blocked_by_policy': push_blocked_by_policy,
                'push_error': push_block_error,
                'secret_variables': secret_set_result,
                'pipeline_create_error': (
                    secret_set_result.get('error')
                    if secret_set_result and not secret_set_result.get('success')
                    else (None if pipeline_created or pipeline_id else 'Pipeline definition could not be created. You may need to create it manually.')
                ),
            }

        except Exception as e:
            logger.error(f"Error in push_yaml_direct: {e}")
            return {'success': False, 'error': str(e)}

    async def _ensure_shared_pipeline_definition(
        self,
        organization: str,
        project: str,
        token: str,
        yaml_content: str,
        repo_data: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create/reuse a shared pipeline repo and pipeline definition for this project."""
        headers = self._build_headers(token)
        shared_repo_name = self.SHARED_PIPELINE_REPO_NAME
        steps = self._new_shared_setup_steps()
        cleanup_plan = self._shared_cleanup_plan()

        created_repo_id = None
        created_pipeline_id = None

        async def _rollback(reason: str) -> Dict[str, Any]:
            actions = []
            if created_pipeline_id:
                pipeline_cleanup = await self._delete_pipeline_definition_internal(
                    organization, project, token, created_pipeline_id
                )
                actions.append({
                    "resource": "pipeline_definition",
                    "id": created_pipeline_id,
                    "success": bool(pipeline_cleanup.get("success")),
                    "detail": pipeline_cleanup.get("error") or pipeline_cleanup.get("message") or "cleanup attempted",
                })
            if created_repo_id:
                repo_cleanup = await self._delete_repository_internal(
                    organization, project, token, created_repo_id
                )
                actions.append({
                    "resource": "shared_pipeline_repo",
                    "id": created_repo_id,
                    "success": bool(repo_cleanup.get("success")),
                    "detail": repo_cleanup.get("error") or repo_cleanup.get("message") or "cleanup attempted",
                })
            return {"reason": reason, "attempted": bool(actions), "actions": actions}

        async def _fail(error_message: str, step_id: Optional[str] = None) -> Dict[str, Any]:
            if step_id:
                self._set_step(steps, step_id, "error", error_message)
            cleanup = await _rollback(error_message)
            return {
                "success": False,
                "error": error_message,
                "setup_steps": steps,
                "cleanup_plan": cleanup_plan,
                "cleanup": cleanup,
            }

        try:
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                # Resolve project id for repository creation.
                project_url = f"https://dev.azure.com/{organization}/_apis/projects/{project}?api-version=7.1"
                async with session.get(project_url, headers=headers) as resp:
                    if resp.status != 200:
                        msg = await resp.text()
                        return await _fail(
                            f"Failed to resolve project for shared pipeline repo: {msg}",
                            "check_shared_pipeline_repo",
                        )
                    project_info = await resp.json()
                    project_id = project_info.get("id")
                    if not project_id:
                        return await _fail(
                            "Failed to resolve project ID for shared pipeline repo",
                            "check_shared_pipeline_repo",
                        )

                # Get/create shared repo.
                repo_info = None
                repo_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{shared_repo_name}?api-version=7.0"
                async with session.get(repo_url, headers=headers) as resp:
                    if resp.status == 200:
                        repo_info = await resp.json()
                        self._set_step(
                            steps,
                            "check_shared_pipeline_repo",
                            "success",
                            f"Found shared repo '{shared_repo_name}'.",
                        )
                        self._set_step(
                            steps,
                            "create_shared_pipeline_repo",
                            "skipped",
                            "Shared repo already exists.",
                        )
                    elif resp.status == 404:
                        self._set_step(
                            steps,
                            "check_shared_pipeline_repo",
                            "success",
                            f"Shared repo '{shared_repo_name}' not found; creating it.",
                        )
                        create_repo_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories?api-version=7.0"
                        create_body = {"name": shared_repo_name, "project": {"id": project_id}}
                        async with session.post(create_repo_url, headers=headers, json=create_body) as c_resp:
                            if c_resp.status not in (200, 201):
                                msg = await c_resp.text()
                                return await _fail(
                                    "Failed to create shared pipeline repo. "
                                    f"Ensure PAT has repository create/push permissions. Azure said: {msg}",
                                    "create_shared_pipeline_repo",
                                )
                            repo_info = await c_resp.json()
                            created_repo_id = repo_info.get("id")
                            self._set_step(
                                steps,
                                "create_shared_pipeline_repo",
                                "success",
                                f"Created shared repo '{shared_repo_name}'.",
                            )
                    else:
                        msg = await resp.text()
                        return await _fail(
                            f"Failed to query shared pipeline repo: {msg}",
                            "check_shared_pipeline_repo",
                        )

                repo_id = repo_info.get("id")
                repo_web_url = repo_info.get("webUrl")
                if not repo_id:
                    return await _fail("Could not resolve shared repo ID", "check_shared_pipeline_repo")

                default_branch = (repo_info.get("defaultBranch") or "refs/heads/main").replace("refs/heads/", "")
                yaml_pushed = False

                # Determine branch head and whether file exists.
                refs_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{shared_repo_name}/refs?filter=heads/{default_branch}&api-version=7.0"
                latest_commit = None
                async with session.get(refs_url, headers=headers) as r_resp:
                    if r_resp.status == 200:
                        refs_data = await r_resp.json()
                        if refs_data.get("value"):
                            latest_commit = refs_data["value"][0].get("objectId")

                change_type = "add"
                file_unchanged = False
                if latest_commit:
                    file_check_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{shared_repo_name}/items?path=azure-pipelines.yml&api-version=7.1-preview.1"
                    async with session.get(file_check_url, headers=headers) as f_resp:
                        if f_resp.status == 200:
                            change_type = "edit"
                            try:
                                existing_yaml = await f_resp.text()
                                if self._normalize_yaml(existing_yaml or "") == self._normalize_yaml(yaml_content or ""):
                                    file_unchanged = True
                            except Exception:
                                file_unchanged = False

                self._set_step(
                    steps,
                    "check_yaml_update",
                    "success",
                    "Shared YAML is up-to-date." if file_unchanged else "Shared YAML needs update.",
                )

                if file_unchanged:
                    self._set_step(
                        steps,
                        "update_shared_yaml",
                        "skipped",
                        "No YAML update needed.",
                    )
                else:
                    push_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{shared_repo_name}/pushes?api-version=7.0"
                    push_data = {
                        "refUpdates": [{
                            "name": f"refs/heads/{default_branch}",
                            "oldObjectId": latest_commit or "0000000000000000000000000000000000000000",
                        }],
                        "commits": [{
                            "comment": "Update shared PR-Agent Azure Pipeline configuration\n\nAuto-managed by PR-Agent Dashboard",
                            "changes": [{
                                "changeType": change_type,
                                "item": {"path": "/azure-pipelines.yml"},
                                "newContent": {"content": yaml_content, "contentType": "rawtext"},
                            }],
                        }],
                    }
                    async with session.post(push_url, headers=headers, json=push_data) as p_resp:
                        if p_resp.status in (200, 201):
                            yaml_pushed = True
                            self._set_step(
                                steps,
                                "update_shared_yaml",
                                "success",
                                "Updated shared pipeline YAML.",
                            )
                        else:
                            msg = await p_resp.text()
                            return await _fail(
                                f"Failed to push shared pipeline YAML to {shared_repo_name}: {msg}",
                                "update_shared_yaml",
                            )

                # Find/create pipeline definition that uses shared repo yaml.
                defs_url = f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions?api-version=7.1-preview.7"
                pipeline_id = None
                async with session.get(defs_url, headers=headers) as d_resp:
                    if d_resp.status == 200:
                        defs = (await d_resp.json()).get("value", [])
                        for d in defs:
                            r = d.get("repository", {})
                            if (r.get("name") == shared_repo_name or r.get("id") == repo_id) and \
                               d.get("process", {}).get("yamlFilename", "") == "azure-pipelines.yml":
                                pipeline_id = d.get("id")
                                break

                pipeline_created = False
                if not pipeline_id:
                    create_url = f"https://dev.azure.com/{organization}/{project}/_apis/pipelines?api-version=7.0"
                    create_body = {
                        "name": "PR-Agent Shared",
                        "folder": "\\",
                        "configuration": {
                            "type": "yaml",
                            "path": "/azure-pipelines.yml",
                            "repository": {
                                "id": repo_id,
                                "type": "azureReposGit",
                            },
                        },
                    }
                    async with session.post(create_url, headers=headers, json=create_body) as c_resp:
                        if c_resp.status in (200, 201):
                            data = await c_resp.json()
                            pipeline_id = data.get("id")
                            created_pipeline_id = pipeline_id
                            pipeline_created = True
                        else:
                            msg = await c_resp.text()
                            return await _fail(
                                f"Failed to create shared PR-Agent pipeline definition: {msg}",
                                "wait_pipeline_available",
                            )

                # Wait for eventual consistency before policy setup.
                self._set_step(
                    steps,
                    "wait_pipeline_available",
                    "in_progress",
                    "Waiting for pipeline definition to be queryable...",
                )
                available = await self._wait_for_pipeline_availability(
                    session, headers, organization, project, int(pipeline_id) if pipeline_id else 0
                )
                if not available:
                    return await _fail(
                        f"Pipeline definition {pipeline_id} was not available in time.",
                        "wait_pipeline_available",
                    )
                self._set_step(
                    steps,
                    "wait_pipeline_available",
                    "success",
                    "Pipeline definition is available.",
                )

                dashboard_api_key = ""
                if repo_data:
                    try:
                        from config import settings as _s
                        dashboard_api_key = (getattr(_s, 'dashboard_api_key', '') or '').strip()
                    except Exception:
                        dashboard_api_key = ""
                variables_to_set: Dict[str, Any] = {
                    "AZURE_DEVOPS_PAT": {"value": (repo_data or {}).get("azure_pat", ""), "is_secret": True},
                    "DASHBOARD_API_KEY": {"value": dashboard_api_key, "is_secret": True},
                }
                for k, v in self._get_expected_pipeline_plain_variables().items():
                    variables_to_set[k] = {"value": v, "is_secret": False}
                secret_set_result = await self._set_pipeline_definition_variables(
                    organization=organization,
                    project=project,
                    token=token,
                    pipeline_id=pipeline_id,
                    variables_to_set=variables_to_set,
                )
                if not secret_set_result.get("success"):
                    return await _fail(
                        secret_set_result.get("error") or "Failed to set pipeline secret variables",
                        "wait_pipeline_available",
                    )

                return {
                    "success": True,
                    "pipeline_id": pipeline_id,
                    "pipeline_created": pipeline_created,
                    "yaml_pushed": yaml_pushed,
                    "yaml_up_to_date": file_unchanged,
                    "shared_repo_name": shared_repo_name,
                    "shared_repo_web_url": repo_web_url,
                    "secret_variables": secret_set_result,
                    "setup_steps": steps,
                    "cleanup_plan": cleanup_plan,
                    "cleanup": {"attempted": False, "actions": []},
                }
        except Exception as e:
            return await _fail(str(e))

    def _get_expected_pipeline_plain_variables(self) -> Dict[str, str]:
        """Return plain-text pipeline variables expected from dashboard runtime settings."""
        values: Dict[str, str] = {}
        try:
            from config import settings as _s
            image = self._normalize_pipeline_image_tag((getattr(_s, 'gcp_runner_pr_agent_image', '') or '').strip())
            gcs_bucket = (getattr(_s, 'pr_agent_config_gcs_bucket', '') or '').strip()
            gcs_prefix = (getattr(_s, 'pr_agent_config_gcs_prefix', '') or '').strip()
            dashboard_url = (getattr(_s, 'backend_base_url', '') or '').strip()
            if image:
                values["PR_AGENT_IMAGE"] = image
            if gcs_bucket:
                values["PR_AGENT_CONFIG_GCS_BUCKET"] = gcs_bucket
            if gcs_prefix:
                values["PR_AGENT_CONFIG_GCS_PREFIX"] = gcs_prefix
            if dashboard_url:
                values["DASHBOARD_URL"] = dashboard_url
        except Exception:
            pass
        return values

    async def _collect_pipeline_variables_status(
        self,
        session: aiohttp.ClientSession,
        headers: Dict[str, str],
        organization: str,
        project: str,
        pipeline_defs: List[Dict[str, Any]],
        required_plain_keys: List[str],
        required_secret_keys: List[str],
    ) -> Dict[str, Any]:
        """Inspect build definitions and report missing required plain/secret variables."""
        pipelines = []
        missing_any = False
        for p in (pipeline_defs or []):
            pipeline_id = p.get("id")
            if not pipeline_id:
                continue
            definition_url = (
                f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions/"
                f"{pipeline_id}?api-version=7.1-preview.7"
            )
            variables: Dict[str, Any] = {}
            fetch_error = None
            try:
                async with session.get(definition_url, headers=headers) as resp:
                    if resp.status == 200:
                        definition = await resp.json()
                        raw_vars = definition.get("variables")
                        if isinstance(raw_vars, dict):
                            variables = raw_vars
                    else:
                        fetch_error = f"Failed to fetch definition variables ({resp.status})"
            except Exception as e:
                fetch_error = str(e)

            missing_plain = [k for k in required_plain_keys if k not in variables]
            invalid_plain = []
            for k in required_plain_keys:
                if k not in variables:
                    continue
                raw_var = variables.get(k)
                raw_value = raw_var.get("value") if isinstance(raw_var, dict) else raw_var
                if raw_value is None:
                    invalid_plain.append(k)
                    continue
                if isinstance(raw_value, str) and not raw_value.strip():
                    invalid_plain.append(k)
            missing_secret = [k for k in required_secret_keys if k not in variables]
            has_missing = bool(missing_plain or invalid_plain or missing_secret or fetch_error)
            missing_any = missing_any or has_missing
            pipelines.append({
                "pipeline_id": pipeline_id,
                "pipeline_name": p.get("name"),
                "missing_plain_keys": missing_plain,
                "invalid_plain_keys": invalid_plain,
                "missing_secret_keys": missing_secret,
                "variables_found_count": len(variables),
                "variables_fetch_error": fetch_error,
                "has_missing_required": has_missing,
            })

        return {
            "required_plain_keys": required_plain_keys,
            "required_secret_keys": required_secret_keys,
            "missing_any": missing_any or len(pipelines) == 0,
            "pipelines_checked": len(pipelines),
            "pipelines": pipelines,
        }

    async def _set_pipeline_definition_variables(
        self,
        organization: str,
        project: str,
        token: str,
        pipeline_id: int,
        variables_to_set: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge variables into a build definition and persist via PUT.
        variables_to_set value supports:
          - "value" (str)
          - "is_secret" (bool)
        """
        if not pipeline_id:
            return {"success": False, "error": "Pipeline ID is required", "pipeline_id": pipeline_id}

        filtered_variables = {}
        for key, entry in (variables_to_set or {}).items():
            if not isinstance(entry, dict):
                continue
            value = entry.get("value")
            if not isinstance(value, str) or not value.strip():
                continue
            filtered_variables[key] = {
                "value": value,
                "is_secret": bool(entry.get("is_secret", False)),
            }
        if not filtered_variables:
            return {
                "success": True,
                "pipeline_id": pipeline_id,
                "updated_keys": [],
                "message": "No non-empty variables provided",
            }

        headers = self._build_headers(token)
        definition_url = (
            f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions/"
            f"{pipeline_id}?api-version=7.1-preview.7"
        )

        try:
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                async with session.get(definition_url, headers=headers) as get_resp:
                    if get_resp.status != 200:
                        msg = await get_resp.text()
                        error = (
                            f"Failed to fetch build definition {pipeline_id} "
                            f"for secret update ({get_resp.status}): {msg}"
                        )
                        logger.error(
                            "Pipeline secret update fetch failed: org=%s project=%s pipeline_id=%s keys=%s status=%s error=%s",
                            organization, project, pipeline_id, list(filtered_variables.keys()), get_resp.status, msg,
                        )
                        return {
                            "success": False,
                            "error": error,
                            "pipeline_id": pipeline_id,
                            "updated_keys": [],
                        }
                    definition = await get_resp.json()

                variables = definition.get("variables")
                if not isinstance(variables, dict):
                    variables = {}

                for key, value_data in filtered_variables.items():
                    variables[key] = {
                        "value": value_data["value"],
                        "isSecret": bool(value_data.get("is_secret", False)),
                        "allowOverride": True,
                    }
                definition["variables"] = variables

                async with session.put(definition_url, headers=headers, json=definition) as put_resp:
                    if put_resp.status in (200, 201):
                        return {
                            "success": True,
                            "pipeline_id": pipeline_id,
                            "updated_keys": list(filtered_variables.keys()),
                        }
                    msg = await put_resp.text()
                    error = (
                        f"Failed to update build definition {pipeline_id} "
                        f"with secret variables ({put_resp.status}): {msg}"
                    )
                    logger.error(
                        "Pipeline secret update put failed: org=%s project=%s pipeline_id=%s keys=%s status=%s error=%s",
                        organization, project, pipeline_id, list(filtered_variables.keys()), put_resp.status, msg,
                    )
                    return {
                        "success": False,
                        "error": error,
                        "pipeline_id": pipeline_id,
                        "updated_keys": list(filtered_variables.keys()),
                    }
        except Exception as e:
            logger.error(
                "Pipeline secret update exception: org=%s project=%s pipeline_id=%s keys=%s error=%s",
                organization, project, pipeline_id, list(filtered_variables.keys()), e,
            )
            return {
                "success": False,
                "error": f"Failed to set pipeline secret variables: {e}",
                "pipeline_id": pipeline_id,
                "updated_keys": list(filtered_variables.keys()),
            }

    async def _set_pipeline_secret_variables(
        self,
        organization: str,
        project: str,
        token: str,
        pipeline_id: int,
        secret_values: Dict[str, str],
    ) -> Dict[str, Any]:
        """Backward-compatible wrapper for secret-only variable updates."""
        variables_to_set = {
            key: {"value": value, "is_secret": True}
            for key, value in (secret_values or {}).items()
        }
        return await self._set_pipeline_definition_variables(
            organization=organization,
            project=project,
            token=token,
            pipeline_id=pipeline_id,
            variables_to_set=variables_to_set,
        )

    async def sync_pipeline_variables(
        self,
        repo_data: Dict[str, Any],
        db_session=None,
        pipeline_definition_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Sync required pipeline variables/secrets from dashboard settings without touching YAML."""
        try:
            organization, project, repository, token = self._validate_and_parse(repo_data)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        sync_status = await self.get_sync_status(repo_data, db_session)
        if sync_status.get("error"):
            return {"success": False, "error": sync_status.get("error")}

        pipeline_defs = sync_status.get("pipeline_definitions") or []
        if pipeline_definition_id:
            pipeline_defs = [p for p in pipeline_defs if str(p.get("id")) == str(pipeline_definition_id)]
        if not pipeline_defs:
            return {
                "success": False,
                "error": "No pipeline definitions found to sync variables. Create/setup pipeline first.",
            }

        dashboard_api_key = ""
        try:
            from config import settings as _s
            dashboard_api_key = (getattr(_s, 'dashboard_api_key', '') or '').strip()
        except Exception:
            dashboard_api_key = ""
        expected_plain = self._get_expected_pipeline_plain_variables()
        results = []
        overall_success = True
        for p in pipeline_defs:
            pid = p.get("id")
            if not pid:
                continue
            variable_map: Dict[str, Any] = {
                "AZURE_DEVOPS_PAT": {"value": repo_data.get("azure_pat", ""), "is_secret": True},
                "DASHBOARD_API_KEY": {"value": dashboard_api_key, "is_secret": True},
            }
            for k, v in expected_plain.items():
                variable_map[k] = {"value": v, "is_secret": False}
            result = await self._set_pipeline_definition_variables(
                organization=organization,
                project=project,
                token=token,
                pipeline_id=int(pid),
                variables_to_set=variable_map,
            )
            results.append({
                "pipeline_id": pid,
                "pipeline_name": p.get("name"),
                **result,
            })
            if not result.get("success"):
                overall_success = False

        return {
            "success": overall_success,
            "results": results,
            "pipelines_targeted": len(results),
            "updated_plain_keys": list(expected_plain.keys()),
            "updated_secret_keys": ["AZURE_DEVOPS_PAT", "DASHBOARD_API_KEY"],
        }

    async def _wait_for_pipeline_availability(
        self,
        session: aiohttp.ClientSession,
        headers: Dict[str, str],
        organization: str,
        project: str,
        pipeline_id: int,
        attempts: int = 10,
        delay_seconds: float = 1.0,
    ) -> bool:
        """Poll build definitions until the target pipeline appears."""
        if not pipeline_id:
            return False
        defs_url = f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions?api-version=7.1-preview.7"
        for _ in range(attempts):
            async with session.get(defs_url, headers=headers) as resp:
                if resp.status == 200:
                    defs = (await resp.json()).get("value", [])
                    if any(int(d.get("id", 0) or 0) == int(pipeline_id) for d in defs):
                        return True
            await asyncio.sleep(delay_seconds)
        return False

    async def _delete_pipeline_definition_internal(
        self, organization: str, project: str, token: str, definition_id: int
    ) -> Dict[str, Any]:
        """Internal cleanup helper used during rollback for newly created pipelines."""
        headers = self._build_headers(token)
        url = f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions/{definition_id}?api-version=7.1-preview.7"
        async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
            async with session.delete(url, headers=headers) as resp:
                if resp.status in (200, 204, 404):
                    return {"success": True, "message": "Pipeline deleted or already absent"}
                err_text = await resp.text()
                return {"success": False, "error": f"Delete pipeline failed ({resp.status}): {err_text}"}

    async def _delete_repository_internal(
        self, organization: str, project: str, token: str, repository_id: str
    ) -> Dict[str, Any]:
        """Internal cleanup helper used during rollback for newly created repos."""
        headers = self._build_headers(token)
        url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository_id}?api-version=7.0"
        async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
            async with session.delete(url, headers=headers) as resp:
                if resp.status in (200, 204, 202, 404):
                    return {"success": True, "message": "Repository deleted or already absent"}
                err_text = await resp.text()
                return {"success": False, "error": f"Delete repository failed ({resp.status}): {err_text}"}

    # ──────────────────────────────────────────────────────────────
    #  Branch listing
    # ──────────────────────────────────────────────────────────────

    async def list_branches(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """List branches for an Azure DevOps repository."""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'error': str(e)}

            headers = self._build_headers(token)

            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                # Get repo info for default branch
                repo_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}?api-version=7.0"
                async with session.get(repo_url, headers=headers) as resp:
                    default_branch = 'main'
                    if resp.status == 200:
                        info = await resp.json()
                        default_branch = info.get('defaultBranch', 'refs/heads/main').replace('refs/heads/', '')

                refs_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/refs?filter=heads/&api-version=7.0"
                async with session.get(refs_url, headers=headers) as resp:
                    if resp.status in (203, 401):
                        return {'error': 'Authentication failed. Check your Azure DevOps PAT.'}
                    if resp.status != 200:
                        return {'error': f'Azure DevOps API error: {resp.status}'}
                    data = await resp.json()
                    branches = []
                    for ref in data.get('value', []):
                        name = ref.get('name', '').replace('refs/heads/', '')
                        if name:
                            branches.append({
                                'name': name,
                                'is_default': name == default_branch,
                            })
                    return {
                        'branches': sorted(branches, key=lambda b: (not b['is_default'], b['name'])),
                        'default_branch': default_branch,
                    }

        except Exception as e:
            logger.error(f"Error listing branches: {e}")
            return {'error': str(e)}

    # ──────────────────────────────────────────────────────────────
    #  Build validation policy management
    # ──────────────────────────────────────────────────────────────

    BUILD_POLICY_TYPE_ID = "0609b952-1397-4640-95ec-e00a01b2c241"

    async def _get_repo_guid(self, organization: str, project: str, repository: str, token: str) -> Optional[str]:
        """Resolve the Azure DevOps repository GUID from its name."""
        headers = self._build_headers(token)
        url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}?api-version=7.0"
        async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status == 200:
                    return (await resp.json()).get('id')
        return None

    async def list_build_policies(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """List build validation policies scoped to this repository."""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'error': str(e)}

            repo_guid = await self._get_repo_guid(organization, project, repository, token)
            if not repo_guid:
                return {'error': 'Could not resolve repository ID'}

            headers = self._build_headers(token)

            url = f"https://dev.azure.com/{organization}/{project}/_apis/policy/configurations?api-version=7.0"
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                async with session.get(url, headers=headers) as resp:
                    if resp.status in (203, 401):
                        return {'error': 'Authentication failed. Check your Azure DevOps PAT.'}
                    if resp.status != 200:
                        return {'error': f'Azure DevOps API error: {resp.status}'}
                    data = await resp.json()

            policies = []
            for cfg in data.get('value', []):
                if cfg.get('type', {}).get('id') != self.BUILD_POLICY_TYPE_ID:
                    continue
                settings = cfg.get('settings', {})
                scopes = settings.get('scope', [])
                matches_repo = any(
                    s.get('repositoryId') == repo_guid for s in scopes
                )
                if not matches_repo and repo_guid:
                    continue
                branch = ''
                for s in scopes:
                    ref = s.get('refName', '')
                    if ref:
                        branch = ref.replace('refs/heads/', '')
                        break
                policies.append({
                    'policy_id': cfg.get('id'),
                    'branch': branch,
                    'pipeline_id': settings.get('buildDefinitionId'),
                    'pipeline_name': settings.get('displayName', ''),
                    'is_blocking': cfg.get('isBlocking', False),
                    'is_enabled': cfg.get('isEnabled', True),
                })

            return {'policies': policies}

        except Exception as e:
            logger.error(f"Error listing build policies: {e}")
            return {'error': str(e)}

    async def ensure_build_policy(
        self,
        repo_data: Dict[str, Any],
        branch: str,
        pipeline_definition_id: int,
        is_blocking: bool = False,
    ) -> Dict[str, Any]:
        """Create or update a build validation policy for the given branch and pipeline."""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'success': False, 'error': str(e)}

            repo_guid = await self._get_repo_guid(organization, project, repository, token)
            if not repo_guid:
                return {'success': False, 'error': 'Could not resolve repository ID'}

            if not branch or not branch.strip():
                return {'success': False, 'error': 'Branch name is required'}

            headers = self._build_headers(token)

            ref_name = f"refs/heads/{branch}" if not branch.startswith('refs/') else branch

            policy_body = {
                "isEnabled": True,
                "isBlocking": is_blocking,
                "type": {"id": self.BUILD_POLICY_TYPE_ID},
                "settings": {
                    "buildDefinitionId": pipeline_definition_id,
                    "queueOnSourceUpdateOnly": True,
                    "manualQueueOnly": False,
                    "displayName": f"PR-Agent Review ({branch})",
                    "validDuration": 720,
                    "scope": [{
                        "repositoryId": repo_guid,
                        "refName": ref_name,
                        "matchKind": "Exact",
                    }]
                }
            }

            existing_id = None
            list_url = f"https://dev.azure.com/{organization}/{project}/_apis/policy/configurations?api-version=7.0"
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                async with session.get(list_url, headers=headers) as resp:
                    if resp.status == 200:
                        for cfg in (await resp.json()).get('value', []):
                            if cfg.get('type', {}).get('id') != self.BUILD_POLICY_TYPE_ID:
                                continue
                            s = cfg.get('settings', {})
                            if s.get('buildDefinitionId') != pipeline_definition_id:
                                continue
                            scopes = s.get('scope', [])
                            if any(sc.get('repositoryId') == repo_guid and sc.get('refName') == ref_name for sc in scopes):
                                existing_id = cfg['id']
                                break

                if existing_id:
                    put_url = f"https://dev.azure.com/{organization}/{project}/_apis/policy/configurations/{existing_id}?api-version=7.0"
                    async with session.put(put_url, headers=headers, json=policy_body) as resp:
                        if resp.status in (200, 201):
                            result = await resp.json()
                            return {'success': True, 'policy_id': result.get('id', existing_id), 'created': False, 'updated': True, 'is_blocking': is_blocking}
                        try:
                            err = await resp.json()
                            msg = err.get('message', str(resp.status))
                        except Exception:
                            msg = await resp.text() or str(resp.status)
                        return {'success': False, 'error': f"Update failed: {msg}"}
                else:
                    post_url = f"https://dev.azure.com/{organization}/{project}/_apis/policy/configurations?api-version=7.0"
                    async with session.post(post_url, headers=headers, json=policy_body) as resp:
                        if resp.status in (200, 201):
                            result = await resp.json()
                            return {'success': True, 'policy_id': result.get('id'), 'created': True, 'updated': False, 'is_blocking': is_blocking}
                        try:
                            err = await resp.json()
                            msg = err.get('message', str(resp.status))
                        except Exception:
                            msg = await resp.text() or str(resp.status)
                        return {'success': False, 'error': f"Create failed: {msg}"}

        except Exception as e:
            logger.error(f"Error ensuring build policy: {e}")
            return {'success': False, 'error': str(e)}

    async def delete_build_policy(self, repo_data: Dict[str, Any], policy_id: int) -> Dict[str, Any]:
        """Delete a build validation policy by ID."""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'success': False, 'error': str(e)}

            headers = self._build_headers(token)

            url = f"https://dev.azure.com/{organization}/{project}/_apis/policy/configurations/{policy_id}?api-version=7.0"
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                async with session.delete(url, headers=headers) as resp:
                    if resp.status in (200, 204):
                        return {'success': True}
                    err_text = await resp.text()
                    return {'success': False, 'error': f"Delete failed ({resp.status}): {err_text}"}

        except Exception as e:
            logger.error(f"Error deleting build policy: {e}")
            return {'success': False, 'error': str(e)}

    # ──────────────────────────────────────────────────────────────
    #  Pipeline definition management
    # ──────────────────────────────────────────────────────────────

    async def delete_pipeline_definition(self, repo_data: Dict[str, Any], definition_id: int) -> Dict[str, Any]:
        """Delete a pipeline (build definition) by its ID."""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'success': False, 'error': str(e)}

            headers = self._build_headers(token)

            url = f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions/{definition_id}?api-version=7.1-preview.7"
            async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
                async with session.delete(url, headers=headers) as resp:
                    if resp.status in (200, 204):
                        return {'success': True}
                    if resp.status == 404:
                        return {'success': True, 'message': 'Pipeline definition already deleted or not found'}
                    err_text = await resp.text()
                    return {'success': False, 'error': f"Delete failed ({resp.status}): {err_text}"}

        except Exception as e:
            logger.error(f"Error deleting pipeline definition {definition_id}: {e}")
            return {'success': False, 'error': str(e)}

    # ──────────────────────────────────────────────────────────────
    #  Comprehensive cleanup
    # ──────────────────────────────────────────────────────────────

    async def cleanup_azure_resources(
        self, repo_data: Dict[str, Any], db_session=None,
        remove_policies: bool = True,
        remove_pipelines: bool = True,
        remove_yaml: bool = False,
    ) -> Dict[str, Any]:
        """
        Remove all Azure DevOps resources this dashboard created for a repo.

        Performs best-effort cleanup: each step is attempted independently so a
        single failure does not prevent the remaining resources from being cleaned.

        Parameters:
            repo_data:         dict with url, azure_pat, provider (and optionally id)
            db_session:        SQLAlchemy session (unused for now, reserved)
            remove_policies:   delete all build-validation policies scoped to this repo
                               whose pipeline name starts with 'PR-Agent'
            remove_pipelines:  delete pipeline definitions whose name starts with 'PR-Agent'
            remove_yaml:       delete azure-pipelines.yml from the default branch
                               (disabled by default - rarely desired)
        """
        try:
            organization, project, repository, token = self._validate_and_parse(repo_data)
        except ValueError as e:
            return {'skipped': True, 'reason': str(e)}

        results: Dict[str, Any] = {
            'policies_removed': [],
            'policies_failed': [],
            'pipelines_removed': [],
            'pipelines_failed': [],
            'yaml_removed': False,
            'errors': [],
        }

        # ── 1. Remove build validation policies scoped to this repo ──
        if remove_policies:
            try:
                policies_result = await self.list_build_policies(repo_data)
                if 'error' not in policies_result:
                    for pol in policies_result.get('policies', []):
                        pol_id = pol.get('policy_id')
                        pol_name = pol.get('pipeline_name', '') or ''
                        if not pol_name.lower().startswith('pr-agent'):
                            continue
                        try:
                            del_result = await self.delete_build_policy(repo_data, pol_id)
                            if del_result.get('success'):
                                results['policies_removed'].append(pol_id)
                                logger.info("Cleanup: removed policy %s (%s) for repo %s",
                                            pol_id, pol_name, repository)
                            else:
                                results['policies_failed'].append({
                                    'policy_id': pol_id, 'error': del_result.get('error', 'unknown')
                                })
                                logger.warning("Cleanup: failed to remove policy %s: %s",
                                               pol_id, del_result.get('error'))
                        except Exception as e:
                            results['policies_failed'].append({'policy_id': pol_id, 'error': str(e)})
                            logger.warning("Cleanup: exception removing policy %s: %s", pol_id, e)
                else:
                    results['errors'].append(f"Could not list policies: {policies_result['error']}")
            except Exception as e:
                results['errors'].append(f"Policy cleanup error: {e}")
                logger.error("Cleanup: policy listing failed for %s: %s", repository, e)

        # ── 2. Remove PR-Agent pipeline definitions ──
        if remove_pipelines:
            try:
                pipeline_info = await self._check_pipeline_definitions(
                    organization, project, repository, token
                )
                for pipe in pipeline_info.get('pipelines', []):
                    pipe_id = pipe.get('id')
                    pipe_name = pipe.get('name', '') or ''
                    if not pipe_name.lower().startswith('pr-agent'):
                        continue
                    try:
                        del_result = await self.delete_pipeline_definition(repo_data, pipe_id)
                        if del_result.get('success'):
                            results['pipelines_removed'].append(pipe_id)
                            logger.info("Cleanup: removed pipeline %s (%s) for repo %s",
                                        pipe_id, pipe_name, repository)
                        else:
                            results['pipelines_failed'].append({
                                'pipeline_id': pipe_id, 'error': del_result.get('error', 'unknown')
                            })
                            logger.warning("Cleanup: failed to remove pipeline %s: %s",
                                           pipe_id, del_result.get('error'))
                    except Exception as e:
                        results['pipelines_failed'].append({'pipeline_id': pipe_id, 'error': str(e)})
                        logger.warning("Cleanup: exception removing pipeline %s: %s", pipe_id, e)
            except Exception as e:
                results['errors'].append(f"Pipeline cleanup error: {e}")
                logger.error("Cleanup: pipeline listing failed for %s: %s", repository, e)

        # ── 3. Optionally remove azure-pipelines.yml ──
        if remove_yaml:
            try:
                await self._delete_pipeline_yaml(organization, project, repository, token)
                results['yaml_removed'] = True
                logger.info("Cleanup: removed azure-pipelines.yml from repo %s", repository)
            except Exception as e:
                results['errors'].append(f"YAML removal error: {e}")
                logger.warning("Cleanup: failed to remove YAML from %s: %s", repository, e)

        total = (len(results['policies_removed']) + len(results['pipelines_removed'])
                 + (1 if results['yaml_removed'] else 0))
        failed = len(results['policies_failed']) + len(results['pipelines_failed']) + len(results['errors'])
        results['summary'] = f"Removed {total} resource(s)" + (f", {failed} failure(s)" if failed else "")

        logger.info("Cleanup complete for %s/%s/%s: %s", organization, project, repository, results['summary'])
        return results

    async def _delete_pipeline_yaml(
        self, organization: str, project: str, repository: str, token: str,
    ) -> None:
        """Delete azure-pipelines.yml from the default branch (best-effort)."""
        headers = self._build_headers(token)

        async with aiohttp.ClientSession(timeout=self.AIOHTTP_TIMEOUT) as session:
            repo_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}?api-version=7.0"
            async with session.get(repo_url, headers=headers) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Could not get repo info ({resp.status})")
                info = await resp.json()
                default_branch = info.get('defaultBranch', 'refs/heads/main').replace('refs/heads/', '')

            refs_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/refs?filter=heads/{default_branch}&api-version=7.0"
            async with session.get(refs_url, headers=headers) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Could not get branch ref ({resp.status})")
                refs_data = await resp.json()
                if not refs_data.get('value'):
                    raise RuntimeError(f"Branch {default_branch} not found")
                latest_commit = refs_data['value'][0]['objectId']

            file_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/items?path=azure-pipelines.yml&api-version=7.1-preview.1"
            async with session.get(file_url, headers=headers) as resp:
                if resp.status != 200:
                    return  # file doesn't exist, nothing to delete

            push_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/pushes?api-version=7.0"
            push_data = {
                "refUpdates": [{
                    "name": f"refs/heads/{default_branch}",
                    "oldObjectId": latest_commit,
                }],
                "commits": [{
                    "comment": "Remove PR-Agent pipeline configuration\n\nCleaned up by PR-Agent Dashboard",
                    "changes": [{
                        "changeType": "delete",
                        "item": {"path": "/azure-pipelines.yml"},
                    }],
                }],
            }
            async with session.post(push_url, headers=headers, json=push_data) as resp:
                if resp.status not in (200, 201):
                    err_text = await resp.text()
                    raise RuntimeError(f"YAML delete push failed ({resp.status}): {err_text}")