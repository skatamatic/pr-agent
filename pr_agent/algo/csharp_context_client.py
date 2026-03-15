# pr_agent/algo/csharp_context_client.py
import httpx
import json
import os
import ssl
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger

def _get_base_url(service_settings) -> str:
    """Resolve context service base URL from settings (supports 'url' or 'base_url' key)."""
    if hasattr(service_settings, "get"):
        url = service_settings.get("base_url") or service_settings.get("url")
    else:
        url = getattr(service_settings, "base_url", None) or getattr(service_settings, "url", None)
    return (url or "").rstrip("/")


async def _login_and_get_service_token(client: httpx.AsyncClient, service_settings) -> str | None:
    """
    Logs into the C# context service and returns an API token.
    """
    base_url = _get_base_url(service_settings)
    if not base_url:
        get_logger().error("[Context] - C# context service URL not configured in settings.")
        return None
    login_url = base_url + "/api/auth/login"
    # Prefer .get() when available (dict-like/Dynaconf) so None/missing is handled correctly
    if hasattr(service_settings, "get"):
        username = service_settings.get("username")
        password = service_settings.get("password")
    else:
        username = getattr(service_settings, "username", None)
        password = getattr(service_settings, "password", None)

    if not username or not password:
        get_logger().error("[Context] - C# context service username or password not configured in settings.")
        return None

    login_payload = {"username": username, "password": password}

    try:
        response = await client.post(login_url, json=login_payload)
        response.raise_for_status() # Will raise an exception for 4xx/5xx errors
        token_data = response.json()
        service_token = token_data.get("token")
        if not service_token:
            get_logger().error("[Context] - Token not found in C# context service login response.", artifact=token_data)
            return None
        return service_token
    except httpx.HTTPStatusError as e:
        get_logger().error(f"[Context] - Login to C# context service failed: {e.response.status_code} - {e.response.text}")
        return None
    except Exception as e:
        get_logger().error(f"[Context] - Exception during C# context service login: {e}", exc_info=True)
        return None


def _build_analysis_payload(source_control_info: dict, owner: str, repo_name: str, pr_number: int, access_token: str, depth: int, mode: str) -> dict:
    """Build a payload compatible with both legacy and current CodeContextService APIs."""
    is_github = bool(source_control_info.get("isGitHub", True))
    if is_github:
        legacy_owner = source_control_info.get("owner") or owner
    else:
        # For Azure DevOps legacy shape, owner should be the project/workspace.
        legacy_owner = source_control_info.get("project") or owner
        if not legacy_owner:
            legacy_owner = source_control_info.get("owner")
    return {
        # New contract
        "sourceControlConnectionInfo": source_control_info,
        "prNumber": pr_number,
        "depth": depth,
        "mode": mode,
        # Legacy contract
        "token": access_token,
        "owner": legacy_owner,
        "repo": repo_name,
    }


def _resolve_source_control_type() -> str:
    """Resolve provider with Azure runtime signals taking precedence over config drift."""
    provider = str(get_settings().config.get("git_provider", "github")).lower()
    if provider in ("azure", "azuredevops", "azure_devops"):
        return "azure"
    # Azure pipeline runtime indicator
    if os.getenv("SYSTEM_COLLECTIONURI"):
        return "azure"
    return "github"


