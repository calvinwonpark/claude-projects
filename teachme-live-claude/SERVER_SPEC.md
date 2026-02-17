# Server-Side Binary WebSocket Protocol Specification

## Overview

The client sends binary WebSocket messages with a simple protocol:
- **Byte 0**: Message type (uint8)
- **Bytes 1-4**: Payload length (uint32, big-endian)
- **Bytes 5+**: Payload (JSON string for control messages, binary PCM16 for audio)

## Message Types (Client → Server)

| Type | Value | Description | Payload |
|------|-------|-------------|---------|
| `AUDIO_FRAME` | 0x01 | PCM16 audio frame (~20ms) | Binary: Int16Array PCM samples |
| `INIT` | 0x02 | Initialize session | JSON: `{session_id, target_language, translator_mode}` |
| `CONFIG_UPDATE` | 0x03 | Update language/config | JSON: `{target_language, translator_mode}` |
| `IMAGE_UPLOAD` | 0x04 | Upload image | JSON: `{image_data: base64}` |
| `REQUEST_NOTES` | 0x05 | Request tutor notes | JSON: `{}` |
| `SPEECH_START` | 0x06 | User started speaking | JSON: `{}` |
| `SPEECH_END` | 0x07 | User stopped speaking | JSON: `{}` |
| `BARGE_IN` | 0x08 | User interrupted (barge-in) | JSON: `{}` |

## Message Types (Server → Client)

| Type | Value | Description | Payload |
|------|-------|-------------|---------|
| `CONNECTED` | 0x10 | Session initialized | JSON: `{session_id}` |
| `TRANSCRIPT_INTERIM` | 0x11 | Interim transcript | JSON: `{text}` |
| `TRANSCRIPT_FINAL` | 0x12 | Final transcript | JSON: `{text}` |
| `AUDIO_CHUNK` | 0x13 | TTS audio chunk | Binary: PCM16 or encoded audio |
| `AUDIO_COMPLETE` | 0x14 | TTS complete | JSON: `{}` |
| `ERROR` | 0x15 | Error message | JSON: `{message}` |
| `NOTES` | 0x16 | Tutor notes | JSON: `{text}` |
| `IMAGE_RECEIVED` | 0x17 | Image received | JSON: `{status}` |
| `CONFIG_UPDATED` | 0x18 | Config updated | JSON: `{status}` |

## Server Implementation Pseudocode

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from google.cloud import speech, texttospeech
from google import genai
import asyncio
import json
import struct

app = FastAPI()

# Session storage
sessions = {}
streaming_recognizers = {}  # Per-session STT streaming

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session_id = None
    stt_stream = None
    
    try:
        # Receive INIT message
        init_msg = await websocket.receive_bytes()
        msg_type, payload_len, payload = parse_binary_message(init_msg)
        
        if msg_type != 0x02:  # INIT
            await send_error(websocket, "Expected INIT message")
            return
        
        init_data = json.loads(payload.decode('utf-8'))
        session_id = init_data['session_id']
        target_lang = init_data.get('target_language', 'en')
        translator_mode = init_data.get('translator_mode', False)
        
        # Initialize session
        sessions[session_id] = {
            'conversation_history': [],
            'target_language': target_lang,
            'translator_mode': translator_mode,
            'audio_buffer': bytearray(),
        }
        
        # Initialize Google Cloud Speech-to-Text streaming
        stt_client = speech.SpeechClient()
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code="en-US" if target_lang == "en" else "ko-KR",
            enable_automatic_punctuation=True,
            enable_interim_results=True,  # For interim transcripts
        )
        
        streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
        )
        
        stt_stream = stt_client.streaming_recognize(streaming_config)
        
        # Send CONNECTED message
        await send_binary_message(websocket, 0x10, json.dumps({
            'session_id': session_id
        }).encode('utf-8'))
        
        # Start background task for STT responses
        stt_task = asyncio.create_task(handle_stt_responses(
            stt_stream, websocket, session_id
        ))
        
        # Main message loop
        while True:
            message = await websocket.receive_bytes()
            msg_type, payload_len, payload = parse_binary_message(message)
            
            if msg_type == 0x01:  # AUDIO_FRAME
                # Send to STT streaming
                audio_request = speech.StreamingRecognizeRequest(
                    audio_content=bytes(payload)
                )
                stt_stream.write(audio_request)
                
            elif msg_type == 0x06:  # SPEECH_START
                # User started speaking - prepare for new utterance
                sessions[session_id]['audio_buffer'] = bytearray()
                
            elif msg_type == 0x07:  # SPEECH_END
                # User stopped speaking - finalize transcription
                stt_stream.write(speech.StreamingRecognizeRequest(
                    audio_content=b''  # Signal end
                ))
                
            elif msg_type == 0x08:  # BARGE_IN
                # User interrupted - cancel ongoing TTS/Gemini
                # Implementation: set a flag, cancel async tasks
                sessions[session_id]['barge_in'] = True
                
            elif msg_type == 0x03:  # CONFIG_UPDATE
                config_data = json.loads(payload.decode('utf-8'))
                sessions[session_id]['target_language'] = config_data['target_language']
                sessions[session_id]['translator_mode'] = config_data['translator_mode']
                # Restart STT stream with new language
                # ... (restart streaming recognizer)
                
            elif msg_type == 0x04:  # IMAGE_UPLOAD
                image_data = json.loads(payload.decode('utf-8'))
                sessions[session_id]['uploaded_image'] = image_data['image_data']
                await send_binary_message(websocket, 0x17, json.dumps({
                    'status': 'ready'
                }).encode('utf-8'))
                
            elif msg_type == 0x05:  # REQUEST_NOTES
                # Generate notes using Gemini
                notes = await generate_notes(sessions[session_id])
                await send_binary_message(websocket, 0x16, json.dumps({
                    'text': notes
                }).encode('utf-8'))
    
    except WebSocketDisconnect:
        pass
    finally:
        # Cleanup
        if stt_stream:
            stt_stream.close()
        if session_id and session_id in sessions:
            del sessions[session_id]
        if session_id and session_id in streaming_recognizers:
            del streaming_recognizers[session_id]


