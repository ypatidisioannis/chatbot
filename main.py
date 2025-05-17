{\rtf1\ansi\ansicpg1252\cocoartf2759
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fswiss\fcharset0 Helvetica;}
{\colortbl;\red255\green255\blue255;}
{\*\expandedcolortbl;;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\pard\tx720\tx1440\tx2160\tx2880\tx3600\tx4320\tx5040\tx5760\tx6480\tx7200\tx7920\tx8640\pardirnatural\partightenfactor0

\f0\fs24 \cf0 from fastapi import FastAPI, Request\
import openai\
import os\
\
openai.api_key = os.getenv("OPENAI_API_KEY")\
\
app = FastAPI()\
\
@app.post("/chat")\
async def chat(request: Request):\
    data = await request.json()\
    user_message = data.get("message")\
\
    response = openai.ChatCompletion.create(\
        model="gpt-3.5-turbo",\
        messages=[\
            \{"role": "system", "content": "You are a helpful support assistant for a business website."\},\
            \{"role": "user", "content": user_message\}\
        ]\
    )\
    return \{"response": response.choices[0].message["content"]\}\
}