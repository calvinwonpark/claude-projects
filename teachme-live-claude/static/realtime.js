// realtime.js - Production-grade realtime voice tutoring app
// Modular architecture with AudioWorklet, VAD, binary WebSocket, and streaming playback

// ============================================================================
// UI Elements
// ============================================================================
const logEl = document.getElementById("log");
const startBtn = document.getElementById("startBtn");
const stopBtn = document.getElementById("stopBtn");
const statusEl = document.getElementById("status");
const statusIndicator = document.getElementById("statusIndicator");
const transcriptEl = document.getElementById("transcript") || document.createElement("div");
const interimTranscriptEl = document.getElementById("interimTranscript") || document.createElement("div");
const imageInput = document.getElementById("imageInput");
const imageStatus = document.getElementById("imageStatus");
const uploadArea = document.getElementById("uploadArea");
const translatorToggle = document.getElementById("translatorToggle");
const notesEl = document.getElementById("tutorNotes");
const updateNotesBtn = document.getElementById("updateNotesBtn");

// ============================================================================
// Configuration
// ============================================================================
const CONFIG = {
  SAMPLE_RATE: 16000,
  FRAME_SIZE: 320, // ~20ms at 16kHz
  VAD: {
    ENERGY_THRESHOLD: 0.01,
    SILENCE_THRESHOLD: 0.005,
    SILENCE_DURATION: 1400, // ms - reduce premature endpointing on brief pauses ("what's 2 + 2")
    SPEECH_START_DURATION: 100, // ms
    TRAILING_SEND_MS: 1200 // keep sending tail through short pauses (e.g., "3 plus 2 ... times 6")
  },
  PLAYBACK: {
    SAMPLE_RATE: 24000, // TTS sample rate
    JITTER_BUFFER_MS: 100,
    MIN_BUFFER_MS: 50
  }
};

// ============================================================================
// State
// ============================================================================
let sessionId = null;
let isSessionActive = false;
let audioCapture = null;
let vad = null;
let transport = null;
let playback = null;
let audioContext = null;
let workletNode = null;
let mediaStream = null;
let uploadedImageUrl = null;
let imageSentForSession = false;
let currentState = 'idle'; // idle, listening, thinking, speaking
let currentModelDelta = '';
let allowAssistantAudio = true;
let currentAssistantTurnId = null;

// ============================================================================
// Utility Functions
// ============================================================================
function log(msg) {
  console.log(msg);
  if (logEl) {
    logEl.textContent += msg + "\n";
    logEl.scrollTop = logEl.scrollHeight;
  }
}

function setStatus(text, state = null) {
  if (statusEl) {
    statusEl.textContent = "Status: " + text;
  }
  
  if (state) {
    currentState = state;
  }
  
  if (statusIndicator) {
    statusIndicator.className = "status-indicator";
    const statusLower = text.toLowerCase();
    if (statusLower.includes("connected") || statusLower.includes("listening")) {
      statusIndicator.classList.add("connected");
    } else if (statusLower.includes("connecting") || statusLower.includes("starting") || statusLower.includes("thinking")) {
      statusIndicator.classList.add("connecting");
    } else if (statusLower.includes("speaking")) {
      statusIndicator.classList.add("speaking");
    } else if (statusLower.includes("error") || statusLower.includes("failed")) {
      statusIndicator.classList.add("error");
    }
  }
}

function updateTranscript(text, isInterim = false) {
  if (isInterim) {
    if (interimTranscriptEl) {
      interimTranscriptEl.textContent = text;
      interimTranscriptEl.style.opacity = '0.6';
    }
  } else {
    if (transcriptEl) {
      transcriptEl.textContent = text;
    }
    if (interimTranscriptEl) {
      interimTranscriptEl.textContent = '';
    }
  }
}

function getTargetLanguage() {
  const checked = document.querySelector('input[name="lang"]:checked');
  return checked ? checked.value : "en";
}

function isTranslatorMode() {
  return translatorToggle ? translatorToggle.checked : false;
}

function parseTutorNotes(raw) {
  if (!raw) return null;
  let value = raw;
  if (typeof value === 'string') {
    try {
      value = JSON.parse(value);
    } catch (e) {
      return null;
    }
  }
  if (value && typeof value === 'object' && typeof value.text === 'string') {
    try {
      return JSON.parse(value.text);
    } catch (e) {
      return null;
    }
  }
  if (value && typeof value === 'object' && typeof value.answer === 'string') {
    return value;
  }
  return null;
}

