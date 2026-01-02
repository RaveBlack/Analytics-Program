# IP & Data Security Tool (Web Server Edition)

A single-file, privacy-focused web application for IP analysis and secure data handling.

## Artifacts

1.  **Linux Executable**: `ip_security_tool_linux`
    - A standalone binary containing the entire application (Python interpreter + Dependencies + Code).
    - Can be run on Linux systems without installing Python or libraries.
2.  **Source Code**: `server.py`
    - The Python source code.

## Features

- **Web Interface**: Clean HTML/CSS/JS frontend.
- **IP Validation & Metadata**: Checks Public/Private IPs and fetches non-location metadata.
- **Secure Encryption**: AES (Fernet) encryption for passwords/emails.
- **Worker Security**: Uses `secret.key` for decryption (must be present in the running directory).

## Usage

### Running the Executable (Linux)

```bash
# Make it executable (if needed)
chmod +x ip_security_tool_linux

# Run
./ip_security_tool_linux
```

The server will start on port `5000`. Access it at:
- `http://localhost:5000`
- `http://YOUR_SERVER_IP:5000`

### Building for Windows (.exe)

Since this environment is Linux, the generated file is a Linux binary. To get a Windows `.exe`:
1.  Copy `server.py` to a Windows machine.
2.  Install Python and requirements: `pip install flask requests cryptography pyinstaller`.
3.  Run: `pyinstaller --onefile --name ip_tool server.py`.

### Encryption Key

On first run, a `secret.key` file is generated. **Keep this file.** It is required to decrypt any data secured by the tool.
