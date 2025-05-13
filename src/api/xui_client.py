import requests
from typing import Dict, Any, Optional, List
from datetime import datetime

class XUIClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url
        self.username = username
        self.password = password
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