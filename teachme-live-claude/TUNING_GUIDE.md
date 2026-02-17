# Tuning Guide for Production Realtime Voice Tutoring

## Audio Capture Parameters

### Frame Size
- **Current**: 320 samples (~20ms at 16kHz)
- **Range**: 160-640 samples (10-40ms)
- **Trade-off**: 
  - Smaller frames = lower latency but more overhead
  - Larger frames = less overhead but higher latency
- **Recommendation**: 320 samples for balanced performance

### Sample Rate
- **Current**: 16000 Hz
- **Options**: 8000, 16000, 24000, 48000 Hz
- **Trade-off**:
  - Lower = less bandwidth, lower quality
  - Higher = better quality, more bandwidth
- **Recommendation**: 16000 Hz for speech recognition (optimal for STT)

## VAD (Voice Activity Detection) Parameters

### Energy Threshold
- **Current**: 0.01
- **Range**: 0.005 - 0.05
- **Tuning**:
  - Increase if too sensitive (detects noise as speech)
  - Decrease if not detecting quiet speech
- **Environment-specific**:
  - Quiet room: 0.005 - 0.01
  - Noisy room: 0.02 - 0.05
  - Use adaptive threshold based on noise floor

### Silence Threshold
- **Current**: 0.005
- **Range**: 0.002 - 0.01
- **Tuning**:
  - Should be lower than energy threshold
  - Prevents false speech detection during silence

### Silence Duration
- **Current**: 800ms
- **Range**: 500 - 1500ms
- **Tuning**:
  - Shorter = faster response but may cut off slow speakers
  - Longer = more natural pauses but slower response
- **Recommendation**: 
  - Fast-paced: 600-700ms
  - Normal: 800-1000ms
  - Slow/thoughtful: 1200-1500ms

### Speech Start Duration
- **Current**: 100ms
- **Range**: 50 - 200ms
- **Tuning**:
  - Prevents false starts from brief noise
  - Shorter = more responsive
  - Longer = more stable

### Zero Crossing Rate (ZCR) Threshold
- **Current**: 0.1
- **Range**: 0.05 - 0.2
- **Tuning**:
  - Higher = more selective (only clear speech)
  - Lower = more permissive (includes unclear speech)
- **Use**: Combined with energy for better VAD accuracy

## Playback Parameters

### Jitter Buffer
- **Current**: 100ms
- **Range**: 50 - 200ms
- **Tuning**:
  - Shorter = lower latency but risk of stuttering
  - Longer = smoother playback but higher latency
- **Network-dependent**:
  - Stable network: 50-100ms
  - Unstable network: 150-200ms

### Minimum Buffer
- **Current**: 50ms
- **Range**: 30 - 100ms
- **Tuning**:
  - Minimum audio to buffer before starting playback
  - Prevents initial stuttering

### TTS Chunk Size
- **Current**: 4800 samples (~200ms at 24kHz)
- **Range**: 2400 - 9600 samples (100-400ms)
- **Tuning**:
  - Smaller = lower latency but more overhead
  - Larger = less overhead but higher latency

## Network Optimization

### WebSocket Frame Size
- **Audio frames**: ~640 bytes (320 samples * 2 bytes)
- **Control messages**: < 100 bytes typically
- **Recommendation**: Keep frames small for low latency

### Binary vs Base64
- **Binary**: 50% smaller, faster encoding/decoding
- **Base64**: Easier debugging, but 33% overhead
- **Current**: Binary (production-grade)

## Performance Monitoring

### Key Metrics to Track
1. **End-to-end latency**: User speaks → AI responds
   - Target: < 2 seconds
   - Components: STT + Gemini + TTS + network
2. **STT latency**: Audio → transcript
   - Target: < 500ms for interim, < 1s for final
3. **TTS latency**: Text → audio
   - Target: < 500ms for first chunk
4. **Frame drop rate**: Audio frames lost
   - Target: < 1%
5. **VAD accuracy**: False positives/negatives
   - Target: < 5% error rate

### Debugging Tips
1. **High latency**: Check network, increase frame size, reduce jitter buffer
2. **Stuttering playback**: Increase jitter buffer, check TTS chunk size
3. **Missed speech**: Lower VAD thresholds, increase speech start duration
4. **False speech detection**: Increase VAD thresholds, improve noise floor adaptation
5. **Audio quality issues**: Check sample rate, encoding format

## Environment-Specific Tuning

### Quiet Office
```javascript
VAD: {
  energyThreshold: 0.005,
  silenceThreshold: 0.002,
  silenceDuration: 700
}
```

### Noisy Environment
```javascript
VAD: {
  energyThreshold: 0.03,
  silenceThreshold: 0.015,
  silenceDuration: 1000
}
```

### Mobile/Headset
```javascript
VAD: {
  energyThreshold: 0.008,
  silenceThreshold: 0.004,
  silenceDuration: 600
}
```

## Adaptive Tuning

Consider implementing:
1. **Noise floor adaptation**: Automatically adjust thresholds based on background noise
2. **Speaker-specific tuning**: Learn user's speech patterns
3. **Network-aware buffering**: Adjust jitter buffer based on network conditions
4. **Dynamic frame sizing**: Adjust based on CPU/network load
