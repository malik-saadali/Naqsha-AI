"""One switch for every AI call: Groq (hosted open-weight) or Ollama (local, offline).

Both expose an OpenAI-compatible API, so the same code talks to either.
"""
import asyncio
import base64
import json
import re
import tempfile

import httpx

from . import config

STATE = {"provider": config.LLM_PROVIDER}
_THINK = re.compile(r"<think>.*?</think>", re.S)
_whisper_model = None


def provider() -> str:
    return STATE["provider"]


def set_provider(name: str) -> str:
    if name not in ("groq", "ollama"):
        raise ValueError("provider must be 'groq' or 'ollama'")
    STATE["provider"] = name
    return name


def models() -> dict:
    c = _cfg()
    return {"provider": provider(), "text": c["text"], "vision": c["vision"],
            "speech": config.GROQ_WHISPER_MODEL if provider() == "groq" else f"faster-whisper-{config.LOCAL_WHISPER_SIZE}"}


def _cfg() -> dict:
    if provider() == "groq":
        return {"base": "https://api.groq.com/openai/v1",
                "headers": {"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                "text": config.GROQ_TEXT_MODEL, "vision": config.GROQ_VISION_MODEL}
    return {"base": config.OLLAMA_URL.rstrip("/") + "/v1", "headers": {},
            "text": config.OLLAMA_TEXT_MODEL, "vision": config.OLLAMA_VISION_MODEL}


async def chat(messages, json_mode=False, vision=False, temperature=0.2, max_tokens=1500) -> str:
    c = _cfg()
    body = {"model": c["vision"] if vision else c["text"], "messages": messages,
            "temperature": temperature, "max_tokens": max_tokens}
    if "gpt-oss" in body["model"]:
        body["reasoning_effort"] = "low"  # hidden reasoning tokens count against max_tokens
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=180) as cl:
        r = await cl.post(c["base"] + "/chat/completions", json=body, headers=c["headers"])
        if r.status_code >= 400 and json_mode:
            body.pop("response_format", None)  # some models reject JSON mode; fall back to plain
            r = await cl.post(c["base"] + "/chat/completions", json=body, headers=c["headers"])
        if r.status_code >= 400:
            raise RuntimeError(_explain(r))
    text = r.json()["choices"][0]["message"].get("content") or ""
    return _THINK.sub("", text).strip()


def _explain(r: httpx.Response) -> str:
    """Turn the common Groq failures into an instruction the user can act on."""
    if r.status_code == 403 and "Access denied" in r.text:
        return ("Groq refused this connection (Access denied). This happens on a VPN: "
                "turn the VPN off while using the dashboard, then try again.")
    if r.status_code == 401:
        return "Groq API key is missing or wrong. Put a valid GROQ_API_KEY in .env and restart."
    if r.status_code == 404 and "model" in r.text:
        return f"Groq no longer offers this model. Set a current model in .env (console.groq.com/docs/models). {r.text[:200]}"
    if r.status_code == 429:
        return "Groq rate limit reached (free tier). Wait a minute and try again."
    return f"LLM error {r.status_code}: {r.text[:300]}"


def parse_json(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text).rstrip("`").strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        return json.loads(m.group(0))
    raise ValueError("Model did not return JSON: " + text[:200])


async def chat_json(system: str, user: str, image: bytes | None = None, mime: str = "image/jpeg") -> dict:
    """Ask for a JSON object. With an image, the vision model is used."""
    if image is not None:
        b64 = base64.b64encode(image).decode()
        content = [{"type": "text", "text": system + "\n\n" + user},
                   {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}]
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    last_err = None
    for _ in range(2):
        txt = await chat(messages, json_mode=True, vision=image is not None)
        try:
            return parse_json(txt)
        except Exception as e:  # ask once more, strictly
            last_err = e
            messages = messages + [{"role": "assistant", "content": txt},
                                   {"role": "user", "content": "Return ONLY one valid JSON object, nothing else."}]
    raise last_err


async def transcribe(audio: bytes, filename: str = "voice.ogg") -> dict:
    """Speech to text with Whisper (Groq-hosted, or local faster-whisper offline)."""
    if not audio:
        return {"text": "", "language": None}
    if provider() == "groq" and config.GROQ_API_KEY:
        async with httpx.AsyncClient(timeout=120) as cl:
            r = await cl.post("https://api.groq.com/openai/v1/audio/transcriptions",
                              headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                              data={"model": config.GROQ_WHISPER_MODEL, "response_format": "verbose_json"},
                              files={"file": (filename, audio)})
        if r.status_code >= 400:
            raise RuntimeError(_explain(r).replace("LLM error", "Whisper error"))
        j = r.json()
        return {"text": j.get("text", "").strip(), "language": j.get("language")}
    return await asyncio.to_thread(_local_whisper, audio, filename)


def _local_whisper(audio: bytes, filename: str) -> dict:
    global _whisper_model
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        return {"text": "", "language": None,
                "error": "Offline speech needs: pip install faster-whisper"}
    if _whisper_model is None:
        _whisper_model = WhisperModel(config.LOCAL_WHISPER_SIZE, compute_type="int8")
    suffix = "." + filename.rsplit(".", 1)[-1] if "." in filename else ".ogg"
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(audio)
        f.flush()
        segments, info = _whisper_model.transcribe(f.name)
        text = "".join(s.text for s in segments).strip()
    return {"text": text, "language": info.language}
