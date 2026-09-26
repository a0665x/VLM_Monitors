"""Single-worker service entrypoint (camera and state are process-local)."""
import threading
from src.server import app, initialize_backend, metrics_emitter

initialize_backend()
threading.Thread(target=metrics_emitter, daemon=True).start()
