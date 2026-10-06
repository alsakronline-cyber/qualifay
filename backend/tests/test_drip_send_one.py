"""drip.send_one must permanently mark numbers that aren't on WhatsApp — including when the
send failure surfaces as an exception (that path once returned early and skipped marking)."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.workers import drip_tasks


def _session_with(lead):
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=lead)))
    db.commit = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=db)
    cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=cm)


def _lead():
    return SimpleNamespace(raw_data={"drip": {"wa_tpl": "t1"}}, status="active")


def _run(send_effect):
    lead = _lead()
    with patch("app.core.database.AsyncSessionLocal", _session_with(lead)), \
         patch("app.workers.outreach_tasks._process_approved_lead", AsyncMock(side_effect=send_effect)):
        out = asyncio.run(drip_tasks._send_one("L1", "whatsapp"))
    return out, lead


def test_exception_400_marks_not_on_whatsapp():
    err = Exception("Failed to send text via 'alsakr' to '2010@s.whatsapp.net': "
                    "Client error '400 Bad Request' for url 'http://localhost:8080/message/sendText/alsakr'")
    out, lead = _run(err)
    assert lead.raw_data["wa_contacted_at"] == "failed:not_on_whatsapp"
    assert out.get("marked") == "not_on_whatsapp"


def test_returned_400_error_also_marks():
    out, lead = _run([{"error": "Client error '400 Bad Request' for url ..."}])
    assert lead.raw_data["wa_contacted_at"] == "failed:not_on_whatsapp"


def test_transient_error_is_not_marked():
    out, lead = _run(Exception("Connection timed out"))
    assert "wa_contacted_at" not in lead.raw_data
    assert "error" in out


def test_already_sent_is_noop():
    lead = _lead()
    lead.raw_data["wa_contacted_at"] = "2026-10-06T07:02:00"
    send = AsyncMock()
    with patch("app.core.database.AsyncSessionLocal", _session_with(lead)), \
         patch("app.workers.outreach_tasks._process_approved_lead", send):
        out = asyncio.run(drip_tasks._send_one("L1", "whatsapp"))
    assert out == {"skipped": "already_sent", "channel": "whatsapp"}
    send.assert_not_called()
