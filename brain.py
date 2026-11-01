"""Cérebro da Faby: monta o contexto, chama o modelo e valida a resposta."""
import base64
import json
import os
import re

from google import genai
from google.genai import types

import memory
from personality import ACTIONS_ANDROID, ACTIONS_IOS, build_system_prompt

# "gemini-flash-latest" aponta sempre para o Flash mais novo. Troque em FABY_MODEL se quiser fixar um modelo.
MODEL = os.getenv("FABY_MODEL", "gemini-flash-latest")
WEB_SEARCH = os.getenv("FABY_WEB_SEARCH", "1") == "1"

_client = None


def _get_client():
    """Cria o cliente do Gemini só quando precisa, lendo a chave do ambiente."""
    global _client
    if _client is None:
        key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not key:
            raise RuntimeError("Falta a variável GEMINI_API_KEY no servidor.")
        _client = genai.Client(api_key=key)
    return _client


# emoção da voz da Faby (tom com que ela fala)
EMOTIONS = {"feliz", "triste", "neutro", "calmo", "animado", "empatico", "preocupado", "firme"}


def _parse(raw: str) -> dict:
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
    return {"reply": raw[:300] or "Desculpe, me perdi um instante.", "emotion": "neutro", "action": None}


def _clean_history(history: list[dict]) -> list[dict]:
    """A API exige que a conversa comece com uma mensagem do usuário."""
    while history and history[0]["role"] != "user":
        history = history[1:]
    return history


def _contents(messages: list[dict]) -> list:
    """Converte a conversa para o formato do Gemini (o papel do modelo se chama 'model')."""
    out = []
    for m in messages:
        role = "user" if m["role"] == "user" else "model"
        out.append(types.Content(role=role, parts=[types.Part(text=m["content"])]))
    return out


def _complete(system: str, messages: list[dict], search: bool) -> dict:
    client = _get_client()
    contents = _contents(messages)

    def run(tools):
        cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=2048, tools=tools)
        return client.models.generate_content(model=MODEL, contents=contents, config=cfg)

    tools = [types.Tool(google_search=types.GoogleSearch())] if (search and WEB_SEARCH) else None
    try:
        resp = run(tools)
    except Exception:
        if not tools:
            raise
        resp = run(None)  # pesquisa na web indisponível: responde sem ela
    return _parse(resp.text or "")


def _finalize(data: dict, platform: str) -> dict:
    allowed = ACTIONS_IOS if platform == "ios" else ACTIONS_ANDROID
    action = data.get("action")
    if not isinstance(action, dict) or action.get("type") not in allowed:
        action = None
    emotion = data.get("emotion") if data.get("emotion") in EMOTIONS else "neutro"
    reply = str(data.get("reply", "")).strip() or "Estou aqui."
    return {"reply": reply, "emotion": emotion, "action": action}


def think(user_id: str, text: str, emotion: str, platform: str,
          intensity: float = 0.5, signals: dict | None = None) -> dict:
    facts = memory.get_facts(user_id)
    history = _clean_history(memory.recent_messages(user_id))
    mood = memory.mood_summary(user_id)
    system = build_system_prompt(platform, emotion, facts, intensity, signals, mood)

    data = _complete(system, history + [{"role": "user", "content": text}], search=True)
    out = _finalize(data, platform)

    memory.add_message(user_id, "user", text, emotion)
    memory.add_message(user_id, "assistant", out["reply"], out["emotion"])
    memory.add_mood(user_id, emotion, intensity)
    fact = data.get("remember")
    if isinstance(fact, str) and fact.strip():
        memory.add_fact(user_id, fact)
    return out


def checkin(user_id: str, platform: str, local_time: str = "") -> dict:
    """A Faby puxa a conversa: cumprimento curto e caloroso, ciente do humor recente."""
    facts = memory.get_facts(user_id)
    mood = memory.mood_summary(user_id)
    system = build_system_prompt(platform, "neutro", facts, 0.3, None, mood)
    hora = f" Agora são {local_time}." if local_time else ""
    msg = ("[Sistema: o usuário acabou de abrir uma conversa por voz com você." + hora +
           " Cumprimente-o de forma calorosa e curta (1 a 2 frases). Se o humor recente justificar, "
           "pergunte como ele está. Não use action e não repita cumprimentos antigos.]")
    data = _complete(system, [{"role": "user", "content": msg}], search=False)
    data["action"] = None
    out = _finalize(data, platform)
    memory.add_message(user_id, "assistant", out["reply"], out["emotion"])
    return out


IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


def describe(image_b64: str, media_type: str = "image/jpeg", question: str = "") -> dict:
    """Descreve uma foto que o usuário confirmou enviar. A imagem não é guardada nem registrada."""
    if media_type not in IMAGE_TYPES:
        media_type = "image/jpeg"
    system = ("Você é a Faby, uma assistente de voz. Descreva a foto em português do Brasil, em até 3 frases "
              "faladas, sem markdown e sem listas. Se houver pessoas, descreva o que fazem e o ambiente, sem "
              "identificá-las pelo rosto nem pelo nome. Se o usuário perguntou algo específico, responda a isso.")
    ask = question.strip() or "Descreva esta foto."
    img = base64.b64decode(image_b64)
    cfg = types.GenerateContentConfig(system_instruction=system, max_output_tokens=1024)
    resp = _get_client().models.generate_content(
        model=MODEL,
        contents=[types.Part.from_bytes(data=img, mime_type=media_type), ask],
        config=cfg)
    text = (resp.text or "").strip()
    return {"reply": text or "Não consegui ver bem esta foto.", "emotion": "neutro", "action": None}
