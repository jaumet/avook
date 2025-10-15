from urllib.parse import urlparse, unquote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlmodel import Session, select, delete

from app.models import (
    Title,
    User,
    Card,
    Store,
    Batch,
    PromoCode,
    PromoRedemption,
    CustomQr,
    QrScanEvent,
)
from app.schemas import (
    AdminDashboard,
    TitleImportRequest,
    TitleRead,
    UserCreate,
    UserUpdateAdmin,
    PromoCodeCreate,
    PromoCodeRead,
    PromoCodeDetail,
    PromoRedemptionRead,
    CustomQrCreate,
    CustomQrRead,
    CustomQrDetail,
    QrScanEventRead,
)
from app.db import get_session
from app.auth import get_current_config_superuser
from app.analytics import build_admin_dashboard
from app.audiobookshelf import (
    AudiobookshelfClient,
    AudiobookshelfError,
    AudiobookshelfNotFound,
    AudiobookshelfUnavailable,
)
from uuid import uuid4, UUID
from fastapi.responses import StreamingResponse
import io
import csv
import segno


def get_audiobookshelf_client(request: Request) -> AudiobookshelfClient:
    override = getattr(request.app.state, "abs_client_override", None)
    if override is not None:
        return override
    return AudiobookshelfClient()


def _extract_title_metadata(data: dict) -> dict:
    item = data.get("libraryItem") or {}
    media = item.get("media") or {}
    metadata = media.get("metadata") or {}

    title = metadata.get("title") or item.get("title")
    author = (
        metadata.get("author")
        or metadata.get("authorName")
        or metadata.get("artist")
        or item.get("author")
    )
    language = metadata.get("language") or item.get("language")

    duration_raw = (
        metadata.get("duration")
        or media.get("duration")
        or item.get("duration")
        or metadata.get("audioDuration")
    )
    try:
        duration = int(float(duration_raw)) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration = None

    cover_url = (
        data.get("coverUrl")
        or metadata.get("cover")
        or metadata.get("coverUrl")
        or media.get("cover")
    )

    return {
        "title": title,
        "author": author,
        "language": language,
        "duration_sec": duration,
        "cover_url": cover_url,
    }

router = APIRouter(
    tags=["Admin"],
    dependencies=[Depends(get_current_config_superuser)]
)

@router.get("/")
def admin_root():
    return {"status": "Admin section"}

@router.get("/ping")
def admin_ping():
    return {"ok": True}


@router.get("/dashboard", response_model=AdminDashboard)
def get_dashboard(db: Session = Depends(get_session)):
    """Return aggregated metrics for the administration panel."""

    return build_admin_dashboard(db)

@router.post("/titles", response_model=Title)
def create_title(title: Title, db: Session = Depends(get_session)):
    db.add(title)
    db.commit()
    db.refresh(title)
    return title

@router.get("/titles", response_model=list[TitleRead])
def read_titles(
    search: str = "",
    active: bool = True,
    db: Session = Depends(get_session),
) -> list[TitleRead]:
    query = select(Title)
    if active is not None:
        query = query.where(Title.active == active)
    if search:
        query = query.where(Title.title.contains(search))
    titles = db.exec(query.order_by(Title.title.asc())).all()
    return [TitleRead.model_validate(row, from_attributes=True) for row in titles]


def _normalise_share_code(value: str) -> str:
    raw = unquote(value or "").strip()
    if not raw:
        return ""

    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        candidate = parsed.path
    else:
        candidate = raw

    candidate = candidate.split("?")[0].split("#")[0].rstrip("/")
    if "/" in candidate:
        candidate = candidate.rsplit("/", 1)[-1]
    return candidate.strip()


@router.get("/titles/by-share/{share_code:path}", response_model=TitleRead)
def read_title_by_share(
    share_code: str, db: Session = Depends(get_session)
) -> TitleRead:
    normalised = _normalise_share_code(share_code)
    if not normalised:
        raise HTTPException(status_code=400, detail="INVALID_SHARE_CODE")

    title = db.exec(select(Title).where(Title.abs_share_code == normalised)).first()
    if not title:
        raise HTTPException(status_code=404, detail="TITLE_NOT_FOUND_FOR_SHARE")

    return TitleRead.model_validate(title, from_attributes=True)


