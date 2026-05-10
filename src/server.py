"""Flask Backend Server for VLM_Monitors."""
import os
import sys
import time
import logging
import asyncio
import threading
import uuid
import re
from datetime import datetime, timezone
from flask import Flask, jsonify, request, send_from_directory, Response
from flask_socketio import SocketIO, emit
from flask_cors import CORS

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from adapters.ollama_client import OllamaClient
from pipelines.camera import MockCamera, FrameCapture
from pipelines.inference import InferenceEngine
from services.prompts import PromptStore
from services.notifier import TwilioNotifier
from services.sound_detection import SoundDetectionThread
from services.system_monitor import SystemMonitor
from utils.logging import configure_logging
from shared.state import AppState
from shared.camera import CameraThread, get_video_devices, get_audio_devices
import cv2
import numpy as np
from urllib import request as urllib_request, error as urllib_error

# Configure Logging
configure_logging()
logger = logging.getLogger(__name__)

# Initialize Flask App
app = Flask(__name__, 
            static_folder='../static',
            static_url_path='/static')
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global State
app_state = None
prompt_store = None
inference_engine = None
analysis_thread = None

# Setup GStreamer Plugin Path for NVIDIA Acceleration
if "GST_PLUGIN_PATH" not in os.environ:
    os.environ["GST_PLUGIN_PATH"] = "/usr/lib/aarch64-linux-gnu/gstreamer-1.0/"


class SelectedSourceFrameThread(threading.Thread):
    """Continuously tap the selected remote source into shared state."""

    def __init__(self, state: AppState, source_id: str, rtsp_url: str):
        super().__init__(daemon=True)
        self.state = state
        self.source_id = source_id
        self.rtsp_url = rtsp_url
        self.running = True

    def stop(self):
        self.running = False

    def run(self):
        cap = None
        while self.running:
            try:
                if cap is None or not cap.isOpened():
                    cap = cv2.VideoCapture(self.rtsp_url, cv2.CAP_FFMPEG)
                    if not cap.isOpened():
                        logger.warning("Failed to open selected source stream: %s", self.rtsp_url)
                        time.sleep(1.0)
                        continue

                ok, frame = cap.read()
                if not ok or frame is None:
                    time.sleep(0.1)
                    continue

                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                with self.state.lock:
                    if self.state.selected_source_id == self.source_id:
                        self.state.selected_frame = frame_rgb
                time.sleep(0.03)
            except Exception as e:
                logger.error("Selected source frame tap error for %s: %s", self.source_id, e)
                time.sleep(1.0)
        if cap is not None:
            cap.release()

