import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-insecura')
DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'portal_secreto.db')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
MAX_CONTENT_LENGTH = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'gif', 'webp'}
VOTE_SALT = os.environ.get('VOTE_SALT', 'default-salt')
ADMIN_DEFAULT_USER = os.environ.get('ADMIN_DEFAULT_USER', 'admin')
ADMIN_DEFAULT_PASSWORD = os.environ.get('ADMIN_DEFAULT_PASSWORD', 'secreto123')
STORIES_PER_PAGE = 12
