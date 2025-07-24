import os
import re
import yaml
import base64
from typing import Dict, Any, Optional, List
from datetime import datetime
import logging
from jinja2 import Template

from .runner_health_service import RunnerHealthService

logger = logging.getLogger(__name__)

class AzurePipelineConfigService:
    """Service for managing Azure DevOps Pipeline configuration files"""
    
    def __init__(self):
        self.runner_health_service = RunnerHealthService()

    async def check_azure_pipeline_config(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check if repository has Azure DevOps Pipeline configuration"""
        try:
            # Get repository details
            repo_name = repo_data.get('name', '')
            provider = repo_data.get('provider', '')
            url = repo_data.get('url', '')
            
            # Only check Azure DevOps repositories
            if provider != 'azure_devops':
                return {
                    'exists': False,
                    'error': 'Azure Pipeline config is only supported for Azure DevOps repositories'
                }
            
            # Get token from repository data
            token = repo_data.get('azure_pat', '')
            if not token or token.strip() == '':
                return {
                    'exists': False,
                    'error': 'Azure DevOps PAT is required to check Pipeline configuration. Please configure the Azure PAT in the General tab.'
                }
            
            # Extract organization, project, and repo from URL
            org_info = self._parse_azure_repo_url(url)
            if not org_info['success']:
                return {
                    'exists': False,
                    'error': org_info['error']
                }
            
            organization = org_info['organization']
            project = org_info['project']
            repository = org_info['repository']
            
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
            import aiohttp
            
            headers = {
                'Authorization': f'Basic {base64.b64encode(f":{token}".encode()).decode()}',
                'Content-Type': 'application/json'
            }
            
            # Get file content via Azure DevOps REST API
            url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/items?path={path}&api-version=7.0"
            
            async with aiohttp.ClientSession() as session:
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
            import aiohttp
            
            headers = {
                'Authorization': f'Basic {base64.b64encode(f":{token}".encode()).decode()}',
                'Content-Type': 'application/json'
            }
            
            # Get build definitions (pipelines) for the project
            url = f"https://dev.azure.com/{organization}/{project}/_apis/build/definitions?api-version=7.0"
            
            async with aiohttp.ClientSession() as session:
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
                    # Extract branch filters if available
                    branch_filters = trigger.get('branchFilters', [])
                    trigger_info['pr_branches'] = [f.get('include', []) for f in branch_filters if f.get('include')]
                elif trigger_type == 'continuousIntegration':
                    trigger_info['has_ci_trigger'] = True
                    branch_filters = trigger.get('branchFilters', [])
                    trigger_info['ci_branches'] = [f.get('include', []) for f in branch_filters if f.get('include')]
            
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
            # Get repository details
            repo_name = repo_data.get('name', '')
            provider = repo_data.get('provider', '')
            url = repo_data.get('url', '')
            
            # Only work with Azure DevOps repositories
            if provider != 'azure_devops':
                return {
                    'success': False,
                    'error': 'Azure Pipeline config is only supported for Azure DevOps repositories'
                }
            
            # Get token
            token = repo_data.get('azure_pat', '')
            if not token:
                return {
                    'success': False,
                    'error': 'Azure DevOps PAT is required'
                }
            
            # Parse repository URL
            org_info = self._parse_azure_repo_url(url)
            if not org_info['success']:
                return {
                    'success': False,
                    'error': org_info['error']
                }
            
            organization = org_info['organization']
            project = org_info['project']
            repository = org_info['repository']
            
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
            import aiohttp
            
            headers = {
                'Authorization': f'Basic {base64.b64encode(f":{token}".encode()).decode()}',
                'Content-Type': 'application/json'
            }
            
            # Generate branch name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            branch_name = f"pr-agent-dashboard/azure-pipeline-config-{timestamp}"
            
            async with aiohttp.ClientSession() as session:
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
                        return {
                            'success': False,
                            'error': f"Failed to create/update file: {error_data.get('message', 'Unknown error')}"
                        }
                
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
                        return {
                            'success': False,
                            'error': f"Failed to create pull request: {error_data.get('message', 'Unknown error')}"
                        }
                    
                    pr_info = await response.json()
                    return {
                        'success': True,
                        'pr_number': pr_info['pullRequestId'],
                        'pr_url': f"https://dev.azure.com/{organization}/{project}/_git/{repository}/pullrequest/{pr_info['pullRequestId']}",
                        'branch_name': branch_name
                    }
                    
        except Exception as e:
            logger.error(f"Error creating config PR: {e}")
            return {
                'success': False,
                'error': f'Failed to create PR: {str(e)}'
            }

    async def check_pr_status(self, repo_data: Dict[str, Any], pr_number: int) -> Dict[str, Any]:
        """Check the status of an Azure DevOps pull request"""
        try:
            # Get repository details
            url = repo_data.get('url', '')
            token = repo_data.get('azure_pat', '')
            
            if not token:
                return {
                    'success': False,
                    'error': 'Azure DevOps PAT is required'
                }
            
            # Parse repository URL
            org_info = self._parse_azure_repo_url(url)
            if not org_info['success']:
                return {
                    'success': False,
                    'error': org_info['error']
                }
            
            organization = org_info['organization']
            project = org_info['project']
            repository = org_info['repository']
            
            # Check PR status
            import aiohttp
            
            headers = {
                'Authorization': f'Basic {base64.b64encode(f":{token}".encode()).decode()}',
                'Content-Type': 'application/json'
            }
            
            pr_url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repository}/pullrequests/{pr_number}?api-version=7.0"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(pr_url, headers=headers) as response:
                    if response.status == 200:
                        pr_data = await response.json()
                        status = pr_data.get('status', '').lower()
                        
                        # Map Azure DevOps status to our standard format
                        mapped_status = 'pending'
                        if status == 'completed':
                            mapped_status = 'merged' if pr_data.get('mergeStatus') == 'succeeded' else 'closed'
                        elif status == 'abandoned':
                            mapped_status = 'closed'
                        
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
            template = Template(template_str)
            return template.render(env_vars=env_vars)
            
        except Exception as e:
            logger.error(f"Error generating YAML config: {e}")
            # Return template with default env vars on error
            try:
                template = Template(self.get_default_config_template())
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