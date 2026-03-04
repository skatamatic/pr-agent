import subprocess
import sys
import psutil
import json
import logging
from typing import Dict, List, Optional, Union
from datetime import datetime

logger = logging.getLogger(__name__)


def _is_windows() -> bool:
    """True when running on Windows (local service checks available). On Linux/Cloud Run, use API-based health."""
    return sys.platform == "win32"


class RunnerServiceMonitor:
    """Service to monitor GitHub Actions runner Windows services (Windows only). On Linux/Cloud use GitHub API."""

    def __init__(self):
        self.logger = logger

    def check_service_status(self, service_name: str) -> Dict[str, Union[str, bool, None]]:
        """
        Check the status of a Windows service (Windows only).
        On non-Windows returns not_available so callers can use API-based health.
        """
        if not _is_windows():
            self.logger.debug("Runner service check skipped on non-Windows; use GitHub Actions API for runner health.")
            return {
                "status": "not_available",
                "status_display": "Local service check only available on Windows; use API-based runner health.",
                "service_name": service_name,
                "exists": False,
                "platform": sys.platform,
            }
        try:
            self.logger.info(f"Checking service status for: {service_name}")
            
            # Get all GitHub runner services using our existing working method
            github_services = self.list_github_runner_services()
            self.logger.info(f"Found {len(github_services)} GitHub runner services")
            
            # Look for exact name match first
            for service in github_services:
                if service.get('name', '') == service_name:
                    self.logger.info(f"Found exact match for service: {service_name}")
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
            
            for service in github_services:
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
                
                # GitHub runner specific matching patterns
                else:
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
            self.logger.warning(f"No matches found for service: {service_name}")
            return {
                'status': 'not_found',
                'status_display': 'Service not found',
                'service_name': service_name,
                'exists': False,
                'match_type': 'none',
                'available_services': [s.get('name', '') for s in github_services]
            }
            
        except Exception as e:
            self.logger.error(f"Error checking service {service_name}: {str(e)}")
            return {
                'status': 'error',
                'status_display': 'Error checking service',
                'service_name': service_name,
                'error': str(e),
                'exists': False
            }

    def _check_service_powershell(self, service_name: str) -> Optional[Dict[str, Union[str, bool, None]]]:
        """Check service using PowerShell Get-Service command"""
        try:
            # PowerShell command to get service information - escape service name properly
            escaped_name = service_name.replace("'", "''")  # Escape single quotes
            cmd = [
                'powershell.exe', 
                '-NoProfile', 
                '-Command',
                f"Get-Service -Name '{escaped_name}' -ErrorAction SilentlyContinue | ConvertTo-Json"
            ]
            
            self.logger.info(f"PowerShell command: {' '.join(cmd)}")
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW  # Hide PowerShell window
            )
            
            self.logger.info(f"PowerShell result - Return code: {result.returncode}")
            self.logger.info(f"PowerShell stdout: {result.stdout}")
            self.logger.info(f"PowerShell stderr: {result.stderr}")
            
            if result.returncode == 0 and result.stdout.strip():
                service_info = json.loads(result.stdout.strip())
                self.logger.info(f"Parsed service info: {service_info}")
                
                # Handle both string and numeric status codes
                status_value = service_info.get('Status', 'Unknown')
                
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
                    'Pause Pending': 'pausing',
                    'Paused': 'paused'
                }
                
                status = status_map.get(status_display, 'unknown')
                
                response = {
                    'status': status,
                    'status_display': status_display,
                    'service_name': service_info.get('Name', service_name),
                    'display_name': service_info.get('DisplayName', ''),
                    'exists': True,
                    'can_stop': service_info.get('CanStop', False),
                    'can_pause_continue': service_info.get('CanPauseAndContinue', False)
                }
                
                self.logger.info(f"Returning service response: {response}")
                return response
            else:
                # Service not found
                self.logger.warning(f"Service not found - Return code: {result.returncode}, stdout: '{result.stdout}', stderr: '{result.stderr}'")
                return {
                    'status': 'not_found',
                    'status_display': 'Service not found',
                    'service_name': service_name,
                    'exists': False
                }
                
        except subprocess.TimeoutExpired:
            self.logger.warning(f"PowerShell command timed out for service {service_name}")
            return None
        except json.JSONDecodeError as e:
            self.logger.warning(f"Could not parse PowerShell output for service {service_name}: {e}")
            self.logger.warning(f"Raw output was: {result.stdout}")
            return None
        except Exception as e:
            self.logger.warning(f"PowerShell check failed for service {service_name}: {str(e)}")
            return None

    def _check_service_psutil(self, service_name: str) -> Dict[str, Union[str, bool, None]]:
        """Fallback method using psutil to check for running processes"""
        try:
            # Look for processes that might be the GitHub Actions runner
            found_processes = []
            
            for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'status']):
                try:
                    proc_info = proc.info
                    proc_name = proc_info.get('name', '').lower()
                    cmdline = ' '.join(proc_info.get('cmdline', [])).lower()
                    
                    # Look for GitHub Actions runner processes
                    if ('github' in proc_name and 'runner' in proc_name) or \
                       ('actions' in cmdline and 'runner' in cmdline) or \
                       ('github.runner' in cmdline):
                        found_processes.append({
                            'pid': proc_info['pid'],
                            'name': proc_info['name'],
                            'status': proc_info['status']
                        })
                        
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue
            
            if found_processes:
                return {
                    'status': 'running',
                    'status_display': 'Running (detected via process)',
                    'service_name': service_name,
                    'exists': True,
                    'processes': found_processes,
                    'detection_method': 'process_scan'
                }
            else:
                return {
                    'status': 'not_found',
                    'status_display': 'Service/Process not found',
                    'service_name': service_name,
                    'exists': False,
                    'detection_method': 'process_scan'
                }
                
        except Exception as e:
            self.logger.error(f"Process scan failed for service {service_name}: {str(e)}")
            return {
                'status': 'error',
                'status_display': 'Error scanning processes',
                'service_name': service_name,
                'error': str(e),
                'exists': False
            }

    def list_github_runner_services(self) -> List[Dict[str, Union[str, bool]]]:
        """
        List all Windows services that appear to be GitHub Actions runners (Windows only).
        On non-Windows returns empty list.
        """
        if not _is_windows():
            self.logger.debug("List runner services skipped on non-Windows.")
            return []
        try:
            # PowerShell command to find GitHub Actions runner services
            cmd = [
                'powershell.exe', 
                '-NoProfile', 
                '-Command',
                'Get-Service | Where-Object { $_.Name -like "*GitHub*" -or $_.DisplayName -like "*GitHub*" -or $_.DisplayName -like "*Actions*" } | ConvertTo-Json'
            ]
            
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            if result.returncode == 0 and result.stdout.strip():
                services_data = json.loads(result.stdout.strip())
                
                # Handle single service or list of services
                if isinstance(services_data, dict):
                    services_data = [services_data]
                elif not isinstance(services_data, list):
                    services_data = []
                
                services = []
                for service in services_data:
                    # Map both string and numeric status codes
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
                        'Pause Pending': 'pausing',
                        'Paused': 'paused'
                    }
                    
                    services.append({
                        'name': service.get('Name', ''),
                        'display_name': service.get('DisplayName', ''),
                        'status': status_map.get(status_display, 'unknown'),
                        'status_display': status_display,
                        'can_stop': service.get('CanStop', False)
                    })
                
                return services
            else:
                return []
                
        except Exception as e:
            self.logger.error(f"Error listing GitHub runner services: {str(e)}")
            return []

    def get_service_health_impact(self, service_status: Dict[str, Union[str, bool, None]]) -> str:
        """
        Determine the health impact of a service status for repository health integration.
        """
        status = service_status.get('status', 'unknown')
        if status == 'not_available':
            return 'healthy'  # On Linux/cloud, local check is N/A; use API health
        if status == 'running':
            return 'healthy'
        elif status in ['stopped', 'not_found']:
            return 'error'  # Service not running affects repository automation
        elif status in ['starting', 'stopping', 'paused']:
            return 'warning'  # Service in transition state
        else:
            return 'error'  # Unknown or error states 