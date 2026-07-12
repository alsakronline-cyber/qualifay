"""Guards for the security fixes and the campaign-stats refactor:
- require_admin correctly blocks non-admins (S1).
- audience_conditions tolerates a non-numeric min_score instead of raising (S2).
- campaign stats aggregation math is correct (refactor to bulk query).
Pure-ish unit tests — no live DB needed.
"""
import pytest
from fastapi import HTTPException


def test_require_admin_allows_admin():
    from app.api.auth import require_admin
    require_admin({"is_tenant_admin": True})  # should not raise


def test_require_admin_blocks_non_admin():
    from app.api.auth import require_admin
    with pytest.raises(HTTPException) as exc:
        require_admin({"is_tenant_admin": False})
    assert exc.value.status_code == 403


def test_require_admin_blocks_missing_flag():
    from app.api.auth import require_admin
    with pytest.raises(HTTPException):
        require_admin({})  # no flag == not admin


def test_audience_conditions_ignores_bad_min_score():
    """S2: a non-numeric min_score must be skipped, not raise."""
    from app.api.campaigns import audience_conditions
    # Should not raise on garbage input.
    conds_bad = audience_conditions({"min_score": "abc"}, "tenant-1")
    conds_empty = audience_conditions({}, "tenant-1")
    # Bad min_score adds no score condition, so it matches the empty-filter length.
    assert len(conds_bad) == len(conds_empty)


def test_audience_conditions_applies_numeric_min_score():
    from app.api.campaigns import audience_conditions
    conds_num = audience_conditions({"min_score": 50}, "tenant-1")
    conds_empty = audience_conditions({}, "tenant-1")
    assert len(conds_num) == len(conds_empty) + 1


def test_stats_from_counts_math():
    from app.api.campaigns import _stats_from_counts
    s = _stats_from_counts({"active": 2, "replied": 1, "completed": 1})
    assert s["enrolled"] == 4
    assert s["replied"] == 1
    assert s["reply_rate"] == 25.0


def test_stats_from_counts_empty():
    from app.api.campaigns import _stats_from_counts
    s = _stats_from_counts({})
    assert s["enrolled"] == 0
    assert s["reply_rate"] == 0.0
