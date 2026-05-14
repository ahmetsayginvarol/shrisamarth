import os
from dotenv import load_dotenv

load_dotenv()

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-key-change-me'

    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)

    SQLALCHEMY_DATABASE_URI = (
        database_url
        or 'sqlite:///' + os.path.join(basedir, 'instance', 'shrisamarth.db')
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    LANGUAGES = ['en', 'hi']
    BABEL_DEFAULT_LOCALE = 'en'
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8