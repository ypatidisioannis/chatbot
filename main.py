import os
import json
import re                   # NEW: for manual regex extraction
import sqlite3
import smtplib
import ssl
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from email.message import EmailMessage
import openai

# ── CONFIG ────────────────────────────────────────────────────────────────
openai.api_key  = os.getenv("OPENAI_API_KEY")
DB_PATH         = "leads.db"
SMTP_HOST       = os.getenv("SMTP_HOST")
SMTP_PORT       = int(os.getenv("SMTP_PORT", 587))
SMTP_USER       = os.getenv("SMTP_USER")
SMTP_PASS       = os.getenv("SMTP_PASS")
LEAD_RECEIVER   = os.getenv("LEAD_RECEIVER")

# ── INIT DB ────────────────────────────────────────────────────────────────
def init_db():
    """Create the leads table if it doesn't exist."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
      CREATE TABLE IF NOT EXISTS leads (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        name        TEXT NOT NULL,
        email       TEXT NOT NULL,
        phone       TEXT NOT NULL,
        created_at  TEXT NOT NULL
      )
    """)
    conn.commit()
    conn.close()

def save_lead_db(name, email, phone):
    """Append a new lead row into the SQLite database."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO leads (name, email, phone, created_at) VALUES (?,?,?,?)",
        (name, email, phone, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

init_db()

# ── MANUAL MULTI-MESSAGE LEAD EXTRACTOR ────────────────────────────────────
# Regex patterns to find email, phone, and name anywhere in the concatenated text.
EMAIL_RE           = re.compile(r"\b[\w\.-]+@[\w\.-]+\.\w+\b")
PHONE_RE           = re.compile(r"(?:\+?\d[\d\-\s\(\)]{7,}\d)")
NAME_RE_PHRASE     = re.compile(r"\b(?:my name is|i am|i'm|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                                 re.IGNORECASE)
NAME_RE_FALLBACK   = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)")

def manual_extract_lead(messages):
    """
    Scan ALL user messages together for name, email, and phone.
    Returns a tuple (name, email, phone) if all are found, else None.
    """
    # Concatenate every user‐role message
    text = " ".join(m["content"] for m in messages if m["role"] == "user")

    # 1) Find email and phone
    email_match = EMAIL_RE.search(text)
    phone_match = PHONE_RE.search(text)

    # 2) Attempt explicit name phrases, otherwise fallback
    name_match = NAME_RE_PHRASE.search(text)
    if name_match:
        name = name_match.group(1).title()
    else:
        fb = NAME_RE_FALLBACK.search(text)
        name = fb.group(1).title() if fb else None

    # Only return if all three pieces are present
    if name and email_match and phone_match:
        return name, email_match.group(0), phone_match.group(0)
    return None

# ── EMAIL HELPER ──────────────────────────────────────────────────────────
def email_lead_simple(name: str, email: str, phone: str):
    """
    Send a simple plain-text email notification whenever a new lead is captured.
    Uses STARTTLS on SMTP_PORT (usually 587).
    """
    msg = EmailMessage()
    msg["Subject"] = f"New Lead: {name}"
    msg["From"]    = SMTP_USER
    msg["To"]      = LEAD_RECEIVER
    msg.set_content(
        f"🎉 You’ve got a new lead!\n\n"
        f"Name : {name}\n"
        f"Email: {email}\n"
        f"Phone: {phone}\n"
        f"Captured at: {datetime.utcnow().isoformat()}\n"
    )

    # Establish a STARTTLS connection
    context = ssl.create_default_context()
    print(f"📧 Connecting to {SMTP_HOST}:{SMTP_PORT} with STARTTLS")
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
        smtp.ehlo()
        smtp.starttls(context=context)
        smtp.ehlo()
        smtp.login(SMTP_USER, SMTP_PASS)
        smtp.send_message(msg)
        print(f"✅ Lead email sent for {name}")

# ── FASTAPI SETUP ─────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ── FUNCTION SPEC ─────────────────────────────────────────────────────────
lead_extractor_fn = {
    "name": "extract_lead",
    "description": "Extract name, email and phone number from the user's message",
    "parameters": {
        "type": "object",
        "properties": {
            "name":  {"type": "string", "description": "Full name"},
            "email": {"type": "string", "description": "Email address"},
            "phone": {"type": "string", "description": "Phone number"}
        },
        "required": ["name", "email", "phone"]
    }
}

# ── /chat ENDPOINT WITH HYBRID EXTRACTION ──────────────────────────────────
@app.post("/chat")
async def chat(request: Request):
    payload  = await request.json()
    messages = payload.get("messages", [])

    # ── 1) MANUAL EXTRACTION ACROSS MESSAGES ─────────────────────────────
    lead = manual_extract_lead(messages)
    if lead:
        name, email, phone = lead

        # Avoid duplicate inserts (optional)
        conn = sqlite3.connect(DB_PATH)
        exists = conn.execute(
            "SELECT 1 FROM leads WHERE name=? AND email=? AND phone=?",
            (name, email, phone)
        ).fetchone()
        conn.close()

        if not exists:
            save_lead_db(name, email, phone)
            email_lead_simple(name, email, phone)

    # ── 2) LET THE MODEL DO ITS THING (FUNCTION CALLING) ────────────────
    client   = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        functions=[lead_extractor_fn],
        function_call="auto"
    )
    msg = response.choices[0].message

    # ── 3) HANDLE MODEL-TRIGGERED EXTRACTION ─────────────────────────────
    if msg.function_call and msg.function_call.name == "extract_lead":
        args = json.loads(msg.function_call.arguments)
        # extract fields
        fn_name, fn_email, fn_phone = args["name"], args["email"], args["phone"]

        save_lead_db(fn_name, fn_email, fn_phone)
        email_lead_simple(fn_name, fn_email, fn_phone)

        # feed the function result back into the convo
        messages.append(msg)
        messages.append({
            "role": "function",
            "name": msg.function_call.name,
            "content": json.dumps(args)
        })

        # get AI acknowledgment
        followup = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        return {"response": followup.choices[0].message.content}

    # ── 4) NORMAL AI RESPONSE ─────────────────────────────────────────────
    return {"response": msg.content}
