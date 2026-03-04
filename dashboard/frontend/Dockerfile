# PR-Agent Dashboard Frontend - build-time env for API/WS URLs
# Build from repo root, e.g.:
#   docker build -f dashboard/frontend/Dockerfile \
#     --build-arg REACT_APP_API_URL=https://api.example.com \
#     --build-arg REACT_APP_WS_URL=wss://api.example.com/ws \
#     -t pr-agent-dashboard-frontend .
# For local backend: --build-arg REACT_APP_API_URL=http://localhost:8000

FROM node:20-alpine AS builder

WORKDIR /app

# Build args - inject at build time (required for Create React App)
ARG REACT_APP_API_URL=http://localhost:8000
ARG REACT_APP_WS_URL=
ENV REACT_APP_API_URL=$REACT_APP_API_URL
# If REACT_APP_WS_URL not set, frontend will derive from REACT_APP_API_URL (http -> ws)
ENV REACT_APP_WS_URL=$REACT_APP_WS_URL

COPY dashboard/frontend/package*.json ./
RUN npm ci --only=production=false

COPY dashboard/frontend/ ./
RUN npm run build

# Production: serve static files with nginx
FROM nginx:alpine

COPY --from=builder /app/build /usr/share/nginx/html
# SPA fallback and optional security headers
RUN echo 'server { \
  listen 80; \
  root /usr/share/nginx/html; \
  index index.html; \
  location / { try_files $uri $uri/ /index.html; } \
  location /health { return 200 "ok"; add_header Content-Type text/plain; } \
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
