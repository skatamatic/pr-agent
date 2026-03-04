import subprocess
import sys
import psutil
import json
import logging
from typing import Dict, List, Optional, Union
from datetime import datetime

logger = logging.getLogger(__name__)


def _is_windows() -> bool:
    """True when running on Windows. On Linux/Cloud Run, use Azure DevOps pool API for agent health."""
    return sys.platform == "win32"


class AzureAgentServiceMonitor:
    """Service to monitor Azure DevOps agent Windows services (Windows only). On Linux/Cloud use Azure DevOps API."""

    def __init__(self):
        self.logger = logger

    def check_service_status(self, service_name: str) -> Dict[str, Union[str, bool, None]]:
        """
        Check the status of an Azure DevOps agent Windows service (Windows only).
        On non-Windows returns not_available so callers can use API-based health.
        """
        if not _is_windows():
            self.logger.debug("Azure agent service check skipped on non-Windows; use Azure DevOps API for agent health.")
            return {
                "status": "not_available",
                "status_display": "Local service check only available on Windows; use API-based agent health.",
                "service_name": service_name,
                "exists": False,
                "platform": sys.platform,
            }
        try:
            self.logger.info(f"Checking Azure agent service status for: {service_name}")
            
            # Get all Azure agent services using our existing working method
            azure_services = self.list_azure_agent_services()
            self.logger.info(f"Found {len(azure_services)} Azure agent services")
            
            # Look for exact name match first
            for service in azure_services:
                if service.get('name', '') == service_name:
                    self.logger.info(f"Found exact match for Azure agent service: {service_name}")
                    return {
                        'status': service.get('status', 'unknown'),
                        'status_display': service.get('status_display', 'Unknown'),
                        'service_name': service.get('name', service_name),
                        'display_name': service.get('display_name', ''),
                        'exists': True,
                        'can_stop': service.get('can_stop', False),
                        'match_type': 'exact'
                    }
            
            # If no exact match, look for partial matches
            self.logger.info(f"No exact match found, looking for partial matches")
            potential_matches = []
            
            for service in azure_services:
                service_display = service.get('display_name', '').lower()
                service_name_lower = service.get('name', '').lower()
                search_name_lower = service_name.lower()
                
                # Detailed logging for debugging
                self.logger.info(f"Comparing search '{search_name_lower}' with service name '{service_name_lower}' and display '{service_display}'")
                
                # Check for various matching patterns
                match_score = 0
                
                # Exact matches
                if search_name_lower == service_name_lower:
                    match_score = 100
                elif search_name_lower == service_display:
                    match_score = 95
                
                # Substring matches
                elif search_name_lower in service_name_lower:
                    match_score = 80
                elif search_name_lower in service_display:
                    match_score = 75
                elif service_name_lower in search_name_lower:
                    match_score = 70
                elif service_display in search_name_lower:
                    match_score = 65
                
                # Azure DevOps agent specific matching patterns
                else:
                    # Handle wildcard patterns (e.g., "vstsagent.org.*")
                    if search_name_lower.endswith('*'):
                        pattern_prefix = search_name_lower[:-1]
                        if service_name_lower.startswith(pattern_prefix):
                            match_score = 90
                            self.logger.info(f"Wildcard pattern match: {service_name_lower} matches {pattern_prefix}*")
                    
                    if match_score == 0:
                        # Extract key components from search name for fuzzy matching
                        search_parts = search_name_lower.replace('.', ' ').replace('-', ' ').replace('_', ' ').split()
                        service_parts = (service_name_lower + ' ' + service_display).replace('.', ' ').replace('-', ' ').replace('_', ' ').split()
                        
                        # Count matching parts
                        matching_parts = 0
                        for part in search_parts:
                            if len(part) > 2:  # Ignore very short parts
                                for service_part in service_parts:
                                    if part in service_part or service_part in part:
                                        matching_parts += 1
                                        self.logger.info(f"Part match: '{part}' found in '{service_part}'")
                                        break
                        
                        if matching_parts > 0:
                            match_score = min(60, matching_parts * 15)  # Score based on matching parts
                            self.logger.info(f"Fuzzy match found: {matching_parts} parts matched, score: {match_score}")
                
                if match_score > 0:
                    self.logger.info(f"Adding potential match: {service.get('name')} (score: {match_score})")
                    potential_matches.append({
                        'service': service,
                        'score': match_score
                    })
            
            if potential_matches:
                # Sort by match score and take the best match
                best_match = sorted(potential_matches, key=lambda x: x['score'], reverse=True)[0]
                service_info = best_match['service']
                
                self.logger.info(f"Found best match: {service_info.get('name')} (score: {best_match['score']})")
                self.logger.info(f"Service info keys: {list(service_info.keys())}")
                self.logger.info(f"Full service info: {service_info}")
                
                response = {
                    'status': service_info.get('status', 'unknown'),
                    'status_display': f"{service_info.get('status_display', 'Unknown')} (fuzzy match)",
                    'service_name': service_info.get('name', service_name),
                    'display_name': service_info.get('display_name', ''),
                    'exists': True,
                    'can_stop': service_info.get('can_stop', False),
                    'match_type': 'fuzzy',
                    'match_score': best_match['score'],
                    'searched_for': service_name
                }
                
                self.logger.info(f"Returning fuzzy match response: {response}")
                return response
            
            # If no matches found at all
            self.logger.warning(f"No matches found for Azure agent service: {service_name}")
            return {
                'status': 'not_found',
                'status_display': 'Service not found',
                'service_name': service_name,
                'exists': False,
                'match_type': 'none',
                'available_services': [s.get('name', '') for s in azure_services]
            }
            
        except Exception as e:
            self.logger.error(f"Error checking Azure agent service {service_name}: {str(e)}")
            return {
                'status': 'error',
                'status_display': 'Error checking service',
                'service_name': service_name,
                'error': str(e),
                'exists': False
            }

    def list_azure_agent_services(self) -> List[Dict[str, Union[str, bool]]]:
        """
        List all Azure DevOps agent services on the system (Windows only).
        On non-Windows returns empty list.
        """
        if not _is_windows():
            self.logger.debug("List Azure agent services skipped on non-Windows.")
            return []
        try:
            self.logger.info("Listing Azure DevOps agent services")
            
            # PowerShell command to get Azure DevOps agent services
            # Azure DevOps agents typically have "Azure", "VSTS", or "vstsagent" in their names
            cmd = [
                'powershell.exe', 
                '-NoProfile', 
                '-Command',
                'Get-Service | Where-Object { $_.Name -like "*Azure*" -or $_.DisplayName -like "*Azure*" -or $_.Name -like "*VSTS*" -or $_.DisplayName -like "*VSTS*" -or $_.Name -like "*vstsagent*" -or $_.DisplayName -like "*Agent*" -or $_.Name -like "vstsagent.*" } | ConvertTo-Json'
            ]
            
            self.logger.info(f"PowerShell command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW  # Hide PowerShell window
            )
            
            self.logger.info(f"PowerShell result - Return code: {result.returncode}")
            self.logger.info(f"PowerShell stdout length: {len(result.stdout) if result.stdout else 0}")
            
            if result.returncode != 0:
                self.logger.error(f"PowerShell stderr: {result.stderr}")
                return []
            
            if not result.stdout.strip():
                self.logger.info("No Azure agent services found")
                return []
            
            try:
                services_data = json.loads(result.stdout.strip())
                self.logger.info(f"Parsed JSON successfully, type: {type(services_data)}")
                
                # Handle single service or list of services
                if isinstance(services_data, dict):
                    services_data = [services_data]
                elif not isinstance(services_data, list):
                    self.logger.warning(f"Unexpected data type: {type(services_data)}")
                    return []
                
                services = []
                for service in services_data:
                    # Filter to only include likely Azure DevOps agent services
                    name = service.get('Name', '').lower()
                    display_name = service.get('DisplayName', '').lower()
                    
                    # Check if it's likely an Azure DevOps agent service
                    # Be more inclusive to catch all Azure DevOps agents
                    is_azure_agent = (
                        'azure' in name or 'azure' in display_name or
                        'vsts' in name or 'vsts' in display_name or
                        'vstsagent' in name or 'vstsagent' in display_name or
                        name.startswith('vstsagent.') or  # Direct match for vstsagent services
                        ('agent' in display_name and ('devops' in display_name or 'azure' in display_name or 'build' in display_name))
                    )
                    
                    self.logger.info(f"Service '{name}' ({'matched' if is_azure_agent else 'filtered out'}): display='{display_name}'")
                    
                    if is_azure_agent:
                        # Handle both string and numeric status codes
                        status_value = service.get('Status', 'Unknown')
                        
                        # Handle numeric status codes
                        if isinstance(status_value, int):
                            numeric_status_map = {
                                1: 'Stopped',
                                2: 'Start Pending',
                                3: 'Stop Pending', 
                                4: 'Running',
                                5: 'Continue Pending',
                                6: 'Pause Pending',
                                7: 'Paused'
                            }
                            status_display = numeric_status_map.get(status_value, f'Unknown ({status_value})')
                        else:
                            status_display = str(status_value)
                        
                        # Map to our internal status codes
                        status_map = {
                            'Running': 'running',
                            'Stopped': 'stopped',
                            'Start Pending': 'starting',
                            'Stop Pending': 'stopping',
                            'Continue Pending': 'starting',
                            'Pause Pending': 'stopping',
                            'Paused': 'paused'
                        }
                        
                        internal_status = status_map.get(status_display, 'unknown')
                        
                        service_info = {
                            'name': service.get('Name', ''),
                            'display_name': service.get('DisplayName', ''),
                            'status': internal_status,
                            'status_display': status_display,
                            'can_stop': service.get('CanStop', False)
                        }
                        
                        services.append(service_info)
                        self.logger.info(f"Added Azure agent service: {service_info}")
                
                self.logger.info(f"Found {len(services)} Azure DevOps agent services")
                # Debug: Log the final services data structure
                self.logger.info(f"FINAL SERVICES DATA: {json.dumps(services, indent=2)}")
                return services
                
            except json.JSONDecodeError as e:
                self.logger.error(f"Failed to parse JSON: {e}")
                self.logger.error(f"Raw output: {result.stdout[:500]}...")
                return []
            
        except Exception as e:
            self.logger.error(f"Error listing Azure agent services: {str(e)}")
            return []

    def get_service_health_impact(self, service_status: Dict[str, Union[str, bool, None]]) -> str:
        """Determine the health impact of a service status."""
        status = service_status.get('status', 'unknown')
        if status == 'not_available':
            return 'healthy'  # On Linux/cloud, local check is N/A; use API health
        if status == 'running':
            return 'healthy'
        elif status in ['starting', 'stopping', 'paused']:
            return 'warning'
        elif status in ['stopped', 'error', 'not_found']:
            return 'error'
        else:
            return 'warning'

    def get_default_service_name(self, repo_name: str, organization: str = None) -> str:
        """
        Generate a default Azure DevOps agent service name
        
        Args:
            repo_name: Repository name
            organization: Azure DevOps organization name
            
        Returns:
            Default service name pattern
        """
        # Azure DevOps agent services follow the pattern: vstsagent.{org}.{agent_name}.{machine_name}
        # Since agent_name and machine_name are dynamic, we provide a realistic example
        if organization:
            # Use a more realistic default that will fuzzy match better
            return f"vstsagent.{organization}.PRAgent_SelfHosted.DESKTOP-U1OGO2O"
        else:
            return f"vstsagent.unknown.PRAgent_SelfHosted.DESKTOP-U1OGO2O"

    def suggest_service_names(self, repo_name: str, organization: str = None) -> List[str]:
        """
        Suggest likely Azure DevOps agent service names based on common patterns
        
        Args:
            repo_name: Repository name
            organization: Azure DevOps organization name
            
        Returns:
            List of suggested service name patterns
        """
        suggestions = []
        
        if organization:
            # Common patterns for Azure DevOps agents
            suggestions.extend([
                f"vstsagent.{organization}.{repo_name}.*",
                f"vstsagent.{organization}.*{repo_name}*",
                f"vstsagent.{organization}.*Agent*",
                f"vstsagent.{organization}.*SelfHosted*",
                f"vstsagent.{organization}.*"
            ])
        else:
            suggestions.extend([
                f"vstsagent.*{repo_name}*",
                f"vstsagent.*Agent*",
                f"vstsagent.*SelfHosted*",
                f"vstsagent.*"
            ])
        
        return suggestions 