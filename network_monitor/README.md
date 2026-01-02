# L7 Network Traffic Monitor

This is a local network traffic monitor application that works like a simplified Wireshark with a web-based interface. It focuses on Layer 7 (Application Layer) traffic and attempts to decode payloads to plain text.

## Features
- **Real-time Monitoring**: Captures packets from your local network interface.
- **Layer 7 Decoding**: Automatically attempts to decode payloads to UTF-8 Plain Text.
- **Hex/Base64 Views**: Options to view binary data in Hex or Base64 formats.
- **Filtering**: Filter traffic by IP address.
- **Web UI**: "Terminal + Wireshark" feel with buttons and interactive table.

## Prerequisites
- Python 3.x installed on your device.
- `pip` (Python package manager).
- Administrator/Root privileges (required for capturing network packets).

## Installation

1. Open a terminal in this directory.
2. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application with sudo (Linux/macOS) or as Administrator (Windows):

   **Linux/macOS:**
   ```bash
   sudo python3 app.py
   ```

   **Windows:**
   Open Command Prompt as Administrator and run:
   ```cmd
   python app.py
   ```

2. Open your web browser and navigate to:
   ```
   http://localhost:5000
   ```

3. **How to use:**
   - **Filter**: Enter an IP address in the top bar and click "Apply Filter" to see traffic only involving that IP.
   - **Pause/Resume**: Use the Pause button to stop the table from updating while you inspect packets.
   - **Inspect**: Click on any row in the table to see the payload in the bottom panel.
   - **Decode**: Use the "Plain Text", "Hex Dump", or "Base64" buttons to change how the payload is displayed.

## Troubleshooting
- **No Packets?** Ensure you are running with `sudo` or Administrator privileges. Regular users often cannot capture network traffic.
- **Address in use?** If port 5000 is taken, edit `app.py` and change the port number at the bottom of the file.
