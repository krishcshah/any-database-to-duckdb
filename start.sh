#!/bin/sh

# Default to port 8080 if PORT environment variable is not set
export PORT=${PORT:-8080}
echo "Starting application on port $PORT..."

# Replace ${PORT} in the nginx configuration template
sed "s/\${PORT}/$PORT/g" /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf

# Start FastAPI backend in the background
echo "Starting FastAPI backend on 127.0.0.1:8000..."
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!

# Start Nginx in the background
echo "Starting Nginx web server..."
nginx -g "daemon off;" &
NGINX_PID=$!

# Monitor processes to enable container self-healing
while true; do
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo "[FATAL] FastAPI backend (uvicorn) exited. Exiting container."
        exit 1
    fi
    if ! kill -0 $NGINX_PID 2>/dev/null; then
        echo "[FATAL] Nginx web server exited. Exiting container."
        exit 1
    fi
    sleep 2
done
