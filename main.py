from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data.get("message")

    client = openai.OpenAI(api_key=openai.api_key)
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
        {"role": "system", "content": "You are an AI assistant for a company that builds custom chatbots and voicebots for businesses. You help website visitors understand how they can use AI to automate support, sales, or general inquiries. Explain clearly, professionally, and in simple terms. If the visitor seems interested, ask if they want a free demo or to speak with a human. Avoid overly technical jargon. Always remain helpful and polite."},
        {"role": "user", "content": user_message}
    ]
    )

    return {"response": response.choices[0].message.content}

