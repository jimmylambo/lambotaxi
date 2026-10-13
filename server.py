"""
LamboTaxi — Backend Flask
Stack: Flask + SQLite (dev) / PostgreSQL (prod) + JWT auth
"""

import os, json, datetime, secrets
from functools import wraps
from flask import Flask, request, jsonify, send_from_directory, g
from flask_cors import CORS

# ── Deps check ──────────────────────────────────────────────────────────────
try:
    import jwt
    import bcrypt
    from flask_sqlalchemy import SQLAlchemy
except ImportError:
    print("Installing deps...")
    os.system("pip install flask flask-cors flask-sqlalchemy pyjwt bcrypt --break-system-packages -q")
    import jwt
    import bcrypt
    from flask_sqlalchemy import SQLAlchemy

# ── App config ───────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder='static')
CORS(app, resources={r"/api/*": {"origins": "*"}, r"/auth/*": {"origins": "*"}, r"/admin/*": {"origins": "*"}})

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', secrets.token_hex(32))
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'sqlite:///lambotaxi.db'
).replace('postgres://', 'postgresql://')  # fix Heroku/Render URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['ADMIN_EMAIL'] = os.environ.get('ADMIN_EMAIL', 'admin@lambotaxi.es')
app.config['ADMIN_PASSWORD'] = os.environ.get('ADMIN_PASSWORD', 'LamboAdmin2025!')
app.config['TOKEN_EXPIRY_HOURS'] = int(os.environ.get('TOKEN_EXPIRY_HOURS', 720))  # 30 days

db = SQLAlchemy(app)

# ── Models ────────────────────────────────────────────────────────────────────
class User(db.Model):
    __tablename__ = 'users'
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    nombre        = db.Column(db.String(255), nullable=False)
    empresa       = db.Column(db.String(255))          # empresa / flota
    ciudad        = db.Column(db.String(100))
    telefono      = db.Column(db.String(50))
    role          = db.Column(db.String(20), default='user')   # 'admin' | 'user'
    status        = db.Column(db.String(20), default='pending') # 'pending'|'active'|'blocked'
    tokens_left   = db.Column(db.Integer, default=0)           # monthly tokens
    tokens_expiry = db.Column(db.DateTime, nullable=True)
    created_at    = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    last_login    = db.Column(db.DateTime, nullable=True)
    notes         = db.Column(db.Text)                         # admin notes

    def set_password(self, pw):
        self.password_hash = bcrypt.hashpw(pw.encode(), bcrypt.gensalt()).decode()

    def check_password(self, pw):
        return bcrypt.checkpw(pw.encode(), self.password_hash.encode())

    def to_dict(self, admin=False):
        d = {
            'id': self.id,
            'email': self.email,
            'nombre': self.nombre,
            'empresa': self.empresa,
            'ciudad': self.ciudad,
            'status': self.status,
            'role': self.role,
            'tokens_left': self.tokens_left,
            'tokens_expiry': self.tokens_expiry.isoformat() if self.tokens_expiry else None,
            'created_at': self.created_at.isoformat(),
            'last_login': self.last_login.isoformat() if self.last_login else None,
        }
        if admin:
            d['telefono'] = self.telefono
            d['notes'] = self.notes
        return d


class UserData(db.Model):
    """Each user's app data stored as JSON blobs per key"""
    __tablename__ = 'user_data'
    id      = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    key     = db.Column(db.String(100), nullable=False)
    value   = db.Column(db.Text, default='[]')
    updated = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)
    __table_args__ = (db.UniqueConstraint('user_id', 'key', name='uq_user_key'),)


