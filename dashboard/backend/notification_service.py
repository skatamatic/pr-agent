import asyncio
import json
import smtplib
import aiohttp
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(self, database):
        self.database = database
        self.enabled_services = {}
        self.load_configurations()

    def load_configurations(self):
        """Load notification configurations from database"""
        try:
            configs = self.database.get_notification_configs()
            self.enabled_services = {
                config['service_type']: config for config in configs if config.get('enabled', False)
            }
        except Exception as e:
            logger.error(f"Failed to load notification configurations: {e}")
            self.enabled_services = {}

    async def send_notification(self, event_type: str, event_data: Dict[str, Any], repositories: List[str] = None):
        """Send notifications for a specific event to all configured services"""
        try:
            # Create notification event record
            event = {
                'event_type': event_type,
                'event_data': event_data,
                'repositories': repositories or [],
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Save event to database
            self.database.save_notification_event(event)

            # Send to all enabled services that are configured for this event type
            tasks = []
            services_to_notify = []
            
            for service_type, config in self.enabled_services.items():
                if self._should_send_notification(config, event_type, repositories):
                    services_to_notify.append(service_type)
                    if service_type.upper() == 'TEAMS':
                        tasks.append(self._send_teams_notification(config, event))
                    elif service_type.upper() == 'SLACK':
                        tasks.append(self._send_slack_notification(config, event))
                    elif service_type.upper() == 'EMAIL':
                        tasks.append(self._send_email_notification(config, event))

            if tasks:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log results and create system logs
                success_count = sum(1 for result in results if result is True)
                failed_count = len(results) - success_count
                
                if success_count > 0:
                    await self._log_to_system(
                        'INFO',
                        f"Notification sent successfully to {success_count} service(s) for {event_type}",
                        {'event_type': event_type, 'services': services_to_notify[:success_count], 'repositories': repositories}
                    )
                
                if failed_count > 0:
                    await self._log_to_system(
                        'ERROR', 
                        f"Failed to send notification to {failed_count} service(s) for {event_type}",
                        {'event_type': event_type, 'failed_services': services_to_notify[success_count:], 'repositories': repositories}
                    )
                
                return success_count > 0
            else:
                # No services configured - this is not an error
                return True

        except Exception as e:
            await self._log_to_system(
                'ERROR',
                f"Notification system error for {event_type}: {str(e)}",
                {'event_type': event_type, 'error': str(e), 'repositories': repositories}
            )
            return False

    async def _log_to_system(self, level: str, message: str, metadata: dict = None):
        """Log notification events to the main system logs"""
        try:
            from datetime import datetime
            import json
            
            # Create a system log entry
            log_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': message,
                'source': 'notification_system',
                'job_id': None,  # System logs don't have job IDs
                'operation_id': None,  # System logs don't have operation IDs
                'repository': None,  # Could be multiple repositories
                'metadata': json.dumps(metadata) if metadata else None
            }
            
            # Save to logs database (this will be handled by the log service)
            # For now, we'll use the standard logger which should be captured by the dashboard
            logger.log(getattr(logging, level), f"[NOTIFICATION] {message}", extra={'metadata': metadata})
            
        except Exception as e:
            # Fallback to basic logging if system logging fails
            logger.error(f"Failed to log notification event: {e}")

    def _should_send_notification(self, config: dict, event_type: str, repositories: List[str]) -> bool:
        """Check if notification should be sent based on configuration"""
        # Always allow TEST events (bypass filtering)
        if event_type == 'TEST':
            return True
            
        # Check if event type is enabled
        if event_type not in config.get('event_types', []):
            return False
        
        # Check repository filter
        repo_filter = config.get('repository_filter', [])
        if repo_filter and repositories:
            # If repository filter is set, at least one repository must match
            return any(repo in repo_filter for repo in repositories)
        
        return True

    async def _send_teams_notification(self, config: dict, event: dict):
        """Send notification to Microsoft Teams"""
        try:
            webhook_url = config.get('webhook_url')
            if not webhook_url:
                return False

            message = self._format_teams_message(event)
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=message) as response:
                    return response.status == 200

        except Exception:
            return False

    async def _send_slack_notification(self, config: dict, event: dict):
        """Send notification to Slack"""
        try:
            webhook_url = config.get('webhook_url')
            if not webhook_url:
                return False

            message = self._format_slack_message(event, config.get('channel'))
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=message) as response:
                    return response.status == 200

        except Exception:
            return False

    async def _send_email_notification(self, config: dict, event: dict):
        """Send notification via Email"""
        try:
            smtp_server = config.get('smtp_server')
            smtp_port = config.get('smtp_port', 587)
            email_username = config.get('email_username')
            email_password = config.get('email_password')
            recipient_emails = config.get('recipient_emails', [])
            
            if not all([smtp_server, email_username, email_password, recipient_emails]):
                return False

            title, _, summary = self._get_event_details(event)
            
            # Create message
            msg = MIMEMultipart()
            msg['From'] = email_username
            msg['To'] = ', '.join(recipient_emails)
            msg['Subject'] = title
            
            # Create HTML body
            html_body = f"""
            <html>
            <body>
                <h2>{title}</h2>
                <p>{summary}</p>
                <table border="1" cellpadding="5">
                    <tr><th>Property</th><th>Value</th></tr>
            """
            
            for fact in self._get_event_facts(event):
                html_body += f"<tr><td>{fact['name']}</td><td>{fact['value']}</td></tr>"
            
            html_body += """
                </table>
            </body>
            </html>
            """
            
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send email
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(email_username, email_password)
                server.send_message(msg)
                
            return True
            
        except Exception:
            return False

    def _format_teams_message(self, event: dict) -> Dict[str, Any]:
        """Format message for Microsoft Teams"""
        title, color, summary = self._get_event_details(event)
        
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
        title, color, summary = self._get_event_details(event)
        
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

    def _get_event_details(self, event: dict) -> tuple:
        """Get event title, color, and summary based on event type"""
        event_data = event['event_data']
        dashboard_url = "http://localhost:3000"  # TODO: Make this configurable
        
        if event['event_type'] in ['NEW_JOB', 'new_job']:
            job_id = event_data.get('job_id', '')
            job_link = f"{dashboard_url}?view=jobs&job={job_id}" if job_id else dashboard_url
            return (
                f"New Job Started: {event_data.get('job_type', 'Unknown')}",
                "#4CAF50",
                f"A new {event_data.get('job_type', 'unknown')} job has been started for {event_data.get('repository', 'unknown repository')}. View details: {job_link}"
            )
        elif event['event_type'] in ['JOB_FAILURE', 'job_failure']:
            job_id = event_data.get('job_id', '')
            job_link = f"{dashboard_url}?view=jobs&job={job_id}" if job_id else dashboard_url
            return (
                f"Job Failed: {event_data.get('job_type', 'Unknown')}",
                "#F44336",
                f"A {event_data.get('job_type', 'unknown')} job has failed for {event_data.get('repository', 'unknown repository')}. View details: {job_link}"
            )
        elif event['event_type'] in ['JOB_SUCCESS', 'job_success']:
            job_id = event_data.get('job_id', '')
            job_link = f"{dashboard_url}?view=jobs&job={job_id}" if job_id else dashboard_url
            return (
                f"Job Completed: {event_data.get('job_type', 'Unknown')}",
                "#4CAF50",
                f"A {event_data.get('job_type', 'unknown')} job has completed successfully for {event_data.get('repository', 'unknown repository')}. View details: {job_link}"
            )
        elif event['event_type'] in ['SYSTEM_HEALTH_CHANGE', 'system_health_change']:
            current_status = event_data.get('current_status', event_data.get('status', 'unknown'))
            service = event_data.get('service', 'unknown service')
            color = "#FF9800" if current_status == 'warning' else "#F44336" if current_status == 'error' else "#4CAF50"
            return (
                f"System Health Change: {service}",
                color,
                f"{service} status changed to {current_status}. View dashboard: {dashboard_url}"
            )
        elif event['event_type'] == 'TEST':
            return (
                f"Test Notification",
                "#2196F3",
                f"This is a test notification from PR Agent Dashboard. View dashboard: {dashboard_url}"
            )
        else:
            return (f"Event: {event['event_type']}", "#9E9E9E", f"An {event['event_type']} event occurred. View dashboard: {dashboard_url}")

    def _get_event_facts(self, event: dict) -> List[Dict[str, str]]:
        """Get event facts for display"""
        facts = [
            {"name": "Event Type", "value": event['event_type'].replace('_', ' ').title()},
            {"name": "Timestamp", "value": datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S UTC')}
        ]
        
        for key, value in event['event_data'].items():
            if key not in ['timestamp']:
                display_key = key.replace('_', ' ').title()
                facts.append({"name": display_key, "value": str(value)})
        
        if event.get('repositories'):
            facts.append({"name": "Repositories", "value": ", ".join(event['repositories'])})
            
        return facts 