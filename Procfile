release: python migration_add_columns.py
web: gunicorn -w 4 -b 0.0.0.0:$PORT app:app
