import asyncio
import base64
import os
import time
import logging
import queue
from io import BytesIO
import numpy as np
from fastrtc import AsyncAudioVideoStreamHandler, wait_for_item
from google import genai
from PIL import Image
import cv2
import sounddevice as sd

logger = logging.getLogger(__name__)

def encode_audio(data: np.ndarray) -> dict:
    """Encode Audio data to send to the server"""
    return {
        "mime_type": "audio/pcm",
        "data": base64.b64encode(data.tobytes()).decode("UTF-8"),
    }

def encode_image(data: np.ndarray) -> dict:
    with BytesIO() as output_bytes:
        pil_image = Image.fromarray(data)
        pil_image.save(output_bytes, "JPEG")
        bytes_data = output_bytes.getvalue()
    base64_str = str(base64.b64encode(bytes_data), "utf-8")
    return {"mime_type": "image/jpeg", "data": base64_str}

from typing import Tuple

class GeminiHandler(AsyncAudioVideoStreamHandler):
    def __init__(self, video_device=0, audio_device=None, bridge=None, transform_callback=None) -> None:
        logger.info(f"GeminiHandler.__init__ called with video_device={video_device}, bridge={bridge is not None}")
        super().__init__(
            "audio-video",
            output_sample_rate=24000,
            input_sample_rate=16000,
        )
        self.video_device = video_device
        self.audio_device = audio_device
        self.bridge = bridge
        self.transform_callback = transform_callback
        
        self.audio_queue = asyncio.Queue() # Gemini -> Client
        self.video_queue = asyncio.Queue() # Server Cam -> Client
        
        self.session = None
        self.last_frame_time = 0
        self.quit = asyncio.Event()
        
        self.cap = None
        self.audio_stream = None
        self.mic_queue = queue.Queue()
        logger.info("GeminiHandler.__init__ completed")

    async def receive(self, frame: Tuple[int, np.ndarray]) -> None:
        # Client audio input - ignored as we use server mic
        pass

    async def video_receive(self, frame: np.ndarray):
        # Client video input - ignored as we use server camera
        pass

    def copy(self) -> "GeminiHandler":
        logger.info(f"GeminiHandler.copy() called, creating new instance with bridge={self.bridge is not None}")
        return GeminiHandler(self.video_device, self.audio_device, self.bridge, self.transform_callback)

    async def start_up(self):
        logger.info("=" * 60)
        logger.info("GeminiHandler.start_up() CALLED!")
        logger.info(f"  video_device: {self.video_device}")
        logger.info(f"  audio_device: {self.audio_device}")
        logger.info(f"  bridge: {self.bridge}")
        logger.info("=" * 60)
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            logger.warning("GEMINI_API_KEY not set - Gemini Live features will be disabled")
            # We might want to raise error or handle gracefully
            
        if api_key:
            try:
                client = genai.Client(
                    api_key=api_key, http_options={"api_version": "v1alpha"}
                )
                config = {"response_modalities": ["AUDIO"]}
                self.session = await client.aio.live.connect(
                    model="gemini-2.0-flash-exp",
                    config=config,
                )
                logger.info("✓ Connected to Gemini Live")
                
                # Start Receive Loop
                asyncio.create_task(self._receive_gemini_loop())
            except Exception as e:
                logger.error(f"Failed to connect to Gemini: {e}", exc_info=True)

        # Start Capture Task - THIS IS CRITICAL
        logger.info("Starting _capture_loop task...")
        asyncio.create_task(self._capture_loop())
        logger.info("GeminiHandler.start_up() completed")

    async def _receive_gemini_loop(self):
        if not self.session:
            return
        while not self.quit.is_set():
            try:
                async for response in self.session.receive():
                    if data := response.data:
                        audio = np.frombuffer(data, dtype=np.int16).reshape(1, -1)
                        self.audio_queue.put_nowait(audio)
            except Exception as e:
                logger.error(f"Gemini receive error: {e}")
                break

    def _audio_callback(self, indata, frames, time, status):
        if status:
            logger.warning(f"Audio status: {status}")
        self.mic_queue.put(indata.copy())

    async def _capture_loop(self):
        logger.info(">>> _capture_loop STARTED <<<")
        logger.info(f"    Bridge is: {self.bridge}")
        
        # Init Video (retry until opened)
        retry_count = 0
        while not self.quit.is_set():
            try:
                vid_source = self.video_device
                # DON'T convert /dev/video paths to integers in Docker!
                # cv2.VideoCapture() can handle device paths directly
                
                logger.info(f"[Attempt {retry_count + 1}] Opening camera: {vid_source}")
                self.cap = cv2.VideoCapture(vid_source)
                if self.cap.isOpened():
                    logger.info(f"✓ Camera opened successfully: {vid_source}")
                    break
                else:
                    logger.error(f"✗ Failed to open camera: {vid_source}. Retrying in 2s...")
                    self.cap.release()
                    retry_count += 1
                    await asyncio.sleep(2.0)
            except Exception as e:
                logger.error(f"Camera init error: {e}", exc_info=True)
                retry_count += 1
                await asyncio.sleep(2.0)

        # Init Audio
        try:
            logger.info(f"Opening audio device: {self.audio_device}")
            self.audio_stream = sd.InputStream(
                device=self.audio_device,
                channels=1,
                samplerate=16000,
                dtype='int16',
                callback=self._audio_callback
            )
            self.audio_stream.start()
        except Exception as e:
            logger.error(f"Audio init error: {e}")

        frame_send_count = 0
        last_log_time = time.time()
        
        while not self.quit.is_set():
            # Process Video
            if self.cap and self.cap.isOpened():
                ret, frame = await asyncio.to_thread(self.cap.read)
                if ret and frame is not None:
                    # Validate frame dimensions
                    if frame.size == 0:
                        logger.warning("Captured empty/invalid frame from camera")
                        await asyncio.sleep(0.1)
                        continue
                    
                    # OpenCV returns BGR, convert to RGB for Gemini and Bridge
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    
                    # Update Bridge for Analysis (Raw Frame)
                    if self.bridge:
                        self.bridge.set_frame(frame)
                        frame_send_count += 1
                        # Log every 10 seconds to track frame flow
                        if time.time() - last_log_time > 10.0:
                            logger.info(f"GeminiHandler: sent {frame_send_count} frames to bridge")
                            last_log_time = time.time()
                    else:
                        logger.warning("Bridge not set in GeminiHandler")
                        
                    # Prepare Display Frame (Apply Overlays)
                    display_frame = frame
                    if self.transform_callback:
                        try:
                            display_frame = self.transform_callback(frame)
                        except Exception as e:
                            logger.error(f"Transform error: {e}")
                            
                    self.video_queue.put_nowait(display_frame)
                    
                    # Send to Gemini (1 FPS) - Use RAW frame
                    if self.session and (time.time() - self.last_frame_time > 1.0):
                        self.last_frame_time = time.time()
                        try:
                            await self.session.send(input=encode_image(frame))
                        except Exception as e:
                            logger.error(f"Error sending image to Gemini: {e}")
                else:
                    logger.debug("Failed to read frame from camera")
                    await asyncio.sleep(0.1)
            else:
                logger.warning("Camera not opened in capture loop")
                await asyncio.sleep(0.1)

            # Process Audio
            while not self.mic_queue.empty():
                audio_data = self.mic_queue.get()
                if self.session:
                    try:
                        # Gemini expects base64 encoded PCM
                        # encode_audio returns {"mime_type":..., "data":...}
                        # We assume audio_data is np.int16
                        # Ensure shape? encode_audio takes np.ndarray
                        await self.session.send(input=encode_audio(audio_data))
                    except Exception as e:
                        logger.error(f"Error sending audio to Gemini: {e}")
            
            await asyncio.sleep(0.01)

    async def video_emit(self):
        # Return frame from Server Camera
        frame = await wait_for_item(self.video_queue, 0.01)
        if frame is not None:
            return frame
        else:
            # Return black frame if no video
            return np.zeros((480, 640, 3), dtype=np.uint8)

    async def emit(self):
        # Return Audio from Gemini
        array = await wait_for_item(self.audio_queue, 0.01)
        if array is not None:
            return (self.output_sample_rate, array)
        return None

    async def shutdown(self) -> None:
        self.quit.set()
        if self.session:
            await self.session.close()
        if self.cap:
            self.cap.release()
        if self.audio_stream:
            self.audio_stream.stop()
            self.audio_stream.close()
