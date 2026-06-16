import os
import hashlib
import secrets
import requests as http_requests
from datetime import datetime, timedelta
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, jsonify, flash, abort, send_from_directory)
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
from sqlalchemy import func

import sqlite3
from sqlalchemy import event
from sqlalchemy.engine import Engine

import config
from models import db, Story, Vote, Sticker, Reaction, Reply, Admin


@event.listens_for(Engine, "connect")
def set_sqlite_wal(dbapi_con, _):
    if isinstance(dbapi_con, sqlite3.Connection):
        dbapi_con.execute("PRAGMA journal_mode=WAL")

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.secret_key = config.SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = config.DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = config.UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)

STICKER_FOLDER = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'stickers')
os.makedirs(STICKER_FOLDER, exist_ok=True)

db.init_app(app)

limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri='memory://',
)

AVATARS    = ['🐱','🐶','🦊','🐻','🐼','🦁','🐸','🦄','🐺','🐨','🐯','🦝']
AGE_RANGES = ['Menos de 18','18-25','26-35','36-45','46-60','Más de 60']

DEFAULT_STICKERS = [
    {'name': 'LOL',     'type': 'emoji', 'value': '😂'},
    {'name': 'Nooo',    'type': 'emoji', 'value': '😭'},
    {'name': 'Fuego',   'type': 'emoji', 'value': '🔥'},
    {'name': 'Muerto',  'type': 'emoji', 'value': '💀'},
    {'name': 'OMG',     'type': 'emoji', 'value': '😱'},
    {'name': 'Shh',     'type': 'emoji', 'value': '🤫'},
    {'name': 'Amor',    'type': 'emoji', 'value': '💜'},
    {'name': 'Respeto', 'type': 'emoji', 'value': '🫡'},
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def voter_token(ip: str) -> str:
    raw = f"{ip}:{config.VOTE_SALT}"
    return hashlib.sha256(raw.encode()).hexdigest()


def country_flag(code: str, name: str = '') -> str:
    if not code or len(code) != 2:
        return ''
    c = code.lower()
    return (f'<img src="https://flagcdn.com/20x15/{c}.png" '
            f'srcset="https://flagcdn.com/40x30/{c}.png 2x" '
            f'alt="{code}" title="{name}" class="country-flag-img" loading="lazy">')


def get_country(ip: str) -> tuple[str, str]:
    # En local usamos la IP pública de la máquina (sin pasar IP al endpoint)
    url = 'http://ip-api.com/json/?fields=countryCode,country' \
          if ip in ('127.0.0.1', '::1', 'localhost') \
          else f'http://ip-api.com/json/{ip}?fields=countryCode,country'
    try:
        r = http_requests.get(url, timeout=2)
        data = r.json()
        return (data.get('countryCode', ''), data.get('country', ''))
    except Exception:
        return ('', '')


def allowed_file(filename: str) -> bool:
    return (
        '.' in filename
        and filename.rsplit('.', 1)[1].lower() in config.ALLOWED_EXTENSIONS
    )


def save_image(file) -> str | None:
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        return None
    ext = file.filename.rsplit('.', 1)[1].lower()
    unique_name = f"{secrets.token_hex(16)}.{ext}"
    path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    img = Image.open(file)
    img.thumbnail((1200, 1200), Image.LANCZOS)
    if img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
        unique_name = unique_name.rsplit('.', 1)[0] + '.jpg'
        path = os.path.join(app.config['UPLOAD_FOLDER'], unique_name)
    img.save(path, optimize=True, quality=85)
    return unique_name


def generate_csrf() -> str:
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_hex(32)
    return session['_csrf']


def validate_csrf(token: str) -> bool:
    return token == session.get('_csrf')


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_id'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


def reactions_for_stories(story_ids, my_token):
    if not story_ids:
        return {}, {}
    rows = db.session.query(
        Reaction.story_id,
        Reaction.sticker_id,
        func.count(Reaction.id).label('cnt')
    ).filter(Reaction.story_id.in_(story_ids))\
     .group_by(Reaction.story_id, Reaction.sticker_id).all()

    by_story = {}
    for r in rows:
        by_story.setdefault(r.story_id, {})[r.sticker_id] = r.cnt

    my_reacts = {
        r.story_id: r.sticker_id
        for r in Reaction.query.filter(
            Reaction.story_id.in_(story_ids),
            Reaction.voter_token == my_token
        ).all()
    }
    return by_story, my_reacts


app.jinja_env.globals['csrf_token']    = generate_csrf
app.jinja_env.globals['now']           = datetime.utcnow
app.jinja_env.globals['AVATARS']       = AVATARS
app.jinja_env.globals['AGE_RANGES']    = AGE_RANGES
app.jinja_env.globals['country_flag']  = country_flag


# ---------------------------------------------------------------------------
# Rutas públicas
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    sort  = request.args.get('sort', 'new')
    page  = request.args.get('page', 1, type=int)
    query = Story.query.filter_by(is_hidden=False)

    if sort == 'top':
        query = query.order_by(Story.vote_count.desc(), Story.created_at.desc())
    elif sort == 'trending':
        stories_all = query.all()
        stories_all.sort(key=lambda s: s.trending_score(), reverse=True)
        total = len(stories_all)
        per   = config.STORIES_PER_PAGE
        start = (page - 1) * per
        stories     = stories_all[start:start + per]
        total_pages = (total + per - 1) // per
    else:
        query = query.order_by(Story.created_at.desc())
        pagination  = query.paginate(page=page, per_page=config.STORIES_PER_PAGE, error_out=False)
        stories     = pagination.items
        total_pages = pagination.pages

    if sort != 'trending':
        pagination  = query.paginate(page=page, per_page=config.STORIES_PER_PAGE, error_out=False)
        stories     = pagination.items
        total_pages = pagination.pages

    ip    = request.remote_addr or '0.0.0.0'
    token = voter_token(ip)
    story_ids = [s.id for s in stories]
    reactions_map, my_reacts = reactions_for_stories(story_ids, token)

    active_stickers = Sticker.query.filter_by(is_active=True)\
                             .order_by(Sticker.sort_order, Sticker.id).all()

    reply_counts = {}
    if story_ids:
        rows = db.session.query(Reply.story_id, func.count(Reply.id).label('cnt'))\
                         .filter(Reply.story_id.in_(story_ids), Reply.is_hidden == False)\
                         .group_by(Reply.story_id).all()
        reply_counts = {r.story_id: r.cnt for r in rows}

    return render_template('index.html',
                           stories=stories, sort=sort,
                           page=page, total_pages=total_pages,
                           reactions_map=reactions_map,
                           my_reacts=my_reacts,
                           active_stickers=active_stickers,
                           reply_counts=reply_counts)


@app.route('/submit', methods=['GET', 'POST'])
@limiter.limit('3 per hour', methods=['POST'])
def submit():
    if request.method == 'POST':
        csrf = request.form.get('csrf_token', '')
        if not validate_csrf(csrf):
            abort(403)

        content = request.form.get('content', '').strip()
        if not content or len(content) > 2000:
            flash('La historia debe tener entre 1 y 2000 caracteres.', 'error')
            return render_template('submit.html')

        image_file = request.files.get('image')
        image_name = None
        if image_file and image_file.filename:
            try:
                image_name = save_image(image_file)
                if not image_name:
                    flash('Formato de imagen no permitido.', 'error')
                    return render_template('submit.html')
            except Exception:
                flash('Error al procesar la imagen.', 'error')
                return render_template('submit.html')

        avatar = request.form.get('avatar', '🐱')
        if avatar not in AVATARS:
            avatar = '🐱'

        age_range = request.form.get('age_range', '').strip()
        if age_range not in AGE_RANGES:
            age_range = None

        ip = request.remote_addr or '0.0.0.0'
        country_code, country_name = get_country(ip)

        story = Story(
            content=content, image_path=image_name,
            avatar=avatar, age_range=age_range,
            country_code=country_code, country_name=country_name,
        )
        db.session.add(story)
        db.session.commit()
        flash('¡Tu secreto ha sido compartido!', 'success')
        return redirect(url_for('index'))

    return render_template('submit.html')


@app.route('/story/<int:story_id>', methods=['GET', 'POST'])
@limiter.limit('3 per hour', methods=['POST'])
def story_detail(story_id):
    story = Story.query.filter_by(id=story_id, is_hidden=False).first_or_404()

    if request.method == 'POST':
        csrf = request.form.get('csrf_token', '')
        if not validate_csrf(csrf):
            abort(403)
        content = request.form.get('content', '').strip()
        if not content or len(content) > 1000:
            flash('La respuesta debe tener entre 1 y 1000 caracteres.', 'error')
        else:
            avatar = request.form.get('avatar', '🐱')
            if avatar not in AVATARS:
                avatar = '🐱'
            age_range = request.form.get('age_range', '').strip()
            if age_range not in AGE_RANGES:
                age_range = None
            ip = request.remote_addr or '0.0.0.0'
            country_code, country_name = get_country(ip)
            reply = Reply(
                story_id=story_id, content=content,
                avatar=avatar, age_range=age_range,
                country_code=country_code, country_name=country_name,
            )
            db.session.add(reply)
            db.session.commit()
            flash('¡Tu respuesta ha sido publicada!', 'success')
            return redirect(url_for('index'))

    replies = Reply.query.filter_by(story_id=story_id, is_hidden=False)\
                         .order_by(Reply.created_at.asc()).all()

    ip = request.remote_addr or '0.0.0.0'
    token = voter_token(ip)
    reactions_map, my_reacts = reactions_for_stories([story_id], token)
    active_stickers = Sticker.query.filter_by(is_active=True)\
                             .order_by(Sticker.sort_order, Sticker.id).all()

    is_admin = bool(session.get('admin_id'))

    return render_template('story.html',
                           story=story, replies=replies,
                           reactions_map=reactions_map, my_reacts=my_reacts,
                           active_stickers=active_stickers,
                           is_admin=is_admin)


@app.route('/admin/reply/<int:reply_id>/hide', methods=['POST'])
@admin_required
def admin_reply_hide(reply_id):
    reply = Reply.query.get_or_404(reply_id)
    reply.is_hidden = not reply.is_hidden
    db.session.commit()
    return redirect(request.referrer or url_for('story_detail', story_id=reply.story_id))


@app.route('/admin/reply/<int:reply_id>/delete', methods=['POST'])
@admin_required
def admin_reply_delete(reply_id):
    reply = Reply.query.get_or_404(reply_id)
    story_id = reply.story_id
    db.session.delete(reply)
    db.session.commit()
    flash('Respuesta eliminada.', 'success')
    return redirect(request.referrer or url_for('story_detail', story_id=story_id))


@app.route('/api/react/<int:story_id>/<int:sticker_id>', methods=['POST'])
@limiter.limit('60 per minute')
def react(story_id, sticker_id):
    story   = Story.query.filter_by(id=story_id, is_hidden=False).first()
    sticker = Sticker.query.filter_by(id=sticker_id, is_active=True).first()
    if not story or not sticker:
        return jsonify({'error': 'no encontrado'}), 404

    ip    = request.remote_addr or '0.0.0.0'
    token = voter_token(ip)
    existing = Reaction.query.filter_by(story_id=story_id, voter_token=token).first()

    if existing:
        if existing.sticker_id == sticker_id:
            # Misma reacción → quitar
            story.vote_count = max(0, story.vote_count - 1)
            db.session.delete(existing)
            db.session.commit()
            return jsonify({'ok': True, 'removed': True,
                            'reactions': _reactions_data(story_id),
                            'total': story.vote_count})
        else:
            # Cambiar de sticker
            existing.sticker_id = sticker_id
            db.session.commit()
            return jsonify({'ok': True, 'changed': True, 'my_sticker': sticker_id,
                            'reactions': _reactions_data(story_id),
                            'total': story.vote_count})

    # Nueva reacción
    db.session.add(Reaction(story_id=story_id, sticker_id=sticker_id, voter_token=token))
    story.vote_count += 1
    db.session.commit()
    return jsonify({'ok': True, 'my_sticker': sticker_id,
                    'reactions': _reactions_data(story_id),
                    'total': story.vote_count})


def _reactions_data(story_id):
    rows = db.session.query(
        Reaction.sticker_id, func.count(Reaction.id).label('cnt')
    ).filter(Reaction.story_id == story_id).group_by(Reaction.sticker_id).all()
    result = []
    for r in rows:
        s = Sticker.query.get(r.sticker_id)
        if s:
            result.append({'sticker_id': s.id, 'count': r.cnt,
                           'type': s.sticker_type, 'value': s.value, 'name': s.name})
    return sorted(result, key=lambda x: x['count'], reverse=True)


@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/stickers/<path:filename>')
def sticker_file(filename):
    return send_from_directory(STICKER_FOLDER, filename)


# ---------------------------------------------------------------------------
# Admin — historias
# ---------------------------------------------------------------------------

@app.route('/admin/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def admin_login():
    if session.get('admin_id'):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session.permanent = True
            session['admin_id'] = admin.id
            session['admin_username'] = admin.username
            return redirect(url_for('admin_dashboard'))
        flash('Credenciales incorrectas.', 'error')
    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('index'))


@app.route('/admin/')
@admin_required
def admin_dashboard():
    filter_by = request.args.get('filter', 'all')
    search    = request.args.get('q', '').strip()
    page      = request.args.get('page', 1, type=int)

    query = Story.query
    if filter_by == 'visible':
        query = query.filter_by(is_hidden=False)
    elif filter_by == 'hidden':
        query = query.filter_by(is_hidden=True)
    elif filter_by == 'edited':
        query = query.filter_by(is_edited=True)
    if search:
        query = query.filter(Story.content.ilike(f'%{search}%'))

    pagination = query.order_by(Story.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False)

    return render_template('admin/dashboard.html',
                           stories=pagination.items, pagination=pagination,
                           filter_by=filter_by, search=search, page=page)


@app.route('/admin/story/<int:story_id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit(story_id):
    story = Story.query.get_or_404(story_id)
    if request.method == 'POST':
        new_content = request.form.get('content', '').strip()
        note        = request.form.get('note', '').strip()
        if not new_content or len(new_content) > 2000:
            flash('Contenido inválido.', 'error')
            return render_template('admin/edit_story.html', story=story)
        story.content  = new_content
        story.is_edited = True
        story.edit_note = note or None
        db.session.commit()
        flash('Historia actualizada.', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/edit_story.html', story=story)


@app.route('/admin/story/<int:story_id>/hide', methods=['POST'])
@admin_required
def admin_hide(story_id):
    story = Story.query.get_or_404(story_id)
    story.is_hidden = not story.is_hidden
    db.session.commit()
    state = 'ocultada' if story.is_hidden else 'visible'
    flash(f'Historia {state}.', 'success')
    return redirect(request.referrer or url_for('admin_dashboard'))


@app.route('/admin/story/<int:story_id>/delete', methods=['POST'])
@admin_required
def admin_delete(story_id):
    story = Story.query.get_or_404(story_id)
    if story.image_path:
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], story.image_path)
        if os.path.exists(img_path):
            os.remove(img_path)
    db.session.delete(story)
    db.session.commit()
    flash('Historia eliminada permanentemente.', 'success')
    return redirect(url_for('admin_dashboard'))


# ---------------------------------------------------------------------------
# Admin — stickers
# ---------------------------------------------------------------------------

@app.route('/admin/stickers')
@admin_required
def admin_stickers():
    stickers = Sticker.query.order_by(Sticker.sort_order, Sticker.id).all()
    return render_template('admin/stickers.html', stickers=stickers)


@app.route('/admin/stickers/upload', methods=['POST'])
@admin_required
def admin_sticker_upload():
    name = request.form.get('name', '').strip()
    file = request.files.get('sticker')
    if not name or not file or not file.filename:
        flash('Nombre e imagen requeridos.', 'error')
        return redirect(url_for('admin_stickers'))
    ext = file.filename.rsplit('.', 1)[-1].lower()
    if ext not in {'png', 'gif', 'webp', 'jpg', 'jpeg'}:
        flash('Formato no válido. Usa PNG, GIF, WEBP o JPG.', 'error')
        return redirect(url_for('admin_stickers'))
    filename = f"sticker_{secrets.token_hex(8)}.{ext}"
    file.save(os.path.join(STICKER_FOLDER, filename))
    max_order = db.session.query(func.max(Sticker.sort_order)).scalar() or 0
    db.session.add(Sticker(name=name, sticker_type='image', value=filename, sort_order=max_order + 1))
    db.session.commit()
    flash(f'Sticker "{name}" añadido.', 'success')
    return redirect(url_for('admin_stickers'))


@app.route('/admin/stickers/add-emoji', methods=['POST'])
@admin_required
def admin_sticker_add_emoji():
    name  = request.form.get('name', '').strip()
    emoji = request.form.get('emoji', '').strip()
    if not name or not emoji:
        flash('Nombre y emoji requeridos.', 'error')
        return redirect(url_for('admin_stickers'))
    max_order = db.session.query(func.max(Sticker.sort_order)).scalar() or 0
    db.session.add(Sticker(name=name, sticker_type='emoji', value=emoji, sort_order=max_order + 1))
    db.session.commit()
    flash(f'Sticker "{name}" añadido.', 'success')
    return redirect(url_for('admin_stickers'))


@app.route('/admin/stickers/<int:sticker_id>/toggle', methods=['POST'])
@admin_required
def admin_sticker_toggle(sticker_id):
    sticker = Sticker.query.get_or_404(sticker_id)
    sticker.is_active = not sticker.is_active
    db.session.commit()
    return redirect(url_for('admin_stickers'))


@app.route('/admin/stickers/<int:sticker_id>/delete', methods=['POST'])
@admin_required
def admin_sticker_delete(sticker_id):
    sticker = Sticker.query.get_or_404(sticker_id)
    if sticker.sticker_type == 'image':
        path = os.path.join(STICKER_FOLDER, sticker.value)
        if os.path.exists(path):
            os.remove(path)
    db.session.delete(sticker)
    db.session.commit()
    flash('Sticker eliminado.', 'success')
    return redirect(url_for('admin_stickers'))


# ---------------------------------------------------------------------------
# CLI + arranque
# ---------------------------------------------------------------------------

def _seed_stickers():
    if Sticker.query.count() == 0:
        for i, s in enumerate(DEFAULT_STICKERS):
            db.session.add(Sticker(name=s['name'], sticker_type=s['type'],
                                   value=s['value'], sort_order=i))
        db.session.commit()
        print('Stickers por defecto creados.')


@app.cli.command('init-db')
def init_db_command():
    db.create_all()
    if not Admin.query.filter_by(username=config.ADMIN_DEFAULT_USER).first():
        db.session.add(Admin(
            username=config.ADMIN_DEFAULT_USER,
            password_hash=generate_password_hash(config.ADMIN_DEFAULT_PASSWORD),
        ))
        db.session.commit()
        print(f"Admin '{config.ADMIN_DEFAULT_USER}' creado.")
    _seed_stickers()


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Admin.query.filter_by(username=config.ADMIN_DEFAULT_USER).first():
            db.session.add(Admin(
                username=config.ADMIN_DEFAULT_USER,
                password_hash=generate_password_hash(config.ADMIN_DEFAULT_PASSWORD),
            ))
            db.session.commit()
        _seed_stickers()
    app.run(debug=True, port=5002)
