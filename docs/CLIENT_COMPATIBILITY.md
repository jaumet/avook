# Client Compatibility Guide

This guide summarises the considerations when integrating mobile apps or progressive web apps with the Audiovook middleware.

## Supported authentication flow

1. Users authenticate via the `/api/v1/login` endpoint to obtain a JWT access token.
2. The client stores the token securely (Keychain, Keystore, or IndexedDB).
3. All subsequent API calls include the `Authorization: Bearer <token>` header.
4. Playback URLs are obtained through `/api/v1/abook/{qr}/play-auth` or `/api/v1/play-auth/{qr}`.

The JWT lifetime and refresh behaviour remain unchanged from previous iterations, so existing applications continue to work.

## CORS configuration

The middleware now supports dynamic CORS configuration through the `CORS_ALLOW_ORIGINS` environment variable. Add each production or staging origin (for example, `https://app.audiovook.cat`) to permit browser-based PWAs to access the API. Local development origins commonly used by Vite (`http://localhost:5173`) and Create React App (`http://localhost:3000`) are allowed by default.

## Service worker and offline support

- The API sets `Allow` headers for all HTTP verbs, allowing service workers to pre-cache or replay requests when offline.
- Streaming URLs returned by the middleware include signed query parameters that are compatible with `<audio>` and media session APIs on iOS and Android.
- When integrating with background audio playback, ensure the PWA or native wrapper preserves the query string parameters when delegating to the system media player.

## Deep links and QR codes

- Promo codes and QR tracking endpoints now emit unique identifiers that can be deep-linked from mobile apps.
- The `/api/v1/qr/visit` endpoint accepts both touch and camera-based scans; mobile clients should forward the `device_id` to maintain exclusive playback enforcement.

## Error handling

- All validation failures return structured JSON with `detail` and, when applicable, translation keys.
- Mobile clients should map known error codes (`TOKEN_EXPIRED`, `DEVICE_MISMATCH`, etc.) to user-friendly strings using the `/api/v1/i18n/{locale}` namespace.

Refer to [`docs/DEPLOYMENT.md`](./DEPLOYMENT.md) for details on running the reference environment used during compatibility testing.
