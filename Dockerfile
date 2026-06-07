# Stage 1: Build React SPA
FROM node:24-slim AS frontend-builder

WORKDIR /frontend

COPY frontend/package*.json ./

RUN npm ci

COPY frontend/ ./

RUN npm run build

# Stage 2: Serve React SPA with Nginx and run FastAPI
FROM python:3.12-slim

# Install Nginx and build-essential
RUN apt-get update && apt-get install -y --no-install-recommends \
    nginx \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy backend requirements and install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY backend/app ./app

# Copy React compilation output to Nginx HTML root
COPY --from=frontend-builder /frontend/dist /usr/share/nginx/html

# Copy Nginx template and startup shell script
COPY nginx.conf.template /etc/nginx/nginx.conf.template
COPY start.sh .
RUN chmod +x start.sh

EXPOSE 8080

CMD ["./start.sh"]
