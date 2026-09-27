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


def test_idle_release_waits_and_skips_active_monitor(monkeypatch):
    state=AppState();calls=[];clock=[1000.0]
    monkeypatch.setattr(server.time,'monotonic',lambda:clock[0])
    thread=server.AnalysisThread(state,SimpleNamespace(ollama_client=SimpleNamespace(unload_model=lambda model:calls.append(model))))
    state.inference_backend='ollama';thread.last_model_use=1000;thread.model_idle_seconds=300
    clock[0]=1299;thread.release_idle_models();assert calls==[]
    clock[0]=1301;state.auto_analyze=True;thread.release_idle_models();assert calls==[]
    thread.set_auto_analyze(False)
    thread.release_idle_models();assert calls==[]  # Stopping starts a new grace period.
    clock[0]=1602;state.analysis_running=True;thread.release_idle_models();assert calls==[]
    state.analysis_running=False
    thread.analysis_lock.acquire();thread.release_idle_models();assert calls==[];thread.analysis_lock.release()
    thread.release_idle_models();assert calls==[state.scoring_model]
    thread.release_idle_models();assert calls==[state.scoring_model]  # Unload once.
    assert not thread.analysis_lock.locked()


def test_new_analysis_extends_idle_deadline(monkeypatch):
    state=AppState();calls=[];clock=[1000.0]
    monkeypatch.setattr(server.time,'monotonic',lambda:clock[0])
    thread=server.AnalysisThread(state,SimpleNamespace(ollama_client=SimpleNamespace(unload_model=lambda model:calls.append(model))))
    thread.model_idle_seconds=300;thread.last_model_use=1000
    clock[0]=1250
    monkeypatch.setattr(server,'get_frame_for_selected_source',lambda state:None)
    monkeypatch.setattr(thread,'_emit_status_update',lambda:None)
    monkeypatch.setattr(server,'emit_inference_stream_update',lambda *args:None)
    thread._analyze()
    assert thread.last_model_use==1250 and calls==[]
    clock[0]=1500;thread.release_idle_models();assert calls==[]
    clock[0]=1551;thread.release_idle_models();assert calls==[state.scoring_model]