function formatTutorNotes(raw) {
  const parsed = parseTutorNotes(raw);
  if (!parsed) {
    return typeof raw === 'string' ? raw : JSON.stringify(raw || {}, null, 2);
  }
  const asList = (items) => Array.isArray(items) ? items.filter(Boolean) : [];
  const lines = [];
  if (parsed.answer) {
    lines.push("Answer");
    lines.push(parsed.answer);
    lines.push("");
  }
  const sections = [
    ["Steps", asList(parsed.steps)],
    ["Examples", asList(parsed.examples)],
    ["Common Mistakes", asList(parsed.common_mistakes)],
    ["Next Exercises", asList(parsed.next_exercises)],
  ];
  for (const [title, items] of sections) {
    if (!items.length) continue;
    lines.push(title);
    for (let i = 0; i < items.length; i++) {
      lines.push(`${i + 1}. ${items[i]}`);
    }
    lines.push("");
  }
  return lines.join("\n").trim();
}

// ============================================================================
// Audio Capture Module
// ============================================================================
class AudioCapture {
  constructor(sampleRate, frameSize) {
    this.sampleRate = sampleRate;
    this.frameSize = frameSize;
    this.audioContext = null;
    this.workletNode = null;
    this.mediaStream = null;
    this.isCapturing = false;
    this.onFrame = null;
  }
  
  async initialize() {
    try {
      // Request microphone access
      this.mediaStream = await navigator.mediaDevices.getUserMedia({
        audio: {
          sampleRate: this.sampleRate,
          channelCount: 1,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true
        }
      });
      
      // Create AudioContext
      this.audioContext = new (window.AudioContext || window.webkitAudioContext)({
        sampleRate: this.sampleRate
      });
      
      // Load and create AudioWorklet
      try {
        await this.audioContext.audioWorklet.addModule('/static/audio-worklet-processor.js');
        this.workletNode = new AudioWorkletNode(this.audioContext, 'pcm-audio-processor');
        
        this.workletNode.port.onmessage = (event) => {
          if (event.data.type === 'audioFrame' && this.onFrame) {
            this.onFrame(event.data.samples, event.data.frameCount);
          }
        };
        
        // Connect audio pipeline
        const source = this.audioContext.createMediaStreamSource(this.mediaStream);
        source.connect(this.workletNode);
        
        log("✅ AudioWorklet initialized");
        return true;
      } catch (workletError) {
        console.warn('AudioWorklet not supported, falling back to ScriptProcessor:', workletError);
        return this._fallbackToScriptProcessor();
      }
    } catch (error) {
      console.error('Failed to initialize audio capture:', error);
      throw error;
    }
  }
  
  _fallbackToScriptProcessor() {
    try {
      const source = this.audioContext.createMediaStreamSource(this.mediaStream);
      const processor = this.audioContext.createScriptProcessor(4096, 1, 1);
      
      processor.onaudioprocess = (e) => {
        if (!this.isCapturing) return;
        
        const inputData = e.inputBuffer.getChannelData(0);
        const pcmData = new Int16Array(inputData.length);
        
        for (let i = 0; i < inputData.length; i++) {
          const s = Math.max(-1, Math.min(1, inputData[i]));
          pcmData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
        }
        
        if (this.onFrame) {
          this.onFrame(pcmData, pcmData.length);
        }
      };
      
      source.connect(processor);
      processor.connect(this.audioContext.destination);
      this.processor = processor;
      
      log("⚠️ Using ScriptProcessor fallback (AudioWorklet not available)");
      return true;
    } catch (error) {
      console.error('ScriptProcessor fallback failed:', error);
      return false;
    }
  }
  
  start() {
    if (!this.audioContext || !this.workletNode) {
      return false;
    }
    
    this.isCapturing = true;
    
    // Request frames from worklet continuously
    this.frameRequestInterval = setInterval(() => {
      if (this.isCapturing && this.workletNode) {
        this.workletNode.port.postMessage({ command: 'getSamples', frames: this.frameSize });
      }
    }, 20); // Request every 20ms
    return true;
  }
  
  stop() {
    this.isCapturing = false;
    
    if (this.frameRequestInterval) {
      clearInterval(this.frameRequestInterval);
      this.frameRequestInterval = null;
    }
    
    if (this.processor) {
      this.processor.disconnect();
      this.processor = null;
    }
    
    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    
    if (this.mediaStream) {
      this.mediaStream.getTracks().forEach(track => track.stop());
      this.mediaStream = null;
    }
    
    if (this.audioContext) {
      this.audioContext.close().catch(e => console.error('Error closing AudioContext:', e));
      this.audioContext = null;
    }
  }
}

