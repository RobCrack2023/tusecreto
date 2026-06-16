from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Story(db.Model):
    __tablename__ = 'stories'

    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255), nullable=True)
    vote_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_hidden = db.Column(db.Boolean, default=False, nullable=False)
    is_edited = db.Column(db.Boolean, default=False, nullable=False)
    edit_note = db.Column(db.Text, nullable=True)
    avatar = db.Column(db.String(10), nullable=True, default='🐱')
    age_range = db.Column(db.String(20), nullable=True)
    country_code = db.Column(db.String(3), nullable=True)
    country_name = db.Column(db.String(80), nullable=True)

    reactions = db.relationship('Reaction', backref='story', lazy='dynamic',
                                cascade='all, delete-orphan')
    replies = db.relationship('Reply', backref='story', lazy='dynamic',
                              cascade='all, delete-orphan')

    def time_ago(self):
        now = datetime.utcnow()
        diff = now - self.created_at
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return 'hace un momento'
        minutes = seconds // 60
        if minutes < 60:
            return f'hace {minutes} min'
        hours = minutes // 60
        if hours < 24:
            return f'hace {hours}h'
        days = hours // 24
        if days < 30:
            return f'hace {days}d'
        return self.created_at.strftime('%d/%m/%Y')

    def trending_score(self):
        import math
        n = self.vote_count
        if n == 0:
            return 0
        age_hours = max(1, (datetime.utcnow() - self.created_at).total_seconds() / 3600)
        return n / (age_hours ** 1.5)


class Sticker(db.Model):
    __tablename__ = 'stickers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    sticker_type = db.Column(db.String(10), default='emoji')  # 'emoji' | 'image'
    value = db.Column(db.String(255), nullable=False)          # emoji char or filename
    sort_order = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    reactions = db.relationship('Reaction', backref='sticker', lazy='dynamic')


class Reaction(db.Model):
    __tablename__ = 'reactions'

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('stories.id'), nullable=False)
    sticker_id = db.Column(db.Integer, db.ForeignKey('stickers.id'), nullable=False)
    voter_token = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint('story_id', 'voter_token', name='uq_one_react_per_story'),
    )


class Reply(db.Model):
    __tablename__ = 'replies'

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('stories.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    avatar = db.Column(db.String(10), nullable=True, default='🐱')
    age_range = db.Column(db.String(20), nullable=True)
    country_code = db.Column(db.String(3), nullable=True)
    country_name = db.Column(db.String(80), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    is_hidden = db.Column(db.Boolean, default=False, nullable=False)

    def time_ago(self):
        now = datetime.utcnow()
        diff = now - self.created_at
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return 'hace un momento'
        minutes = seconds // 60
        if minutes < 60:
            return f'hace {minutes} min'
        hours = minutes // 60
        if hours < 24:
            return f'hace {hours}h'
        days = hours // 24
        if days < 30:
            return f'hace {days}d'
        return self.created_at.strftime('%d/%m/%Y')


class Vote(db.Model):
    __tablename__ = 'votes'

    id = db.Column(db.Integer, primary_key=True)
    story_id = db.Column(db.Integer, db.ForeignKey('stories.id'), nullable=False)
    voter_token = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('story_id', 'voter_token', name='uq_vote_per_story'),
    )


class Admin(db.Model):
    __tablename__ = 'admins'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
