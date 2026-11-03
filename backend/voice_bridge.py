"""Live in-call AI voice bridge: Exotel Voicebot (Voice Streaming) <-> OpenAI Realtime.

This is the real two-way audio path for Option 2. Exotel connects to this WebSocket as a
client (it is the STREAM client; we host the endpoint). Audio in both directions is raw
16-bit PCM little-endian mono, base64-encoded. We run Exotel at 24 kHz (?sample-rate=24000),
which matches OpenAI Realtime's pcm16 24 kHz — so the raw PCM passes through with no resampling.

Protocol (verified against Exotel AgentStream docs, not guessed):
  Exotel -> us:  {"event":"connected"} | {"event":"start","stream_sid":..,"start":{..,"custom_parameters":{..}}}
                 | {"event":"media","stream_sid":..,"media":{"payload":<b64 pcm16>}} | {"event":"stop"}
  us -> Exotel:  {"event":"media","stream_sid":..,"media":{"payload":<b64 pcm16>}}
                 chunks must be multiples of 320 bytes, min ~3.2 KB.

Safety: the bridge only DISCLOSES + negotiates within the frozen authority already stored on
the call. It cannot change authority and cannot place an order. Transcript lines are persisted
live so the Review Center shows the real conversation.
"""
import os
import json
import base64
import asyncio
import logging
from datetime import datetime, timezone

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from db import get_db
import ai_service

log = logging.getLogger("voice_bridge")
router = APIRouter()

