# tts_stream.py
# Streaming Text-to-Speech implementation

import asyncio
from typing import Callable, Optional, Awaitable
from google.cloud import texttospeech
import logging

logger = logging.getLogger(__name__)


class StreamingTTS:
    """Manages Google Cloud Text-to-Speech with chunked streaming"""
    
    def __init__(
        self,
        tts_client: texttospeech.TextToSpeechClient,
        on_audio_chunk: Optional[Callable[[bytes], Awaitable[None]]] = None,
        on_complete: Optional[Callable[[], Awaitable[None]]] = None,
    ):
        self.tts_client = tts_client
        self.on_audio_chunk = on_audio_chunk
        self.on_complete = on_complete
        self.chunk_size = 4800 * 2  # ~200ms of 16-bit PCM at 24kHz
    
    async def synthesize_and_stream(
        self,
        text: str,
        language_code: str = "en-US",
        cancel_event: Optional[asyncio.Event] = None,
    ):
        """
        Synthesize speech and stream in chunks
        
        Args:
            text: Text to synthesize
            language_code: Language code (e.g., "en-US", "ko-KR")
            cancel_event: Event to check for cancellation
        """
        try:
            # Select voice
            if language_code.startswith("ko"):
                voice_name = "ko-KR-Standard-A"
                ssml_gender = texttospeech.SsmlVoiceGender.FEMALE
            else:
                voice_name = "en-US-Neural2-F"
                ssml_gender = texttospeech.SsmlVoiceGender.FEMALE
            
            # Configure synthesis - use LINEAR16 for low-latency streaming
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice = texttospeech.VoiceSelectionParams(
                language_code=language_code,
                name=voice_name,
                ssml_gender=ssml_gender,
            )
            audio_config = texttospeech.AudioConfig(
                audio_encoding=texttospeech.AudioEncoding.LINEAR16,  # PCM16 for streaming
                sample_rate_hertz=24000,  # Standard TTS sample rate
                speaking_rate=1.0,
                pitch=0.0,
            )
            
            # Check cancellation before API call
            if cancel_event and cancel_event.is_set():
                logger.info("TTS cancelled before synthesis")
                return
            
            # Synthesize (run in thread pool)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.tts_client.synthesize_speech(
                    input=synthesis_input,
                    voice=voice,
                    audio_config=audio_config
                )
            )
            
            # Check cancellation after synthesis
            if cancel_event and cancel_event.is_set():
                logger.info("TTS cancelled after synthesis")
                return
            
            audio_data = response.audio_content
            
            # Stream in chunks
            for i in range(0, len(audio_data), self.chunk_size):
                # Check cancellation before each chunk
                if cancel_event and cancel_event.is_set():
                    logger.info("TTS cancelled during streaming")
                    return
                
                chunk = audio_data[i:i + self.chunk_size]
                
                if self.on_audio_chunk:
                    if asyncio.iscoroutinefunction(self.on_audio_chunk):
                        await self.on_audio_chunk(chunk)
                    else:
                        self.on_audio_chunk(chunk)
                
                # Small delay to prevent overwhelming the client
                await asyncio.sleep(0.01)
            
            if self.on_complete:
                if asyncio.iscoroutinefunction(self.on_complete):
                    await self.on_complete()
                else:
                    self.on_complete()
            
            logger.info(f"TTS streaming complete: {len(audio_data)} bytes")
        
        except asyncio.CancelledError:
            logger.info("TTS task cancelled")
        except Exception as e:
            logger.error(f"TTS error: {e}")
            raise
