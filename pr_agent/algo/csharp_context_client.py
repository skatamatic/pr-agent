# pr_agent/algo/csharp_context_client.py
from __future__ import annotations

import asyncio
import httpx
import json
import os
import ssl
from typing import Any
from urllib.parse import urlparse

from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger

# Process-wide cache keyed by _make_context_cache_key(...). Safe across concurrent asyncio
# tasks: identical keys share one HTTP fetch. Different PRs use different keys.
# reset_csharp_context_cache_for_job() clears entries (e.g. between sequential jobs if desired).
_context_results: dict[tuple[Any, ...], dict | None] = {}
_context_inflight: dict[tuple[Any, ...], asyncio.Task] = {}


def reset_csharp_context_cache_for_job() -> None:
    """
    Clear in-memory C# context cache and in-flight trackers.

    Call between jobs if you reuse the same worker process and need to drop stale
    entries; otherwise keys already include owner/repo/PR and coalesce correctly.
    """
    _context_results.clear()
    _context_inflight.clear()


def _make_context_cache_key(
    owner: str, repo_name: str, pr_number: int, access_token: str | None
) -> tuple[Any, ...]:
    """
    Hashable key for everything that affects the /api/analyze payload for this call.

    Same owner/repo/PR/token with same settings + source-control resolution => one fetch.
    """
    service_settings = get_settings().csharp_code_context_service
    if hasattr(service_settings, "get"):
        depth = service_settings.get("default_depth", 1)
        mode = str(service_settings.get("default_mode", "Minified"))
    else:
        depth = getattr(service_settings, "default_depth", 1)
        mode = str(getattr(service_settings, "default_mode", "Minified"))

    sc = _resolve_source_control_type()
    token = access_token or ""

    if sc == "azure":
        azure_org_setting = ""
        try:
            azure_org_setting = get_settings().azure_devops.get("org", "") or ""
        except Exception:
            pass
        azure_org_setting = azure_org_setting or os.getenv("SYSTEM_COLLECTIONURI", "")
        org, collection_uri = _normalize_azure_org_and_collection(azure_org_setting)
        azure_bits = (org, collection_uri)
    else:
        azure_bits = ("", "")

    try:
        depth_int = int(depth)
    except (TypeError, ValueError):
        depth_int = 1

    return (
        owner,
        repo_name,
        int(pr_number),
        token,
        sc,
        depth_int,
        mode,
        azure_bits,
    )

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


def _normalize_azure_org_and_collection(azure_org_setting: str) -> tuple[str, str]:
    """
    Normalize Azure org and collection URI from either:
    - full collection URI (https://dev.azure.com/{org}/ or https://{org}.visualstudio.com/)
    - plain org string ({org})
    """
    raw = (azure_org_setting or "").strip()
    if not raw:
        return "", ""

    if raw.startswith("https://") or raw.startswith("http://"):
        parsed = urlparse(raw)
        host = (parsed.hostname or "").lower()
        path_parts = [p for p in (parsed.path or "").split("/") if p]
        org = ""
        if host.endswith(".visualstudio.com"):
            org = host.split(".")[0]
            collection_uri = f"{parsed.scheme}://{host}"
        elif host == "dev.azure.com":
            org = path_parts[0] if path_parts else ""
            collection_uri = f"{parsed.scheme}://{host}/{org}" if org else f"{parsed.scheme}://{host}"
        else:
            # Fallback for uncommon host styles
            org = path_parts[0] if path_parts else (host.split(".")[0] if host else "")
            collection_uri = f"{parsed.scheme}://{host}"
        return org, collection_uri.rstrip("/")

    # Plain org name provided
    org = raw.strip("/")
    return org, f"https://dev.azure.com/{org}"


async def _fetch_csharp_minimal_context_impl(
    owner: str, repo_name: str, pr_number: int, access_token: str
) -> dict | None:
    """Perform HTTP login + analyze (uncached)."""
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
            # Get organization/collection from Azure settings or pipeline runtime.
            azure_org_setting = (
                get_settings().azure_devops.get("org", "")
                or os.getenv("SYSTEM_COLLECTIONURI", "")
            )
            org, collection_uri = _normalize_azure_org_and_collection(azure_org_setting)
            
            # For Azure DevOps, owner is the workspace/project from the PR URL parsing
            project = owner if owner else ""
            
            source_control_info = {
                "isGitHub": False,
                "token": access_token,
                "org": org,  # Organization name (e.g., "mdt-software")
                "owner": org,  # In Azure DevOps, owner is typically the same as org
                "project": project,  # Project name (e.g., "Product")
                "repo": repo_name,
                # Extra explicit fields for service variants that need the collection URL.
                "collectionUri": collection_uri,
                "organizationUrl": collection_uri,
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


_cache_lock = asyncio.Lock()


async def get_csharp_minimal_context(
    owner: str, repo_name: str, pr_number: int, access_token: str
) -> dict | None:
    """
    Fetch minimal C# analysis context from the configured service.

    Identical requests in the same process (same owner/repo/PR/token and same
    settings-derived payload) are served from an in-memory cache so callers
    such as ``get_pr_diff`` and ``get_pr_context`` do not each trigger a
    duplicate HTTP round-trip. Concurrent awaiters coalesce to a single fetch.
    """
    service_settings = get_settings().csharp_code_context_service
    if not service_settings.get("enabled", False):
        return None

    key = _make_context_cache_key(owner, repo_name, pr_number, access_token)
    results = _context_results
    inflight = _context_inflight

    if key in results:
        get_logger().debug(
            "[Context] - Reusing in-memory C# context cache for %s/%s PR#%s",
            owner,
            repo_name,
            pr_number,
        )
        return results[key]

    async with _cache_lock:
        if key in results:
            return results[key]
        if key in inflight:
            task = inflight[key]
        else:

            async def _run_fetch() -> dict | None:
                try:
                    res = await _fetch_csharp_minimal_context_impl(
                        owner, repo_name, pr_number, access_token
                    )
                    async with _cache_lock:
                        results[key] = res
                    return res
                finally:
                    async with _cache_lock:
                        inflight.pop(key, None)

            task = asyncio.create_task(_run_fetch())
            inflight[key] = task

    return await task