class Jornada(db.Model):
    """Conductor shift log"""
    __tablename__ = 'jornadas'
    id            = db.Column(db.Integer, primary_key=True)
    user_id       = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    fecha         = db.Column(db.String(10), nullable=False)
    hora_inicio   = db.Column(db.String(5))
    hora_fin      = db.Column(db.String(5))
    total_factura = db.Column(db.Float, default=0)
    propinas      = db.Column(db.Float, default=0)
    repostaje_l   = db.Column(db.Float, default=0)
    repostaje_e   = db.Column(db.Float, default=0)
    repostaje_tipo= db.Column(db.String(20))
    km_actual     = db.Column(db.Integer, default=0)
    km_desde_ultimo= db.Column(db.Integer, default=0)
    gasolinera    = db.Column(db.String(100))
    carreras      = db.Column(db.Text)   # JSON array of trips
    observaciones = db.Column(db.Text)
    created_at    = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at    = db.Column(db.DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'user_id': self.user_id,
            'fecha': self.fecha,
            'hora_inicio': self.hora_inicio,
            'hora_fin': self.hora_fin,
            'total_factura': self.total_factura,
            'propinas': self.propinas,
            'repostaje_l': self.repostaje_l,
            'repostaje_e': self.repostaje_e,
            'repostaje_tipo': self.repostaje_tipo,
            'km_actual': self.km_actual,
            'km_desde_ultimo': self.km_desde_ultimo,
            'gasolinera': self.gasolinera,
            'carreras': self.carreras,
            'observaciones': self.observaciones,
            'created_at': self.created_at.isoformat(),
        }


    __tablename__ = 'audit_log'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action     = db.Column(db.String(100))
    detail     = db.Column(db.Text)
    ip         = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)


class AppConfig(db.Model):
    """Global parameters editable from admin panel"""
    __tablename__ = 'app_config'
    key   = db.Column(db.String(100), primary_key=True)
    value = db.Column(db.Text)
    label = db.Column(db.String(255))
    type  = db.Column(db.String(20), default='text')  # text|number|bool|json


class AuditLog(db.Model):
    """Audit trail for admin actions and user logins"""
    __tablename__ = 'audit_logs'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action     = db.Column(db.String(100))
    detail     = db.Column(db.Text)
    ip         = db.Column(db.String(50))
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'user_id': self.user_id,
            'action': self.action, 'detail': self.detail,
            'created_at': self.created_at.isoformat()
        }


# ── Auth helpers ──────────────────────────────────────────────────────────────
def make_token(user_id, role):
    payload = {
        'sub': str(user_id),
        'role': role,
        'iat': datetime.datetime.utcnow(),
        'exp': datetime.datetime.utcnow() + datetime.timedelta(hours=app.config['TOKEN_EXPIRY_HOURS'])
    }
    return jwt.encode(payload, app.config['SECRET_KEY'], algorithm='HS256')

def decode_token(token):
    data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
    data['sub'] = int(data['sub'])
    return data

