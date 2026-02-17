# session_state.py
# Session state management for realtime voice tutoring

import asyncio
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class SessionState:
    """Per-session state for realtime voice tutoring"""
    session_id: str
    target_language: str = "en"
    translator_mode: bool = False
    instructions: str = ""
    
    # Conversation history
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    uploaded_image: Optional[str] = None
    
    # Audio processing
    audio_queue: asyncio.Queue = field(default=None)
    last_audio_time: Optional[float] = None
    silence_timeout_ms: int = 1200  # ms of silence before endpointing (less clipping on trailing words)
    
    # Async tasks
    stt_task: Optional[asyncio.Task] = None
    llm_task: Optional[asyncio.Task] = None
    tts_task: Optional[asyncio.Task] = None
    _stt_response_task: Optional[asyncio.Task] = None  # Internal STT response handler
    
    # Cancellation and barge-in
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    active_generation_cancel_event: Optional[asyncio.Event] = None
    generation_id: int = 0  # Increment on each new generation to cancel old ones
    is_tts_playing: bool = False
    
    # STT streaming state
    stt_stream: Optional[Any] = None  # Google Cloud STT streaming recognizer
    current_utterance_id: int = 0
    current_turn_id: int = 0
    turn_started_at: float | None = None
    turn_audio_bytes: int = 0
    last_transcript_confidence: float = 1.0
    
    # Backpressure
    max_queue_size: int = 100  # Max frames in queue (~2 seconds at 20ms/frame)
    dropped_frames: int = 0
    
    def __post_init__(self):
        """Initialize audio_queue with maxsize for real backpressure"""
        if self.audio_queue is None:
            self.audio_queue = asyncio.Queue(maxsize=self.max_queue_size)
    
    def increment_generation_id(self) -> int:
        """Increment generation ID for cancellation tracking"""
        self.generation_id += 1
        return self.generation_id
    
    def should_drop_frame(self) -> bool:
        """Check if we should drop frames due to backpressure"""
        return self.audio_queue.qsize() >= self.max_queue_size

    def begin_turn(self, now_ts: float) -> int:
        self.current_turn_id += 1
        self.turn_started_at = now_ts
        self.turn_audio_bytes = 0
        return self.current_turn_id
    
    def cleanup(self):
        """Cleanup all tasks and resources"""
        # Cancel all tasks
        if self.stt_task and not self.stt_task.done():
            self.stt_task.cancel()
        if self._stt_response_task and not self._stt_response_task.done():
            self._stt_response_task.cancel()
        if self.llm_task and not self.llm_task.done():
            self.llm_task.cancel()
        if self.tts_task and not self.tts_task.done():
            self.tts_task.cancel()
        
        # Set cancel event
        self.cancel_event.set()
        if self.active_generation_cancel_event:
            self.active_generation_cancel_event.set()
        
        # Close STT stream if exists
        if self.stt_stream:
            try:
                self.stt_stream.close()
            except Exception as e:
                print(f"Error closing STT stream: {e}")
        
        # Clear queue
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
