from app.workers.report_tasks import build_report


def test_report_lists_sends_replies_and_next_steps():
    subject, body = build_report(
        "Walaa 3D Studio",
        sent=[("07:12", "AVA Robotics", "info@avarobotics.com"), ("07:25", "HAL Robotics", "the-team@hal-robotics.com")],
        replies=[("AVA Robotics", "info@avarobotics.com", "Sounds interesting")],
        opted_out=[("X Corp", "info@x.com")], bounced=[], queued=40, tomorrow_cap=5, day="2026-10-15")
    assert subject == "Walaa 3D Studio — daily outreach report 2026-10-15: 2 sent, 1 replies"
    assert "1. AVA Robotics <info@avarobotics.com>  at 07:12 UTC" in body
    assert "Sounds interesting" in body and "UNSUBSCRIBED" in body
    assert "STILL QUEUED: 40" in body and "up to 5 emails tomorrow" in body
    assert "BOUNCED" not in body


def test_empty_day():
    _, body = build_report("W", [], [], [], [], 0, 5, "2026-10-15")
    assert "EMAILS SENT: 0" in body and "(none)" in body
