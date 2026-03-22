const express = require('express');
const axios = require('axios');
const bodyParser = require('body-parser');
const app = express();

// --- Configuration & "Database" ---
const PORT = process.argv[2] || 3000;
const DOMAIN = process.argv[3] || `localhost:${PORT}`;

app.use(bodyParser.json());
app.use(express.static('public'));

let messages = []; // Local message store
let sentValidations = new Map(); // Stores outgoing messages for validation checks

// --- Helpers ---
const getUrlFromReceiver = (receiver) => receiver.split('@')[1];

// --- Protocol Endpoints ---

// 1. Client Trigger: Send a message
app.post("/api/sendmessage", async (req, res) => {
    const { sender, receiver, messageText } = req.body;
    const messageId = Math.random().toString(36).substring(7);
    const validationKey = "val-" + Math.random().toString(36).substring(7);

    const message = { messageId, sender, receiver, messageText, validationKey, timestamp: Date.now() };
    
    // Store locally for validation later
    sentValidations.set(messageId, message);
    
    const targetDomain = getUrlFromReceiver(receiver);
    try {
        const response = await axios.post(`http://${targetDomain}/federation/receive/message`, message);
        res.json({ status: "Sent to " + targetDomain, remoteResponse: response.data });
    } catch (err) {
        res.status(500).json({ error: "Federation failed", details: err.message });
    }
});

// 2. Federation: Receive a message
app.post("/federation/receive/message", async (req, res) => {
    const message = req.body;
    const senderDomain = getUrlFromReceiver(message.sender);

    try {
        // Validation callback
        const valRes = await axios.get(`http://${senderDomain}/federation/validate/message`, {
            params: { messageId: message.messageId, validationKey: message.validationKey }
        });

        if (valRes.data.valid) {
            messages.push(message);
            console.log(`[${DOMAIN}] Message verified and stored from ${message.sender}`);
            res.send("Success");
        } else {
            res.status(401).send("Validation Failed");
        }
    } catch (err) {
        res.status(500).send("Validation Request Error");
    }
});

// 3. Federation: Validate a message
app.get("/federation/validate/message", (req, res) => {
    const { messageId, validationKey } = req.query;
    const original = sentValidations.get(messageId);

    if (original && original.validationKey === validationKey) {
        res.json({ valid: true });
    } else {
        res.json({ valid: false });
    }
});

// --- Web UI Endpoints ---
app.get("/api/messages", (req, res) => res.json(messages));
app.get("/", (req, res) => {
    res.send(`
        <html>
            <body style="font-family:sans-serif; padding:20px; background:#121212; color:white;">
                <h2>Node: ${DOMAIN}</h2>
                <div style="border:1px solid #444; padding:10px; margin-bottom:20px;">
                    <h3>Send Message</h3>
                    <input id="to" placeholder="receiver@localhost:3001">
                    <input id="txt" placeholder="Hello!">
                    <button onclick="send()">Send</button>
                </div>
                <h3>Inbox</h3>
                <div id="inbox"></div>
                <script>
                    const user = "user@${DOMAIN}";
                    async function send() {
                        await fetch('/api/sendmessage', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ sender: user, receiver: document.getElementById('to').value, messageText: document.getElementById('txt').value })
                        });
                        alert('Sent request processed');
                    }
                    setInterval(async () => {
                        const res = await fetch('/api/messages');
                        const data = await res.json();
                        document.getElementById('inbox').innerHTML = data.map(m => \`<div><b>\${m.sender}:</b> \${m.messageText}</div>\`).join('');
                    }, 1000);
                </script>
            </body>
        </html>
    `);
});

app.listen(PORT, () => console.log(`Server started on http://localhost:${PORT} as domain ${DOMAIN}`));
