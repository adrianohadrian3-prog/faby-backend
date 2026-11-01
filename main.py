import os

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel

load_dotenv()

import brain  # noqa: E402  (depois do load_dotenv)
import memory  # noqa: E402

memory.init()
app = FastAPI(title="Faby Backend")
APP_KEY = os.getenv("FABY_APP_KEY", "")


class ChatIn(BaseModel):
    text: str
    emotion: str = "neutro"
    platform: str = "android"   # android | ios
    user_id: str = "default"
    intensity: float = 0.5      # 0 a 1, intensidade da emoção do usuário
    signals: dict = {}          # ex.: {"texto": "triste", "voz": "cansado", "rosto": "neutro"}


class CheckinIn(BaseModel):
    platform: str = "android"
    user_id: str = "default"
    local_time: str = ""        # "HH:mm" do aparelho


class DescribeIn(BaseModel):
    image_b64: str
    media_type: str = "image/jpeg"
    question: str = ""


def _auth(key: str | None):
    if APP_KEY and key != APP_KEY:
        raise HTTPException(status_code=401, detail="chave inválida")


@app.post("/chat")
def chat(body: ChatIn, x_faby_key: str | None = Header(default=None)):
    _auth(x_faby_key)
    platform = "ios" if body.platform.lower() == "ios" else "android"
    try:
        return brain.think(body.user_id, body.text.strip(), body.emotion, platform,
                           body.intensity, body.signals)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"erro no modelo: {e}")


@app.post("/checkin")
def checkin(body: CheckinIn, x_faby_key: str | None = Header(default=None)):
    """A Faby inicia a conversa (cumprimento + como você está)."""
    _auth(x_faby_key)
    platform = "ios" if body.platform.lower() == "ios" else "android"
    try:
        return brain.checkin(body.user_id, platform, body.local_time)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"erro no modelo: {e}")


@app.post("/describe")
def describe(body: DescribeIn, x_faby_key: str | None = Header(default=None)):
    """Descreve uma foto. O app só chama isto depois de o usuário confirmar por voz."""
    _auth(x_faby_key)
    if len(body.image_b64) > 6_000_000:
        raise HTTPException(status_code=413, detail="imagem grande demais")
    try:
        return brain.describe(body.image_b64, body.media_type, body.question)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"erro no modelo: {e}")


@app.get("/mood/{user_id}")
def mood(user_id: str, x_faby_key: str | None = Header(default=None)):
    _auth(x_faby_key)
    return {"summary": memory.mood_summary(user_id)}


@app.get("/memory/{user_id}")
def get_memory(user_id: str, x_faby_key: str | None = Header(default=None)):
    _auth(x_faby_key)
    return {"facts": memory.get_facts(user_id)}


@app.delete("/memory/{user_id}")
def forget(user_id: str, x_faby_key: str | None = Header(default=None)):
    _auth(x_faby_key)
    memory.forget_all(user_id)
    return {"ok": True}


@app.get("/health")
def health():
    return {"status": "ok"}