// ============================================================================
// Main Session Management
// ============================================================================
async function startSession() {
  if (isSessionActive) {
    log("⚠️ Session already active");
    return;
  }
  
  setStatus("starting…", "connecting");
  log("Starting session…");
  
  try {
    // Generate session ID
    sessionId = "session_" + Date.now() + "_" + Math.random().toString(36).substr(2, 9);
    
    // Initialize audio capture
    audioCapture = new AudioCapture(CONFIG.SAMPLE_RATE, CONFIG.FRAME_SIZE);
    await audioCapture.initialize();
    
    // Initialize VAD
    let lastSpeechTimestamp = 0;
    vad = new VADEndpointing({
      sampleRate: CONFIG.SAMPLE_RATE,
      frameSize: CONFIG.FRAME_SIZE,
      energyThreshold: CONFIG.VAD.ENERGY_THRESHOLD,
      silenceThreshold: CONFIG.VAD.SILENCE_THRESHOLD,
      silenceDuration: CONFIG.VAD.SILENCE_DURATION,
      speechStartDuration: CONFIG.VAD.SPEECH_START_DURATION,
      onSpeechStart: () => {
        log("🎤 Speech detected");
        setStatus("listening…", "listening");
        transport.sendSpeechStart();
        // Barge-in: stop assistant output if playback or generation is likely active.
        const hasPendingPlayback = playback && (
          playback.isPlaying ||
          playback.bufferDuration > 0 ||
          (playback.playbackQueue && playback.playbackQueue.length > 0)
        );
        const assistantLikelyActive =
          hasPendingPlayback ||
          currentState === 'speaking' ||
          currentState === 'thinking' ||
          (typeof currentModelDelta === 'string' && currentModelDelta.length > 0);

        if (assistantLikelyActive) {
          playback.bargeIn();
          transport.sendBargeIn();
          // Ignore stale server audio until the next model turn starts.
          allowAssistantAudio = false;
        }
      },
      onSpeechEnd: () => {
        log("👂 Speech ended");
        setStatus("processing…", "thinking");
        transport.sendSpeechEnd();
      },
      onFrame: (frameData) => {
        // Stream during speech and a short trailing window to avoid clipping final syllables.
        if (frameData.isSpeech) {
          lastSpeechTimestamp = frameData.timestamp;
          transport.sendAudioFrame(frameData.samples);
          return;
        }
        if (lastSpeechTimestamp > 0 && (frameData.timestamp - lastSpeechTimestamp) <= CONFIG.VAD.TRAILING_SEND_MS) {
          transport.sendAudioFrame(frameData.samples);
        }
      }
    });
    
    // Initialize WebSocket transport
    transport = new WebSocketTransport({
      onOpen: () => {
        log("✅ WebSocket connected");
        setStatus("connected", "listening");
      },
      onClose: () => {
        log("🔌 WebSocket closed");
        setStatus("disconnected", "idle");
      },
      onError: (error) => {
        log("❌ WebSocket error: " + error);
        setStatus("error", "idle");
      },
      onMessage: handleServerMessage
    });
    
    // Initialize audio playback
    playback = new AudioPlayback({
      sampleRate: CONFIG.PLAYBACK.SAMPLE_RATE,
      jitterBufferMs: CONFIG.PLAYBACK.JITTER_BUFFER_MS,
      minBufferMs: CONFIG.PLAYBACK.MIN_BUFFER_MS,
      onPlaybackStart: () => {
        setStatus("speaking…", "speaking");
      },
      onPlaybackEnd: () => {
        setStatus("listening…", "listening");
      },
      onPlaybackStop: () => {
        setStatus("listening…", "listening");
      }
    });
    await playback.initialize();

    // Read selected language/mode before opening WebSocket so INIT carries correct config.
    const targetLang = getTargetLanguage();
    const translatorMode = isTranslatorMode();
    
    // Connect WebSocket with selected language config so INIT is correct on first packet.
    transport.connect(sessionId, targetLang, translatorMode);
    
    // Start audio capture
    audioCapture.onFrame = (samples, frameCount) => {
      vad.processFrame(samples);
    };
    audioCapture.start();
    
    // Send initial config as a follow-up (safe if socket is open; INIT already has same values).
    transport.sendConfigUpdate(targetLang, translatorMode);
    
    // Image upload is sent after 'connected' ack to avoid pre-open drops.
    
    isSessionActive = true;
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = false;
    
    log("✅ Session started");
  } catch (error) {
    log("❌ Failed to start session: " + error.message);
    setStatus("error", "idle");
    stopSession();
  }
}

function stopSession() {
  if (!isSessionActive) return;
  
  setStatus("stopping…", "idle");
  log("Stopping session…");
  
  isSessionActive = false;
  imageSentForSession = false;
  
  // Cleanup modules
  if (audioCapture) {
    audioCapture.stop();
    audioCapture = null;
  }
  
  if (vad) {
    vad.reset();
    vad = null;
  }
  
  if (transport) {
    transport.close();
    transport = null;
  }
  
  if (playback) {
    playback.cleanup();
    playback = null;
  }
  
  if (startBtn) startBtn.disabled = false;
  if (stopBtn) stopBtn.disabled = true;
  
  setStatus("idle", "idle");
  log("🛑 Session stopped");
}

