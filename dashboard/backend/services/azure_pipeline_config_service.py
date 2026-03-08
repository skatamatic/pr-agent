import os
import base64
import difflib
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

    def get_docker_pipeline_template(self, pool_name: str = "PRAgent_Cloud") -> str:
        """Return the Docker-based pipeline YAML with pool name filled in."""
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
        source /opt/pr-agent-runner/env 2>/dev/null || true

        IMAGE="${{PR_AGENT_IMAGE_OVERRIDE:-${{GCP_RUNNER_PR_AGENT_IMAGE:-}}}}"
        if [ -z "$IMAGE" ]; then
          echo "##vso[task.logissue type=error]No PR-Agent image found."
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
        echo "##vso[task.setvariable variable=VM_GCS_BUCKET]${{PR_AGENT_CONFIG_GCS_BUCKET:-}}"
        echo "##vso[task.setvariable variable=VM_GCS_PREFIX]${{PR_AGENT_CONFIG_GCS_PREFIX:-}}"
        echo "##vso[task.setvariable variable=VM_DASHBOARD_URL]${{DASHBOARD_URL:-}}"
        echo "##vso[task.setvariable variable=VM_DASHBOARD_API_KEY;issecret=true]${{DASHBOARD_API_KEY:-}}"
        echo "##vso[task.setvariable variable=VM_AZURE_DEVOPS_PAT;issecret=true]${{AZURE_DEVOPS_PAT:-}}"
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
        SYSTEM_TEAMPROJECT: $(System.TeamProject)
        BUILD_REPOSITORY_NAME: $(Build.Repository.Name)
        SYSTEM_COLLECTIONURI: $(System.CollectionUri)
        AZURE_DEVOPS_PAT: $(VM_AZURE_DEVOPS_PAT)
        SYSTEM_ACCESSTOKEN: $(System.AccessToken)
        DASHBOARD_URL: $(VM_DASHBOARD_URL)
        DASHBOARD_API_KEY: $(VM_DASHBOARD_API_KEY)
        PR_AGENT_CONFIG_GCS_BUCKET: $(VM_GCS_BUCKET)
        PR_AGENT_CONFIG_GCS_PREFIX: $(VM_GCS_PREFIX)
"""

    def get_canonical_template(self, repo_data: Dict[str, Any], db_session=None) -> str:
        """Select the right pipeline template based on runner configuration."""
        pool_name = None
        uses_docker = False

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
            if getattr(settings, 'gcp_runner_pr_agent_image', ''):
                uses_docker = True
        except Exception:
            pass

        if uses_docker and pool_name:
            return self.get_docker_pipeline_template(pool_name)
        elif uses_docker:
            return self.get_docker_pipeline_template()
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
        """Compare repo's azure-pipelines.yml against the canonical template."""
        try:
            try:
                organization, project, repository, token = self._validate_and_parse(repo_data)
            except ValueError as e:
                return {'error': str(e)}

            yaml_file = await self._get_file_content(
                organization, project, repository, 'azure-pipelines.yml', token
            )
            pipeline_info = await self._check_pipeline_definitions(
                organization, project, repository, token
            )
            canonical = self.get_canonical_template(repo_data, db_session)

            if not yaml_file['exists']:
                if yaml_file.get('error') and yaml_file['error'] != 'File not found':
                    return {'error': f"Failed to check YAML file: {yaml_file['error']}"}
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
                    'pipelines_url': f"https://dev.azure.com/{organization}/{project}/_build",
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
                'pipelines_url': f"https://dev.azure.com/{organization}/{project}/_build",
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

            headers = self._build_headers(token)

            yaml_pushed = False
            pipeline_created = False
            pipeline_id = None

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

            return {
                'success': True,
                'yaml_pushed': yaml_pushed,
                'pipeline_created': pipeline_created,
                'pipeline_id': pipeline_id,
                'pipeline_create_error': None if pipeline_created or pipeline_id else 'Pipeline definition could not be created. You may need to create it manually.',
            }

        except Exception as e:
            logger.error(f"Error in push_yaml_direct: {e}")
            return {'success': False, 'error': str(e)}

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