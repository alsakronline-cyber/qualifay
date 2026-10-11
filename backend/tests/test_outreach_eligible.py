from types import SimpleNamespace as N

from app.workers.outreach_tasks import outreach_eligible


def inst(name, day=30, paused=False, sent=0):
    return N(instance_name=name, day_of_life=day, paused=paused, sent_today_wa=sent)


def test_paused_number_never_sends():
    assert outreach_eligible([inst("alsakr", paused=True)]) == []


def test_new_number_in_protection_period_never_sends():
    assert outreach_eligible([inst("masoud", day=3), inst("fresh", day=None)]) == []
    assert [i.instance_name for i in outreach_eligible([inst("ok", day=14)])] == ["ok"]


def test_least_used_eligible_number_first():
    got = outreach_eligible([inst("a", sent=12), inst("b", sent=3), inst("c", paused=True)])
    assert [i.instance_name for i in got] == ["b", "a"]
