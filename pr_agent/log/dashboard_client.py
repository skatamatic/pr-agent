"""
Dashboard Client - Interface for PR-Agent to communicate with the Dashboard API
Provides simple methods for job and operation management.
Environment overrides: DASHBOARD_URL, DASHBOARD_API_KEY (for GCP/container deployment).

Metrics endpoints (use exactly one per logical update to avoid duplicate dashboard writes):
- ``POST /api/operations/{id}/ai-metrics`` — single primary model, legacy ``input_tokens`` /
  ``output_tokens``, optional ``estimated_dev_hours_saved``. Use for one-model flows.
- ``POST /api/operations/{id}/multi-model-ai-metrics`` — body ``models_data`` mapping model name
  to ``{input_tokens, output_tokens}``, optional ``estimated_dev_hours_saved``. Use when multiple
  models contribute to the same operation in one payload.
"""
import asyncio
import json
import os
from typing import Dict, Any, Optional, List
from datetime import datetime

try:
    import aiohttp
except ImportError:
    aiohttp = None

try:
    from loguru import logger
except ImportError:
    logger = None

from pr_agent.config_loader import get_settings


def _is_local_dashboard_url(url: Optional[str]) -> bool:
    value = (url or "").strip().lower()
    if not value:
        return True
    return "localhost" in value or "127.0.0.1" in value or value.startswith("http://0.0.0.0")


def _resolve_dashboard_url(override_url: Optional[str] = None) -> Optional[str]:
    candidates: List[str] = []
    if override_url:
        candidates.append(str(override_url).strip())
    env_url = (os.getenv("DASHBOARD_URL", "") or "").strip()
    if env_url:
        candidates.append(env_url)
    env_nested = (os.getenv("DASHBOARD__URL", "") or "").strip()
    if env_nested:
        candidates.append(env_nested)

    try:
        settings = get_settings()
        dash_obj = settings.get("DASHBOARD", {}) if settings else {}
        if isinstance(dash_obj, dict):
            for key in ("url", "URL"):
                val = (dash_obj.get(key) or "").strip()
                if val:
                    candidates.append(val)
        direct = (settings.get("DASHBOARD.URL") or "").strip() if settings else ""
        if direct:
            candidates.append(direct)
    except Exception:
        pass

    # Prefer first non-localhost candidate when available.
    for candidate in candidates:
        if candidate and not _is_local_dashboard_url(candidate):
            return candidate
    for candidate in candidates:
        if candidate:
            return candidate
    return None


