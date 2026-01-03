# L7 Network Traffic Monitor

This is a local network traffic monitor application that works like a simplified Wireshark with a web-based interface. It focuses on Layer 7 (Application Layer) traffic and attempts to decode payloads to plain text.

## Features
- **Real-time Monitoring**: Captures packets from your local network interface.
- **Layer 7 Decoding**: Automatically attempts to decode payloads to UTF-8 Plain Text.
- **Hex/Base64 Views**: Options to view binary data in Hex or Base64 formats.
- **Filtering**: Filter traffic by IP address.
- **Web UI**: "Terminal + Wireshark" feel with buttons and interactive table.
- **Permissioned Diagnostics**: Ping + traceroute buttons from the web UI.
- **Wireshark CLI Captures**: Start/stop duration-limited captures using `tshark`, list and download capture files.
- **Device List**: Shows devices from your OS ARP/neighbor cache (passive; no scanning).
- **Device Discovery (Safe)**: Optional controlled **ping sweep** on your **private LAN** to help populate the ARP/neighbor cache, then displays discovered entries.
- **Router Leases Import (Optional)**: Upload a router DHCP leases export (CSV or OpenWrt `dhcp.leases`) and merge it with neighbor/ARP data. Download merged devices as CSV.
- **Remote Control (Agents)**: (Your devices only) Optional agent that can connect back to the dashboard and accept **authorized** commands like shutdown.

## Prerequisites
- Python 3.x installed on your device.
- `pip` (Python package manager).
- Administrator/Root privileges (required for capturing network packets).
- Optional: **Wireshark / tshark** installed (for file captures).

> This project is intended for monitoring and troubleshooting **networks you own or have explicit permission to test**.
>
> Remote shutdown is only supported for devices **you control** by running an agent on them. There is no “shutdown by IP” feature.

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
   - **Tools panel**:
     - **Ping / Traceroute**: Run basic diagnostics and see the output in the page.
     - **Devices**: View ARP/neighbor-cache entries (may be empty until your machine talks to devices).
     - **Device discovery**: Runs a limited ping sweep on your local private subnet, then shows the neighbor/ARP table.
     - **Router leases import**: Upload your router’s DHCP leases export to get a more complete “who’s connected” list, then use “Download CSV”.
     - **Captures (tshark)**: Start a duration-limited capture and then download the resulting `.pcapng`.
     - **Remote control (agents)**: Run `agent.py` on a device you own, then refresh “Agents” and (optionally) issue shutdown.

## Remote control agent setup (your devices only)

The agent connects to the server over Socket.IO and will only execute shutdown when explicitly enabled.

### Server hardening (recommended)
- Set an admin key for shutdown requests:
  - `ADMIN_API_KEY=<strong secret>`
- Set an agent shared key (so only your agents can register):
  - `AGENT_SHARED_KEY=<strong secret>`
- Access the dashboard remotely via **VPN** (Tailscale/WireGuard) rather than exposing port 5000 to the public internet.

### Run agent on a device

- **Windows (PowerShell as Administrator)**:
  - Set env vars and run:
    - `setx SERVER_URL "http://<your-server-ip>:5000"`
    - `setx AGENT_ID "my-pc-1"`
    - `setx AGENT_SHARED_KEY "<same as server>"`
    - `setx ENABLE_SHUTDOWN "1"`
  - Then start:
    - `python agent.py`

- **Linux/macOS**:
  - `SERVER_URL="http://<your-server-ip>:5000" AGENT_ID="my-pc-1" AGENT_SHARED_KEY="<same as server>" ENABLE_SHUTDOWN=1 python3 agent.py`

> The UI will prompt you to type `SHUTDOWN` before sending the command. The agent will refuse to power off unless `ENABLE_SHUTDOWN=1` is set on that machine.

## Wireshark / tshark setup

- **Linux (Debian/Ubuntu)**:
  - Install `tshark` via your package manager (often `wireshark-common` / `tshark`).
  - You may need privileges/capabilities to capture (running as root is simplest for local testing).
- **Windows**:
  - Install Wireshark and ensure `tshark.exe` is available on `PATH` (or use the Wireshark install that includes it).

## Troubleshooting
- **No Packets?** Ensure you are running with `sudo` or Administrator privileges. Regular users often cannot capture network traffic.
- **Address in use?** If port 5000 is taken, edit `app.py` and change the port number at the bottom of the file.
- **tshark missing?** The Tools panel will show `tshark: missing` until Wireshark/tshark is installed and on `PATH`.
- **Discovery didn’t find devices?** Many devices block ICMP/ping. Discovery relies on ping to help populate ARP/neighbor tables, so results vary. For an authoritative list, use your router’s **DHCP leases/connected clients** page.
