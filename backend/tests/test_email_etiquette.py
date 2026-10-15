from app.services.email_inbox_service import is_opt_out
from app.services.email_service import build_message
from app.workers.drip_tasks import EMAIL_GAP, cold_email_cap, send_window_offset


def test_new_mailbox_ramps_slowly():
    assert [cold_email_cap(d) for d in (1, 7, 8, 14, 15, 21, 22, 30, 31)] == [5, 5, 10, 10, 15, 15, 20, 20, 30]


def test_emails_are_minutes_apart():
    assert EMAIL_GAP[0] >= 5 * 60


def test_recipient_morning_windows():
    assert send_window_offset("1 Main St, Boston, MA 02110, USA") > 6 * 3600
    assert send_window_offset("London EC1V, United Kingdom") == 3600
    assert send_window_offset("Dubai - United Arab Emirates") == 0


def test_message_headers():
    m = build_message("Walaa 3D Studio", "contact@walaa3d.studio", "info@x.com", "Hi", "Body")
    assert m["List-Unsubscribe"] == "<mailto:contact@walaa3d.studio?subject=unsubscribe>"
    assert m["Reply-To"] == "contact@walaa3d.studio"
    assert m["Message-ID"].endswith("@walaa3d.studio>") and m["Date"]
    assert not m.is_multipart()


def test_opt_out_detection():
    assert is_opt_out("unsubscribe", "")
    assert is_opt_out("Re: hello", "Please remove me from your list")
    assert is_opt_out("Re: hi", "Stop\n\nOn Mon, Walaa wrote:\n> ...")
    # The quoted original mentions "unsubscribe" — that alone is not an opt-out.
    assert not is_opt_out("Re: 3D animation", "Sounds interesting, call me.\n\nOn Mon, Walaa wrote:\n> reply unsubscribe")
    assert not is_opt_out("Re: hi", "Can you share your prices?")


def test_tenant_fixed_daily_cap():
    from app.workers.drip_tasks import daily_email_cap
    assert daily_email_cap({"email_daily_max": 10}, provider_cap=20, drip_max=30, day=1) == 10
    assert daily_email_cap({}, provider_cap=20, drip_max=30, day=1) == 5          # ramp
    assert daily_email_cap({"email_daily_max": 50}, provider_cap=20, drip_max=30, day=1) == 20  # provider bound
