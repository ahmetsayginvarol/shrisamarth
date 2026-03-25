import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-me'

    # Database — defaults to SQLite in instance folder if not set
    SQLALCHEMY_DATABASE_URI = (
        os.environ.get('DATABASE_URL')
        or 'sqlite:///' + os.path.join(basedir, 'instance', 'shrisamarth.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Babel (i18n)
    LANGUAGES = ['en', 'hi']
    BABEL_DEFAULT_LOCALE = 'en'

    # Session
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8  # 8 hours