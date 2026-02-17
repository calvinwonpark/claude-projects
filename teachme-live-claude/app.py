import asyncio
import json
import logging
import time
from typing import Dict, Optional
from pathlib import Path
import sys

APP_MODULE_DIR = Path(__file__).parent / "app"
if str(APP_MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(APP_MODULE_DIR))

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from google.cloud import speech, texttospeech

from agent.runtime import (
    build_structured_system_prompt,
    is_image_required_query,
    parse_structured_json,
    run_tutor_turn,
    safe_structured_fallback,
)

from config import settings
from llm.anthropic_client import AnthropicClient
from metrics import metrics
from session_state import SessionState
from stt_stream import StreamingSTT
from tts_stream import StreamingTTS
from websocket_protocol import WebSocketProtocol

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

claude_client = AnthropicClient(api_key=settings.anthropic_api_key) if settings.anthropic_api_key else None
speech_client = speech.SpeechClient()
tts_client = texttospeech.TextToSpeechClient()
sessions: Dict[str, SessionState] = {}


def build_instructions(target_lang: str, translator_mode: bool) -> str:
    return build_structured_system_prompt(target_lang, translator_mode)


async def send_binary_message(websocket: WebSocket, msg_type: int, payload: bytes):
    """Send binary WebSocket message"""
    try:
        message = WebSocketProtocol.encode_message(msg_type, payload)
        await websocket.send_bytes(message)
    except (WebSocketDisconnect, RuntimeError, ConnectionError) as e:
        # Expected errors when WebSocket is closed - don't log as error
        pass
    except Exception as e:
        logger.error(f"Error sending binary message: {e}")


async def send_json_message(websocket: WebSocket, msg_type: int, data: dict):
    """Send JSON WebSocket message"""
    try:
        message = WebSocketProtocol.encode_json_message(msg_type, data)
        await websocket.send_bytes(message)
    except (WebSocketDisconnect, RuntimeError, ConnectionError) as e:
        # Expected errors when WebSocket is closed - don't log as error
        pass
    except Exception as e:
        logger.error(f"Error sending JSON message: {e}")


async def send_error(websocket: WebSocket, message: str, code: int = 500):
    await send_json_message(websocket, WebSocketProtocol.ERROR, {"message": message, "code": code})


def _structured_to_speakable_text(structured: dict, target_lang: str) -> str:
    answer = str(structured.get("answer", "")).strip()
    steps = [str(s).strip() for s in structured.get("steps", []) if str(s).strip()]
    examples = [str(s).strip() for s in structured.get("examples", []) if str(s).strip()]
    if target_lang == "ko":
        lines = [answer]
        if steps:
            lines.append("핵심 단계:")
            lines.extend([f"{i+1}. {s}" for i, s in enumerate(steps[:3])])
        if examples:
            lines.append(f"예시: {examples[0]}")
        return "\n".join(lines).strip()
    lines = [answer]
    if steps:
        lines.append("Key steps:")
        lines.extend([f"{i+1}. {s}" for i, s in enumerate(steps[:3])])
    if examples:
        lines.append(f"Example: {examples[0]}")
    return "\n".join(lines).strip()


def _clarification_text(target_lang: str) -> str:
    if target_lang == "ko":
        return "방금 말씀을 정확히 듣지 못했어요. 한 번만 더 천천히 말씀해 주실래요?"
    return "I couldn't catch that clearly. Could you repeat it once more, a bit slowly?"


async def _speak_text(
    *,
    websocket: WebSocket,
    session_state: SessionState,
    generation_id: int,
    text: str,
    turn_cancel_event: asyncio.Event,
) -> float:
    tts_started = time.perf_counter()

    async def on_audio_chunk(chunk: bytes):
        if generation_id != session_state.generation_id or turn_cancel_event.is_set():
            return
        await send_binary_message(websocket, WebSocketProtocol.AUDIO_CHUNK, chunk)

    async def on_complete():
        if generation_id != session_state.generation_id or turn_cancel_event.is_set():
            return
        await send_json_message(websocket, WebSocketProtocol.AUDIO_COMPLETE, {})

    tts_stream = StreamingTTS(tts_client=tts_client, on_audio_chunk=on_audio_chunk, on_complete=on_complete)
    tts_language = "ko-KR" if session_state.target_language == "ko" else "en-US"
    await tts_stream.synthesize_and_stream(text=text, language_code=tts_language, cancel_event=turn_cancel_event)
    return (time.perf_counter() - tts_started) * 1000.0


