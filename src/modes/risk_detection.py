"""Streamlit entrypoint for VLM_Monitors."""
import streamlit as st
import cv2
import threading
import time
import os
import math
import numpy as np
import asyncio
import uuid
import subprocess
import logging
from datetime import datetime, timezone
import re


from adapters.ollama_client import OllamaClient
from pipelines.camera import MockCamera, FrameCapture
from pipelines.inference import InferenceEngine
from services.prompts import PromptStore
from services.notifier import TwilioNotifier
from services.sound_detection import SoundDetectionThread
from utils.logging import configure_logging
from shared.state import AppState
from shared.camera import CameraThread, get_video_devices, get_audio_devices
from services.system_monitor import SystemMonitor

# Configure Logging
configure_logging()
logger = logging.getLogger(__name__)

class AnalysisThread(threading.Thread):
    def __init__(self, state: AppState, engine: InferenceEngine):
        super().__init__(daemon=True)
        self.state = state
        self.engine = engine
        self.running = True
        
    def run(self):
        while self.running:
            if self.state.auto_analyze:
                try:
                    self._analyze()
                except Exception as e:
                    logger.error(f"Analysis error: {e}")
            time.sleep(self.state.analysis_interval)
            
    def trigger(self):
        """Force a single analysis run."""
        threading.Thread(target=self._analyze, daemon=True).start()

    def _analyze(self):
        frame = None
        with self.state.lock:
            if self.state.latest_frame is not None:
                frame = self.state.latest_frame.copy()
        
        if frame is None:
            return
            
        # Wrap for engine
        fc = FrameCapture(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            source="stream",
            preview_bytes=b"", 
            prompt_version=1
        )
        # Encode for engine compatibility
        success, buffer = cv2.imencode(".jpg", cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        if success:
            fc.preview_bytes = buffer.tobytes()
            asyncio.run(self._run_inference(fc))
            
    async def _run_inference(self, frame_cap):
        _, result, _ = await self.engine.process_next_frame(
            scoring_model=self.state.scoring_model,
            frame=frame_cap
        )
        
        self.state.risk_binary = result.risk
        self.state.risk_score = result.confidence
        self.state.risk_explanation = result.explanation
        
        if result.risk:
            self.state.consecutive_risk_count += 1
            await self._check_alert()
        else:
            self.state.consecutive_risk_count = 0
            
    async def _check_alert(self):
        if self.state.consecutive_risk_count >= self.state.risk_threshold:
            now = time.time()
            if now - self.state.last_alert_time > self.state.alert_cooldown:
                msg = self.state.custom_msg or f"RISK DETECTED! Score: {self.state.risk_score:.2f}"
                
                # 1. Send SMS
                if self.state.notifier.is_active and self.state.enable_sms:
                    await self.state.notifier.send_sms(self.state.alert_receiver, msg)
                
                # 2. Send Webhook (n8n)
                if self.state.webhook_url and self.state.enable_webhook:
                    try:
                        import requests
                        payload = {
                            "timestamp": datetime.now().isoformat(),
                            "risk_score": self.state.risk_score,
                            "explanation": self.state.risk_explanation,
                            "message": msg
                        }
                        # Run in thread to not block
                        threading.Thread(target=requests.post, args=(self.state.webhook_url,), kwargs={"json": payload, "timeout": 5}).start()
                        logger.info(f"Webhook sent to {self.state.webhook_url}")
                    except Exception as e:
                        logger.error(f"Webhook failed: {e}")

                self.state.last_alert_time = now

def get_backend():
    # Check if we have a shared state from session (passed from app.py or other modes)
    # But st.cache_resource is global. 
    # Let's try to use a singleton pattern that persists better or check session state.
    
    if "app_state" not in st.session_state:
        st.session_state.app_state = AppState()
        logger.info("[BACKEND] Created new AppState")
        
    state = st.session_state.app_state
    
    # Ensure camera is running if not
    if not hasattr(state, 'camera_thread') or state.camera_thread is None or not state.camera_thread.is_alive():
         logger.info("[BACKEND] Starting new CameraThread")
         cam_thread = CameraThread(state)
         cam_thread.start()
         state.camera_thread = cam_thread
         state.audio_device = getattr(cam_thread, "audio_device", "default")
    else:
         logger.debug("[BACKEND] CameraThread already running")
         
    if not getattr(state, "audio_device", None):
         state.audio_device = getattr(state.camera_thread, "audio_device", "default")
         
    prompt_store = PromptStore()
    ollama = OllamaClient()
    engine = InferenceEngine(MockCamera(), prompt_store, ollama)
    
    # Ensure analysis thread is running
    if not hasattr(state, 'analysis_thread') or state.analysis_thread is None or not state.analysis_thread.is_alive():
        logger.info("[BACKEND] Starting new AnalysisThread")
        analysis_thread = AnalysisThread(state, engine)
        analysis_thread.start()
        state.analysis_thread = analysis_thread
    else:
        logger.debug("[BACKEND] AnalysisThread already running")
    
    return state, prompt_store

def run():
    # Log script execution to debug frequency
    logger.info(f"Streamlit Script Re-run: {datetime.now().time()}")

    # --- UI ---
    state, prompt_store = get_backend()

    def sync_sound_thread(enable: bool) -> None:
        if enable:
            if state.sound_thread is None or not state.sound_thread.is_alive():
                state.sound_thread = SoundDetectionThread(state, device=state.audio_device)
                state.sound_thread.start()
        else:
            if state.sound_thread and state.sound_thread.is_alive():
                state.sound_thread.stop()
                state.sound_thread.join(timeout=1.0)
                state.sound_thread = None
            state.sound_risk = False

    # Sidebar
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        with st.expander("Notifications", expanded=True):
            # File Uploader for Config
            uploaded_file = st.file_uploader("Upload Config (txt/ini)", type=['txt', 'ini'])
            
            # Default values from state or empty
            default_sid = ""
            default_token = ""
            default_from = ""
            default_to = state.alert_receiver
            
            if uploaded_file is not None:
                try:
                    content = uploaded_file.getvalue().decode("utf-8")
                    for line in content.splitlines():
                        if "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip().lower()
                            v = v.strip()
                            if k == "sid": default_sid = v
                            elif k == "token": default_token = v
                            elif k == "from_number": default_from = v
                            elif k == "to_number": default_to = v
                    st.success("Config Loaded!")
                except Exception as e:
                    st.error(f"Error parsing file: {e}")

            sid = st.text_input("Twilio SID", value=default_sid, type="password", help="Found in Twilio Console")
            token = st.text_input("Auth Token", value=default_token, type="password", help="Found in Twilio Console")
            from_num = st.text_input("From Number", value=default_from, help="e.g. +1234567890")
            to_num = st.text_input("To Number", value=default_to, help="e.g. +1987654321")
            msg = st.text_input("Custom Message", value=state.custom_msg)
            
            # Help Link
            if not sid or not token:
                st.info("Need credentials? [Get them here](https://console.twilio.com/)")
            
            # Rate Limiting (Manual Input + Slider)
            st.markdown("**Alert Cooldown (s)**")
            col_cd1, col_cd2 = st.columns([1, 1])
            with col_cd1:
                # Slider
                cd_slider = st.slider("Slider", 60, 600, int(state.alert_cooldown), label_visibility="collapsed")
            with col_cd2:
                # Number Input
                cd_input = st.number_input("Seconds", 60, 600, cd_slider, label_visibility="collapsed")
                
            state.alert_cooldown = cd_input
            
            if st.button("Save Configuration", type="primary"):
                if sid and token and from_num:
                    state.notifier.configure(sid, token, from_num, "")
                    state.alert_receiver = to_num
                    state.custom_msg = msg
                    st.success("Configuration Saved!")
                else:
                    st.error("Missing required fields")
                    
            # Status Display
            st.markdown("---")
            st.markdown("**Current Status:**")
            if state.notifier.is_active:
                st.success("Twilio Configured ✅")
            else:
                st.warning("Twilio Not Configured ⚠️")

        with st.expander("Analysis Settings"):
            # Fetch Vision Models (Cached to prevent constant polling)
            @st.cache_data(ttl=300, show_spinner=False)
            def get_cached_vision_models():
                logger.info("Cache MISS: Fetching models from Ollama...")
                try:
                    return OllamaClient.get_models(capability="vision")
                except Exception as e:
                    logger.error(f"Failed to get models: {e}")
                    return []

            vision_models = get_cached_vision_models()
            
            if not vision_models:
                # Fallback if no vision models found
                vision_models = ["llama3.2-vision:11b", "minicpm-v:8b"]
                
            state.scoring_model = st.selectbox("Model", vision_models, index=0 if "llama3.2-vision:11b" in vision_models else 0)
            
            # Handle Model Unloading on Switch
            if "last_risk_model" not in st.session_state:
                st.session_state.last_risk_model = state.scoring_model
            
            if st.session_state.last_risk_model != state.scoring_model:
                st.toast(f"Unloading {st.session_state.last_risk_model}...", icon="🧹")
                OllamaClient.unload_model(st.session_state.last_risk_model)
                st.session_state.last_risk_model = state.scoring_model
                
            state.analysis_interval = st.slider("Interval (s)", 1, 60, 5)

            state.risk_threshold = st.slider("Risk Threshold", 1, 10, 3)

        with st.expander("Device Settings"):
            # Video Device Selection
            video_devices = get_video_devices()
            # Try to find current device index
            try:
                dev_index = video_devices.index(state.camera_thread.device)
            except ValueError:
                dev_index = 0
                
            selected_device = st.selectbox("Video Device", video_devices, index=dev_index)
            
            # Audio Device Input
            # Audio Device Selection
            audio_devices = get_audio_devices()
            # Try to match current thread's audio device if possible, else default
            current_audio = getattr(state.camera_thread, 'audio_device', 'default')
            
            # Helper to find index of current_audio in list (by matching hw:X,Y part or full string)
            audio_index = 0
            for i, d in enumerate(audio_devices):
                if current_audio in d: # Simple substring match for "hw:1,0" in "Name (hw:1,0)"
                    audio_index = i
                    break
                    
            selected_audio_device = st.selectbox("Audio Device (ALSA/Pulse)", audio_devices, index=audio_index)
            
            # Extract actual device string for ffmpeg
            # If "default", use "default". If "Name (hw:1,0)", extract "hw:1,0"
            # If "Pulse: Name (pulse:name)", extract "pulse:name"
            real_audio_device = "default"
            if "hw:" in selected_audio_device:
                match = re.search(r'\((hw:\d+,\d+)\)', selected_audio_device)
                if match:
                    real_audio_device = match.group(1)
            elif "pulse:" in selected_audio_device:
                match = re.search(r'\((pulse:.*)\)', selected_audio_device)
                if match:
                    real_audio_device = match.group(1)
            elif selected_audio_device != "default":
                 # Fallback if format is different but not default
                 real_audio_device = selected_audio_device
            
            with st.expander("Test Microphone"):
                st.info(f"Testing device: {real_audio_device}")
                if st.button("Record 5s Test"):
                    with st.spinner("Recording..."):
                        test_file = "temp/test_audio.wav"
                        os.makedirs("temp", exist_ok=True)
                        
                        # Build Command
                        cmd = ['ffmpeg', '-y']
                        if "pulse" in real_audio_device:
                            source = real_audio_device.split(":", 1)[1]
                            cmd.extend(['-f', 'pulse', '-i', source])
                        else:
                            cmd.extend(['-f', 'alsa', '-i', real_audio_device])
                            
                        cmd.extend(['-t', '5', test_file])
                        
                        try:
                            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                            st.success("Recording Complete!")
                            st.audio(test_file)
                        except subprocess.CalledProcessError:
                            st.error("Recording Failed. Check logs.")

            state.enable_audio = st.checkbox("Enable Microphone (RTSP)", value=state.enable_audio, help="Requires restart of camera")
            
            if st.button("Apply & Restart Camera"):
                # Stop old thread
                if hasattr(state, 'camera_thread') and state.camera_thread.is_alive():
                    state.camera_thread.running = False
                    state.camera_thread.join(timeout=2.0)
                
                new_thread = CameraThread(state, device=selected_device, audio_device=real_audio_device)
                new_thread.start()
                state.camera_thread = new_thread
                state.audio_device = real_audio_device
                if state.enable_sound_detection:
                    sync_sound_thread(False)
                    sync_sound_thread(True)
                st.success(f"Switched to {selected_device}")
                time.sleep(1)
                st.rerun()

        # System Metrics
        st.markdown("---")
        st.markdown("### System Resources")
        
        # Cache system metrics to reduce overhead (updates every 2 seconds)
        @st.cache_data(ttl=2, show_spinner=False)
        def get_cached_metrics():
            logger.debug("[METRICS] Fetching system metrics")
            return SystemMonitor().get_metrics()
        
        try:
            metrics = get_cached_metrics()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("CPU", f"{metrics['cpu_percent']}%")
            if metrics.get('ram'):
                c1.metric("RAM", f"{metrics['ram']['percent']}%", f"{metrics['ram']['used_gb']}/{metrics['ram']['total_gb']} GB")
            
            if metrics.get('gpu'):
                c2.metric("GPU Util", f"{metrics['gpu']['utilization_percent']}%")
                c2.metric("VRAM", f"{metrics['gpu']['memory_percent']}%", f"{metrics['gpu']['used_gb']}/{metrics['gpu']['total_gb']} GB")
                c3.caption(f"GPU: {metrics['gpu']['name']}")
            else:
                c2.warning("No GPU detected")
        except Exception as e:
            logger.error(f"[METRICS] Error: {e}")
            st.error(f"Monitor Error: {e}")

    # Main Dashboard
    st.title("VLM_Monitors - Risk Detection")

    # Layout: Video (Left) | Intelligence (Right)
    col_video, col_intel = st.columns([2, 1])

    with col_video:
        st.subheader("Live Feed")
        
        # RTSP URL Display
        # RTSP URL Display
        rtsp_url_display = "rtsp://127.0.0.1:8554/camera"
        st.code(rtsp_url_display, language="text")

        # Ngrok URL Display
        ngrok_file = "data/ngrok_url.txt"
        if os.path.exists(ngrok_file):
            with open(ngrok_file, "r") as f:
                ngrok_url = f.read().strip()
            if ngrok_url:
                st.markdown("**Public Access:**")
                st.code(ngrok_url, language="text")
        
        # WebRTC Streamer
        from streamlit_webrtc import webrtc_streamer, VideoTransformerBase, WebRtcMode
        import av
        
        # Custom Video Track for Server Camera
        from aiortc import VideoStreamTrack
        
        # Camera Stream Track
        # We define this inside the function to capture `state` closure, but the class should be outside ideally.
        # Since it's already here, we keep it but ensure it's robust.
        
        class CameraStreamTrack(VideoStreamTrack):
            def __init__(self, state):
                super().__init__()
                self.state = state
                self.kind = "video"

            async def recv(self):
                pts, time_base = await self.next_timestamp()
                
                frame = None
                # Wait for a frame with timeout
                for _ in range(10):
                    with self.state.lock:
                        if self.state.latest_frame is not None:
                            frame = self.state.latest_frame.copy()
                            break
                    await asyncio.sleep(0.01)
                
                if frame is None:
                     frame = np.zeros((480, 640, 3), dtype=np.uint8)
                
                # Verify WebRTC Output FPS
                now = time.time()
                if not hasattr(self, "last_log"):
                    self.last_log = now
                    self.frames = 0
                
                self.frames += 1
                if now - self.last_log > 5.0:
                    fps = self.frames / (now - self.last_log)
                    logger.info(f"[WEBRTC] Send FPS: {fps:.2f}")
                    self.frames = 0
                    self.last_log = now
                
                new_frame = av.VideoFrame.from_ndarray(frame, format="rgb24")
                new_frame.pts = pts
                new_frame.time_base = time_base
                return new_frame

        # Managing the Track
        # If the camera thread changes (restarted), `state.latest_frame` logic handles it, 
        # but the `CameraStreamTrack` instance persists in session_state.
        # The key for webrtc_streamer determines if the component re-mounts.
        
        # We'll use a session-specific key for the streamer.
        if "webrtc_key" not in st.session_state:
            st.session_state["webrtc_key"] = f"monitor-{int(time.time())}"

        # Ensure track exists using current state
        if "camera_track" not in st.session_state:
            st.session_state["camera_track"] = CameraStreamTrack(state)
        else:
             # Update state ref just in case backend changed (though state object should be same)
             st.session_state["camera_track"].state = state

        # Helper to restart streamer if needed
        def restart_stream():
             st.session_state["webrtc_key"] = f"monitor-{int(time.time())}"
        
        if st.button("Refresh Stream", help="Click if stream freezes or errors"):
             restart_stream()
             st.rerun()

        webrtc_streamer(
            key=st.session_state["webrtc_key"],
            mode=WebRtcMode.RECVONLY,
            source_video_track=st.session_state["camera_track"],
            media_stream_constraints={"video": True, "audio": False},
            rtc_configuration={
                "iceServers": [{"urls": ["stun:stun.l.google.com:19302"]}]
            },
            async_processing=True,
        )

    with col_intel:
        st.subheader("Risk Intelligence")
        
        # Async Fragment for Stats
        @st.fragment(run_every=0.5)
        def show_stats():
            # Status Indicators
            risk = state.risk_binary or state.sound_risk
            score = state.risk_score
            expl = state.risk_explanation
            
            risk_color = "red" if risk else "green"
            risk_text = "RISK DETECTED" if risk else "SAFE"
            
            st.markdown(f"### Status: :{risk_color}[{risk_text}]")
            st.metric("Confidence Score", f"{score:.2f}")
            if state.enable_sound_detection:
                st.metric("Sound Model FPS", f"{state.sound_fps:.2f}")
            
            st.markdown("**Explanation:**")
            if expl:
                st.info(expl)
            else:
                st.info("Waiting for analysis...")
            if state.enable_sound_detection:
                if state.sound_label:
                    st.caption(f"Sound: {state.sound_label} ({state.sound_score:.2f})")
                else:
                    st.caption("Sound: waiting for audio...")
                
            st.divider()
            
            # Controls inside fragment to be responsive
            col_btn1, col_btn2 = st.columns(2)
            with col_btn1:
                if st.button("Analyze Once", use_container_width=True):
                    state.analysis_thread.trigger()
                    st.toast("Analysis Triggered!")
            
            with col_btn2:
                # Toggle state needs to be persisted outside fragment if possible, 
                # but st.toggle inside fragment works for UI state. 
                # We sync it with backend state.
                auto = st.toggle("Auto Analysis", value=state.auto_analyze)
                state.auto_analyze = auto
                
                if state.auto_analyze:
                    state.enable_sms = st.checkbox("Enable SMS", value=state.enable_sms)
                    state.enable_webhook = st.checkbox("Enable Webhook", value=state.enable_webhook)
                
                sound_enabled = st.checkbox("Sound Detection", value=state.enable_sound_detection)
                if sound_enabled != state.enable_sound_detection:
                    state.enable_sound_detection = sound_enabled
                    sync_sound_thread(sound_enabled)

                # Reset Risk if Auto is OFF
                if not auto:
                    state.risk_binary = False

        show_stats()
        
        st.divider()
        st.subheader("Criteria")
        current_prompt = prompt_store.load()
        
        # Callback to update prompt from history
        def update_prompt_from_history():
            if st.session_state.history_selection:
                st.session_state.prompt_input = st.session_state.history_selection

        new_prompt = st.text_area("Prompt", value=current_prompt.text, height=150, key="prompt_input")
        if st.button("Apply Criteria"):
            prompt_store.update(text=new_prompt)
            st.success("Updated!")
            
        history = st.selectbox(
            "History", 
            prompt_store.get_history_texts(), 
            index=None, 
            placeholder="Select from history...",
            key="history_selection",
            on_change=update_prompt_from_history
        )
