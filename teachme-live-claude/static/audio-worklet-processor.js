// audio-worklet-processor.js
// AudioWorklet processor for low-latency PCM audio capture

class PCMAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.bufferSize = 4096; // ~256ms at 16kHz
    this.ringBuffer = new Int16Array(this.bufferSize);
    this.writeIndex = 0;
    this.readIndex = 0;
    this.sampleCount = 0;
    
    this.port.onmessage = (event) => {
      if (event.data.command === 'getSamples') {
        const requestedFrames = event.data.frames || 320; // ~20ms at 16kHz
        const available = this.getAvailableSamples();
        const framesToSend = Math.min(requestedFrames, available);
        
        if (framesToSend > 0) {
          const samples = this.readSamples(framesToSend);
          this.port.postMessage({
            type: 'audioFrame',
            samples: samples,
            frameCount: framesToSend
          });
        }
      } else if (event.data.command === 'reset') {
        this.writeIndex = 0;
        this.readIndex = 0;
        this.sampleCount = 0;
      }
    };
  }
  
  getAvailableSamples() {
    if (this.writeIndex >= this.readIndex) {
      return this.writeIndex - this.readIndex;
    } else {
      return (this.bufferSize - this.readIndex) + this.writeIndex;
    }
  }
  
  readSamples(count) {
    const samples = new Int16Array(count);
    let readPos = 0;
    
    while (readPos < count && this.getAvailableSamples() > 0) {
      samples[readPos] = this.ringBuffer[this.readIndex];
      this.readIndex = (this.readIndex + 1) % this.bufferSize;
      readPos++;
    }
    
    return samples;
  }
  
  process(inputs, outputs, parameters) {
    const input = inputs[0];
    if (input.length > 0) {
      const inputChannel = input[0];
      
      // Convert Float32 to Int16 PCM and write to ring buffer
      for (let i = 0; i < inputChannel.length; i++) {
        const sample = Math.max(-1, Math.min(1, inputChannel[i]));
        const int16Sample = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
        
        // Check if buffer is full (overwrite old data if needed)
        const nextWrite = (this.writeIndex + 1) % this.bufferSize;
        if (nextWrite === this.readIndex && this.getAvailableSamples() > 0) {
          // Buffer full, advance read index (drop oldest)
          this.readIndex = (this.readIndex + 1) % this.bufferSize;
        }
        
        this.ringBuffer[this.writeIndex] = int16Sample;
        this.writeIndex = nextWrite;
        this.sampleCount++;
      }
    }
    
    return true; // Keep processor alive
  }
}

registerProcessor('pcm-audio-processor', PCMAudioProcessor);
