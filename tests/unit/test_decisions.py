import asyncio
import copy
import threading
from types import SimpleNamespace
import pytest
from src import server
from shared.state import AppState
from services.decisions import validate_results, validate_settings


def result():
    return {'person': {'state': 'present', 'probabilities': {'present': .8, 'absent': .1, 'unknown': .1}}}


@pytest.mark.parametrize('data', [None, {}, {'mode':'other'}, {'mode':'parallel_decision','scenarios':[]}, {'mode':'direct','scenarios':['custom']}, {'mode':'direct','scenarios':['person','person']}])
def test_reject_invalid_selection(data):
    with pytest.raises(ValueError): validate_settings(data)


@pytest.mark.parametrize('value', [float('nan'),float('inf'),-1,2,True])
def test_reject_invalid_probabilities(value):
    data=result();data['person']['probabilities']['present']=value
    with pytest.raises(ValueError):validate_results(data,['person'])


def test_distribution_and_identity_validation():
    assert validate_results(result(),['person'])==result()
    with pytest.raises(ValueError):validate_results(result(),['fire'])
    data=result();data['person']['probabilities']['present']=.2
    with pytest.raises(ValueError):validate_results(data,['person'])
    data=result();data['person']['state']='absent'
    with pytest.raises(ValueError):validate_results(data,['person'])


def test_mode_atomic_switch_and_busy(monkeypatch,tmp_path):
    monkeypatch.chdir(tmp_path)
    state=AppState();state.decision_history=[{'old':True}]
    monkeypatch.setattr(server,'app_state',state)
    lock=threading.Lock()
    monkeypatch.setattr(server,'analysis_thread',SimpleNamespace(analysis_lock=lock))
    monkeypatch.setattr(server,'decision_health',lambda:{'ready':False})
    client=server.app.test_client();payload={'mode':'parallel_decision','scenarios':['person']}
    assert client.post('/api/settings/decisions',json=payload).status_code==503
    assert state.decision_settings['mode']=='direct'
    monkeypatch.setattr(server,'decision_health',lambda:{'ready':True})
    with lock: assert client.post('/api/settings/decisions',json=payload).status_code==409
    assert client.post('/api/settings/decisions',json=payload).status_code==200
    assert state.decision_settings==payload and state.decision_history==[]
    assert (tmp_path/'temp/decision-settings.json').exists()


def test_parallel_result_history_and_no_alerts(monkeypatch):
    state=AppState();state.decision_settings={'mode':'parallel_decision','scenarios':['person']}
    engine=SimpleNamespace(ollama_client=object())
    thread=server.AnalysisThread(state,engine)
    calls=[]
    async def classify(*args):
        return {'results':result(),'observations':'A person is visible.','vision_model':'vision', 'decision_model':'text','vision_ms':10,'decision_ms':2,'total_ms':12,'calibrated':False}
    async def alert(): calls.append('alert')
    monkeypatch.setattr(server,'analyze_decisions',classify)
    monkeypatch.setattr(thread,'_check_alert',alert)
    frame=SimpleNamespace(id='f1',timestamp='2026-09-26T01:00:00Z',preview_bytes=b'jpeg')
    asyncio.run(thread._run_inference(frame,0))
    assert state.decision_result['results']==result()
    assert state.decision_history[0]['frame_id']=='f1'
    assert not state.risk_binary and not calls
    state.analysis_epoch=1
    asyncio.run(thread._run_inference(frame,0))
    assert len(state.decision_history)==1


def test_classifier_failure_not_a_negative_decision(monkeypatch):
    state=AppState();state.decision_settings={'mode':'parallel_decision','scenarios':['person']}
    thread=server.AnalysisThread(state,SimpleNamespace(ollama_client=object()))
    state.auto_analyze=True
    async def fail(*args):raise ValueError('model unavailable')
    monkeypatch.setattr(server,'analyze_decisions',fail)
    asyncio.run(thread._run_inference(SimpleNamespace(preview_bytes=b'jpeg'),0))
    assert state.last_inference_error=='model unavailable'
    assert not state.auto_analyze
    assert state.decision_result is None and state.decision_history==[]


def test_unknown_evidence_abstains_without_fake_probabilities():
    from services.decisions import extract_evidence
    assert extract_evidence('person: PRESENT, visible face\nfire: UNKNOWN',['person','fire','smoke']) == {'person':'PRESENT, visible face','fire':None,'smoke':None}
    payload={'fire':{'state':'unknown','probabilities':None,'abstained':True}}
    assert validate_results(payload,['fire'])==payload
    payload['fire']['state']='absent'
    with pytest.raises(ValueError):validate_results(payload,['fire'])


def test_offline_classifier_blocks_start_without_vision(monkeypatch):
    state=AppState();state.decision_settings={'mode':'parallel_decision','scenarios':['person','fire']}
    monkeypatch.setattr(server,'app_state',state)
    monkeypatch.setattr(server,'decision_health',lambda:{'ready':False})
    monkeypatch.setattr(server,'analysis_thread',SimpleNamespace())
    client=server.app.test_client()
    assert client.post('/api/analysis/trigger').status_code==503
    assert client.post('/api/analysis/auto',json={'enabled':True}).status_code==503
    assert not state.auto_analyze


def test_preflight_failure_never_generates_vision(monkeypatch):
    from services import decisions
    class Offline:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,*args):raise decisions.httpx.ConnectError('offline')
    monkeypatch.setattr(decisions.httpx,'AsyncClient',Offline)
    with pytest.raises(ValueError,match='Classifier unavailable'):
        asyncio.run(decisions.analyze_frame(object(),'vision',b'jpeg',['person']))


def test_idle_release_skips_active_monitor(monkeypatch):
    state=AppState();calls=[]
    thread=server.AnalysisThread(state,SimpleNamespace(ollama_client=SimpleNamespace(unload_model=lambda model:calls.append(model))))
    state.inference_backend='ollama';state.auto_analyze=True
    thread.release_idle_models();assert calls==[]
    state.auto_analyze=False
    thread.release_idle_models();assert calls==[state.scoring_model]
    assert not thread.analysis_lock.locked()