class AnalysisThread(threading.Thread):
    """Background thread for automatic risk analysis."""
    
    def __init__(self, state: AppState, engine: InferenceEngine):
        super().__init__(daemon=True)
        self.state = state
        self.engine = engine
        self.running = True
        self.analysis_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.wake_event = threading.Event()
        self.immediate_requested = False
        
    def run(self):
        next_run_at = None
        while self.running and not self.stop_event.is_set():
            if not self.state.auto_analyze:
                next_run_at = None
                self.wake_event.wait(timeout=0.25)
                self.wake_event.clear()
                continue

            now = time.monotonic()
            should_run_now = self.immediate_requested or next_run_at is None or now >= next_run_at
            if should_run_now:
                self.immediate_requested = False
                try:
                    self._analyze()
                except Exception as e:
                    logger.error(f"Analysis error: {e}")
                next_run_at = time.monotonic() + max(0.0, float(self.state.analysis_interval))
                continue

            timeout = max(0.0, next_run_at - now)
            self.wake_event.wait(timeout=timeout)
            self.wake_event.clear()
            
    def trigger(self):
        """Force a single analysis run."""
        if self.state.analysis_running or self.analysis_lock.locked():
            return False
        self.state.analysis_running = True
        self._emit_status_update()
        threading.Thread(target=self._analyze, daemon=True).start()
        return True

    def set_auto_analyze(self, enabled: bool):
        self.state.auto_analyze = enabled
        self.immediate_requested = enabled
        if not enabled:
            self.state.analysis_running = False
        self.wake_event.set()

    def notify_config_changed(self, immediate: bool = False):
        if immediate:
            self.immediate_requested = True
        self.wake_event.set()

    def stop(self):
        self.running = False
        self.stop_event.set()
        self.wake_event.set()

    def _analyze(self):
        if not self.analysis_lock.acquire(blocking=False):
            logger.info("Skipping analysis because another inference is already running")
            return

        try:
            analysis_epoch = self.state.analysis_epoch
            self.state.analysis_running = True
            self.state.last_inference_error = ""
            self.state.last_inference_text = ""
            self.state.streaming_inference_text = ""
            self.state.streaming_source_id = self.state.selected_source_id
            emit_inference_stream_update(self.state, "", False)
            self._emit_status_update()

            frame = get_frame_for_selected_source(self.state)
            
            if frame is None:
                if self.state.selected_source_id != self.state.local_source_id:
                    deadline = time.time() + 2.5
                    while time.time() < deadline and frame is None:
                        time.sleep(0.1)
                        frame = get_frame_for_selected_source(self.state)
                if frame is None:
                    self.state.last_inference_error = f"No frame available yet for {self.state.selected_source_id}"
                    self.state.risk_explanation = f"No frame available yet for {self.state.selected_source_id}."
                    self._emit_status_update()
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
            if not success:
                self.state.last_inference_error = "Failed to encode current frame"
                self.state.risk_explanation = "Failed to encode current frame."
                self._emit_status_update()
                return

            fc.preview_bytes = buffer.tobytes()
            asyncio.run(self._run_inference(fc, analysis_epoch))
        finally:
            self.state.analysis_running = False
            self._emit_status_update()
            self.analysis_lock.release()
            
    async def _run_inference(self, frame_cap, analysis_epoch):
        def on_stream_chunk(text: str, done: bool = False):
            if analysis_epoch != self.state.analysis_epoch:
                return
            self.state.streaming_inference_text = text
            self.state.streaming_source_id = self.state.selected_source_id
            emit_inference_stream_update(self.state, text, done)

        try:
            _, result, _ = await self.engine.process_next_frame(
                scoring_model=self.state.scoring_model,
                frame=frame_cap,
                stream_handler=on_stream_chunk if self.state.show_inference_overlay else None,
            )
        except Exception as e:
            logger.error("Inference error: %s", e)
            if analysis_epoch != self.state.analysis_epoch:
                logger.info("Discarding stale inference error from epoch %s", analysis_epoch)
                return
            self.state.last_inference_error = str(e)
            self.state.risk_binary = False
            self.state.risk_score = 0.0
            self.state.risk_explanation = f"Error during inference: {e}"
            self.state.consecutive_risk_count = 0
            self.state.last_inference_text = ""
            self.state.streaming_inference_text = ""
            emit_inference_stream_update(self.state, "", True)
            return

        if analysis_epoch != self.state.analysis_epoch:
            logger.info("Discarding stale inference result from epoch %s", analysis_epoch)
            return

        self.state.risk_binary = result.risk
        self.state.risk_score = result.confidence
        self.state.risk_explanation = result.explanation
        self.state.last_inference_text = result.explanation
        self.state.streaming_inference_text = result.explanation if self.state.show_inference_overlay else ""
        self.state.last_inference_at = datetime.now(timezone.utc).isoformat()
        self.state.last_inference_latency_ms = result.latency_ms
        self.state.last_inference_model = result.model
        self.state.last_inference_error = ""
        emit_inference_stream_update(
            self.state,
            self.state.streaming_inference_text if self.state.show_inference_overlay else "",
            True,
        )
        self._emit_status_update()
        
        if result.risk:
            self.state.consecutive_risk_count += 1
            await self._check_alert()
        else:
            self.state.consecutive_risk_count = 0

    def _status_payload(self):
        return build_status_payload(self.state)

    def _emit_status_update(self):
        socketio.emit('status_update', self._status_payload())
            
    async def _check_alert(self):
        if self.state.consecutive_risk_count >= self.state.risk_threshold:
            now = time.time()
            if now - self.state.last_alert_time > self.state.alert_cooldown:
                msg = self.state.custom_msg or f"RISK DETECTED! Score: {self.state.risk_score:.2f}"
                payload = {
                    "timestamp": datetime.now().isoformat(),
                    "risk_score": self.state.risk_score,
                    "explanation": self.state.risk_explanation,
                    "message": msg
                }
                
                # 1. Send SMS
                if self.state.notifier.is_active and self.state.enable_sms and self.state.alert_receiver:
                    await self.state.notifier.send_sms(self.state.alert_receiver, msg)
                
                # 2. Send Webhook (n8n)
                if self.state.webhook_url and self.state.enable_webhook:
                    try:
                        await self.state.notifier.send_webhook(payload)
                        logger.info(f"Webhook sent to {self.state.webhook_url}")
                    except Exception as e:
                        logger.error(f"Webhook failed: {e}")

                self.state.last_alert_time = now


