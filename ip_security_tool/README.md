# IP & Data Security Tool

A Python-based privacy-focused tool for IP analysis and data security tasks.

## Features

1.  **IP Validation & Metadata**: 
    - Validates IPv4/IPv6 addresses.
    - Checks if the IP is public or private.
    - Fetches technical metadata (ISP, ASN, Org) for public IPs using `ip-api.com`.
    - **Privacy**: No geolocation data (city, country, coordinates) is fetched or displayed.

2.  **Password Hashing**:
    - Generates secure SHA-256 hashes for provided passwords.
    - Performed locally for security.

3.  **Email Masking**:
    - Validates and masks email addresses (e.g., `u***r@example.com`).

## Usage

1.  Navigate to the directory:
    ```bash
    cd ip_security_tool
    ```

2.  Run the tool:
    ```bash
    python3 main.py
    ```

## Requirements

- Python 3
- `requests`
- `rich`

(These are pre-installed in the current environment).
