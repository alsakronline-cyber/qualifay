"""Autonomous Growth Phase 2 — verification + autonomy routing.

These cover the pure decision logic that decides whether a scraped lead is real and
where it goes after BANT scoring. Kept DB-free so the safety-critical rule ("never
auto-message a junk or unreachable lead") is fast to check and can't silently regress.
"""
from app.workers.ai_tasks import (
    is_junk_identity, has_contact_channel, verify_real_lead, resolve_route,
)


# ── identity ──────────────────────────────────────────────
def test_junk_identity_rejects_placeholders():
    assert is_junk_identity("", "") is True
    assert is_junk_identity("N/A", None) is True
    assert is_junk_identity(None, "غير معروف") is True
    assert is_junk_identity("01012345678", None) is True   # phone-as-name, no letters
    assert is_junk_identity("-", "--") is True


def test_junk_identity_accepts_real_names():
    assert is_junk_identity("Ahmed Ali", None) is False
    assert is_junk_identity(None, "Al Nour Contracting") is False
    assert is_junk_identity(None, "شركة النور") is False


# ── reachability ──────────────────────────────────────────
def test_contact_channel():
    assert has_contact_channel("+201000000000", None, None) is True
    assert has_contact_channel(None, "a@b.com", None) is True
    assert has_contact_channel(None, "not-an-email", None) is False   # no @/domain
    assert has_contact_channel(None, "a@localhost", None) is False    # no dot in domain
    assert has_contact_channel(None, None, "site.com") is True
    assert has_contact_channel(None, None, None) is False


def test_verify_real_lead():
    ok, _ = verify_real_lead(name="Ahmed", company="Al Nour", phone="+201000000000",
                             email=None, website=None)
    assert ok is True
    bad_id, reason = verify_real_lead(name="", company="", phone="+201000000000",
                                      email=None, website=None)
    assert bad_id is False and "اسم" in reason
    no_contact, reason2 = verify_real_lead(name="Ahmed", company="Al Nour", phone=None,
                                           email=None, website=None)
    assert no_contact is False and "تواصل" in reason2


# ── routing ───────────────────────────────────────────────
def test_route_below_threshold_archived():
    assert resolve_route(autonomy="full", auto_approve=True, verified_real=True,
                         score=30, min_score=50) == "archived"


def test_route_full_autonomy_verified_auto_approves():
    assert resolve_route(autonomy="full", auto_approve=False, verified_real=True,
                         score=80, min_score=50) == "approved"


def test_route_full_autonomy_unverified_never_auto_approves():
    # The safety rule: a high score does NOT auto-message an unreachable/junk lead.
    assert resolve_route(autonomy="full", auto_approve=True, verified_real=False,
                         score=90, min_score=50) == "pending_review"


def test_route_copilot_and_manual_go_to_review():
    for mode in ("copilot", "manual", "off"):
        assert resolve_route(autonomy=mode, auto_approve=True, verified_real=True,
                             score=90, min_score=50) == "pending_review"


def test_route_legacy_auto_approve_when_autonomy_unset():
    assert resolve_route(autonomy="", auto_approve=True, verified_real=True,
                         score=80, min_score=50) == "approved"
    assert resolve_route(autonomy=None, auto_approve=False, verified_real=True,
                         score=80, min_score=50) == "pending_review"
