import sys, uuid, requests, os
from flask import Flask, request, jsonify, render_template_string, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from dotenv import load_dotenv

# Pak het .env bestand uit het eerste argument (bijv: python app.py NodeA.env)
env_file = sys.argv[1] if len(sys.argv) > 1 else ".env"
load_dotenv(env_file)

app = Flask(__name__)

# Configuratie via omgevingsvariabelen (met defaults)
app.secret_key = os.getenv("SECRET_KEY", "default_secret_key")
PORT = int(os.getenv("PORT", 5000))
DOMAIN = os.getenv("DOMAIN", f"localhost:{PORT}")
DB_NAME = os.getenv("DB_NAME", f"database_{PORT}.db")

# Database Setup - Gebruik een absoluut pad naar de huidige map
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{os.path.join(basedir, DB_NAME)}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

class Message(db.Model):
    id = db.Column(db.String(36), primary_key=True) # UUID as ID
    sender = db.Column(db.String(100))
    receiver = db.Column(db.String(100))
    text = db.Column(db.Text)
    validation_key = db.Column(db.String(50))
    is_received = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# --- Protocol Logic ---

@app.route("/api/sendmessage", methods=["POST"])
def send_message():
    if 'username' not in session: return "Unauthorized", 401
    
    data = request.json
    msg_id = str(uuid.uuid4())
    val_key = "key-" + str(uuid.uuid4())[:8]

    # Store locally for validation
    new_msg = Message(id=msg_id, sender=session['username'], receiver=data['receiver'], 
                      text=data['messageText'], validation_key=val_key, is_received=False)
    db.session.add(new_msg)
    db.session.commit()
    
    target_domain = data['receiver'].split('@')[-1]
    payload = {"id": msg_id, "sender": session['username'], "receiver": data['receiver'], 
               "text": data['messageText'], "validationKey": val_key}
    
    try:
        requests.post(f"http://{target_domain}/federation/receive/message", json=payload, timeout=5)
        return jsonify({"status": "Sent", "message_url": f"/message/{msg_id}"})
    except:
        return jsonify({"error": "Federation failed"}), 500

@app.route("/federation/receive/message", methods=["POST"])
def receive_message():
    data = request.json
    sender_domain = data['sender'].split('@')[-1]

    # Validate back with sender
    val_params = {"messageId": data['id'], "validationKey": data['validationKey']}
    val_resp = requests.get(f"http://{sender_domain}/federation/validate/message", params=val_params)
    
    if val_resp.json().get("valid"):
        # Save received message to DB
        received = Message(id=data['id'], sender=data['sender'], receiver=data['receiver'], 
                           text=data['text'], is_received=True)
        db.session.add(received)
        db.session.commit()
        return "OK", 200
    return "Invalid", 401

@app.route("/federation/validate/message")
def validate_message():
    msg = Message.query.filter_by(id=request.args.get("messageId")).first()
    if msg and msg.validation_key == request.args.get("validationKey"):
        return jsonify({"valid": True})
    return jsonify({"valid": False})

# --- Web UI & Viewers ---

@app.route("/message/<msg_id>")
def view_message(msg_id):
    msg = Message.query.get_or_404(msg_id)
    return f"<h3>Message {msg_id}</h3><p>From: {msg.sender}</p><p>Text: {msg.text}</p><a href='/'>Back</a>"

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        session['username'] = f"{request.form['user']}@{DOMAIN}"
        return redirect(url_for('index'))
    return '<form method="post">User: <input name="user"><button>Login</button></form>'

@app.route("/")
def index():
    if 'username' not in session: return redirect(url_for('login'))
    msgs = Message.query.filter_by(is_received=True).order_by(Message.timestamp.desc()).all()
    return render_template_string('''
        <body style="font-family:sans-serif; background:#121212; color:white; padding:20px;">
            <h2>Logged in as: {{ user }}</h2>
            <div style="background:#222; padding:15px; border-radius:5px;">
                <input id="to" placeholder="iris@localhost:5001">
                <input id="txt" placeholder="Message">
                <button onclick="send()">Send</button>
            </div>
            <h3>Received Messages</h3>
            {% for m in msgs %}
                <div style="border-bottom:1px solid #333; padding:10px;">
                    <a href="/message/{{ m.id }}" style="color:#0af;">View ID</a> | 
                    <b>{{ m.sender }}:</b> {{ m.text }}
                </div>
            {% endfor %}
            <script>
                async function send() {
                    const res = await fetch('/api/sendmessage', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({receiver: document.getElementById('to').value, messageText: document.getElementById('txt').value})
                    });
                    const data = await res.json();
                    if(data.message_url) window.location.reload();
                }
            </script>
        </body>
    ''', user=session['username'], msgs=msgs)

if __name__ == "__main__":
    app.run(port=PORT)
