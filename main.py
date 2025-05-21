from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

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
    messages = data.get("messages")  # full chat history

    client = openai.OpenAI()
    chat_response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=messages
    )

    return {"response": chat_response.choices[0].message.content}
