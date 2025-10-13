from fastapi import APIRouter, Depends, HTTPException, Body, Query, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select, delete
from datetime import datetime, timedelta, timezone
import hmac, hashlib, base64, os
from uuid import uuid4, UUID
from pydantic import BaseModel
from app.models import ListeningProgress, PlaySession, User, Card, Title
from app.auth import create_access_token, get_current_user, verify_password, get_password_hash
from app.db import get_session, get_user_by_email, hash_password
from app.schemas import (
    PlayAuthResponse,
    ProxyValidationResponse,
    UserCreate,
    User as UserSchema,
    Token,
    UserUpdate,
)
from app.audiobookshelf import (
    AudiobookshelfClient,
    AudiobookshelfError,
    AudiobookshelfNotFound,
    AudiobookshelfUnavailable,
)
from app.i18n import get_catalog, resolve_language, translate_status


router = APIRouter()

ABS_HOST = os.getenv("ABS_HOST", "localhost:13378")
TTL_HOURS = int(os.getenv("URL_TTL_HOURS", 4))
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")


def _get_abs_client() -> AudiobookshelfClient:
    """Dependency factory returning the Audiobookshelf client."""

    return AudiobookshelfClient()


def _compute_signature(qr: str, user_id: str, device_id: str, expiry_ts: int) -> str:
    """Return the HMAC signature used to protect playback URLs."""

    message = f"{qr}:{user_id}:{device_id}:{expiry_ts}".encode()
    secret = SECRET_KEY.encode()
    digest = hmac.new(secret, message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _normalise_host(host: str) -> str:
    if host.startswith("http://") or host.startswith("https://"):
        return host
    return f"http://{host}"


def _generate_signed_url(qr: str, user_id: str, device_id: str, expiry_ts: int) -> str:
    """Generate a signed playback URL for Audiobookshelf.

    The signature is an HMAC‐SHA256 digest over the QR code, the user id,
    the device identifier and an expiry timestamp.  The resulting digest is
    base64url encoded without padding.  The URL includes the QR, the user id
    (``uid``), the device id (``did``) and the expiry (``exp``) as query
    parameters along with the signature.

    Args:
        qr: the QR identifier for the book being requested.
        user_id: the UUID of the authenticated user as a string.
        device_id: identifier of the playback device requesting access.
        expiry_ts: UTC timestamp (seconds) when the token should expire.

    Returns:
        A fully qualified URL pointing at the Audiobookshelf host with
        signed query parameters.
    """
    # Construct the message to sign.  Including the QR and user id binds the
    # signature to both the resource and the requester.
    signature = _compute_signature(qr, user_id, device_id, expiry_ts)

    # Build the URL.  We default to HTTP if no scheme is present.  A real
    # deployment should use HTTPS.
    host = _normalise_host(ABS_HOST)
    return (
        f"{host}/stream/{qr}?uid={user_id}&did={device_id}&exp={expiry_ts}&sig={signature}"
    )

@router.get("/ping")
def ping():
    return {"pong": True}

@router.post("/login", response_model=Token)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_session),
):
    user = get_user_by_email(form_data.username, db)
    print("🧪 login intent:", user)
    if not user or not verify_password(form_data.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Credencials incorrectes")
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}

