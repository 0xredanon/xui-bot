import requests
from typing import Dict, Any

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

    def get_client_traffics(self, email: str) -> Dict[str, Any]:
        """Get client traffic information."""
        response = self.session.get(f'{self.base_url}/panel/api/inbounds/getClientTraffics/{email}')
        if response.status_code == 200:
            return response.json()
        return None

    def close(self):
        """Close the session."""
        self.session.close() 