def get_bearer():
    h = request.headers.get('Authorization', '')
    return h.split(' ')[1] if h.startswith('Bearer ') else None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_bearer()
        if not token:
            return jsonify({'error': 'Token requerido'}), 401
        try:
            payload = decode_token(token)
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Sesión expirada'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token inválido'}), 401
        user = User.query.get(payload['sub'])
        if not user or user.status != 'active':
            return jsonify({'error': 'Acceso no autorizado'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = get_bearer()
        if not token:
            return jsonify({'error': 'Token requerido'}), 401
        try:
            payload = decode_token(token)
        except Exception:
            return jsonify({'error': 'Token inválido'}), 401
        if payload.get('role') != 'admin':
            return jsonify({'error': 'Acceso solo para administradores'}), 403
        user = User.query.get(payload['sub'])
        if not user or user.role != 'admin':
            return jsonify({'error': 'Acceso denegado'}), 403
        g.user = user
        return f(*args, **kwargs)
    return decorated

def log_action(action, detail='', user_id=None):
    entry = AuditLog(
        user_id=user_id or (g.user.id if hasattr(g, 'user') else None),
        action=action,
        detail=detail,
        ip=request.remote_addr
    )
    db.session.add(entry)
    db.session.commit()


# ── Auth routes ───────────────────────────────────────────────────────────────
@app.route('/auth/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    email    = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''
    nombre   = (data.get('nombre') or '').strip()
    empresa  = (data.get('empresa') or '').strip()
    ciudad   = (data.get('ciudad') or '').strip()
    telefono = (data.get('telefono') or '').strip()
    licencia = (data.get('licencia') or '').strip()
    marca    = (data.get('marca') or '').strip()
    modelo   = (data.get('modelo') or '').strip()
    combustible = (data.get('combustible') or '').strip()
    emisora  = data.get('emisora')   # {nombre, comision} or None
    apps     = data.get('apps')      # list or None

    if not email or not password or not nombre:
        return jsonify({'error': 'Email, contraseña y nombre son obligatorios'}), 400
    if len(password) < 8:
        return jsonify({'error': 'La contraseña debe tener al menos 8 caracteres'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Este email ya está registrado'}), 409

    user = User(email=email, nombre=nombre, empresa=empresa, ciudad=ciudad, telefono=telefono)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()  # get user.id
    # Store extra registration data as user data keys
    extra = {}
    if licencia:    extra['lt_licencia']    = licencia
    if marca:       extra['lt_marca']       = marca
    if modelo:      extra['lt_modelo']      = modelo
    if combustible: extra['lt_combustible'] = combustible
    if emisora:     extra['lt_emisora']     = json.dumps(emisora)
    if apps:        extra['lt_apps']        = json.dumps(apps)
    for key, value in extra.items():
        db.session.add(UserData(user_id=user.id, key=key, value=json.dumps(value)))
    db.session.commit()
    log_action('register', f'New user: {email}', user_id=user.id)
    return jsonify({
        'message': 'Registro completado. Tu solicitud está siendo revisada por el administrador.',
        'status': 'pending'
    }), 201


@app.route('/auth/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email    = (data.get('email') or '').strip().lower()
    password = data.get('password') or ''

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({'error': 'Email o contraseña incorrectos'}), 401

    if user.status == 'pending':
        return jsonify({'error': 'pending', 'message': 'Tu solicitud está pendiente de aprobación'}), 403
    if user.status == 'blocked':
        return jsonify({'error': 'blocked', 'message': 'Tu acceso ha sido bloqueado. Contacta con el administrador'}), 403

    # Check tokens if not admin
    if user.role != 'admin':
        if user.tokens_left <= 0:
            return jsonify({'error': 'no_tokens', 'message': 'No tienes tokens de acceso disponibles. Contacta con el administrador'}), 402
        if user.tokens_expiry and user.tokens_expiry < datetime.datetime.utcnow():
            return jsonify({'error': 'tokens_expired', 'message': 'Tu período de acceso ha expirado'}), 402

    user.last_login = datetime.datetime.utcnow()
    db.session.commit()
    log_action('login', f'Login: {email}', user_id=user.id)
    token = make_token(user.id, user.role)
    return jsonify({
        'token': token,
        'user': user.to_dict(),
        'expires_in': app.config['TOKEN_EXPIRY_HOURS'] * 3600
    })


@app.route('/auth/me', methods=['GET'])
@require_auth
def me():
    return jsonify(g.user.to_dict())


@app.route('/auth/status', methods=['POST'])
def check_status():
    """Check registration status without logging in"""
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    user = User.query.filter_by(email=email).first()
    if not user:
        return jsonify({'status': 'not_found'})
    return jsonify({'status': user.status})


# ── User data routes ──────────────────────────────────────────────────────────
@app.route('/api/data/<key>', methods=['GET'])
@require_auth
def get_data(key):
    row = UserData.query.filter_by(user_id=g.user.id, key=key).first()
    return jsonify({'key': key, 'value': json.loads(row.value) if row else []})


@app.route('/api/data/<key>', methods=['POST', 'PUT'])
@require_auth
def set_data(key):
    value = request.get_json()
    row = UserData.query.filter_by(user_id=g.user.id, key=key).first()
    if row:
        row.value = json.dumps(value)
        row.updated = datetime.datetime.utcnow()
    else:
        row = UserData(user_id=g.user.id, key=key, value=json.dumps(value))
        db.session.add(row)
    db.session.commit()
    return jsonify({'ok': True, 'key': key})


@app.route('/api/data', methods=['GET'])
@require_auth
def get_all_data():
    rows = UserData.query.filter_by(user_id=g.user.id).all()
    return jsonify({r.key: json.loads(r.value) for r in rows})


@app.route('/api/data', methods=['POST'])
@require_auth
def set_all_data():
    """Bulk import — accepts {key: value, ...}"""
    data = request.get_json() or {}
    for key, value in data.items():
        row = UserData.query.filter_by(user_id=g.user.id, key=key).first()
        if row:
            row.value = json.dumps(value)
        else:
            db.session.add(UserData(user_id=g.user.id, key=key, value=json.dumps(value)))
    db.session.commit()
    return jsonify({'ok': True, 'keys': list(data.keys())})


# ── Admin routes ──────────────────────────────────────────────────────────────
@app.route('/admin/users', methods=['GET'])
@require_admin
def admin_list_users():
    status = request.args.get('status')
    q = User.query
    if status:
        q = q.filter_by(status=status)
    users = q.order_by(User.created_at.desc()).all()
    return jsonify([u.to_dict(admin=True) for u in users])


@app.route('/admin/users/create', methods=['POST'])
@require_admin
def admin_create_user():
    data = request.get_json() or {}
    email    = data.get('email','').strip().lower()
    nombre   = data.get('nombre','').strip()
    password = data.get('password','')
    if not email or not nombre or not password:
        return jsonify({'error': 'Nombre, email y contraseña son obligatorios'}), 400
    if len(password) < 8:
        return jsonify({'error': 'La contraseña debe tener al menos 8 caracteres'}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({'error': 'Ya existe un usuario con ese email'}), 409
    user = User(
        email        = email,
        nombre       = nombre,
        ciudad       = data.get('ciudad',''),
        telefono     = data.get('telefono',''),
        role         = data.get('role','user'),
        status       = data.get('status','active'),
        tokens_left  = int(data.get('tokens_left', 30)),
        notes        = data.get('notas',''),
    )
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    # Save extra fields as UserData
    extras = {}
    if data.get('licencia'): extras['licencia'] = data['licencia']
    if data.get('vehiculo'): extras['vehiculo'] = data['vehiculo']
    if extras:
        db.session.add(UserData(user_id=user.id, key='lt_sets', value=json.dumps(extras)))
        db.session.commit()
    log_action('admin_create_user', f'Creado: {email}', user_id=g.user.id)
    return jsonify({'ok': True, 'id': user.id}), 201


@app.route('/admin/users/<int:uid>', methods=['GET'])
@require_admin
def admin_get_user(uid):
    user = User.query.get_or_404(uid)
    return jsonify(user.to_dict(admin=True))


@app.route('/admin/users/<int:uid>', methods=['PUT'])
@require_admin
def admin_update_user(uid):
    user = User.query.get_or_404(uid)
    data = request.get_json() or {}
    old_status = user.status

    if 'status' in data:
        user.status = data['status']
    if 'role' in data and data['role'] in ('admin', 'user'):
        user.role = data['role']
    if 'notes' in data:
        user.notes = data['notes']
    if 'tokens_left' in data:
        user.tokens_left = int(data['tokens_left'])
    if 'tokens_expiry' in data:
        user.tokens_expiry = datetime.datetime.fromisoformat(data['tokens_expiry']) if data['tokens_expiry'] else None

    db.session.commit()
    log_action('admin_update_user', f'User {uid}: {old_status} → {user.status}')
    return jsonify({'ok': True, 'user': user.to_dict(admin=True)})


@app.route('/admin/users/<int:uid>/approve', methods=['POST'])
@require_admin
def admin_approve(uid):
    user = User.query.get_or_404(uid)
    data = request.get_json() or {}
    user.status = 'active'
    # Grant tokens on approval
    tokens = int(data.get('tokens', 30))
    days   = int(data.get('days', 30))
    user.tokens_left   = tokens
    user.tokens_expiry = datetime.datetime.utcnow() + datetime.timedelta(days=days)
    db.session.commit()
    log_action('admin_approve', f'Approved user {uid} ({user.email}) — {tokens} tokens, {days} days')
    return jsonify({'ok': True, 'message': f'Usuario {user.nombre} aprobado con {tokens} tokens por {days} días'})


@app.route('/admin/users/<int:uid>/block', methods=['POST'])
@require_admin
def admin_block(uid):
    user = User.query.get_or_404(uid)
    if user.role == 'admin':
        return jsonify({'error': 'No puedes bloquear un administrador'}), 400
    user.status = 'blocked'
    db.session.commit()
    log_action('admin_block', f'Blocked user {uid} ({user.email})')
    return jsonify({'ok': True})


@app.route('/admin/users/<int:uid>/tokens', methods=['POST'])
@require_admin
def admin_add_tokens(uid):
    user = User.query.get_or_404(uid)
    data = request.get_json() or {}
    tokens = int(data.get('tokens', 30))
    days   = int(data.get('days', 30))
    user.tokens_left   = (user.tokens_left or 0) + tokens
    user.tokens_expiry = datetime.datetime.utcnow() + datetime.timedelta(days=days)
    if user.status != 'active':
        user.status = 'active'
    db.session.commit()
    log_action('admin_add_tokens', f'Added {tokens} tokens to user {uid} ({user.email}), {days} days')
    return jsonify({'ok': True, 'tokens_left': user.tokens_left})


@app.route('/admin/users/<int:uid>', methods=['DELETE'])
@require_admin
def admin_delete_user(uid):
    user = User.query.get_or_404(uid)
    if user.role == 'admin':
        return jsonify({'error': 'No puedes eliminar un administrador'}), 400
    UserData.query.filter_by(user_id=uid).delete()
    db.session.delete(user)
    db.session.commit()
    log_action('admin_delete_user', f'Deleted user {uid} ({user.email})')
    return jsonify({'ok': True})


@app.route('/admin/stats', methods=['GET'])
@require_admin
def admin_stats():
    total   = User.query.count()
    pending = User.query.filter_by(status='pending').count()
    active  = User.query.filter_by(status='active').count()
    blocked = User.query.filter_by(status='blocked').count()
    recent  = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(20).all()
    return jsonify({
        'users': {'total': total, 'pending': pending, 'active': active, 'blocked': blocked},
        'recent_activity': [{'action': l.action, 'detail': l.detail, 'ip': l.ip,
                              'created_at': l.created_at.isoformat(), 'user_id': l.user_id} for l in recent]
    })


# ── App config routes ─────────────────────────────────────────────────────────
@app.route('/admin/config', methods=['GET'])
@require_admin
def admin_get_config():
    rows = AppConfig.query.all()
    return jsonify({r.key: {'value': r.value, 'label': r.label, 'type': r.type} for r in rows})


@app.route('/admin/config', methods=['POST'])
@require_admin
def admin_set_config():
    data = request.get_json() or {}
    for key, val in data.items():
        row = AppConfig.query.get(key)
        if row:
            row.value = str(val)
        else:
            db.session.add(AppConfig(key=key, value=str(val)))
    db.session.commit()
    log_action('admin_config', f'Updated: {list(data.keys())}')
    return jsonify({'ok': True})


@app.route('/api/config', methods=['GET'])
@require_auth
def get_public_config():
    """Public config available to all active users"""
    PUBLIC_KEYS = ['app_name', 'app_version', 'maintenance_mode', 'welcome_message']
    rows = AppConfig.query.filter(AppConfig.key.in_(PUBLIC_KEYS)).all()
    return jsonify({r.key: r.value for r in rows})


# ── Conductor jornada routes ──────────────────────────────────────────────────
@app.route('/jornada', methods=['GET'])
@require_auth
def get_jornadas():
    """Get own jornadas (conductor) or all for admin"""
    if g.user.role == 'admin':
        uid = request.args.get('user_id')
        q = Jornada.query
        if uid:
            q = q.filter_by(user_id=int(uid))
        jornadas = q.order_by(Jornada.fecha.desc()).limit(200).all()
    else:
        jornadas = Jornada.query.filter_by(user_id=g.user.id).order_by(Jornada.fecha.desc()).limit(200).all()
    # Include user name for admin view
    result = []
    for j in jornadas:
        d = j.to_dict()
        if g.user.role == 'admin':
            u = User.query.get(j.user_id)
            d['conductor_nombre'] = u.nombre if u else '—'
        result.append(d)
    return jsonify(result)


@app.route('/jornada', methods=['POST'])
@require_auth
def save_jornada():
    data = request.get_json() or {}
    fecha = data.get('fecha')
    if not fecha:
        return jsonify({'error': 'La fecha es obligatoria'}), 400

    existing = Jornada.query.filter_by(user_id=g.user.id, fecha=fecha).first()
    if existing:
        existing.hora_inicio    = data.get('hora_inicio', existing.hora_inicio)
        existing.hora_fin       = data.get('hora_fin', existing.hora_fin)
        existing.total_factura  = float(data.get('total_factura', existing.total_factura or 0))
        existing.propinas       = float(data.get('propinas', existing.propinas or 0))
        existing.repostaje_l    = float(data.get('repostaje_l', existing.repostaje_l or 0))
        existing.repostaje_e    = float(data.get('repostaje_e', existing.repostaje_e or 0))
        existing.repostaje_tipo = data.get('repostaje_tipo', existing.repostaje_tipo)
        existing.km_actual      = int(data.get('km_actual', existing.km_actual or 0))
        existing.km_desde_ultimo= int(data.get('km_desde_ultimo', existing.km_desde_ultimo or 0))
        existing.gasolinera     = data.get('gasolinera', existing.gasolinera)
        existing.carreras       = data.get('carreras', existing.carreras)
        existing.observaciones  = data.get('observaciones', existing.observaciones)
        existing.updated_at     = datetime.datetime.utcnow()
        db.session.commit()
        return jsonify({'ok': True, 'id': existing.id, 'action': 'updated'})

    j = Jornada(
        user_id        = g.user.id,
        fecha          = fecha,
        hora_inicio    = data.get('hora_inicio'),
        hora_fin       = data.get('hora_fin'),
        total_factura  = float(data.get('total_factura', 0)),
        propinas       = float(data.get('propinas', 0)),
        repostaje_l    = float(data.get('repostaje_l', 0)),
        repostaje_e    = float(data.get('repostaje_e', 0)),
        repostaje_tipo = data.get('repostaje_tipo'),
        km_actual      = int(data.get('km_actual', 0)),
        km_desde_ultimo= int(data.get('km_desde_ultimo', 0)),
        gasolinera     = data.get('gasolinera'),
        carreras       = data.get('carreras'),
        observaciones  = data.get('observaciones'),
    )
    db.session.add(j)
    db.session.commit()
    log_action('jornada_save', f'Jornada {fecha}', user_id=g.user.id)
    return jsonify({'ok': True, 'id': j.id, 'action': 'created'}), 201


@app.route('/jornada/<int:jid>', methods=['DELETE'])
@require_auth
def delete_jornada(jid):
    j = Jornada.query.get_or_404(jid)
    if j.user_id != g.user.id and g.user.role != 'admin':
        return jsonify({'error': 'Sin permiso'}), 403
    db.session.delete(j)
    db.session.commit()
    return jsonify({'ok': True})


@app.route('/admin/jornadas', methods=['GET'])
@require_admin
def admin_get_all_jornadas():
    """Admin: get all jornadas with conductor names"""
    uid = request.args.get('user_id')
    q = Jornada.query
    if uid:
        q = q.filter_by(user_id=int(uid))
    jornadas = q.order_by(Jornada.fecha.desc()).limit(500).all()
    result = []
    user_cache = {}
    for j in jornadas:
        d = j.to_dict()
        if j.user_id not in user_cache:
            u = User.query.get(j.user_id)
            user_cache[j.user_id] = u.nombre if u else '—'
        d['conductor_nombre'] = user_cache[j.user_id]
        result.append(d)
    return jsonify(result)


# ── Static files ──────────────────────────────────────────────────────────────

@app.route('/health')
def health():
    try:
        db.session.execute(db.text('SELECT 1'))
        return jsonify({'status':'ok','db':'ok'})
    except Exception as e:
        return jsonify({'status':'error','db':str(e)}),500

@app.route('/')
def index():
    return send_from_directory('static', 'login.html')

@app.route('/app')
@app.route('/app/')
def app_page():
    return send_from_directory('static', 'app.html')

@app.route('/admin-panel')
def admin_panel():
    return send_from_directory('static', 'admin.html')

class SoporteTicket(db.Model):
    __tablename__ = 'soporte_tickets'
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    ticket_ref = db.Column(db.String(30))
    tipo       = db.Column(db.String(50))
    asunto     = db.Column(db.String(255))
    mensaje    = db.Column(db.Text)
    email      = db.Column(db.String(255))
    estado     = db.Column(db.String(20), default='enviado')
    respuesta  = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id, 'ticket_ref': self.ticket_ref,
            'tipo': self.tipo, 'asunto': self.asunto,
            'estado': self.estado, 'respuesta': self.respuesta,
            'created_at': self.created_at.isoformat()
        }


# ── Soporte routes ────────────────────────────────────────────────────────────
@app.route('/soporte', methods=['POST'])
@require_auth
def create_ticket():
    data = request.get_json() or {}
    ticket = SoporteTicket(
        user_id    = g.user.id,
        ticket_ref = data.get('id', 'TK-' + str(int(datetime.datetime.utcnow().timestamp()))),
        tipo       = data.get('tipo', 'otro'),
        asunto     = data.get('asunto', ''),
        mensaje    = data.get('mensaje', ''),
        email      = data.get('email') or g.user.email,
    )
    db.session.add(ticket)
    db.session.commit()
    log_action('soporte_ticket', f'Ticket: {ticket.asunto[:50]}', user_id=g.user.id)
    return jsonify({'ok': True, 'ticket_ref': ticket.ticket_ref}), 201


@app.route('/soporte', methods=['GET'])
@require_auth
def get_tickets():
    tickets = SoporteTicket.query.filter_by(user_id=g.user.id).order_by(SoporteTicket.created_at.desc()).all()
    return jsonify([t.to_dict() for t in tickets])


@app.route('/admin/soporte', methods=['GET'])
@require_admin
def admin_get_tickets():
    tickets = SoporteTicket.query.order_by(SoporteTicket.created_at.desc()).limit(200).all()
    result = []
    for t in tickets:
        d = t.to_dict()
        u = User.query.get(t.user_id)
        d['user_nombre'] = u.nombre if u else '—'
        d['user_email']  = u.email if u else t.email
        d['mensaje'] = t.mensaje
        result.append(d)
    return jsonify(result)


@app.route('/admin/soporte/<int:tid>', methods=['PUT'])
@require_admin
def admin_update_ticket(tid):
    ticket = SoporteTicket.query.get_or_404(tid)
    data = request.get_json() or {}
    if 'estado'    in data: ticket.estado    = data['estado']
    if 'respuesta' in data: ticket.respuesta = data['respuesta']
    ticket.updated_at = datetime.datetime.utcnow()
    db.session.commit()
    return jsonify({'ok': True})


# ── Public API routes (for external integrations) ─────────────────────────────
@app.route('/api/v1/ingresos', methods=['POST'])
@require_auth
def api_add_ingreso():
    """
    Public API: Add income transaction
    POST /api/v1/ingresos
    Body: { "categoria": "Uber", "importe": 25.50, "fecha": "2025-08-30",
            "nota": "opcional", "conductor": "JYL" }
    """
    data = request.get_json() or {}
    if not data.get('importe') or not data.get('fecha'):
        return jsonify({'error': 'importe y fecha son obligatorios'}), 400

    row = UserData.query.filter_by(user_id=g.user.id, key='lt_tx').first()
    txs = json.loads(row.value) if row else []

    new_tx = {
        'id': int(datetime.datetime.utcnow().timestamp() * 1000),
        'type': 'income',
        'category': data.get('categoria', 'Calle'),
        'amount': float(data['importe']),
        'date': data['fecha'],
        'note': data.get('nota', ''),
        'conductor': data.get('conductor', ''),
        'source': 'api'
    }
    txs.insert(0, new_tx)

    if row:
        row.value = json.dumps(txs)
    else:
        db.session.add(UserData(user_id=g.user.id, key='lt_tx', value=json.dumps(txs)))
    db.session.commit()
    return jsonify({'ok': True, 'id': new_tx['id']}), 201


@app.route('/api/v1/gastos', methods=['POST'])
@require_auth
def api_add_gasto():
    """
    Public API: Add expense transaction
    POST /api/v1/gastos
    Body: { "categoria": "Gasolina", "importe": 45.00, "fecha": "2025-08-30", "nota": "opcional" }
    """
    data = request.get_json() or {}
    if not data.get('importe') or not data.get('fecha'):
        return jsonify({'error': 'importe y fecha son obligatorios'}), 400

    row = UserData.query.filter_by(user_id=g.user.id, key='lt_tx').first()
    txs = json.loads(row.value) if row else []

    new_tx = {
        'id': int(datetime.datetime.utcnow().timestamp() * 1000),
        'type': 'expense',
        'category': data.get('categoria', 'Coche'),
        'amount': float(data['importe']),
        'date': data['fecha'],
        'note': data.get('nota', ''),
        'source': 'api'
    }
    txs.insert(0, new_tx)

    if row:
        row.value = json.dumps(txs)
    else:
        db.session.add(UserData(user_id=g.user.id, key='lt_tx', value=json.dumps(txs)))
    db.session.commit()
    return jsonify({'ok': True, 'id': new_tx['id']}), 201


@app.route('/api/v1/repostaje', methods=['POST'])
@require_auth
def api_add_repostaje():
    """
    Public API: Add fuel record
    POST /api/v1/repostaje
    Body: { "tipo": "gasolina|glp", "litros": 40.0, "importe": 58.50,
            "precio_litro": 1.46, "km": 125000, "gasolinera": "Repsol Alcalá", "fecha": "2025-08-30" }
    """
    data = request.get_json() or {}
    if not data.get('importe') or not data.get('fecha'):
        return jsonify({'error': 'importe y fecha son obligatorios'}), 400

    row = UserData.query.filter_by(user_id=g.user.id, key='lt_fuel').first()
    fuel = json.loads(row.value) if row else []

    new_fuel = {
        'id': int(datetime.datetime.utcnow().timestamp() * 1000),
        'type': data.get('tipo', 'gasolina'),
        'total': float(data['importe']),
        'litros': float(data.get('litros', 0)),
        'precioL': float(data.get('precio_litro', 0)),
        'km': int(data.get('km', 0)),
        'station': data.get('gasolinera', ''),
        'date': data['fecha'],
        'conductor': data.get('conductor', ''),
        'source': 'api'
    }
    fuel.insert(0, new_fuel)

    if row:
        row.value = json.dumps(fuel)
    else:
        db.session.add(UserData(user_id=g.user.id, key='lt_fuel', value=json.dumps(fuel)))
    db.session.commit()
    return jsonify({'ok': True, 'id': new_fuel['id']}), 201


@app.route('/api/v1/resumen', methods=['GET'])
@require_auth
def api_resumen():
    """
    Public API: Get monthly summary
    GET /api/v1/resumen?mes=8&anio=2025
    """
    mes  = request.args.get('mes',  datetime.datetime.utcnow().month,  type=int)
    anio = request.args.get('anio', datetime.datetime.utcnow().year,   type=int)

    row = UserData.query.filter_by(user_id=g.user.id, key='lt_tx').first()
    txs = json.loads(row.value) if row else []

    mes_txs = [t for t in txs if datetime.datetime.strptime(t['date'], '%Y-%m-%d').month == mes
               and datetime.datetime.strptime(t['date'], '%Y-%m-%d').year == anio]

    ingresos = sum(t['amount'] for t in mes_txs if t['type'] == 'income')
    gastos   = sum(t['amount'] for t in mes_txs if t['type'] == 'expense')

    return jsonify({
        'mes': mes, 'anio': anio,
        'ingresos': round(ingresos, 2),
        'gastos':   round(gastos, 2),
        'beneficio': round(ingresos - gastos, 2),
        'movimientos': len(mes_txs)
    })


@app.route('/conductor')
@app.route('/conductor/')
def conductor_panel():
    return send_from_directory('static', 'conductor.html')

@app.route('/static/<path:path>')
def static_files(path):
    return send_from_directory('static', path)


# ── Init ──────────────────────────────────────────────────────────────────────
def init_db():
    db.create_all()  # Creates all models including SoporteTicket, Jornada
    # Create admin user if not exists
    admin_email = app.config['ADMIN_EMAIL']
    if not User.query.filter_by(email=admin_email).first():
        admin = User(
            email=admin_email,
            nombre='Administrador LamboTaxi',
            role='admin',
            status='active',
            tokens_left=999999
        )
        admin.set_password(app.config['ADMIN_PASSWORD'])
        db.session.add(admin)
        # Default app config
        defaults = [
            AppConfig(key='app_name', value='LamboTaxi', label='Nombre de la app', type='text'),
            AppConfig(key='app_version', value='1.0.0', label='Versión', type='text'),
            AppConfig(key='maintenance_mode', value='false', label='Modo mantenimiento', type='bool'),
            AppConfig(key='welcome_message', value='Bienvenido a LamboTaxi', label='Mensaje de bienvenida', type='text'),
            AppConfig(key='tokens_per_month', value='30', label='Tokens por mes (por defecto)', type='number'),
            AppConfig(key='trial_days', value='14', label='Días de prueba gratuitos', type='number'),
            AppConfig(key='max_users', value='100', label='Máximo de usuarios activos', type='number'),
        ]
        db.session.add_all(defaults)
        db.session.commit()
        print(f"✅ Admin creado: {admin_email}")
    print("✅ Base de datos iniciada")


# ── Init DB on startup (works with both gunicorn and flask run) ───────────────
with app.app_context():
    try:
        init_db()
    except Exception as e:
        print(f"⚠️ init_db error: {e}")


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV', 'production') == 'development'
    print(f"🚀 LamboTaxi server en http://localhost:{port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
