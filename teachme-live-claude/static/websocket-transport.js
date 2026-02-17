// websocket-transport.js
// Binary WebSocket transport with protocol definition

class WebSocketTransport {
  constructor(options = {}) {
    this.url = options.url;
    this.onOpen = options.onOpen || (() => {});
    this.onClose = options.onClose || (() => {});
    this.onError = options.onError || (() => {});
    this.onMessage = options.onMessage || (() => {});
    
    this.ws = null;
    this.sessionId = null;
    this.targetLanguage = 'en';
    this.translatorMode = false;
    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectDelay = 1000;
    this.isReconnecting = false;
  }
  
  // Binary protocol:
  // Byte 0: Message type (0x01=audio_frame, 0x02=init, 0x03=config_update, 0x04=image_upload, 0x05=request_notes, 0x06=speech_start, 0x07=speech_end, 0x08=barge_in)
  // Bytes 1-4: Payload length (uint32, big-endian)
  // Bytes 5+: Payload (JSON string for non-audio, binary for audio)
  
  static MESSAGE_TYPES = {
    AUDIO_FRAME: 0x01,
    INIT: 0x02,
    CONFIG_UPDATE: 0x03,
    IMAGE_UPLOAD: 0x04,
    REQUEST_NOTES: 0x05,
    SPEECH_START: 0x06,
    SPEECH_END: 0x07,
    BARGE_IN: 0x08
  };
  
  static SERVER_MESSAGE_TYPES = {
    CONNECTED: 0x10,
    TRANSCRIPT_INTERIM: 0x11,
    TRANSCRIPT_FINAL: 0x12,
    AUDIO_CHUNK: 0x13,
    AUDIO_COMPLETE: 0x14,
    ERROR: 0x15,
    NOTES: 0x16,
    IMAGE_RECEIVED: 0x17,
    CONFIG_UPDATED: 0x18,
    LLM_DELTA: 0x19
  };
  
  connect(sessionId, targetLanguage = 'en', translatorMode = false) {
    this.sessionId = sessionId;
    this.targetLanguage = targetLanguage;
    this.translatorMode = translatorMode;
    this._connect();
  }
  