async def get_csharp_minimal_context(owner: str, repo_name: str, pr_number: int, access_token: str) -> dict | None:
    service_settings = get_settings().csharp_code_context_service
    if not service_settings.get("enabled", False):
        return None

    base_url = _get_base_url(service_settings)
    if not base_url:
        get_logger().error("[Context] - C# context service URL not configured in settings.")
        return None
    analyze_endpoint = f"{base_url}/api/analyze"

    if not access_token: # This is the access token for your service to access the repo
        get_logger().error("[Context] - Access token (for repo access by C# service) is not available.")
        return None
    
    # Determine source control type; prefer runtime Azure signals over stale config.
    git_provider_type = _resolve_source_control_type()
    is_github = git_provider_type == "github"
    
    get_logger().info(f"[Context] - Using source control type: {'GitHub' if is_github else 'Azure DevOps'} (git_provider={git_provider_type})")

    # For local development with self-signed certificates
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    timeout = service_settings.get("timeout", 180) if hasattr(service_settings, "get") else getattr(service_settings, "timeout", 180)
    async with httpx.AsyncClient(timeout=timeout, verify=ssl_context) as client:
        # Login to get the service API token
        service_api_token = await _login_and_get_service_token(client, service_settings)
        if not service_api_token:
            get_logger().error("[Context] - Failed to obtain API token from C# context service. Cannot proceed with analysis.")
            return None

        headers = {"Authorization": f"Bearer {service_api_token}"}

        # Build the new API payload format
        if is_github:
            # GitHub format
            source_control_info = {
                "isGitHub": True,
                "token": access_token,
                "org": "",  # GitHub doesn't use org in this context
                "owner": owner,
                "project": "",  # GitHub doesn't use project
                "repo": repo_name
            }
        else:
            # Azure DevOps format
            # Get the organization from Azure DevOps settings (set by pipeline runner)
            azure_org_setting = get_settings().azure_devops.get("org", "")
            if azure_org_setting and azure_org_setting.startswith("https://"):
                # Extract organization name from URL like "https://mdt-software.visualstudio.com"
                org = azure_org_setting.rstrip('/').split('/')[-1]
            else:
                org = azure_org_setting if azure_org_setting else ""
            
            # For Azure DevOps, owner is the workspace/project from the PR URL parsing
            project = owner if owner else ""
            
            source_control_info = {
                "isGitHub": False,
                "token": access_token,
                "org": org,  # Organization name (e.g., "mdt-software")
                "owner": org,  # In Azure DevOps, owner is typically the same as org
                "project": project,  # Project name (e.g., "Product")
                "repo": repo_name
            }
        
        depth = service_settings.get("default_depth", 1) if hasattr(service_settings, "get") else getattr(service_settings, "default_depth", 1)
        mode = service_settings.get("default_mode", "Minified") if hasattr(service_settings, "get") else getattr(service_settings, "default_mode", "Minified")

        payload_for_analysis = _build_analysis_payload(
            source_control_info=source_control_info,
            owner=owner,
            repo_name=repo_name,
            pr_number=pr_number,
            access_token=access_token,
            depth=depth,
            mode=mode,
        )
        
        # Log context service request
        get_logger().debug(f"[Context] - Requesting analysis for {owner}/{repo_name} PR #{pr_number}")
        get_logger().debug(f"[Context] - API payload: {json.dumps(payload_for_analysis, indent=2)}")

        try:
            response = await client.post(analyze_endpoint, json=payload_for_analysis, headers=headers)
            response.raise_for_status()

            api_response_data = response.json()
            # Process service logs with appropriate log levels
            logs = api_response_data.get("logs", [])
            for log_entry in logs:
                log_lower = log_entry.lower()
                
                # Special case: Never treat "flat analysis complete complete" as an error
                # (it contains source code that might accidentally trigger error keywords)
                if "flat analysis complete complete" in log_lower:
                    get_logger().debug(f"[Context] {log_entry}")
                elif any(keyword in log_lower for keyword in ['error', 'fail', 'exception']):
                    # Only log actual errors as errors
                    get_logger().error(f"[Context] {log_entry}")
                elif any(keyword in log_lower for keyword in ['complete', 'success', 'finished', 'done']):
                    # Log completion/success messages as debug (less verbose)
                    get_logger().debug(f"[Context] {log_entry}")
                elif any(keyword in log_lower for keyword in ['warn', 'warning']):
                    # Log warnings appropriately
                    get_logger().warning(f"[Context] {log_entry}")
                # Skip other log entries to avoid spam

            analysis_result = api_response_data.get("result", None)

            if isinstance(analysis_result, dict):
                # Summary log only
                get_logger().info(f"[Context] - C# context retrieved for {len(analysis_result)} file(s)")
                return analysis_result
            elif analysis_result is None:
                return {}
            else:
                get_logger().error(f"[Context] - C# CodeContextService API returned unexpected format for 'result'. Expected dict, got {type(analysis_result)}.")
                return None

        except httpx.HTTPStatusError as e:
            get_logger().error(f"[Context] - HTTP error from C# CodeContextService (analysis): {e.response.status_code} - {e.response.text}")
            return None
        except httpx.RequestError as e:
            get_logger().error(f"[Context] - Request error calling C# CodeContextService (analysis): {e}")
            return None
        except Exception as e:
            get_logger().error(f"[Context] - Error processing C# CodeContextService (analysis) response: {e}", exc_info=True)
            return None