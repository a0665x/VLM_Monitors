import importlib.util
import sys
import time
from pathlib import Path
import numpy as np
import pytest
from flask import Flask, jsonify
from services.accounts import init_accounts
from services.archive import init_archive, scene_change, scene_signature

@pytest.fixture
def host(tmp_path,monkeypatch):
    for key in ('GOOGLE_CLIENT_ID','GOOGLE_CLIENT_SECRET','AUTH_PUBLIC_URL'):monkeypatch.delenv(key,raising=False)
    app=Flask(__name__,static_folder=str(Path(__file__).resolve().parents[2]/'static'));app.testing=True
    accounts=init_accounts(app,tmp_path/'private')
    @app.route('/api/status')
    def status():return jsonify(ok=True)
    @app.route('/proxy/webrtc/camera/whep',methods=['POST'])
    def whep():return jsonify(ok=True)
    archive=init_archive(app,accounts,lambda source:None,lambda:{'camera':{}},directory=tmp_path/'archive',start=False)
    return app,accounts,archive

def admin(host):
    app,accounts,_=host;client=app.test_client();csrf=client.get('/auth/status').json['csrf']
    r=client.post('/auth/setup',json={'code':accounts.setup_token,'email':'admin@example.test','password':'test-only-password-123'},headers={'X-CSRF-Token':csrf})
    assert r.status_code==200
    return client,client.get('/auth/status').json

def test_auth_required_and_setup_single_use(host):
    app,accounts,_=host;c=app.test_client()
    assert c.get('/api/status').status_code==401
    assert c.get('/archive').status_code==302
    assert c.get('/api/archive/download').status_code==401
    c,info=admin(host)
    assert c.get('/api/status').status_code==200
    assert c.post('/auth/setup',json={},headers={'X-CSRF-Token':info['csrf']}).status_code==400
    assert accounts.initialized()

def test_csrf_and_session_revocation(host):
    app,accounts,_=host;c,info=admin(host)
    assert c.post('/api/archive/config',json={'source_id':'camera','enabled':True}).status_code==403
    with c.session_transaction() as s:old=dict(s)
    assert c.post('/auth/logout',headers={'X-CSRF-Token':info['csrf']}).status_code==200
    with c.session_transaction() as s:s.update(old)
    assert c.get('/api/status').status_code==401

def test_secure_cookie_and_same_origin_signaling(host):
    app,_,_=host;c,info=admin(host)
    assert c.post('/proxy/webrtc/camera/whep',headers={'Origin':'https://attacker.example'}).status_code==403
    assert c.post('/proxy/webrtc/camera/whep',headers={'Origin':'http://localhost'}).status_code==200
    r=app.test_client().get('/auth/status',base_url='https://host.example')
    assert 'Secure;' in r.headers['Set-Cookie'] and 'HttpOnly;' in r.headers['Set-Cookie']

def test_one_slot_change_aware_sampling_and_events(host):
    _,_,a=host;uid='u1';now=time.time();frame=np.zeros((100,200,3),dtype=np.uint8)
    a.configure(uid,'camera',True);a.sample(uid,'camera',frame,now)
    a.sample(uid,'camera',frame,now+2)
    assert a.info(uid)['usage']['n']==1
    changed=frame.copy();changed[20:80,30:130]=255
    assert scene_change(scene_signature(frame),scene_signature(changed))>.025
    a.sample(uid,'camera',changed,now+3)
    assert a.info(uid)['usage']['n']==2
    a.record_event('camera',['person'],changed,now+4)
    assert a.info(uid)['events'][0]['categories']==['person']
    a.sample(uid,'camera',changed,now+5)
    assert a.info(uid)['usage']['n']>=4
    a.configure(uid,'camera',False);n=a.info(uid)['usage']['n'];a.sample(uid,'camera',changed,now+6)
    assert a.info(uid)['usage']['n']==n
    with a.db() as db:assert db.execute('SELECT COUNT(*) FROM archive_config WHERE user_id=?',(uid,)).fetchone()[0]==1

def test_owner_isolation_for_frames_and_metadata(host):
    app,accounts,a=host;c,info=admin(host)
    fid=a.save('someone-else','camera',np.zeros((20,20,3),dtype=np.uint8),time.time(),'change',1)
    assert c.get('/api/archive/frame/'+fid).status_code==404
    assert c.get('/api/archive').json['usage']['n']==0
    assert c.get('/api/archive/download').status_code==404

def test_retention_and_quota(host):
    _,_,a=host;frame=np.zeros((20,20,3),dtype=np.uint8);now=time.time()
    a.save('u','camera',frame,now-8*86400,'heartbeat',0);a.save('u','camera',frame,now,'change',1)
    a.prune('u',now);assert a.info('u')['usage']['n']==1
    a.frame_quota=1;a.prune('u',now);assert a.info('u')['usage']['n']==0

