// audio-playback.js
// Streaming audio playback with jitter buffering

class AudioPlayback {
  constructor(options = {}) {
    this.sampleRate = options.sampleRate || 24000; // TTS typically uses 24kHz
    this.bufferSize = options.bufferSize || 4096;
    this.jitterBufferMs = options.jitterBufferMs || 100; // 100ms jitter buffer
    this.minBufferMs = options.minBufferMs || 50; // Start playing after 50ms buffered
    
    this.audioContext = null;
    this.sourceNode = null;
    this.gainNode = null;
    this.isPlaying = false;
    this.isPaused = false;
    this.playbackQueue = [];
    this.scheduledTime = 0;
    this.bufferDuration = 0;
    
    this.onPlaybackStart = options.onPlaybackStart || (() => {});
    this.onPlaybackEnd = options.onPlaybackEnd || (() => {});
    this.onPlaybackStop = options.onPlaybackStop || (() => {});
    this.activeSources = new Set();
  }
  
  async initialize() {
    try {
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: this.sampleRate
      });
      
      this.gainNode = this.audioContext.createGain();
      this.gainNode.connect(this.audioContext.destination);
      this.gainNode.gain.value = 1.0;
      
      return true;
    } catch (error) {
      console.error('Failed to initialize AudioContext:', error);
      return false;
    }
  }
  
  // Decode and schedule audio chunk for playback
  async addAudioChunk(audioData) {
    if (!this.audioContext) {
      const initialized = await this.initialize();
      if (!initialized) {
        console.error('Failed to initialize audio playback');
        return;
      }
    }
    
    try {
      // audioData is ArrayBuffer (PCM16 LINEAR16 from TTS)
      // TTS returns LINEAR16 PCM at 24kHz
      const audioBuffer = await this._decodePCM16(audioData);
      
      if (!audioBuffer) {
        console.error('Failed to decode audio chunk');
        return;
      }
      
      const duration = audioBuffer.duration;
      this.bufferDuration += duration;
      
      // Add to queue
      this.playbackQueue.push({
        buffer: audioBuffer,
        duration: duration,
        timestamp: this.audioContext.currentTime
      });
      
      // Start playback if we have enough buffered
      if (!this.isPlaying && this.bufferDuration >= this.minBufferMs / 1000) {
        this._startPlayback();
      }
      
      // Continue scheduling if already playing
      if (this.isPlaying) {
        this._scheduleNextChunk();
      }
    } catch (error) {
      console.error('Error adding audio chunk:', error);
    }
  }
  
  async _decodePCM16(pcmData) {
    // Convert Int16 PCM to AudioBuffer
    const int16Array = new Int16Array(pcmData);
    const float32Array = new Float32Array(int16Array.length);
    
    for (let i = 0; i < int16Array.length; i++) {
      float32Array[i] = int16Array[i] / 32768.0;
    }
    
    const audioBuffer = this.audioContext.createBuffer(
      1, // mono
      float32Array.length,
      this.sampleRate
    );
    
    audioBuffer.getChannelData(0).set(float32Array);
    return audioBuffer;
  }
  
  _startPlayback() {
    if (this.isPlaying || this.playbackQueue.length === 0) {
      return;
    }
    
    this.isPlaying = true;
    this.scheduledTime = this.audioContext.currentTime + (this.jitterBufferMs / 1000);
    this.onPlaybackStart();
    this._scheduleNextChunk();
  }
  
  _scheduleNextChunk() {
    if (this.playbackQueue.length === 0) {
      // Check if we should stop
      if (this.bufferDuration <= 0.1) { // Less than 100ms left
        this._stopPlayback();
      }
      return;
    }
    
    const chunk = this.playbackQueue.shift();
    const source = this.audioContext.createBufferSource();
    source.buffer = chunk.buffer;
    source.connect(this.gainNode);
    this.activeSources.add(source);
    this.sourceNode = source;
    
    source.onended = () => {
      this.activeSources.delete(source);
      if (this.sourceNode === source) {
        this.sourceNode = null;
      }
      this.bufferDuration -= chunk.duration;
      this._scheduleNextChunk();
    };
    
    source.start(this.scheduledTime);
    this.scheduledTime += chunk.duration;
  }
  
  _stopPlayback() {
    if (!this.isPlaying) return;
    
    this.isPlaying = false;
    this.playbackQueue = [];
    this.bufferDuration = 0;
    this.scheduledTime = 0;
    
    // Stop every scheduled/active source immediately to guarantee barge-in.
    for (const source of this.activeSources) {
      try {
        source.onended = null;
        source.stop();
      } catch (e) {
        // Source may already be stopped.
      }
    }
    this.activeSources.clear();
    this.sourceNode = null;
    
    this.onPlaybackEnd();
  }
  
  stop() {
    this._stopPlayback();
    this.onPlaybackStop();
  }
  
  // Barge-in: immediately stop playback
  bargeIn() {
    this.stop();
  }
  
  setVolume(volume) {
    if (this.gainNode) {
      this.gainNode.gain.value = Math.max(0, Math.min(1, volume));
    }
  }
  
  cleanup() {
    this.stop();
    if (this.audioContext) {
      this.audioContext.close().catch(e => console.error('Error closing AudioContext:', e));
      this.audioContext = null;
    }
  }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = AudioPlayback;
}
