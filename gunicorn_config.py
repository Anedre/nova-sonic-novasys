import os

# Bind to PORT if defined, otherwise to 5000
bind = f"0.0.0.0:{os.environ.get('PORT', '5000')}"

# Use eventlet worker for WebSocket support
worker_class = 'eventlet'
# Aumentar workers puede ayudar si hay CPU disponible. Para Flask-SocketIO en
# multi-worker se recomienda configurar un message queue (Redis) para broadcast
# entre procesos. Este proyecto emite por sesión en el mismo proceso, por lo
# que 2 workers suelen ser seguros con conexiones pegajosas del proxy.
workers = int(os.environ.get('WEB_CONCURRENCY', '2'))
worker_connections = int(os.environ.get('WORKER_CONNECTIONS', '1000'))

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Don't preload app (needed for eventlet)
preload_app = False
