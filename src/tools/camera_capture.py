import cv2
import base64
import logging
from shared.state import AppState
from tools.registry import registry

logger = logging.getLogger(__name__)

from adapters.ollama_client import OllamaClient
import httpx
import json

@registry.register
def capture_current_frame(state: AppState = None):
    """
    Captures the current frame and generates a detailed description using a Vision LLM.
    
    Args:
        state (AppState): The shared application state.
        
    Returns:
        str: A detailed description of the image.
    """
    try:
        frame = None
        with state.lock:
            if state.latest_frame is not None:
                frame = state.latest_frame.copy()
        
        if frame is None:
            return "Error: No frame available from camera."
            
        # Encode to JPEG then Base64
        bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        success, buffer = cv2.imencode(".jpg", bgr_frame)
        
        if not success:
            return "Error: Failed to encode frame."
            
        b64_image = base64.b64encode(buffer).decode('utf-8')
        
        # Generate Description
        model_name = "llava-llama3:8b"
        prompt = "Describe this image, starting from a high-level concept and moving to fine details."
        
        try:
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": model_name,
                "prompt": prompt,
                "images": [b64_image],
                "stream": False
            }
            
            with httpx.Client(timeout=60.0) as client:
                resp = client.post(url, json=payload)
                if resp.status_code == 200:
                    data = resp.json()
                    description = data.get("response", "No description generated.")
                    return f"Image Description:\n{description}"
                else:
                    return f"Error from Ollama: {resp.status_code} - {resp.text}"
            
        except Exception as e:
            logger.error(f"Error generating description: {e}")
            return f"Error generating description: {e}"
            
        finally:
            # Unload the model to free resources
            try:
                OllamaClient.unload_model(model_name)
                logger.info(f"Unloaded model: {model_name}")
            except Exception as e:
                logger.warning(f"Failed to unload model {model_name}: {e}")

    except Exception as e:
        logger.error(f"Error capturing frame: {e}")
        return f"Error capturing frame: {str(e)}"
