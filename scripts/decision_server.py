#!/usr/bin/env python3
"""CPU-only coordinator; a disposable process owns every CUDA allocation."""
import multiprocessing
import os
import sys
import threading
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from services.decisions import validate_settings

MODEL = os.getenv('DECISION_MODEL', 'Qwen/Qwen2.5-1.5B-Instruct')
IDLE_SECONDS = max(5, int(os.getenv('MODEL_IDLE_SECONDS', '300')))
app = FastAPI()
lock = threading.Lock()
process = connection = None
loaded = False
last_used = 0
load_error = ''
stopping = threading.Event()


def worker_main(pipe):
    # Import torch only inside this child. Termination releases its CUDA context.
    try:
        from scripts.decision_model import classify, Request
        while True:
            body = pipe.recv()
            try:
                pipe.send({'result': classify(Request(**body))})
            except HTTPException as exc:
                pipe.send({'error': str(exc.detail), 'status': exc.status_code})
            except Exception as exc:
                pipe.send({'error': str(exc), 'status': 503})
    except (EOFError, BrokenPipeError):
        pass
    finally:
        pipe.close()


def stop_worker():
    global process, connection, loaded
    if process is not None:
        if process.is_alive(): process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        process.close()
    if connection is not None: connection.close()
    process = connection = None
    loaded = False


def reap_idle():
    while not stopping.wait(2):
        if not lock.acquire(blocking=False): continue
        try:
            if process is not None and (not process.is_alive() or time.monotonic()-last_used >= IDLE_SECONDS):
                stop_worker()
        finally:
            lock.release()


@app.on_event('startup')
def startup():
    stopping.clear()
    threading.Thread(target=reap_idle, daemon=True).start()


@app.on_event('shutdown')
def shutdown():
    stopping.set()
    with lock: stop_worker()


@app.get('/health')
def health():
    return {'ready': True, 'loaded': loaded, 'model': MODEL,
            'idle_timeout_seconds': IDLE_SECONDS, 'device': 'on-demand', 'state': 'loaded' if loaded else 'standby',
            'error': load_error, 'calibrated': False, 'method': 'batched_candidate_logits'}


class Request(BaseModel):
    observations: str = Field(min_length=1, max_length=12000)
    scenarios: list[str]


@app.post('/classify')
def classify(body: Request):
    global process, connection, loaded, last_used, load_error
    try:
        validate_settings({'mode': 'parallel_decision', 'scenarios': body.scenarios})
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if not lock.acquire(blocking=False):
        raise HTTPException(409, 'Decision model is busy')
    try:
        if process is None or not process.is_alive():
            stop_worker()
            context = multiprocessing.get_context('spawn')
            connection, child = context.Pipe()
            process = context.Process(target=worker_main, args=(child,), daemon=True)
            process.start()
            child.close()
        connection.send(body.model_dump())
        if not connection.poll(85):
            raise TimeoutError('Classifier request timed out')
        response = connection.recv()
        if 'error' in response:
            raise HTTPException(response.get('status', 503), response['error'])
        loaded = True
        load_error = ''
        last_used = time.monotonic()
        return response['result']
    except Exception as exc:
        load_error = str(exc.detail) if isinstance(exc, HTTPException) else str(exc)
        stop_worker()
        if isinstance(exc, HTTPException): raise
        raise HTTPException(503, 'Classifier worker failed; retry analysis') from exc
    finally:
        lock.release()


@app.post('/unload')
def unload():
    if not lock.acquire(blocking=False):
        raise HTTPException(409, 'Classifier is busy')
    try:
        stop_worker()
        return {'success': True, 'loaded': False}
    finally:
        lock.release()


@app.post('/keepalive')
def keepalive():
    global last_used
    # Never start or load a worker merely because a client renews its lease.
    last_used = time.monotonic()
    return {'success': True, 'loaded': loaded}