async def handle_final_transcript(
    session_state: SessionState,
    websocket: WebSocket,
    transcript: str,
    confidence: float = 1.0,
):
    if not transcript or transcript.strip() == "":
        return
    turn_started = session_state.turn_started_at or time.perf_counter()
    stt_latency_ms = max(0.0, (time.perf_counter() - turn_started) * 1000.0)
    session_state.last_transcript_confidence = confidence
    logger.info(
        json.dumps(
            {
                "event": "final_transcript",
                "session_id": session_state.session_id,
                "turn_id": session_state.current_turn_id,
                "chars": len(transcript),
                "confidence": round(confidence, 3),
            },
            ensure_ascii=False,
        )
    )

    await send_json_message(websocket, WebSocketProtocol.TRANSCRIPT_FINAL, {"text": transcript, "confidence": confidence})
    generation_id = session_state.increment_generation_id()
    if session_state.active_generation_cancel_event is not None:
        session_state.active_generation_cancel_event.set()
    turn_cancel_event = asyncio.Event()
    session_state.active_generation_cancel_event = turn_cancel_event
    session_state.is_tts_playing = False

    async def generate_and_speak():
        try:
            if confidence < settings.stt_confidence_threshold:
                metrics.transcripts_low_confidence_total += 1
                clarification = _clarification_text(session_state.target_language)
                await send_json_message(
                    websocket,
                    WebSocketProtocol.LLM_DELTA,
                    {
                        "text": clarification,
                        "turn_id": session_state.current_turn_id,
                        "final": True,
                    },
                )
                session_state.is_tts_playing = True
                tts_latency = await _speak_text(
                    websocket=websocket,
                session_state=session_state,
                    generation_id=generation_id,
                    text=clarification,
                    turn_cancel_event=turn_cancel_event,
                )
                metrics.record_turn(stt_latency_ms=stt_latency_ms, llm_latency_ms=0.0, tts_latency_ms=tts_latency, e2e_latency_ms=(time.perf_counter() - turn_started) * 1000.0)
                session_state.is_tts_playing = False
                return

            if is_image_required_query(transcript) and not session_state.uploaded_image:
                guardrail_text = (
                    "이미지 관련 질문을 하셨다면 먼저 이미지를 업로드해 주세요."
                    if session_state.target_language == "ko"
                    else "If your question is about an image, please upload the image first."
                )
                await send_json_message(
                    websocket,
                    WebSocketProtocol.LLM_DELTA,
                    {
                        "text": guardrail_text,
                        "turn_id": session_state.current_turn_id,
                        "final": True,
                    },
                )
                session_state.is_tts_playing = True
                tts_latency = await _speak_text(
                    websocket=websocket,
                    session_state=session_state,
                    generation_id=generation_id,
                    text=guardrail_text,
                    turn_cancel_event=turn_cancel_event,
                )
                metrics.record_turn(stt_latency_ms=stt_latency_ms, llm_latency_ms=0.0, tts_latency_ms=tts_latency, e2e_latency_ms=(time.perf_counter() - turn_started) * 1000.0)
                session_state.is_tts_playing = False
                return
            
            if claude_client is None:
                raise RuntimeError("ANTHROPIC_API_KEY is missing")

            llm_started = time.perf_counter()
            image_blocks: list[dict] = []
            use_uploaded_image = bool(session_state.uploaded_image and is_image_required_query(transcript))
            if use_uploaded_image:
                mime_type = "image/jpeg"
                data = session_state.uploaded_image
                if data.startswith("data:") and "," in data:
                    header, b64_data = data.split(",", 1)
                    data = b64_data
                    if ";" in header:
                        mime_type = header[5:].split(";", 1)[0] or mime_type
                image_blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime_type, "data": data}})

            conv = []
            for msg in session_state.conversation_history[-10:]:
                conv.append({"role": msg.get("role", "user"), "content": [{"type": "text", "text": msg.get("text", "")}]})
            user_content = [{"type": "text", "text": transcript}] + image_blocks
            conv.append({"role": "user", "content": user_content})
            has_image_in_turn = len(image_blocks) > 0

            token_buffer: list[str] = []

            async def _on_token(delta: str):
                token_buffer.append(delta)
                await send_json_message(
                    websocket,
                    WebSocketProtocol.LLM_DELTA,
                    {
                        "text": delta,
                        "turn_id": session_state.current_turn_id,
                        "final": False,
                    },
                )

            try:
                timeout_budget_s = max(
                    1.0,
                    (
                        settings.image_time_budget_ms
                        if has_image_in_turn
                        else settings.time_budget_ms
                    ) / 1000.0,
                )
                result = await asyncio.wait_for(
                    run_tutor_turn(
                        claude=claude_client,
                        conversation_messages=conv,
                        query=transcript,
                        target_language=session_state.target_language,
                        translator_mode=session_state.translator_mode,
                        on_token=_on_token,
                    ),
                    timeout=timeout_budget_s,
                )
            except asyncio.TimeoutError:
                quick = safe_structured_fallback(session_state.target_language)
                quick["answer"] = (
                    "응답이 길어질 것 같아 핵심만 먼저 짧게 정리할게요."
                    if session_state.target_language == "ko"
                    else "This may take longer, so here is a quick summary first."
                )
                quick_text = _structured_to_speakable_text(quick, session_state.target_language)
                await send_json_message(
                    websocket,
                    WebSocketProtocol.LLM_DELTA,
                    {
                        "text": quick_text,
                        "turn_id": session_state.current_turn_id,
                        "final": True,
                    },
                )
                llm_latency = (time.perf_counter() - llm_started) * 1000.0
                session_state.is_tts_playing = True
                tts_latency = await _speak_text(
                    websocket=websocket,
                    session_state=session_state,
                    generation_id=generation_id,
                    text=quick_text,
                    turn_cancel_event=turn_cancel_event,
                )
                metrics.record_turn(
                    stt_latency_ms=stt_latency_ms,
                    llm_latency_ms=llm_latency,
                    tts_latency_ms=tts_latency,
                    e2e_latency_ms=(time.perf_counter() - turn_started) * 1000.0,
                )
                session_state.is_tts_playing = False
                await send_json_message(websocket, WebSocketProtocol.NOTES, {"text": json.dumps(quick, ensure_ascii=False, indent=2)})
                return

            llm_latency = (time.perf_counter() - llm_started) * 1000.0

            if turn_cancel_event.is_set():
                session_state.is_tts_playing = False
                return
            if generation_id != session_state.generation_id:
                session_state.is_tts_playing = False
                return
            
            structured = parse_structured_json(result.raw_text) or result.structured or safe_structured_fallback(session_state.target_language)
            speak_text = _structured_to_speakable_text(structured, session_state.target_language)

            if token_buffer:
                await send_json_message(
                    websocket,
                    WebSocketProtocol.LLM_DELTA,
                    {"text": "", "turn_id": session_state.current_turn_id, "final": True},
                )
            else:
                await send_json_message(
                    websocket,
                    WebSocketProtocol.LLM_DELTA,
                    {"text": result.raw_text, "turn_id": session_state.current_turn_id, "final": True},
                )

            session_state.is_tts_playing = True
            tts_latency = await _speak_text(
                websocket=websocket,
                session_state=session_state,
                generation_id=generation_id,
                text=speak_text,
                turn_cancel_event=turn_cancel_event,
            )
            session_state.is_tts_playing = False
            
            session_state.conversation_history.append({"role": "user", "text": transcript})
            session_state.conversation_history.append({"role": "assistant", "text": speak_text})
            session_state.conversation_history = session_state.conversation_history[-20:]

            metrics.tool_calls_total += len(result.tool_calls)
            metrics.tool_failures_total += int(result.tool_failures)
            metrics.record_turn(
                stt_latency_ms=stt_latency_ms,
                llm_latency_ms=llm_latency,
                tts_latency_ms=tts_latency,
                e2e_latency_ms=(time.perf_counter() - turn_started) * 1000.0,
            )

            await send_json_message(websocket, WebSocketProtocol.NOTES, {"text": json.dumps(structured, ensure_ascii=False, indent=2)})
            logger.info(
                json.dumps(
                    {
                        "event": "turn_complete",
                        "session_id": session_state.session_id,
                        "turn_id": session_state.current_turn_id,
                        "model": result.model,
                        "request_id": result.request_id,
                        "tokens_in": result.input_tokens,
                        "tokens_out": result.output_tokens,
                        "tool_calls": [t["name"] for t in result.tool_calls],
                    },
                    ensure_ascii=False,
                )
            )
        except asyncio.CancelledError:
            session_state.is_tts_playing = False
        except Exception as e:
            logger.error(f"Error in generate_and_speak: {e}")
            session_state.is_tts_playing = False
            await send_error(websocket, f"Error generating response: {str(e)}")
    
    session_state.llm_task = asyncio.create_task(generate_and_speak())


