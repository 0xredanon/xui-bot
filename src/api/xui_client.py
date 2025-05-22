import os
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta, timezone
from proj import *
import pytz
import json
import logging

from src.utils.logger import CustomLogger
from src.utils.formatting import format_date, format_remaining_time

# Initialize logger
logger = CustomLogger("XUIClient")

# Add a dedicated logger for date debugging
date_debug_logger = logging.getLogger("DateDebug")
date_debug_logger.setLevel(logging.DEBUG)
date_debug_handler = logging.FileHandler("date_debug.log", encoding="utf-8")
date_debug_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
date_debug_logger.addHandler(date_debug_handler)

class XUIClient:
    def __init__(self):
        # Hardcoded configuration
        self.base_url = PANEL_URL  # Replace with your X-UI panel URL
        self.username = PANEL_USERNAME  # Replace with your X-UI username
        self.password = PANEL_PASSWORD  # Replace with your X-UI password
        self.session = requests.Session()
        self._login()

    def _login(self) -> bool:
        """Login to X-UI panel."""
        login_payload = {
            'username': self.username,
            'password': self.password
        }
        response = self.session.post(f'{self.base_url}/login', json=login_payload)
        return response.status_code == 200

    def get_client_traffics(self, email: str) -> Optional[Dict[str, Any]]:
        """Get client traffic information."""
        response = self.session.get(f'{self.base_url}/panel/api/inbounds/getClientTraffics/{email}')
        if response.status_code == 200:
            return response.json()
        return None

    def create_backup(self) -> Dict[str, Any]:
        """Create a backup of inbounds configuration.
        
        Returns:
            Dict containing backup data and status information
        """
        try:
            # Try new createbackup endpoint first
            response = self.session.get(f'{self.base_url}/panel/api/inbounds/createbackup')
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return {
                        'success': True,
                        'data': data.get('obj', {}),
                        'message': 'Backup created successfully using new endpoint'
                    }
            
            # Fallback to legacy backup endpoint
            response = self.session.post(f'{self.base_url}/panel/api/inbounds/backup')
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return {
                        'success': True,
                        'data': data.get('obj', {}),
                        'message': 'Backup created successfully using legacy endpoint'
                    }
            
            # Final fallback to list endpoint
            response = self.session.get(f'{self.base_url}/panel/api/inbounds/list')
            if response.status_code == 200:
                data = response.json()
                if data.get('success'):
                    return {
                        'success': True,
                        'data': data.get('obj', {}),
                        'message': 'Backup created from inbounds list'
                    }
                    
            return {
                'success': False,
                'error': 'Failed to create backup using any available endpoint',
                'status_code': response.status_code
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Request failed: {str(e)}',
                'exception': str(e)
            }
        except Exception as e:
            return {
                'success': False,
                'error': f'Unexpected error: {str(e)}',
                'exception': str(e)
            }

    def get_client_ips(self, email: str) -> Optional[Dict[str, Any]]:
        """Get IP addresses used by a client."""
        response = self.session.post(f'{self.base_url}/panel/api/inbounds/clientIps/{email}')
        if response.status_code == 200:
            return response.json()
        return None

    def add_client(self, inbound_id: int, email: str, uuid: str, total_gb: int = 0,
                  expiry_time: int = 0, limit_ip: int = 0, tg_id: str = "",
                  enable: bool = True) -> Optional[Dict[str, Any]]:
        """Add a new client to an inbound."""
        settings = {
            "clients": [{
                "id": uuid,
                "flow": "",
                "email": email,
                "limitIp": limit_ip,
                "totalGB": total_gb,
                "expiryTime": expiry_time,
                "enable": enable,
                "tgId": tg_id,
                "subId": self._generate_sub_id(),
                "reset": 0
            }]
        }
        
        payload = {
            "id": inbound_id,
            "settings": str(settings)
        }
        
        response = self.session.post(f'{self.base_url}/panel/api/inbounds/addClient', json=payload)
        if response.status_code == 200:
            return response.json()
        return None

    def update_client(self, inbound_id: int, uuid: str, email: str, 
                     total_gb: int, expiry_time: int, enable: bool = True,
                     limit_ip: int = 0, tg_id: str = "") -> Optional[Dict[str, Any]]:
        """Update an existing client."""
        settings = {
            "clients": [{
                "id": uuid,
                "flow": "",
                "email": email,
                "limitIp": limit_ip,
                "totalGB": total_gb,
                "expiryTime": expiry_time,
                "enable": enable,
                "tgId": tg_id,
                "subId": self._generate_sub_id(),
                "reset": 0
            }]
        }
        
        payload = {
            "id": inbound_id,
            "settings": str(settings)
        }
        
        response = self.session.post(f'{self.base_url}/panel/api/inbounds/updateClient/{uuid}', json=payload)
        if response.status_code == 200:
            return response.json()
        return None

    def reset_client_traffic(self, inbound_id: int, email: str) -> bool:
        """Reset traffic statistics for a client."""
        try:
            response = self.session.post(f'{self.base_url}/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}')
            if response.status_code == 200:
                return True
            else:
                print(f"Error resetting traffic: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"Exception resetting traffic: {str(e)}")
            return False

    def get_online_clients(self) -> Optional[List[Dict[str, Any]]]:
        """Get list of currently online clients."""
        response = self.session.post(f'{self.base_url}/panel/api/inbounds/onlines')
        if response.status_code == 200:
            data = response.json()
            if isinstance(data, dict) and 'obj' in data:
                return data['obj']
            return []
        return None

    def _generate_sub_id(self) -> str:
        """Generate a random subscription ID."""
        import random
        import string
        return ''.join(random.choices(string.ascii_lowercase + string.digits, k=16))

    def close(self):
        """Close the session."""
        self.session.close()

    def _make_request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make an HTTP request to the X-UI API"""
        url = f"{self.base_url}{endpoint}"
        response = self.session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()
    
    def get_clients(self, telegram_id: Optional[int] = None) -> List[Dict]:
        """Get all clients or filter by telegram_id"""
        response = self._make_request("GET", "/panel/api/inbounds/list")
        clients = []
        
        tehran_tz = pytz.timezone('Asia/Tehran')

        for inbound in response["obj"]:
            inbound_id = inbound["id"]
            # Ensure settings is a dictionary, parse if it's a string
            settings_raw = inbound.get("settings")
            if isinstance(settings_raw, str):
                try:
                    settings = json.loads(settings_raw)
                except json.JSONDecodeError:
                    # Log error or handle as appropriate if settings are malformed
                    settings = {"clients": []} # Default to empty if parsing fails
            elif isinstance(settings_raw, dict):
                settings = settings_raw
            else:
                settings = {"clients": []} # Default if settings are missing or wrong type
            
            for client in settings.get("clients", []): # Use .get for safety
                if telegram_id and client.get("tgId") != str(telegram_id): # Compare tgId as string
                    continue
                
                expire_date_str = "Never"
                expiry_time_ms = client.get("expiryTime", 0)
                logger.info(f"Raw expiry time from API: {expiry_time_ms} (type: {type(expiry_time_ms)})")
                
                if isinstance(expiry_time_ms, (int, float)) and expiry_time_ms > 0:
                    expire_date_str = expiry_time_ms  # Pass raw timestamp instead of formatted string
                    logger.info(f"Using expiry time: {expire_date_str}")

                client_data = {
                    "uuid": client.get("id"), # Use .get for safety
                    "email": client.get("email"),
                    "inbound_id": inbound_id,
                    "enable": client.get("enable", False),
                    "total_traffic": client.get("totalGB", 0),
                    "used_traffic": round(
                        (client.get("up", 0) + client.get("down", 0)) / (1024 * 1024 * 1024),
                        2
                    ),
                    "expire_time": expire_date_str,  # Changed from expire_date to expire_time
                    "protocol": inbound.get("protocol"),
                    "port": inbound.get("port"),
                    "settings": client # Original client dict for other uses
                }
                logger.info(f"Client data prepared: {client_data}")
                clients.append(client_data)
        
        return clients
    
    def get_client(self, client_uuid: str) -> Optional[Dict]:
        """Get a specific client by UUID"""
        clients = self.get_clients()
        for client in clients:
            if client["uuid"] == client_uuid:
                return client
        return None
    
    def set_traffic(self, client_uuid: str, gb: int):
        """Set traffic limit for a client"""
        client = self.get_client(client_uuid)
        if not client:
            raise ValueError("Client not found")
        
        endpoint = f"/api/inbound/{client['inbound_id']}/client/{client_uuid}"
        client_data = client["settings"]
        client_data["total_gb"] = gb
        
        self._make_request("PUT", endpoint, json=client_data)
    
    def set_expiry(self, client_uuid: str, days: int):
        """Set expiry date for a client"""
        client = self.get_client(client_uuid)
        if not client:
            raise ValueError("Client not found")
        
        endpoint = f"/api/inbound/{client['inbound_id']}/client/{client_uuid}"
        client_data = client["settings"].copy() # Use .copy() to avoid modifying the cached client dict directly
        
        if days > 0:
            expiry_time = int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp() * 1000)
        else:
            expiry_time = 0  # Never expires
        
        client_data["expiryTime"] = expiry_time
        self._make_request("PUT", endpoint, json=client_data)
    
    def reset_traffic(self, client_uuid: str):
        """Reset traffic usage for a client"""
        client = self.get_client(client_uuid)
        if not client:
            raise ValueError("Client not found")
        
        # Use the documented endpoint with inbound_id and email
        inbound_id = client['inbound_id']
        email = client['email']
        
        # Try the new API endpoint first
        try:
            endpoint = f"/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}"
            response = self.session.post(f'{self.base_url}{endpoint}')
            if response.status_code == 200:
                return True
        except Exception as e:
            print(f"Error using new API endpoint: {str(e)}")
            
        # Fallback to the old endpoint as last resort
        try:
            endpoint = f"/api/inbound/{inbound_id}/client/{client_uuid}/reset"
            self._make_request("POST", endpoint)
            return True
        except:
            return False
    
    def set_unlimited(self, client_uuid: str):
        """Set unlimited traffic and no expiry for a client"""
        client = self.get_client(client_uuid)
        if not client:
            raise ValueError("Client not found")
        
        endpoint = f"/api/inbound/{client['inbound_id']}/client/{client_uuid}"
        client_data = client["settings"]
        client_data["total_gb"] = 0  # Unlimited traffic
        client_data["expiryTime"] = 0  # Never expires
        
        self._make_request("PUT", endpoint, json=client_data)
    
    def delete_client(self, client_uuid: str) -> bool:
        """Delete a client by UUID"""
        try:
            client = self.get_client(client_uuid)
            if not client:
                raise ValueError("Client not found")
            
            inbound_id = client['inbound_id']
            
            # Use the documented endpoint
            endpoint = f"/panel/api/inbounds/{inbound_id}/delClient/{client_uuid}"
            response = self.session.post(f'{self.base_url}{endpoint}')
            
            if response.status_code == 200:
                return True
            else:
                print(f"Error deleting client: {response.status_code} - {response.text}")
                
                # Try fallback endpoint
                endpoint = f"/api/inbound/{inbound_id}/client/{client_uuid}"
                response = self.session.delete(f'{self.base_url}{endpoint}')
                return response.status_code == 200
        except Exception as e:
            print(f"Exception deleting client: {str(e)}")
            return False

    def get_client_info(self, uuid: Optional[str] = None, email: Optional[str] = None, inbound_id: Optional[int] = None) -> Dict[str, Any]:
        """Get client information by UUID or email and optionally inbound_id"""
        try:
            logger.info(f"Getting client info for UUID: {uuid} or email: {email}, inbound_id: {inbound_id}")
            date_debug_logger.info(f"=== NEW CALL: uuid={uuid}, email={email}, inbound_id={inbound_id} ===")
            
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
                    logger.info(f"Raw inbound info: {inbound_info}")
                    
                    if inbound_info and 'settings' in inbound_info:
                        settings = inbound_info.get('settings')
                        logger.info(f"Raw settings: {settings}")
                        
                        # Parse settings if it's a string
                        if isinstance(settings, str):
                            try:
                                settings = json.loads(settings)
                                logger.info(f"Parsed settings: {settings}")
                            except Exception as e:
                                logger.error(f"Error parsing settings JSON: {str(e)}")
                                settings = {}
                        
                        # Find matching client
                        if isinstance(settings, dict) and 'clients' in settings:
                            for client in settings.get('clients', []):
                                if (uuid and client.get('id') == uuid) or (email and client.get('email') == email):
                                    logger.info(f"Found matching client: {client}")
                                    # Update client data instead of replacing it
                                    client_data.update({
                                        **client,
                                        'inbound_id': inbound_id,
                                        'protocol': inbound_info.get('protocol', 'unknown'),
                                        'port': inbound_info.get('port', 0),
                                        'is_online': is_online,
                                        'expire_time': client.get('expiryTime', 0),
                                        'last_connection': client.get('lastConnection', 0),
                                        'created_at': client.get('createdAt', 0)
                                    })
                                    logger.info(f"Updated client data: {client_data}")
                                    break
                except Exception as e:
                    logger.error(f"Error in direct inbound lookup: {str(e)}")
            
            # If client not found using direct approach, try the API endpoints
            if not client_data:
                # Try with the specific endpoints for a single client
                if uuid:
                    try:
                        data = self._make_request('GET', f'/panel/api/inbounds/getClientTrafficsById/{uuid}')
                        logger.info(f"API response for UUID {uuid}: {data}")
                        
                        if data.get('success'):
                            obj = data.get('obj', [])
                            if isinstance(obj, list) and obj:
                                client_data.update({
                                    **obj[0],
                                    'is_online': is_online,
                                    'expire_time': obj[0].get('expiryTime', 0),
                                    'last_connection': obj[0].get('lastConnection', 0),
                                    'created_at': obj[0].get('createdAt', 0)
                                })
                            elif isinstance(obj, dict):
                                client_data.update({
                                    **obj,
                                    'is_online': is_online,
                                    'expire_time': obj.get('expiryTime', 0),
                                    'last_connection': obj.get('lastConnection', 0),
                                    'created_at': obj.get('createdAt', 0)
                                })
                            logger.info(f"Client data from API: {client_data}")
                    except Exception as e:
                        logger.error(f"Error getting client info by UUID {uuid}: {str(e)}")
                
                if email and not client_data:
                    try:
                        data = self._make_request('GET', f'/panel/api/inbounds/getClientTraffics/{email}')
                        logger.info(f"API response for email {email}: {data}")
                        
                        if data.get('success'):
                            obj = data.get('obj', [])
                            if isinstance(obj, list) and obj:
                                client_data.update({
                                    **obj[0],
                                    'is_online': is_online,
                                    'expire_time': obj[0].get('expiryTime', 0),
                                    'last_connection': obj[0].get('lastConnection', 0),
                                    'created_at': obj[0].get('createdAt', 0)
                                })
                            elif isinstance(obj, dict):
                                client_data.update({
                                    **obj,
                                    'is_online': is_online,
                                    'expire_time': obj.get('expiryTime', 0),
                                    'last_connection': obj.get('lastConnection', 0),
                                    'created_at': obj.get('createdAt', 0)
                                })
                            logger.info(f"Client data from API: {client_data}")
                    except Exception as e:
                        logger.error(f"Error getting client info by email {email}: {str(e)}")
            
            # Format dates using the same logic as the test file
            if client_data:
                date_debug_logger.info(f"Raw client_data before date formatting: {client_data}")
                
                # Format each date field
                for field in ['created_at', 'last_connection', 'expire_time']:
                    value = client_data.get(field)
                    date_debug_logger.info(f"Field '{field}': raw value = {value} (type: {type(value)})")
                    
                    # Format the date using the same function as the test file
                    formatted_date = format_date(value)
                    date_debug_logger.info(f"Field '{field}': formatted = {formatted_date}")
                    
                    # Add formatted date to client data
                    client_data[f'{field}_formatted'] = formatted_date
                    
                    # For expire_time, also add remaining time
                    if field == 'expire_time':
                        remaining_time = format_remaining_time(value)
                        date_debug_logger.info(f"Field '{field}': remaining time = {remaining_time}")
                        client_data['remaining_time'] = remaining_time
                
                date_debug_logger.info(f"Final client_data after date formatting: {client_data}")
            else:
                date_debug_logger.warning(f"No client information found for UUID={uuid} or email={email}")
            
            return client_data or {}
        except Exception as e:
            logger.error(f"Error getting client info: {str(e)}")
            date_debug_logger.error(f"Exception in get_client_info: {e}")
            return {} 