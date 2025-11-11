#!/bin/bash
# Railway startup script that handles PORT variable
exec gunicorn -c gunicorn_config.py app:app
