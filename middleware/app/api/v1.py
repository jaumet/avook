from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from datetime import datetime, timedelta, timezone
import hmac, hashlib, base64, os
from uuid import uuid4
from pydantic import BaseModel
from app.models import ListeningProgress, Claim, PlaySession, User, Card
from app.auth import create_access_token, get_current_user, verify_password, get_password_hash
from app.db import get_session, get_user_by_email, hash_password
from app.schemas import PlayAuthResponse  # ⬅️ assegura’t que aquest import funcioni


router = APIRouter()

ABS_HOST = os.getenv("ABS_HOST", "localhost:13378")
TTL_HOURS = int(os.getenv("URL_TTL_HOURS", 4))
SECRET_KEY = os.getenv("SECRET_KEY", "change-me")


def _generate_signed_url(qr: str, user_id: str) -> str:
    """Generate a signed playback URL for Audiobookshelf.

    The signature is an HMAC‐SHA256 digest over the QR code, the user id and
    an expiry timestamp.  The resulting digest is base64url encoded without
    padding.  The URL includes the QR, the user id (``uid``) and the expiry
    (``exp``) as query parameters along with the signature.

    Args:
        qr: the QR identifier for the book being requested.
        user_id: the UUID of the authenticated user as a string.

    Returns:
        A fully qualified URL pointing at the Audiobookshelf host with
        signed query parameters.
    """
    # Compute an expiry timestamp TTL_HOURS into the future.  We use UTC to
    # avoid timezone issues.  Cast to int to avoid floating point in the URL.
    expiry_dt = datetime.utcnow() + timedelta(hours=TTL_HOURS)
    expiry_ts = int(expiry_dt.timestamp())

    # Construct the message to sign.  Including the QR and user id binds the
    # signature to both the resource and the requester.
    message = f"{qr}:{user_id}:{expiry_ts}".encode()
    secret = SECRET_KEY.encode()

    # Create the HMAC digest and encode using URL‑safe base64 (no padding).
    digest = hmac.new(secret, message, hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).decode().rstrip("=")

    # Build the URL.  We default to HTTP if no scheme is present.  A real
    # deployment should use HTTPS.
    host = ABS_HOST
    if not host.startswith("http://") and not host.startswith("https://"):
        host = f"http://{host}"
    return f"{host}/stream/{qr}?uid={user_id}&exp={expiry_ts}&sig={signature}"

@router.get("/ping")
def ping():
    return {"pong": True}

@router.post("/login")
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

@router.post("/register")
def register(email: str = Body(...), password: str = Body(...), name: str = Body(...), location: str = Body(...), db: Session = Depends(get_session)):
    existing = db.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ja existeix un usuari amb aquest correu")

    user = User(id=uuid4(), email=email, password_hash=hash_password(password), name=name, location=location)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email, "name": user.name, "location": user.location}

@router.get("/users/me")
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

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
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user)
) -> PlayAuthResponse:
    card = db.get(Card, qr)
    if not card:
        raise HTTPException(status_code=404, detail="QR_NOT_FOUND")

    can_play = user.id == card.owner_user_id or user.id == card.borrower_user_id
    if not can_play:
        raise HTTPException(status_code=403, detail="NOT_ALLOWED_TO_PLAY")

    # Check for active play sessions
    active_session = db.exec(select(PlaySession).where(PlaySession.qr == qr, PlaySession.expires_at > datetime.now(timezone.utc))).first()
    if active_session and active_session.device_id != str(user.id): # simple check, can be improved
        raise HTTPException(status_code=409, detail="ACTIVE_SESSION_EXISTS")

    title = db.get(Title, card.title_id)
    if not title:
        raise HTTPException(status_code=404, detail="TITLE_NOT_FOUND")

    progress = db.exec(
        select(ListeningProgress)
        .where(ListeningProgress.user_id == user.id, ListeningProgress.qr == qr)
    ).first()
    start_position = progress.position if progress else 0.0

    signed_url = _generate_signed_url(qr, str(user.id))

    # Create a new play session
    session_ttl = timedelta(hours=TTL_HOURS)
    new_session = PlaySession(
        qr=qr,
        device_id=str(user.id),
        issued_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + session_ttl,
    )
    db.add(new_session)
    db.commit()

    return PlayAuthResponse(
        can_play=True,
        reason="owner" if user.id == card.owner_user_id else "borrower",
        start_position=start_position,
        signed_url=signed_url,
        redirect_url=f"https://{ABS_HOST}/#/book/{title.abs_share_code}?pt={signed_url.split('sig=')[1]}",
        expires_in=int(session_ttl.total_seconds()),
    )


@router.get("/play-auth/{qr}", response_model=PlayAuthResponse)
def get_play_auth_alias(
    qr: str,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user)
) -> PlayAuthResponse:
    """Alias for backwards compatibility.

    This route mirrors the behaviour of `/abook/{qr}/play-auth` but lives at
    `/play-auth/{qr}`.  Some existing clients use the shorter path so we
    expose both.
    """
    return get_play_auth(qr=qr, db=db, user=user)

@router.post("/abook/{qr}/stop-lend")
def stop_lend(
    qr: str,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    card = db.get(Card, qr)
    if not card:
        raise HTTPException(status_code=404, detail="QR_NOT_FOUND")
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
    return {"message": "Lend stopped", "qr": card.qr, "status": card.user_state}

def get_status_label(status: int, lent_at: datetime | None = None) -> str:
    """Return a human‑readable label for a claim status.

    The logic avoids embedding a dynamically computed duration in the label,
    since tests expect the plain text "En préstec" when a book is lent out.
    Additional statuses (3 and 4) are included for future extensions.
    """
    match status:
        case 0:
            return "No reclamat"
        case 1:
            return "Reclamat"
        case 2:
            # Always return a simple label; durations can be computed separately.
            return "En préstec"
        case 3:
            return "Préstec actiu"
        case 4:
            return "Préstec desactivat"
        case _:
            return "Desconegut"

@router.get("/abook/{qr}/status")
def abook_status(
    qr: str,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),
):
    card = db.get(Card, qr)
    if not card:
        raise HTTPException(status_code=404, detail="QR_NOT_FOUND")

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
        "status_label": get_status_label(card.user_state),
        "owner_email": owner.email if owner else None,
        "borrower_email": borrower.email if borrower else None,
        "claimed_at": card.claimed_at,
        "lent_at": card.lent_at,
        "can_claim": can_claim,
        "can_lend": can_lend,
        "can_stop_lend": can_stop_lend,
        "can_play": can_play,
        "start_position": start_position,
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
