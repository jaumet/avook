from fastapi import APIRouter, Depends, HTTPException, Body, Query
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select
from datetime import datetime, timedelta, timezone
import hmac, hashlib, base64, os
from uuid import uuid4
from pydantic import BaseModel
from app.models import ListeningProgress, Claim, PlaySession, User
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
def register(email: str = Body(...), password: str = Body(...), db: Session = Depends(get_session)):
    existing = db.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ja existeix un usuari amb aquest correu")

    user = User(id=uuid4(), email=email, password_hash=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "email": user.email}

@router.post("/claim/{qr}")
async def claim_qr(
    qr: str,
    owner_email: str,
    db: Session = Depends(get_session),
    user_id: str = Depends(get_current_user),
):
    existing = db.exec(select(Claim).where(Claim.qr == qr)).first()
    if existing:
        raise HTTPException(status_code=400, detail="QR ja reclamat")
    claim = Claim(qr=qr, owner_email=owner_email)
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return {"id": claim.id, "claimed_at": claim.claimed_at}

@router.post("/lend/{qr}")
def lend_book(
    qr: str,
    # Allow the borrower's email to come from either the request body or a query parameter.
    borrower_email: str | None = Body(None),
    borrower_email_param: str | None = Query(None, alias="borrower_email"),
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user)
) -> dict:
    # Determine the borrower email from body or query string.
    email = borrower_email or borrower_email_param
    if not email:
        raise HTTPException(status_code=400, detail="borrower_email is required")

    claim = db.exec(select(Claim).where(Claim.qr == qr)).first()
    if not claim:
        raise HTTPException(status_code=404, detail="QR not claimed")
    if claim.owner_email != user.email:
        raise HTTPException(status_code=403, detail="You are not the owner")
    if claim.status != 1:
        raise HTTPException(status_code=400, detail="Book is not available for lending")

    claim.borrower_email = email
    claim.lent_at = datetime.now(timezone.utc)
    claim.status = 2

    db.add(claim)
    db.commit()
    db.refresh(claim)
    return {"ok": True, "msg": "Lent successfully"}

@router.get("/abook/{qr}/play-auth", response_model=PlayAuthResponse)
def get_play_auth(
    qr: str,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user)
) -> PlayAuthResponse:
    """Determine whether a user can play an audiobook and return a signed URL.

    This endpoint checks the claim associated with the QR code.  If the
    requesting user is the owner or the current borrower, playback is
    authorised.  A signed Audiobookshelf stream URL is returned along with
    the current listening position.  Otherwise `can_play` is ``False`` and
    the reason indicates why.

    Args:
        qr: the QR code for the audiobook card.
        db: database session dependency.
        user: the authenticated user, injected via the dependency system.

    Returns:
        A `PlayAuthResponse` model.
    """
    claim = db.exec(select(Claim).where(Claim.qr == qr)).first()
    if not claim:
        raise HTTPException(status_code=404, detail="QR not claimed yet")

    # Determine playback permission and reason.
    if claim.owner_email == user.email:
        can_play = True
        reason = "owner"
    elif claim.borrower_email == user.email and claim.status == 2:
        can_play = True
        reason = "borrower"
    else:
        can_play = False
        reason = "unauthorized"

    # Fetch the last known listening progress for this QR/user.
    progress = db.exec(
        select(ListeningProgress)
        .where(ListeningProgress.user_id == user.id, ListeningProgress.qr == qr)
    ).first()
    start_position = progress.position if progress else 0.0

    # When authorised, generate the signed playback URL.  Otherwise keep None.
    signed_url = _generate_signed_url(qr, str(user.id)) if can_play else None

    return PlayAuthResponse(
        can_play=can_play,
        reason=reason,
        start_position=start_position,
        signed_url=signed_url,
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
    """Terminate an active lending session and return the book to the owner.

    Only the owner of the claim may invoke this endpoint.  It clears the
    borrower and resets the claim status to ``1`` (Reclamat).  If the book
    is not currently lent out or the caller is not the owner, appropriate
    HTTP errors are raised.
    """
    claim = db.exec(select(Claim).where(Claim.qr == qr)).first()
    if not claim:
        raise HTTPException(status_code=404, detail="QR inexistent")

    # Ensure the authenticated user is the owner of the claim.
    if user.email != claim.owner_email:
        raise HTTPException(status_code=403, detail="Només el propietari pot fer stop-lend")

    if not claim.borrower_email:
        raise HTTPException(status_code=400, detail="Aquest llibre no està en préstec")

    claim.borrower_email = None
    claim.lent_at = None
    claim.status = 1
    db.add(claim)
    db.commit()
    db.refresh(claim)
    return {"message": "Préstec aturat", "qr": claim.qr, "status": claim.status}

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
    print("🧪 user rebut a status:", type(user), user)
    
    claim = db.exec(select(Claim).where(Claim.qr == qr)).first()
    if not claim:
        raise HTTPException(status_code=404, detail="QR inexistent")

    return {
        "qr": claim.qr,
        "status": claim.status,
        "status_label": get_status_label(claim.status, claim.lent_at),
        "owner_email": claim.owner_email,
        "borrower_email": claim.borrower_email,
        "claimed_at": claim.claimed_at,
        "lent_at": claim.lent_at,
        "returned_at": claim.returned_at,
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
