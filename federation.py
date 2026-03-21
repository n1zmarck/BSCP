import sys
import uuid
import requests
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# --- Configuration & State ---
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
DOMAIN = sys.argv[2] if len(sys.argv) > 2 else f"localhost:{PORT}"

# In-memory "Database"
messages_inbox = []      # Received messages
sent_validations = {}    # Stores local messages for validation checks

def get_url_from_receiver(receiver):
    # Splits 'user@domain.com' to get 'domain.com'
    return receiver.split('@')[-1]

# --- Protocol Endpoints ---

# 1. API: Send a message (Triggered by Web UI)
@app.route("/api/sendmessage", methods=["POST"])
def send_message():
    data = request.json
    msg_id = str(uuid.uuid4())
    validation_key = "key-" + str(uuid.uuid4())[:8]

    message = {
        "messageId": msg_id,
        "sender": data['sender'],
        "receiver": data['receiver'],
        "messageText": data['messageText'],
        "validationKey": validation_key
    }

    # Store for later validation by the receiver
    sent_validations[msg_id] = message
    
    target_domain = get_url_from_receiver(data['receiver'])
    try:
        # Step 1 in diagram: POST message to receiver
        resp = requests.post(f"http://{target_domain}/federation/receive/message", json=message, timeout=5)
        return jsonify({"status": f"Sent to {target_domain}", "remote_response": resp.text})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# 2. Federation: Receive a message
@app.route("/federation/receive/message", methods=["POST"])
def receive_message():
    message = request.json
    sender_domain = get_url_from_receiver(message['sender'])

    try:
        # Step 2 in diagram: GET request back to sender to validate
        val_params = {"messageId": message['messageId'], "validationKey": message['validationKey']}
        val_resp = requests.get(f"http://{sender_domain}/federation/validate/message", params=val_params, timeout=5)
        
        if val_resp.json().get("valid"):
            messages_inbox.append(message)
            print(f"[*] {DOMAIN}: Validated & Stored message from {message['sender']}")
            return "Success", 200
        else:
            return "Validation Failed", 401
    except Exception as e:
        return f"Federation Error: {str(e)}", 500

# 3. Federation: Validate a message
@app.route("/federation/validate/message", methods=["GET"])
def validate_message():
    msg_id = request.args.get("messageId")
    val_key = request.args.get("validationKey")
    
    original = sent_validations.get(msg_id)
    if original and original['validationKey'] == val_key:
        return jsonify({"valid": True})
    return jsonify({"valid": False})

# --- Web UI ---

@app.route("/api/messages")
def get_inbox():
    return jsonify(messages_inbox)

@app.route("/")
def index():
    return render_template_string('''
        <body style="font-family:sans-serif; background:#1a1a1a; color:#eee; padding:40px;">
            <h1>Server: {{ domain }}</h1>
            <div style="background:#2a2a2a; padding:20px; border-radius:8px; margin-bottom:20px;">
                <h3>Send Federated Message</h3>
                <input id="to" placeholder="iris@localhost:5001" style="padding:5px;">
                <input id="txt" placeholder="Message content" style="padding:5px;">
                <button onclick="send()" style="padding:5px 15px; cursor:pointer;">Send</button>
            </div>
            <h3>Received Messages (Inbox)</h3>
            <div id="inbox"></div>
            <script>
                async function send() {
                    const payload = {
                        sender: "user@{{ domain }}",
                        receiver: document.getElementById('to').value,
                        messageText: document.getElementById('txt').value
                    };
                    await fetch('/api/sendmessage', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(payload)
                    });
                    alert("Handshake started...");
                }
                setInterval(async () => {
                    const res = await fetch('/api/messages');
                    const msgs = await res.json();
                    document.getElementById('inbox').innerHTML = msgs.map(m => 
                        `<div style="border-bottom:1px solid #444; padding:10px;">
                            <b>${m.sender}:</b> ${m.messageText}
                        </div>`
                    ).join('');
                }, 1500);
            </script>
        </body>
    ''', domain=DOMAIN)

if __name__ == "__main__":
    app.run(port=PORT)