def initialize_backend():
    """Initialize backend services."""
    global app_state, prompt_store, inference_engine, analysis_thread
    
    logger.info("[BACKEND] Initializing backend services...")
    
    # 1. Ensure MediaMTX is running FIRST (before camera)
    import subprocess
    try:
        # Check if Media MTX is already running
        subprocess.check_call(["pgrep", "-x", "mediamtx"], stdout=subprocess.DEVNULL)
        logger.info("[BACKEND] MediaMTX already running")
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Not running, try to start
        mtx_path = "./temp/mediamtx"
        mtx_config = "./mediamtx.yml"  # Use our custom config
        if os.path.exists(mtx_path):
            logger.info("[BACKEND] Starting MediaMTX...")
            # Start MediaMTX with config file
            subprocess.Popen([mtx_path, mtx_config], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2)  # Wait for MediaMTX to start
            logger.info("[BACKEND] MediaMTX started")
        else:
            logger.warning(f"[BACKEND] MediaMTX binary not found at {mtx_path}")
    
    # Create AppState
    app_state = AppState()
    
    # 2. Start Camera Thread (will connect to MediaMTX)
    logger.info("[BACKEND] Starting CameraThread...")
    cam_thread = CameraThread(app_state)
    cam_thread.start()
    app_state.camera_thread = cam_thread
    
    # Initialize Prompt Store and Inference Engine
    prompt_store = PromptStore()
    ollama = OllamaClient()
    inference_engine = InferenceEngine(MockCamera(), prompt_store, ollama)
    
    # Start Analysis Thread
    logger.info("[BACKEND] Starting AnalysisThread...")
    analysis_thread = AnalysisThread(app_state, inference_engine)
    analysis_thread.start()
    app_state.analysis_thread = analysis_thread
    _refresh_local_source_state()
    
    logger.info("[BACKEND] Backend initialized successfully!")


def source_path_for(source_id: str) -> str:
    if source_id == app_state.local_source_id:
        return "camera"
    return source_id


def source_urls(source_id: str):
    path = source_path_for(source_id)
    return {
        "path": path,
        "rtsp_url": f"rtsp://127.0.0.1:8554/{path}",
        "webrtc_url": f"http://localhost:8889/{path}",
        "publish_url": f"http://localhost:8889/{path}/publish",
        "hls_url": f"http://localhost:8888/{path}/index.m3u8",
    }


def serialize_source(source: dict):
    urls = source_urls(source["id"])
    last_seen_ts = float(source.get("last_seen", 0.0) or 0.0)
    return {
        "id": source["id"],
        "label": source.get("label") or source["id"],
        "kind": source.get("kind", "remote"),
        "status": source.get("status", "offline"),
        "is_local": bool(source.get("is_local")),
        "last_seen": datetime.fromtimestamp(last_seen_ts, timezone.utc).isoformat() if last_seen_ts else "",
        **urls,
    }


def _refresh_local_source_state():
    source = app_state.sources.setdefault(
        app_state.local_source_id,
        {
            "id": app_state.local_source_id,
            "label": "AGX Local Camera",
            "kind": "local",
            "status": "online",
            "is_local": True,
        },
    )
    source["label"] = "AGX Local Camera"
    source["status"] = "online"
    source["kind"] = "local"
    source["is_local"] = True
    source["last_seen"] = time.time()
    source["updated_at"] = datetime.now(timezone.utc).isoformat()


def _mark_stale_sources_offline(timeout_seconds: float = 300.0):
    now = time.time()
    changed = False
    for source_id, source in app_state.sources.items():
        if source_id == app_state.local_source_id:
            continue
        last_seen = float(source.get("last_seen", 0.0) or 0.0)
        new_status = "online" if now - last_seen <= timeout_seconds else "offline"
        if source.get("status") != new_status:
            source["status"] = new_status
            changed = True
    return changed


def _sorted_sources():
    _refresh_local_source_state()
    _mark_stale_sources_offline()
    return [serialize_source(source) for source in sorted(app_state.sources.values(), key=lambda item: (not item.get("is_local", False), item.get("label", item["id"]).lower()))]


