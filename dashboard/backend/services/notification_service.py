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
        # Special case: always send TEST notifications for testing purposes
        if event_type == 'TEST':
            logger.info(f"Allowing TEST event type for testing")
            return True
            
        # Check if event type is enabled
        if event_type not in config.get('event_types', []):
            logger.info(f"Event type {event_type} not in configured types: {config.get('event_types', [])}")
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
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=message) as response:
                    if response.status == 200:
                        logger.info(f"Teams notification sent successfully for event {event['event_type']}")
                        self._log_to_system("INFO", f"Teams notification sent successfully for {event['event_type']} event")
                        return True
                    else:
                        logger.error(f"Failed to send Teams notification: {response.status}")
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
                requests.post('http://localhost:8000/logs/immediate', json=log_data, timeout=1)
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
            
            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=message) as response:
                    if response.status == 200:
                        logger.info(f"Slack notification sent successfully for event {event['event_type']}")
                        self._log_to_system("INFO", f"Slack notification sent successfully for {event['event_type']} event")
                        return True
                    else:
                        logger.error(f"Failed to send Slack notification: {response.status}")
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
            with smtplib.SMTP(config['smtp_server'], config['smtp_port']) as server:
                if config['smtp_port'] in [587, 25]:  # TLS ports
                    server.starttls()
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

    def _format_email_message(self, event: dict, config: dict) -> MIMEMultipart:
        """Format email message"""
        title, color, summary = self._get_event_details(event)
        
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
        
        if event['event_type'] == 'new_job':
            return (
                f"New Job Started: {event_data.get('job_type', 'Unknown')}",
                "#4CAF50",
                f"A new {event_data.get('job_type', 'unknown')} job has been started for {event_data.get('repository', 'unknown repository')}"
            )
        elif event['event_type'] == 'new_operation':
            return (
                f"New Operation: {event_data.get('operation_type', 'Unknown')}",
                "#2196F3",
                f"A new {event_data.get('operation_type', 'unknown')} operation has been started"
            )
        elif event['event_type'] == 'job_failure':
            return (
                f"Job Failed: {event_data.get('job_type', 'Unknown')}",
                "#F44336",
                f"A {event_data.get('job_type', 'unknown')} job has failed for {event_data.get('repository', 'unknown repository')}"
            )
        elif event['event_type'] == 'system_health_change':
            status = event_data.get('status', 'unknown')
            service = event_data.get('service', 'unknown service')
            color = "#FF9800" if status == 'warning' else "#F44336" if status == 'error' else "#4CAF50"
            return (
                f"System Health Change: {service}",
                color,
                f"{service} status changed to {status}"
            )
        elif event['event_type'] in ['test_notification', 'TEST']:
            return (
                f"Test Notification - {event_data.get('service_type', 'Unknown').title()}",
                "#2196F3",
                event_data.get('message', 'Test notification from PR-Agent Dashboard')
            )
        else:
            return (
                f"Unknown Event: {event['event_type']}",
                "#9E9E9E",
                f"An {event['event_type']} event occurred"
            )

    def _get_event_facts(self, event: dict) -> List[Dict[str, str]]:
        """Get event facts for display"""
        facts = [
            {"name": "Event Type", "value": event['event_type'].replace('_', ' ').title()},
            {"name": "Timestamp", "value": datetime.fromisoformat(event['timestamp'].replace('Z', '+00:00')).strftime('%Y-%m-%d %H:%M:%S UTC')}
        ]
        
        # Add event-specific data
        for key, value in event['event_data'].items():
            if key not in ['timestamp']:  # Skip redundant fields
                display_key = key.replace('_', ' ').title()
                facts.append({"name": display_key, "value": str(value)})
        
        if event.get('repositories'):
            facts.append({"name": "Repositories", "value": ", ".join(event['repositories'])})
            
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
            
            # Use the full send_notification flow to properly create and track the event
            result = await self.send_notification(
                event_type="TEST",
                event_data={
                    "title": "Test Notification",
                    "message": "This is a test notification from PR-Agent Dashboard",
                    "service_type": config['service_type'],
                    "job_id": f"test-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
                    "repository": "test/repository",
                    "status": "success"
                },
                repositories=["test/repository"]
            )
            
            return result
        except Exception as e:
            logger.error(f"Test notification failed: {e}")
            self._log_to_system("ERROR", f"Test notification failed: {str(e)}")
            return False 