import json
import asyncio
from typing import Dict, Any, Optional
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


class DashboardSink:
    """
    Custom Loguru sink for sending logs to an AI dashboard system.
    Captures status updates, context, errors, and full logs.
    """
    
    def __init__(self, 
                 dashboard_url: Optional[str] = None,
                 api_key: Optional[str] = None,
                 batch_size: int = 10,
                 flush_interval: float = 5.0):
        self.dashboard_url = dashboard_url or get_settings().get("DASHBOARD.URL")
        self.api_key = api_key or get_settings().get("DASHBOARD.API_KEY")
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.log_buffer = []
        self.session = None
        self._flush_task = None
        
    def __call__(self, message):
        """
        Loguru sink function - called for each log message (MUST be synchronous)
        """
        try:
            record = message.record
            log_entry = self._format_log_entry(record)
            
            # Add to buffer
            self.log_buffer.append(log_entry)
            
            # Try to handle async operations
            async_handled = False
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Send immediately for errors or status updates (including EXCEPTION logs)
                    if record["level"].name in ["ERROR", "CRITICAL", "EXCEPTION"] or self._is_status_update(record):
                        asyncio.create_task(self._send_immediately(log_entry))
                    
                    # Batch send for other logs
                    if len(self.log_buffer) >= self.batch_size:
                        asyncio.create_task(self._flush_buffer())
                    
                    async_handled = True
                else:
                    # No event loop running, try to create one for this operation
                    self._manual_flush_if_needed()
            except RuntimeError:
                # No event loop available, use manual flush
                self._manual_flush_if_needed()
                
        except Exception as e:
            # Don't let dashboard logging break the main application
            print(f"Dashboard sink error: {e}")
            import traceback
            traceback.print_exc()
    
    def _format_log_entry(self, record):
        """Convert loguru record to dashboard log entry format"""
        
        # Get current step for automatic prefixing
        current_step = None
        try:
            from pr_agent.log.job_context import JobContext
            current_step = JobContext.get_current_step()
        except Exception:
            pass  # Ignore errors getting current step
        
        # Extract basic log information
        timestamp = record["time"].timestamp()
        level = record["level"].name
        
        # Get the raw message before any prefixing
        raw_message = record["message"]
        
        # Apply automatic step prefixing if:
        # 1. We have a current step
        # 2. The message doesn't already have a step prefix
        # 3. The message doesn't start with common system prefixes
        message = raw_message
        if (current_step and 
            not self._has_existing_prefix(raw_message) and
            not self._is_system_message(raw_message)):
            message = f"[{current_step}] - {raw_message}"
        
        # Extract context from extra fields
        extra = record.get("extra", {})
        
        log_entry = {
            "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
            "level": level,
            "message": message,
            "module": record.get("name", "unknown"),
            "function": record.get("function", "unknown"),
            "line": record.get("line", 0),
            "source": "pr_agent",
        }
        
        # Add context from extra fields
        context_fields = [
            "job_id", "operation_id", "command", "repo", "pr_url", 
            "installation_id", "sender", "request_id", "status"
        ]
        
        for field in context_fields:
            if field in extra:
                log_entry[field] = extra[field]
        
        # Handle artifacts (complex data structures)
        if "artifacts" in extra:
            artifacts = extra["artifacts"]
            if isinstance(artifacts, dict):
                # Store artifacts as separate field for structured display
                log_entry["artifacts"] = artifacts
                
                # Convert artifacts to a formatted string representation for message text
                formatted_artifacts = self._format_artifacts_for_message(artifacts)
                if formatted_artifacts:
                    log_entry["message"] += f" | Artifacts: {formatted_artifacts}"
        
        return log_entry

    def _has_existing_prefix(self, message: str) -> bool:
        """Check if message already has a step prefix"""
        if not message:
            return False
        
        # Check for existing step prefixes
        step_prefixes = ['[Context]', '[Generating]', '[Reflecting]', '[Publishing]', '[DevTime]', '[AI]']
        return any(message.startswith(prefix) for prefix in step_prefixes)
    
    def _is_system_message(self, message: str) -> bool:
        """Check if this is a system message that shouldn't get step prefixes"""
        if not message:
            return False
        
        # System message patterns that shouldn't get step prefixes
        system_patterns = [
            '[NOTIFICATION]', '[RETENTION]', '[HEALTH]', '[SYSTEM]',
            'Dashboard', 'WebSocket', 'HTTP', 'Database', 'Cache',
            'Starting comprehensive', 'Operation completed', 'Job completed',
            'AI metrics updated', 'Metrics recalculated'
        ]
        return any(pattern in message for pattern in system_patterns)
    
    def _format_artifacts_for_message(self, extra: Dict[str, Any]) -> str:
        """
        Format artifacts into readable text for appending to log messages
        """
        artifacts_parts = []
        
        # Handle single artifact
        artifact = extra.get("artifact")
        if artifact is not None:
            if isinstance(artifact, dict):
                # Format dict artifacts as key-value pairs
                formatted_dict = []
                for key, value in artifact.items():
                    if isinstance(value, (dict, list)):
                        # For complex values, format as JSON but compact
                        try:
                            value_str = json.dumps(value, separators=(',', ':'))
                            # Increased limit for better debugging, especially for estimation inputs
                            if len(value_str) > 2000:
                                value_str = value_str[:1997] + "..."
                        except:
                            value_str = str(value)[:2000]
                    else:
                        value_str = str(value)
                    formatted_dict.append(f"{key}={value_str}")
                artifacts_parts.append("Artifact: " + ", ".join(formatted_dict))
            else:
                # For simple artifacts, just convert to string
                artifact_str = str(artifact)
                # Increased limit for better debugging
                if len(artifact_str) > 2000:
                    artifact_str = artifact_str[:1997] + "..."
                artifacts_parts.append(f"Artifact: {artifact_str}")
        
        # Handle multiple artifacts
        artifacts = extra.get("artifacts")
        if artifacts is not None and isinstance(artifacts, dict):
            formatted_artifacts = []
            for key, value in artifacts.items():
                if isinstance(value, (dict, list)):
                    # For complex values, format as JSON but compact
                    try:
                        value_str = json.dumps(value, separators=(',', ':'))
                        # Increased limit for better debugging, especially for estimation inputs
                        if len(value_str) > 2000:
                            value_str = value_str[:1997] + "..."
                    except:
                        value_str = str(value)[:2000]
                else:
                    value_str = str(value)
                formatted_artifacts.append(f"{key}={value_str}")
            
            if formatted_artifacts:
                artifacts_parts.append("Artifacts: " + ", ".join(formatted_artifacts))
        
        return " | ".join(artifacts_parts)
    
    def _extract_status(self, record: Dict[str, Any]) -> Optional[str]:
        """
        Extract status information from log messages based on actual pr-agent patterns
        """
        message = record["message"].lower()
        extra = record.get("extra", {})
        
        # Direct status from context
        if "status" in extra:
            return extra["status"]
            
        # Infer status from actual message patterns found in the codebase
        status_patterns = {
            # Starting operations
            "starting": [
                "pr-agent request handler started",
                "generating a pr description for pr_id",
                "reviewing pr:",
                "generating code suggestions for pr"
            ],
            
            # Code context operations
            "fetching_context": [
                "fetching context...",
                "requesting c# context for pr:",
                "attempting login to c# context service",
                "calling c# context service for analysis",
                "csharp_code_context_service is enabled and this diff is a csharp one"
            ],
            
            "context_completed": [
                "got context!",
                "successfully received context",
                "successfully logged into c# context service",
                "c# context map"
            ],
            
            "context_disabled": [
                "context fetch is disabled",
                "c# context service is disabled"
            ],
            
            "context_failed": [
                "failed to get c# context",
                "failed to obtain api token from c# context service",
                "login to c# context service failed",
                "http error from c# codecontextservice",
                "exception during c# context service login"
            ],
            
            # Preparation phases  
            "preparing": [
                "preparing review...",
                "preparing pr description...",
                "preparing suggestions..."
            ],
            
            # Processing phases
            "processing": [
                "pr diff",
                "ai response:",
                "system:",
                "user:"
            ],
            
            # Self-reflection (specific to code suggestions)
            "self_reflecting": [
                "self reflect", 
                "reflecting",
                "validating suggestions"
            ],
            
            # Publishing/output phases
            "publishing": [
                "pr output",
                "published labels",
                "publishing comment",
                "publish_comment"
            ],
            
            # Completion states
            "completed": [
                "generated successfully",
                "review output is not published",
                "code suggestions generated for pr, but not published"
            ],
            
            # Skip/no action states
            "skipped": [
                "pr has no files:",
                "skipping",
                "no code suggestions found",
                "no changes found"
            ],
            
            # Error states are handled by log level
        }
        
        # Handle errors by log level (including EXCEPTION logs)
        if record["level"].name in ["ERROR", "CRITICAL", "EXCEPTION"]:
            return "failed"
        
        # Check for specific patterns
        for status, keywords in status_patterns.items():
            if any(keyword in message for keyword in keywords):
                return status
                
        # Check for analytics events - these often indicate status changes
        if extra.get("analytics", False):
            return "analytics_event"
                
        return None
    
    def _extract_error_info(self, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Extract error information from log records
        """
        # Include EXCEPTION logs as errors since they'll be converted to ERROR level
        if record["level"].name not in ["ERROR", "CRITICAL", "EXCEPTION"]:
            return None
            
        # Convert EXCEPTION to ERROR for consistency
        level_name = record["level"].name
        if level_name == "EXCEPTION":
            level_name = "ERROR"
            
        error_info = {
            "level": level_name,
            "message": record["message"],
        }
        
        # Add exception info if available
        if record.get("exception"):
            error_info["exception"] = {
                "type": record["exception"]["type"],
                "value": record["exception"]["value"],
                "traceback": record["exception"]["traceback"]
            }
            
        # Add artifact if it contains error details
        extra = record.get("extra", {})
        if "artifact" in extra and isinstance(extra["artifact"], dict):
            if "error" in extra["artifact"] or "traceback" in extra["artifact"]:
                error_info["details"] = extra["artifact"]
        
        # Also check artifacts field for error details        
        if "artifacts" in extra and isinstance(extra["artifacts"], dict):
            error_details = {}
            for key, value in extra["artifacts"].items():
                if "error" in key.lower() or "exception" in key.lower() or "traceback" in key.lower():
                    error_details[key] = value
            if error_details:
                error_info["artifacts_details"] = error_details
                
        return error_info
    
    def _is_status_update(self, record: Dict[str, Any]) -> bool:
        """
        Check if this is a status update that should be sent immediately
        """
        extra = record.get("extra", {})
        
        # Explicit status updates
        if "status" in extra:
            return True
            
        # Analytics events (often status-related)
        if extra.get("analytics", False):
            return True
            
        # Important operation starts/ends
        status_keywords = [
            "starting", "completed", "finished", "failed",
            "processing pr", "generating", "publishing"
        ]
        
        message = record["message"].lower()
        return any(keyword in message for keyword in status_keywords)
    
    async def _send_immediately(self, log_entry: Dict[str, Any]):
        """
        Send log entry immediately (for errors and status updates)
        """
        try:
            # Use dashboard client instead of direct HTTP
            from pr_agent.log.dashboard_client import get_dashboard_client
            
            client = get_dashboard_client()
            if client:
                await client.send_log(log_entry)
                    
        except Exception as e:
            # Silent failure - don't break the main application
            pass
    
    async def _flush_buffer(self):
        """
        Send buffered logs to dashboard
        """
        if not self.log_buffer:
            return
            
        try:
            # Use dashboard client instead of direct HTTP
            from pr_agent.log.dashboard_client import get_dashboard_client
            
            client = get_dashboard_client()
            if client:
                logs_to_send = self.log_buffer.copy()
                
                success = await client.send_logs_batch(logs_to_send)
                if success:
                    self.log_buffer.clear()
                    
        except Exception as e:
            # Silent failure - don't break the main application
            pass
    
    async def start_flush_timer(self):
        """
        Start periodic flushing of log buffer
        """
        # Don't start if already running
        if self._flush_task and not self._flush_task.done():
            return
            
        async def flush_periodically():
            try:
                while True:
                    await asyncio.sleep(self.flush_interval)
                    await self._flush_buffer()
            except asyncio.CancelledError:
                # Task was cancelled, clean exit
                pass
            except Exception as e:
                # Log error but don't crash
                pass
                
        self._flush_task = asyncio.create_task(flush_periodically())
    
    async def close(self):
        """
        Clean up resources
        """
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass  # Expected when cancelling
            
        await self._flush_buffer()  # Final flush
        
        if self.session:
            await self.session.close()

    def _manual_flush_if_needed(self):
        """Manual flush when no event loop is available"""
        try:
            # If buffer is getting full or we have important logs, try to flush
            if len(self.log_buffer) >= self.batch_size:
                # Try to run the flush using synchronous requests
                try:
                    # Use requests library for synchronous HTTP when no event loop is available
                    import requests
                    import json
                    from pr_agent.log.dashboard_client import get_dashboard_client
                    
                    client = get_dashboard_client()
                    if client and client._enabled:
                        logs_to_send = self.log_buffer.copy()
                        
                        # Use synchronous requests instead of aiohttp
                        headers = {"Content-Type": "application/json"}
                        if client.api_key:
                            headers["Authorization"] = f"Bearer {client.api_key}"
                        
                        url = f"{client.dashboard_url.rstrip('/')}/logs/batch"
                        batch_data = {'logs': logs_to_send}
                        
                        response = requests.post(
                            url,
                            json=batch_data,
                            headers=headers,
                            timeout=10
                        )
                        
                        if response.status_code == 200:
                            self.log_buffer.clear()
                        
                except Exception as e:
                    # Silent failure - don't break the main application
                    pass
        except Exception as e:
            # Silent failure - don't break the main application
            pass


# Global dashboard sink instance
_dashboard_sink = None

def get_dashboard_sink() -> Optional[DashboardSink]:
    """Get the global dashboard sink instance"""
    return _dashboard_sink

def setup_dashboard_sink(dashboard_url: Optional[str] = None, api_key: Optional[str] = None) -> Optional[DashboardSink]:
    """
    Setup and register the dashboard sink with Loguru
    """
    global _dashboard_sink
    
    if _dashboard_sink:
        return _dashboard_sink
        
    _dashboard_sink = DashboardSink(dashboard_url, api_key)
    
    # Add the sink to Loguru
    handler_id = logger.add(
        _dashboard_sink,
        level="DEBUG",
        format="{message}",  # We handle formatting in the sink
        colorize=False,
        serialize=False,
        catch=True,  # Don't let dashboard errors crash the app
        enqueue=True,  # Use async queue for better performance
    )
    
    # Start the periodic flush timer (only if event loop is running)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Store the task reference to prevent warnings
            task = loop.create_task(_dashboard_sink.start_flush_timer())
            # Add weak reference to prevent circular dependencies
            _dashboard_sink._flush_task = task
    except RuntimeError:
        # No event loop running yet, will start later when needed
        pass
    
    return _dashboard_sink

async def cleanup_dashboard_sink():
    """
    Cleanup the dashboard sink and any running tasks
    """
    global _dashboard_sink
    
    if _dashboard_sink:
        try:
            await _dashboard_sink.close()
        except Exception as e:
            # Silent cleanup - don't break shutdown
            pass 