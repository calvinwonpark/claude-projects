# stt_stream.py
# Streaming Speech-to-Text implementation

import asyncio
import queue as stdlib_queue
import threading
from typing import Callable, Optional, Awaitable
from google.cloud import speech
import logging

logger = logging.getLogger(__name__)


class StreamingSTT:
    """Manages Google Cloud Speech-to-Text streaming recognition"""
    
    def __init__(
        self,
        session_state,
        language_code: str = "en-US",
        sample_rate: int = 16000,
        on_interim: Optional[Callable[[str], Awaitable[None]]] = None,
        on_final: Optional[Callable[[str, float], Awaitable[None]]] = None,
    ):
        self.session_state = session_state
        self.language_code = language_code
        self.sample_rate = sample_rate
        self.on_interim = on_interim
        self.on_final = on_final
        self.stt_client = None
        self.stream = None
        self.request_queue = stdlib_queue.Queue(maxsize=50)  # Limit queue size to prevent unbounded growth
        self.is_active = False
        self._stop_event = threading.Event()  # Dedicated STT stop event (only set on session shutdown)
        self._stream_thread = None  # Thread that runs stream creation and iteration
        self._event_loop = None  # Main event loop (set during initialize)
        self._active_queue = None  # Queue that the active stream thread is reading from
        self._stream_lock = threading.Lock()  # Lock for stream/queue operations
        
    def initialize(self, stt_client):
        """Initialize STT client and create streaming config (stream will start on first audio)"""
        self.stt_client = stt_client
        self._event_loop = asyncio.get_event_loop()  # Store main event loop for callbacks from thread
        
        # Create streaming config (store for later use)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=self.sample_rate,
            language_code=self.language_code,
            alternative_language_codes=["ko-KR", "en-US"] if self.language_code == "en-US" else ["en-US", "ko-KR"],
            enable_automatic_punctuation=True,
            model="latest_long",
        )
        
        self.streaming_config = speech.StreamingRecognitionConfig(
            config=config,
            interim_results=True,
            single_utterance=False,
        )
        
        self.is_active = True
        self.stream = None  # Will be created when first audio arrives
        logger.info(f"STT client initialized for session {self.session_state.session_id} (stream will start on first audio)")
    
    async def process_audio_queue(self):
        """Process audio frames from queue and send to STT"""
        try:
            logger.info("STT audio processing started")
            
            # Wait for first audio frame before starting STT stream
            first_frame_received = False
            frame_count = 0
            loop_count = 0
            
            # Process audio queue and add to request queue
            # Note: Don't check cancel_event here - STT should continue processing even during barge-in
            while True:
                loop_count += 1
                if loop_count % 100 == 0:  # Log every 100 iterations to show it's alive
                    logger.debug(f"STT process_audio_queue: Loop iteration {loop_count}, audio_queue size: {self.session_state.audio_queue.qsize()}, request_queue size: {self.request_queue.qsize()}")
                try:
                    # Get audio frame with timeout
                    timeout = 0.1
                    if loop_count <= 5 or loop_count % 50 == 0:  # Log first 5 iterations and then every 50
                        logger.debug(f"STT process_audio_queue: Waiting for frame (timeout={timeout}s, audio_queue_size={self.session_state.audio_queue.qsize()})")
                    audio_frame = await asyncio.wait_for(
                        self.session_state.audio_queue.get(),
                        timeout=timeout
                    )
                    frame_count += 1
                    
                    # Check for sentinel BEFORE logging len() to avoid crash
                    if audio_frame is None:  # Sentinel for shutdown
                        logger.info("STT process_audio_queue: Received shutdown sentinel")
                        # Close active stream/thread even if self.stream is None
                        await self._close_and_restart_stream()
                        break
                    
                    logger.info(f"STT process_audio_queue: Got frame #{frame_count} from queue: {len(audio_frame)} bytes")
                    
                    # Atomically decide whether to start a new stream thread and pick target queue.
                    # If stream is active, always target the pinned active queue.
                    start_thread = False
                    with self._stream_lock:
                        if self._stream_thread is None or not self._stream_thread.is_alive():
                            # No live stream thread: next utterance should use current request_queue.
                            target_q = self.request_queue
                            # Publish active queue immediately to avoid "thread alive but not pinned yet" gap.
                            self._active_queue = target_q
                            self._stream_thread = threading.Thread(
                                target=self._start_stream_and_iterate,
                                args=(target_q,),
                                daemon=True,
                                name="STT-stream-thread"
                            )
                            start_thread = True
                        else:
                            # Live stream thread: enqueue to active pinned queue.
                            target_q = self._active_queue

                            if target_q is None:
                                # should never happen now
                                logger.error("Invariant violated: stream thread alive but _active_queue is None")
                                continue
                    
                    if not first_frame_received:
                        logger.info("STT process_audio_queue: First frame received")
                        first_frame_received = True
                    
                    if start_thread:
                        # Start new stream - enqueue frame first so generator has something to yield immediately
                        logger.info("STT process_audio_queue: Starting stream in dedicated thread...")
                        try:
                            request = speech.StreamingRecognizeRequest(audio_content=audio_frame)
                            target_q.put_nowait(request)
                            logger.info(f"Added audio frame to STT queue: {len(audio_frame)} bytes")
                        except stdlib_queue.Full:
                            logger.error("STT request queue full on first frame - this should not happen!")
                            continue
                        except Exception as e:
                            logger.error(f"Error adding first frame to STT queue: {e}", exc_info=True)
                            continue
                        
                        # Start stream in dedicated thread that creates stream AND immediately iterates it.
                        # Thread object was assigned under lock to avoid races.
                        self._stream_thread.start()
                        logger.info("STT process_audio_queue: Stream thread started")
                    else:
                        try:
                            request = speech.StreamingRecognizeRequest(audio_content=audio_frame)
                            target_q.put_nowait(request)
                            logger.debug(f"Added audio frame #{frame_count} to STT queue: {len(audio_frame)} bytes, queue size: {target_q.qsize()}")
                        except stdlib_queue.Full:
                            logger.warning(f"STT request queue full, dropping frame (queue size: {target_q.qsize()})")
                        except Exception as e:
                            logger.error(f"Error adding frame to STT queue: {e}", exc_info=True)
                    
                    # Update last audio time
                    self.session_state.last_audio_time = asyncio.get_event_loop().time()
                    logger.debug(f"Updated last_audio_time: {self.session_state.last_audio_time}")
                    
                except asyncio.TimeoutError:
                    # Timeout waiting for audio frame
                    audio_queue_size = self.session_state.audio_queue.qsize()
                    # Log timeout occasionally to show loop is running
                    if loop_count % 20 == 0:
                        logger.debug(f"STT process_audio_queue: Timeout (loop={loop_count}, audio_queue_size={audio_queue_size}, request_queue_size={self.request_queue.qsize()})")
                    
                    # Check for silence timeout (endpointing)
                    if self.session_state.last_audio_time:
                        silence_duration = (
                            asyncio.get_event_loop().time() - 
                            self.session_state.last_audio_time
                        ) * 1000  # Convert to ms
                        
                        if silence_duration >= self.session_state.silence_timeout_ms:
                            # Endpoint detected - close current stream and restart for next utterance
                            logger.info(f"Silence timeout ({silence_duration:.0f}ms) - closing stream and restarting for next utterance")
                            await self._close_and_restart_stream()
                            self.session_state.last_audio_time = None
                    
                    continue
                except Exception as e:
                    logger.error(f"Error processing audio frame: {e}", exc_info=True)
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    continue
        
        except asyncio.CancelledError:
            logger.info("STT processing cancelled")
        except Exception as e:
            logger.error(f"STT processing error: {e}", exc_info=True)
        finally:
            self.is_active = False
            logger.info("STT audio processing stopped")
    
    def _start_stream_and_iterate(self, q):
        """Start STT stream and immediately iterate responses in the same thread
        
        CRITICAL: streaming_recognize() doesn't actually start the RPC until you iterate the stream.
        We must create the stream AND start iterating it in the same thread to avoid the 10-12s delay.
        
        CRITICAL: Pin the queue in the generator closure so queue swapping doesn't redirect the generator.
        """
        # CRITICAL: q is passed from process_audio_queue at thread creation time.
        # This guarantees the thread pins the exact queue that received first frame.
        with self._stream_lock:
            self._active_queue = q  # Track the active queue for this stream thread
        
        # Note: We don't check if self.stream is not None here because:
        # 1. Thread gating (should_start_stream) already prevents multiple threads
        # 2. Early return could cause deadlock if stream exists but thread is dead
        # 3. If stream exists, streaming_recognize() will handle it appropriately
        
        # Create request generator that yields from queue
        # Note: config is passed to streaming_recognize(), so requests should NOT include config
        def request_generator():
            logger.info("STT generator: Starting generator function")
            frame_count = 0
            # Yield audio requests from queue (config is already passed to streaming_recognize)
            # CRITICAL: Use pinned queue 'q', not self.request_queue (which can be swapped)
            while self.is_active and not self._stop_event.is_set():
                try:
                    # Wait for audio frame (short timeout to check stop event periodically)
                    queue_size = q.qsize()
                    logger.debug(f"STT generator: Waiting for frame (queue_size={queue_size})")
                    item = q.get(timeout=0.5)
                    # Internal shutdown sentinel: stop generator without yielding to Google STT.
                    # Sending audio_content=None to Google causes "Malordered Data Received".
                    if item is None:
                        logger.info("STT generator: Received internal sentinel, stopping generator")
                        break
                    req = item
                    frame_count += 1
                    logger.info(f"STT generator: Got frame #{frame_count}, yielding to STT (size={len(req.audio_content)} bytes)")
                    yield req
                    logger.debug(f"STT generator yielded audio frame: {len(req.audio_content)} bytes")
                except stdlib_queue.Empty:
                    # Timeout - just continue loop to check stop event
                    # Don't send empty audio - let STT naturally finalize
                    logger.debug(f"STT generator: Timeout, checking stop event (frame_count={frame_count}, queue_size={q.qsize()})")
                    # Continue loop to check stop event
                    continue
            logger.info("STT generator: Exiting (stop event set or is_active=False)")
        
        # Start streaming recognition
        # config parameter provides the streaming config, requests generator provides audio
        try:
            logger.info("STT _start_stream_and_iterate: About to call streaming_recognize()...")
            logger.info(f"STT _start_stream_and_iterate: streaming_config={self.streaming_config}")
            logger.info("STT _start_stream_and_iterate: Creating generator and calling streaming_recognize()...")
            gen = request_generator()
            logger.info("STT _start_stream_and_iterate: Generator created, calling streaming_recognize()...")
            self.stream = self.stt_client.streaming_recognize(
                config=self.streaming_config,
                requests=gen
            )
            logger.info("STT _start_stream_and_iterate: streaming_recognize() returned, stream object created")
            logger.info("STT stream created - starting immediate iteration (critical for RPC to actually start)")
            
            # CRITICAL: Immediately start iterating the stream in the same thread
            # The RPC doesn't actually start until you iterate, so we must do this here
            # Use stored event loop (we're in a thread, can't use get_event_loop())
            loop = self._event_loop
            if loop is None:
                logger.error("Event loop not set - cannot schedule callbacks")
                return
            response_count = 0
            
            for response in self.stream:
                # Check stop event (not cancel_event - STT must continue during barge-in)
                if self._stop_event.is_set():
                    logger.info("STT stream iteration stopped (stop event set)")
                    break
                
                response_count += 1
                logger.debug(f"STT response #{response_count} received")
                
                if not response.results:
                    logger.debug("STT response has no results")
                    continue
                
                result = response.results[0]
                if not result.alternatives:
                    logger.debug("STT result has no alternatives")
                    continue
                
                transcript = result.alternatives[0].transcript
                confidence = float(getattr(result.alternatives[0], "confidence", 0.0) or 0.0)
                is_final = getattr(result, "is_final", False)
                
                # Schedule callback in event loop
                if is_final:
                    logger.info(f"STT Final: {transcript}")
                    if self.on_final:
                        if asyncio.iscoroutinefunction(self.on_final):
                            asyncio.run_coroutine_threadsafe(self.on_final(transcript, confidence), loop)
                        else:
                            loop.call_soon_threadsafe(self.on_final, transcript, confidence)
                else:
                    logger.debug(f"STT Interim: {transcript}")
                    if self.on_interim:
                        if asyncio.iscoroutinefunction(self.on_interim):
                            asyncio.run_coroutine_threadsafe(self.on_interim(transcript), loop)
                        else:
                            loop.call_soon_threadsafe(self.on_interim, transcript)
                            
        except Exception as e:
            logger.error(f"Error in streaming_recognize() or iteration: {e}", exc_info=True)
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            raise
        finally:
            logger.info("STT stream iteration ended")
            # Clear active queue reference when thread exits
            with self._stream_lock:
                if self._active_queue == q:  # Only clear if this thread's queue
                    self._active_queue = None
    
    async def _finalize_utterance(self):
        """Finalize current utterance - close and restart stream for next utterance"""
        logger.debug("Finalizing utterance - closing stream and restarting for next utterance")
        await self._close_and_restart_stream()
        if self.session_state.last_audio_time:
            self.session_state.last_audio_time = None
    
    async def _close_and_restart_stream(self):
        # Snapshot under lock + swap request queue for next utterance
        with self._stream_lock:
            t = self._stream_thread
            old_queue = self._active_queue

            if t is None:
                return  # no stream to close

            if t.is_alive() and old_queue is None:
                logger.error("Invariant violated: stream thread alive but _active_queue is None")
                return

            if old_queue is None:
                old_queue = self.request_queue

            # swap queue for next utterance ONCE
            self.request_queue = stdlib_queue.Queue(maxsize=50)

        logger.info("Closing STT stream for utterance end")

        # Send sentinel to end current request generator (never send to Google)
        try:
            old_queue.put_nowait(None)
            logger.debug("Sentinel sent to active stream queue")
        except stdlib_queue.Full:
            try:
                old_queue.put(None)
                logger.debug("Sentinel sent to active stream queue (blocking)")
            except Exception as e:
                logger.warning(f"Error sending sentinel (blocking): {e}")
        except Exception as e:
            logger.warning(f"Error sending sentinel: {e}")

        # Wait for thread to exit
        if t.is_alive():
            logger.debug("Waiting for stream thread to exit...")
            for _ in range(30):
                if not t.is_alive():
                    break
                await asyncio.sleep(0.1)

        # Clear state only when thread is dead
        with self._stream_lock:
            self.stream = None
            if not t.is_alive():
                self._stream_thread = None
                self._active_queue = None

        logger.info("STT stream closed - will restart on next audio frame with fresh queue")

    
    async def handle_responses(self):
        """Handle STT streaming responses
        
        Note: Response handling is now done in _start_stream_and_iterate() in the same thread
        that creates the stream. This method just waits for the stream thread to complete.
        """
        try:
            logger.info("STT response handler started")
            
            # Wait for stream thread to start (stream is created and iterated in that thread)
            max_wait_time = 30.0  # seconds
            wait_start = asyncio.get_event_loop().time()
            
            while (self._stream_thread is None or not self._stream_thread.is_alive()) and not self._stop_event.is_set():
                elapsed = asyncio.get_event_loop().time() - wait_start
                if elapsed >= max_wait_time:
                    logger.warning(f"STT stream creation timeout after {elapsed:.1f}s")
                    break
                
                # Log progress every 5 seconds
                if elapsed > 0 and int(elapsed) % 5 == 0:
                    logger.debug(f"STT response handler: Waiting for stream thread ({elapsed:.1f}s elapsed)")
                
                await asyncio.sleep(0.1)
            
            # Check if stream thread was created
            if self._stream_thread and self._stream_thread.is_alive():
                elapsed = asyncio.get_event_loop().time() - wait_start
                logger.info(f"STT stream thread detected after {elapsed:.1f}s wait")
            else:
                # Only warn if stream wasn't created (and we weren't stopped)
                if not self._stop_event.is_set():
                    logger.warning("STT stream thread was never created")
                else:
                    logger.debug("STT stream thread was never created (stop event set)")
                return
            
            # Wait for stream thread to complete (it handles all response processing)
            logger.info("STT response handler: Waiting for stream thread to complete")
            # Pin thread reference locally to avoid races when _stream_thread is reset elsewhere.
            t = self._stream_thread
            if t is None:
                return
            # Thread will exit when stream ends or stop_event is set
            while t.is_alive() and self.is_active and not self._stop_event.is_set():
                await asyncio.sleep(1.0)
        
        except Exception as e:
            logger.error(f"Error handling STT responses: {e}")
    
    def update_language(self, language_code: str):
        """Update language and restart stream"""
        self.language_code = language_code
        # Stream will be restarted on next audio frame
    
    def close(self):
        """Close STT stream"""
        logger.info("STT close() called")
        # Set stop event to signal shutdown to all STT components
        self._stop_event.set()
        self.is_active = False
        
        # Signal shutdown to the active queue (the one the generator is reading from)
        # This works even if self.stream is None
        with self._stream_lock:
            q = self._active_queue or self.request_queue
        
        if q:
            try:
                q.put_nowait(None)
                logger.debug("STT shutdown sentinel sent to active queue")
            except stdlib_queue.Full:
                try:
                    q.put(None)
                    logger.debug("STT shutdown sentinel sent to active queue (blocking)")
                except Exception as e:
                    logger.warning(f"Error sending shutdown sentinel (blocking): {e}")
            except Exception as e:
                logger.warning(f"Error sending shutdown sentinel: {e}")
        
        # Reset stream state under lock for consistency
        with self._stream_lock:
            self.stream = None
