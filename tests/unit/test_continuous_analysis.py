import json
import numpy as np
import src.server as server
from src.shared.state import AppState


def test_continuous_latest_frame_only_and_no_status_churn(monkeypatch):
    state=AppState();state.continuous_analysis=True;state.auto_analyze=True
    worker=server.AnalysisThread(state,None);calls=[];updates=[]
    monkeypatch.setattr(worker,'_emit_status_update',lambda:updates.append(True))
    monkeypatch.setattr(server,'emit_inference_stream_update',lambda *args:None)
    async def infer(frame,epoch):calls.append(frame)
    monkeypatch.setattr(worker,'_run_inference',infer)
    worker._analyze()
    assert not calls and not updates
    state.latest_frame=np.zeros((8,8,3),dtype=np.uint8);state.latest_frame_at=1
    worker._analyze();count=len(updates);worker._analyze()
    assert len(calls)==1 and len(updates)==count
    state.latest_frame_at=4 # Intermediate frames are superseded, never queued.
    worker._analyze();assert len(calls)==2
    state.selected_source_id='phone';state.selected_frame=state.latest_frame;state.selected_frame_at=1
    worker._analyze();worker._analyze();assert len(calls)==3
    state.selected_frame_at=2;worker._analyze();assert len(calls)==4


def test_continuous_checkbox_preserves_interval_and_persists(monkeypatch,tmp_path):
    state=AppState();state.analysis_interval=12
    monkeypatch.setattr(server,'app_state',state)
    monkeypatch.setattr(server,'analysis_thread',None)
    target=tmp_path/'analysis.json';monkeypatch.setattr(server,'ANALYSIS_SETTINGS_PATH',target)
    client=server.app.test_client()
    response=client.post('/api/analysis/config',json={'continuous_analysis':True})
    assert response.status_code==200 and response.json['status']['continuous_analysis']
    assert state.analysis_interval==12 and json.loads(target.read_text())['continuous_analysis']
    client.post('/api/analysis/config',json={'continuous_analysis':False})
    assert not state.continuous_analysis and state.analysis_interval==12
    assert client.post('/api/analysis/config',json={'continuous_analysis':'yes'}).status_code==400


def test_continuous_scheduler_does_not_wait_configured_interval(monkeypatch):
    import time
    state=AppState();state.continuous_analysis=True;state.auto_analyze=True;state.analysis_interval=60
    worker=server.AnalysisThread(state,None);calls=[]
    def analyze():
        calls.append(time.monotonic())
        if len(calls)==2:worker.stop()
        return True
    monkeypatch.setattr(worker,'_analyze',analyze)
    worker.start();worker.join(timeout=1)
    worker.stop();worker.join(timeout=1)
    assert len(calls)==2 and calls[1]-calls[0]<1
