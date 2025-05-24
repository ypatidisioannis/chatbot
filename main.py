# main.py

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import openai, os, re, sqlite3, smtplib
from datetime import datetime
from email.message import EmailMessage

# ── CONFIG ────────────────────────────────────────────────────────────────
openai.api_key  = os.getenv("OPENAI_API_KEY")
DB_PATH         = "leads.db"
SMTP_HOST       = os.getenv("SMTP_HOST")            # e.g. smtp.gmail.com
SMTP_PORT       = int(os.getenv("SMTP_PORT", 587))  # e.g. 587
SMTP_USER       = os.getenv("SMTP_USER")            # your SMTP login
SMTP_PASS       = os.getenv("SMTP_PASS")            # your SMTP password/app-password
LEAD_RECEIVER   = os.getenv("LEAD_RECEIVER")        # where to send lead emails

# ── INITIALIZE SQLITE DB ──────────────────────────────────────────────────
def init_db():
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

def save_lead_db(name: str, email: str, phone: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
      "INSERT INTO leads (name, email, phone, created_at) VALUES (?, ?, ?, ?)",
      (name, email, phone, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()

init_db()

# ── EXTRACT LEAD FROM CHAT ─────────────────────────────────────────────────
def extract_lead(messages):
    text = " ".join(m["content"] for m in messages if m["role"] == "user")
    nm = re.search(r"\bname is ([A-Z][a-z]+(?: [A-Z][a-z]+)*)", text, re.IGNORECASE)
    em = re.search(r"([\w\.-]+@[\w\.-]+)", text)
    ph = re.search(r"(?:\+?\d[\d \-]{7,}\d)", text)
    if nm and em and ph:
        return nm.group(1).strip().title(), em.group(1).strip(), ph.group(0).strip()
    return None

# ── SEND SIMPLE EMAIL FOR NEW LEAD ────────────────────────────────────────
def email_lead_simple(name: str, email: str, phone: str):
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

    try:
        print(f"📧 Connecting to SMTP {SMTP_HOST}:{SMTP_PORT} as {SMTP_USER}")
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.starttls()
            print("🔐 Starting TLS")
            smtp.login(SMTP_USER, SMTP_PASS)
            print("✅ Logged in successfully")
            smtp.send_message(msg)
            print(f"✅ Lead email sent for {name} to {LEAD_RECEIVER}")
    except Exception as e:
        # Log the full stack trace and re-raise so Render surfaces it in the logs
        import traceback
        traceback.print_exc()
        print(f"❌ Failed to send lead email for {name}: {e}")
        raise


# ── FASTAPI SETUP ─────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── CHAT ENDPOINT ─────────────────────────────────────────────────────────
@app.post("/chat")
async def chat(request: Request):
    payload  = await request.json()
    messages = payload.get("messages", [])

    # 1) Detect + save + email any new lead
    lead = extract_lead(messages)
    if lead:
        name, email, phone = lead
        save_lead_db(name, email, phone)
        try:
            email_lead_simple(name, email, phone)
        except Exception as e:
            print("Failed to email lead:", e)

    # 2) Forward conversation to OpenAI
    client   = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        max_tokens=150,
        temperature=0.6,
    )

    return {"response": response.choices[0].message.content}