@router.post("/register", response_model=UserSchema)
def register(user: UserCreate, db: Session = Depends(get_session)):
    existing = db.exec(select(User).where(User.email == user.email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ja existeix un usuari amb aquest correu")

    user_db = User(
        id=uuid4(),
        email=user.email,
        password_hash=hash_password(user.password),
        name=user.name,
        location=user.location
    )
    db.add(user_db)
    db.commit()
    db.refresh(user_db)
    return user_db

@router.get("/users/me", response_model=UserSchema)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

@router.put("/users/me", response_model=UserSchema)
def update_user_me(
    user_update: UserUpdate,
    db: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    if user_update.password:
        if user_update.password != user_update.password_confirm:
            raise HTTPException(status_code=400, detail="Les contrasenyes no coincideixen")
        current_user.password_hash = hash_password(user_update.password)

    if user_update.name:
        current_user.name = user_update.name

    if user_update.location:
        current_user.location = user_update.location

    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return current_user

def _get_lend_ttl() -> timedelta:
    """Return the configured lending TTL as a ``timedelta``.

    The value can be overridden at runtime through the ``LEND_TTL_HOURS``
    environment variable which makes testing easier without requiring the
    application to be reloaded.
    """

    hours = int(os.getenv("LEND_TTL_HOURS", 24 * 14))
    return timedelta(hours=hours)


def _enforce_lend_expiry(card: Card, db: Session) -> None:
    """Automatically expire loans whose TTL has elapsed.

    When a card has been lent for longer than the configured TTL the loan is
    cleared so the owner regains control.  Any lingering playback sessions for
    the QR are also removed to guarantee that a new device can start playback
    immediately after the expiry is detected.
    """

    if card.user_state != 2 or not card.lent_at:
        return

    now_utc = datetime.now(timezone.utc)
    lend_ttl = _get_lend_ttl()
    if card.lent_at + lend_ttl > now_utc:
        return

    card.borrower_user_id = None
    card.lent_at = None
    card.user_state = 1
    card.updated_at = datetime.utcnow()
    db.add(card)
    db.exec(delete(PlaySession).where(PlaySession.qr == card.qr))
    db.commit()
    db.refresh(card)


@router.post("/claim/{qr}")
def claim_qr(
    qr: str,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    card = db.get(Card, qr)
    if not card:
        raise HTTPException(status_code=404, detail="QR_NOT_FOUND")
    if card.user_state != 0:
        raise HTTPException(status_code=400, detail="ALREADY_CLAIMED")

    card.owner_user_id = user.id
    card.claimed_at = datetime.now(timezone.utc)
    card.user_state = 1
    db.add(card)
    db.commit()
    db.refresh(card)

    owner = db.get(User, card.owner_user_id)
    return {"qr": card.qr, "status": card.user_state, "owner_email": owner.email}

@router.post("/lend/{qr}")
def lend_book(
    qr: str,
    borrower_email: str = Body(embed=True),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user)
) -> dict:
    card = db.get(Card, qr)
    if not card:
        raise HTTPException(status_code=404, detail="QR_NOT_FOUND")
    _enforce_lend_expiry(card, db)
    if card.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="NOT_OWNER")
    if card.user_state != 1:
        raise HTTPException(status_code=400, detail="ALREADY_LENT")

    borrower = get_user_by_email(borrower_email, db)
    if not borrower or borrower.id == user.id:
        raise HTTPException(status_code=400, detail="INVALID_BORROWER")

    card.borrower_user_id = borrower.id
    card.lent_at = datetime.now(timezone.utc)
    card.user_state = 2

    db.add(card)
    db.commit()
    db.refresh(card)
    return {"ok": True, "msg": "Lent successfully"}

@router.get("/abook/{qr}/play-auth", response_model=PlayAuthResponse)
def get_play_auth(
    qr: str,
    device_id: str = Query(..., min_length=1),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    abs_client: AudiobookshelfClient = Depends(_get_abs_client)
) -> PlayAuthResponse:
    card = db.get(Card, qr)
    if not card:
        raise HTTPException(status_code=404, detail="QR_NOT_FOUND")

    _enforce_lend_expiry(card, db)

    can_play = user.id == card.owner_user_id or user.id == card.borrower_user_id
    if not can_play:
        raise HTTPException(status_code=403, detail="NOT_ALLOWED_TO_PLAY")

    # Check for active play sessions
    now_utc = datetime.now(timezone.utc)
    db.exec(delete(PlaySession).where(PlaySession.expires_at <= now_utc))
    db.commit()

    active_session = (
        db.exec(
            select(PlaySession)
            .where(PlaySession.qr == qr, PlaySession.expires_at > now_utc)
            .order_by(PlaySession.expires_at.desc())
        ).first()
    )
    if active_session and active_session.device_id != device_id:
        raise HTTPException(status_code=409, detail="ACTIVE_SESSION_EXISTS")

    title = db.get(Title, card.title_id)
    if not title:
        raise HTTPException(status_code=404, detail="TITLE_NOT_FOUND")

    progress = db.exec(
        select(ListeningProgress)
        .where(ListeningProgress.user_id == user.id, ListeningProgress.qr == qr)
    ).first()
    start_position = progress.position if progress else 0.0

    session_ttl = timedelta(hours=TTL_HOURS)
    expiry = now_utc + session_ttl
    expiry_ts = int(expiry.timestamp())

    try:
        share_info = abs_client.ensure_share_available(title.abs_share_code or "")
    except AudiobookshelfNotFound as exc:
        raise HTTPException(status_code=502, detail="ABS_SHARE_NOT_FOUND") from exc
    except AudiobookshelfUnavailable as exc:
        raise HTTPException(status_code=502, detail="ABS_UNAVAILABLE") from exc
    except AudiobookshelfError as exc:
        raise HTTPException(status_code=502, detail="ABS_CONFIGURATION_ERROR") from exc

    signed_url = _generate_signed_url(qr, str(user.id), device_id, expiry_ts)

    # Create a new play session
    if active_session:
        active_session.device_id = device_id
        active_session.issued_at = now_utc
        active_session.expires_at = expiry
        db.add(active_session)
    else:
        new_session = PlaySession(
            qr=qr,
            device_id=device_id,
            issued_at=now_utc,
            expires_at=expiry,
        )
        db.add(new_session)
    db.commit()

    fallback_redirect = _normalise_host(ABS_HOST)
    if title.abs_share_code:
        fallback_redirect = f"{fallback_redirect}/#/book/{title.abs_share_code}"

    redirect_url = (
        share_info.get("webUrl")
        or share_info.get("shareUrl")
        or fallback_redirect
    )

    return PlayAuthResponse(
        can_play=True,
        reason="owner" if user.id == card.owner_user_id else "borrower",
        start_position=start_position,
        signed_url=signed_url,
        redirect_url=redirect_url,
        expires_in=int(session_ttl.total_seconds()),
        abs_stream_url=share_info.get("streamUrl"),
    )


@router.get("/play-auth/{qr}", response_model=PlayAuthResponse)
def get_play_auth_alias(
    qr: str,
    device_id: str = Query(..., min_length=1),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    abs_client: AudiobookshelfClient = Depends(_get_abs_client),
) -> PlayAuthResponse:
    """Alias for backwards compatibility.

    This route mirrors the behaviour of `/abook/{qr}/play-auth` but lives at
    `/play-auth/{qr}`.  Some existing clients use the shorter path so we
    expose both.
    """
    return get_play_auth(qr=qr, device_id=device_id, db=db, user=user, abs_client=abs_client)


@router.get("/proxy/validate", response_model=ProxyValidationResponse)
def validate_proxy_request(
    qr: str,
    uid: UUID = Query(..., alias="uid"),
    exp: int = Query(..., alias="exp"),
    sig: str = Query(..., alias="sig", min_length=1),
    device_id: str = Query(..., alias="did", min_length=1),
    db: Session = Depends(get_session),
    abs_client: AudiobookshelfClient = Depends(_get_abs_client),
) -> ProxyValidationResponse:
    """Validate signed playback requests coming from the NGINX proxy."""

    now = datetime.now(timezone.utc)
    expiry_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
    if expiry_dt <= now:
        raise HTTPException(status_code=403, detail="TOKEN_EXPIRED")

    expected_sig = _compute_signature(qr, str(uid), device_id, exp)
    if not hmac.compare_digest(expected_sig, sig):
        raise HTTPException(status_code=403, detail="INVALID_SIGNATURE")

    card = db.get(Card, qr)
    if not card:
        raise HTTPException(status_code=404, detail="QR_NOT_FOUND")

    allowed_users = {user_id for user_id in (card.owner_user_id, card.borrower_user_id) if user_id}
    if uid not in allowed_users:
        raise HTTPException(status_code=403, detail="USER_NOT_AUTHORISED")

    session = (
        db.exec(
            select(PlaySession)
            .where(PlaySession.qr == qr, PlaySession.expires_at > now)
            .order_by(PlaySession.expires_at.desc())
        ).first()
    )
    if not session:
        raise HTTPException(status_code=403, detail="SESSION_NOT_FOUND")
    if session.device_id != device_id:
        raise HTTPException(status_code=409, detail="DEVICE_MISMATCH")

    if int(session.expires_at.timestamp()) != exp:
        raise HTTPException(status_code=409, detail="EXPIRY_MISMATCH")

    title = db.get(Title, card.title_id)
    if not title:
        raise HTTPException(status_code=404, detail="TITLE_NOT_FOUND")

    try:
        share_info = abs_client.ensure_share_available(title.abs_share_code or "")
    except AudiobookshelfNotFound as exc:
        raise HTTPException(status_code=502, detail="ABS_SHARE_NOT_FOUND") from exc
    except AudiobookshelfUnavailable as exc:
        raise HTTPException(status_code=502, detail="ABS_UNAVAILABLE") from exc
    except AudiobookshelfError as exc:
        raise HTTPException(status_code=502, detail="ABS_CONFIGURATION_ERROR") from exc

    return ProxyValidationResponse(
        ok=True,
        qr=qr,
        user_id=uid,
        device_id=device_id,
        abs_share_code=title.abs_share_code,
        stream_url=share_info.get("streamUrl"),
        expires_at=exp,
    )

@router.post("/abook/{qr}/stop-lend")
def stop_lend(
    qr: str,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    card = db.get(Card, qr)
    if not card:
        raise HTTPException(status_code=404, detail="QR_NOT_FOUND")
    _enforce_lend_expiry(card, db)
    if card.owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="NOT_OWNER")
    if card.user_state != 2:
        raise HTTPException(status_code=400, detail="Book is not on loan")

    card.borrower_user_id = None
    card.lent_at = None
    card.user_state = 1
    db.add(card)
    db.commit()
    db.refresh(card)
    db.exec(delete(PlaySession).where(PlaySession.qr == card.qr))
    db.commit()
    return {"message": "Lend stopped", "qr": card.qr, "status": card.user_state}

def get_status_label(
    status: int,
    lent_at: datetime | None = None,  # maintained for backwards compatibility
    language: str | None = None,
) -> str:
    """Return the translated label for a claim status.

    ``lent_at`` is accepted for legacy callers but the translation itself is
    delegated to :mod:`app.i18n` so the wording stays consistent across the
    middleware and the front-end.
    """

    return translate_status(status, language)

@router.get("/abook/{qr}/status")
def abook_status(
    qr: str,
    request: Request,
    lang: str | None = Query(None, description="Language override (ca, es, en)"),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    card = db.get(Card, qr)
    if not card:
        raise HTTPException(status_code=404, detail="QR_NOT_FOUND")

    _enforce_lend_expiry(card, db)

    language = resolve_language(lang, request.headers.get("Accept-Language"))

    owner = db.get(User, card.owner_user_id) if card.owner_user_id else None
    borrower = db.get(User, card.borrower_user_id) if card.borrower_user_id else None

    can_claim = card.user_state == 0
    can_lend = user.id == card.owner_user_id and card.user_state == 1
    can_stop_lend = user.id == card.owner_user_id and card.user_state == 2
    can_play = user.id == card.owner_user_id or user.id == card.borrower_user_id

    progress = db.exec(
        select(ListeningProgress)
        .where(ListeningProgress.user_id == user.id, ListeningProgress.qr == qr)
    ).first()
    start_position = progress.position if progress else 0.0

    return {
        "qr": card.qr,
        "status": card.user_state,
        "status_label": get_status_label(card.user_state, language=language),
        "owner_email": owner.email if owner else None,
        "borrower_email": borrower.email if borrower else None,
        "claimed_at": card.claimed_at,
        "lent_at": card.lent_at,
        "can_claim": can_claim,
        "can_lend": can_lend,
        "can_stop_lend": can_stop_lend,
        "can_play": can_play,
        "start_position": start_position,
        "language": language,
    }

class ProgressData(BaseModel):
    position: float

@router.post("/abook/{qr}/progress")
def save_progress(
    qr: str,
    progress: ProgressData,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
) -> dict:
    """Persist the current listening position for a user and audiobook.

    Updates the `ListeningProgress` record if it exists or creates a new
    entry otherwise.  The timestamp is recorded in UTC.

    Args:
        qr: QR code of the audiobook.
        progress: progress data containing the new position.
        user: the authenticated user.
        session: database session.

    Returns:
        Confirmation of the operation.
    """
    lp = session.exec(
        select(ListeningProgress).where(
            (ListeningProgress.qr == qr) & (ListeningProgress.user_id == user.id)
        )
    ).first()

    now_utc = datetime.now(timezone.utc)
    if lp:
        lp.position = progress.position
        lp.updated_at = now_utc
    else:
        lp = ListeningProgress(
            qr=qr,
            user_id=user.id,
            position=progress.position,
            updated_at=now_utc
        )
        session.add(lp)

    session.commit()
    return {"ok": True}


__all__ = ["router"]


@router.get("/translations/{lang}")
def get_translations(
    lang: str,
    namespace: str = Query(
        "errors",
        description="Translation namespace (errors, statuses, all)",
    ),
):
    catalog = get_catalog()
    language = catalog.normalise(lang)
    if namespace == "all":
        payload = {
            "language": language,
            "errors": catalog.section(language, "errors"),
            "statuses": catalog.section(language, "statuses"),
        }
        if not payload["errors"] and not payload["statuses"]:
            raise HTTPException(status_code=404, detail="Translations not found")
        return payload

    if namespace not in {"errors", "statuses"}:
        raise HTTPException(status_code=400, detail="Unsupported namespace")

    section = catalog.section(language, namespace)
    if not section:
        raise HTTPException(status_code=404, detail="Translations not found")
    return section
