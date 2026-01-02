from flask import Flask, render_template
from flask_socketio import SocketIO, emit
from scapy.all import sniff, IP, TCP, UDP, ICMP, Raw
import threading
import time
import base64
import logging
import eventlet

# Monkey patch for eventlet - important for Flask-SocketIO
eventlet.monkey_patch()

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("TrafficMonitor")

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
# Allow connections from any origin
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet')

# Global Variables
sniffing = True
target_ip_filter = "" 

def decode_payload(raw_bytes):
    """
    Attempt to decode bytes into a readable string.
    Tries UTF-8, then Latin-1. Returns (decoded_string, is_plain_text_bool).
    """
    try:
        return raw_bytes.decode('utf-8'), True
    except UnicodeDecodeError:
        try:
            return raw_bytes.decode('latin-1'), True
        except:
            # If all text decoding fails, return Base64
            return base64.b64encode(raw_bytes).decode('utf-8'), False

def packet_callback(packet):
    global target_ip_filter, sniffing
    
    if not sniffing:
        return

    try:
        if IP in packet:
            src_ip = packet[IP].src
            dst_ip = packet[IP].dst
            
            # Filter Logic
            if target_ip_filter and (target_ip_filter not in [src_ip, dst_ip]):
                return

            # Protocol Identification
            if TCP in packet:
                protocol = "TCP"
            elif UDP in packet:
                protocol = "UDP"
            elif ICMP in packet:
                protocol = "ICMP"
            else:
                protocol = "OTHER"

            # Payload Extraction
            payload = ""
            is_plain_text = False
            raw_bytes = b""
            
            if Raw in packet:
                raw_bytes = packet[Raw].load
            elif ICMP in packet:
                # ICMP might have payload in Raw or just be a header
                if Raw in packet:
                    raw_bytes = packet[Raw].load
                else:
                    raw_bytes = bytes(packet[ICMP].payload)

            if raw_bytes:
                payload, is_plain_text = decode_payload(raw_bytes)
            
            # Data to send to frontend
            pkt_data = {
                'id': int(time.time() * 100000), 
                'timestamp': time.strftime('%H:%M:%S', time.localtime()),
                'src': src_ip,
                'dst': dst_ip,
                'protocol': protocol,
                'length': len(packet),
                'payload': payload,
                'is_plain_text': is_plain_text,
                'summary': str(packet.summary())
            }
            
            socketio.emit('new_packet', pkt_data)
            
    except Exception as e:
        logger.error(f"Error processing packet: {e}")

def start_sniffing():
    logger.info("Starting Sniffer...")
    # store=0 prevents memory buildup
    try:
        sniff(prn=packet_callback, filter="ip", store=0)
    except Exception as e:
        logger.error(f"Sniffer failed: {e}")

# Start Sniffer in Background Thread
# We use a standard thread here to avoid blocking the eventlet loop
t = threading.Thread(target=start_sniffing)
t.daemon = True
t.start()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    emit('status', {'msg': 'Connected to Traffic Monitor Server'})

@socketio.on('set_filter')
def handle_filter(data):
    global target_ip_filter
    target_ip_filter = data.get('ip', '').strip()
    emit('status', {'msg': f'Filter: {target_ip_filter if target_ip_filter else "None"}'})

@socketio.on('toggle_sniffing')
def handle_toggle(data):
    global sniffing
    sniffing = data.get('state', True)
    state_str = "Resumed" if sniffing else "Paused"
    emit('status', {'msg': f'Sniffing {state_str}'})

if __name__ == '__main__':
    print("--------------------------------------------------")
    print(" Traffic Monitor running at: http://0.0.0.0:5000")
    print(" Access via localhost or your network IP.")
    print("--------------------------------------------------")
    socketio.run(app, host='0.0.0.0', port=5000)
