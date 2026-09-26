import json
import threading
from types import SimpleNamespace
from src import server
from shared.state import AppState
from services import tailnet


def setup_engine(monkeypatch, tmp_path, models):
    monkeypatch.chdir(tmp_path)
    state = AppState()
    monkeypatch.setattr(server, 'app_state', state)
    monkeypatch.setattr(server, 'analysis_thread', SimpleNamespace(analysis_lock=threading.Lock()))
    old = object()
    monkeypatch.setattr(server, 'inference_engine', SimpleNamespace(ollama_client=old))
    client = SimpleNamespace(get_models=lambda **kw: models)
    monkeypatch.setattr(server, 'create_inference_client', lambda *args: client)
    return state, old, client


def test_engine_switch_persists_and_replaces_client(monkeypatch, tmp_path):
    state, old, client = setup_engine(monkeypatch, tmp_path, ['vision'])
    response = server.app.test_client().post('/api/settings/engine', json={'backend':'vllm', 'model':'vision'})
    assert response.status_code == 200
    assert state.inference_backend == 'vllm'
    assert server.inference_engine.ollama_client is client
    assert json.loads((tmp_path/'temp/engine-settings.json').read_text()) == {'backend':'vllm','model':'vision'}


def test_unavailable_engine_preserves_settings(monkeypatch, tmp_path):
    state, old, _ = setup_engine(monkeypatch, tmp_path, [])
    before = state.scoring_model
    response = server.app.test_client().post('/api/settings/engine', json={'backend':'vllm','model':'missing'})
    assert response.status_code == 503
    assert state.scoring_model == before
    assert server.inference_engine.ollama_client is old
    assert not (tmp_path/'temp/engine-settings.json').exists()


def test_busy_engine_rejects_switch(monkeypatch, tmp_path):
    setup_engine(monkeypatch, tmp_path, ['vision'])
    server.analysis_thread.analysis_lock.acquire()
    assert server.app.test_client().post('/api/settings/engine', json={'backend':'vllm','model':'vision'}).status_code == 409


def test_tailnet_only_advertises_matching_private_route(monkeypatch):
    status = {'BackendState':'Running','Self':{'DNSName':'host.example.ts.net.'}}
    config = {'Web':{'host.example.ts.net:443':{'Handlers':{'/':{'Proxy':'http://127.0.0.1:5000'}}}}}
    monkeypatch.setenv('SERVICE_BIND','127.0.0.1:5000')
    monkeypatch.setattr(tailnet.subprocess,'check_output',lambda args, **kw: json.dumps(status if args[1]=='status' else config).encode())
    assert tailnet.get_share_status()['url'] == 'https://host.example.ts.net/join'
    config['AllowFunnel'] = {'host.example.ts.net:443':True}
    assert not tailnet.get_share_status()['ready']
    config.clear()
    assert not tailnet.get_share_status()['url']


def test_qr_requires_active_share(monkeypatch):
    monkeypatch.setattr(tailnet,'get_share_status',lambda: {'url':''})
    assert server.app.test_client().get('/api/share/qr.svg').status_code == 409
    monkeypatch.setattr(tailnet,'get_share_status',lambda: {'url':'https://host.example.ts.net/'})
    response = server.app.test_client().get('/api/share/qr.svg')
    assert response.status_code == 200
    assert b'<svg' in response.data
