#!/bin/bash --login
PORT=8000
gunicorn --bind 0.0.0.0:$PORT --worker-class eventlet --workers 1 --threads 1 start:app 