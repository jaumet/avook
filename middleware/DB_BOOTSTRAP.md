# Database Bootstrap

This document explains how to initialize the database with the required schema and some initial data for development.

## 1. Create the database schema

The database schema is created automatically when the middleware service starts, thanks to the `SQLModel.metadata.create_all(engine)` command in `app/db.py`.

If you need to create the schema manually, you can run the following command from the `middleware` directory:
```bash
python -c "from app.db import init_db; init_db()"
```

## 2. Populate the database with development data

To populate the database with some initial data for development, you can run the bootstrap script:
```bash
python app/bootstrap.py
```
This will create a sample title, store, batch, and card. You can modify the `app/bootstrap.py` script to add more data.
