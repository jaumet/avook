import json

from sqlmodel import SQLModel, Session, create_engine

from app.backup import perform_backup
from app.models import Card, Title, User


def test_perform_backup_persists_tables(tmp_path):
    database_path = tmp_path / "backup.db"
    engine = create_engine(f"sqlite:///{database_path}", echo=False)
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(email="backup@example.com", password_hash="hashed")
        session.add(user)
        title = Title(
            title="Backup",
            author="Author",
            language="ca",
            duration_sec=123,
            price_retail=9.99,
            currency="EUR",
            abs_share_code="share-backup",
        )
        session.add(title)
        session.commit()

        card = Card(qr="QR-BACKUP", title_id=title.id, owner_user_id=user.id, user_state=1)
        session.add(card)
        session.commit()

    backup_file = perform_backup(engine, tmp_path)
    assert backup_file.exists()

    payload = json.loads(backup_file.read_text())
    assert payload["tables"]["User"][0]["email"] == "backup@example.com"
    assert payload["tables"]["Card"][0]["qr"] == "QR-BACKUP"
    assert payload["tables"]["Title"][0]["abs_share_code"] == "share-backup"
