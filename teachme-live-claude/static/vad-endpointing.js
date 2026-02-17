// vad-endpointing.js
// Voice Activity Detection and Endpointing module

class VADEndpointing {
  constructor(options = {}) {
    this.sampleRate = options.sampleRate || 16000;
    this.frameSize = options.frameSize || 320; // ~20ms at 16kHz
    this.energyThreshold = options.energyThreshold || 0.01;
    this.silenceThreshold = options.silenceThreshold || 0.005;
    this.silenceDuration = options.silenceDuration || 800; // ms
    this.speechStartDuration = options.speechStartDuration || 100; // ms
    
    // Adaptive noise floor
    this.noiseFloor = 0.001;
    this.noiseFloorAlpha = 0.95; // Smoothing factor
    this.adaptationFrames = 0;
    this.maxAdaptationFrames = 50; // ~1 second
    
    // Zero Crossing Rate (ZCR) for better VAD
    this.zcrThreshold = 0.1;
    
    // State
    this.isSpeechActive = false;
    this.silenceStartTime = null;
    this.speechStartTime = null;
    this.consecutiveSpeechFrames = 0;
    this.consecutiveSilenceFrames = 0;
    
    // Callbacks
    this.onSpeechStart = options.onSpeechStart || (() => {});
    this.onSpeechEnd = options.onSpeechEnd || (() => {});
    this.onFrame = options.onFrame || (() => {});
  }
  
  // Calculate short-time energy
  calculateEnergy(samples) {
    let sum = 0;
    for (let i = 0; i < samples.length; i++) {
      sum += Math.abs(samples[i]);
    }
    return sum / samples.length;
  }
  
  // Calculate Zero Crossing Rate
  calculateZCR(samples) {
    let crossings = 0;
    for (let i = 1; i < samples.length; i++) {
      if ((samples[i] >= 0 && samples[i - 1] < 0) || 
          (samples[i] < 0 && samples[i - 1] >= 0)) {
        crossings++;
      }
    }
    return crossings / samples.length;
  }
  
  // Normalize Int16 samples to Float32 [-1, 1]
  normalizeSamples(int16Samples) {
    const floatSamples = new Float32Array(int16Samples.length);
    for (let i = 0; i < int16Samples.length; i++) {
      floatSamples[i] = int16Samples[i] / 32768.0;
    }
    return floatSamples;
  }
  
  processFrame(int16Samples) {
    const normalized = this.normalizeSamples(int16Samples);
    const energy = this.calculateEnergy(normalized);
    const zcr = this.calculateZCR(normalized);
    
    // Adapt noise floor during initial frames
    if (this.adaptationFrames < this.maxAdaptationFrames) {
      this.noiseFloor = this.noiseFloorAlpha * this.noiseFloor + 
                       (1 - this.noiseFloorAlpha) * energy;
      this.adaptationFrames++;
    }
    
    // Adaptive thresholds based on noise floor
    const adaptiveEnergyThreshold = Math.max(
      this.energyThreshold,
      this.noiseFloor * 3
    );
    const adaptiveSilenceThreshold = Math.max(
      this.silenceThreshold,
      this.noiseFloor * 1.5
    );
    
    // VAD decision: speech if energy is high OR (energy is moderate AND ZCR is high)
    const hasEnergy = energy > adaptiveEnergyThreshold;
    const hasModerateEnergy = energy > adaptiveSilenceThreshold;
    const hasHighZCR = zcr > this.zcrThreshold;
    const isSpeech = hasEnergy || (hasModerateEnergy && hasHighZCR);
    
    const now = Date.now();
    
    if (isSpeech) {
      this.consecutiveSpeechFrames++;
      this.consecutiveSilenceFrames = 0;
      
      if (!this.isSpeechActive) {
        // Need consecutive speech frames to confirm start
        if (this.consecutiveSpeechFrames >= 3) { // ~60ms
          this.isSpeechActive = true;
          this.speechStartTime = now;
          this.silenceStartTime = null;
          this.onSpeechStart();
        }
      }
    } else {
      this.consecutiveSilenceFrames++;
      this.consecutiveSpeechFrames = 0;
      
      if (this.isSpeechActive) {
        if (this.silenceStartTime === null) {
          this.silenceStartTime = now;
        }
        
        const silenceDuration = now - this.silenceStartTime;
        if (silenceDuration >= this.silenceDuration) {
          this.isSpeechActive = false;
          this.silenceStartTime = null;
          this.onSpeechEnd();
        }
      }
    }
    
    // Always call onFrame, but mark if it's speech or silence
    this.onFrame({
      samples: int16Samples,
      isSpeech: this.isSpeechActive,
      energy: energy,
      zcr: zcr,
      timestamp: now
    });
    
    return {
      isSpeech: this.isSpeechActive,
      energy: energy,
      zcr: zcr
    };
  }
  
  reset() {
    this.isSpeechActive = false;
    this.silenceStartTime = null;
    this.speechStartTime = null;
    this.consecutiveSpeechFrames = 0;
    this.consecutiveSilenceFrames = 0;
    this.adaptationFrames = 0;
    this.noiseFloor = 0.001;
  }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = VADEndpointing;
}
