import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import app
from app.extensions import db
import sqlalchemy.orm

a = app.create_app('testing')
with a.app_context():
    try:
        sqlalchemy.orm.configure_mappers()
        print("SUCCESS! All mappers configured properly.")
    except Exception as e:
        print("ERROR:", type(e), e)
