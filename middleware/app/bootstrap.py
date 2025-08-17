from sqlmodel import Session, SQLModel, create_engine
from app.models import Title, Card, Store, Batch
from app.db import engine

def create_db_and_tables():
    SQLModel.metadata.create_all(engine)

def create_dev_data():
    with Session(engine) as session:
        # Create a title
        title1 = Title(
            title="The Adventures of Jules",
            author="Jules Verne",
            language="en",
            duration_sec=3600,
            price_retail=19.99,
            currency="USD",
        )
        session.add(title1)
        session.commit()
        session.refresh(title1)

        # Create a store
        store1 = Store(
            name="The Book Nook",
            channel_type="bookstore",
            city="Paris",
            country="France",
        )
        session.add(store1)
        session.commit()
        session.refresh(store1)

        # Create a batch
        batch1 = Batch(
            title_id=title1.id,
            qty=100,
        )
        session.add(batch1)
        session.commit()
        session.refresh(batch1)

        # Create a card
        card1 = Card(
            qr="PA-DEV-0001",
            title_id=title1.id,
            store_id=store1.id,
            batch_id=batch1.id,
        )
        session.add(card1)
        session.commit()

if __name__ == "__main__":
    create_db_and_tables()
    create_dev_data()
