# IP & Data Security Tool (Web Server Edition)

A single-file, privacy-focused web application for IP analysis and secure data handling.

## Artifact

The tool is compiled into a single bytecode file: `ip_tool.pyc`.

## Features

1.  **Web Interface**: A clean HTML/CSS frontend embedded in the application.
2.  **IP Validation & Metadata**: 
    - Validates IPv4/IPv6.
    - Checks Public vs Private status.
    - Fetches metadata (ISP, Org, ASN) for public IPs.
    - **Privacy**: No geolocation.
3.  **Secure Encryption**:
    - Uses AES (Fernet) encryption.
    - **Worker Access Only**: Requires a `secret.key` file in the same directory to decrypt.
4.  **Email Masking**: Validates and masks emails.

## Usage

### 1. Run Locally or on a Server

Run the compiled file directly with Python:

```bash
python3 ip_tool.pyc
```

- The server starts on port `5000` by default.
- It listens on `0.0.0.0`, meaning it is accessible from the network.

### 2. Domain Setup (Type A Record)

To host this on a domain:

1.  **Get your Server IP**: Find the Public IPv4 address of the machine running this tool.
2.  **DNS Configuration**: Go to your domain registrar and create an **A Record**.
    - **Host**: `@` (or a subdomain like `tool`)
    - **Value**: Your Server's Public IP.
3.  **Access**: Open your browser to `http://yourdomain.com:5000`.

### 3. Encryption Key

- On the first run, the tool generates a `secret.key` file in the working directory.
- **Keep this file safe.**
- Only a server/worker with this exact `secret.key` can decrypt data encrypted by the tool.

## Development

The source code is in `server.py`. To re-compile:

```bash
python3 -m py_compile server.py
mv __pycache__/server.*.pyc ip_tool.pyc
```
