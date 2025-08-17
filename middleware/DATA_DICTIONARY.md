# Data Dictionary

This document provides a description of the database tables and their fields.

## `titles`

| Field            | Type      | Description                               |
| ---------------- | --------- | ----------------------------------------- |
| id               | int       | Primary key                               |
| title            | str       | Title of the book                         |
| author           | str       | Author of the book                        |
| language         | str       | Language of the book (e.g., "en", "es")   |
| duration_sec     | int       | Duration of the audiobook in seconds      |
| cover_url        | str       | URL of the book cover image               |
| abs_share_code   | str       | Share code from Audiobookshelf            |
| price_retail     | float     | Retail price of the book                  |
| currency         | str       | Currency of the price (e.g., "USD")       |
| active           | bool      | Whether the title is active or not        |

## `cards`

| Field            | Type      | Description                               |
| ---------------- | --------- | ----------------------------------------- |
| qr               | str       | QR code (primary key)                     |
| title_id         | int       | Foreign key to the `titles` table         |
| user_state       | int       | {0: factory, 1: claimed, 2: on loan, 3: loanable, 4: loan disabled} |
| owner_user_id    | UUID      | Foreign key to the `user` table (nullable)|
| borrower_user_id | UUID      | Foreign key to the `user` table (nullable)|
| retail_state     | str       | {warehouse, assigned, on_sale, sold, void} |
| store_id         | int       | Foreign key to the `stores` table (nullable)|
| batch_id         | int       | Foreign key to the `batches` table (nullable)|
| claimed_at       | datetime  | Timestamp when the card was claimed       |
| lent_at          | datetime  | Timestamp when the card was lent          |
| updated_at       | datetime  | Timestamp of the last update              |
| notes            | str       | Additional notes                          |

## `stores`

| Field          | Type    | Description                           |
| -------------- | ------- | ------------------------------------- |
| id             | int     | Primary key                           |
| name           | str     | Name of the store                     |
| channel_type   | str     | {bookstore, kiosk, online}            |
| city           | str     | City where the store is located       |
| country        | str     | Country where the store is located    |
| contact_email  | str     | Contact email of the store            |
| external_ref   | str     | External reference for the store      |

## `batches`

| Field          | Type      | Description                               |
| -------------- | --------- | ----------------------------------------- |
| id             | int       | Primary key                               |
| title_id       | int       | Foreign key to the `titles` table         |
| qty            | int       | Quantity of cards in the batch            |
| printed_on     | datetime  | Timestamp when the batch was printed      |
| printer_vendor | str       | Name of the printer vendor                |
| notes          | str       | Additional notes                          |

## `user`

| Field         | Type    | Description                           |
| ------------- | ------- | ------------------------------------- |
| id            | UUID    | Primary key                           |
| email         | str     | User's email (unique)                 |
| password_hash | str     | Hashed password                       |
| name          | str     | User's name (nullable)                |
| location      | str     | User's location (nullable)            |

## `claim` (historical)

| Field          | Type      | Description                               |
| -------------- | --------- | ----------------------------------------- |
| id             | int       | Primary key                               |
| qr             | str       | QR code                                   |
| claimed_at     | datetime  | Timestamp when the card was claimed       |
| owner_email    | str       | Email of the owner                        |
| borrower_email | str       | Email of the borrower (nullable)          |
| lent_at        | datetime  | Timestamp when the card was lent          |
| returned_at    | datetime  | Timestamp when the card was returned      |
| status         | int       | Status of the claim                       |

## `playsession`

| Field       | Type      | Description                               |
| ----------- | --------- | ----------------------------------------- |
| id          | int       | Primary key                               |
| qr          | str       | QR code                                   |
| device_id   | str       | ID of the device                          |
| issued_at   | datetime  | Timestamp when the session was issued     |
| expires_at  | datetime  | Timestamp when the session expires        |

## `listeningprogress`

| Field      | Type      | Description                               |
| ---------- | --------- | ----------------------------------------- |
| id         | UUID      | Primary key                               |
| user_id    | UUID      | Foreign key to the `user` table           |
| qr         | str       | QR code                                   |
| position   | float     | Last listening position in seconds        |
| updated_at | datetime  | Timestamp of the last update              |
