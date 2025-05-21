from fastapi import FastAPI, Request
import openai
import os

openai.api_key = os.getenv("OPENAI_API_KEY")

app = FastAPI()

@app.post("/chat")
async def chat(request: Request):
    data = await request.json()
    user_message = data.get("message")

    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful assistant for a business website."},
            {"role": "user", "content": user_message}
        ]
    )
    return {"response": response.choices[0].message["content"]}