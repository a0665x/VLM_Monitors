import threading
import time
import queue
import logging
from typing import Optional

import numpy as np

try:
    import sounddevice as sd
except Exception:  # pragma: no cover - optional dependency at runtime
    sd = None  # type: ignore

try:
    from transformers import pipeline
except Exception:  # pragma: no cover - optional dependency at runtime
    pipeline = None  # type: ignore

try:
    import torch
except Exception:  # pragma: no cover - optional dependency at runtime
    torch = None  # type: ignore

logger = logging.getLogger(__name__)


class SoundDetectionThread(threading.Thread):
    def __init__(
        self,
        state,
        device: Optional[str] = None,
        sample_rate: int = 16000,
        window_seconds: float = 1.0,
        model_name: Optional[str] = None,
        risk_threshold: float = 0.6,
        threshold_db: Optional[float] = None,
    ) -> None:
        super().__init__(daemon=True)
        self.state = state
        self.device = device
        self.sample_rate = sample_rate
        self.window_seconds = window_seconds
        self.model_name = model_name
        self.risk_threshold = risk_threshold
        self.threshold_db = threshold_db
        self.running = True
        self._audio_queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=20)
        self._stream = None
        self._classifier = None

    def stop(self) -> None:
        self.running = False
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

    def run(self) -> None:
        if sd is None:
            logger.error("Sound detection unavailable: sounddevice missing.")
            return

        try:
            self._load_model()
        except Exception as exc:
            logger.info("Using dB threshold sound detection: %s", exc)
            self._classifier = None

        try:
            self._stream = sd.InputStream(
                device=self._sounddevice_device(),
                channels=1,
                samplerate=self.sample_rate,
                dtype="float32",
                callback=self._audio_callback,
            )
            self._stream.start()
        except Exception as exc:
            logger.error("Failed to open audio device %s: %s", self.device, exc)
            return

        window_samples = int(self.sample_rate * self.window_seconds)
        buffer = np.zeros((0,), dtype=np.float32)

        while self.running:
            try:
                chunk = self._audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue

            if chunk.size == 0:
                continue

            buffer = np.concatenate([buffer, chunk[:, 0]])
            while buffer.size >= window_samples:
                window = buffer[:window_samples]
                buffer = buffer[window_samples:]
                self._infer(window)

        self.stop()

    def _load_model(self) -> None:
        if not self.model_name:
            raise RuntimeError("sound classifier disabled")
        if pipeline is None:
            raise RuntimeError("transformers pipeline is not installed")
        device_id = -1
        if torch is not None and torch.cuda.is_available():
            device_id = 0
        self._classifier = pipeline(
            "audio-classification",
            model=self.model_name,
            device=device_id,
        )

    def _sounddevice_device(self):
        if not self.device or self.device == "default":
            return None
        if isinstance(self.device, str) and self.device.startswith("pulse:"):
            return self.device.split(":", 1)[1] or None
        return self.device

    def _audio_callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.debug("Audio callback status: %s", status)
        try:
            self._audio_queue.put_nowait(indata.copy())
        except queue.Full:
            pass

    def _infer(self, audio_window: np.ndarray) -> None:
        start = time.perf_counter()
        # Remove DC offset to get true AC noise levels
        audio_window = audio_window - np.mean(audio_window)
        
        # Fix unscaled 16-bit float data from ALSA/PulseAudio
        if np.max(np.abs(audio_window)) > 2.0:
            audio_window = audio_window / 32768.0
            
        rms = float(np.sqrt(np.mean(np.square(audio_window))) + 1e-9)
        db = max(-120.0, min(0.0, 20.0 * np.log10(rms)))

        label = "volume"
        score = min(1.0, max(0.0, (db + 80.0) / 80.0))
        if self._classifier is not None:
            try:
                results = self._classifier(
                    {"array": audio_window, "sampling_rate": self.sample_rate}
                )
                top = results[0] if results else {"label": "unknown", "score": 0.0}
                label = str(top.get("label", "unknown"))
                score = float(top.get("score", 0.0))
            except Exception as exc:
                logger.error("Sound classification failed: %s", exc)

        elapsed = max(time.perf_counter() - start, 1e-6)
        fps = 1.0 / elapsed

        threshold_db = self.threshold_db
        if threshold_db is None:
            threshold_db = getattr(self.state, "sound_threshold_db", -35.0)
        sound_risk = db >= float(threshold_db)

        with self.state.lock:
            self.state.sound_risk = sound_risk
            self.state.sound_score = score
            self.state.sound_label = label
            self.state.sound_fps = fps
            self.state.sound_db = db
            self.state.sound_threshold_db = float(threshold_db)
            self.state.sound_last_ts = time.time()
