import ipaddress
import hashlib
import re
import os
import requests
from cryptography.fernet import Fernet

# Key management for encryption
KEY_FILE = "secret.key"

def load_or_generate_key():
    """
    Loads the encryption key from the current directory or generates a new one.
    Returns:
        bytes: The encryption key.
    """
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as key_file:
            return key_file.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as key_file:
            key_file.write(key)
        return key

def encrypt_data(data, key):
    """
    Encrypts a string using Fernet (symmetric encryption).
    Returns:
        str: The encrypted data (encoded as string).
    """
    f = Fernet(key)
    # Fernet encrypt/decrypt expects bytes
    encrypted = f.encrypt(data.encode())
    return encrypted.decode()

def decrypt_data(encrypted_data, key):
    """
    Decrypts a Fernet-encrypted string.
    Returns:
        tuple: (success, decrypted_string_or_error)
    """
    f = Fernet(key)
    try:
        decrypted = f.decrypt(encrypted_data.encode())
        return True, decrypted.decode()
    except Exception as e:
        return False, str(e)

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