  _connect() {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = this.url || `${protocol}//${window.location.host}/ws`;
      
      this.ws = new WebSocket(wsUrl);
      this.ws.binaryType = 'arraybuffer';
      
      this.ws.onopen = () => {
        this.reconnectAttempts = 0;
        this.isReconnecting = false;
        this.onOpen();
        // Send init message
        this.sendInit(this.sessionId, this.targetLanguage, this.translatorMode);
      };
      
      this.ws.onclose = () => {
        this.onClose();
        if (!this.isReconnecting && this.reconnectAttempts < this.maxReconnectAttempts) {
          this._reconnect();
        }
      };
      
      this.ws.onerror = (error) => {
        this.onError(error);
      };
      
      this.ws.onmessage = (event) => {
        if (event.data instanceof ArrayBuffer) {
          this._handleBinaryMessage(event.data);
        } else {
          // Fallback for text messages (backward compatibility)
          try {
            const data = JSON.parse(event.data);
            this.onMessage(data);
          } catch (e) {
            console.error('Error parsing text message:', e);
          }
        }
      };
    } catch (error) {
      console.error('WebSocket connection error:', error);
      this.onError(error);
      this._reconnect();
    }
  }
  
  _reconnect() {
    if (this.isReconnecting) return;
    
    this.isReconnecting = true;
    this.reconnectAttempts++;
    const delay = Math.min(this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1), 10000);
    
    setTimeout(() => {
      console.log(`Reconnecting... (attempt ${this.reconnectAttempts})`);
      this._connect();
    }, delay);
  }
  
  _handleBinaryMessage(buffer) {
    if (buffer.byteLength < 5) {
      console.error('Invalid binary message: too short');
      return;
    }
    
    const view = new DataView(buffer);
    const messageType = view.getUint8(0);
    const payloadLength = view.getUint32(1, false); // big-endian
    
    if (buffer.byteLength < 5 + payloadLength) {
      console.error('Invalid binary message: payload length mismatch');
      return;
    }
    
    const payload = buffer.slice(5, 5 + payloadLength);
    
    switch (messageType) {
      case WebSocketTransport.SERVER_MESSAGE_TYPES.CONNECTED:
        const sessionId = this._decodeString(payload);
        this.onMessage({ type: 'connected', session_id: sessionId });
        break;
        
      case WebSocketTransport.SERVER_MESSAGE_TYPES.TRANSCRIPT_INTERIM:
        {
          const interim = this._decodeJson(payload);
          const interimText = typeof interim.text === 'string' ? interim.text : this._decodeString(payload);
          this.onMessage({ type: 'transcript_interim', text: interimText });
        }
        break;
        
      case WebSocketTransport.SERVER_MESSAGE_TYPES.TRANSCRIPT_FINAL:
        {
          const final = this._decodeJson(payload);
          const finalText = typeof final.text === 'string' ? final.text : this._decodeString(payload);
          this.onMessage({
            type: 'transcript_final',
            text: finalText,
            confidence: typeof final.confidence === 'number' ? final.confidence : undefined
          });
        }
        break;
        
      case WebSocketTransport.SERVER_MESSAGE_TYPES.AUDIO_CHUNK:
        this.onMessage({ type: 'audio_chunk', data: payload });
        break;
        
      case WebSocketTransport.SERVER_MESSAGE_TYPES.AUDIO_COMPLETE:
        this.onMessage({ type: 'audio_complete' });
        break;
        
      case WebSocketTransport.SERVER_MESSAGE_TYPES.ERROR:
        const errorText = this._decodeString(payload);
        this.onMessage({ type: 'error', message: errorText });
        break;
        
      case WebSocketTransport.SERVER_MESSAGE_TYPES.NOTES:
        const notesText = this._decodeString(payload);
        this.onMessage({ type: 'notes', text: notesText });
        break;

      case WebSocketTransport.SERVER_MESSAGE_TYPES.IMAGE_RECEIVED:
        this.onMessage({ type: 'image_received' });
        break;

      case WebSocketTransport.SERVER_MESSAGE_TYPES.CONFIG_UPDATED: {
        const cfg = this._decodeJson(payload);
        this.onMessage({ type: 'config_updated', ...cfg });
        break;
      }

      case WebSocketTransport.SERVER_MESSAGE_TYPES.LLM_DELTA: {
        const delta = this._decodeJson(payload);
        this.onMessage({
          type: 'llm_delta',
          text: delta.text || '',
          turn_id: delta.turn_id,
          final: Boolean(delta.final)
        });
        break;
      }
        
      default:
        console.warn('Unknown message type:', messageType);
    }
  }
  
  _encodeString(str) {
    const encoder = new TextEncoder();
    return encoder.encode(str);
  }
  
  _decodeString(buffer) {
    const decoder = new TextDecoder();
    return decoder.decode(buffer);
  }

  _decodeJson(buffer) {
    try {
      return JSON.parse(this._decodeString(buffer));
    } catch (e) {
      return {};
    }
  }
  
  _sendBinaryMessage(type, payload) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
      console.warn('WebSocket not open, cannot send message');
      return false;
    }
    
    const payloadBuffer = payload instanceof ArrayBuffer ? payload : 
                         payload instanceof Uint8Array ? payload.buffer :
                         this._encodeString(JSON.stringify(payload)).buffer;
    
    const totalLength = 5 + payloadBuffer.byteLength;
    const buffer = new ArrayBuffer(totalLength);
    const view = new DataView(buffer);
    
    view.setUint8(0, type);
    view.setUint32(1, payloadBuffer.byteLength, false); // big-endian
    
    const payloadView = new Uint8Array(buffer, 5);
    const sourceView = new Uint8Array(payloadBuffer);
    payloadView.set(sourceView);
    
    this.ws.send(buffer);
    return true;
  }
  
  sendInit(sessionId, targetLanguage = 'en', translatorMode = false) {
    return this._sendBinaryMessage(WebSocketTransport.MESSAGE_TYPES.INIT, {
      session_id: sessionId,
      target_language: targetLanguage,
      translator_mode: translatorMode
    });
  }
  
  sendAudioFrame(samples) {
    // samples is Int16Array
    return this._sendBinaryMessage(
      WebSocketTransport.MESSAGE_TYPES.AUDIO_FRAME,
      samples.buffer
    );
  }
  
  sendSpeechStart() {
    return this._sendBinaryMessage(WebSocketTransport.MESSAGE_TYPES.SPEECH_START, {});
  }
  
  sendSpeechEnd() {
    return this._sendBinaryMessage(WebSocketTransport.MESSAGE_TYPES.SPEECH_END, {});
  }
  
  sendBargeIn() {
    return this._sendBinaryMessage(WebSocketTransport.MESSAGE_TYPES.BARGE_IN, {});
  }
  
  sendConfigUpdate(targetLanguage, translatorMode) {
    return this._sendBinaryMessage(WebSocketTransport.MESSAGE_TYPES.CONFIG_UPDATE, {
      target_language: targetLanguage,
      translator_mode: translatorMode
    });
  }
  
  sendImageUpload(imageData) {
    // imageData is base64 string
    return this._sendBinaryMessage(WebSocketTransport.MESSAGE_TYPES.IMAGE_UPLOAD, {
      image_data: imageData
    });
  }
  
  sendRequestNotes() {
    return this._sendBinaryMessage(WebSocketTransport.MESSAGE_TYPES.REQUEST_NOTES, {});
  }
  
  close() {
    if (this.ws) {
      // Prevent reconnection when explicitly closing
      this.isReconnecting = true;
      this.reconnectAttempts = this.maxReconnectAttempts; // Prevent auto-reconnect
      
      // Close with normal closure code
      if (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING) {
        this.ws.close(1000, 'Session closed'); // Normal closure
      }
      this.ws = null;
    }
  }
}

// Export for use in modules
if (typeof module !== 'undefined' && module.exports) {
  module.exports = WebSocketTransport;
}
