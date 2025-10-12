# 🧠 Audiovook Middleware — Auditoria Tècnica

## 🎯 Objectiu
Aquest document ofereix una visió tècnica del **middleware Audiovook**, el sistema intermediari que connecta els usuaris, les targetes físiques (QR) i el reproductor Audiobookshelf.  
El projecte s'ha analitzat a partir de l'estructura actual del repositori (`DEV-local-working-senseABS.zip`).

---

## 🧱 Arquitectura General

```
[Usuari / App / Web]
        │
        ▼
[ API Audiovook Middleware ]
        │
        ├── Autenticació JWT
        ├── Control de targetes (claim / lend / play)
        ├── Gestió de préstecs
        ├── Generació d’URL temporal signada
        ▼
[ Audiobookshelf Backend ]
        │
        └── Stream d’àudio segur
```

---

## 📂 Estructura principal

| Directori / Fitxer | Descripció | Estat |
|--------------------|-------------|--------|
| `app/` | Arrel de l’aplicació FastAPI | ✔️ |
| `app/models/` | Models SQLModel per a `user`, `abook`, `claim`, `play_session`, etc. | ✔️ |
| `app/routers/` | Rutes d’API: registre, login, claim, lend, play-auth, etc. | ⚙️ |
| `app/schemas/` | Schemes Pydantic per validació d’entrades/sortides | ✔️ |
| `app/core/` | Configuració bàsica: JWT, seguretat, dependències | ⚙️ |
| `db.py` | Connexió PostgreSQL + dependències SQLAlchemy | ✔️ |
| `main.py` | Punt d’entrada FastAPI amb inclusió de routers | ✔️ |
| `tests/` | Tests parcials d’endpoints | ⚙️ |
| `Dockerfile`, `docker-compose.yml` | Contenidors de backend, db i ABS | ✔️ |
| `docs/` | Fitxers complementaris i esquema de flux | ✔️ |
| `audiobookshelf/` | Exclòs del ZIP (fora d’aquesta auditoria) | — |

---

## 📊 Estat funcional (resum)

| Component | Funcionalitat | Estat |
|------------|----------------|--------|
| Base de dades (PostgreSQL) | Esquema complet (`users`, `abooks`, `listening_progress`, etc.) | ✔️ |
| Autenticació JWT (bcrypt + tokens) | Login i protecció de rutes | ✔️ |
| Endpoint `/register` | Alta d’usuaris | ✔️ |
| Endpoint `/login` | Retorna JWT vàlid | ✔️ |
| Endpoint `/abook/:qr/claim` | Reclama una targeta | ✔️ |
| Endpoint `/abook/:qr/lend` | Cedeix un llibre temporalment | ⚙️ (necessita validació extra) |
| Endpoint `/abook/:qr/stop-lend` | Finalitza préstec | ⚙️ |
| Endpoint `/abook/:qr/play-auth` | Genera URL signada per a streaming | ⚙️ |
| Endpoint `/abook/:qr/progress` | Desa i consulta posició d’escolta | ✔️ |
| Integració Audiobookshelf | Via NGINX i signed URLs | ⏳ pendent |
| Logs / monitoratge | Implementació bàsica | ⚙️ |
| Tests automatitzats | Existents però incomplets | ⚙️ |

---

## 🧩 Flux d’interacció (simplificat)

```
Usuari escaneja QR
        │
        ▼
API Audiovook:
   - Valida JWT
   - Comprova propietari / préstec
   - Retorna signed URL temporal
        │
        ▼
NGINX Reverse Proxy
   - Valida token
   - Redirigeix a Audiobookshelf
        │
        ▼
Audiobookshelf
   - Serveix stream d’àudio
```

---

## 🔐 Seguretat

- Tots els endpoints protegits amb JWT (Bearer token)
- Hash de contrasenyes amb bcrypt
- URLs signades amb caducitat
- Cap accés directe a Audiobookshelf sense validació prèvia

---

## 🧾 Recomanacions següents

1. Completar lògica de **lend/stop-lend** amb validacions addicionals.
2. Implementar capa **NGINX reverse proxy** amb verificació de token signat.
3. Afegir **tests unitaris i integració** (pytest + coverage).
4. Definir **mecanismes d’error i logs** centralitzats.
5. Preparar **documentació OpenAPI (Swagger)** neta.
6. Afegir un mòdul d’**administració bàsic** (estadístiques, control de préstecs).

---

## 📋 Fitxers associats

- `CHECKLIST_middleware.md` → Seguiment detallat de fases i tasques.
- `roadmap_middleware.md` → Roadmap estratègic complet.
- `July25-Dev-plan.txt` → Disseny de base de dades i endpoints.
