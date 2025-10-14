"""Utilities for computing aggregated statistics for the admin dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import func
from sqlmodel import Session, select

from app.models import Card, Title, User
from app.schemas import AdminDashboard, DashboardDailyStat, DashboardTotals

_WINDOW_DAYS = 30


def _coerce_date(value) -> date:
    """Convert values returned by SQL backends into ``date`` objects.

    SQLite returns ISO formatted strings for ``DATE`` expressions whereas
    PostgreSQL will return ``datetime``/``date`` objects.  Normalising the
    values ensures the returned series is stable across engines.
    """

    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        return datetime.fromisoformat(value).date()
    raise TypeError(f"Unsupported date value: {value!r}")


def _build_series(
    rows: Iterable[tuple[object, int]],
    start_day: date,
    window_days: int,
) -> list[DashboardDailyStat]:
    """Normalise aggregated rows into a dense list of data points."""

    mapping = {_coerce_date(day): int(count or 0) for day, count in rows}
    series: list[DashboardDailyStat] = []
    for offset in range(window_days):
        current_day = start_day + timedelta(days=offset)
        series.append(
            DashboardDailyStat(date=current_day, count=mapping.get(current_day, 0))
        )
    return series


def _count(session: Session, stmt) -> int:
    """Execute a ``SELECT COUNT`` statement and return an integer."""

    result = session.exec(stmt)
    value = result.one()
    return int(value) if value is not None else 0


def build_admin_dashboard(session: Session) -> AdminDashboard:
    """Compute aggregate metrics for the admin dashboard."""

    today = datetime.now(timezone.utc).date()
    window_days = _WINDOW_DAYS
    start_day = today - timedelta(days=window_days - 1)
    start_boundary = start_day.isoformat()

    totals = DashboardTotals(
        users=_count(session, select(func.count()).select_from(User)),
        titles=_count(session, select(func.count()).select_from(Title)),
        cards=_count(session, select(func.count()).select_from(Card)),
        claimed_cards=_count(
            session,
            select(func.count()).select_from(Card).where(Card.claimed_at.is_not(None)),
        ),
        active_loans=_count(
            session,
            select(func.count()).select_from(Card).where(Card.user_state == 2),
        ),
    )

    activations_last_window = _count(
        session,
        select(func.count())
        .select_from(Card)
        .where(Card.claimed_at.is_not(None), func.date(Card.claimed_at) >= start_boundary),
    )

    loans_last_window = _count(
        session,
        select(func.count())
        .select_from(Card)
        .where(Card.lent_at.is_not(None), func.date(Card.lent_at) >= start_boundary),
    )

    activation_day = func.date(Card.claimed_at)
    loan_day = func.date(Card.lent_at)

    activation_rows = session.exec(
        select(activation_day, func.count())
        .where(Card.claimed_at.is_not(None), activation_day >= start_boundary)
        .group_by(activation_day)
        .order_by(activation_day)
    ).all()

    loan_rows = session.exec(
        select(loan_day, func.count())
        .where(Card.lent_at.is_not(None), loan_day >= start_boundary)
        .group_by(loan_day)
        .order_by(loan_day)
    ).all()

    return AdminDashboard(
        generated_at=datetime.now(timezone.utc),
        totals=totals,
        activations_last_30_days=activations_last_window,
        loans_last_30_days=loans_last_window,
        activations_trend=_build_series(activation_rows, start_day, window_days),
        loans_trend=_build_series(loan_rows, start_day, window_days),
    )
