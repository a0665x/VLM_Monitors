import threading
import time
from services.notifier import TwilioNotifier

class AppState:
    def __init__(self):
        self.lock = threading.Lock()
        self.latest_frame = None
        self.selected_frame = None
        self.risk_score = 0.0
        self.risk_binary = False
        self.risk_explanation = ""
        self.consecutive_risk_count = 0
        self.analysis_running = False
        self.last_inference_at = ""
        self.last_inference_latency_ms = 0
        self.last_inference_model = ""
        self.last_inference_error = ""
        self.last_inference_text = ""
        self.streaming_inference_text = ""
        self.streaming_source_id = ""
        self.analysis_epoch = 0
        
        # Settings
        self.auto_analyze = False
        self.analysis_interval = 5.0
        self.scoring_model = "qwen3-vl:8b"
        self.risk_threshold = 3
        self.show_inference_overlay = False
        self.alert_cooldown = 60.0
        self.last_alert_time = 0.0
        self.enable_audio = False # New: Audio Toggle
        self.audio_device = "default"

        # Sound detection
        self.enable_sound_detection = False
        self.sound_risk = False
        self.sound_score = 0.0
        self.sound_label = ""
        self.sound_fps = 0.0
        self.sound_last_ts = 0.0
        self.sound_db = -120.0
        self.sound_threshold_db = -35.0
        
        # Notifier
        self.notifier = TwilioNotifier()
        self.alert_receiver = ""
        self.custom_msg = ""
        self.webhook_url = ""
        self.enable_sms = False
        self.enable_webhook = False

        # Multi-source situation room
        self.local_source_id = "agx-local"
        self.selected_source_id = self.local_source_id
        self.selected_source_label = "AGX Local Camera"
        self.active_source_id = self.local_source_id
        self.ui_mode = "situation"
        self.situation_room_client_id = ""
        self.sources = {
            self.local_source_id: {
                "id": self.local_source_id,
                "label": self.selected_source_label,
                "kind": "local",
                "path": "camera",
                "status": "online",
                "last_seen": time.time(),
                "updated_at": "",
                "is_local": True,
            }
        }
        
        # Thread references
        self.camera_thread = None
        self.analysis_thread = None
        self.sound_thread = None
        self.selected_source_thread = None
