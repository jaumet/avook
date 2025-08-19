from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from app.models import Title, User, Card, Store, Batch
from app.db import get_session
from app.auth import get_current_admin_user
from uuid import uuid4
from fastapi.responses import StreamingResponse
import io
import csv

router = APIRouter(
    tags=["Admin"],
    dependencies=[Depends(get_current_admin_user)]
)

@router.get("/")
def admin_root():
    return {"status": "Admin section"}

@router.get("/ping")
def admin_ping():
    return {"ok": True}

@router.post("/titles", response_model=Title)
def create_title(title: Title, db: Session = Depends(get_session)):
    db.add(title)
    db.commit()
    db.refresh(title)
    return title

@router.get("/titles", response_model=list[Title])
def read_titles(search: str = "", active: bool = True, db: Session = Depends(get_session)):
    query = select(Title).where(Title.active == active)
    if search:
        query = query.where(Title.title.contains(search))
    titles = db.exec(query).all()
    return titles

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

@router.get("/batches", response_model=list[Batch])
def read_batches(db: Session = Depends(get_session)):
    batches = db.exec(select(Batch)).all()
    return batches

@router.put("/users/{user_id}/make-admin", response_model=User)
def make_admin(user_id: UUID, db: Session = Depends(get_session), admin: User = Depends(get_current_admin_user)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_admin = True
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.get("/users", response_model=list[User])
def read_users(db: Session = Depends(get_session)):
    users = db.exec(select(User)).all()
    return users

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
