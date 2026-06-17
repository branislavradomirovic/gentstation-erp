from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from core.models import CCTVEvent, CCTVReviewAction


REVIEW_STATUS_NEW = "new"
REVIEW_STATUS_ACKNOWLEDGED = "acknowledged"
REVIEW_STATUS_REVIEWED = "reviewed"
REVIEW_STATUS_FALSE_POSITIVE = "false_positive"
REVIEW_STATUS_RESOLVED = "resolved"
REVIEW_STATUS_ESCALATED = "escalated"

REVIEW_ACTION_TO_STATUS = {
    REVIEW_STATUS_ACKNOWLEDGED: REVIEW_STATUS_ACKNOWLEDGED,
    REVIEW_STATUS_REVIEWED: REVIEW_STATUS_REVIEWED,
    REVIEW_STATUS_FALSE_POSITIVE: REVIEW_STATUS_FALSE_POSITIVE,
    REVIEW_STATUS_RESOLVED: REVIEW_STATUS_RESOLVED,
    REVIEW_STATUS_ESCALATED: REVIEW_STATUS_ESCALATED,
}

ALLOWED_REVIEW_STATUSES = frozenset(REVIEW_ACTION_TO_STATUS.keys()) | frozenset({REVIEW_STATUS_NEW})

ALLOWED_REVIEW_TRANSITIONS = {
    REVIEW_STATUS_NEW: frozenset(REVIEW_ACTION_TO_STATUS.keys()),
    REVIEW_STATUS_ACKNOWLEDGED: frozenset(REVIEW_ACTION_TO_STATUS.keys()),
    REVIEW_STATUS_REVIEWED: frozenset({REVIEW_STATUS_RESOLVED, REVIEW_STATUS_ESCALATED, REVIEW_STATUS_FALSE_POSITIVE}),
    REVIEW_STATUS_FALSE_POSITIVE: frozenset(),
    REVIEW_STATUS_RESOLVED: frozenset(),
    REVIEW_STATUS_ESCALATED: frozenset({REVIEW_STATUS_REVIEWED}),
}


@dataclass(frozen=True)
class ReviewTransitionResult:
    previous_status: str
    new_status: str
    action: CCTVReviewAction


def normalize_review_status(value: Optional[str]) -> str:
    status = str(value or REVIEW_STATUS_NEW).strip().lower()
    return status if status in ALLOWED_REVIEW_STATUSES else REVIEW_STATUS_NEW


def allowed_review_actions(current_status: Optional[str]) -> tuple[str, ...]:
    status = normalize_review_status(current_status)
    return tuple(sorted(ALLOWED_REVIEW_TRANSITIONS.get(status, frozenset())))


def apply_review_transition(
    session,
    *,
    event: CCTVEvent,
    tenant_id: int,
    reviewer_user_id: Optional[int],
    new_status: str,
    comment: Optional[str] = None,
) -> ReviewTransitionResult:
    if event.tenant_id != tenant_id:
        raise ValueError("CCTV event does not belong to the active tenant.")

    current_status = normalize_review_status(event.status)
    desired_status = normalize_review_status(new_status)
    if desired_status not in ALLOWED_REVIEW_STATUSES:
        raise ValueError(f"Unsupported review status: {new_status!r}")

    allowed_targets = ALLOWED_REVIEW_TRANSITIONS.get(current_status, frozenset())
    if desired_status not in allowed_targets and desired_status != current_status:
        raise ValueError(f"Cannot transition CCTV event from {current_status!r} to {desired_status!r}.")

    event.status = desired_status
    action = CCTVReviewAction(
        tenant_id=tenant_id,
        event_id=event.id,
        reviewer_user_id=reviewer_user_id,
        action=desired_status,
        from_status=current_status,
        to_status=desired_status,
        comment=(comment or "").strip() or None,
    )
    session.add(action)
    return ReviewTransitionResult(previous_status=current_status, new_status=desired_status, action=action)
