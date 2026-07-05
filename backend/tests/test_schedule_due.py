"""Daily scrape schedule — due-logic (runs once per day, respects monthly cap, resets
the counter at month rollover)."""
from datetime import datetime, date
from types import SimpleNamespace

from app.workers.scrape_tasks import schedule_due_action

TODAY = date(2026, 7, 2)
MONTH = "2026-07"


def _sched(last_run=None, month_key=MONTH, count=0, cap=100):
    return SimpleNamespace(
        last_run_at=last_run, month_key=month_key, monthly_count=count, monthly_cap=cap,
    )


def test_runs_when_never_run():
    assert schedule_due_action(_sched(), TODAY, MONTH) == "run"


def test_skips_when_already_ran_today():
    last = datetime(2026, 7, 2, 9, 0)
    assert schedule_due_action(_sched(last_run=last), TODAY, MONTH) == "ran_today"


def test_runs_when_last_run_was_yesterday():
    last = datetime(2026, 7, 1, 9, 0)
    assert schedule_due_action(_sched(last_run=last), TODAY, MONTH) == "run"


def test_capped_when_count_at_cap():
    assert schedule_due_action(_sched(count=100, cap=100), TODAY, MONTH) == "capped"


def test_capped_when_count_over_cap():
    assert schedule_due_action(_sched(count=250, cap=100), TODAY, MONTH) == "capped"


def test_not_capped_just_below():
    assert schedule_due_action(_sched(count=99, cap=100), TODAY, MONTH) == "run"


def test_month_rollover_resets_effective_count():
    # High count but from a previous month → effective count is 0 → should run.
    s = _sched(month_key="2026-06", count=999, cap=100)
    assert schedule_due_action(s, TODAY, MONTH) == "run"


def test_ran_today_takes_precedence_over_cap():
    last = datetime(2026, 7, 2, 9, 0)
    s = _sched(last_run=last, count=999, cap=100)
    assert schedule_due_action(s, TODAY, MONTH) == "ran_today"