@router.post("/titles/import", response_model=TitleRead)
def import_title_from_share(
    payload: TitleImportRequest,
    db: Session = Depends(get_session),
    abs_client: AudiobookshelfClient = Depends(get_audiobookshelf_client),
) -> TitleRead:
    share_code = _normalise_share_code(payload.share)
    if not share_code:
        raise HTTPException(status_code=400, detail="INVALID_SHARE_CODE")

    existing = db.exec(select(Title).where(Title.abs_share_code == share_code)).first()

    try:
        share_data = abs_client.ensure_share_available(share_code)
    except AudiobookshelfNotFound as exc:
        raise HTTPException(status_code=404, detail="ABS_SHARE_NOT_FOUND") from exc
    except AudiobookshelfUnavailable as exc:
        raise HTTPException(status_code=502, detail="ABS_UNAVAILABLE") from exc
    except AudiobookshelfError as exc:
        raise HTTPException(status_code=500, detail="ABS_ERROR") from exc

    metadata = _extract_title_metadata(share_data)

    def _resolve(attr: str, default=None):
        override = getattr(payload, attr, None)
        if override not in (None, ""):
            return override
        value = metadata.get(attr)
        if value not in (None, ""):
            return value
        if existing is not None:
            return getattr(existing, attr)
        return default

    title_values = {
        "title": _resolve("title", default=share_code),
        "author": _resolve("author", default=""),
        "language": _resolve("language", default="und"),
        "duration_sec": _resolve("duration_sec", default=0) or 0,
        "cover_url": _resolve("cover_url"),
        "price_retail": _resolve("price_retail", default=0.0) or 0.0,
        "currency": _resolve("currency", default="EUR"),
        "abs_share_code": share_code,
    }

    if existing:
        for key, value in title_values.items():
            setattr(existing, key, value)
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return TitleRead.model_validate(existing, from_attributes=True)

    new_title = Title(**title_values)
    db.add(new_title)
    db.commit()
    db.refresh(new_title)
    return TitleRead.model_validate(new_title, from_attributes=True)

