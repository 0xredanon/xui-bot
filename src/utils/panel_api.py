import requests
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any, List
import json
from ..utils.logger import CustomLogger
from ..utils.exceptions import APIError

# Initialize logger
logger = CustomLogger("PanelAPI")

class PanelAPI:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._session_cookie = None

    def _make_request(self, method: str, endpoint: str, data: Dict = None) -> Dict:
        """Make an authenticated request to the panel API"""
        if not self._session_cookie and not self.login():
            raise APIError("Failed to authenticate with panel")

        try:
            url = f"{self.base_url}{endpoint}"
            headers = {
                "Accept": "application/json",
                "Content-Type": "application/json"
            }

            if method.upper() == 'GET':
                response = self.session.get(url, headers=headers)
            elif method.upper() == 'POST':
                response = self.session.post(url, headers=headers, json=data)
            else:
                raise APIError(f"Unsupported HTTP method: {method}")

            if not response.ok:
                raise APIError(f"Request failed with status {response.status_code}")

            return response.json()

        except requests.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            raise APIError(f"Request failed: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {str(e)}")
            raise APIError("Invalid JSON response from panel")
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise APIError(f"Unexpected error: {str(e)}")

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
                traffic_data = response.get('obj', [{}])[0] if isinstance(response.get('obj'), list) else response.get('obj', {})
                return traffic_data

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

    def get_client_info(self, uuid: str) -> Optional[Dict[str, Any]]:
        """Get client information from panel API"""
        try:
            # First try to get client traffic which contains most of the info we need
            traffic_info = self.get_client_traffic(uuid)
            if not traffic_info:
                logger.error("Failed to get client traffic info")
                return None

            # Standardize field names
            standardized_info = {
                'enable': traffic_info.get('enable', True),
                'email': traffic_info.get('email', ''),
                'up': traffic_info.get('up', 0),
                'down': traffic_info.get('down', 0),
                'total': traffic_info.get('total', 0),
                'expire_time': traffic_info.get('expiryTime', 0),  # Standardize to expire_time
                'id': traffic_info.get('id') or uuid
            }

            # Get additional info from inbounds list
            response = self._make_request('GET', '/panel/api/inbounds/list')
            if response and isinstance(response, dict):
                inbounds = response.get('obj', [])
                for inbound in inbounds:
                    if isinstance(inbound, str):
                        try:
                            inbound = json.loads(inbound)
                        except json.JSONDecodeError:
                            continue

                    settings = inbound.get('settings', '{}')
                    if isinstance(settings, str):
                        try:
                            settings = json.loads(settings)
                        except json.JSONDecodeError:
                            continue

                    stream_settings = inbound.get('streamSettings', '{}')
                    if isinstance(stream_settings, str):
                        try:
                            stream_settings = json.loads(stream_settings)
                        except json.JSONDecodeError:
                            stream_settings = {}

                    clients = settings.get('clients', [])
                    for client in clients:
                        if client.get('id') == uuid:
                            # Update standardized info with additional data
                            standardized_info.update({
                                'port': inbound.get('port'),
                                'protocol': inbound.get('protocol', ''),
                                'tls': stream_settings.get('security', ''),
                                'total_gb': client.get('totalGB', 0),
                                'expire_time': client.get('expiryTime', standardized_info['expire_time'])  # Prefer client config expiry
                            })
                            return standardized_info

            # If we couldn't get additional info, return standardized traffic info
            return standardized_info

        except APIError as e:
            logger.error(f"Error getting client info: {str(e)}")
            return None

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
        """Generate subscription URL for a client"""
        try:
            # Get base URL without trailing slash
            base_url = self.base_url.rstrip('/')
            
            # Extract client email and uuid
            email = client_info.get('email', '')
            uuid = client_info.get('id')
            
            if not uuid:
                raise APIError("Client UUID not found")
            
            # URL encode the email
            encoded_email = requests.utils.quote(email)
            
            # Generate subscription URL
            sub_url = f"{base_url}/sub/{encoded_email}/{uuid}"
            
            return sub_url
            
        except Exception as e:
            logger.error(f"Error generating subscription URL: {str(e)}")
            raise APIError("Failed to generate subscription URL")

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