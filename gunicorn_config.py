import os

# Bind to PORT if defined, otherwise to 5000
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Use eventlet worker for WebSocket support
worker_class = 'eventlet'
workers = 1

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Don't preload app (needed for eventlet)
preload_app = False
