import requests
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any, List, Union
import json
from ..utils.logger import CustomLogger
from ..utils.exceptions import APIError
from datetime import datetime
import pytz

# Initialize logger
logger = CustomLogger("PanelAPI")

class PanelAPI:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._session_cookie = None

    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make HTTP request to panel API with proper error handling"""
        try:
            url = f"{self.base_url}{endpoint}"
            response = self.session.request(method, url, **kwargs)
            
            # Check if response is successful
            response.raise_for_status()
            
            # Handle empty responses
            if not response.content:
                raise APIError("Empty response received")
                
            return response
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            raise APIError(f"Request failed: {str(e)}")

    def login(self) -> bool:
        """Login to panel and get session cookie"""
        try:
            response = self.session.post(
                f"{self.base_url}/login",
                json={"username": self.username, "password": self.password}
            )
            if response.ok:
                self._session_cookie = self.session.cookies.get("session")
                logger.info("Successfully logged in to panel")
                return True
            logger.warning("Failed to log in to panel")
            return False
        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            return False

    def get_client_traffic(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Get client traffic info from panel API using UUID or email"""
        try:
            # Try getting traffic by UUID first
            response = self._make_request(
                'GET',
                f"/panel/api/inbounds/getClientTrafficsById/{identifier}"
            )
            
            if response and isinstance(response, dict) and response.get('success'):
                obj = response.get('obj', [])
                if isinstance(obj, list) and obj:
                    return obj[0]
                elif isinstance(obj, dict):
                    return obj
                return {}

            # If UUID fails, try getting traffic by email
            response = self._make_request(
                'GET',
                f"/panel/api/inbounds/getClientTraffics/{identifier}"
            )
            
            if response and isinstance(response, dict) and response.get('success'):
                traffic_data = response.get('obj', {})
                return traffic_data

            logger.error("Failed to get client traffic with both UUID and email")
            return None

        except APIError as e:
            logger.error(f"Error getting client traffic: {str(e)}")
            return None

    def get_client_info(self, uuid: Optional[str] = None, email: Optional[str] = None) -> Dict[str, Any]:
        """Get client information by UUID or email"""
        try:
            if uuid:
                response = self._make_request('GET', f'/client/{uuid}')
            elif email:
                response = self._make_request('GET', f'/client/email/{email}')
            else:
                raise ValueError("Either UUID or email must be provided")

            return response.json()
        except Exception as e:
            logger.error(f"Error getting client info: {str(e)}")
            return {}

    @staticmethod
    def extract_identifier_from_link(link: str) -> Optional[str]:
        """Extract client identifier from VPN link"""
        try:
            # Handle vless:// links
            if link.startswith('vless://'):
                # Extract the UUID part
                uuid_match = re.search(r'vless://([^@]+)@', link)
                if uuid_match:
                    return uuid_match.group(1)
                
                # If no UUID found, try to extract from the name part
                name_match = re.search(r'#([^#]+)$', link)
                if name_match:
                    return name_match.group(1)
            
            return None
        except Exception as e:
            logger.error(f"Error extracting identifier: {str(e)}")
            return None

    def get_subscription_url(self, client_info: Dict[str, Any]) -> str:
        """Generate subscription URL for client"""
        try:
            base_url = self.base_url.replace('api/', '')
            return f"{base_url}/sub/{client_info['uuid']}"
        except Exception as e:
            logger.error(f"Error generating subscription URL: {str(e)}")
            return ""

    def get_online_clients(self) -> List[Dict]:
        """Get list of online clients from panel"""
        try:
            response = self._make_request('POST', '/panel/api/inbounds/onlines')
            if isinstance(response, dict):
                obj = response.get('obj', [])
                # اگر obj یک رشته باشد، آن را به JSON تبدیل می‌کنیم
                if isinstance(obj, str):
                    try:
                        obj = json.loads(obj)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse online clients response")
                        return []
                return obj if isinstance(obj, list) else []
            return []
        except Exception as e:
            logger.error(f"Error getting online clients: {str(e)}")
            raise APIError("Failed to get online clients")

    def create_backup(self) -> Union[Dict[str, Any], bytes]:
        """Create panel backup"""
        try:
            response = self._make_request('GET', '/panel/backup')
            if not response or not response.content:
                raise APIError("No backup data received")
                
            # Try to parse as JSON first
            try:
                backup_data = response.json()
            except ValueError:
                # If not JSON, treat as raw backup data
                backup_data = response.content
                
            return backup_data
        except Exception as e:
            logger.error(f"Error creating panel backup: {str(e)}")
            raise APIError(f"Failed to create backup: {str(e)}")

    def set_traffic(self, uuid: str, gb: int) -> bool:
        """Set client traffic limit in GB"""
        try:
            data = {'uuid': uuid, 'traffic_gb': gb}
            response = self._make_request('POST', '/client/traffic', json=data)
            return response.json().get('success', False)
        except Exception as e:
            logger.error(f"Error setting traffic: {str(e)}")
            return False

    def set_expiry(self, uuid: str, days: int) -> bool:
        """Set client expiry date in days"""
        try:
            data = {'uuid': uuid, 'days': days}
            response = self._make_request('POST', '/client/expiry', json=data)
            return response.json().get('success', False)
        except Exception as e:
            logger.error(f"Error setting expiry: {str(e)}")
            return False

    def set_unlimited(self, uuid: str) -> bool:
        """Set client traffic to unlimited"""
        try:
            data = {'uuid': uuid}
            response = self._make_request('POST', '/client/unlimited', json=data)
            return response.json().get('success', False)
        except Exception as e:
            logger.error(f"Error setting unlimited: {str(e)}")
            return False

    def reset_traffic(self, uuid: str) -> bool:
        """Reset client traffic usage"""
        try:
            data = {'uuid': uuid}
            response = self._make_request('POST', '/client/reset', json=data)
            return response.json().get('success', False)
        except Exception as e:
            logger.error(f"Error resetting traffic: {str(e)}")
            return False

    def delete_client(self, uuid: str) -> bool:
        """Delete a client"""
        try:
            response = self._make_request('DELETE', f'/client/{uuid}')
            return response.json().get('success', False)
        except Exception as e:
            logger.error(f"Error deleting client: {str(e)}")
            return False

    def close(self):
        """Close the session and cleanup resources"""
        try:
            if self.session:
                self.session.close()
            logger.info("Panel API session closed")
        except Exception as e:
            logger.error(f"Error closing panel API session: {str(e)}") 