@router.get("/titles/{title_id}", response_model=Title)
def read_title(title_id: int, db: Session = Depends(get_session)):
    title = db.get(Title, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")
    return title

@router.put("/titles/{title_id}", response_model=Title)
def update_title(title_id: int, title: Title, db: Session = Depends(get_session)):
    db_title = db.get(Title, title_id)
    if not db_title:
        raise HTTPException(status_code=404, detail="Title not found")
    title_data = title.dict(exclude_unset=True)
    for key, value in title_data.items():
        setattr(db_title, key, value)
    db.add(db_title)
    db.commit()
    db.refresh(db_title)
    return db_title

@router.post("/titles/{title_id}/cards/batch", response_model=list[Card])
def create_cards_batch(title_id: int, qty: int, db: Session = Depends(get_session)):
    title = db.get(Title, title_id)
    if not title:
        raise HTTPException(status_code=404, detail="Title not found")

    cards = []
    for _ in range(qty):
        qr = f"QR-{uuid4()}"
        card = Card(qr=qr, title_id=title_id)
        db.add(card)
        cards.append(card)

    db.commit()
    for card in cards:
        db.refresh(card)
    return cards

@router.get("/cards", response_model=list[Card])
def read_cards(title: int = None, store: int = None, user_state: int = None, retail_state: str = None, q: str = None, db: Session = Depends(get_session)):
    query = select(Card)
    if title:
        query = query.where(Card.title_id == title)
    if store:
        query = query.where(Card.store_id == store)
    if user_state:
        query = query.where(Card.user_state == user_state)
    if retail_state:
        query = query.where(Card.retail_state == retail_state)
    if q:
        query = query.where(Card.qr.contains(q))

    cards = db.exec(query).all()
    return cards

@router.put("/cards/{qr}", response_model=Card)
def update_card(qr: str, card: Card, db: Session = Depends(get_session)):
    db_card = db.get(Card, qr)
    if not db_card:
        raise HTTPException(status_code=404, detail="Card not found")

    card_data = card.dict(exclude_unset=True)
    for key, value in card_data.items():
        setattr(db_card, key, value)

    db.add(db_card)
    db.commit()
    db.refresh(db_card)
    return db_card

@router.post("/stores", response_model=Store)
def create_store(store: Store, db: Session = Depends(get_session)):
    db.add(store)
    db.commit()
    db.refresh(store)
    return store

@router.get("/stores", response_model=list[Store])
def read_stores(db: Session = Depends(get_session)):
    stores = db.exec(select(Store)).all()
    return stores

@router.get("/stores/{store_id}", response_model=Store)
def read_store(store_id: int, db: Session = Depends(get_session)):
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    return store

@router.put("/stores/{store_id}", response_model=Store)
def update_store(store_id: int, store: Store, db: Session = Depends(get_session)):
    db_store = db.get(Store, store_id)
    if not db_store:
        raise HTTPException(status_code=404, detail="Store not found")

    store_data = store.dict(exclude_unset=True)
    for key, value in store_data.items():
        setattr(db_store, key, value)

    db.add(db_store)
    db.commit()
    db.refresh(db_store)
    return db_store

@router.delete("/stores/{store_id}")
def delete_store(store_id: int, db: Session = Depends(get_session)):
    store = db.get(Store, store_id)
    if not store:
        raise HTTPException(status_code=404, detail="Store not found")
    db.delete(store)
    db.commit()
    return {"ok": True}


def _normalise_code(value: str) -> str:
    return value.strip().upper()


@router.post("/promo-codes", response_model=PromoCodeRead)
def create_promo_code(
    payload: PromoCodeCreate, db: Session = Depends(get_session)
) -> PromoCodeRead:
    code = _normalise_code(payload.code)
    if db.get(PromoCode, code):
        raise HTTPException(status_code=400, detail="PROMO_CODE_EXISTS")

    promo = PromoCode(
        code=code,
        title_id=payload.title_id,
        label=payload.label,
        kind=payload.kind,
        campaign=payload.campaign,
        notes=payload.notes,
        max_uses=payload.max_uses,
        expires_at=payload.expires_at,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    remaining = (
        max(promo.max_uses - promo.usage_count, 0)
        if promo.max_uses is not None
        else None
    )
    promo_read = PromoCodeRead.model_validate(promo, from_attributes=True)
    promo_read.remaining_uses = remaining
    return promo_read


@router.get("/promo-codes", response_model=list[PromoCodeRead])
def list_promo_codes(db: Session = Depends(get_session)) -> list[PromoCodeRead]:
    promos = (
        db.exec(select(PromoCode).order_by(PromoCode.created_at.desc())).all()
    )
    results: list[PromoCodeRead] = []
    for promo in promos:
        remaining = (
            max(promo.max_uses - promo.usage_count, 0)
            if promo.max_uses is not None
            else None
        )
        promo_read = PromoCodeRead.model_validate(promo, from_attributes=True)
        promo_read.remaining_uses = remaining
        results.append(promo_read)
    return results


@router.get("/promo-codes/{code}", response_model=PromoCodeDetail)
def get_promo_code(code: str, db: Session = Depends(get_session)) -> PromoCodeDetail:
    promo = db.get(PromoCode, _normalise_code(code))
    if not promo:
        raise HTTPException(status_code=404, detail="PROMO_CODE_NOT_FOUND")

    redemptions = (
        db.exec(
            select(PromoRedemption)
            .where(PromoRedemption.promo_code_code == promo.code)
            .order_by(PromoRedemption.redeemed_at.desc())
        ).all()
    )
    remaining = (
        max(promo.max_uses - promo.usage_count, 0)
        if promo.max_uses is not None
        else None
    )
    promo_read = PromoCodeRead.model_validate(promo, from_attributes=True)
    promo_read.remaining_uses = remaining
    redemption_reads = [
        PromoRedemptionRead.model_validate(r, from_attributes=True)
        for r in redemptions
    ]
    return PromoCodeDetail(
        **promo_read.model_dump(),
        redemptions=redemption_reads,
    )


@router.post("/qr/custom", response_model=CustomQrRead)
def create_custom_qr(
    payload: CustomQrCreate, db: Session = Depends(get_session)
) -> CustomQrRead:
    slug = payload.slug.strip().lower()
    if db.get(CustomQr, slug):
        raise HTTPException(status_code=400, detail="CUSTOM_QR_EXISTS")

    record = CustomQr(
        slug=slug,
        target_url=payload.target_url,
        title_id=payload.title_id,
        label=payload.label,
        campaign=payload.campaign,
        notes=payload.notes,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return CustomQrRead.model_validate(record, from_attributes=True)


@router.get("/qr/custom", response_model=list[CustomQrRead])
def list_custom_qr(db: Session = Depends(get_session)) -> list[CustomQrRead]:
    records = (
        db.exec(select(CustomQr).order_by(CustomQr.created_at.desc())).all()
    )
    return [CustomQrRead.model_validate(row, from_attributes=True) for row in records]


@router.get("/qr/custom/{slug}", response_model=CustomQrDetail)
def get_custom_qr(slug: str, db: Session = Depends(get_session)) -> CustomQrDetail:
    record = db.get(CustomQr, slug.strip().lower())
    if not record:
        raise HTTPException(status_code=404, detail="CUSTOM_QR_NOT_FOUND")

    events = (
        db.exec(
            select(QrScanEvent)
            .where(QrScanEvent.slug == record.slug)
            .order_by(QrScanEvent.scanned_at.desc())
            .limit(100)
        ).all()
    )
    base = CustomQrRead.model_validate(record, from_attributes=True)
    event_reads = [
        QrScanEventRead.model_validate(event, from_attributes=True)
        for event in events
    ]
    return CustomQrDetail(
        **base.model_dump(),
        events=event_reads,
    )


@router.get("/qr/custom/{slug}/svg")
def download_custom_qr_svg(slug: str, db: Session = Depends(get_session)) -> Response:
    slug_normalised = slug.strip().lower()
    record = db.get(CustomQr, slug_normalised)
    if not record:
        raise HTTPException(status_code=404, detail="CUSTOM_QR_NOT_FOUND")

    qr = segno.make(record.target_url, error="h")
    buffer = io.BytesIO()
    qr.save(buffer, kind="svg", xmldecl=False)
    buffer.seek(0)
    return Response(content=buffer.read(), media_type="image/svg+xml")


@router.delete("/qr/custom/{slug}", status_code=204)
def delete_custom_qr(slug: str, db: Session = Depends(get_session)) -> Response:
    slug_normalised = slug.strip().lower()
    record = db.get(CustomQr, slug_normalised)
    if not record:
        raise HTTPException(status_code=404, detail="CUSTOM_QR_NOT_FOUND")

    db.exec(delete(QrScanEvent).where(QrScanEvent.slug == record.slug))
    db.delete(record)
    db.commit()
    return Response(status_code=204)

@router.get("/batches", response_model=list[Batch])
def read_batches(db: Session = Depends(get_session)):
    batches = db.exec(select(Batch)).all()
    return batches

@router.get("/users", response_model=list[User])
def read_users(db: Session = Depends(get_session)):
    users = db.exec(select(User)).all()
    return users

@router.get("/users/{user_id}", response_model=User)
def read_user(user_id: UUID, db: Session = Depends(get_session)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.put("/users/{user_id}", response_model=User)
def update_user(user_id: UUID, user_update: UserUpdateAdmin, db: Session = Depends(get_session)):
    db_user = db.get(User, user_id)
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")

    update_data = user_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.put("/users/{user_id}/make-admin", response_model=User)
def make_admin(user_id, db: Session = Depends(get_session)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_admin = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.get("/titles/{title_id}/cards/export.csv")
def export_cards_csv(title_id: int, batch: int = None, db: Session = Depends(get_session)):
    query = select(Card).where(Card.title_id == title_id)
    if batch:
        query = query.where(Card.batch_id == batch)

    cards = db.exec(query).all()

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow(["qr", "title", "abs_share_code", "store", "retail_state", "notes"])

    for card in cards:
        title = db.get(Title, card.title_id)
        store = db.get(Store, card.store_id) if card.store_id else None
        writer.writerow([
            card.qr,
            title.title if title else "",
            title.abs_share_code if title else "",
            store.name if store else "",
            card.retail_state,
            card.notes
        ])

    output.seek(0)
    return StreamingResponse(output, media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=cards_export_{title_id}.csv"})
def get_audiobookshelf_client() -> AudiobookshelfClient:
    return AudiobookshelfClient()


def _extract_title_metadata(data: dict) -> dict:
    item = data.get("libraryItem") or {}
    media = item.get("media") or {}
    metadata = media.get("metadata") or {}

    title = metadata.get("title") or item.get("title")
    author = (
        metadata.get("author")
        or metadata.get("authorName")
        or metadata.get("artist")
        or item.get("author")
    )
    language = metadata.get("language") or item.get("language")

    duration_raw = (
        metadata.get("duration")
        or media.get("duration")
        or item.get("duration")
        or metadata.get("audioDuration")
    )
    try:
        duration = int(float(duration_raw)) if duration_raw is not None else None
    except (TypeError, ValueError):
        duration = None

    cover_url = (
        data.get("coverUrl")
        or metadata.get("cover")
        or metadata.get("coverUrl")
        or media.get("cover")
    )

    return {
        "title": title,
        "author": author,
        "language": language,
        "duration_sec": duration,
        "cover_url": cover_url,
    }

