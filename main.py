import os, json, sqlite3, smtplib
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from email.message import EmailMessage
import openai
import ssl


# ── CONFIG ────────────────────────────────────────────────────────────────
openai.api_key = os.getenv("OPENAI_API_KEY")
DB_PATH       = "leads.db"
SMTP_HOST     = os.getenv("SMTP_HOST")
SMTP_PORT     = int(os.getenv("SMTP_PORT", 587))
SMTP_USER     = os.getenv("SMTP_USER")
SMTP_PASS     = os.getenv("SMTP_PASS")
LEAD_RECEIVER = os.getenv("LEAD_RECEIVER")

# ── INIT DB (your existing code) ──────────────────────────────────────────
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
    conn.commit(); conn.close()

def save_lead_db(name, email, phone):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT INTO leads (name,email,phone,created_at) VALUES (?,?,?,?)",
        (name, email, phone, datetime.utcnow().isoformat())
    )
    conn.commit(); conn.close()

init_db()

# ── EMAIL HELPER (your existing code) ────────────────────────────────────


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
app.add_middleware(CORSMiddleware,
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
            "name":  {"type": "string", "description": "The person's full name"},
            "email": {"type": "string", "description": "The person's email address"},
            "phone": {"type": "string", "description": "The person's phone number"}
        },
        "required": ["name", "email", "phone"]
    }
}

# ── /chat ENDPOINT WITH FUNCTION CALLING ───────────────────────────────────
@app.post("/chat")
async def chat(request: Request):
    payload  = await request.json()
    messages = payload.get("messages", [])

    # 1) Let the model try to extract a lead via function call
    client = openai.OpenAI()
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages,
        functions=[lead_extractor_fn],
        function_call="auto"
    )
    msg = response.choices[0].message

    # 2) If the model called our function, handle it
    if msg.function_call and msg.function_call.name == "extract_lead":
        args = json.loads(msg.function_call.arguments)
        name, email, phone = args["name"], args["email"], args["phone"]

        # persist & email
        save_lead_db(name, email, phone)
        email_lead_simple(name, email, phone)

        # append the function result to the conversation
        messages.append(msg)
        messages.append({
            "role": "function",
            "name": msg.function_call.name,
            "content": json.dumps(args)
        })

        # 3) Ask the model to acknowledge receipt
        followup = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages
        )
        return {"response": followup.choices[0].message.content}

    # 4) Otherwise just return the normal chat response
    return {"response": msg.content}
