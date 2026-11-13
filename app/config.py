import os
from datetime import timedelta
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / '.env')


class Config:
    """Base application configuration."""
    SECRET_KEY = os.getenv('SECRET_KEY')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max upload
    ITEMS_PER_PAGE = 10
    WTF_CSRF_TIME_LIMIT = 3600


class DevelopmentConfig(Config):
    """Development environment configuration."""
    DEBUG = True
    SECRET_KEY = os.getenv('SECRET_KEY', 'lifebridge-dev-secret-key-cse601330')
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        f"sqlite:///{BASE_DIR / 'instance' / 'lifebridge.db'}"
    )


class TestingConfig(Config):
    """Testing environment configuration."""
    TESTING = True
    DEBUG = True
    SECRET_KEY = 'test-secret-key'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False


class ProductionConfig(Config):
    """Production environment configuration."""
    DEBUG = False
    SESSION_COOKIE_SECURE = True

    @property
    def SQLALCHEMY_DATABASE_URI(self):
        uri = os.getenv('DATABASE_URL')
        if not uri:
            raise RuntimeError("DATABASE_URL must be set in production environment.")
        return uri

    def __init__(self):
        super().__init__()
        if not os.getenv('SECRET_KEY'):
            raise RuntimeError("SECRET_KEY environment variable must be set in production mode.")


def get_config(config_name=None):
    if not config_name:
        config_name = os.getenv('FLASK_ENV', 'development')
    if config_name == 'production':
        return ProductionConfig()
    return config_by_name.get(config_name, DevelopmentConfig)


config_by_name = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