OPENAI_REALTIME_URL = ("wss://api.openai.com/v1/realtime?model="
                       + os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime"))
OUT_MIN_BYTES = 3200          # ~100ms at 24kHz; Exotel min send
OUT_MULTIPLE = 320            # payloads must be multiples of 320 bytes


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _load_call(db, call_sid: str | None, to: str | None, ref: str | None):
    """Match the Exotel stream to the voice_calls record (by session_ref, call_sid, or destination)."""
    if ref:
        doc = await db.voice_calls.find_one({"session_ref": ref}, {"_id": 0})
        if doc:
            return doc
    if call_sid:
        doc = await db.voice_calls.find_one({"call_sid": call_sid}, {"_id": 0})
        if doc:
            return doc
    if to:
        norm = to[-10:]
        doc = await db.voice_calls.find_one(
            {"to": {"$regex": f"{norm}$"}, "status": {"$in": ["calling", "connected", "initiating"]}},
            {"_id": 0}, sort=[("created_at", -1)])
        if doc:
            return doc
    return None


async def _append_transcript(db, ref: str, speaker: str, text: str, confidence=None):
    if not (ref and text and text.strip()):
        return
    line = {"id": os.urandom(8).hex(), "speaker": speaker, "text": text.strip(),
            "timestamp": _now(), "confidence": confidence}
    await db.voice_calls.update_one(
        {"session_ref": ref},
        {"$push": {"transcript": line}, "$set": {"transcript_status": "AVAILABLE",
                                                 "updated_at": _now()}})


def _agent_instructions(doc: dict) -> str:
    """Build the spoken-agent brief from the frozen call config (authority is read-only)."""
    obj = doc.get("objective") or {}
    auth = doc.get("authority") or {}
    disclosure = doc.get("disclosure_script") or (
        "Hi, I'm NegoBuy's AI procurement assistant, calling on behalf of a buyer to discuss a "
        "potential purchase. Is this a good time to talk?")
    return (
        "You are NegoBuy's AI procurement assistant on a LIVE phone call. Speak naturally, calmly "
        "and briefly, like a friendly professional buyer. Do NOT claim to be a human.\n"
        f"OPEN THE CALL by saying: \"{disclosure}\"\n"
        f"Goal: negotiate {obj.get('product') or 'the purchase'} "
        f"(quantity {obj.get('quantity')}). Target price {auth.get('currency')} "
        f"{auth.get('target_price_per_unit')} per unit. You must NEVER agree above the maximum "
        f"authorized price of {auth.get('currency')} {auth.get('max_price_per_unit')} per unit.\n"
        "Ask about delivery, shipping, loading/unloading charges, taxes, warranty and payment terms "
        "where relevant. Confirm numbers back to the supplier. If the supplier asks for anything "
        "outside your limits (price above the max, different specs, unusual payment, a binding "
        "commitment, or to finalize an order), say you'll need to confirm with the buyer first — "
        "you are NOT authorized to commit or finalize. Keep turns short and let them speak.\n"
        f"Special instructions: {obj.get('special_instructions') or 'none'}."
    )


@router.websocket("/api/voice/stream")
async def exotel_stream(ws: WebSocket):
    await ws.accept()
    db = get_db()
    stream_sid = None
    ref = None
    openai_ws = None
    out_buf = bytearray()
    tasks = []

    async def close_all():
        for t in tasks:
            t.cancel()
        if openai_ws:
            try:
                await openai_ws.close()
            except Exception:
                pass

    async def flush_to_exotel(force=False):
        nonlocal out_buf
        while len(out_buf) >= OUT_MIN_BYTES or (force and out_buf):
            take = len(out_buf) - (len(out_buf) % OUT_MULTIPLE)
            if not force:
                take = min(take, 32000)
            if take <= 0:
                break
            chunk = bytes(out_buf[:take])
            del out_buf[:take]
            await ws.send_text(json.dumps({
                "event": "media", "stream_sid": stream_sid,
                "media": {"payload": base64.b64encode(chunk).decode()}}))
            if force:
                break

    async def pump_openai():
        """Read OpenAI Realtime events -> audio out to Exotel + persist transcripts."""
        nonlocal out_buf
        async for raw in openai_ws:
            evt = json.loads(raw)
            etype = evt.get("type")
            # GA event names (with beta fallbacks for safety)
            if etype in ("response.output_audio.delta", "response.audio.delta") and evt.get("delta"):
                out_buf.extend(base64.b64decode(evt["delta"]))
                await flush_to_exotel()
            elif etype in ("response.output_audio.done", "response.audio.done"):
                await flush_to_exotel(force=True)
            elif etype in ("response.output_audio_transcript.done", "response.audio_transcript.done"):
                await _append_transcript(db, ref, "AI", evt.get("transcript", ""))
            elif etype == "conversation.item.input_audio_transcription.completed":
                await _append_transcript(db, ref, "SUPPLIER", evt.get("transcript", ""))
            elif etype == "error":
                log.error("OpenAI realtime error: %s", str(evt.get("error"))[:200])

    try:
        while True:
            msg = json.loads(await ws.receive_text())
            event = msg.get("event")

            if event == "connected":
                continue

            if event == "start":
                stream_sid = msg.get("stream_sid") or (msg.get("start") or {}).get("stream_sid")
                start = msg.get("start") or {}
                params = start.get("custom_parameters") or {}
                doc = await _load_call(db, start.get("call_sid"),
                                       start.get("to") or start.get("from"),
                                       params.get("session_ref") or params.get("ref"))
                if not doc:
                    log.error("stream start: no matching voice_calls record")
                    await ws.close()
                    return
                ref = doc["session_ref"]
                await db.voice_calls.update_one(
                    {"session_ref": ref},
                    {"$set": {"status": "connected", "channel": "exotel",
                              "recording": {"state": "RECORDING_ACTIVE",
                                            "url": (doc.get("recording") or {}).get("url")}
                              if doc.get("recording_notice") else doc.get("recording"),
                              "updated_at": _now()}})
                await _append_transcript(db, ref, "SYSTEM", "Live call connected.")

                # open OpenAI Realtime (GA API — no beta header) and configure the session
                openai_ws = await websockets.connect(
                    OPENAI_REALTIME_URL,
                    additional_headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
                    max_size=None)
                await openai_ws.send(json.dumps({
                    "type": "session.update",
                    "session": {
                        "type": "realtime",
                        "model": os.environ.get("OPENAI_REALTIME_MODEL", "gpt-realtime"),
                        "instructions": _agent_instructions(doc),
                        "audio": {
                            "input": {
                                "format": {"type": "audio/pcm", "rate": 24000},
                                "turn_detection": {"type": "server_vad", "silence_duration_ms": 600},
                                "transcription": {"model": "whisper-1"},
                            },
                            "output": {
                                "format": {"type": "audio/pcm", "rate": 24000},
                                "voice": os.environ.get("OPENAI_REALTIME_VOICE", "marin"),
                            },
                        },
                    }}))
                # AI speaks first (the disclosure)
                await openai_ws.send(json.dumps({
                    "type": "response.create",
                    "response": {"instructions": "Open the call now with the disclosure line."}}))
                tasks.append(asyncio.create_task(pump_openai()))

            elif event == "media" and openai_ws:
                payload = (msg.get("media") or {}).get("payload")
                if payload:
                    await openai_ws.send(json.dumps({
                        "type": "input_audio_buffer.append", "audio": payload}))

            elif event == "stop":
                break

    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error("voice bridge error: %s", type(e).__name__)
    finally:
        if ref:
            await db.voice_calls.update_one(
                {"session_ref": ref},
                {"$set": {"status": "completed", "ended_at": _now(), "updated_at": _now()}})
            try:
                doc = await db.voice_calls.find_one({"session_ref": ref}, {"_id": 0})
                if (doc.get("transcript")):
                    analysis = await ai_service.analyze_call(
                        doc["objective"], doc["authority"], doc["transcript"], f"call-an-{ref}")
                    await db.voice_calls.update_one({"session_ref": ref},
                                                    {"$set": {"analysis": analysis}})
            except Exception as e:
                log.error("post-bridge analysis failed: %s", type(e).__name__)
        await close_all()
