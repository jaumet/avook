# 🧠 Audiovook Middleware

Audiovook Middleware is a FastAPI application that brokers access between physical audiobook cards, mobile/PWA clients, and an Audiobookshelf instance. It centralises authentication, lending, promo campaigns, QR tracking, and monitoring for the Audiovook platform.

## ✨ Key capabilities

- **User access & lending** — Claim QR cards, lend titles, and enforce one-device playback with automatic expiry.
- **Secure playback** — Generate signed URLs and validate them through an NGINX auth proxy before handing off to Audiobookshelf.
- **Caching & backups** — Redis-backed metadata cache and an automated JSON backup scheduler for redundancy.
- **Monitoring & localisation** — Structured logs, request telemetry, and translated status messaging (CA/ES/EN).
- **Admin tooling** — Dashboard metrics, promo code management, and QR tracking utilities for marketing teams.

## 🏗️ Architecture overview

```
[Client / PWA / Mobile]
        │
        ▼
[ Audiovook Middleware API ]
        │
        ├── Authentication & lending workflows
        ├── Promo codes and QR tracking
        ├── Proxy validator for signed playback URLs
        ▼
[ NGINX Validation Proxy ] ──▶ [ Audiobookshelf ]
```

## 🚀 Getting started

The repository ships with a Docker Compose stack that includes PostgreSQL, the middleware API, Audiobookshelf, the validation proxy, and the public Jekyll site.

```bash
docker compose up --build
```

Services:

| Service | URL | Notes |
|---------|-----|-------|
| Middleware API | http://localhost:8000 | FastAPI app with OpenAPI docs at `/docs` |
| NGINX proxy | http://localhost:8080 | Validates signed playback URLs before streaming |
| Audiobookshelf | http://localhost:13378 | Reference audio backend |
| Jekyll site | http://localhost:4000 | Public site and admin UI |
| PostgreSQL | localhost:5432 | Default database (`avook`/`avookpass`) |

> ℹ️ See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for detailed deployment notes and environment variable guidance.

If your Audiobookshelf server protects the share metadata API, set
`ABS_USERNAME` and `ABS_PASSWORD` in `.env`. The middleware will log in with
those credentials and reuse the issued token for admin imports and proxy checks.

## 🌐 PWA & mobile compatibility

The middleware exposes granular CORS controls to accommodate progressive web apps and native wrappers:

- Common local dev origins (`http://localhost:3000`, `http://localhost:5173`, etc.) are enabled out of the box.
- Define `CORS_ALLOW_ORIGINS` in the `.env` file to whitelist production domains (comma-separated).
- Signed playback URLs include all metadata required by `<audio>` elements and native media players on iOS/Android.

See [`docs/CLIENT_COMPATIBILITY.md`](docs/CLIENT_COMPATIBILITY.md) for a full checklist covering service workers, deep links, and error mapping.

## 🛡️ Proxy validation flow

1. Clients request playback from `/api/v1/abook/{qr}/play-auth` (or `/api/v1/play-auth/{qr}`) providing a `device_id`.
2. The middleware records a `PlaySession` and returns a signed URL pointing at the proxy (`http://localhost:8080/stream/...`).
3. NGINX calls `/api/v1/proxy/validate` via `auth_request` to confirm the signature, device, and Audiobookshelf share availability.
4. Valid requests are proxied to Audiobookshelf; failures return appropriate HTTP status codes without exposing the upstream.

The stock proxy configuration lives at [`nginx/conf.d/middleware.conf`](nginx/conf.d/middleware.conf) and can be adapted for production domains or TLS.

## 🧩 Feature modules

- `app/analytics.py` — Aggregates lending and activation metrics for the admin dashboard.
- `app/audiobookshelf.py` — Lightweight client for Audiobookshelf share validation.
- `app/cache.py` — Redis helpers with namespaced keys for share metadata.
- `app/backup.py` — Asynchronous scheduler that exports JSON backups periodically.
- `app/i18n.py` — Translation loader for CA/ES/EN locales.
- `app/monitoring.py` — Structured logging and request timing middleware.

Tests covering these modules live under `middleware/tests/`.

## ✅ Development checklist

Progress across the middleware roadmap is tracked in [`CHECKLIST_middleware.md`](CHECKLIST_middleware.md). All phase objectives and general tasks are now complete, including the new validation proxy, client compatibility review, and documentation refresh.

## 📚 Documentation

- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — Running the stack and configuring NGINX/CORS.
- [`docs/CLIENT_COMPATIBILITY.md`](docs/CLIENT_COMPATIBILITY.md) — Guidance for PWAs and mobile apps.

Additional background materials such as historical notes and roadmap documents remain available in the repository root.

## 🧪 Testing

Execute the test suite inside the middleware container:

```bash
PYTHONPATH=middleware pytest
```

Some integration tests rely on PostgreSQL and Redis being available; ensure the Docker Compose stack is running when executing them locally.
