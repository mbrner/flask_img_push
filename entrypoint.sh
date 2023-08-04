#!/bin/bash --login

source /venv/bin/activate

gunicorn --bind 0.0.0.0:8000 --worker-class eventlet --workers 1 --threads 1 start:app 