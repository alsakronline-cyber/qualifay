from app.workers.drip_tasks import _cold_room


def test_new_number_sends_nothing_for_two_weeks():
    assert _cold_room(0, 200) == 0
    assert _cold_room(None, 200) == 0
    assert _cold_room(13, 200) == 0


def test_then_five_a_day_for_a_week():
    assert _cold_room(14, 200) == 5
    assert _cold_room(20, 200) == 5
    assert _cold_room(14, 3) == 3       # never above what warmup still allows


def test_mature_number_uses_full_room():
    assert _cold_room(21, 200) == 200
    assert _cold_room(60, 0) == 0
