#!/bin/sh

# Default to port 8080 if PORT environment variable is not set
export PORT=${PORT:-8080}
echo "Starting application on port $PORT..."

# Replace ${PORT} in the nginx configuration template
sed "s/\${PORT}/$PORT/g" /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

# Start FastAPI backend in the background
echo "Starting FastAPI backend on 127.0.0.1:8000..."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &

# Start Nginx in the foreground
echo "Starting Nginx web server..."
nginx -g "daemon off;"