async def handle_stt_responses(stt_stream, websocket, session_id):
    """Handle STT streaming responses and generate Gemini responses"""
    try:
        for response in stt_stream:
            if not response.results:
                continue
            
            result = response.results[0]
            
            if result.alternatives:
                transcript = result.alternatives[0].transcript
                
                if result.is_final_result:
                    # Final transcript
                    await send_binary_message(websocket, 0x12, json.dumps({
                        'text': transcript
                    }).encode('utf-8'))
                    
                    # Generate Gemini response
                    if not sessions[session_id].get('barge_in', False):
                        response_text = await generate_gemini_response(
                            sessions[session_id], transcript
                        )
                        
                        # Synthesize TTS
                        await stream_tts_response(
                            websocket, response_text, 
                            sessions[session_id]['target_language']
                        )
                    
                    sessions[session_id]['barge_in'] = False
                else:
                    # Interim transcript
                    await send_binary_message(websocket, 0x11, json.dumps({
                        'text': transcript
                    }).encode('utf-8'))
    
    except Exception as e:
        print(f"STT stream error: {e}")
        await send_error(websocket, str(e))


async def stream_tts_response(websocket, text, language_code):
    """Stream TTS audio in chunks"""
    tts_client = texttospeech.TextToSpeechClient()
    
    synthesis_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=24000
    )
    
    response = tts_client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config
    )
    
    # Stream audio in chunks (e.g., 4800 samples = 200ms at 24kHz)
    chunk_size = 4800 * 2  # 200ms of 16-bit PCM
    audio_data = response.audio_content
    
    for i in range(0, len(audio_data), chunk_size):
        chunk = audio_data[i:i + chunk_size]
        await send_binary_message(websocket, 0x13, chunk)
    
    await send_binary_message(websocket, 0x14, b'{}')  # AUDIO_COMPLETE


def parse_binary_message(buffer):
    """Parse binary WebSocket message"""
    if len(buffer) < 5:
        raise ValueError("Message too short")
    
    msg_type = buffer[0]
    payload_len = struct.unpack('>I', buffer[1:5])[0]  # big-endian uint32
    
    if len(buffer) < 5 + payload_len:
        raise ValueError("Payload length mismatch")
    
    payload = buffer[5:5 + payload_len]
    return msg_type, payload_len, payload


async def send_binary_message(websocket, msg_type, payload):
    """Send binary WebSocket message"""
    payload_bytes = payload if isinstance(payload, bytes) else payload.encode('utf-8')
    buffer = bytearray(5 + len(payload_bytes))
    buffer[0] = msg_type
    struct.pack_into('>I', buffer, 1, len(payload_bytes))  # big-endian
    buffer[5:] = payload_bytes
    await websocket.send_bytes(bytes(buffer))


async def send_error(websocket, message):
    """Send error message"""
    await send_binary_message(websocket, 0x15, json.dumps({
        'message': message
    }).encode('utf-8'))
```

## Key Implementation Notes

1. **Streaming STT**: Use `streaming_recognize()` for low-latency transcription
2. **Interim Results**: Enable `interim_results=True` for real-time feedback
3. **Audio Chunking**: Stream TTS in ~200ms chunks for smooth playback
4. **Barge-in Handling**: Check `barge_in` flag before sending TTS/Gemini responses
5. **Session Management**: Store conversation history per session
6. **Error Handling**: Always send error messages in binary format
7. **Resource Cleanup**: Close STT streams on disconnect

## Tuning Parameters

- **Frame Size**: 320 samples (~20ms at 16kHz) - good balance of latency vs overhead
- **TTS Chunk Size**: 4800 samples (~200ms at 24kHz) - smooth playback
- **STT Sample Rate**: 16000 Hz (standard for speech recognition)
- **TTS Sample Rate**: 24000 Hz (standard for TTS)
- **Interim Results**: Enabled for <500ms latency
- **Jitter Buffer**: 100ms on client side
