"""Site Factory funnel: statuses, legal transitions, and the consent/timing policy.

Consent rules (Egypt PDPL 151/2020 + WhatsApp Business policy), enforced in code:
  1. Nothing is sent to a business until a human approves its intro (`intro_approved_by`).
  2. The intro only ASKS permission. The preview link is sent only after the business
     replies yes (`opted_in_at`).
  3. At most ONE follow-up per phase; silence after that ends the conversation.
  4. Any stop / no / cancel → data deleted, number hashed into a suppression list.
  5. Previews are private (unguessable token, noindex) and expire after PREVIEW_TTL.
"""
from __future__ import annotations

from datetime import datetime, timedelta

# ── Statuses ────────────────────────────────────────────────────────────────
FOUND = "found"                      # discovered, has the website gap
BUILT = "built"                      # facts gathered, copy written, preview rendered
AWAITING_APPROVAL = "awaiting_approval"  # waiting for a human to approve the intro
INTRO_SENT = "intro_sent"            # asked permission to send the preview
OPTED_IN = "opted_in"                # replied yes — consent recorded
PREVIEW_SENT = "preview_sent"        # link delivered, asked for feedback
CHANGES_REQUESTED = "changes_requested"  # wants edits — handed to a human
PAYMENT_SENT = "payment_sent"        # wants to buy — payment options sent
PAID = "paid"
LIVE = "live"                        # published (public, indexable)

# terminal
REJECTED = "rejected"                # human decided not to contact
DECLINED = "declined"                # said no / not interested
CANCELLED = "cancelled"              # cancelled the purchase or said stop
EXPIRED = "expired"                  # no answer within the window
UNREACHABLE = "unreachable"          # not on WhatsApp

ACTIVE_CONVERSATION = {INTRO_SENT, OPTED_IN, PREVIEW_SENT, CHANGES_REQUESTED, PAYMENT_SENT}
TERMINAL = {REJECTED, DECLINED, CANCELLED, EXPIRED, UNREACHABLE}
# Statuses whose personal data is purged (only a suppression hash survives).
PURGE_ON = {DECLINED, CANCELLED, EXPIRED, REJECTED}

TRANSITIONS: dict[str, set[str]] = {
    FOUND: {BUILT, UNREACHABLE, REJECTED},
    BUILT: {AWAITING_APPROVAL, UNREACHABLE, REJECTED},
    AWAITING_APPROVAL: {INTRO_SENT, REJECTED, UNREACHABLE},
    INTRO_SENT: {OPTED_IN, DECLINED, CANCELLED, EXPIRED},
    OPTED_IN: {PREVIEW_SENT, CANCELLED},
    PREVIEW_SENT: {PAYMENT_SENT, CHANGES_REQUESTED, DECLINED, CANCELLED, EXPIRED},
    CHANGES_REQUESTED: {PREVIEW_SENT, PAYMENT_SENT, DECLINED, CANCELLED, EXPIRED},
    PAYMENT_SENT: {PAID, CHANGES_REQUESTED, CANCELLED, EXPIRED},
    PAID: {LIVE},
    LIVE: set(),
}

# ── Timing policy ───────────────────────────────────────────────────────────
PREVIEW_TTL = timedelta(days=14)
FOLLOWUP_AFTER = {
    INTRO_SENT: timedelta(days=3),
    PREVIEW_SENT: timedelta(days=2),
    PAYMENT_SENT: timedelta(days=2),
}
GIVE_UP_AFTER = {          # measured from the last event, after the one follow-up
    INTRO_SENT: timedelta(days=6),
    PREVIEW_SENT: timedelta(days=5),
    PAYMENT_SENT: timedelta(days=7),
    CHANGES_REQUESTED: timedelta(days=10),
}
MAX_FOLLOWUPS_PER_PHASE = 1
SEND_HOURS_CAIRO = range(10, 20)   # 10:00–19:59 local; never message at night


class TransitionError(ValueError):
    pass


def can_transition(current: str, new: str) -> bool:
    return new in TRANSITIONS.get(current, set())


def assert_transition(current: str, new: str) -> None:
    if not can_transition(current, new):
        raise TransitionError(f"illegal site-prospect transition {current} → {new}")


def may_send_intro(status: str, approved_by: str | None, suppressed: bool, wa_reachable: bool | None) -> tuple[bool, str]:
    """The human gate. Returns (allowed, reason)."""
    if suppressed:
        return False, "suppressed"
    if wa_reachable is False:
        return False, "not_on_whatsapp"
    if status != AWAITING_APPROVAL:
        return False, f"status_{status}"
    if not approved_by:
        return False, "not_approved"
    return True, "ok"


def may_send_preview(status: str, opted_in_at: datetime | None) -> tuple[bool, str]:
    """The consent gate: the link goes out only after the business said yes."""
    if opted_in_at is None:
        return False, "no_consent"
    if status not in {OPTED_IN, CHANGES_REQUESTED}:
        return False, f"status_{status}"
    return True, "ok"


def in_send_window(now_cairo: datetime) -> bool:
    return now_cairo.hour in SEND_HOURS_CAIRO


def due_action(status: str, last_event_at: datetime, followups_sent: int, now: datetime) -> str | None:
    """What the scheduler should do for a silent prospect: 'followup', 'expire' or None."""
    if status not in FOLLOWUP_AFTER and status not in GIVE_UP_AFTER:
        return None
    idle = now - last_event_at
    if status in FOLLOWUP_AFTER and followups_sent < MAX_FOLLOWUPS_PER_PHASE and idle >= FOLLOWUP_AFTER[status]:
        return "followup"
    if status in GIVE_UP_AFTER and idle >= GIVE_UP_AFTER[status] and (
        followups_sent >= MAX_FOLLOWUPS_PER_PHASE or status not in FOLLOWUP_AFTER
    ):
        return "expire"
    return None