// ============================================================================
// Server Message Handling
// ============================================================================
function handleServerMessage(msg) {
  switch (msg.type) {
    case 'connected':
      log("✅ Session initialized: " + msg.session_id);
      // Send image after connection is confirmed to avoid dropping upload before WS is open.
      if (uploadedImageUrl && transport && !imageSentForSession) {
        transport.sendImageUpload(uploadedImageUrl);
      }
      break;
      
    case 'transcript_interim':
      updateTranscript(msg.text, true);
      log("👤 USER (interim): " + msg.text);
      break;
      
    case 'transcript_final':
      updateTranscript(msg.text, false);
      currentModelDelta = '';
      // Block audio until we observe next model delta for this user turn.
      allowAssistantAudio = false;
      log("👤 USER: " + msg.text);
      break;

    case 'llm_delta':
      if (typeof msg.turn_id === 'number' && msg.turn_id !== currentAssistantTurnId) {
        currentAssistantTurnId = msg.turn_id;
        // Flush any stale buffered playback before the new turn audio starts.
        if (playback) {
          playback.bargeIn();
        }
      }
      allowAssistantAudio = true;
      if (typeof msg.text === 'string' && msg.text.length > 0) {
        currentModelDelta += msg.text;
      }
      if (msg.final) {
        if (currentModelDelta.trim()) {
          log("🧠 MODEL: " + currentModelDelta.trim());
        }
        currentModelDelta = '';
      }
      break;
      
    case 'audio_chunk':
      // Stream audio chunk for playback
      if (playback && allowAssistantAudio) {
        playback.addAudioChunk(msg.data);
      }
      break;
      
    case 'audio_complete':
      // Audio response complete
      setStatus("listening…", "listening");
      break;
      
    case 'error':
      log("❌ Server error: " + msg.message);
      setStatus("error", "idle");
      break;
      
    case 'notes':
      if (notesEl) {
        notesEl.textContent = formatTutorNotes(msg.text);
      }
      log("📝 Tutor notes received");
      break;
      
    case 'image_received':
      imageSentForSession = true;
      log("📷 Image received by server");
      break;
      
    case 'config_updated':
      log("⚙️ Config updated");
      break;
  }
}

// ============================================================================
// UI Event Handlers
// ============================================================================
if (startBtn) {
  startBtn.addEventListener("click", startSession);
}

if (stopBtn) {
  stopBtn.addEventListener("click", stopSession);
  stopBtn.disabled = true;
}

if (translatorToggle) {
  translatorToggle.addEventListener("change", () => {
    if (transport && isSessionActive) {
      const targetLang = getTargetLanguage();
      const translatorMode = isTranslatorMode();
      transport.sendConfigUpdate(targetLang, translatorMode);
    }
  });
}

// Keep backend config synced when answer language radio changes during an active session.
document.querySelectorAll('input[name="lang"]').forEach((radio) => {
  radio.addEventListener("change", () => {
    if (transport && isSessionActive) {
      const targetLang = getTargetLanguage();
      const translatorMode = isTranslatorMode();
      transport.sendConfigUpdate(targetLang, translatorMode);
    }
  });
});

if (updateNotesBtn) {
  updateNotesBtn.addEventListener("click", () => {
    if (transport && isSessionActive) {
      transport.sendRequestNotes();
      log("📑 Requested tutor notes");
    } else {
      log("⚠️ Cannot request notes: session not active");
    }
  });
}

// Image upload handling
if (imageInput) {
  imageInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file && file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (event) => {
        uploadedImageUrl = event.target.result;
        imageSentForSession = false;
        if (imageStatus) {
          imageStatus.textContent = "Image loaded: " + file.name;
        }
        if (transport && isSessionActive) {
          transport.sendImageUpload(uploadedImageUrl);
        }
        log("📷 Image loaded: " + file.name);
      };
      reader.readAsDataURL(file);
    }
  });
}

if (uploadArea) {
  uploadArea.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadArea.style.backgroundColor = "#f0f0f0";
  });
  
  uploadArea.addEventListener("dragleave", () => {
    uploadArea.style.backgroundColor = "";
  });
  
  uploadArea.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadArea.style.backgroundColor = "";
    const file = e.dataTransfer.files[0];
    if (file && file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (event) => {
        uploadedImageUrl = event.target.result;
        imageSentForSession = false;
        if (imageStatus) {
          imageStatus.textContent = "Image loaded: " + file.name;
        }
        if (transport && isSessionActive) {
          transport.sendImageUpload(uploadedImageUrl);
        }
        log("📷 Image loaded: " + file.name);
      };
      reader.readAsDataURL(file);
    }
  });
}

// Cleanup on page unload
window.addEventListener("beforeunload", () => {
  stopSession();
});
