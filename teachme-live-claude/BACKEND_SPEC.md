# Backend Binary WebSocket Protocol Specification

## Message Format

All messages use a binary protocol:
- **Byte 0**: Message type (uint8)
- **Bytes 1-4**: Payload length (uint32, big-endian)
- **Bytes 5+**: Payload (JSON string for control messages, binary PCM16 for audio)

## Client → Server Message Types

| Type | Value | Description | Payload Format |
|------|-------|-------------|----------------|
| `AUDIO_FRAME` | 0x01 | PCM16 audio frame | Binary: Int16Array PCM samples |
| `INIT` | 0x02 | Initialize session | JSON: `{session_id, target_language, translator_mode}` |
| `CONFIG_UPDATE` | 0x03 | Update language/config | JSON: `{target_language, translator_mode}` |
| `IMAGE_UPLOAD` | 0x04 | Upload image | JSON: `{image_data: base64}` |
| `REQUEST_NOTES` | 0x05 | Request tutor notes | JSON: `{}` |
| `SPEECH_START` | 0x06 | User started speaking | JSON: `{}` |
| `SPEECH_END` | 0x07 | User stopped speaking | JSON: `{}` |
| `BARGE_IN` | 0x08 | User interrupted (barge-in) | JSON: `{}` |

## Server → Client Message Types

| Type | Value | Description | Payload Format |
|------|-------|-------------|----------------|
| `CONNECTED` | 0x10 | Session initialized | JSON: `{session_id}` |
| `TRANSCRIPT_INTERIM` | 0x11 | Interim transcript | JSON: `{text}` |
| `TRANSCRIPT_FINAL` | 0x12 | Final transcript | JSON: `{text}` |
| `AUDIO_CHUNK` | 0x13 | TTS audio chunk | Binary: LINEAR16 PCM samples |
| `AUDIO_COMPLETE` | 0x14 | TTS complete | JSON: `{}` |
| `ERROR` | 0x15 | Error message | JSON: `{message}` |
| `NOTES` | 0x16 | Tutor notes | JSON: `{text}` |
| `IMAGE_RECEIVED` | 0x17 | Image received | JSON: `{status}` |
| `CONFIG_UPDATED` | 0x18 | Config updated | JSON: `{status}` |

## Audio Format

### Input (Client → Server)
- **Format**: LINEAR16 (PCM16)
- **Sample Rate**: 16000 Hz
- **Channels**: Mono (1 channel)
- **Frame Size**: 320 samples (~20ms) recommended
- **Frame Bytes**: 640 bytes (320 samples × 2 bytes)

### Output (Server → Client)
- **Format**: LINEAR16 (PCM16)
- **Sample Rate**: 24000 Hz (TTS standard)
- **Channels**: Mono (1 channel)
- **Chunk Size**: ~4800 samples (~200ms) per chunk

## Architecture

### Per-Session Components

Each WebSocket session maintains:

1. **SessionState**: Core state management
   - Conversation history
   - Configuration (language, translator mode)
   - Audio queue (asyncio.Queue)
   - Async tasks (STT, LLM, TTS)
   - Cancellation events

2. **StreamingSTT**: Google Cloud Speech-to-Text streaming
   - Consumes audio_queue
   - Emits interim and final transcripts
   - Handles endpointing via silence timeout

3. **GeminiClient**: Response generation
   - Structured conversation history
   - Cancellable generation
   - Image support

4. **StreamingTTS**: Text-to-Speech streaming
   - Chunked audio output
   - Cancellable synthesis

### Task Flow

```
Audio Frame → audio_queue → STT Task → Interim/Final Transcripts
                                              ↓
                                    Final Transcript → LLM Task → TTS Task → Audio Chunks
```

### Barge-in Flow

```
User speaks → SPEECH_START/BARGE_IN → cancel_event.set()
                                              ↓
                                    Cancel LLM/TTS tasks → Reset state → Process new audio
```

## Endpointing Strategy

1. **Client VAD**: Client sends `SPEECH_START` and `SPEECH_END` messages
2. **Server-side Silence Detection**: 
   - Track `last_audio_time`
   - If silence > `silence_timeout_ms` (default 800ms), finalize utterance
3. **STT Streaming**: Uses `singleUtterance=False` for continuous recognition
4. **Finalization**: Send empty audio content to STT to finalize current utterance

## Backpressure Handling

- **Max Queue Size**: 100 frames (~2 seconds at 20ms/frame)
- **Strategy**: Drop oldest frames if queue is full
- **Monitoring**: Track `dropped_frames` counter

## Tuning Parameters

### SessionState
- `silence_timeout_ms`: 800ms (configurable)
- `max_queue_size`: 100 frames
- `sample_rate`: 16000 Hz (STT), 24000 Hz (TTS)

### STT Streaming
- `enable_interim_results`: True (for low latency)
- `model`: "latest_long" (better for longer utterances)
- `single_utterance`: False (continuous recognition)

### TTS Streaming
- `audio_encoding`: LINEAR16 (PCM16)
- `sample_rate_hertz`: 24000
- `chunk_size`: 4800 samples (~200ms)

## Error Handling

- All async tasks wrapped in try/except
- Cancellation handled gracefully
- STT stream errors logged and recovered
- WebSocket disconnects trigger cleanup
- Error messages sent to client via `ERROR` message type

## Resource Cleanup

On WebSocket disconnect:
1. Cancel all async tasks (STT, LLM, TTS)
2. Close STT stream
3. Clear audio queue
4. Remove session from storage
5. Set cancellation events

## Backward Compatibility

The server supports both:
- **Binary protocol** (preferred, production)
- **Text JSON messages** (legacy, for testing)

Text messages are automatically converted to binary protocol internally.
