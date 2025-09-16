# pr_agent/algo/csharp_context_client.py
import httpx
import json
import ssl
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger

async def _login_and_get_service_token(client: httpx.AsyncClient, service_settings: dict) -> str | None:
    """
    Logs into the C# context service and returns an API token.
    """
    login_url = service_settings.base_url.rstrip('/') + "/api/auth/login"
    username = service_settings.get("username")
    password = service_settings.get("password")

    if not username or not password:
        get_logger().error("[Context] - C# context service username or password not configured in settings.")
        return None

    login_payload = {"username": username, "password": password}
    
    # DANGEROUS DEBUG LOGGING - REMOVE AFTER DEBUGGING
    get_logger().info(f"[Context] DEBUG LOGIN - URL: {login_url}")
    get_logger().info(f"[Context] DEBUG LOGIN - Username: {username}")
    get_logger().info(f"[Context] DEBUG LOGIN - Password: {password}")
    get_logger().info(f"[Context] DEBUG LOGIN - Full payload: {json.dumps(login_payload, indent=2)}")
    
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
    
async def get_csharp_minimal_context(owner: str, repo_name: str, pr_number: int, access_token: str) -> dict | None:
    service_settings = get_settings().csharp_code_context_service
    if not service_settings.get("enabled", False):
        return None

    base_url = service_settings.base_url.rstrip('/')
    analyze_endpoint = f"{base_url}/api/analyze"

    if not access_token: # This is the access token for your service to access the repo
        get_logger().error("[Context] - Access token (for repo access by C# service) is not available.")
        return None
    
    # Determine source control type based on git provider setting
    git_provider_type = get_settings().config.get("git_provider", "github").lower()
    is_github = git_provider_type == "github"
    
    get_logger().info(f"[Context] - Using source control type: {'GitHub' if is_github else 'Azure DevOps'} (git_provider={git_provider_type})")

    # For local development with self-signed certificates
    ssl_context = ssl.create_default_context()
    ssl_context.check_hostname = False
    ssl_context.verify_mode = ssl.CERT_NONE

    async with httpx.AsyncClient(timeout=service_settings.timeout, verify=ssl_context) as client:
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
        
        payload_for_analysis = {
            "sourceControlConnectionInfo": source_control_info,
            "prNumber": pr_number,
            "depth": service_settings.default_depth,
            "mode": service_settings.default_mode
        }
        
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