import json
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from app.auth import create_access_token, verify_password, get_current_config_superuser
from app.schemas import Token

router = APIRouter()

SUPERUSER_CONFIG_PATH = "superuser.json"

@router.post("/login", response_model=Token, tags=["Superuser"])
def su_login(form_data: OAuth2PasswordRequestForm = Depends()):
    try:
        with open(SUPERUSER_CONFIG_PATH, "r") as f:
            superuser_data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Superuser is not configured correctly.",
        )

    email = superuser_data.get("email")
    password_hash = superuser_data.get("password_hash")

    is_valid_user = form_data.username == email
    is_valid_password = verify_password(form_data.password, password_hash)

    if not is_valid_user or not is_valid_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # The 'sub' can be the superuser's email. Add a specific scope for protection.
    token = create_access_token({"sub": email, "scope": "superuser"})
    return {"access_token": token, "token_type": "bearer"}

@router.get("/ping", tags=["Superuser"])
def su_ping(payload: dict = Depends(get_current_config_superuser)):
    return {"status": "ok", "message": "Superuser session is valid.", "user": payload.get("sub")}