def test_real_software_mp4_and_timestamp_manifest(host):
    _,_,a=host;now=time.time();frame=np.zeros((90,160,3),dtype=np.uint8)
    for i in range(3):a.save('u','camera',frame+i*70,now+i,'change',1)
    from datetime import datetime,timezone
    day=datetime.fromtimestamp(now,timezone.utc).strftime('%Y-%m-%d');a._export('u',day)
    assert a.jobs['u']['state']=='ready'
    assert (a.root/'u/timelapse.mp4').stat().st_size>1000
    import json,cv2
    manifest=json.loads((a.root/'u/manifest.json').read_text());assert len(manifest['frames'])==3
    assert manifest['frames'][0]['ts']==now and manifest['timestamp_overlay']=='bottom-right'
    cap=cv2.VideoCapture(str(a.root/'u/timelapse.mp4'));ok,image=cap.read();cap.release()
    assert ok and image.shape[:2]==(540,960)
    assert image[510:540,600:950].max()>150

def test_low_disk_blocks_regular_trigger_and_export(host,monkeypatch):
    from services.archive import StorageFull
    from collections import namedtuple
    _,_,a=host;frame=np.zeros((20,20,3),dtype=np.uint8);a.configure('u','camera',True)
    usage=namedtuple('usage','total used free')
    monkeypatch.setattr('services.archive.shutil.disk_usage',lambda p:usage(100,99,1))
    with pytest.raises(StorageFull):a.sample('u','camera',frame,time.time())
    with pytest.raises(StorageFull):a.record_event('camera',['person'],frame)
    with pytest.raises(StorageFull):a.export('u','2026-09-27')
    assert a.info('u')['usage']['n']==0 and a.storage()['paused']

def test_total_budget_removes_oldest_across_accounts(host):
    _,_,a=host;frame=np.zeros((20,20,3),dtype=np.uint8);now=time.time()
    a.save('one','camera',frame,now,'change',1);size=a.disk_bytes();a.total_quota=size+100
    a.save('two','camera',frame,now+1,'change',1)
    assert a.info('one')['usage']['n']==0 and a.info('two')['usage']['n']==1
    assert a.disk_bytes()<=a.total_quota

def test_hardlink_snapshot_counted_once_and_prevents_overflow(host):
    import os
    from services.archive import StorageFull
    _,_,a=host;frame=np.zeros((20,20,3),dtype=np.uint8)
    fid=a.save('u','camera',frame,time.time(),'change',1);size=a.disk_bytes()
    work=a.root/'u/export-work';work.mkdir();os.link(a.root/f'u/frames/{fid}.jpg',work/'00000000.jpg')
    assert a.disk_bytes()==size
    a.total_quota=size
    with pytest.raises(StorageFull):a.save('other','camera',frame,time.time()+1,'change',1)
    assert a.disk_bytes()==size

def test_google_requires_verified_allowed_identity(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from authlib.integrations.flask_client import OAuth
    monkeypatch.setenv('GOOGLE_CLIENT_ID','test-id');monkeypatch.setenv('GOOGLE_CLIENT_SECRET','test-secret')
    monkeypatch.setenv('AUTH_PUBLIC_URL','https://host.example');monkeypatch.setenv('AUTH_ALLOWED_EMAILS','member@example.test')
    claims={'email':'member@example.test','sub':'google-test-subject','email_verified':False}
    fake=SimpleNamespace(authorize_access_token=lambda:{'userinfo':claims})
    monkeypatch.setattr(OAuth,'register',lambda *args,**kwargs:fake)
    app=Flask(__name__);app.testing=True;accounts=init_accounts(app,tmp_path/'oauth')
    accounts.bootstrap(accounts.setup_token,'admin@example.test','Admin','test-only-password-123')
    c=app.test_client()
    assert c.get('/auth/google/callback').location.endswith('error=google')
    claims['email_verified']=True;claims['email']='outsider@example.test'
    assert c.get('/auth/google/callback').location.endswith('error=google')
    claims['email']='admin@example.test'
    assert c.get('/auth/google/callback').location.endswith('error=google')
    claims['email']='member@example.test'
    assert c.get('/auth/google/callback').location=='/join'
    assert c.get('/auth/status').json['user']['role']=='member'

def test_member_cannot_change_host_or_publish_foreign_camera(host):
    from flask import session
    app,accounts,_=host
    for route in ['/api/sources/register','/api/settings/engine','/proxy/webrtc/phone/whip']:
        app.add_url_rule(route,route,lambda:jsonify(ok=True),methods=['POST'])
    c,info=admin(host)
    assert c.post('/api/sources/register',json={'source_id':'phone'},headers={'X-CSRF-Token':info['csrf']}).status_code==200
    with accounts.connect() as db:db.execute("INSERT INTO users(id,email,name) VALUES('member','member@example.test','Member')")
    with app.test_request_context():
        accounts.login('member');saved=dict(session)
    member=app.test_client()
    with member.session_transaction() as s:s.update(saved)
    headers={'X-CSRF-Token':saved['csrf']}
    assert member.post('/api/settings/engine',json={},headers=headers).status_code==403
    assert member.post('/api/sources/register',json={'source_id':'phone'},headers=headers).status_code==403
    assert member.post('/proxy/webrtc/phone/whip',headers=headers).status_code==403
    assert member.post('/api/sources/register',json={'source_id':'own-phone'},headers=headers).status_code==200