def upsert_remote_source(source_id: str, label: str):
    now = time.time()
    source = app_state.sources.get(source_id, {})
    source.update({
        "id": source_id,
        "label": label,
        "kind": "remote",
        "status": "online",
        "is_local": False,
        "last_seen": now,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    app_state.sources[source_id] = source
    return source


def emit_sources_update():
    if app_state is None:
        return
    payload = {
        "sources": _sorted_sources(),
        "selected_source_id": app_state.selected_source_id,
        "situation_room_client_id": app_state.situation_room_client_id,
    }
    socketio.emit("sources_update", payload)


def emit_inference_stream_update(state: AppState, text: str, done: bool):
    socketio.emit("inference_stream", {
        "source_id": state.streaming_source_id or state.selected_source_id,
        "text": text,
        "enabled": bool(state.show_inference_overlay),
        "done": bool(done),
        "timestamp": datetime.now().isoformat(),
    })


def stop_selected_source_thread():
    thread = getattr(app_state, "selected_source_thread", None)
    if thread and thread.is_alive():
        thread.stop()
        thread.join(timeout=1.0)
    app_state.selected_source_thread = None
    with app_state.lock:
        app_state.selected_frame = None


def ensure_selected_source_thread():
    stop_selected_source_thread()
    selected_id = app_state.selected_source_id
    if selected_id == app_state.local_source_id:
        return
    source = app_state.sources.get(selected_id)
    if not source or source.get("status") != "online":
        return
    thread = SelectedSourceFrameThread(app_state, selected_id, source_urls(selected_id)["rtsp_url"])
    thread.start()
    app_state.selected_source_thread = thread


def ensure_valid_selected_source():
    source = app_state.sources.get(app_state.selected_source_id)
    if source and source.get("status") == "online":
        return
    fallback_id = app_state.local_source_id
    if app_state.selected_source_id != fallback_id:
        set_selected_source(fallback_id)


def set_selected_source(source_id: str):
    source = app_state.sources.get(source_id)
    if source is None:
        return False, "Unknown source"
    if source.get("status") != "online" and source_id == app_state.local_source_id:
        return False, "Source is offline"
    if source_id != app_state.local_source_id and source.get("status") != "online":
        source["status"] = "online"
        source["last_seen"] = time.time()
        source["updated_at"] = datetime.now(timezone.utc).isoformat()
    app_state.selected_source_id = source_id
    app_state.selected_source_label = source.get("label") or source_id
    app_state.active_source_id = source_id
    reset_detection_state(f"Selected source switched to {app_state.selected_source_label}.")
    ensure_selected_source_thread()
    emit_sources_update()
    socketio.emit("status_update", build_status_payload(app_state))
    if app_state.auto_analyze and analysis_thread:
        analysis_thread.notify_config_changed(immediate=True)
    return True, ""


def build_status_payload(state: AppState):
    """Build the REST/WebSocket status payload from shared state."""
    return {
        'risk': state.risk_binary or state.sound_risk,
        'source_id': state.selected_source_id,
        'source_label': state.selected_source_label,
        'score': state.risk_score,
        'explanation': state.risk_explanation,
        'auto_analyze': state.auto_analyze,
        'analysis_interval': state.analysis_interval,
        'risk_threshold': state.risk_threshold,
        'consecutive_count': state.consecutive_risk_count,
        'analysis_running': state.analysis_running,
        'last_inference_at': state.last_inference_at,
        'last_inference_latency_ms': state.last_inference_latency_ms,
        'scoring_model': state.scoring_model,
        'last_inference_model': state.last_inference_model or state.scoring_model,
        'last_inference_error': state.last_inference_error,
        'last_inference_text': state.last_inference_text,
        'streaming_inference_text': state.streaming_inference_text,
        'show_inference_overlay': state.show_inference_overlay,
        'analysis_epoch': state.analysis_epoch,
        'alert_cooldown': state.alert_cooldown,
        'enable_sms': state.enable_sms,
        'enable_webhook': state.enable_webhook,
        'alert_receiver': state.alert_receiver,
        'custom_msg': state.custom_msg,
        'webhook_url': state.webhook_url,
        'ui_mode': state.ui_mode,
        'situation_room_client_id': state.situation_room_client_id,
        'sound_detection_enabled': state.enable_sound_detection,
        'sound_risk': state.sound_risk if hasattr(state, 'sound_risk') else False,
        'sound_label': state.sound_label if hasattr(state, 'sound_label') else None,
        'sound_score': state.sound_score if hasattr(state, 'sound_score') else 0.0,
        'sound_fps': state.sound_fps if hasattr(state, 'sound_fps') else 0.0,
        'sound_db': state.sound_db if hasattr(state, 'sound_db') else -120.0,
        'sound_threshold_db': state.sound_threshold_db if hasattr(state, 'sound_threshold_db') else -35.0,
        'timestamp': datetime.now().isoformat()
    }


def reset_detection_state(reason: str = ""):
    """Clear visible risk state and invalidate in-flight inference results."""
    app_state.analysis_epoch += 1
    app_state.analysis_running = False
    app_state.risk_binary = False
    app_state.risk_score = 0.0
    app_state.risk_explanation = reason
    app_state.consecutive_risk_count = 0
    app_state.last_inference_error = ""
    app_state.last_inference_text = ""
    app_state.streaming_inference_text = ""
    app_state.streaming_source_id = app_state.selected_source_id
    emit_inference_stream_update(app_state, "", True)


def get_frame_for_selected_source(state: AppState):
    with state.lock:
        if state.selected_source_id == state.local_source_id:
            return state.latest_frame.copy() if state.latest_frame is not None else None
        return state.selected_frame.copy() if state.selected_frame is not None else None


def normalize_audio_device(value):
    if not value or value == "default":
        return "default"
    if "hw:" in value:
        import re
        match = re.search(r'\((hw:\d+,\d+)\)', value)
        return match.group(1) if match else value
    if "pulse:" in value:
        import re
        match = re.search(r'\((pulse:[^)]+)\)', value)
        return match.group(1) if match else value
    return value


def normalize_source_id(value: str):
    text = (value or "browser-src").strip().lower()
    text = re.sub(r"[^a-z0-9_-]+", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text or "browser-src"


def stop_camera_thread():
    if app_state.camera_thread and app_state.camera_thread.is_alive():
        try:
            app_state.camera_thread.stop(timeout=3.0)
        except AttributeError:
            app_state.camera_thread.running = False
            app_state.camera_thread.join(timeout=2.0)
    app_state.camera_thread = None
    with app_state.lock:
        app_state.latest_frame = None
    _refresh_local_source_state()


def wait_for_camera_frame(timeout: float = 8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        with app_state.lock:
            if app_state.latest_frame is not None:
                return True
        time.sleep(0.1)
    return False


# ==================== REST API ENDPOINTS ====================

@app.route('/')
def index():
    """Serve main HTML page."""
    return send_from_directory('../static', 'index.html')

@app.route('/api/status')
def get_status():
    """Get current risk detection status."""
    return jsonify(build_status_payload(app_state))


@app.route('/api/sources')
def get_sources():
    return jsonify({
        "sources": _sorted_sources(),
        "selected_source_id": app_state.selected_source_id,
        "situation_room_client_id": app_state.situation_room_client_id,
    })


@app.route('/api/sources/register', methods=['POST'])
def register_source():
    data = request.json or {}
    source_id = normalize_source_id(data.get("source_id", "browser-src"))
    label = (data.get("label") or source_id).strip() or source_id
    source = upsert_remote_source(source_id, label)
    emit_sources_update()
    return jsonify({"success": True, "source": serialize_source(source)})


@app.route('/api/sources/heartbeat', methods=['POST'])
def heartbeat_source():
    data = request.json or {}
    source_id = normalize_source_id(data.get("source_id", "browser-src"))
    source = app_state.sources.get(source_id)
    if source is None:
        return jsonify({"success": False, "error": "Unknown source"}), 404
    source["status"] = "online"
    source["last_seen"] = time.time()
    source["updated_at"] = datetime.now(timezone.utc).isoformat()
    emit_sources_update()
    return jsonify({"success": True, "source": serialize_source(source)})


@app.route('/api/sources/select', methods=['POST'])
def select_source():
    data = request.json or {}
    source_id = normalize_source_id(data.get("source_id", ""))
    ok, message = set_selected_source(source_id)
    if not ok:
        return jsonify({"success": False, "error": message}), 400
    return jsonify({
        "success": True,
        "selected_source_id": app_state.selected_source_id,
        "status": build_status_payload(app_state),
    })


@app.route('/api/sources/disconnect', methods=['POST'])
def disconnect_source():
    data = request.json or {}
    source_id = normalize_source_id(data.get("source_id", ""))
    if not source_id:
        return jsonify({"success": False, "error": "Missing source_id"}), 400
    if source_id == app_state.local_source_id:
        return jsonify({"success": False, "error": "Local source cannot be disconnected"}), 400

    source = app_state.sources.get(source_id)
    if source is None:
        return jsonify({"success": False, "error": "Unknown source"}), 404

    was_selected = app_state.selected_source_id == source_id
    app_state.sources.pop(source_id, None)

    if was_selected:
        set_selected_source(app_state.local_source_id)
    else:
        emit_sources_update()
        socketio.emit("status_update", build_status_payload(app_state))

    return jsonify({
        "success": True,
        "disconnected_source_id": source_id,
        "selected_source_id": app_state.selected_source_id,
    })


@app.route('/api/mode', methods=['POST'])
def set_mode():
    data = request.json or {}
    requested_mode = data.get("mode", "camera")
    source_id = normalize_source_id(data.get("source_id", "browser-src"))
    register_source = bool(data.get("register_source", False))

    if requested_mode == "situation":
        app_state.ui_mode = "situation"
    else:
        if register_source:
            upsert_remote_source(source_id, (data.get("label") or source_id).strip() or source_id)

    emit_sources_update()
    return jsonify({
        "success": True,
        "mode": requested_mode,
        "situation_room_client_id": app_state.situation_room_client_id,
        "selected_source_id": app_state.selected_source_id,
    })

@app.route('/api/public-urls')
def get_public_urls():
    """Get optional public URLs created by run.sh/ngrok."""
    def read_url(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except OSError:
            return ""

    return jsonify({
        "ui": read_url("data/ngrok_url.txt"),
        "webrtc": read_url("data/ngrok_webrtc_url.txt")
    })


@app.route('/proxy/hls/<path:resource>')
def proxy_hls(resource: str):
    """Proxy MediaMTX HLS assets through the UI origin for remote HTTPS clients."""
    upstream = f"http://127.0.0.1:8888/{resource.lstrip('/')}"
    try:
        with urllib_request.urlopen(upstream, timeout=5) as resp:
            content = resp.read()
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            return Response(
                content,
                status=resp.status,
                content_type=content_type,
                headers={
                    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                },
            )
    except urllib_error.HTTPError as exc:
        return Response(exc.read(), status=exc.code, content_type=exc.headers.get("Content-Type", "text/plain"))
    except Exception as exc:
        logger.error("HLS proxy error for %s: %s", resource, exc)
        return Response(f"HLS proxy error: {exc}", status=502, content_type="text/plain")

@app.route('/api/metrics')
def get_metrics():
    """Get system resource metrics."""
    try:
        metrics = SystemMonitor().get_metrics()
        return jsonify(metrics)
    except Exception as e:
        logger.error(f"Metrics error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/analysis/trigger', methods=['POST'])
def trigger_analysis():
    """Trigger a single analysis."""
    try:
        started = analysis_thread.trigger()
        if not started:
            return jsonify({'success': False, 'busy': True, 'message': 'Analysis is already running'}), 409
        return jsonify({'success': True, 'message': 'Analysis triggered'})
    except Exception as e:
        logger.error(f"Trigger error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/analysis/auto', methods=['POST'])
def toggle_auto_analysis():
    """Enable/disable auto analysis."""
    data = request.json
    enabled = bool(data.get('enabled', data.get('auto_analyze', False)))
    if analysis_thread:
        analysis_thread.set_auto_analyze(enabled)
    else:
        app_state.auto_analyze = enabled
    
    # Reset risk if disabling
    if not enabled:
        reset_detection_state("Auto analysis disabled.")
        socketio.emit('status_update', build_status_payload(app_state))
    elif analysis_thread:
        analysis_thread.notify_config_changed(immediate=True)
    
    return jsonify({'success': True, 'enabled': enabled})

@app.route('/api/analysis/config', methods=['POST'])
def update_analysis_config():
    """Update analysis configuration."""
    data = request.json
    
    rerun_immediately = False

    if 'model' in data:
        # Unload previous model
        old_model = app_state.scoring_model
        if old_model and old_model != data['model']:
            try:
                OllamaClient.unload_model(old_model)
            except Exception as e:
                logger.error(f"Failed to unload model: {e}")
        app_state.scoring_model = data['model']
        app_state.last_inference_model = data['model']
        reset_detection_state(f"Switched model to {data['model']}. Waiting for next analysis.")
        rerun_immediately = True
        
    if 'interval' in data:
        app_state.analysis_interval = max(0.0, float(data['interval']))
        rerun_immediately = rerun_immediately or app_state.auto_analyze

    if 'threshold' in data:
        app_state.risk_threshold = max(1, int(data['threshold']))

    if 'show_inference_overlay' in data:
        app_state.show_inference_overlay = bool(data['show_inference_overlay'])
        if not app_state.show_inference_overlay:
            app_state.streaming_inference_text = ""
            emit_inference_stream_update(app_state, "", True)

    if analysis_thread:
        analysis_thread.notify_config_changed(immediate=rerun_immediately)
    
    status = build_status_payload(app_state)
    socketio.emit('status_update', status)
    return jsonify({'success': True, 'status': status})

@app.route('/api/config/twilio', methods=['POST'])
def save_twilio_config():
    """Save Twilio configuration."""
    data = request.json
    
    sid = data.get('sid', '')
    token = data.get('token', '')
    from_number = data.get('from_number', '')
    to_number = data.get('to_number', '')
    custom_msg = data.get('custom_msg', '')
    cooldown = data.get('cooldown', 300)
    
    if sid and token and from_number:
        app_state.notifier.configure(sid, token, from_number, app_state.webhook_url)
        app_state.alert_receiver = to_number
        app_state.custom_msg = custom_msg
        app_state.alert_cooldown = cooldown
        status = build_status_payload(app_state)
        socketio.emit('status_update', status)
        return jsonify({'success': True, 'status': status})
    else:
        return jsonify({'success': False, 'error': 'Missing required fields'}), 400

@app.route('/api/config/notifications', methods=['POST'])
def update_notification_settings():
    """Update notification settings (SMS/Webhook)."""
    data = request.json
    
    if 'enable_sms' in data:
        app_state.enable_sms = data['enable_sms']
        
    if 'enable_webhook' in data:
        app_state.enable_webhook = data['enable_webhook']
        
    if 'webhook_url' in data:
        app_state.webhook_url = data['webhook_url']
    app_state.notifier.webhook_url = app_state.webhook_url

    status = build_status_payload(app_state)
    socketio.emit('status_update', status)
    return jsonify({'success': True, 'status': status})

@app.route('/api/devices/video')
def get_video_devices_list():
    """Get available video devices."""
    try:
        devices = get_video_devices()
        current = app_state.camera_thread.device if app_state.camera_thread else None
        return jsonify({'devices': devices, 'current': current})
    except Exception as e:
        logger.error(f"Video devices error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/devices/audio')
def get_audio_devices_list():
    """Get available audio devices."""
    try:
        devices = get_audio_devices()
        current = getattr(app_state.camera_thread, 'audio_device', 'default') if app_state.camera_thread else 'default'
        return jsonify({'devices': devices, 'current': current})
    except Exception as e:
        logger.error(f"Audio devices error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/devices/switch', methods=['POST'])
def switch_device():
    """Switch video/audio device."""
    data = request.json
    video_device = data.get('video_device')
    audio_device = normalize_audio_device(data.get('audio_device', 'default'))
    enable_audio = data.get('enable_audio', False)
    
    try:
        previous_device = app_state.camera_thread.device if app_state.camera_thread else "/dev/video0"
        previous_audio_device = getattr(app_state, 'audio_device', 'default')
        previous_enable_audio = getattr(app_state, 'enable_audio', False)

        # Stop old camera thread
        stop_camera_thread()
        
        # Stop sound detection if running
        if app_state.sound_thread and app_state.sound_thread.is_alive():
            app_state.sound_thread.stop()
            app_state.sound_thread.join(timeout=1.0)
            app_state.sound_thread = None
        
        # Update state
        app_state.enable_audio = enable_audio
        app_state.audio_device = audio_device
        
        # Start new camera thread
        new_thread = CameraThread(app_state, device=video_device, audio_device=audio_device)
        new_thread.start()
        app_state.camera_thread = new_thread
        _refresh_local_source_state()
        if not wait_for_camera_frame():
            logger.error("No frames received from %s; rolling back to %s", video_device, previous_device)
            stop_camera_thread()
            app_state.enable_audio = previous_enable_audio
            app_state.audio_device = previous_audio_device
            rollback_thread = CameraThread(app_state, device=previous_device, audio_device=previous_audio_device)
            rollback_thread.start()
            app_state.camera_thread = rollback_thread
            _refresh_local_source_state()
            wait_for_camera_frame()
            if app_state.enable_sound_detection:
                app_state.sound_thread = SoundDetectionThread(
                    app_state,
                    device=previous_audio_device,
                    threshold_db=app_state.sound_threshold_db,
                )
                app_state.sound_thread.start()
            return jsonify({
                'success': False,
                'error': f'No frames received from {video_device}; rolled back to {previous_device}',
                'current': previous_device,
            }), 500
        
        # Restart sound detection if it was enabled
        if app_state.enable_sound_detection:
            app_state.sound_thread = SoundDetectionThread(
                app_state,
                device=audio_device,
                threshold_db=app_state.sound_threshold_db,
            )
            app_state.sound_thread.start()

        emit_sources_update()
        socketio.emit('status_update', build_status_payload(app_state))
        return jsonify({'success': True, 'message': f'Switched to {video_device}'})
    except Exception as e:
        logger.error(f"Device switch error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/sound/toggle', methods=['POST'])
def toggle_sound_detection():
    """Toggle sound detection."""
    data = request.json
    enabled = data.get('enabled', False)
    
    try:
        app_state.enable_sound_detection = enabled
        if 'threshold_db' in data:
            app_state.sound_threshold_db = float(data['threshold_db'])
        
        if enabled:
            if app_state.sound_thread is None or not app_state.sound_thread.is_alive():
                audio_device = getattr(app_state, 'audio_device', 'default')
                app_state.sound_thread = SoundDetectionThread(
                    app_state,
                    device=audio_device,
                    threshold_db=app_state.sound_threshold_db,
                )
                app_state.sound_thread.start()
        else:
            if app_state.sound_thread and app_state.sound_thread.is_alive():
                app_state.sound_thread.stop()
                app_state.sound_thread.join(timeout=1.0)
                app_state.sound_thread = None
            app_state.sound_risk = False
            app_state.sound_db = -120.0
        
        socketio.emit('status_update', build_status_payload(app_state))
        return jsonify({'success': True, 'enabled': enabled, 'status': build_status_payload(app_state)})
    except Exception as e:
        logger.error(f"Sound toggle error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/sound/config', methods=['POST'])
def update_sound_config():
    data = request.json
    try:
        if 'threshold_db' in data:
            app_state.sound_threshold_db = float(data['threshold_db'])
            if app_state.sound_thread and app_state.sound_thread.is_alive():
                app_state.sound_thread.threshold_db = app_state.sound_threshold_db
        socketio.emit('status_update', build_status_payload(app_state))
        return jsonify({'success': True, 'status': build_status_payload(app_state)})
    except Exception as e:
        logger.error(f"Sound config error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/prompt/current')
def get_current_prompt():
    """Get current risk detection prompt."""
    prompt = prompt_store.load()
    return jsonify({
        'text': prompt.text,
        'version': prompt.version,
        'timestamp': prompt.updated_at
    })

@app.route('/api/prompt/update', methods=['POST'])
def update_prompt():
    """Update risk detection prompt."""
    data = request.json
    text = data.get('text', '')
    
    if text:
        prompt = prompt_store.update(text=text)
        reset_detection_state("Risk criteria updated. Waiting for next analysis.")
        socketio.emit('status_update', build_status_payload(app_state))
        if app_state.auto_analyze and analysis_thread:
            analysis_thread.trigger()
        return jsonify({
            'success': True,
            'prompt': {
                'text': prompt.text,
                'version': prompt.version,
                'timestamp': prompt.updated_at
            },
            'status': build_status_payload(app_state)
        })
    else:
        return jsonify({'success': False, 'error': 'Empty prompt'}), 400

@app.route('/api/prompt/history')
def get_prompt_history():
    """Get prompt history."""
    history = prompt_store.get_history_texts()
    return jsonify({'history': history})

@app.route('/api/models/vision')
def get_vision_models():
    """Get available vision models."""
    try:
        models = OllamaClient.get_models(capability="vision")
        if not models:
            models = ["qwen3-vl:8b", "llama3.2-vision:11b", "minicpm-v:8b"]
        current = app_state.scoring_model
        return jsonify({'models': models, 'current': current})
    except Exception as e:
        logger.error(f"Models error: {e}")
        return jsonify({'models': ["qwen3-vl:8b"], 'current': 'qwen3-vl:8b'})


# ==================== WEBSOCKET EVENTS ====================

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection."""
    logger.info(f"Client connected: {request.sid}")
    emit('connected', {'message': 'Connected to VLM_Monitors'})

@socketio.on('disconnect')
def handle_disconnect():
    """Handle WebSocket disconnection."""
    logger.info(f"Client disconnected: {request.sid}")

@socketio.on('request_status')
def handle_request_status():
    """Handle request for current status."""
    emit('status_update', build_status_payload(app_state))
    emit('sources_update', {
        'sources': _sorted_sources(),
        'selected_source_id': app_state.selected_source_id,
        'situation_room_client_id': app_state.situation_room_client_id,
    })
    emit('inference_stream', {
        'source_id': app_state.streaming_source_id or app_state.selected_source_id,
        'text': app_state.streaming_inference_text,
        'enabled': bool(app_state.show_inference_overlay),
        'done': True,
        'timestamp': datetime.now().isoformat(),
    })


# Background thread to emit metrics periodically
def metrics_emitter():
    """Background thread to emit system metrics via WebSocket."""
    while True:
        try:
            metrics = SystemMonitor().get_metrics()
            socketio.emit('metrics_update', metrics)
            if app_state is not None:
                _refresh_local_source_state()
                changed = _mark_stale_sources_offline()
                previous_selected = app_state.selected_source_id
                ensure_valid_selected_source()
                selected_changed = previous_selected != app_state.selected_source_id
                if changed:
                    emit_sources_update()
                if selected_changed:
                    socketio.emit('status_update', build_status_payload(app_state))
        except Exception as e:
            logger.error(f"Metrics emitter error: {e}")
        time.sleep(2)  # Update every 2 seconds


if __name__ == '__main__':
    # Initialize backend
    initialize_backend()
    
    # Start metrics emitter thread
    metrics_thread = threading.Thread(target=metrics_emitter, daemon=True)
    metrics_thread.start()
    
    # Start Flask-SocketIO server
    logger.info("Starting Flask server on http://0.0.0.0:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False, allow_unsafe_werkzeug=True)
