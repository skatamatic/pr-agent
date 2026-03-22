import asyncio
import json
import smtplib
import aiohttp
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Any
from models import NotificationConfig, NotificationEvent
from config import settings, internal_log_ingest_headers

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, database):
        self.database = database
        self.enabled_services = {}
        self.load_configurations()

    @staticmethod
    def _normalize_service_type(value: Optional[str]) -> str:
        return (value or "").strip().upper()

    @staticmethod
    def _normalize_event_type(value: Optional[str]) -> str:
        return (value or "").strip().upper()

    def load_configurations(self):
        """Load notification configurations from database"""
        try:
            configs = self.database.get_notification_configs()
            normalized: Dict[str, Dict[str, Any]] = {}
            for config in configs:
                if not config.get('enabled', False):
                    continue
                service_type = self._normalize_service_type(config.get('service_type'))
                if not service_type:
                    continue
                cfg = dict(config)
                cfg['service_type'] = service_type
                cfg['event_types'] = [self._normalize_event_type(t) for t in (cfg.get('event_types') or [])]
                normalized[service_type] = cfg
            self.enabled_services = normalized
        except Exception as e:
            logger.error(f"Failed to load notification configurations: {e}")
            self.enabled_services = {}

    async def send_notification(self, event_type: str, event_data: Dict[str, Any], repositories: List[str] = None):
        """Send notifications for a specific event to all configured services"""
        print(f"DEBUG: send_notification called with event_type={event_type}")
        logger.info(f"DEBUG: send_notification method entry point reached")
        
        try:
            logger.info(f"Starting notification send for event_type: {event_type}")
            
            # Create notification event record
            event = {
                'event_type': event_type,
                'event_data': event_data,
                'repositories': repositories or [],
                'timestamp': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Created event record: {event}")
            
            # Save event to database
            event_id = None
            try:
                logger.info("About to save event to database")
                saved_event = self.database.save_notification_event(event)
                event_id = saved_event.get('id')
                logger.info(f"Event saved to database successfully with ID: {event_id}")
            except Exception as e:
                logger.error(f"Failed to save event to database: {e}")
                import traceback
                logger.error(f"Database save traceback: {traceback.format_exc()}")
                # Don't raise - continue with notification sending even if database save fails
                logger.info("Continuing with notification despite database save failure")

            logger.info(f"Enabled services: {list(self.enabled_services.keys())}")

            # Track which services we're sending to and their results
            sent_to_services = []
            delivery_status = {}
            
            # Send to all enabled services that are configured for this event type
            tasks = []
            service_tasks = []  # Keep track of service types for result mapping
            
            for service_type, config in self.enabled_services.items():
                logger.info(f"Checking service {service_type} for event {event_type}")
                if self._should_send_notification(config, event_type, repositories):
                    logger.info(f"Sending to {service_type}")
                    sent_to_services.append(service_type)
                    
                    if service_type == 'TEAMS':
                        tasks.append(self._send_teams_notification(config, event))
                        service_tasks.append(service_type)
                    elif service_type == 'SLACK':
                        tasks.append(self._send_slack_notification(config, event))
                        service_tasks.append(service_type)
                    elif service_type == 'EMAIL':
                        tasks.append(self._send_email_notification(config, event))
                        service_tasks.append(service_type)
                else:
                    logger.info(f"Skipping {service_type} - should_send returned False")

            if tasks:
                logger.info(f"Executing {len(tasks)} notification tasks")
                results = await asyncio.gather(*tasks, return_exceptions=True)
                logger.info(f"Notification results: {results}")
                
                # Map results to delivery status
                for i, result in enumerate(results):
                    service_type = service_tasks[i]
                    if isinstance(result, Exception):
                        delivery_status[service_type] = f"error: {str(result)}"
                    elif result is True:
                        delivery_status[service_type] = "success"
                    else:
                        delivery_status[service_type] = "failed"
                
                success = not any(isinstance(r, Exception) or r is False for r in results)
            else:
                logger.warning("No notification tasks to execute")
                success = False

            # Update the event in the database with processing results
            if event_id:
                try:
                    self.database.update_notification_event(event_id, {
                        'sent_to_services': sent_to_services,
                        'delivery_status': delivery_status,
                        'processed': True
                    })
                    logger.info(f"Updated event {event_id} with processing results")
                    
                    # Log system activity for successful notifications
                    if sent_to_services:
                        services_list = ", ".join(sent_to_services)
                        self._log_to_system("INFO", f"Notification sent for {event_type} event to {services_list}")
                    
                except Exception as e:
                    logger.error(f"Failed to update event {event_id}: {e}")

            return success

        except Exception as e:
            logger.error(f"Failed to send notification for event {event_type}: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False

    def _should_send_notification(self, config: dict, event_type: str, repositories: List[str]) -> bool:
        """Check if notification should be sent based on configuration"""
        normalized_event_type = self._normalize_event_type(event_type)
        # Special case: always send TEST notifications for testing purposes
        if normalized_event_type == 'TEST':
            logger.info(f"Allowing TEST event type for testing")
            return True
            
        # Check if event type is enabled
        configured_types = [self._normalize_event_type(t) for t in (config.get('event_types', []) or [])]
        if normalized_event_type not in configured_types:
            logger.info(f"Event type {normalized_event_type} not in configured types: {configured_types}")
            return False
        
        # Check repository filter
        repo_filter = config.get('repository_filter', [])
        if repo_filter and repositories:
            # If repository filter is set, at least one repository must match
            match = any(repo in repo_filter for repo in repositories)
            logger.info(f"Repository filter check: {repositories} vs {repo_filter} = {match}")
            return match
        
        logger.info(f"Notification should be sent for {event_type}")
        return True

    async def _send_teams_notification(self, config: dict, event: dict):
        """Send notification to Microsoft Teams"""
        try:
            webhook_url = config.get('webhook_url')
            if not webhook_url:
                logger.error("Teams webhook URL not configured")
                self._log_to_system("ERROR", f"Teams notification failed: webhook URL not configured")
                return False

            message = self._format_teams_message(event)
            if message is None:
                logger.info(f"Skipping Teams notification for event {event['event_type']} - not significant")
                return True  # Return True to indicate "handled" even though we skipped
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook_url, json=message) as response:
                    if 200 <= response.status < 300:
                        logger.info(f"Teams notification sent successfully for event {event['event_type']}")
                        self._log_to_system("INFO", f"Teams notification sent successfully for {event['event_type']} event")
                        return True
                    else:
                        body = await response.text()
                        logger.error(f"Failed to send Teams notification: {response.status} body={body[:300]}")
                        self._log_to_system("ERROR", f"Teams notification failed with status {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Error sending Teams notification: {e}")
            self._log_to_system("ERROR", f"Teams notification error: {str(e)}")
            return False

    def _log_to_system(self, level: str, message: str):
        """Create a system log entry for notification events"""
        try:
            # Import requests to send log directly to dashboard
            import requests
            
            # Create a system log entry
            log_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': f"[NOTIFICATION] {message}",
                'source': 'notification_system',
                'job_id': None,  # System logs don't have job IDs  
                'operation_id': None,  # System logs don't have operation IDs
                'repository': None,
                'status': None
            }
            
            # Send directly to dashboard backend - this will also broadcast via WebSocket
            try:
                backend_url = getattr(settings, 'backend_base_url', 'http://localhost:8000')
                requests.post(
                    f'{backend_url.rstrip("/")}/logs/immediate',
                    json=log_data,
                    headers=internal_log_ingest_headers(),
                    timeout=1,
                )
            except:
                pass  # Don't fail if dashboard is not available
            
        except Exception as e:
            logger.error(f"Failed to create system log: {e}")

    async def _send_slack_notification(self, config: dict, event: dict):
        """Send notification to Slack"""
        try:
            webhook_url = config.get('webhook_url')
            if not webhook_url:
                logger.error("Slack webhook URL not configured")
                self._log_to_system("ERROR", f"Slack notification failed: webhook URL not configured")
                return False

            message = self._format_slack_message(event, config.get('channel', ''))
            if message is None:
                logger.info(f"Skipping Slack notification for event {event['event_type']} - not significant")
                return True  # Return True to indicate "handled" even though we skipped
            
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(webhook_url, json=message) as response:
                    if 200 <= response.status < 300:
                        logger.info(f"Slack notification sent successfully for event {event['event_type']}")
                        self._log_to_system("INFO", f"Slack notification sent successfully for {event['event_type']} event")
                        return True
                    else:
                        body = await response.text()
                        logger.error(f"Failed to send Slack notification: {response.status} body={body[:300]}")
                        self._log_to_system("ERROR", f"Slack notification failed with status {response.status}")
                        return False

        except Exception as e:
            logger.error(f"Error sending Slack notification: {e}")
            self._log_to_system("ERROR", f"Slack notification error: {str(e)}")
            return False

    async def _send_email_notification(self, config: dict, event: dict):
        """Send email notification"""
        try:
            required_fields = ['smtp_server', 'smtp_port', 'email_username', 'email_password', 'recipient_emails']
            if not all(config.get(field) for field in required_fields):
                logger.error("Email configuration incomplete")
                self._log_to_system("ERROR", f"Email notification failed: configuration incomplete")
                return False

            message = self._format_email_message(event, config)
            if message is None:
                logger.info(f"Skipping Email notification for event {event['event_type']} - not significant")
                return True  # Return True to indicate "handled" even though we skipped
            
            # Use asyncio to run the synchronous SMTP operation
            result = await asyncio.get_event_loop().run_in_executor(
                None, self._send_smtp_email, config, message, event['event_type']
            )
            return result

        except Exception as e:
            logger.error(f"Error sending email notification: {e}")
            self._log_to_system("ERROR", f"Email notification error: {str(e)}")
            return False

    def _send_smtp_email(self, config: dict, message: MIMEMultipart, event_type: str):
        """Send email via SMTP (synchronous)"""
        try:
            smtp_port = int(config['smtp_port'])
            if smtp_port == 465:
                server_ctx = smtplib.SMTP_SSL(config['smtp_server'], smtp_port, timeout=15)
            else:
                server_ctx = smtplib.SMTP(config['smtp_server'], smtp_port, timeout=15)

            with server_ctx as server:
                if smtp_port in [587, 25]:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                if config.get('email_username') and config.get('email_password'):
                    server.login(config['email_username'], config['email_password'])
                server.send_message(message)
                logger.info(f"Email notification sent successfully")
                self._log_to_system("INFO", f"Email notification sent successfully for {event_type} event")
                return True
        except Exception as e:
            logger.error(f"SMTP email sending failed: {e}")
            self._log_to_system("ERROR", f"Email notification SMTP error: {str(e)}")
            return False

    def _format_teams_message(self, event: dict) -> Dict[str, Any]:
        """Format message for Microsoft Teams"""
        event_details = self._get_event_details(event)
        if event_details is None:
            return None  # Skip this notification
            
        title, color, summary = event_details
        
        return {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "themeColor": color,
            "summary": summary,
            "sections": [{
                "activityTitle": title,
                "activitySubtitle": f"PR-Agent Dashboard - {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC",
                "facts": self._get_event_facts(event),
                "markdown": True
            }]
        }

    def _format_slack_message(self, event: dict, channel: str = None) -> Dict[str, Any]:
        """Format message for Slack"""
        event_details = self._get_event_details(event)
        if event_details is None:
            return None  # Skip this notification
            
        title, color, summary = event_details
        
        message = {
            "text": summary,
            "attachments": [{
                "color": color,
                "title": title,
                "fields": [
                    {"title": field["name"], "value": field["value"], "short": True}
                    for field in self._get_event_facts(event)
                ],
                "footer": "PR-Agent Dashboard",
                "ts": int(datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00')).timestamp())
            }]
        }
        
        if channel:
            message["channel"] = channel
            
        return message

    def _format_email_message(self, event: dict, config: dict) -> MIMEMultipart:
        """Format email message"""
        event_details = self._get_event_details(event)
        if event_details is None:
            return None  # Skip this notification
            
        title, color, summary = event_details
        
        msg = MIMEMultipart()
        msg['From'] = config['email_username']
        msg['To'] = ', '.join(config['recipient_emails'])
        msg['Subject'] = f"PR-Agent: {title}"

        # HTML email body
        html_body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: {color}; color: white; padding: 15px; border-radius: 5px 5px 0 0;">
                    <h2 style="margin: 0;">{title}</h2>
                    <p style="margin: 5px 0 0 0; opacity: 0.9;">PR-Agent Dashboard Notification</p>
                </div>
                <div style="background: #f9f9f9; padding: 20px; border-radius: 0 0 5px 5px; border: 1px solid #ddd;">
                    <p><strong>Summary:</strong> {summary}</p>
                    <hr style="border: none; height: 1px; background: #ddd; margin: 15px 0;">
                    <h3>Event Details:</h3>
                    <ul>
        """
        
        for fact in self._get_event_facts(event):
            html_body += f"<li><strong>{fact['name']}:</strong> {fact['value']}</li>"
        
        html_body += f"""
                    </ul>
                    <hr style="border: none; height: 1px; background: #ddd; margin: 15px 0;">
                    <p style="color: #666; font-size: 0.9em;">
                        Sent at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_body, 'html'))
        return msg

    def _get_event_details(self, event: dict) -> tuple:
        """Get event title, color, and summary based on event type"""
        event_data = event['event_data']
        
        if event['event_type'] == 'NEW_JOB':
            job_type = event_data.get('job_type', 'Unknown')
            repository = event_data.get('repository', 'unknown repository')
            pr_url = event_data.get('pr_url', '')
            trigger_user = event_data.get('trigger_user', 'System')
            
            title = f"🚀 New {job_type.title()} Job Started"
            if pr_url:
                pr_number = pr_url.split('/')[-1] if pr_url else 'Unknown'
                summary = f"**{trigger_user}** started a {job_type} job for **{repository}** (PR #{pr_number})"
            else:
                summary = f"**{trigger_user}** started a {job_type} job for **{repository}**"
            
            return (title, "#4CAF50", summary)
            
        elif event['event_type'] == 'JOB_SUCCESS':
            job_type = event_data.get('job_type', 'Unknown')
            repository = event_data.get('repository', 'unknown repository')
            duration = event_data.get('duration')
            pr_url = event_data.get('pr_url', '')
            
            title = f"✅ {job_type.title()} Job Completed Successfully"
            duration_text = f" in {self._format_duration(duration)}" if duration else ""
            if pr_url:
                pr_number = pr_url.split('/')[-1] if pr_url else 'Unknown'
                summary = f"Job for **{repository}** (PR #{pr_number}) completed successfully{duration_text}"
            else:
                summary = f"Job for **{repository}** completed successfully{duration_text}"
            
            return (title, "#4CAF50", summary)
            
        elif event['event_type'] == 'JOB_FAILURE':
            job_type = event_data.get('job_type', 'Unknown')
            repository = event_data.get('repository', 'unknown repository')
            error_details = event_data.get('error_details', '')
            pr_url = event_data.get('pr_url', '')
            duration = event_data.get('duration')
            
            title = f"❌ {job_type.title()} Job Failed"
            duration_text = f" after {self._format_duration(duration)}" if duration else ""
            if pr_url:
                pr_number = pr_url.split('/')[-1] if pr_url else 'Unknown'
                summary = f"Job for **{repository}** (PR #{pr_number}) failed{duration_text}"
            else:
                summary = f"Job for **{repository}** failed{duration_text}"
            
            if error_details:
                summary += f"\n**Error:** {error_details}"
            
            return (title, "#F44336", summary)
            
        elif event['event_type'] == 'OPERATION_FAILURE':
            operation_type = event_data.get('operation_type', 'Unknown')
            repository = event_data.get('repository', 'unknown repository')
            error_details = event_data.get('error_details', '')
            
            title = f"⚠️ {operation_type.title()} Operation Failed"
            summary = f"**{operation_type}** operation failed for **{repository}**"
            if error_details:
                summary += f"\n**Error:** {error_details}"
            
            return (title, "#FF9800", summary)
            
        elif event['event_type'] == 'SYSTEM_HEALTH_CHANGE':
            service = event_data.get('service', 'unknown service')
            status = event_data.get('current_status') or event_data.get('status', 'unknown')
            error_details = event_data.get('error_details', '')
            previous_status = event_data.get('previous_status', '')
            endpoint = event_data.get('endpoint', '')
            
            # Don't send notifications for transitions to/from "unknown" unless it's a real issue
            if status == 'unknown' or previous_status == 'unknown':
                # Skip notifications for initial "unknown" states or temporary unknowns
                if not error_details and (not previous_status or previous_status in ['connected', 'healthy']):
                    return None  # Signal to skip this notification
            
            if status in ['error', 'unhealthy', 'unreachable', 'misconfigured']:
                title = f"🔴 System Health Alert: {service.replace('_', ' ').title()}"
                color = "#F44336"
                if previous_status and previous_status not in ['unknown', status]:
                    summary = f"**{service.replace('_', ' ').title()}** health degraded from **{previous_status}** to **{status}**"
                else:
                    summary = f"**{service.replace('_', ' ').title()}** is now **{status}**"
                
                if error_details:
                    summary += f"\n**Issue:** {error_details}"
                if endpoint:
                    summary += f"\n**Endpoint:** {endpoint}"
                
                summary += f"\n**Action needed:** Check service configuration and connectivity"
                
            elif status in ['warning', 'degraded']:
                title = f"🟡 System Health Warning: {service.replace('_', ' ').title()}"
                color = "#FF9800"
                summary = f"**{service.replace('_', ' ').title()}** is experiencing issues (status: **{status}**)"
                if error_details:
                    summary += f"\n**Details:** {error_details}"
                    
            else:  # healthy, recovered, connected
                # Only notify about recovery if coming from a problematic state
                if previous_status and previous_status in ['error', 'unhealthy', 'unreachable', 'warning', 'degraded', 'misconfigured']:
                    title = f"🟢 System Health Recovered: {service.replace('_', ' ').title()}"
                    color = "#4CAF50"
                    summary = f"**{service.replace('_', ' ').title()}** has recovered from **{previous_status}** to **{status}**"
                else:
                    # Don't notify for normal healthy states
                    return None  # Signal to skip this notification
            
            return (title, color, summary)
            
        elif event['event_type'] in ['TEST_NOTIFICATION', 'TEST']:
            return (
                f"🧪 Test Notification - {event_data.get('service_type', 'Unknown').title()}",
                "#2196F3",
                event_data.get('message', 'Test notification from PR-Agent Dashboard - configuration is working correctly!')
            )
        else:
            return (
                f"📋 {event['event_type'].replace('_', ' ').title()}",
                "#9E9E9E",
                f"A {event['event_type'].replace('_', ' ').lower()} event occurred"
            )
    
    def _format_duration(self, duration):
        """Format duration in a human-readable way"""
        if not duration:
            return "unknown time"
        
        seconds = int(duration)
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            minutes = seconds // 60
            remaining_seconds = seconds % 60
            return f"{minutes}m {remaining_seconds}s"
        else:
            hours = seconds // 3600
            remaining_minutes = (seconds % 3600) // 60
            return f"{hours}h {remaining_minutes}m"

    def _get_event_facts(self, event: dict) -> List[Dict[str, str]]:
        """Get event facts for display with smart formatting"""
        event_data = event['event_data']
        facts = [
            {"name": "🕒 Timestamp", "value": datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S UTC')}
        ]
        
        # Event-specific intelligent facts
        if event['event_type'] in ['NEW_JOB', 'JOB_SUCCESS', 'JOB_FAILURE']:
            if event_data.get('repository'):
                facts.append({"name": "📁 Repository", "value": event_data['repository']})
            if event_data.get('pr_url'):
                pr_number = event_data['pr_url'].split('/')[-1] if event_data['pr_url'] else 'Unknown'
                facts.append({"name": "🔀 Pull Request", "value": f"#{pr_number}"})
                facts.append({"name": "🔗 PR Link", "value": event_data['pr_url']})
            if event_data.get('trigger_user'):
                facts.append({"name": "👤 Triggered By", "value": event_data['trigger_user']})
            if event_data.get('job_type'):
                facts.append({"name": "⚙️ Job Type", "value": event_data['job_type'].title()})
            if event_data.get('duration'):
                facts.append({"name": "⏱️ Duration", "value": self._format_duration(event_data['duration'])})
            if event_data.get('started_at'):
                start_time = datetime.fromisoformat(event_data['started_at'].replace('Z', '+00:00'))
                facts.append({"name": "🚀 Started At", "value": start_time.strftime('%H:%M:%S UTC')})
            if event_data.get('completed_at'):
                end_time = datetime.fromisoformat(event_data['completed_at'].replace('Z', '+00:00'))
                facts.append({"name": "🏁 Completed At", "value": end_time.strftime('%H:%M:%S UTC')})
                
        elif event['event_type'] == 'OPERATION_FAILURE':
            if event_data.get('operation_type'):
                facts.append({"name": "🔧 Operation", "value": event_data['operation_type'].title()})
            if event_data.get('repository'):
                facts.append({"name": "📁 Repository", "value": event_data['repository']})
            if event_data.get('error_details'):
                facts.append({"name": "❌ Error Details", "value": event_data['error_details']})
                
        elif event['event_type'] == 'SYSTEM_HEALTH_CHANGE':
            if event_data.get('service'):
                facts.append({"name": "🔧 Service", "value": event_data['service'].replace('_', ' ').title()})
            if event_data.get('status'):
                status_emoji = {"healthy": "🟢", "warning": "🟡", "error": "🔴", "unreachable": "🔴", "disabled": "⚪"}.get(event_data['status'], "⚫")
                facts.append({"name": "📊 Current Status", "value": f"{status_emoji} {event_data['status'].title()}"})
            if event_data.get('previous_status'):
                prev_emoji = {"healthy": "🟢", "warning": "🟡", "error": "🔴", "unreachable": "🔴", "disabled": "⚪"}.get(event_data['previous_status'], "⚫")
                facts.append({"name": "📈 Previous Status", "value": f"{prev_emoji} {event_data['previous_status'].title()}"})
            if event_data.get('endpoint'):
                facts.append({"name": "🌐 Endpoint", "value": event_data['endpoint']})
            if event_data.get('error_details'):
                facts.append({"name": "🚨 Error Details", "value": event_data['error_details']})
            if event_data.get('last_checked'):
                check_time = datetime.fromisoformat(event_data['last_checked'].replace('Z', '+00:00'))
                facts.append({"name": "🔍 Last Checked", "value": check_time.strftime('%H:%M:%S UTC')})
                
        else:
            # Fallback to generic facts for unknown event types
            for key, value in event_data.items():
                if key not in ['timestamp'] and value is not None:
                    # Smart key formatting
                    display_key = key.replace('_', ' ').title()
                    icon_map = {
                        'Job Id': '🆔', 'Operation Id': '🆔', 'Repository': '📁', 
                        'Status': '📊', 'Error Details': '❌', 'Message': '💬',
                        'Service Type': '🔧', 'Duration': '⏱️'
                    }
                    icon = icon_map.get(display_key, '📋')
                    facts.append({"name": f"{icon} {display_key}", "value": str(value)})
        
        if event.get('repositories'):
            facts.append({"name": "📂 Affected Repositories", "value": ", ".join(event['repositories'])})
            
        return facts

    # Configuration management methods
    def save_notification_config(self, config: dict) -> bool:
        """Save notification configuration"""
        try:
            self.database.save_notification_config(config)
            self.load_configurations()  # Reload configurations
            return True
        except Exception as e:
            logger.error(f"Failed to save notification config: {e}")
            return False

    def get_notification_configs(self) -> List[dict]:
        """Get all notification configurations"""
        try:
            return self.database.get_notification_configs()
        except Exception as e:
            logger.error(f"Failed to get notification configs: {e}")
            return []

    def delete_notification_config(self, config_id: int) -> bool:
        """Delete notification configuration"""
        try:
            self.database.delete_notification_config(config_id)
            self.load_configurations()  # Reload configurations
            return True
        except Exception as e:
            logger.error(f"Failed to delete notification config: {e}")
            return False

    async def test_notification_config(self, config: dict) -> bool:
        """Test a notification configuration by sending a test message"""
        try:
            # Log test start
            self._log_to_system("INFO", f"Testing {config['service_type']} notification configuration")

            # Test ONLY the provided config (even if disabled), not all enabled services.
            event = {
                'event_type': 'TEST',
                'event_data': {
                    "title": "Test Notification",
                    "message": "This is a test notification from PR-Agent Dashboard",
                    "service_type": config['service_type'],
                    "job_id": f"test-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    "repository": "test/repository",
                    "status": "success"
                },
                'repositories': ["test/repository"],
                'timestamp': datetime.utcnow().isoformat()
            }

            service_type = self._normalize_service_type(config.get('service_type'))
            cfg = dict(config)
            cfg['service_type'] = service_type

            if service_type == 'TEAMS':
                return await self._send_teams_notification(cfg, event)
            if service_type == 'SLACK':
                return await self._send_slack_notification(cfg, event)
            if service_type == 'EMAIL':
                return await self._send_email_notification(cfg, event)

            logger.error(f"Unsupported notification service type for test: {service_type}")
            return False
        except Exception as e:
            logger.error(f"Test notification failed: {e}")
            self._log_to_system("ERROR", f"Test notification failed: {str(e)}")
            return False 