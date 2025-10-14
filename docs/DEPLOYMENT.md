# Deployment Guide

This document describes how to run the Audiovook middleware stack locally using Docker Compose.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose v2
- A `.env` file at the project root with the environment variables expected by the middleware

## Services

`docker-compose.yml` defines the following containers:

| Service | Purpose |
|---------|---------|
| `db` | PostgreSQL 16 database used by the middleware |
| `middleware` | FastAPI application that powers the Audiovook API |
| `audiobookshelf` | Upstream Audiobookshelf instance that serves audio streams |
| `nginx` | Reverse proxy that validates signed playback URLs before streaming |
| `jekyll` | Static site for the public catalogue and admin dashboard |

The new **NGINX** service exposes port `8080` and validates playback requests via the middleware's `/api/v1/proxy/validate` endpoint before forwarding traffic to Audiobookshelf. The stock configuration lives in [`nginx/conf.d/middleware.conf`](../nginx/conf.d/middleware.conf) and can be customised for production deployments.

## Running the stack

```bash
docker compose up --build
```

Once running:

- API: http://localhost:8000
- Proxy + Audiobookshelf stream entrypoint: http://localhost:8080
- Audiobookshelf UI: http://localhost:13378
- Jekyll site: http://localhost:4000

## Customising CORS for clients

Set `CORS_ALLOW_ORIGINS` in the `.env` file to a comma-separated list of origins that should be allowed to call the middleware API (for example, progressive web apps served from HTTPS domains).

```env
CORS_ALLOW_ORIGINS=https://app.audiovook.cat,https://pwa.audiovook.cat
```

Restart the middleware container after changing the environment variable so the new values are applied.