async def handle_interim_transcript(websocket: WebSocket, transcript: str):
    """Handle interim transcript: send to client for real-time feedback"""
    if transcript and transcript.strip():
        await send_json_message(websocket, WebSocketProtocol.TRANSCRIPT_INTERIM, {
            "text": transcript
        })


@app.get("/", response_class=HTMLResponse)
def index():
    with open("static/index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.get("/health")
def health():
    return {"ok": True, "app": settings.app_name}


@app.get("/api/metrics")
def api_metrics():
    return metrics.as_dict(active_sessions=len(sessions))


@app.post("/api/chat")
async def chat(payload: dict):
    if claude_client is None:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY missing")
    text = str(payload.get("message") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="message required")
    target = str(payload.get("target_language") or "en")
    translator_mode = bool(payload.get("translator_mode") or False)
    conv = [{"role": "user", "content": [{"type": "text", "text": text}]}]
    result = await run_tutor_turn(
        claude=claude_client,
        conversation_messages=conv,
        query=text,
        target_language=target,
        translator_mode=translator_mode,
        on_token=None,
    )
    structured = parse_structured_json(result.raw_text) or result.structured or safe_structured_fallback(target)
    return {
        "structured": structured,
        "model": result.model,
        "request_id": result.request_id,
        "tool_calls": result.tool_calls,
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time communication with binary protocol"""
    await websocket.accept()
    logger.info("WebSocket connection accepted")
    session_state: Optional[SessionState] = None
    stt_stream: Optional[StreamingSTT] = None
    
    try:
        # Receive INIT message (binary or text for backward compatibility)
        try:
            message = await websocket.receive()
            
            # Handle both binary and text (for backward compatibility)
            if "bytes" in message:
                msg_type, payload = WebSocketProtocol.parse_message(message["bytes"])
                if msg_type != WebSocketProtocol.INIT:
                    await send_error(websocket, "Expected INIT message")
                    return
                init_data = WebSocketProtocol.decode_json_payload(payload)
            elif "text" in message:
                # Backward compatibility: JSON text message
                init_data = json.loads(message["text"])
                if init_data.get("type") != "init":
                    await send_error(websocket, "Expected init message")
                    return
            else:
                await send_error(websocket, "Invalid message format")
                return
            
            session_id = init_data.get("session_id", f"session_{asyncio.get_event_loop().time()}")
            target_lang = init_data.get("target_language", "en")
            translator_mode = init_data.get("translator_mode", False)
            
            # Create session state
            session_state = SessionState(
                session_id=session_id,
                target_language=target_lang,
                translator_mode=translator_mode,
                instructions=build_instructions(target_lang, translator_mode),
            )
            sessions[session_id] = session_state
            
            stt_language = "ko-KR" if target_lang == "ko" else "en-US"
            
            async def on_interim(text: str):
                await handle_interim_transcript(websocket, text)
            
            async def on_final(text: str, conf: float = 1.0):
                await handle_final_transcript(session_state, websocket, text, conf)
            
            stt_stream = StreamingSTT(
                session_state=session_state,
                language_code=stt_language,
                sample_rate=settings.stt_sample_rate_hz,
                on_interim=on_interim,
                on_final=on_final,
            )
            stt_stream.initialize(speech_client)
            session_state.stt_stream = stt_stream.stream
            session_state.silence_timeout_ms = settings.turn_silence_ms
            
            # Start STT processing tasks
            session_state.stt_task = asyncio.create_task(stt_stream.process_audio_queue())
            stt_response_task = asyncio.create_task(stt_stream.handle_responses())
            
            # Store response task for cleanup
            session_state._stt_response_task = stt_response_task
            
            # Send CONNECTED message
            await send_json_message(websocket, WebSocketProtocol.CONNECTED, {
                "session_id": session_id
            })
            
            logger.info(f"Session initialized: {session_id}")
            
            # Main message loop
            disconnected = False
            while not disconnected:
                try:
                    message = await websocket.receive()
                    
                    # Handle binary messages
                    if "bytes" in message:
                        try:
                            msg_type, payload = WebSocketProtocol.parse_message(message["bytes"])
                            
                            if msg_type == WebSocketProtocol.AUDIO_FRAME:
                                if session_state.turn_started_at is None:
                                    session_state.begin_turn(time.perf_counter())
                                session_state.turn_audio_bytes += len(payload)

                                if session_state.turn_audio_bytes > settings.max_audio_bytes:
                                    await send_error(websocket, "Audio payload too large for a single turn.", code=413)
                                    continue
                                if session_state.turn_started_at and (time.perf_counter() - session_state.turn_started_at) > settings.turn_max_seconds:
                                    await send_error(websocket, "Turn exceeded maximum duration. Please ask in shorter segments.", code=413)
                                    continue
                                
                                if session_state.should_drop_frame():
                                    session_state.dropped_frames += 1
                                    logger.warning(f"Dropping frame due to backpressure (queue size: {session_state.audio_queue.qsize()})")
                                else:
                                    await session_state.audio_queue.put(payload)
                                    session_state.last_audio_time = asyncio.get_event_loop().time()
                                    logger.debug(f"Received audio frame: {len(payload)} bytes, queue size: {session_state.audio_queue.qsize()}")
                            
                            elif msg_type == WebSocketProtocol.SPEECH_START:
                                now_ts = time.perf_counter()
                                session_state.begin_turn(now_ts)
                                session_state.increment_generation_id()
                                if session_state.active_generation_cancel_event:
                                    session_state.active_generation_cancel_event.set()
                                if session_state.llm_task and not session_state.llm_task.done():
                                    session_state.llm_task.cancel()
                                if session_state.tts_task and not session_state.tts_task.done():
                                    session_state.tts_task.cancel()
                                session_state.cancel_event.set()
                                session_state.is_tts_playing = False
                                session_state.last_audio_time = asyncio.get_event_loop().time()
                            
                            elif msg_type == WebSocketProtocol.SPEECH_END:
                                logger.info("Speech end detected")
                            
                            elif msg_type == WebSocketProtocol.BARGE_IN:
                                # User interrupted - cancel everything
                                logger.info("Barge-in detected")
                                if session_state.active_generation_cancel_event:
                                    session_state.active_generation_cancel_event.set()
                                session_state.cancel_event.set()
                                session_state.increment_generation_id()
                                
                                # Cancel tasks
                                if session_state.llm_task and not session_state.llm_task.done():
                                    session_state.llm_task.cancel()
                                if session_state.tts_task and not session_state.tts_task.done():
                                    session_state.tts_task.cancel()
                                
                                session_state.is_tts_playing = False
                            
                            elif msg_type == WebSocketProtocol.CONFIG_UPDATE:
                                config_data = WebSocketProtocol.decode_json_payload(payload)
                                session_state.target_language = config_data.get("target_language", session_state.target_language)
                                session_state.translator_mode = config_data.get("translator_mode", session_state.translator_mode)
                                session_state.instructions = build_instructions(
                                    session_state.target_language,
                                    session_state.translator_mode
                                )
                                
                                new_stt_language = "ko-KR" if session_state.target_language == "ko" else "en-US"
                                if stt_stream and stt_stream.language_code != new_stt_language:
                                    if session_state.stt_task and not session_state.stt_task.done():
                                        session_state.stt_task.cancel()
                                    stt_stream.close()
                                    
                                    async def on_interim(text: str):
                                        await handle_interim_transcript(websocket, text)
                                    
                                    async def on_final(text: str, conf: float = 1.0):
                                        await handle_final_transcript(session_state, websocket, text, conf)
                                    
                                    stt_stream = StreamingSTT(
                                        session_state=session_state,
                                        language_code=new_stt_language,
                                        sample_rate=settings.stt_sample_rate_hz,
                                        on_interim=on_interim,
                                        on_final=on_final,
                                    )
                                    stt_stream.initialize(speech_client)
                                    session_state.stt_stream = stt_stream.stream
                                    session_state.stt_task = asyncio.create_task(stt_stream.process_audio_queue())
                                    session_state._stt_response_task = asyncio.create_task(stt_stream.handle_responses())
                                
                                await send_json_message(websocket, WebSocketProtocol.CONFIG_UPDATED, {
                                    "status": "ok"
                                })
                            
                            elif msg_type == WebSocketProtocol.IMAGE_UPLOAD:
                                image_data = WebSocketProtocol.decode_json_payload(payload)
                                session_state.uploaded_image = image_data.get("image_data")
                                await send_json_message(websocket, WebSocketProtocol.IMAGE_RECEIVED, {
                                    "status": "ready"
                                })
                                logger.info("Image uploaded")
                            
                            elif msg_type == WebSocketProtocol.REQUEST_NOTES:
                                notes_prompt = (
                                    "Summarize our tutoring session so far. "
                                    "Return JSON with answer, steps, examples, common_mistakes, next_exercises. "
                                    "Do NOT speak these aloud; just return text notes."
                                    )
                                
                                async def generate_notes():
                                    try:
                                        if claude_client is None:
                                            raise RuntimeError("ANTHROPIC_API_KEY missing")
                                        conv = [{"role": "user", "content": [{"type": "text", "text": notes_prompt}]}]
                                        result = await run_tutor_turn(
                                            claude=claude_client,
                                            conversation_messages=conv,
                                            query=notes_prompt,
                                            target_language=session_state.target_language,
                                            translator_mode=session_state.translator_mode,
                                            on_token=None,
                                        )
                                        structured = parse_structured_json(result.raw_text) or result.structured or safe_structured_fallback(session_state.target_language)
                                        await send_json_message(websocket, WebSocketProtocol.NOTES, {"text": json.dumps(structured, ensure_ascii=False, indent=2)})
                                    except Exception as e:
                                        logger.error(f"Error generating notes: {e}")
                                        await send_error(websocket, f"Error generating notes: {str(e)}")
                                
                                asyncio.create_task(generate_notes())
                        
                        except ValueError as e:
                            logger.error(f"Invalid binary message: {e}")
                            await send_error(websocket, f"Invalid message: {str(e)}")
                        except Exception as e:
                            logger.error(f"Error processing binary message: {e}")
                            await send_error(websocket, f"Error: {str(e)}")
                    
                    # Handle text messages (backward compatibility)
                    elif "text" in message:
                        try:
                            data = json.loads(message["text"])
                            msg_type_str = data.get("type")
                            
                            # Map text message types to binary protocol
                            if msg_type_str == "audio_chunk":
                                # Legacy: base64 audio - decode and queue
                                audio_b64 = data.get("audio_data")
                                if audio_b64:
                                    import base64
                                    audio_bytes = base64.b64decode(audio_b64)
                                    if not session_state.should_drop_frame():
                                        await session_state.audio_queue.put(audio_bytes)
                                        session_state.last_audio_time = asyncio.get_event_loop().time()
                            
                            elif msg_type_str in ["image_upload", "update_config", "request_notes"]:
                                # Handle as binary protocol would
                                logger.warning(f"Legacy text message type: {msg_type_str}")
                        
                        except Exception as e:
                            logger.error(f"Error processing text message: {e}")
                
                except WebSocketDisconnect:
                    logger.info("WebSocket disconnected (inner loop)")
                    disconnected = True
                    break
                except RuntimeError as e:
                    # FastAPI raises RuntimeError when trying to receive after disconnect
                    if "disconnect" in str(e).lower() or "receive" in str(e).lower():
                        logger.info("WebSocket disconnected (RuntimeError)")
                        disconnected = True
                        break
                    else:
                        logger.error(f"RuntimeError in message loop: {e}")
                        try:
                            await send_error(websocket, f"Error: {str(e)}")
                        except:
                            pass
                except Exception as e:
                    # Check if it's a disconnect-related error
                    error_str = str(e).lower()
                    if "disconnect" in error_str or ("receive" in error_str and "disconnect" in error_str):
                        logger.info(f"WebSocket disconnected ({type(e).__name__})")
                        disconnected = True
                        break
                    logger.error(f"Error in message loop: {e}")
                    try:
                        await send_error(websocket, f"Error: {str(e)}")
                    except:
                        pass  # WebSocket might be closed
        
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected (message loop)")
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            try:
                await send_error(websocket, f"Error: {str(e)}")
            except:
                pass  # WebSocket might be closed
    
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: {session_id if 'session_id' in locals() else 'unknown'}")
    except Exception as e:
        logger.error(f"WebSocket endpoint error: {e}")
    finally:
        # Cleanup
        session_id_to_cleanup = session_id if 'session_id' in locals() else None
        if session_state:
            try:
                session_state.cleanup()
            except Exception as e:
                logger.error(f"Error during session cleanup: {e}")
            if session_state.session_id in sessions:
                del sessions[session_state.session_id]
            logger.info(f"Session cleaned up: {session_state.session_id}")
        
        if stt_stream:
            try:
                stt_stream.close()
            except Exception as e:
                logger.error(f"Error closing STT stream: {e}")
        
        logger.info(f"WebSocket connection closed for session: {session_id_to_cleanup}")


@app.on_event("shutdown")
async def shutdown_event():
    for session_state in list(sessions.values()):
        session_state.cleanup()
    sessions.clear()
    logger.info("All sessions cleaned up")
