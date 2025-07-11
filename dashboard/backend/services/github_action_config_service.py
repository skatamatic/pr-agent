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

class GitHubActionConfigService:
    """Service for managing GitHub Action configuration files"""
    
    def __init__(self):
        self.runner_health_service = RunnerHealthService()

    async def check_github_action_config(self, repo_data: Dict[str, Any]) -> Dict[str, Any]:
        """Check if repository has GitHub Action configuration"""
        try:
            # Get repository details
            repo_name = repo_data.get('name', '')
            provider = repo_data.get('provider', '')
            url = repo_data.get('url', '')
            

            # Only check GitHub repositories
            if provider != 'github':
                return {
                    'exists': False,
                    'error': 'GitHub Action config is only supported for GitHub repositories'
                }
            
            # Get token from repository data
            token = repo_data.get('github_token', '')
            if not token or token.strip() == '':
                return {
                    'exists': False,
                    'error': 'GitHub token is required to check Action configuration. Please configure the GitHub token in the General tab.'
                }
            
            # Extract owner and repo from URL
            try:
                # Handle various GitHub URL formats
                if url.endswith('.git'):
                    url = url[:-4]
                
                # Extract owner/repo from URL
                if 'github.com' in url:
                    parts = url.split('github.com/')[-1].split('/')
                    if len(parts) >= 2:
                        owner = parts[0]
                        repo = parts[1]
                    else:
                        raise ValueError("Invalid GitHub URL format")
                else:
                    raise ValueError("Not a GitHub repository URL")
                
            except Exception as e:
                return {
                    'exists': False,
                    'error': f'Invalid GitHub repository URL: {str(e)}'
                }
            
            # Check for GitHub Action config file
            config_path = '.github/workflows/pr_agent.yml'
            file_info = await self._get_file_content(owner, repo, config_path, token)
            
            if file_info['exists']:
                return {
                    'exists': True,
                    'content': file_info['content'],
                    'decoded_content': file_info['decoded_content'],
                    'sha': file_info['sha'],
                    'path': config_path,
                    'last_modified': file_info['last_modified']
                }
            else:
                # Only return error if it's not just "file not found" (404)
                if file_info.get('error') and file_info.get('error') != 'File not found':
                    return {
                        'exists': False,
                        'error': file_info.get('error')
                    }
                else:
                    # File simply doesn't exist - this is expected, not an error
                    return {
                        'exists': False
                    }
                
        except Exception as e:
            logger.error(f"Error checking GitHub Action config: {e}")
            return {
                'exists': False,
                'error': f'Failed to check GitHub Action config: {str(e)}'
            }

    async def _get_file_content(self, owner: str, repo: str, path: str, token: str) -> Dict[str, Any]:
        """Get file content from GitHub repository"""
        try:
            import aiohttp
            
            url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'PR-Agent-Dashboard'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Decode content
                        content = data.get('content', '')
                        decoded_content = base64.b64decode(content).decode('utf-8')
                        
                        return {
                            'exists': True,
                            'content': content,
                            'decoded_content': decoded_content,
                            'sha': data.get('sha', ''),
                            'last_modified': data.get('commit', {}).get('committer', {}).get('date', '')
                        }
                    elif response.status == 404:
                        return {
                            'exists': False,
                            'error': 'File not found'
                        }
                    else:
                        error_data = await response.json()
                        return {
                            'exists': False,
                            'error': f"GitHub API error: {error_data.get('message', f'HTTP {response.status}')}"
                        }
                        
        except Exception as e:
            logger.error(f"Error fetching file content: {e}")
            return {
                'exists': False,
                'error': f'Failed to fetch file: {str(e)}'
            }

    async def create_github_action_config_pr(self, repo_data: Dict[str, Any], config_content: str, db_session=None) -> Dict[str, Any]:
        """Create a PR with GitHub Action configuration"""
        try:
            # Get repository details
            repo_name = repo_data.get('name', '')
            provider = repo_data.get('provider', '')
            url = repo_data.get('url', '')
            
            # Only work with GitHub repositories
            if provider != 'github':
                return {
                    'success': False,
                    'error': 'GitHub Action config is only supported for GitHub repositories'
                }
            
            # Get token
            token = repo_data.get('github_token', '')
            if not token:
                return {
                    'success': False,
                    'error': 'GitHub token is required'
                }
            
            # Extract owner and repo from URL
            try:
                if url.endswith('.git'):
                    url = url[:-4]
                
                if 'github.com' in url:
                    parts = url.split('github.com/')[-1].split('/')
                    if len(parts) >= 2:
                        owner = parts[0]
                        repo = parts[1]
                    else:
                        raise ValueError("Invalid GitHub URL format")
                else:
                    raise ValueError("Not a GitHub repository URL")
                
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Invalid GitHub repository URL: {str(e)}'
                }
            
            # Create the PR
            pr_result = await self._create_config_pr(owner, repo, token, config_content)
            
            # If PR was created successfully and we have a database session, save the PR info
            if pr_result['success'] and db_session:
                try:
                    from models import RepositoryDB
                    db_repo = db_session.query(RepositoryDB).filter(RepositoryDB.id == repo_data.get('id')).first()
                    if db_repo:
                        db_repo.github_action_config_pr_url = pr_result['pr_url']
                        db_repo.github_action_config_pr_number = pr_result['pr_number']
                        db_repo.github_action_config_pr_branch = pr_result['branch_name']
                        db_repo.github_action_config_pr_status = 'pending'
                        db_session.commit()
                        logger.info(f"Saved GitHub Action config PR info for repository {repo_data.get('name')}")
                except Exception as db_error:
                    logger.error(f"Failed to save PR info to database: {db_error}")
                    # Don't fail the whole operation if just the database save fails
            
            return pr_result
            
        except Exception as e:
            logger.error(f"Error creating GitHub Action config PR: {e}")
            return {
                'success': False,
                'error': f'Failed to create PR: {str(e)}'
            }

    async def _create_config_pr(self, owner: str, repo: str, token: str, config_content: str) -> Dict[str, Any]:
        """Create a pull request with the GitHub Action configuration"""
        try:
            import aiohttp
            
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'PR-Agent-Dashboard'
            }
            
            # Generate branch name
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            branch_name = f"pr-agent-dashboard/github-action-config-{timestamp}"
            
            async with aiohttp.ClientSession() as session:
                # Get the default branch
                repo_url = f"https://api.github.com/repos/{owner}/{repo}"
                async with session.get(repo_url, headers=headers) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        return {
                            'success': False,
                            'error': f"Failed to get repository info: {error_data.get('message', 'Unknown error')}"
                        }
                    repo_info = await response.json()
                    default_branch = repo_info.get('default_branch', 'main')
                
                # Get the latest commit of the default branch
                ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs/heads/{default_branch}"
                async with session.get(ref_url, headers=headers) as response:
                    if response.status != 200:
                        error_data = await response.json()
                        return {
                            'success': False,
                            'error': f"Failed to get branch info: {error_data.get('message', 'Unknown error')}"
                        }
                    ref_data = await response.json()
                    latest_commit_sha = ref_data['object']['sha']
                
                # Create new branch
                create_ref_url = f"https://api.github.com/repos/{owner}/{repo}/git/refs"
                branch_data = {
                    "ref": f"refs/heads/{branch_name}",
                    "sha": latest_commit_sha
                }
                
                async with session.post(create_ref_url, headers=headers, json=branch_data) as response:
                    if response.status != 201:
                        error_data = await response.json()
                        return {
                            'success': False,
                            'error': f"Failed to create branch: {error_data.get('message', 'Unknown error')}"
                        }
                
                # Check if file exists
                file_path = '.github/workflows/pr_agent.yml'
                file_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
                
                # Try to get existing file
                existing_file = None
                async with session.get(file_url, headers=headers) as response:
                    if response.status == 200:
                        existing_file = await response.json()
                
                # Create or update file
                file_data = {
                    "message": "Update GitHub Action configuration for PR-Agent\n\nThis PR was created automatically via PR Agent Dashboard",
                    "content": base64.b64encode(config_content.encode('utf-8')).decode('utf-8'),
                    "branch": branch_name
                }
                
                if existing_file:
                    file_data["sha"] = existing_file["sha"]
                
                async with session.put(file_url, headers=headers, json=file_data) as response:
                    if response.status not in [200, 201]:
                        error_data = await response.json()
                        return {
                            'success': False,
                            'error': f"Failed to create/update file: {error_data.get('message', 'Unknown error')}"
                        }
                
                # Create pull request
                pr_data = {
                    "title": "Update GitHub Action configuration for PR-Agent",
                    "body": "This PR updates the GitHub Action configuration for PR-Agent.\n\nThis PR was created automatically via PR Agent Dashboard.\n\nPlease review the changes and merge when ready.",
                    "head": branch_name,
                    "base": default_branch
                }
                
                pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls"
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
                        'pr_number': pr_info['number'],
                        'pr_url': pr_info['html_url'],
                        'branch_name': branch_name
                    }
                    
        except Exception as e:
            logger.error(f"Error creating config PR: {e}")
            return {
                'success': False,
                'error': f'Failed to create PR: {str(e)}'
            }

    async def check_pr_status(self, repo_data: Dict[str, Any], pr_number: int) -> Dict[str, Any]:
        """Check the status of a pull request"""
        try:
            # Get repository details
            url = repo_data.get('url', '')
            token = repo_data.get('github_token', '')
            
            if not token:
                return {
                    'success': False,
                    'error': 'GitHub token is required'
                }
            
            # Extract owner and repo from URL
            try:
                if url.endswith('.git'):
                    url = url[:-4]
                
                if 'github.com' in url:
                    parts = url.split('github.com/')[-1].split('/')
                    if len(parts) >= 2:
                        owner = parts[0]
                        repo = parts[1]
                    else:
                        raise ValueError("Invalid GitHub URL format")
                else:
                    raise ValueError("Not a GitHub repository URL")
                
            except Exception as e:
                return {
                    'success': False,
                    'error': f'Invalid GitHub repository URL: {str(e)}'
                }
            
            # Check PR status
            import aiohttp
            
            headers = {
                'Authorization': f'token {token}',
                'Accept': 'application/vnd.github.v3+json',
                'User-Agent': 'PR-Agent-Dashboard'
            }
            
            pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
            
            async with aiohttp.ClientSession() as session:
                async with session.get(pr_url, headers=headers) as response:
                    if response.status == 200:
                        pr_data = await response.json()
                        return {
                            'success': True,
                            'pr_number': pr_data['number'],
                            'pr_url': pr_data['html_url'],
                            'state': pr_data['state'],
                            'merged': pr_data['merged'],
                            'mergeable': pr_data['mergeable'],
                            'title': pr_data['title'],
                            'updated_at': pr_data['updated_at']
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
                            'error': f"GitHub API error: {error_data.get('message', f'HTTP {response.status}')}"
                        }
                        
        except Exception as e:
            logger.error(f"Error checking PR status: {e}")
            return {
                'success': False,
                'error': f'Failed to check PR status: {str(e)}'
            }

    def get_default_config_template(self) -> str:
        """Get the default GitHub Action configuration template"""
        return """name: PRAgent on SelfHosted Runner (No Docker)

on:
  pull_request:
    types: [opened, reopened, ready_for_review]

jobs:
  pr_agent_job:
    if: {% raw %}${{ github.event.sender.type != 'Bot' }}{% endraw %}
    runs-on: [self-hosted, windows]

    permissions:
      issues: write
      pull-requests: write
      contents: write

    # ────────────────────────────────────────────────────────────────
    # 1. Global environment – anything that never changes.
    #    Secrets are still referenced exactly once here so you don't
    #    have to repeat them in every step.
    # ────────────────────────────────────────────────────────────────
    env:
{%- for key, value in env_vars.items() %}
{%- if '.' not in key %}
{%- if key in ['OPENAI_KEY', 'OPENAI__KEY', 'ANTHROPIC_KEY', 'ANTHROPIC__KEY', 'GITHUB_TOKEN', 'CSHARP_CODE_CONTEXT_SERVICE__PASSWORD'] %}
      {{ key.ljust(30) }}: {{ value }}
{%- elif key.startswith('CSHARP_CODE_CONTEXT_SERVICE__') %}
      {{ key }}: {{ value }}
{%- else %}
      {{ key }}: {{ value }}
{%- endif %}
{%- endif %}
{%- endfor %}

    steps:
    # ────────────────────────────────────────────────────────────────
    # 2. Get the PR‑Agent code (exact branch)
    # ────────────────────────────────────────────────────────────────
    - name: Checkout PRAgent fork (CodeContextIntegration)
      uses: actions/checkout@v4
      with:
        repository: skatamatic/pr-agent
        ref: Dashboard
        path: pr_agent_code

    # ────────────────────────────────────────────────────────────────
    # 3. Install Python 3.12 **once** and cache your pip packages
    #    – works on Windows runners too.
    # ────────────────────────────────────────────────────────────────
    - name: Set up Python 3.12
      uses: actions/setup-python@v5
      with:
        python-version: 3.12          # uses official 3.12.x
        cache: pip
        cache-dependency-path: pr_agent_code/requirements.txt

    # 3.1 Extra safety: make sure the wheel cache survives even on failure
    - name: Save / restore pip wheel cache
      uses: actions/cache@v4
      with:
        # Default pip wheel dir on Windows; add the Linux/Mac dir for cross-OS runners
        path: |
          {% raw %}${{ env.LOCALAPPDATA }}{% endraw %}\\pip\\Cache
          ~/.cache/pip
        key: {% raw %}${{ runner.os }}{% endraw %}-pip-{% raw %}${{ hashFiles('pr_agent_code/requirements.txt') }}{% endraw %}
        restore-keys: |
          {% raw %}${{ runner.os }}{% endraw %}-pip-

    # ────────────────────────────────────────────────────────────────
    # 4. Install / update dependencies (fast thanks to cache)
    # ────────────────────────────────────────────────────────────────
    - name: Install PRAgent requirements
      run: |
        pip install --upgrade pip
        pip install -r pr_agent_code/requirements.txt

    # ────────────────────────────────────────────────────────────────
    # 5. Some configs expect an env‑var *with a dot* in its name.
    #    YAML keys cannot contain dots, so we add it at runtime.
    # ────────────────────────────────────────────────────────────────
{%- set has_dotted_vars = namespace(value=false) %}
{%- for key, value in env_vars.items() %}
{%- if '.' in key %}
{%- set has_dotted_vars.value = true %}
{%- endif %}
{%- endfor %}
{%- if has_dotted_vars.value %}
    - name: Export environment variables with dots
      shell: powershell
      run: |
        # Append to $GITHUB_ENV so it's visible in the next steps
{%- for key, value in env_vars.items() %}
{%- if '.' in key %}
        Add-Content $env:GITHUB_ENV "{{ key }}={{ value }}"
{%- endif %}
{%- endfor %}
{%- endif %}

    # ────────────────────────────────────────────────────────────────
    # 6. Copy the event file to the classic Docker path
    # ────────────────────────────────────────────────────────────────
    - name: Mirror event.json to legacy location
      shell: powershell
      run: |
        $legacy = "$env:GITHUB_WORKSPACE\\github\\workflow"
        New-Item -ItemType Directory -Force -Path $legacy | Out-Null
        Copy-Item -Force $env:GITHUB_EVENT_PATH "$legacy\\event.json"
        # update the variable so the runner script sees the legacy path
        Add-Content $env:GITHUB_ENV "GITHUB_EVENT_PATH=$legacy\\\\event.json"

    # ────────────────────────────────────────────────────────────────
    # 7. Run PRAgent
    # ────────────────────────────────────────────────────────────────
    - name: Run PRAgent
      shell: powershell
      working-directory: pr_agent_code
      run: |
        python pr_agent/servers/github_action_runner.py
"""

    def get_github_action_env_vars(self) -> List[Dict[str, Any]]:
        """Get list of GitHub Action environment variables that can be configured"""
        return [
            {
                'key': 'GITHUB_ACTION_CONFIG.AUTO_REVIEW',
                'label': 'Auto Review',
                'description': 'Enable automatic PR review',
                'type': 'boolean',
                'default': 'true',
                'category': 'PR Actions'
            },
            {
                'key': 'GITHUB_ACTION_CONFIG.AUTO_DESCRIBE',
                'label': 'Auto Describe',
                'description': 'Enable automatic PR description generation',
                'type': 'boolean',
                'default': 'true',
                'category': 'PR Actions'
            },
            {
                'key': 'GITHUB_ACTION_CONFIG.AUTO_IMPROVE',
                'label': 'Auto Improve',
                'description': 'Enable automatic PR improvement suggestions',
                'type': 'boolean',
                'default': 'false',
                'category': 'PR Actions'
            },
            {
                'key': 'GITHUB_ACTION_CONFIG.ENABLE_OUTPUT',
                'label': 'Enable Output',
                'description': 'Enable GitHub Action output generation',
                'type': 'boolean',
                'default': 'true',
                'category': 'Output'
            },
            {
                'key': 'GITHUB_ACTION_CONFIG.PR_ACTIONS',
                'label': 'PR Actions',
                'description': 'List of PR actions that trigger the workflow',
                'type': 'array',
                'default': '["opened", "reopened", "ready_for_review"]',
                'category': 'Triggers'
            },
            {
                'key': 'OPENAI_KEY',
                'label': 'OpenAI API Key',
                'description': 'OpenAI API key for GPT models',
                'type': 'secret',
                'default': '${{ secrets.OPENAI_KEY }}',
                'category': 'AI Services'
            },
            {
                'key': 'ANTHROPIC_KEY',
                'label': 'Anthropic API Key',
                'description': 'Anthropic API key for Claude models',
                'type': 'secret',
                'default': '${{ secrets.ANTHROPIC_KEY }}',
                'category': 'AI Services'
            },
            {
                'key': 'GITHUB_TOKEN',
                'label': 'GitHub Token',
                'description': 'GitHub token for repository access',
                'type': 'secret',
                'default': '${{ secrets.GITHUB_TOKEN }}',
                'category': 'Authentication'
            },
            {
                'key': 'PYTHONPATH',
                'label': 'Python Path',
                'description': 'Python path for PR Agent code',
                'type': 'string',
                'default': '${{ github.workspace }}\\pr_agent_code',
                'category': 'Environment'
            },
            {
                'key': 'PYTHONUTF8',
                'label': 'Python UTF-8',
                'description': 'Force UTF-8 encoding in Python',
                'type': 'string',
                'default': '1',
                'category': 'Environment'
            },
            {
                'key': 'GITHUB_EVENT_PATH',
                'label': 'GitHub Event Path',
                'description': 'Path to the GitHub event file',
                'type': 'string',
                'default': '${{ github.event_path }}',
                'category': 'GitHub Context'
            },
            {
                'key': 'GITHUB_EVENT_NAME',
                'label': 'GitHub Event Name',
                'description': 'Name of the GitHub event',
                'type': 'string',
                'default': '${{ github.event_name }}',
                'category': 'GitHub Context'
            },
            {
                'key': 'OPENAI__KEY',
                'label': 'OpenAI Key (Alternative)',
                'description': 'Alternative OpenAI API key format',
                'type': 'secret',
                'default': '${{ secrets.OPENAI_KEY }}',
                'category': 'AI Services'
            },
            {
                'key': 'ANTHROPIC__KEY',
                'label': 'Anthropic Key (Alternative)',
                'description': 'Alternative Anthropic API key format',
                'type': 'secret',
                'default': '${{ secrets.ANTHROPIC_KEY }}',
                'category': 'AI Services'
            },
            {
                'key': 'CSHARP_CODE_CONTEXT_SERVICE__BASE_URL',
                'label': 'C# Code Context Service URL',
                'description': 'Base URL for C# code context service',
                'type': 'string',
                'default': 'https://localhost:7110',
                'category': 'Code Context'
            },
            {
                'key': 'CSHARP_CODE_CONTEXT_SERVICE__USERNAME',
                'label': 'C# Code Context Service Username',
                'description': 'Username for C# code context service',
                'type': 'string',
                'default': 'Skatamatic',
                'category': 'Code Context'
            },
            {
                'key': 'CSHARP_CODE_CONTEXT_SERVICE__PASSWORD',
                'label': 'C# Code Context Service Password',
                'description': 'Password for C# code context service',
                'type': 'secret',
                'default': '${{ secrets.CONTEXT_PASSWORD }}',
                'category': 'Code Context'
            },
            {
                'key': 'RUNNER_TOOL_CACHE',
                'label': 'Runner Tool Cache',
                'description': 'Tool cache directory for self-hosted runners',
                'type': 'string',
                'default': 'C:\\actions-runner\\toolcache',
                'category': 'Runner Configuration'
            }
        ]

    def parse_yaml_config(self, yaml_content: str) -> Dict[str, Any]:
        """Parse YAML config and extract environment variables"""
        try:
            config = yaml.safe_load(yaml_content)
            
            # Extract environment variables from the config
            env_vars = {}
            
            # Check if the config has the expected structure
            if 'jobs' in config:
                for job_name, job_config in config['jobs'].items():
                    # Extract variables from main env section
                    if 'env' in job_config:
                        env_vars.update(job_config['env'])
                    
                    # Extract dotted variables from PowerShell step
                    if 'steps' in job_config:
                        for step in job_config['steps']:
                            if (step.get('name') == 'Export environment variables with dots' and 
                                step.get('shell') == 'powershell' and 
                                'run' in step):
                                
                                # Parse the PowerShell commands to extract dotted variables
                                run_script = step['run']
                                # Look for lines like: Add-Content $env:GITHUB_ENV "KEY=value"
                                import re
                                for line in run_script.split('\n'):
                                    match = re.match(r'^\s*Add-Content\s+\$env:GITHUB_ENV\s+"([^=]+)=([^"]*)"', line)
                                    if match:
                                        key = match.group(1)
                                        value = match.group(2)
                                        env_vars[key] = value
            
            return {
                'success': True,
                'env_vars': env_vars,
                'config': config
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': f'Failed to parse YAML: {str(e)}'
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
                return """name: PRAgent on SelfHosted Runner (No Docker)

on:
  pull_request:
    types: [opened, reopened, ready_for_review]

jobs:
  pr_agent_job:
    if: ${{ github.event.sender.type != 'Bot' }}
    runs-on: [self-hosted, windows]
    permissions:
      issues: write
      pull-requests: write
      contents: write
    env:
      GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
      OPENAI_KEY: ${{ secrets.OPENAI_KEY }}
    steps:
    - name: Checkout PRAgent code
      uses: actions/checkout@v4
      with:
        repository: skatamatic/pr-agent
        ref: Dashboard
        path: pr_agent_code
    - name: Run PRAgent
      working-directory: pr_agent_code
      run: python pr_agent/servers/github_action_runner.py"""
    
    def get_default_env_vars(self) -> Dict[str, str]:
        """Get default environment variables"""
        return {
            'PYTHONPATH': '${{ github.workspace }}\\pr_agent_code',
            'RUNNER_TOOL_CACHE': 'C:\\actions-runner\\toolcache',
            'OPENAI_KEY': '${{ secrets.OPENAI_KEY }}',
            'OPENAI__KEY': '${{ secrets.OPENAI_KEY }}',
            'ANTHROPIC__KEY': '${{ secrets.ANTHROPIC_KEY }}',
            'ANTHROPIC_KEY': '${{ secrets.ANTHROPIC_KEY }}',
            'GITHUB_TOKEN': '${{ secrets.GITHUB_TOKEN }}',
            'CSHARP_CODE_CONTEXT_SERVICE__BASE_URL': 'https://localhost:7110',
            'CSHARP_CODE_CONTEXT_SERVICE__USERNAME': 'Skatamatic',
            'CSHARP_CODE_CONTEXT_SERVICE__PASSWORD': '${{ secrets.CONTEXT_PASSWORD }}',
            'GITHUB_EVENT_PATH': '${{ github.event_path }}',
            'GITHUB_EVENT_NAME': '${{ github.event_name }}',
            'PYTHONUTF8': '1'
        }