import httpx
from src import server
from services import client_network, tailnet
from shared.state import AppState


def test_private_media_config_uses_tailnet_interface(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path/'temp').mkdir()
    config = tmp_path/'local.yml'
    config.write_text('webrtcLocalUDPAddress: 127.0.0.1:8189\nwebrtcAdditionalHosts: [127.0.0.1]\n')
    monkeypatch.setattr(tailnet, 'get_share_status', lambda: {'ready': True})
    monkeypatch.setattr(client_network.subprocess, 'check_output', lambda *a, **kw: '100.100.24.51\n')
    output = client_network.prepare_media_config(str(config))
    text = (tmp_path/output).read_text()
    assert '100.100.24.51:8189' in text
    assert 'webrtcLocalTCPAddress: 100.100.24.51:8189' in text
    assert 'apiAddress: 127.0.0.1:9997' in text
    assert '0.0.0.0' not in text
    assert config.read_text().startswith('webrtcLocalUDPAddress: 127.0.0.1')


def test_no_serve_keeps_loopback(monkeypatch):
    monkeypatch.setattr(tailnet, 'get_share_status', lambda: {'ready': False})
    assert client_network.prepare_media_config('missing.yml') == 'missing.yml'


def test_webrtc_proxy_preserves_patch_and_location(monkeypatch):
    calls=[]
    def upstream(method, url, **kw):
        calls.append((method,url,kw))
        return httpx.Response(201, content=b'answer', headers={'Content-Type':'application/sdp', 'ETag':'"session"', 'Location':'/phone-test/whip/session-id'})
    monkeypatch.setattr(httpx,'request',upstream)
    response=server.app.test_client().patch('/proxy/webrtc/phone-test/whip/session-id?test=1',data=b'candidate',headers={'Content-Type':'application/trickle-ice-sdpfrag','If-Match':'"session"'})
    assert response.status_code==201
    assert response.headers['Location']=='/proxy/webrtc/phone-test/whip/session-id'
    assert response.headers['ETag']=='"session"'
    assert calls[0][0]=='PATCH'
    assert calls[0][1]=='http://127.0.0.1:8889/phone-test/whip/session-id?test=1'
    assert calls[0][2]['headers']['If-Match']=='"session"'
    assert calls[0][2]['content']==b'candidate'


def test_proxy_rejects_traversal_and_large_payload():
    client=server.app.test_client()
    assert client.get('/proxy/webrtc/a/../bad').status_code==400
    assert client.post('/proxy/webrtc/a/whip',data=b'x'*(1024*1024+1)).status_code==413


def test_network_readiness_comes_from_media_not_heartbeat(monkeypatch):
    state=AppState()
    state.sources['phone-test']={'id':'phone-test','label':'Phone','kind':'remote','status':'online','is_local':False,'last_seen':9999999999}
    monkeypatch.setattr(server,'app_state',state)
    monkeypatch.setattr(tailnet,'get_share_status',lambda:{'ready':True})
    monkeypatch.setattr(client_network,'live_paths',lambda:{'camera':{'readers':[]}})
    data=server.app.test_client().get('/api/network').get_json()
    assert data['media_ready']
    assert next(s for s in data['sources'] if s['id']=='phone-test')['ready'] is False
    assert next(s for s in data['sources'] if s['is_local'])['ready'] is True


def test_cannot_register_over_host_camera(monkeypatch):
    monkeypatch.setattr(server,'app_state',AppState())
    for source_id in ['camera','agx-local']:
        assert server.app.test_client().post('/api/sources/register',json={'source_id':source_id}).status_code==400


def test_join_serves_without_device_role_gate():
    response=server.app.test_client().get('/join')
    assert response.status_code==200
    assert b'id="role-gate"' not in response.data
    assert b'https://console.tailscale.com/admin/machines' in response.data
