from app.workers.drip_tasks import _split


def test_even_split_between_two_numbers():
    assert _split(30, {"alyan": 200, "masoud": 200}) == {"alyan": 15, "masoud": 15}


def test_young_number_capped_rest_goes_to_other():
    # masoud is new (warmup cap 10): it takes 10, alyan picks up the remaining 20.
    assert _split(30, {"alyan": 200, "masoud": 10}) == {"alyan": 20, "masoud": 10}


def test_total_never_exceeded_and_odd_totals():
    plan = _split(31, {"a": 200, "b": 200})
    assert sum(plan.values()) == 31 and abs(plan["a"] - plan["b"]) <= 1


def test_not_enough_room_sends_what_fits():
    assert _split(30, {"a": 5, "b": 3}) == {"a": 5, "b": 3}


def test_single_number_and_none():
    assert _split(30, {"only": 200}) == {"only": 30}
    assert _split(30, {}) == {}
    assert _split(30, {"a": 0}) == {"a": 0}
