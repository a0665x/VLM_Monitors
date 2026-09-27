"""Private-host accounts, revocable sessions and Google OpenID Connect."""
import hashlib
import os
import secrets
import sqlite3
import time
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlencode
from flask import Blueprint, abort, g, jsonify, redirect, request, session, send_from_directory, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from flask.sessions import SecureCookieSessionInterface
from werkzeug.middleware.proxy_fix import ProxyFix

def safe_destination(value):
    allowed={'/','/#monitor','/#settings','/#connect','/join','/join?mode=watch','/join?mode=publish','/archive'}
    return value if value in allowed else '/join'

class Accounts:
    def __init__(self, directory):
        self.root=Path(directory);self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.path=self.root/'accounts.sqlite3'
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT,google_sub TEXT UNIQUE,role TEXT NOT NULL DEFAULT 'member');
            CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS source_owners(source_id TEXT PRIMARY KEY,user_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS attempts(key TEXT PRIMARY KEY,count INTEGER NOT NULL,until REAL NOT NULL);''')
        os.chmod(self.path,0o600)
        self.secret=self.file_secret('session.key')
        self.setup_token=self.file_secret('setup-token')
    def file_secret(self,name):
        path=self.root/name
        try:
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as out:out.write(secrets.token_urlsafe(48))
        except FileExistsError:pass
        return path.read_text().strip()
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row;return db
    def initialized(self):
        with self.connect() as db:return bool(db.execute('SELECT 1 FROM users LIMIT 1').fetchone())
    def current(self):
        sid=session.get('sid')
        if not sid:return None
        with self.connect() as db:
            row=db.execute('SELECT u.id,u.email,u.name,u.role FROM users u JOIN sessions s ON s.user_id=u.id WHERE s.id=? AND s.expires>?',(hashlib.sha256(sid.encode()).hexdigest(),time.time())).fetchone()
        return dict(row) if row else None
    def login(self,user_id):
        session.clear();sid=secrets.token_urlsafe(32);session['sid']=sid;session['csrf']=secrets.token_urlsafe(32);session.permanent=True
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(sid.encode()).hexdigest(),user_id,time.time()+86400))
    def logout(self):
        sid=session.get('sid','')
        with self.connect() as db:db.execute('DELETE FROM sessions WHERE id=?',(hashlib.sha256(sid.encode()).hexdigest(),))
        session.clear()
    def rate_limit(self):
        key=hashlib.sha256((request.remote_addr or 'unknown').encode()).hexdigest();now=time.time()
        with self.connect() as db:
            db.execute('DELETE FROM attempts WHERE until<?',(now,))
            row=db.execute('SELECT count FROM attempts WHERE key=?',(key,)).fetchone()
            if row and row['count']>=10:abort(429,description='Too many attempts. Try again in 15 minutes.')
            db.execute('INSERT INTO attempts VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,now+900))
    def bootstrap(self,token,email,name,password):
        if not secrets.compare_digest(str(token),self.setup_token):raise ValueError('Invalid setup code')
        if not isinstance(password,str) or not 6<=len(password)<=128:raise ValueError('Use a password with 6–128 characters')
        if not isinstance(email,str) or '@' not in email or len(email)>254:raise ValueError('Enter a valid email')
        uid=secrets.token_hex(16)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM users LIMIT 1').fetchone():raise ValueError('Setup already complete')
            db.execute('INSERT INTO users(id,email,name,password,role) VALUES(?,?,?,?,?)',(uid,email.strip().lower(),str(name or 'Administrator')[:80],generate_password_hash(password),'admin'))
        return uid

def init_accounts(app,directory=None):
    store=Accounts(directory or os.getenv('VLM_ACCOUNT_DIR','data/private'))
    app.extensions['accounts']=store;app.secret_key=store.secret
    public=os.getenv('AUTH_PUBLIC_URL','').rstrip('/')
    if public:
        url=urlsplit(public)
        if url.scheme!='https' or not url.netloc or url.path:raise ValueError('AUTH_PUBLIC_URL must be an HTTPS origin')
    app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=bool(public),PERMANENT_SESSION_LIFETIME=timedelta(days=1),MAX_CONTENT_LENGTH=1024*1024)
    class CookiePolicy(SecureCookieSessionInterface):
        def get_cookie_secure(self, app):return request.is_secure
    app.session_interface=CookiePolicy()
    original=app.wsgi_app
    forwarded=ProxyFix(original,x_for=0,x_proto=1,x_host=0,x_port=0,x_prefix=0)
    app.wsgi_app=lambda environ,start_response: (forwarded if environ.get('REMOTE_ADDR') in {'127.0.0.1','::1'} else original)(environ,start_response)
    bp=Blueprint('auth',__name__)
    oauth=None
    if os.getenv('GOOGLE_CLIENT_ID') and os.getenv('GOOGLE_CLIENT_SECRET') and public:
        from authlib.integrations.flask_client import OAuth
        oauth=OAuth(app).register('google',client_id=os.environ['GOOGLE_CLIENT_ID'],client_secret=os.environ['GOOGLE_CLIENT_SECRET'],server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',client_kwargs={'scope':'openid email profile','code_challenge_method':'S256'})
    @bp.app_errorhandler(429)
    def rate_error(error):return jsonify(error=error.description),429
    @bp.route('/login')
    @bp.route('/setup')
    def login_page():return send_from_directory(app.static_folder,'login.html')
    @bp.route('/auth/status')
    def info():
        session.setdefault('csrf',secrets.token_urlsafe(32))
        return jsonify(user=store.current(),csrf=session['csrf'],setup_required=not store.initialized(),google_enabled=bool(oauth))
    @bp.route('/auth/setup',methods=['POST'])
    def setup():
        store.rate_limit();data=request.get_json(silent=True) or {}
        try:uid=store.bootstrap(data.get('code',''),data.get('email',''),data.get('name',''),data.get('password',''))
        except ValueError as exc:return jsonify(error=str(exc)),400
        store.login(uid);return jsonify(success=True)
    @bp.route('/auth/login',methods=['POST'])
    def login():
        store.rate_limit();data=request.get_json(silent=True) or {};password=data.get('password','')
        if not isinstance(password,str) or len(password)>128:abort(400)
        with store.connect() as db:row=db.execute('SELECT id,password FROM users WHERE email=?',(str(data.get('email','')).lower().strip(),)).fetchone()
        if not row or not row['password'] or not check_password_hash(row['password'],password):return jsonify(error='Email or password is incorrect'),401
        store.login(row['id']);return jsonify(success=True)
    @bp.route('/auth/logout',methods=['POST'])
    def logout():
        store.logout();return jsonify(success=True)
    @bp.route('/auth/google')
    def google_login():
        if not oauth or not store.initialized():return redirect('/login')
        user=store.current()
        session['link_user']=user['id'] if user else None
        session['login_next']=safe_destination(request.args.get('next'))
        return oauth.authorize_redirect(public+'/auth/google/callback',nonce=secrets.token_urlsafe(32))
    @bp.route('/auth/google/callback')
    def callback():
        if not oauth:abort(404)
        try:
            token=oauth.authorize_access_token();info=token.get('userinfo',{})
            if not info.get('email_verified') or not info.get('sub'):raise ValueError('Unverified identity')
            email=info['email'].lower();sub=info['sub'];link_user=session.pop('link_user',None)
            current=store.current()
            allowed={v.strip().lower() for v in os.getenv('AUTH_ALLOWED_EMAILS','').split(',') if v.strip()}
            with store.connect() as db:
                row=db.execute('SELECT * FROM users WHERE google_sub=?',(sub,)).fetchone()
                if not row and link_user and current and current['id']==link_user and current['email']==email:
                    db.execute('UPDATE users SET google_sub=? WHERE id=?',(sub,link_user));uid=link_user
                elif not row:
                    # Do not silently link an existing local account by email.
                    if email not in allowed or db.execute('SELECT 1 FROM users WHERE email=?',(email,)).fetchone():raise ValueError('Account needs administrator approval')
                    uid=secrets.token_hex(16);db.execute('INSERT INTO users(id,email,name,google_sub) VALUES(?,?,?,?)',(uid,email,str(info.get('name',email))[:80],sub))
                else:uid=row['id']
            destination=safe_destination(session.pop('login_next',None))
            store.login(uid);return redirect(destination)
        except Exception:
            app.logger.warning('Google sign-in rejected')
            return redirect('/login?error=google')
    app.register_blueprint(bp)
    @app.before_request
    def guard():
        g.user=store.current()
        if request.method not in ('GET','HEAD','OPTIONS'):
            expected=session.get('csrf','');provided=request.headers.get('X-CSRF-Token','')
            # MediaMTX's embedded client sends same-origin signaling without a custom token.
            signaling=request.path.startswith('/proxy/webrtc/')
            origin=request.headers.get('Origin')
            origin_ok=origin in {request.host_url.rstrip('/'),public} and bool(origin)
            if not ((expected and secrets.compare_digest(expected,provided)) or (signaling and origin_ok)):
                return jsonify(error='Request expired. Reload the page.'),403
        if request.path.startswith('/static/') or request.path in {'/login','/setup','/auth/status','/auth/setup','/auth/login','/auth/google','/auth/google/callback'}:return
        if not g.user:
            if request.path.startswith(('/api/','/proxy/','/auth/')):return jsonify(error='Sign in required'),401
            return redirect('/login?'+urlencode({'next':safe_destination(request.full_path.rstrip('?'))}))
        if request.method not in ('GET','HEAD','OPTIONS') and request.path.startswith('/api/'):
            if request.path in {'/api/sources/register','/api/sources/heartbeat','/api/sources/disconnect'}:
                import re
                data=request.get_json(silent=True) or {};source=str(data.get('source_id',''))
                if not re.fullmatch(r'[a-z0-9_-]{1,100}',source) or source in {'camera','agx-local'}:return jsonify(error='Invalid source'),400
                with store.connect() as db:
                    db.execute('BEGIN IMMEDIATE')
                    owner=db.execute('SELECT user_id FROM source_owners WHERE source_id=?',(source,)).fetchone()
                    if owner and owner['user_id']!=g.user['id'] and g.user['role']!='admin':return jsonify(error='Camera belongs to another account'),403
                    if not owner and request.path.endswith('/register'):db.execute('INSERT INTO source_owners VALUES(?,?)',(source,g.user['id']))
                    elif not owner and g.user['role']!='admin':return jsonify(error='Register this camera first'),403
        if request.method not in ('GET','HEAD','OPTIONS') and request.path.startswith('/proxy/webrtc/') and '/whip' in request.path:
            source=request.path.split('/')[3]
            with store.connect() as db:owner=db.execute('SELECT user_id FROM source_owners WHERE source_id=?',(source,)).fetchone()
            if not owner or (owner['user_id']!=g.user['id'] and g.user['role']!='admin'):return jsonify(error='Camera publishing is not authorized'),403
        if request.method not in ('GET','HEAD','OPTIONS') and request.path.startswith('/api/'):
            member_routes={'/api/sources/register','/api/sources/heartbeat','/api/sources/disconnect'}
            if not request.path.startswith('/api/archive') and request.path not in member_routes and g.user['role']!='admin':return jsonify(error='Administrator access required'),403
    @app.after_request
    def headers(response):
        if request.path.startswith(('/api/','/auth/','/proxy/')):response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='same-origin'
        return response
    return store
