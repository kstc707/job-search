"""Customer notification text for tasks flagged as likely to miss their pickup window.

Deterministic templates, no language model: the message must state only times the system knows.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class Notification:
    order_id: int
    risk: float
    message: str


def _hhmm(ts: pd.Timestamp) -> str:
    return pd.Timestamp(ts).strftime("%H:%M")


def compose(order_id: int, window_start, window_end, accept_time, eta_minutes: float, risk: float) -> Notification:
    """Message for one flagged task. Gives an estimated time only when it is past the window end;
    otherwise the ETA model and the risk model disagree, and we say only that it may run late."""
    end = pd.Timestamp(window_end)
    eta = pd.Timestamp(accept_time) + pd.Timedelta(minutes=float(eta_minutes))
    base = f"Your pickup window is {_hhmm(window_start)}-{_hhmm(end)}. The courier may arrive after {_hhmm(end)}."
    if eta > end:
        rounded = eta.ceil("15min")
        base += f" Current estimate: around {_hhmm(rounded)}."
    base += " We will message you again if this changes. Reply R to pick a new time."
    return Notification(order_id=int(order_id), risk=round(float(risk), 4), message=base)
