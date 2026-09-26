"""Account-scoped, change-aware frame archive and on-demand software MP4 export."""
import json
import logging
import os
import secrets
import shutil
import sqlite3
import subprocess
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
import cv2
import numpy as np
from flask import Blueprint, abort, g, jsonify, request, send_file, send_from_directory

logger=logging.getLogger(__name__)

def scene_signature(frame):
    return cv2.GaussianBlur(cv2.cvtColor(cv2.resize(frame,(160,90)),cv2.COLOR_RGB2GRAY),(5,5),0)

def scene_change(previous,current):
    if previous is None:return 1.0
    # Fraction of pixels whose luminance changed substantially. No bitrate assumptions.
    return float(np.mean(cv2.absdiff(previous,current)>18))

class StorageFull(RuntimeError):
    pass

class Archive:
    def __init__(self,accounts,directory,frame_provider,sources):
        self.accounts=accounts;self.root=Path(directory).resolve();self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.frame_provider=frame_provider;self.sources=sources;self.running=True
        self.lock=threading.RLock();self.recent={};self.last={};self.post_until={};self.jobs={};self.cooldowns={};self.errors={}
        self.retention=max(1,min(365,int(os.getenv('ARCHIVE_RETENTION_DAYS','7'))));self.quota=max(16,int(os.getenv('ARCHIVE_QUOTA_MB','1024')))*1024*1024
        self.frame_quota=self.quota//2
        self.total_quota=max(16,int(os.getenv('ARCHIVE_TOTAL_MB','10240')))*1024*1024
        self.min_free=max(0,int(os.getenv('ARCHIVE_MIN_FREE_MB','1024')))*1024*1024
        self.export_lock=threading.Lock()
        self.last_prune={}
        for folder in self.root.iterdir():
            if folder.is_dir() and not folder.is_symlink():
                shutil.rmtree(folder/'export-work',ignore_errors=True)
                for name in ('timelapse.pending.mp4','manifest.pending.json'):(folder/name).unlink(missing_ok=True)
                for path in (folder/'frames').glob('*.tmp'):path.unlink(missing_ok=True)
        with self.db() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS archive_config(user_id TEXT PRIMARY KEY,source_id TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS archive_frames(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,source_id TEXT NOT NULL,ts REAL NOT NULL,path TEXT NOT NULL,bytes INTEGER NOT NULL,reason TEXT NOT NULL,change REAL NOT NULL);
            CREATE INDEX IF NOT EXISTS frames_owner_time ON archive_frames(user_id,ts);
            CREATE TABLE IF NOT EXISTS archive_events(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,source_id TEXT NOT NULL,ts REAL NOT NULL,categories TEXT NOT NULL,frame_id TEXT);
            CREATE INDEX IF NOT EXISTS events_owner_time ON archive_events(user_id,ts);''')
    def db(self):return self.accounts.connect()
    def disk_bytes(self, directory=None):
        # Count hard-linked export snapshots once, including files no longer in the DB.
        seen=set();total=0
        for path in (directory or self.root).rglob('*'):
            if not path.is_file() or path.is_symlink():continue
            try:stat=path.stat()
            except FileNotFoundError:continue
            key=(stat.st_dev,stat.st_ino)
            if key not in seen:total+=stat.st_size;seen.add(key)
        return total
    def storage(self):
        free=shutil.disk_usage(self.root).free
        return dict(used_bytes=self.disk_bytes(),quota_bytes=self.total_quota,free_bytes=free,min_free_bytes=self.min_free,paused=free<=self.min_free)
    def reserve(self,uid,amount):
        # All frame writes and exports share the same guard. Never remove unrelated files.
        if shutil.disk_usage(self.root).free-amount<self.min_free:
            raise StorageFull('Host disk space is low. Recording paused.')
        own=self.disk_bytes(self.root/uid);total=self.disk_bytes()
        with self.db() as db:
            if own+amount>self.quota or total+amount>self.total_quota:
                rows=db.execute('SELECT id,user_id,path FROM archive_frames ORDER BY ts').fetchall()
                for row in rows:
                    if own+amount<=self.quota and total+amount<=self.total_quota:break
                    if own+amount>self.quota and row['user_id']!=uid:continue
                    path=self.root/row['path']
                    try:
                        stat=path.stat();freed=stat.st_size if stat.st_nlink==1 else 0
                    except FileNotFoundError:freed=0
                    path.unlink(missing_ok=True)
                    db.execute('DELETE FROM archive_frames WHERE id=?',(row['id'],))
                    total-=freed
                    if row['user_id']==uid:own-=freed
        if own+amount>self.quota or total+amount>self.total_quota:
            raise StorageFull('Storage quota reached. Recording paused.')
    def configure(self,uid,source,enabled):
        if not isinstance(enabled,bool):raise ValueError('enabled must be true or false')
        if source not in self.sources():raise ValueError('Camera is unavailable')
        with self.lock,self.db() as db:
            db.execute('INSERT INTO archive_config VALUES(?,?,?) ON CONFLICT(user_id) DO UPDATE SET source_id=excluded.source_id,enabled=excluded.enabled',(uid,source,int(enabled)))
            self.last.pop(uid,None);self.recent.pop(uid,None);self.post_until.pop(uid,None)
    def configs(self):
        with self.db() as db:return [dict(r) for r in db.execute('SELECT * FROM archive_config WHERE enabled=1')]
    def info(self,uid):
        with self.db() as db:
            config=db.execute('SELECT * FROM archive_config WHERE user_id=?',(uid,)).fetchone()
            totals=db.execute('SELECT COUNT(*) n,COALESCE(SUM(bytes),0) bytes,MIN(ts) oldest,MAX(ts) latest FROM archive_frames WHERE user_id=?',(uid,)).fetchone()
            events=[dict(r) for r in db.execute('SELECT * FROM archive_events WHERE user_id=? ORDER BY ts DESC LIMIT 100',(uid,))]
            days=[dict(r) for r in db.execute("SELECT strftime('%Y-%m-%d',ts,'unixepoch') day,COUNT(*) frames FROM archive_frames WHERE user_id=? GROUP BY day ORDER BY day DESC",(uid,))]
        for e in events:e['categories']=json.loads(e['categories'])
        export_file=self.root/uid/'timelapse.mp4'
        totals=dict(totals);totals['bytes']+=export_file.stat().st_size if export_file.exists() else 0
        if uid not in self.jobs and export_file.exists():self.jobs[uid]={'state':'ready'}
        return dict(config=dict(config) if config else None,usage=dict(totals),events=events,days=days,quota_bytes=self.quota,retention_days=self.retention,slots=1,job=self.jobs.get(uid),error=self.errors.get(uid,''),storage=self.storage())
    def save(self,uid,source,frame,ts,reason,change):
        # Idempotent per account/source/capture timestamp, including pre-trigger replay.
        ident=__import__('hashlib').sha256(f'{uid}/{source}/{ts:.3f}'.encode()).hexdigest()[:32]
        with self.db() as db:
            if db.execute('SELECT 1 FROM archive_frames WHERE id=?',(ident,)).fetchone():return ident
        folder=self.root/uid/'frames';folder.mkdir(parents=True,exist_ok=True,mode=0o700)
        h,w=frame.shape[:2];scale=min(960/w,540/h);resized=cv2.resize(frame,(max(1,round(w*scale)),max(1,round(h*scale))))
        image=np.zeros((540,960,3),dtype=np.uint8);rh,rw=resized.shape[:2];image[(540-rh)//2:(540-rh)//2+rh,(960-rw)//2:(960-rw)//2+rw]=cv2.cvtColor(resized,cv2.COLOR_RGB2BGR)
        stamp=datetime.fromtimestamp(ts,timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
        size=cv2.getTextSize(stamp,cv2.FONT_HERSHEY_SIMPLEX,.55,1)[0];x=950-size[0]
        cv2.rectangle(image,(x-8,507),(959,539),(12,22,28),-1)
        cv2.putText(image,stamp,(x,529),cv2.FONT_HERSHEY_SIMPLEX,.55,(240,247,250),1,cv2.LINE_AA)
        ok,encoded=cv2.imencode('.jpg',image,[cv2.IMWRITE_JPEG_QUALITY,78])
        if not ok:raise RuntimeError('Frame encoding failed')
        with self.lock:
            self.reserve(uid,len(encoded))
            rel=f'{uid}/frames/{ident}.jpg';path=self.root/rel;tmp=path.with_suffix('.tmp');tmp.write_bytes(encoded.tobytes());tmp.replace(path)
            with self.db() as db:db.execute('INSERT OR IGNORE INTO archive_frames VALUES(?,?,?,?,?,?,?,?)',(ident,uid,source,ts,rel,path.stat().st_size,reason,change))
        return ident
    def sample(self,uid,source,frame,ts):
        with self.lock:
            with self.db() as db:config=db.execute('SELECT * FROM archive_config WHERE user_id=?',(uid,)).fetchone()
            if not config or not config['enabled'] or config['source_id']!=source:return
            signature=scene_signature(frame);last=self.last.get(uid);delta=scene_change(last[1] if last else None,signature)
            h,w=frame.shape[:2];scale=min(1,960/w,540/h);small=cv2.resize(frame,(max(1,round(w*scale)),max(1,round(h*scale))));ring=self.recent.setdefault(uid,deque(maxlen=5));ring.append((ts,source,small.copy(),delta))
            reason='event' if ts<=self.post_until.get(uid,0) else 'change' if delta>=.025 else 'heartbeat' if not last or ts-last[0]>=60 else None
            if reason:
                self.save(uid,source,small,ts,reason,delta);self.last[uid]=(ts,signature)
            if ts-self.last_prune.get(uid,0)>=10:self.prune(uid,ts);self.last_prune[uid]=ts
    def record_event(self,source,categories,frame,ts=None):
        if not categories:return
        ts=ts or time.time()
        with self.lock:
            for config in self.configs():
                if config['source_id']!=source:continue
                uid=config['user_id'];key=(uid,source,tuple(sorted(categories)))
                self.post_until[uid]=max(time.time(),ts)+10
                if ts-self.cooldowns.get(key,0)<30:continue
                self.cooldowns[key]=ts
                for stamp,previous_source,previous,delta in self.recent.get(uid,[]):
                    if previous_source==source:self.save(uid,source,previous,stamp,'pre-event' if stamp<=ts else 'event',delta)
                fid=self.save(uid,source,frame,ts,'trigger',1.0)
                with self.db() as db:db.execute('INSERT INTO archive_events VALUES(?,?,?,?,?,?)',(secrets.token_hex(16),uid,source,ts,json.dumps(categories),fid))
                self.prune(uid,ts)
    def prune(self,uid,now):
        with self.db() as db:
            rows=db.execute('SELECT id,path,bytes,ts FROM archive_frames WHERE user_id=? ORDER BY ts',(uid,)).fetchall();total=sum(r['bytes'] for r in rows)
            for row in rows:
                if row['ts']>=now-self.retention*86400 and total<=self.frame_quota:break
                (self.root/row['path']).unlink(missing_ok=True);db.execute('DELETE FROM archive_frames WHERE id=?',(row['id'],));total-=row['bytes']
            export=self.root/uid/'timelapse.mp4'
            if export.exists() and export.stat().st_mtime<now-self.retention*86400:
                export.unlink();(self.root/uid/'manifest.json').unlink(missing_ok=True);self.jobs.pop(uid,None)
            db.execute('DELETE FROM archive_events WHERE user_id=? AND ts<?',(uid,now-self.retention*86400))
    def run(self):
        last_cleanup=0
        while self.running:
            configs=self.configs();frames={}
            for config in configs:
                uid=config['user_id'];source=config['source_id']
                try:
                    if source not in frames:frames[source]=self.frame_provider(source)
                    frame=frames[source]
                    if frame is None:self.errors[uid]='Waiting for camera';continue
                    self.sample(uid,source,frame,time.time());self.errors.pop(uid,None)
                except Exception as exc:
                    logger.warning('Archive capture failed: %s',exc);self.errors[uid]=str(exc) if isinstance(exc,StorageFull) else 'Recording unavailable; check host storage and camera.'
            if time.time()-last_cleanup>300:
                with self.lock,self.db() as db:
                    for row in db.execute('SELECT user_id FROM archive_config').fetchall():self.prune(row['user_id'],time.time())
                last_cleanup=time.time()
            time.sleep(1)
    def export(self,uid,day):
        datetime.strptime(day,'%Y-%m-%d')
        with self.lock:
            if any(j.get('state')=='working' for j in self.jobs.values()):raise ValueError('Export already running')
            self.reserve(uid,1024*1024)
            self.jobs[uid]={'state':'working','day':day}
        threading.Thread(target=self._export,args=(uid,day),daemon=True).start()
    def _export(self,uid,day):
        folder=self.root/uid;work=folder/'export-work';shutil.rmtree(work,ignore_errors=True);work.mkdir(parents=True,exist_ok=True)
        try:
            start=datetime.strptime(day,'%Y-%m-%d').replace(tzinfo=timezone.utc).timestamp()
            with self.lock,self.db() as db:
                rows=[dict(r) for r in db.execute('SELECT * FROM archive_frames WHERE user_id=? AND ts>=? AND ts<? ORDER BY ts',(uid,start,start+86400))]
                if not rows:raise ValueError('No frames for this day')
                # Hard links preserve this snapshot while retention removes original names.
                for i,row in enumerate(rows):os.link(self.root/row['path'],work/f'{i:08d}.jpg')
            import imageio_ffmpeg
            output=folder/'timelapse.pending.mp4'
            command=[imageio_ffmpeg.get_ffmpeg_exe(),'-hide_banner','-loglevel','error','-y','-framerate','12','-i',str(work/'%08d.jpg'),'-c:v','libx264','-threads','1','-preset','veryfast','-crf','25','-pix_fmt','yuv420p','-movflags','+faststart','-fs',str(self.quota//4),str(output)]
            with self.export_lock:
                process=subprocess.Popen(command,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                deadline=time.monotonic()+600
                try:
                    while process.poll() is None:
                        with self.lock:
                            self.reserve(uid,1024*1024)
                            if output.exists() and output.stat().st_size>=self.quota//4:raise StorageFull('Video exceeds export allowance')
                        if time.monotonic()>deadline:raise TimeoutError('Export timed out')
                        time.sleep(.1)
                    if process.returncode:raise RuntimeError('Video encoding failed')
                finally:
                    if process.poll() is None:process.kill()
                    process.wait()
            if output.stat().st_size>=self.quota//4:raise StorageFull('Video exceeds export allowance')
            # -fs can stop cleanly at its limit: verify every requested frame was encoded.
            cap=cv2.VideoCapture(str(output));count=int(cap.get(cv2.CAP_PROP_FRAME_COUNT));cap.release()
            if count!=len(rows):raise RuntimeError('Incomplete export')
            with self.lock:self.reserve(uid,1024*1024)
            manifest=dict(day=day,fps=12,time_zone='UTC',timestamp_overlay='bottom-right',frames=[{k:r[k] for k in ('source_id','ts','reason','change')} for r in rows])
            metadata=json.dumps(manifest).encode()
            with self.lock:
                self.reserve(uid,len(metadata))
                pending=folder/'manifest.pending.json';pending.write_bytes(metadata)
                output.replace(folder/'timelapse.mp4');pending.replace(folder/'manifest.json')
            self.jobs[uid]={'state':'ready','day':day,'frames':len(rows),'url':'/api/archive/download','metadata_url':'/api/archive/metadata'}
        except Exception:
            logger.exception('Timelapse export failed');self.jobs[uid]={'state':'error','message':'Export failed. Check retained frames and disk space.'}
        finally:
            shutil.rmtree(work,ignore_errors=True)
            (folder/'timelapse.pending.mp4').unlink(missing_ok=True)
            (folder/'manifest.pending.json').unlink(missing_ok=True)

def init_archive(app,accounts,frame_provider,sources,directory=None,start=True):
    archive=Archive(accounts,directory or os.getenv('ARCHIVE_DIR','data/archive'),frame_provider,sources);app.extensions['archive']=archive
    bp=Blueprint('archive',__name__)
    @bp.route('/archive')
    def page():return send_from_directory(app.static_folder,'archive.html')
    @bp.route('/api/archive')
    def status():return jsonify(archive.info(g.user['id']))
    @bp.route('/api/archive/config',methods=['POST'])
    def config():
        data=request.get_json(silent=True) or {}
        try:archive.configure(g.user['id'],data.get('source_id'),data.get('enabled'))
        except ValueError as exc:return jsonify(error=str(exc)),400
        return jsonify(success=True)
    @bp.route('/api/archive/frame/<frame_id>')
    def frame(frame_id):
        with archive.db() as db:row=db.execute('SELECT path FROM archive_frames WHERE user_id=? AND id=?',(g.user['id'],frame_id)).fetchone()
        if not row:abort(404)
        return send_file(archive.root/row['path'],mimetype='image/jpeg')
    @bp.route('/api/archive/export',methods=['POST'])
    def export():
        try:archive.export(g.user['id'],(request.get_json(silent=True) or {}).get('day',''))
        except StorageFull as exc:return jsonify(error=str(exc)),409
        except (ValueError,TypeError) as exc:return jsonify(error=str(exc)),400
        return jsonify(success=True),202
    @bp.route('/api/archive/download')
    @bp.route('/api/archive/metadata')
    def download():
        name='manifest.json' if request.path.endswith('metadata') else 'timelapse.mp4';path=archive.root/g.user['id']/name
        if not path.exists():abort(404)
        return send_file(path,as_attachment=True,download_name=name)
    app.register_blueprint(bp)
    if start:threading.Thread(target=archive.run,daemon=True,name='archive').start()
    return archive
