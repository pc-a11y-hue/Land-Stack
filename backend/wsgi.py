"""Production entry point:  gunicorn wsgi:application --workers 1 --threads 8

IMPORTANT: keep --workers 1. The app holds its working data in memory and uses a single-writer SQLite file, so
several worker processes would each see different state. Scale with threads, not workers (see Technical Document §11).
"""
from app import create_app

application = create_app()
