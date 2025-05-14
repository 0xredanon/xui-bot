import os
import requests
from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from proj import *
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

    def create_backup(self) -> bool:
        """Create a backup of inbounds configuration."""
        response = self.session.post(f'{self.base_url}/panel/api/inbounds/createbackup')
        return response.status_code == 200

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
        response = self.session.post(f'{self.base_url}/panel/api/inbounds/{inbound_id}/resetClientTraffic/{email}')
        return response.status_code == 200

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
        response = self._make_request("GET", "/api/inbounds")
        clients = []
        
        for inbound in response["obj"]:
            inbound_id = inbound["id"]
            settings = inbound["settings"]
            
            for client in settings["clients"]:
                if telegram_id and client.get("telegram_id") != telegram_id:
                    continue
                
                client_data = {
                    "uuid": client["id"],
                    "email": client["email"],
                    "inbound_id": inbound_id,
                    "enable": client["enable"],
                    "total_traffic": client["total_gb"],
                    "used_traffic": round(
                        (client["up"] + client["down"]) / (1024 * 1024 * 1024),
                        2
                    ),
                    "expire_date": datetime.fromtimestamp(
                        client["expiryTime"] / 1000
                    ).strftime("%Y-%m-%d %H:%M:%S") if client["expiryTime"] > 0 else "Never",
                    "protocol": inbound["protocol"],
                    "port": inbound["port"],
                    "settings": client
                }
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
        client_data = client["settings"]
        
        if days > 0:
            expiry_time = int((datetime.now() + timedelta(days=days)).timestamp() * 1000)
        else:
            expiry_time = 0  # Never expires
        
        client_data["expiryTime"] = expiry_time
        self._make_request("PUT", endpoint, json=client_data)
    
    def reset_traffic(self, client_uuid: str):
        """Reset traffic usage for a client"""
        client = self.get_client(client_uuid)
        if not client:
            raise ValueError("Client not found")
        
        endpoint = f"/api/inbound/{client['inbound_id']}/client/{client_uuid}/reset"
        self._make_request("POST", endpoint)
    
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