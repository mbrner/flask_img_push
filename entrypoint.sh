#!/bin/bash --login
gunicorn --bind $HOSTNAME:$PORT --worker-class eventlet --workers 1 --threads 1 start:app 