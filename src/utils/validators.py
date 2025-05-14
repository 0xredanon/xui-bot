import re
import uuid

def is_valid_email(email: str) -> bool:
    """Validate email format."""
    pattern = r'^[a-zA-Z0-9]+$'
    return bool(re.match(pattern, email))

def is_valid_uuid(uuid_str: str) -> bool:
    """Validate UUID format."""
    try:
        uuid_obj = uuid.UUID(uuid_str)
        return str(uuid_obj) == uuid_str
    except ValueError:
        return False 