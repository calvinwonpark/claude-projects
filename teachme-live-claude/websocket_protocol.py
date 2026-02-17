# websocket_protocol.py
# Binary WebSocket protocol implementation

import struct
import json
from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class WebSocketProtocol:
    """Binary WebSocket protocol handler"""
    
    # Client message types
    AUDIO_FRAME = 0x01
    INIT = 0x02
    CONFIG_UPDATE = 0x03
    IMAGE_UPLOAD = 0x04
    REQUEST_NOTES = 0x05
    SPEECH_START = 0x06
    SPEECH_END = 0x07
    BARGE_IN = 0x08
    
    # Server message types
    CONNECTED = 0x10
    TRANSCRIPT_INTERIM = 0x11
    TRANSCRIPT_FINAL = 0x12
    AUDIO_CHUNK = 0x13
    AUDIO_COMPLETE = 0x14
    ERROR = 0x15
    NOTES = 0x16
    IMAGE_RECEIVED = 0x17
    CONFIG_UPDATED = 0x18
    LLM_DELTA = 0x19
    
    @staticmethod
    def parse_message(buffer: bytes) -> Tuple[int, bytes]:
        """
        Parse binary WebSocket message
        
        Returns:
            (message_type, payload)
        """
        if len(buffer) < 5:
            raise ValueError("Message too short")
        
        msg_type = buffer[0]
        payload_len = struct.unpack('>I', buffer[1:5])[0]  # big-endian uint32
        
        if len(buffer) < 5 + payload_len:
            raise ValueError(f"Payload length mismatch: expected {payload_len}, got {len(buffer) - 5}")
        
        payload = buffer[5:5 + payload_len]
        return msg_type, payload
    
    @staticmethod
    def encode_message(msg_type: int, payload: bytes) -> bytes:
        """
        Encode binary WebSocket message
        
        Args:
            msg_type: Message type byte
            payload: Payload bytes
        
        Returns:
            Encoded message bytes
        """
        payload_bytes = payload if isinstance(payload, bytes) else payload.encode('utf-8')
        buffer = bytearray(5 + len(payload_bytes))
        buffer[0] = msg_type
        struct.pack_into('>I', buffer, 1, len(payload_bytes))  # big-endian
        buffer[5:] = payload_bytes
        return bytes(buffer)
    
    @staticmethod
    def encode_json_message(msg_type: int, data: dict) -> bytes:
        """Encode JSON message"""
        payload = json.dumps(data).encode('utf-8')
        return WebSocketProtocol.encode_message(msg_type, payload)
    
    @staticmethod
    def decode_json_payload(payload: bytes) -> dict:
        """Decode JSON payload"""
        return json.loads(payload.decode('utf-8'))
