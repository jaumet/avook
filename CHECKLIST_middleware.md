# ✅ CHECKLIST — Desenvolupament del Middleware Audiovook

## 🧱 Fase 1 — Fonaments i arquitectura bàsica
- [x] Definir esquema de dades (users, abooks, play_sessions)
- [x] Implementar models SQLModel
- [x] Crear `db.py` i connexió PostgreSQL
- [x] Endpoint `/register`
- [x] Endpoint `/login`
- [x] Sistema JWT + bcrypt
- [x] Inicialitzar FastAPI (`main.py`)
- [ ] Afegir validacions avançades d'entrada (email, contrasenya forta)
- [ ] Documentació Swagger inicial

## 🔁 Fase 2 — Control de préstec i lògica condicional
- [x] Endpoint `/abook/:qr/claim`
- [x] Control d’estats `status 0→1`
- [x] Associació `owner_id`
- [x] Taula `listening_progress`
- [x] Endpoint `/abook/:qr/lend` amb validació completa
- [x] Endpoint `/abook/:qr/stop-lend`
- [x] Control exclusiu d’un dispositiu per llibre
- [x] Expiració automàtica de préstec

## 🎧 Fase 3 — Integració amb reproductor i experiència d’usuari
- [x] Endpoint `/abook/:qr/play-auth` (esborrany funcional)
- [x] Generació d’URL signada segura
- [ ] Integració NGINX proxy validator
- [ ] Connexió real amb Audiobookshelf
- [x] Missatges d’estat personalitzats (“És teu / prestat / no disponible”)

## 🚀 Fase 4 — Escalabilitat, tests i redundància
- [ ] Implementar cache (Redis)
- [ ] Còpies de seguretat automàtiques
- [ ] Tests unitari i integració
- [ ] Monitoratge i logs centralitzats
- [ ] Internacionalització (CA/ES/EN)

## 🏢 Fase 5 — Extensió i personalització per editorials
- [ ] Panell d’administració bàsic
- [ ] Estadístiques de préstec i activacions
- [ ] Codis promocionals / premsa
- [ ] QR personalitzats amb tracking

---

## 🧩 Altres tasques generals
- [x] Docker Compose amb serveis `backend`, `db`
- [ ] Afegir servei `nginx` de validació
- [ ] Revisar compatibilitat amb PWA/app mòbil
- [x] Afegir fitxer `LICENSE` i metadades GPL3
- [ ] Actualitzar documentació `/docs` i `README.md`