class DashboardClient:
    """Client for communicating with the PR-Agent Dashboard API"""
    
    def __init__(self, dashboard_url: Optional[str] = None, api_key: Optional[str] = None):
        self.dashboard_url = _resolve_dashboard_url(dashboard_url)
        self.api_key = (
            api_key
            or os.getenv("DASHBOARD_API_KEY")
            or get_settings().get("DASHBOARD.API_KEY")
        )
        self.session = None
        self._enabled = bool(self.dashboard_url)
        
    async def _get_session(self):
        """Get or create aiohttp session"""
        if not self.session:
            if aiohttp is None:
                raise ImportError("aiohttp is required for dashboard client")
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def _make_request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """Make HTTP request to dashboard API"""
        if not self._enabled:
            return None
            
        try:
            session = await self._get_session()
            
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            url = f"{self.dashboard_url.rstrip('/')}/{endpoint.lstrip('/')}"
            
            async with session.request(
                method,
                url,
                json=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10)
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    # Get response body for better error reporting
                    try:
                        error_body = await response.text()
                    except:
                        error_body = "Unable to read response body"
                    
                    if logger:
                        logger.warning(f"Dashboard API request failed: {response.status} - {endpoint} - {error_body}")
                    return None
                    
        except Exception as e:
            if logger:
                logger.warning(f"Dashboard API request error: {e}")
            return None
    
    async def create_job(self, 
                        job_type: str,
                        source: str,
                        repository: Optional[str] = None,
                        pr_url: Optional[str] = None,
                        trigger_user: Optional[str] = None,
                        trigger_event: Optional[str] = None,
                        installation_id: Optional[str] = None,
                        request_id: Optional[str] = None,
                        webhook_payload: Optional[Dict[str, Any]] = None,
                        job_id: Optional[str] = None) -> Optional[str]:
        """Create a new job and return its job_id with retry logic"""
        import asyncio
        
        job_data = {
            'job_type': job_type,
            'source': source,
            'repository': repository,
            'pr_url': pr_url,
            'trigger_user': trigger_user,
            'trigger_event': trigger_event,
            'installation_id': installation_id,
            'request_id': request_id,
            'webhook_payload': webhook_payload,
            'job_id': job_id
        }
        
        # Remove None values
        job_data = {k: v for k, v in job_data.items() if v is not None}
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                response = await self._make_request('POST', '/api/jobs/create', job_data)
                if response and response.get('data'):
                    job_id_result = response['data'].get('job_id')
                    if job_id_result:
                        if logger:
                            logger.info(f"✅ Dashboard job creation successful (async) for job {job_id_result} (attempt {attempt + 1})")
                        return job_id_result
                
                # If we get here, the response was not successful
                if logger:
                    logger.warning(f"⚠️ Dashboard job creation failed (async): Invalid response (attempt {attempt + 1}/{max_retries})")
                
            except Exception as e:
                if logger:
                    logger.warning(f"⚠️ Dashboard job creation exception (async): {e} (attempt {attempt + 1}/{max_retries})")
            
            # Exponential backoff before retry (except on last attempt)
            if attempt < max_retries - 1:
                delay = 0.5 * (2 ** attempt)  # 0.5s, 1s, 2s
                await asyncio.sleep(delay)
        
        # If all retries failed, log a BIG ERROR
        error_msg = f"""
🚨🚨🚨 CRITICAL DASHBOARD ERROR (ASYNC) 🚨🚨🚨
❌ FAILED TO CREATE JOB IN DASHBOARD AFTER {max_retries} RETRIES!
❌ Job ID: {job_id or 'Unknown'}
❌ Repository: {repository or 'Unknown'}
❌ Job Type: {job_type}
❌ This will cause orphaned operations and dashboard inconsistency!
❌ Please check dashboard connectivity and API endpoints!
🚨🚨🚨 CRITICAL DASHBOARD ERROR (ASYNC) 🚨🚨🚨
"""
        if logger:
            logger.error(error_msg)
        else:
            print(error_msg)  # Fallback if logger is not available
            
        return None
    
    async def update_job_status(self, 
                               job_id: str, 
                               status: str, 
                               error_details: Optional[str] = None,
                               result_summary: Optional[Dict[str, Any]] = None) -> bool:
        """Update job status"""
        status_data = {
            'status': status,
            'error_details': error_details,
            'result_summary': result_summary
        }
        
        # Remove None values
        status_data = {k: v for k, v in status_data.items() if v is not None}
        
        response = await self._make_request('POST', f'/api/jobs/{job_id}/status', status_data)
        return response is not None
    
    async def create_operation(self,
                              job_id: str,
                              operation_type: str,
                              command: Optional[str] = None,
                              repo: Optional[str] = None,
                              pr_url: Optional[str] = None,
                              installation_id: Optional[str] = None,
                              sender: Optional[str] = None,
                              request_id: Optional[str] = None,
                              operation_id: Optional[str] = None) -> Optional[str]:
        """Create a new operation and return its operation_id"""
        operation_data = {
            'job_id': job_id,
            'operation_type': operation_type,
            'command': command,
            'repo': repo,
            'pr_url': pr_url,
            'installation_id': installation_id,
            'sender': sender,
            'request_id': request_id,
            'operation_id': operation_id
        }
        
        # Remove None values
        operation_data = {k: v for k, v in operation_data.items() if v is not None}
        
        response = await self._make_request('POST', '/api/operations/create', operation_data)
        if response and response.get('data'):
            return response['data'].get('operation_id')
        return None
    
    async def update_operation_status(self,
                                     operation_id: str,
                                     status: str,
                                     error_details: Optional[str] = None,
                                     result_data: Optional[Dict[str, Any]] = None) -> bool:
        """Update operation status"""
        status_data = {
            'status': status,
            'error_details': error_details,
            'result_data': result_data
        }
        
        # Remove None values
        status_data = {k: v for k, v in status_data.items() if v is not None}
        
        response = await self._make_request('POST', f'/api/operations/{operation_id}/status', status_data)
        return response is not None
    
    async def update_operation_ai_metrics(self,
                                         operation_id: str,
                                         model_used: Optional[str] = None,
                                         input_tokens: Optional[int] = None,
                                         output_tokens: Optional[int] = None,
                                         estimated_dev_hours_saved: Optional[float] = None) -> bool:
        """Update operation AI/LLM metrics"""
        metrics_data = {
            'model_used': model_used,
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'estimated_dev_hours_saved': estimated_dev_hours_saved
        }
        
        # Remove None values
        metrics_data = {k: v for k, v in metrics_data.items() if v is not None}
        
        if not metrics_data:
            return True  # Nothing to update
        
        response = await self._make_request('POST', f'/api/operations/{operation_id}/ai-metrics', metrics_data)
        return response is not None
    
    async def send_log(self, log_data: Dict[str, Any]) -> bool:
        """Send a single log entry to the dashboard"""
        if not self._enabled:
            return False
            
        response = await self._make_request('POST', '/logs/immediate', log_data)
        return response is not None
    
    async def send_logs_batch(self, logs: List[Dict[str, Any]]) -> bool:
        """Send a batch of log entries to the dashboard"""
        if not self._enabled or not logs:
            return False
            
        batch_data = {'logs': logs}
        response = await self._make_request('POST', '/logs/batch', batch_data)
        return response is not None
    
    async def close(self):
        """Close the client session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def update_operation_multi_model_ai_metrics(self, operation_id: str, models_data: Dict[str, Dict[str, int]], 
                                                     estimated_dev_hours_saved: Optional[float] = None):
        """Update operation multi-model AI metrics"""
        if not self._enabled:
            return
        
        try:
            metrics_data = {
                'models_data': models_data,
                'estimated_dev_hours_saved': estimated_dev_hours_saved
            }
            # Remove None values
            metrics_data = {k: v for k, v in metrics_data.items() if v is not None}
            
            if not metrics_data:
                return  # Nothing to update
            
            url = f"{self.dashboard_url.rstrip('/')}/api/operations/{operation_id}/multi-model-ai-metrics"
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=metrics_data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        logger.debug(f"Dashboard multi-model AI metrics update successful for {operation_id}")
                    else:
                        logger.debug(f"Dashboard multi-model AI metrics update failed: {response.status}")
                        
        except Exception as e:
            logger.debug(f"Dashboard multi-model AI metrics update failed for {operation_id}: {e}")

    async def update_operation_step(self, operation_id: str, current_step: str):
        """Update operation current step"""
        if not self._enabled:
            return
        
        try:
            step_data = {'current_step': current_step}
            
            url = f"{self.dashboard_url.rstrip('/')}/api/operations/{operation_id}/step"
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=step_data, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status == 200:
                        logger.debug(f"Dashboard operation step update successful for {operation_id}")
                    else:
                        logger.debug(f"Dashboard operation step update failed: {response.status}")
                        
        except Exception as e:
            logger.debug(f"Dashboard operation step update failed for {operation_id}: {e}")

    async def update_operation_insights(self, insights: Dict[str, Any]):
        """Update operation insights"""
        if not self._enabled:
            if logger:
                logger.debug("Dashboard client not enabled for insights update")
            return
        
        try:
            from pr_agent.log.job_context import JobContext
            operation_id = JobContext.get_current_operation_id()
            
            if not operation_id:
                if logger:
                    logger.warning("No operation ID available for insights update - insights will not be saved!")
                return
            
            insights_data = {'insights': insights}
            
            url = f"{self.dashboard_url.rstrip('/')}/api/operations/{operation_id}/insights"
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            
            async with aiohttp.ClientSession() as session:
                async with session.put(url, json=insights_data, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        if logger:
                            logger.info(f"Dashboard insights update successful for {operation_id}")
                    else:
                        if logger:
                            logger.warning(f"Dashboard insights update failed: {response.status} - {await response.text()}")
                        
        except Exception as e:
            if logger:
                logger.warning(f"Dashboard insights update failed: {e}")
                import traceback
                logger.warning(f"Dashboard insights traceback: {traceback.format_exc()}")


# Global dashboard client instance
_dashboard_client = None

# Check if dashboard integration is available
try:
    DASHBOARD_AVAILABLE = True
except Exception:
    DASHBOARD_AVAILABLE = False

def get_dashboard_client() -> Optional[DashboardClient]:
    """Get the global dashboard client instance"""
    global _dashboard_client
    
    # Auto-initialize if not yet created
    if _dashboard_client is None:
        _dashboard_client = setup_dashboard_client()
    
    return _dashboard_client

def setup_dashboard_client(dashboard_url: Optional[str] = None, api_key: Optional[str] = None) -> Optional[DashboardClient]:
    """Setup the global dashboard client with error resilience"""
    global _dashboard_client
    
    if _dashboard_client:
        return _dashboard_client
    
    try:
        _dashboard_client = DashboardClient(dashboard_url, api_key)
        
        # Test if dashboard integration is enabled
        if _dashboard_client._enabled:
            if logger:
                logger.info(f"Dashboard client initialized - URL: {_dashboard_client.dashboard_url}")
        else:
            if logger:
                logger.info("Dashboard integration disabled - no URL configured")
                
        return _dashboard_client
        
    except Exception as e:
        if logger:
            logger.warning(f"Failed to setup dashboard client: {e}")
        # Create a disabled client to prevent None checks everywhere
        _dashboard_client = DashboardClient(None, None)
        return _dashboard_client

# Convenience functions for common operations
async def create_job_from_context(job_type: str, source: str, **kwargs) -> Optional[str]:
    """Create a job using the global client"""
    client = get_dashboard_client()
    if client:
        return await client.create_job(job_type, source, **kwargs)
    return None

async def update_job_status_from_context(job_id: str, status: str, **kwargs) -> bool:
    """Update job status using the global client"""
    client = get_dashboard_client()
    if client:
        return await client.update_job_status(job_id, status, **kwargs)
    return False

async def create_operation_from_context(job_id: str, operation_type: str, **kwargs) -> Optional[str]:
    """Create an operation using the global client"""
    client = get_dashboard_client()
    if client:
        return await client.create_operation(job_id, operation_type, **kwargs)
    return None

async def update_operation_status_from_context(operation_id: str, status: str, **kwargs) -> bool:
    """Update operation status using the global client"""
    client = get_dashboard_client()
    if client:
        return await client.update_operation_status(operation_id, status, **kwargs)
    return False

async def update_operation_ai_metrics_from_context(operation_id: str, **kwargs) -> bool:
    """Update operation AI metrics using the global client"""
    client = get_dashboard_client()
    if client:
        return await client.update_operation_ai_metrics(operation_id, **kwargs)
    return False 