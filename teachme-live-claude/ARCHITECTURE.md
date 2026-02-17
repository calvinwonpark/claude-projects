# Production-Grade Realtime Voice Tutoring Architecture

## Overview

This is a refactored, production-grade implementation of a realtime voice tutoring application with low-latency audio streaming, advanced VAD, barge-in support, and modular architecture.

## Architecture Components

### 1. Audio Capture Module (`audio-worklet-processor.js` + `realtime.js`)

**Technology**: AudioWorklet (with ScriptProcessor fallback)

**Features**:
- Low-latency PCM16 capture at 16kHz
- Ring buffer for efficient audio processing
- Automatic fallback to ScriptProcessor if AudioWorklet unavailable
- Continuous frame streaming (20ms frames)

**Key Classes**:
- `PCMAudioProcessor`: AudioWorklet processor for real-time PCM conversion
- `AudioCapture`: Main capture module with fallback support

### 2. VAD & Endpointing Module (`vad-endpointing.js`)

**Technology**: Energy-based VAD + Zero Crossing Rate (ZCR)

**Features**:
- Adaptive noise floor estimation
- Short-time energy calculation
- Zero Crossing Rate for better speech detection
- Configurable thresholds and silence duration
- Speech start/end event emission

**Key Class**:
- `VADEndpointing`: Handles voice activity detection and endpointing

**Parameters**:
- Energy threshold: 0.01 (default)
- Silence threshold: 0.005 (default)
- Silence duration: 800ms (default)
- ZCR threshold: 0.1 (default)

### 3. WebSocket Transport Module (`websocket-transport.js`)

**Technology**: Binary WebSocket protocol

**Features**:
- Binary message encoding (no base64 overhead)
- Compact protocol: 1 byte type + 4 bytes length + payload
- Automatic reconnection with exponential backoff
- Message type constants for type safety

**Key Class**:
- `WebSocketTransport`: Handles all WebSocket communication

**Protocol**:
- Client messages: 0x01-0x08 (audio, control)
- Server messages: 0x10-0x18 (responses, errors)

### 4. Audio Playback Module (`audio-playback.js`)

**Technology**: Web Audio API with scheduled playback

**Features**:
- Jitter buffering for smooth playback
- Streaming chunked audio (no blob URLs)
- Barge-in support (immediate stop)
- Volume control
- Proper resource cleanup

**Key Class**:
- `AudioPlayback`: Handles TTS audio playback

**Parameters**:
- Jitter buffer: 100ms (default)
- Minimum buffer: 50ms (default)
- Sample rate: 24kHz (TTS standard)

### 5. Main Application (`realtime.js`)

**Architecture**: Modular, event-driven

**Features**:
- Clean separation of concerns
- State management (idle, listening, thinking, speaking)
- UI bindings
- Session management
- Image upload support
- Translator mode toggle
- Tutor notes generation

## Data Flow

```
User Speech
    ↓
AudioWorklet (PCM16 @ 16kHz)
    ↓
VAD Module (detects speech/silence)
    ↓
WebSocket Transport (binary frames)
    ↓
Server: Google Cloud STT (streaming)
    ↓
Interim/Final Transcripts
    ↓
Gemini 1.5 Flash (response generation)
    ↓
Google Cloud TTS (audio synthesis)
    ↓
Audio Playback Module (streaming)
    ↓
User hears response
```

## Key Features

### 1. Low Latency
- **20ms audio frames**: Minimal buffering
- **Binary protocol**: 50% smaller than base64
- **Streaming STT**: Interim results in <500ms
- **Chunked TTS**: First audio in <500ms

### 2. Barge-in Support
- User can interrupt AI while speaking
- Immediate playback stop
- Server cancels ongoing TTS/Gemini
- Seamless transition to new user input

### 3. Advanced VAD
- Energy + ZCR for accurate detection
- Adaptive noise floor
- Configurable thresholds
- Prevents false positives/negatives

### 4. UX Improvements
- **Interim transcripts**: Real-time feedback
- **State indicators**: Visual feedback (listening, thinking, speaking)
- **Smooth playback**: Jitter buffering prevents stuttering
- **Error handling**: Graceful degradation

### 5. Production Features
- **Resource cleanup**: Proper AudioContext/WebSocket cleanup
- **Reconnection logic**: Automatic retry with backoff
- **Error recovery**: Handles network/API failures
- **Modular design**: Easy to test and maintain

## File Structure

```
static/
├── audio-worklet-processor.js  # AudioWorklet processor
├── vad-endpointing.js          # VAD module
├── websocket-transport.js      # Binary WebSocket transport
├── audio-playback.js           # Streaming playback
├── realtime.js                 # Main application
└── index.html                  # UI

SERVER_SPEC.md                  # Server protocol specification
TUNING_GUIDE.md                 # Performance tuning guide
ARCHITECTURE.md                 # This file
```

## Browser Compatibility

### AudioWorklet Support
- Chrome/Edge: ✅ (v66+)
- Firefox: ✅ (v76+)
- Safari: ✅ (v14.1+)

### Fallback (ScriptProcessor)
- All modern browsers: ✅
- Automatically used if AudioWorklet unavailable

## Performance Targets

- **End-to-end latency**: < 2 seconds
- **STT latency**: < 500ms (interim), < 1s (final)
- **TTS latency**: < 500ms (first chunk)
- **Frame drop rate**: < 1%
- **VAD accuracy**: > 95%

## Next Steps for Production

1. **Add metrics/analytics**: Track latency, errors, usage
2. **Implement adaptive tuning**: Auto-adjust VAD based on environment
3. **Add audio quality monitoring**: Detect microphone issues
4. **Implement rate limiting**: Prevent abuse
5. **Add authentication**: Secure WebSocket connections
6. **Scale horizontally**: Use Redis for session storage
7. **Add monitoring**: Prometheus/Grafana for observability
8. **Implement A/B testing**: Test different VAD parameters

## Testing

### Manual Testing Checklist
- [ ] AudioWorklet loads correctly
- [ ] Fallback to ScriptProcessor works
- [ ] VAD detects speech accurately
- [ ] Interim transcripts appear
- [ ] Final transcripts are accurate
- [ ] TTS playback is smooth
- [ ] Barge-in stops playback immediately
- [ ] Reconnection works after disconnect
- [ ] Image upload works
- [ ] Translator mode works
- [ ] Tutor notes generation works

### Performance Testing
- Measure end-to-end latency
- Test with different network conditions
- Test with different microphones
- Test in noisy/quiet environments
- Load test with multiple concurrent sessions
