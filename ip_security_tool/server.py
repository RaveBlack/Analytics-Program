import os
import sys
import re
import ipaddress
import requests
import secrets
from flask import Flask, request, jsonify, render_template_string
from cryptography.fernet import Fernet

# --- CONFIG & KEYS ---
KEY_FILE = "secret.key"

def load_or_generate_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        return key

# Initialize encryption
try:
    ENCRYPTION_KEY = load_or_generate_key()
    fernet = Fernet(ENCRYPTION_KEY)
except Exception as e:
    print(f"Error initializing encryption: {e}")
    # In a real app we might exit, but for a single file script we might want to allow start 
    # and fail only on crypto ops. But the requirement is strict on worker security.
    # We'll allow it but crypto will fail.
    fernet = None

# --- CORE LOGIC ---

def check_ip(ip_str):
    try:
        ip = ipaddress.ip_address(ip_str)
        # is_global excludes private networks
        is_public = ip.is_global
        return {"valid": True, "public": is_public, "version": ip.version, "ip": str(ip)}
    except ValueError:
        return {"valid": False, "error": "Invalid IP address"}

def get_metadata(ip_str):
    try:
        url = f"http://ip-api.com/json/{ip_str}?fields=status,message,isp,org,as"
        resp = requests.get(url, timeout=5)
        return resp.json()
    except Exception as e:
        return {"status": "fail", "message": str(e)}

def mask_email_logic(email):
    email_regex = r"(^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$)"
    if not re.match(email_regex, email):
        return {"valid": False, "error": "Invalid format"}
    try:
        user, domain = email.split('@')
        if len(user) <= 1: masked = "*" * len(user)
        elif len(user) <= 3: masked = user[0] + "*" * (len(user)-1)
        else: masked = user[0] + "***" + user[-1]
        return {"valid": True, "masked": f"{masked}@{domain}"}
    except:
        return {"valid": False, "error": "Processing error"}

# --- FLASK APP ---

app = Flask(__name__)
app.secret_key = secrets.token_hex(16)

HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IP & Data Security Tool</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; background: #f4f4f9; color: #333; }
        .card { background: white; padding: 20px; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        h1 { color: #2c3e50; text-align: center; }
        h2 { border-bottom: 2px solid #eee; padding-bottom: 10px; font-size: 1.2em; color: #34495e; margin-top: 0; }
        .input-group { display: flex; gap: 10px; margin-top: 15px; }
        input[type="text"], textarea { flex-grow: 1; padding: 10px; border: 1px solid #ddd; border-radius: 4px; box-sizing: border-box; font-size: 16px; }
        textarea { width: 100%; margin-bottom: 10px; font-family: monospace; }
        button { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 4px; cursor: pointer; font-size: 16px; white-space: nowrap; transition: background 0.2s; }
        button:hover { background: #2980b9; }
        .result { margin-top: 15px; padding: 15px; background: #f8f9fa; border-left: 4px solid #3498db; border-radius: 4px; white-space: pre-wrap; font-family: monospace; display: none; }
        .error { color: #e74c3c; font-weight: bold; }
        .success { color: #27ae60; font-weight: bold; }
        .dim { color: #7f8c8d; font-size: 0.9em; }
    </style>
</head>
<body>
    <h1>IP & Data Security Tool</h1>
    
    <div class="card">
        <h2>IP Lookup (Public Only)</h2>
        <p class="dim">Checks validity and metadata (ISP, Org, ASN). No geolocation.</p>
        <div class="input-group">
            <input type="text" id="ipInput" placeholder="Enter IPv4 or IPv6 Address">
            <button onclick="lookupIP()">Check IP</button>
        </div>
        <div id="ipResult" class="result"></div>
    </div>

    <div class="card">
        <h2>Secure Encryption / Decryption</h2>
        <p class="dim">Data is encrypted using a local key file (<code>secret.key</code>). Only this server/worker can decrypt.</p>
        <textarea id="cryptoInput" rows="3" placeholder="Enter text (password, email, etc)"></textarea>
        <div style="display: flex; gap: 10px;">
            <button onclick="doCrypto('encrypt')">Encrypt</button>
            <button onclick="doCrypto('decrypt')" style="background:#7f8c8d;">Decrypt</button>
        </div>
        <div id="cryptoResult" class="result"></div>
    </div>

    <div class="card">
        <h2>Email Masking</h2>
        <p class="dim">Validates format and masks sensitive parts.</p>
        <div class="input-group">
            <input type="text" id="emailInput" placeholder="user@example.com">
            <button onclick="maskEmail()">Mask</button>
        </div>
        <div id="emailResult" class="result"></div>
    </div>

    <script>
        async function lookupIP() {
            const ip = document.getElementById('ipInput').value;
            const resDiv = document.getElementById('ipResult');
            resDiv.style.display = 'block';
            resDiv.textContent = 'Checking...';
            
            try {
                const req = await fetch('/api/ip', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({ip})
                });
                const data = await req.json();
                if (data.error) {
                    resDiv.innerHTML = `<span class="error">${data.error}</span>`;
                } else {
                    let html = `<span class="success">Valid ${data.public ? 'Public' : 'Private'} IP (v${data.version})</span>\n`;
                    if (data.metadata) {
                        html += `\nISP: ${data.metadata.isp}\nOrg: ${data.metadata.org}\nAS:  ${data.metadata.as}`;
                    } else if (data.metadata_error) {
                         html += `\nMetadata Error: ${data.metadata_error}`;
                    }
                    resDiv.innerHTML = html;
                }
            } catch (e) { resDiv.textContent = "Error: " + e; }
        }

        async function doCrypto(action) {
            const text = document.getElementById('cryptoInput').value;
            const resDiv = document.getElementById('cryptoResult');
            resDiv.style.display = 'block';
            
            try {
                const req = await fetch('/api/crypto', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({text, action})
                });
                const data = await req.json();
                if (data.error) resDiv.innerHTML = `<span class="error">${data.error}</span>`;
                else resDiv.textContent = data.result;
            } catch (e) { resDiv.textContent = "Error: " + e; }
        }

        async function maskEmail() {
            const email = document.getElementById('emailInput').value;
            const resDiv = document.getElementById('emailResult');
            resDiv.style.display = 'block';
            
            try {
                const req = await fetch('/api/mask', {
                    method: 'POST', headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({email})
                });
                const data = await req.json();
                if (data.error) resDiv.innerHTML = `<span class="error">${data.error}</span>`;
                else resDiv.textContent = data.masked;
            } catch (e) { resDiv.textContent = "Error: " + e; }
        }
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/ip', methods=['POST'])
def api_ip():
    data = request.json
    ip_str = data.get('ip', '').strip()
    check = check_ip(ip_str)
    
    if not check['valid']:
        return jsonify({"error": check['error']})
    
    response = check
    if check['public']:
        meta = get_metadata(ip_str)
        if meta.get('status') == 'success':
            response['metadata'] = meta
        else:
            response['metadata_error'] = meta.get('message')
            
    return jsonify(response)

@app.route('/api/crypto', methods=['POST'])
def api_crypto():
    data = request.json
    text = data.get('text', '')
    action = data.get('action', 'encrypt')
    
    if not text:
        return jsonify({"error": "Empty input"})
    
    if fernet is None:
         return jsonify({"error": "Encryption system not initialized"})

    try:
        if action == 'encrypt':
            res = fernet.encrypt(text.encode()).decode()
            return jsonify({"result": res})
        else:
            res = fernet.decrypt(text.encode()).decode()
            return jsonify({"result": res})
    except Exception as e:
        return jsonify({"error": "Operation failed (Invalid key or token)"})

@app.route('/api/mask', methods=['POST'])
def api_mask():
    data = request.json
    res = mask_email_logic(data.get('email', ''))
    if res['valid']:
        return jsonify(res)
    return jsonify({"error": res['error']})

if __name__ == "__main__":
    # Host on 0.0.0.0 to be accessible via IP (A Record)
    host = os.environ.get('HOST', '0.0.0.0')
    port = int(os.environ.get('PORT', 5000))
    print(f"Starting server on {host}:{port}")
    app.run(host=host, port=port)
