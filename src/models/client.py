from dataclasses import dataclass
from typing import Optional
from datetime import datetime

@dataclass
class Client:
    email: str
    uuid: str
    enable: bool
    total_gb: int
    expiry_time: int
    limit_ip: int
    tg_id: str
    sub_id: str
    reset: int = 0
    flow: str = ""

    @property
    def is_expired(self) -> bool:
        """Check if client subscription is expired."""
        if self.expiry_time == 0:
            return False
        return self.expiry_time <= int(datetime.now().timestamp() * 1000)

    @property
    def has_unlimited_traffic(self) -> bool:
        """Check if client has unlimited traffic."""
        return self.total_gb == 0

    @property
    def remaining_days(self) -> Optional[int]:
        """Get remaining days until expiration."""
        if self.expiry_time == 0:
            return None
        remaining = (self.expiry_time - int(datetime.now().timestamp() * 1000)) / (1000 * 60 * 60 * 24)
        return int(remaining) if remaining > 0 else 0 