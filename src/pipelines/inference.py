"""Inference orchestration for the monitoring loop."""
from __future__ import annotations

import re
import time
import logging
import os
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional, Protocol, Tuple

from adapters.ollama_client import OllamaResponse
from services.prompts import PromptStore, RiskPrompt
from .camera import CameraSource, FrameCapture

logger = logging.getLogger(__name__)


@dataclass
class InferenceResult:
    frame_id: str
    model: str
    latency_ms: int
    risk: bool
    confidence: float
    explanation: str


@dataclass
class AlertState:
    state: str
    active_frame_id: Optional[str]
    message: str
    acknowledged_at: Optional[str] = None
    timestamp: str = "" # Added for new pipeline


class OllamaClientProtocol(Protocol):
    async def generate(self, system_prompt: str, user_prompt: str, image_bytes: Optional[bytes] = None, model: Optional[str] = None) -> OllamaResponse:  # pragma: no cover - interface definition only
        ...


class InferenceEngine:
    def __init__(
        self,
        camera: CameraSource,
        prompt_store: PromptStore,
        ollama_client: OllamaClientProtocol,
    ) -> None:
        self.camera = camera
        self.prompt_store = prompt_store
        self.ollama_client = ollama_client
        self.last_frame: Optional[FrameCapture] = None
        
        # Binary classification state
        self.current_risk = False
        self.alert_state = AlertState(
            state="monitoring",
            active_frame_id=None,
            message="Monitoring",
            timestamp="",
        )
        
        # Frame logging setup
        self.log_dir = Path("temp")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "llm.log"

    async def process_next_frame(
        self,
        scoring_model: str = "llama3.2-vision:11b",
        frame: Optional[FrameCapture] = None,
        stream_handler: Optional[Callable[[str, bool], None]] = None,
    ) -> Tuple[FrameCapture, InferenceResult, AlertState]:
        """
        Captures a frame (if not provided) and runs the inference pipeline.
        """
        prompt = self.prompt_store.load()
        if frame is None:
            frame = self.camera.capture_frame(prompt_version=prompt.version)
        self.last_frame = frame

        start_time = time.time()
        
        # Log Session Start
        self._log_session_start()

        if not frame.preview_bytes:
            explanation = "No frame available from stream; start camera/WebRTC first."
            logger.warning(explanation)
            result = InferenceResult(
                frame_id=frame.id,
                model=scoring_model,
                risk=False,
                confidence=0.0,
                explanation=explanation,
                latency_ms=0,
            )
            alert = AlertState(
                state="monitoring",
                active_frame_id=frame.id,
                message=explanation,
                timestamp=frame.timestamp,
            )
            self.alert_state = alert
            return frame, result, alert

        # 1-Stage: Direct Vision Inference
        try:
            is_risk, explanation = await self._run_1_stage_inference(
                frame,
                prompt.text,
                scoring_model,
                stream_handler=stream_handler,
            )
        except Exception as e:
            logger.error(f"Inference failed for model {scoring_model}: {e}")
            # Return a safe fallback result instead of crashing
            is_risk = False
            explanation = f"Error during inference: {str(e)}"
            
        model_name = scoring_model
        
        # Update state
        self.current_risk = is_risk
        
        # Log frame if risk detected (or always, as per previous request, but let's stick to risk for now to save space, 
        # actually user asked for "logging" generally, let's keep _log_frame called always if we want strictly following "short_cut.jpg")
        # The previous code logged frame always to short_cut.jpg.
        self._log_frame(frame)
        
        latency_ms = int((time.time() - start_time) * 1000)

        result = InferenceResult(
            frame_id=frame.id,
            model=model_name,
            risk=is_risk,
            confidence=1.0 if is_risk else 0.0,
            explanation=explanation,
            latency_ms=latency_ms,
        )

        alert = AlertState(
            state="risk" if is_risk else "monitoring",
            active_frame_id=frame.id,
            message="Risk detected" if is_risk else "Safe",
            timestamp=frame.timestamp,
        )
        self.alert_state = alert

        logger.info(
            "frame=%s risk=%s conf=%.2f latency=%sms",
            result.frame_id,
            result.risk,
            result.confidence,
            result.latency_ms,
        )

        return frame, result, alert

    async def _run_1_stage_inference(
        self,
        frame: FrameCapture,
        criteria: str,
        model: str,
        stream_handler: Optional[Callable[[str, bool], None]] = None,
    ) -> Tuple[bool, str]:
        """1-Stage: Ask VLM directly if the image matches risk criteria."""
        system_prompt = (
            "You are a risk assessment engine. "
            "Analyze the image against the Risk Criteria. "
            "Answer ONLY 'YES' if the image matches the risk criteria, or 'NO' if it does not. "
            "Then provide a brief explanation."
        )
        user_prompt = (
            f"Risk Criteria: {criteria}\n\n"
            "Does this image match the risk criteria? Start with YES or NO."
        )
        
        try:
            if stream_handler is not None and hasattr(self.ollama_client, "generate_stream"):
                response = await self.ollama_client.generate_stream(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    image_bytes=frame.preview_bytes,
                    model=model,
                    on_chunk=stream_handler,
                )
            else:
                response = await self.ollama_client.generate(
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    image_bytes=frame.preview_bytes,
                    model=model
                )
        except TypeError as e:
            if "model" not in str(e):
                raise
            response = await self.ollama_client.generate(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                image_bytes=frame.preview_bytes
            )
        
        self._log_interaction("1-Stage Vision", model, system_prompt, user_prompt, response.text)
        
        text_lower = response.text.lower().strip()
        # Stricter parsing: Check for explicit YES/NO at start, or "yes" word. 
        # Use regex to handle punctuation like "Yes." or "Yes,"
        import re
        
        # Check for "Yes" at the start (ignoring case/whitespace)
        if re.match(r'^\s*(yes|YES)(\b|[.,!])', text_lower):
            is_risk = True
        elif re.match(r'^\s*(no|NO)(\b|[.,!])', text_lower):
            is_risk = False
        else:
            # Fall back to the adapter's risk flag, then a whole-word YES scan.
            is_risk = bool(getattr(response, "risk", False) or re.search(r'\byes\b', text_lower))
            
        return is_risk, response.text



    def _log_frame(self, frame: FrameCapture) -> None:
        """Save current frame to temp/short_cut.jpg (non-blocking)."""
        if not frame.preview_bytes:
            return
        # Run in executor to avoid blocking the event loop with disk I/O
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._save_frame_sync, frame)
        except RuntimeError:
            # Fallback if no loop (e.g. tests)
            self._save_frame_sync(frame)

    def _save_frame_sync(self, frame: FrameCapture) -> None:
        try:
            filename = self.log_dir / "short_cut.jpg"
            import cv2
            import numpy as np
            import os
            
            if not frame.preview_bytes:
                logger.warning("Cannot save frame: empty preview_bytes")
                return
            
            # Decode frame
            nparr = np.frombuffer(frame.preview_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if img is None:
                logger.error("Failed to decode frame buffer")
                return
            
            # Try to remove old file if it exists and has permission issues
            if filename.exists():
                try:
                    os.remove(str(filename))
                except PermissionError:
                    logger.warning(f"Could not remove old {filename} (permission denied), trying to overwrite")
            
            # Write new frame
            success = cv2.imwrite(str(filename), img)
            if not success:
                logger.error(f"cv2.imwrite failed for {filename}")
            else:
                logger.debug(f"Saved frame to {filename}")
                
        except Exception as e:
            logger.error(f"Failed to log frame: {e}", exc_info=True)

    def acknowledge_alert(self) -> None:
        self.current_risk = False
        self.alert_state = AlertState(
            state="monitoring",
            active_frame_id=None,
            message="Acknowledged",
            acknowledged_at=datetime.now().isoformat(),
            timestamp=datetime.now().isoformat(),
        )

    def _log_session_start(self) -> None:
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._log_session_start_sync)
        except RuntimeError:
            self._log_session_start_sync()

    def _log_session_start_sync(self) -> None:
        try:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            separator = "=" * 80
            with open(self.log_file, "a") as f:
                f.write(f"\n{separator}\n[{timestamp}] SESSION START\n{separator}\n")
        except Exception:
            pass

    def _log_interaction(self, stage: str, model: str, system: str, user: str, output: str) -> None:
        """Log full interaction details (non-blocking)."""
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, self._log_interaction_sync, stage, model, system, user, output)
        except RuntimeError:
            self._log_interaction_sync(stage, model, system, user, output)

    def _log_interaction_sync(self, stage: str, model: str, system: str, user: str, output: str) -> None:
        try:
            separator = "-" * 80
            log_entry = (
                f"[{stage}]\n"
                f"Model: {model}\n"
                f"System Prompt: {system}\n"
                f"User Prompt: {user}\n"
                f"Output: {output}\n"
                f"{separator}\n"
            )
            with open(self.log_file, "a") as f:
                f.write(log_entry)
        except Exception as e:
            logger.error(f"Failed to log interaction: {e}")


__all__ = ["InferenceEngine", "InferenceResult", "AlertState"]
