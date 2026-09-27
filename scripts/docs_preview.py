#!/usr/bin/env python3
"""Render real WebUI assets with synthetic fixtures. No camera/model/service imports.
Run: .venv/bin/python scripts/docs_preview.py (loopback port 5055).
"""
from pathlib import Path
from io import BytesIO
from flask import Flask, jsonify, request, send_from_directory, Response
import qrcode
import qrcode.image.svg
ROOT = Path(__file__).resolve().parents[1]
app = Flask(__name__, static_folder=str(ROOT/'static'))
selected = 'host-camera'
settings = {'mode':'parallel_decision','scenarios':['person','baby','fire','smoke','pet']}
SOURCES = [dict(id='host-camera',path='camera',label='Host camera · Living room',is_local=True),dict(id='phone-kitchen',path='phone-kitchen',label='iPhone · Kitchen',is_local=False)]
SOURCES = [dict(s,status='online',ready=True,webrtc_url='/proxy/webrtc/'+s['path']) for s in SOURCES]

def status():
    kitchen = selected == 'phone-kitchen'
    values = [.01,.01,.94,.88,.02] if kitchen else [.97,.01,.01,.02,.93]
    results = {key:dict(state='present' if p>.5 else 'absent', probabilities=dict(present=p,absent=round(1-p-.01,4),unknown=.01)) for key,p in zip(settings['scenarios'],values)}
    return dict(source_id=selected,source_label=SOURCES[int(kitchen)]['label'],ui_mode='situation',auto_analyze=False,analysis_running=False,analysis_interval=5,risk=False,score=0,scoring_model='qwen2.5vl:3b',inference_backend='ollama',last_inference_error='',last_inference_text='Illustrative fixture — not an inference result.',explanation='Synthetic scene · illustrative scores · no live inference',risk_threshold=3,show_inference_overlay=False,sound_detection_enabled=False,sound_db=-120,decision_settings=settings,decision_result=dict(results=results,frame_id=selected,timestamp='2026-09-26T08:00:00Z',decision_model='Qwen 1.5B · illustrative fixture',calibrated=False,observations='Synthetic scene',vision_ms=0,decision_ms=0,total_ms=0))

@app.route('/')
@app.route('/join')
@app.route('/archive')
def page():
    name={'/join':'join.html','/archive':'archive.html'}.get(request.path,'index.html')
    html=(ROOT/'static'/name).read_text()
    html=html.replace('https://cdn.jsdelivr.net/npm/hls.js@latest','/static/vendor/hls.min.js').replace('https://cdn.socket.io/4.5.4/socket.io.min.js','/docs/demo/socket.js')
    html=html.replace('</head>','<link rel="stylesheet" href="/docs/demo/preview.css"></head>')
    html=html.replace('</body>','<script src="/docs/demo/preview.js"></script></body>')
    return html

@app.route('/auth/status')
def demo_account():return jsonify(user=dict(name='Demo host',role='admin'),csrf='preview',google_enabled=False,setup_required=False)

@app.route('/docs/<path:name>')
def assets(name):return send_from_directory(ROOT/'docs',name)

@app.route('/proxy/webrtc/<path:name>')
def frame(name):
    asset='scenario-fire-smoke.png' if 'phone-kitchen' in name else 'scenario-person-pet.png'
    return '<html><body style="margin:0;background:#101c22;height:100vh;display:grid;place-items:center"><img alt="AI-generated fictional scenario" src="/docs/assets/'+asset+'" style="width:100%;height:100%;object-fit:cover"><span style="position:absolute;bottom:8px;left:8px;background:#101c22cc;color:white;font:11px system-ui;padding:4px 8px;border-radius:4px">SYNTHETIC DEMO IMAGE</span></body></html>'

@app.route('/api/share/qr.svg')
def qr():
    output=BytesIO();qrcode.make('https://example.com/vlm-monitor-demo',image_factory=qrcode.image.svg.SvgPathImage).save(output)
    return Response(output.getvalue(),mimetype='image/svg+xml')

@app.route('/api/<path:name>',methods=['GET','POST'])
def api(name):
    global selected
    if request.method=='POST':
        if name=='mode':return jsonify(success=True,mode='situation',selected_source_id=selected)
        if name=='sources/select':
            source_id=(request.get_json(silent=True) or {}).get('source_id')
            if source_id not in {s['id'] for s in SOURCES}:return jsonify(error='Unknown demo source'),400
            selected=source_id
            return jsonify(success=True,selected_source_id=selected,sources=SOURCES)
        return jsonify(success=False,error='Documentation preview: live actions are disabled.'),403
    if name=='archive':
        from datetime import datetime,timezone
        return jsonify(config={'source_id':'host-camera','enabled':False},recorded_sources=['host-camera','phone-kitchen'],usage={'n':120,'bytes':18000000},quota_bytes=1073741824,retention_days=7,days=[{'day':datetime.now(timezone.utc).strftime('%Y-%m-%d'),'frames':120}],storage={'paused':False},job=None,error='')
    if name=='archive/playback':
        start=float(request.args.get('start',0))+9*3600
        return jsonify(frames=[dict(id='demo-'+str(i),ts=start+i*60,reason='change') for i in range(30)],events=[dict(id='demo-event',ts=start+5*60,frame_id='demo-5',categories=['person','pet'])],total_frames=30)
    if name.startswith('archive/frame/demo-'):return send_from_directory(ROOT/'docs/assets','scenario-person-pet.png')
    routes={
      'status':status(),
      'service':dict(inference_backend='ollama'),
      'sources':dict(sources=SOURCES,selected_source_id=selected),
      'network':dict(sources=SOURCES,selected_source_id=selected,share_ready=True,media_ready=True,backend='ollama',model='qwen2.5vl:3b'),
      'share':dict(ready=True,url='https://example.com/vlm-monitor-demo',message='Documentation QR only'),
      'public-urls':dict(ui='',webrtc=''),
      'metrics':dict(cpu_percent=0,ram_percent=0,gpu_percent=0),
      'settings/decisions':dict(settings=settings,service=dict(ready=True)),
      'settings/engine':dict(current_backend='ollama',current_model='qwen2.5vl:3b',backend='ollama',model='qwen2.5vl:3b',models=['qwen2.5vl:3b'],available=True),
      'models/vision':dict(models=['qwen2.5vl:3b']),
      'devices/video':dict(devices=[]),'devices/audio':dict(devices=[]),
      'prompt/current':dict(text='Is there a person visible in the image?'),
      'prompt/history':dict(history=[]),
    }
    return jsonify(routes.get(name,{}))

if __name__=='__main__':app.run(host='127.0.0.1',port=5055,debug=False)
