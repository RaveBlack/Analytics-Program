## Workspace

This repo contains multiple experiments. The **privacy-compliant, production-ready** beacon system requested in this task lives in:

- `privacy_beacon/`

Run it:

```bash
python3 privacy_beacon/server.py run
```

Docs:

- `privacy_beacon/README.md`

---

## IP & Data Security Tool (CLI, no geolocation)

Single-file tool: `ip_data_security_tool.py`

### Features

- **IP validation**: only attempts lookups for valid IPv4/IPv6, and only if the IP is **public/global** (uses `ipaddress`)
- **Network metadata only**: fetches **ASN / Organization** (no city/country/coords)
- **Password hashing (local-only)**: SHA-256 (stdlib) or bcrypt (optional dependency)
- **Email masking**: validates format and masks local part (e.g. `u***r@example.com`)

### Run (Linux/macOS/Windows)

```bash
python3 ip_data_security_tool.py
```

Subcommands:

```bash
python3 ip_data_security_tool.py ip 8.8.8.8
python3 ip_data_security_tool.py email user@example.com
python3 ip_data_security_tool.py hash --algo sha256
```

ASN lookups require `requests`:

```bash
pip install requests
```

### Build a single `.exe` for Windows (PyInstaller one-file)

On Windows (PowerShell):

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install requests pyinstaller

py -m PyInstaller --onefile --name ip_data_security_tool ip_data_security_tool.py
```

Output:

- `dist\ip_data_security_tool.exe`

