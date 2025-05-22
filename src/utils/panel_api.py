import requests
import re
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any, List, Union
import json
from ..utils.logger import CustomLogger
from ..utils.exceptions import APIError
from datetime import datetime
import pytz
import time
import traceback
from ..utils.jalali_datetime import JalaliDateTime

# Initialize logger
logger = CustomLogger("PanelAPI")

class PanelAPI:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.username = username
        self.password = password
        self.session = requests.Session()
        self._session_cookie = None

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to panel API with proper error handling"""
        try:
            url = f"{self.base_url}{endpoint}"
            
            # Add timeout to prevent hanging
            if 'timeout' not in kwargs:
                kwargs['timeout'] = 30
                
            # Ensure we have a valid session
            if not self._session_cookie:
                self.login()
                
            response = self.session.request(method, url, **kwargs)
            
            # Check if we got unauthorized and need to re-login
            if response.status_code == 401:
                logger.warning("Session expired, attempting to re-login")
                if self.login():
                    response = self.session.request(method, url, **kwargs)
            
            # Check if response is successful
            response.raise_for_status()
            
            # Handle empty responses
            if not response.content:
                raise APIError("Empty response received")
            
            # Try to parse JSON response
            try:
                data = response.json()
                # If the response is a string, try to parse it as JSON
                if isinstance(data, str):
                    try:
                        data = json.loads(data)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse response string as JSON: {data}")
                        raise APIError("Invalid JSON response")
                
                return data
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse response as JSON: {str(e)}")
                raise APIError("Invalid JSON response")
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            raise APIError(f"Request failed: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error in request: {str(e)}")
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

    def get_client_info(self, uuid: Optional[str] = None, email: Optional[str] = None, inbound_id: Optional[int] = None) -> Dict[str, Any]:
        """Get client information by UUID or email and optionally inbound_id
        
        Args:
            uuid: Client UUID
            email: Client email identifier
            inbound_id: Optional inbound ID if known, for faster lookup
            
        Returns:
            Dict: Client information dictionary
        """
        try:
            logger.info(f"Getting client info for UUID: {uuid} or email: {email}, inbound_id: {inbound_id}")
            
            # We need either UUID or email
            if not uuid and not email:
                logger.error("Either UUID or email must be provided")
                raise ValueError("Either UUID or email must be provided")

            client_data = {}
            
            # Get online clients first
            online_clients = self.get_online_clients()
            is_online = False
            
            if isinstance(online_clients, list):
                for client in online_clients:
                    if isinstance(client, dict):
                        client_uuid = client.get('uuid') or client.get('id')
                        client_email = client.get('email')
                        if (uuid and client_uuid == uuid) or (email and client_email == email):
                            is_online = True
                            # Add online client data
                            client_data.update({
                                'up': client.get('up', 0),
                                'down': client.get('down', 0),
                                'ip': client.get('ip', ''),
                                'last_seen': client.get('last_seen', 0)
                            })
                            break
            
            # If we know the inbound ID, use a more direct approach
            if inbound_id:
                try:
                    inbound_info = self._get_inbound_info(inbound_id)
                    if inbound_info and 'settings' in inbound_info:
                        settings = inbound_info.get('settings')
                        
                        # Parse settings if it's a string
                        if isinstance(settings, str):
                            try:
                                settings = json.loads(settings)
                            except Exception as e:
                                logger.error(f"Error parsing settings JSON: {str(e)}")
                                settings = {}
                        
                        # Find matching client
                        if isinstance(settings, dict) and 'clients' in settings:
                            for client in settings.get('clients', []):
                                if (uuid and client.get('id') == uuid) or (email and client.get('email') == email):
                                    # Create a client data object with the inbound_id included
                                    client_data.update({
                                        **client,
                                        'inbound_id': inbound_id,
                                        'protocol': inbound_info.get('protocol', 'unknown'),
                                        'port': inbound_info.get('port', 0),
                                        'is_online': is_online
                                    })
                                    logger.info(f"Found client in inbound {inbound_id} using direct lookup")
                                    break
                except Exception as e:
                    logger.error(f"Error in direct inbound lookup: {str(e)}")
            
            # If client not found using direct approach, try the API endpoints
            if not client_data:
                # Try with the specific endpoints for a single client
                if uuid:
                    try:
                        data = self._make_request('GET', f'/panel/api/inbounds/getClientTrafficsById/{uuid}')
                        
                        if data.get('success'):
                            obj = data.get('obj', [])
                            if isinstance(obj, list) and obj:
                                client_data.update({**obj[0], 'is_online': is_online})
                            elif isinstance(obj, dict):
                                client_data.update({**obj, 'is_online': is_online})
                            elif isinstance(obj, str):
                                try:
                                    # Try to parse string as JSON
                                    parsed_obj = json.loads(obj)
                                    if isinstance(parsed_obj, list) and parsed_obj:
                                        client_data.update({**parsed_obj[0], 'is_online': is_online})
                                    elif isinstance(parsed_obj, dict):
                                        client_data.update({**parsed_obj, 'is_online': is_online})
                                except json.JSONDecodeError:
                                    logger.error(f"Failed to parse client data string as JSON: {obj}")
                    except Exception as e:
                        logger.error(f"Error getting client info by UUID {uuid}: {str(e)}")
                
                if email and not client_data:
                    try:
                        data = self._make_request('GET', f'/panel/api/inbounds/getClientTraffics/{email}')
                        
                        if data.get('success'):
                            obj = data.get('obj', [])
                            if isinstance(obj, list) and obj:
                                client_data.update({**obj[0], 'is_online': is_online})
                            elif isinstance(obj, dict):
                                client_data.update({**obj, 'is_online': is_online})
                            elif isinstance(obj, str):
                                try:
                                    # Try to parse string as JSON
                                    parsed_obj = json.loads(obj)
                                    if isinstance(parsed_obj, list) and parsed_obj:
                                        client_data.update({**parsed_obj[0], 'is_online': is_online})
                                    elif isinstance(parsed_obj, dict):
                                        client_data.update({**parsed_obj, 'is_online': is_online})
                                except json.JSONDecodeError:
                                    logger.error(f"Failed to parse client data string as JSON: {obj}")
                    except Exception as e:
                        logger.error(f"Error getting client info by email {email}: {str(e)}")
            
            # If still not found, search all inbounds
            if not client_data:
                logger.info("Client not found with direct methods, searching all inbounds")
                try:
                    data = self._make_request('GET', '/panel/api/inbounds/list')
                    
                    if data.get('success'):
                        inbounds = data.get('obj', [])
                        
                        for inbound in inbounds:
                            inbound_id = inbound.get('id')
                            settings = inbound.get('settings')
                            
                            # Parse settings if it's a string
                            if isinstance(settings, str):
                                try:
                                    settings = json.loads(settings)
                                except:
                                    continue
                            
                            # Look for client with matching UUID or email
                            if isinstance(settings, dict) and 'clients' in settings:
                                for client in settings.get('clients', []):
                                    if (uuid and client.get('id') == uuid) or (email and client.get('email') == email):
                                        # Create a client data object with the inbound_id included
                                        client_data.update({
                                            **client,
                                            'inbound_id': inbound_id,
                                            'protocol': inbound.get('protocol', 'unknown'),
                                            'port': inbound.get('port', 0),
                                            'is_online': is_online
                                        })
                                        break
                                
                                if client_data:
                                    logger.info(f"Found client in inbound {inbound_id}")
                                    break
                except Exception as e:
                    logger.error(f"Error searching for client in inbounds: {str(e)}")
            
            # Ensure inbound_id is included in the client data
            if client_data and 'inbound_id' not in client_data:
                # Try to get inbound_id from settings
                if 'settings' in client_data:
                    settings = client_data.get('settings')
                    if isinstance(settings, str):
                        try:
                            settings = json.loads(settings)
                            if 'inbound_id' in settings:
                                client_data['inbound_id'] = settings['inbound_id']
                        except:
                            pass
                
                # If still no inbound_id, look for it in top level properties
                for key in client_data:
                    if key.lower() in ['inboundid', 'inbound_id', 'inbound']:
                        client_data['inbound_id'] = client_data[key]
                        break
            
            # Make sure UUID is also included as 'uuid' for consistency
            if client_data and 'id' in client_data and 'uuid' not in client_data:
                client_data['uuid'] = client_data['id']
            
            # Add online status if not already present
            if client_data and 'is_online' not in client_data:
                client_data['is_online'] = is_online
            
            # Log the result
            if client_data:
                logger.info(f"Client info retrieved: UUID={client_data.get('id')}, email={client_data.get('email')}, inbound_id={client_data.get('inbound_id')}, is_online={client_data.get('is_online')}")
            else:
                logger.warning(f"No client information found for UUID={uuid} or email={email}")
            
            return client_data or {}
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

    def get_vless_link(self, client_info: Dict[str, Any], base_server: str = "iran.olympusm.ir") -> str:
        """Generate VLESS connection link with time information
        
        Args:
            client_info: Client information dictionary
            base_server: Base server hostname (defaults to iran.olympusm.ir)
            
        Returns:
            str: VLESS connection string with time information
        """
        try:
            # Extract required parameters
            uuid = client_info.get('id') or client_info.get('uuid')
            email = client_info.get('email', '')
            expire_time = client_info.get('expire_time', 0)
            
            # Use a default port if not available in client_info
            port = client_info.get('port')
            if not port:
                port = 33950  # Default port
            
            if not uuid:
                logger.error(f"Missing required UUID for VLESS link generation")
                return ""
            
            # Format VLESS link with all required parameters
            vless_link = f"vless://{uuid}@{base_server}:{port}?security=none&alpn=null&encryption=none&headerType=http&type=tcp"
            
            # Add remark/name with time information
            if expire_time > 0:
                # Convert to Tehran timezone
                tehran_tz = pytz.timezone('Asia/Tehran')
                expiry_date = datetime.fromtimestamp(expire_time/1000, tehran_tz)
                jdate = JalaliDateTime.to_jalali(expiry_date)
                expiry_str = jdate.strftime('%Y/%m/%d')
                remark = f"OlampVPN-{email}-{expiry_str}"
            else:
                remark = f"OlampVPN-{email}"  # Removed -نامحدود suffix
            
            vless_link += f"#{remark}"
            
            logger.info(f"Generated VLESS link for client {email} with UUID: {uuid}")  # Added UUID to log
            return vless_link
            
        except Exception as e:
            logger.error(f"Error generating VLESS link: {str(e)}")
            return ""

    def get_online_clients(self) -> List[Dict]:
        """Get list of online clients from panel"""
        try:
            data = self._make_request('POST', '/panel/api/inbounds/onlines')
            
            if data.get('success'):
                obj = data.get('obj', [])
                # If obj is a string, try to parse it as JSON
                if isinstance(obj, str):
                    try:
                        obj = json.loads(obj)
                    except json.JSONDecodeError:
                        logger.error("Failed to parse online clients response")
                        return []
                # Ensure we return a list
                return obj if isinstance(obj, list) else [obj] if obj else []
            return []
        except Exception as e:
            logger.error(f"Error getting online clients: {str(e)}")
            raise APIError("Failed to get online clients")

    def create_backup(self) -> Union[Dict[str, Any], bytes]:
        """Create panel backup with improved error handling and endpoint fallback"""
        # First try to get .db file
        db_endpoints = [
            '/panel/api/inbounds/createbackup',
        ]
        
        json_endpoints = [
            '/panel/api/inbounds/list'  # Fallback endpoint
        ]
        
        # Try to get .db file first
        db_backup = None
        db_error = None
        for endpoint in db_endpoints:
            try:
                # Ensure we have a valid session
                if not self._session_cookie:
                    self.login()
                
                response = self._make_request('GET', endpoint)
                
                # Check if response is binary and likely a SQLite file (starts with SQLite format)
                if response.content and response.content.startswith(b'SQLite format'):
                    logger.info(f"Successfully created DB backup using endpoint: {endpoint}")
                    db_backup = response.content
                    break
                    
            except APIError as e:
                db_error = str(e)
                logger.warning(f"Failed to create DB backup using endpoint {endpoint}: {db_error}")
                try:
                    self.login()
                except:
                    pass
                continue
            except Exception as e:
                db_error = str(e)
                logger.error(f"Unexpected error using endpoint {endpoint}: {db_error}")
                continue
        
        # Then try to get JSON backup
        json_backup = None
        json_error = None
        for endpoint in json_endpoints:
            try:
                # Ensure we have a valid session
                if not self._session_cookie:
                    self.login()
                
                response = self._make_request('GET', endpoint)
                
                # Handle different response types
                if response.headers.get('content-type', '').startswith('application/json'):
                    try:
                        data = response.json()
                        if isinstance(data, dict) and data.get('success'):
                            logger.info(f"Successfully created JSON backup using endpoint: {endpoint}")
                            json_backup = data
                            break
                        elif isinstance(data, dict) and 'obj' in data:
                            # Handle list endpoint as fallback
                            logger.info("Created JSON backup using inbounds list as fallback")
                            json_backup = {
                                'success': True,
                                'msg': 'Backup created from inbounds list',
                                'obj': data['obj']
                            }
                            break
                    except ValueError:
                        pass
                
                # Handle binary response
                if response.content and not response.content.startswith(b'SQLite format'):
                    logger.info(f"Successfully created binary backup using endpoint: {endpoint}")
                    json_backup = response.content
                    break
                
            except APIError as e:
                json_error = str(e)
                logger.warning(f"Failed to create JSON backup using endpoint {endpoint}: {json_error}")
                try:
                    self.login()
                except:
                    pass
                continue
            except Exception as e:
                json_error = str(e)
                logger.error(f"Unexpected error using endpoint {endpoint}: {json_error}")
                continue
        
        # Return results
        if db_backup or json_backup:
            return {
                'db_backup': db_backup,
                'json_backup': json_backup,
                'db_error': db_error,
                'json_error': json_error
            }
        
        # If we get here, all endpoints failed
        error_msg = f"All backup endpoints failed. DB error: {db_error}, JSON error: {json_error}"
        logger.error(error_msg)
        raise APIError(error_msg)

    def reset_traffic(self, uuid: str, inbound_id: int = None, email: str = None) -> bool:
        """Reset client traffic usage"""
        try:
            logger.info(f"Attempting to reset traffic for UUID: {uuid}")
            
            # Check if we have the required parameters
            if inbound_id is None or email is None:
                logger.info(f"Missing parameters (inbound_id: {inbound_id}, email: {email}), attempting to get from client info")
                
                # Try to get them from client info
                client_info = self.get_client_info(uuid=uuid)
                
                if not client_info:
                    logger.error(f"Failed to retrieve client info for UUID: {uuid}")
                    
                    # Try one more time to get client info by directly calling the API
                    try:
                        response = self._make_request('GET', f'/panel/api/inbounds/list')
                        inbounds = response.get('obj', [])
                        
                        # Search all inbounds for the client with this UUID
                        for inbound in inbounds:
                            inbound_id = inbound.get('id')
                            settings = inbound.get('settings')
                            
                            # Parse settings if it's a string
                            if isinstance(settings, str):
                                try:
                                    import json
                                    settings = json.loads(settings)
                                except:
                                    continue
                            
                            # Look for client with matching UUID
                            if isinstance(settings, dict) and 'clients' in settings:
                                for client in settings.get('clients', []):
                                    if client.get('id') == uuid:
                                        email = client.get('email')
                                        logger.info(f"Found client in inbound {inbound_id} with email {email}")
                                        break
                                
                                if email:
                                    break
                    except Exception as e:
                        logger.error(f"Error searching inbounds for client: {str(e)}")
                
                else:
                    logger.info(f"Client info retrieved successfully")
                    inbound_id = client_info.get('inbound_id')
                    email = client_info.get('email')
                    
                    if inbound_id is None:
                        logger.error(f"Client info does not contain inbound_id field: {client_info}")
                    
                    if email is None:
                        logger.error(f"Client info does not contain email field: {client_info}")
                
                # If still missing required parameters, return error
                if inbound_id is None or email is None:
                    logger.error(f"Missing required parameters for reset_traffic: inbound_id={inbound_id}, email={email}")
                    return False
            
            # Use the standard API endpoint format
            endpoint = f"/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}"
            logger.info(f"Resetting traffic for user {email} in inbound {inbound_id}")
            response = self._make_request('POST', endpoint)
            
            # Verify success
            if isinstance(response, dict):
                success = response.get('success', False)
                if success:
                    logger.info(f"Successfully reset traffic for {email}")
                else:
                    logger.warning(f"API returned success=false when resetting traffic for {email}: {response.get('msg', 'No message')}")
                return success
            else:
                logger.error(f"Failed to reset traffic for {email}: Invalid response format")
                return False
                
        except Exception as e:
            logger.error(f"Error resetting traffic: {str(e)}")
            return False

    def set_traffic(self, uuid: str, gb: int) -> bool:
        """Set client traffic limit in GB"""
        try:
            # Use the direct update_client method with better error handling
            return self.update_client(uuid=uuid, traffic_gb=gb)
        except Exception as e:
            logger.error(f"Error setting traffic: {str(e)}")
            return False

    def set_expiry(self, uuid: str, days: int) -> bool:
        """Set client expiry date in days"""
        try:
            # Use the direct update_client method with better error handling
            return self.update_client(uuid=uuid, expiry_days=days)
        except Exception as e:
            logger.error(f"Error setting expiry: {str(e)}")
            return False

    def set_unlimited(self, uuid: str) -> bool:
        """Set client traffic to unlimited by using a very large value"""
        try:
            # Use update_client with a very large value
            return self.update_client(uuid=uuid, traffic_gb=0)  # 0 means unlimited (handled in update_client)
        except Exception as e:
            logger.error(f"Error setting unlimited: {str(e)}")
            return False

    def delete_client(self, uuid: str, inbound_id: int = None) -> bool:
        """Delete a client"""
        try:
            # Check if we have the required inbound_id parameter
            if inbound_id is None:
                # Try to get it from client info
                client_info = self.get_client_info(uuid=uuid)
                if client_info:
                    inbound_id = client_info.get('inbound_id')
                
                # If still missing required parameter, return error
                if inbound_id is None:
                    logger.error("Missing required parameter for delete_client: inbound_id")
                    return False
            
            # Use the standard API endpoint format
            endpoint = f"/panel/api/inbounds/{inbound_id}/delClient/{uuid}"
            logger.info(f"Deleting client {uuid} from inbound {inbound_id}")
            response = self._make_request('POST', endpoint)
            
            # Verify success - response is already a dict from _make_request
            if isinstance(response, dict):
                success = response.get('success', False)
                if success:
                    logger.info(f"Successfully deleted client {uuid}")
                else:
                    logger.warning(f"API returned success=false when deleting client {uuid}: {response.get('msg', 'No message')}")
                return success
            else:
                logger.error(f"Failed to delete client {uuid}: Invalid response format")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting client: {str(e)}")
            return False

    def update_client(self, uuid: str, inbound_id: int = None, traffic_gb: int = None, expiry_days: int = None, expiry_time: int = None) -> bool:
        """Update client using the direct API endpoint with better error handling"""
        try:
            logger.info(f"Updating client {uuid} with traffic_gb={traffic_gb}, expiry_days={expiry_days}, expiry_time={expiry_time}")
            
            # Get current client info to update specific fields
            client_info = self.get_client_info(uuid=uuid)
            if not client_info:
                logger.error(f"Client info not found for UUID: {uuid}")
                return False
                
            # Get inbound ID if not provided
            if inbound_id is None:
                inbound_id = client_info.get('inbound_id')
                if not inbound_id:
                    logger.error(f"Inbound ID not found for client {uuid}")
                    return False
            
            # Extract client details from client_info
            client_details = {}
            for key in ['id', 'flow', 'email', 'limitIp', 'totalGB', 'expiryTime', 'enable', 'tgId', 'subId', 'reset']:
                if key in client_info:
                    client_details[key] = client_info[key]
            
            # Ensure required fields exist
            if 'id' not in client_details:
                client_details['id'] = uuid
            if 'email' not in client_details:
                client_details['email'] = client_info.get('email', '')
            if 'enable' not in client_details:
                client_details['enable'] = True
            if 'flow' not in client_details:
                client_details['flow'] = ""
            if 'limitIp' not in client_details:
                client_details['limitIp'] = 0
            if 'tgId' not in client_details:
                client_details['tgId'] = ""
            if 'subId' not in client_details:
                client_details['subId'] = ""
            if 'reset' not in client_details:
                client_details['reset'] = 0
                
            # Update traffic if specified
            if traffic_gb is not None:
                if traffic_gb > 0:
                    # Convert GB to bytes
                    client_details['totalGB'] = traffic_gb * 1024 * 1024 * 1024
                else:
                    # Set to a very large number for unlimited
                    client_details['totalGB'] = 1099511627776  # 1TB
            
            # Update expiry if days specified
            if expiry_days is not None:
                if expiry_days > 0:
                    # Calculate new expiry time based on current time + days
                    current_time_ms = int(time.time() * 1000)
                    client_details['expiryTime'] = current_time_ms + (expiry_days * 24 * 60 * 60 * 1000)
                else:
                    # Set to a far future date for unlimited
                    client_details['expiryTime'] = int(time.time() * 1000) + (10 * 365 * 24 * 60 * 60 * 1000)  # 10 years
            
            # Use specific expiry time if provided (overrides days)
            if expiry_time is not None:
                client_details['expiryTime'] = expiry_time
                
            # Prepare the request payload
            settings = {"clients": [client_details]}
            payload = {
                "id": int(inbound_id),
                "settings": json.dumps(settings)
            }
            
            logger.info(f"Sending update request for client {uuid} with payload: {payload}")
            
            # Send update request
            endpoint = f"/panel/api/inbounds/updateClient/{uuid}"
            response = self._make_request('POST', endpoint, json=payload)
            
            # Check response
            data = response.json()
            success = data.get('success', False)
            
            if success:
                logger.info(f"Successfully updated client {uuid}")
            else:
                logger.error(f"Failed to update client {uuid}: {data.get('msg', 'Unknown error')}")
                
            return success
            
        except Exception as e:
            logger.error(f"Error updating client: {str(e)}\n{traceback.format_exc()}")
            return False

    def add_client(self, inbound_id: int, email: str, uuid: str = None, traffic_gb: int = 0, 
                  expiry_days: int = 0, limit_ip: int = 0, telegram_id: str = "", 
                  enable: bool = True) -> Union[str, bool]:
        """Add a new client to an inbound using the official XUI panel API"""
        try:
            logger.info(f"Adding client with email={email} to inbound_id={inbound_id}")
            
            # Check if email already exists
            existing_client = None
            try:
                inbound_info = self._get_inbound_info(inbound_id)
                if inbound_info and 'settings' in inbound_info:
                    settings = inbound_info.get('settings')
                    if isinstance(settings, str):
                        settings = json.loads(settings)
                    if isinstance(settings, dict) and 'clients' in settings:
                        for client in settings.get('clients', []):
                            if client.get('email') == email:
                                existing_client = client
                                break
            except Exception as e:
                logger.error(f"Error checking existing client: {str(e)}")
            
            # If client exists, delete it first
            if existing_client:
                logger.info(f"Found existing client with email {email}, deleting it first")
                if not self.delete_client(existing_client.get('id'), inbound_id):
                    logger.error(f"Failed to delete existing client with email {email}")
                    return False
            
            # Generate UUID if not provided
            if not uuid:
                import uuid as uuid_lib
                uuid = str(uuid_lib.uuid4())
                
            # Generate random subscription ID
            import random
            import string
            sub_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))
            
            # Calculate expiry time if days are provided
            if expiry_days > 0:
                current_time_ms = int(time.time() * 1000)
                expiry_time = current_time_ms + (expiry_days * 24 * 60 * 60 * 1000)
            else:
                expiry_time = 0  # 0 means unlimited
            
            # Convert GB to bytes
            total_bytes = 0
            if traffic_gb > 0:
                total_bytes = traffic_gb * 1024 * 1024 * 1024
            
            # Create client object
            client = {
                "id": uuid,
                "flow": "",
                "email": email,
                "limitIp": limit_ip,
                "totalGB": total_bytes,
                "expiryTime": expiry_time,
                "enable": enable,
                "tgId": telegram_id,
                "subId": sub_id,
                "reset": 0
            }
            
            # Prepare the request payload
            settings = {"clients": [client]}
            payload = {
                "id": int(inbound_id),
                "settings": json.dumps(settings)
            }
            
            logger.info(f"Sending add client request with payload: {payload}")
            
            # Send request to add client
            endpoint = "/panel/api/inbounds/addClient"
            response = self._make_request('POST', endpoint, json=payload)
            
            # Check response
            if isinstance(response, dict):
                data = response
            else:
                data = response.json()
            success = data.get('success', False)
            
            if success:
                logger.info(f"Successfully added client {email} with UUID {uuid}")
                return uuid
            else:
                logger.error(f"Failed to add client {email}: {data.get('msg', 'Unknown error')}")
                return False
            
        except Exception as e:
            logger.error(f"Error adding client: {str(e)}\n{traceback.format_exc()}")
            return False
            
    def _get_inbound_info(self, inbound_id: int) -> Dict[str, Any]:
        """Get inbound information including client details
        
        Args:
            inbound_id: The ID of the inbound to get info for
            
        Returns:
            Dict: Inbound information dictionary
        """
        try:
            # Get list of inbounds
            response = self._make_request('GET', '/panel/api/inbounds/list')
            
            if isinstance(response, dict) and response.get('success'):
                inbounds = response.get('obj', [])
                
                # Find the inbound with the matching ID
                for inbound in inbounds:
                    if inbound.get('id') == inbound_id:
                        return inbound
            
            return {}
        except Exception as e:
            logger.error(f"Error getting inbound info: {str(e)}")
            return {}

    def close(self):
        """Close the session and cleanup resources"""
        try:
            if self.session:
                self.session.close()
            logger.info("Panel API session closed")
        except Exception as e:
            logger.error(f"Error closing panel API session: {str(e)}")  