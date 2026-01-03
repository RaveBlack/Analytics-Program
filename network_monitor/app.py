import eventlet
eventlet.monkey_patch()

from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from scapy.all import sniff, IP, TCP, UDP, Raw, conf
import threading
import time
import json
import base64
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TrafficMonitor")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins="*")

# Global control variables
sniffing = True
# Simple string filter for IP presence (source or dest)
target_ip_filter = "" 

def packet_callback(packet):
    global target_ip_filter, sniffing
    
    if not sniffing:
        return

    if IP in packet:
        src_ip = packet[IP].src
        dst_ip = packet[IP].dst
        
        # Filter logic: if filter is set, one of the IPs must match
        if target_ip_filter and (target_ip_filter != src_ip and target_ip_filter != dst_ip):
            return

        proto_num = packet[IP].proto
        protocol = "OTHER"
        if proto_num == 6:
            protocol = "TCP"
        elif proto_num == 17:
            protocol = "UDP"
        elif proto_num == 1:
            protocol = "ICMP"

        payload = ""
        payload_text = "[No L7 payload]"
        is_plain_text = False
        raw_bytes = b""
        
        # Extract L7 payload
        if Raw in packet:
            raw_bytes = packet[Raw].load
            try:
                # Try to decode as UTF-8 for "plain text"
                payload = raw_bytes.decode('utf-8')
                is_plain_text = True
            except UnicodeDecodeError:
                # If binary, we encode it as base64 so it can be sent to JSON
                # The frontend can then decide to show it as Hex or try other decodings
                payload = base64.b64encode(raw_bytes).decode('utf-8')
                is_plain_text = False
            # Always provide a best-effort plain text view
            payload_text = raw_bytes.decode("utf-8", errors="replace")
        
        pkt_data = {
            'timestamp': time.strftime('%H:%M:%S', time.localtime()),
            'src': src_ip,
            'dst': dst_ip,
            'protocol': protocol,
            'length': len(packet),
            'payload': payload,
            'payload_text': payload_text,
            'is_plain_text': is_plain_text,
            'summary': packet.summary()
        }
        
        socketio.emit('new_packet', pkt_data)
        eventlet.sleep(0) # Yield to eventlet loop

def start_sniffing():
    logger.info("Starting packet sniffer...")
    # store=0 prevents memory buildup
    # filter="ip" ensures we only look at IP packets (IPv4)
    sniff(prn=packet_callback, filter="ip", store=0)

# Start sniffer in a separate thread
# Note: In a production environment with eventlet, we prefer eventlet.spawn
sniffer_thread = eventlet.spawn(start_sniffing)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def test_connect():
    emit('status', {'msg': 'Connected to Traffic Monitor'})

@socketio.on('set_filter')
def handle_filter(data):
    global target_ip_filter
    target_ip_filter = data.get('ip', '').strip()
    emit('status', {'msg': f'Filter set to: {target_ip_filter if target_ip_filter else "None"}'})

@socketio.on('toggle_sniffing')
def handle_toggle(data):
    global sniffing
    sniffing = data.get('state', True)
    status = "Resumed" if sniffing else "Paused"
    emit('status', {'msg': f'Sniffing {status}'})

if __name__ == '__main__':
    # We must run with sudo for scapy to sniff on Linux
    print("Starting Web Server on http://0.0.0.0:5000")
    print("NOTE: You must run this script with sudo privileges to capture packets.")
    socketio.run(app, host='0.0.0.0', port=5000)
