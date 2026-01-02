import ipaddress
import hashlib
import re
import requests

def validate_and_check_ip(ip_str):
    """
    Validates if the string is a valid IPv4 or IPv6 address and checks if it is public.
    Returns:
        tuple: (is_valid, is_public, ip_obj_or_error_message)
    """
    try:
        ip_obj = ipaddress.ip_address(ip_str)
        # is_global is available in Python 3.4+. It returns True if the address is allocated 
        # for public networks. 
        # Note: ipaddress.is_global excludes private, loopback, link-local, reserved, etc.
        is_public = ip_obj.is_global
        return True, is_public, ip_obj
    except ValueError:
        return False, False, "Invalid IP address format."

def get_ip_metadata(ip_str):
    """
    Fetches ASN, ISP, and Organization metadata for the given IP.
    Explicitly requests only non-location fields.
    """
    url = f"http://ip-api.com/json/{ip_str}"
    # Fields: status, message, isp, org, as
    params = {
        "fields": "status,message,isp,org,as"
    }
    
    try:
        response = requests.get(url, params=params, timeout=5)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        return {"status": "fail", "message": str(e)}

def hash_password(password):
    """
    Hashes a password using SHA-256.
    """
    # Use SHA-256 as requested
    return hashlib.sha256(password.encode()).hexdigest()

def mask_email(email):
    """
    Validates email format and masks it (e.g., u***r@example.com).
    Returns:
        tuple: (is_valid, masked_email_or_error)
    """
    # Simple regex for email validation
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    
    if not re.match(email_regex, email):
        return False, "Invalid email format."
    
    try:
        user_part, domain_part = email.split('@')
        
        if len(user_part) <= 1:
            masked_user = "*" * len(user_part)
        elif len(user_part) <= 3:
            masked_user = user_part[0] + "*" * (len(user_part) - 1)
        else:
            masked_user = user_part[0] + "***" + user_part[-1]
            
        return True, f"{masked_user}@{domain_part}"
    except Exception:
        return False, "Error processing email."
