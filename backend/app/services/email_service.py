"""Email service — SMTP outreach for leads without a WhatsApp number (e.g. LinkedIn).

Uses stdlib smtplib (no extra dependency). The blocking send runs in a thread so it
doesn't stall the async event loop. Credentials come from settings (loaded literally
from .env via the celery env_file, so passwords with $ aren't mangled by compose).
"""
import asyncio
import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from app.core.config import settings

logger = logging.getLogger(__name__)


def _hdr(value: str) -> str:
    """Sanitize a value destined for a MIME header: embedded CR/LF would let extra
    headers (e.g. a hidden Bcc:) be injected into the outgoing message."""
    return (value or "").replace("\r", " ").replace("\n", " ").strip()


def build_message(from_name, from_addr, to, subject, body_text, unsubscribe_url=None):
    """A plain, well-formed single-part text email — what mailbox providers expect from a
    person writing one-to-one: Date, a Message-ID on the sender's own domain, Reply-To, and
    a List-Unsubscribe header (Gmail/Yahoo sender requirements) so opting out is one click."""
    from email.utils import formatdate, make_msgid
    from_addr = _hdr(from_addr)
    domain = from_addr.split("@", 1)[1] if "@" in from_addr else None
    msg = MIMEText(body_text or "", "plain", "utf-8")
    msg["From"] = formataddr((_hdr(from_name), from_addr))
    msg["To"] = _hdr(to)
    msg["Subject"] = _hdr(subject)
    msg["Date"] = formatdate(localtime=False, usegmt=True)
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Reply-To"] = from_addr
    mailto = f"<mailto:{from_addr}?subject=unsubscribe>"
    if unsubscribe_url:
        # https first + List-Unsubscribe-Post = RFC 8058 one-click (Gmail/Yahoo bulk rules).
        msg["List-Unsubscribe"] = f"<{_hdr(unsubscribe_url)}>, {mailto}"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    else:
        msg["List-Unsubscribe"] = mailto
    return msg


class EmailService:
    def is_configured(self) -> bool:
        return bool(settings.SMTP_HOST and settings.SMTP_USER and self._password())

    def _password(self) -> str:
        # Prefer SMTP_PASSWORD; fall back to the older SMTP_APP_PASSWORD name.
        return settings.SMTP_PASSWORD or settings.SMTP_APP_PASSWORD or ""

    def _from(self) -> str:
        return settings.SMTP_FROM or settings.SMTP_USER

    def _send_sync(self, to: str, subject: str, body_text: str) -> None:
        msg = MIMEMultipart()
        msg["From"] = formataddr((settings.SMTP_FROM_NAME or "", self._from()))
        msg["To"] = _hdr(to)
        msg["Subject"] = _hdr(subject)
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        ctx = ssl.create_default_context()
        host, port, pwd = settings.SMTP_HOST, settings.SMTP_PORT, self._password()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=25) as s:
                s.login(settings.SMTP_USER, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=25) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.login(settings.SMTP_USER, pwd)
                s.send_message(msg)

    async def send(self, to: str, subject: str, body_text: str) -> None:
        if not self.is_configured():
            raise RuntimeError("SMTP is not configured")
        await asyncio.to_thread(self._send_sync, to, subject, body_text)

    def _send_via_sync(self, host, port, user, pwd, from_name, from_email,
                       to, subject, body_text, unsubscribe_url=None) -> None:
        msg = build_message(from_name, from_email or user, to, subject, body_text, unsubscribe_url)
        ctx = ssl.create_default_context()
        if int(port) == 465:
            with smtplib.SMTP_SSL(host, int(port), context=ctx, timeout=25) as s:
                s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, int(port), timeout=25) as s:
                s.ehlo()
                s.starttls(context=ctx)
                s.login(user, pwd)
                s.send_message(msg)

    async def send_via_account(self, account, to: str, subject: str, body_text: str,
                               unsubscribe_url: str = None) -> None:
        """Send using a specific EmailAccount's SMTP credentials. Mail to a lead passes
        `unsubscribe_url` (see app.services.unsubscribe) for the one-click header."""
        from app.core.crypto import decrypt
        pwd = decrypt(account.smtp_password_enc)
        await asyncio.to_thread(
            self._send_via_sync,
            account.smtp_host, account.smtp_port, account.smtp_user, pwd,
            account.from_name, account.from_email, to, subject, body_text, unsubscribe_url,
        )


email_service = EmailService()


async def send_system(db, to: str, subject: str, body_text: str) -> None:
    """Platform-level email (e.g. signup verification). A brand-new tenant has no mailbox
    of its own yet, so use the global .env SMTP if configured, otherwise fall back to any
    configured EmailAccount as the platform sender. Raises if nothing is available."""
    if email_service.is_configured():
        await email_service.send(to, subject, body_text)
        return
    from app.models.models import EmailAccount
    from sqlalchemy import select
    acct = (await db.execute(
        select(EmailAccount).where(EmailAccount.smtp_host.isnot(None))
    )).scalars().first()
    if acct:
        await email_service.send_via_account(acct, to, subject, body_text)
        return
    raise RuntimeError("No system email sender configured")


async def send_for_tenant(db, tenant_id: str, to: str, subject: str, body_text: str) -> None:
    """Send an email on behalf of a tenant. Prefers the tenant's own configured
    EmailAccount SMTP (e.g. Hostinger/Gmail), falling back to the global .env SMTP.
    Raises RuntimeError if neither is configured."""
    from app.models.models import EmailAccount
    from sqlalchemy import select, and_
    acct = (await db.execute(select(EmailAccount).where(and_(
        EmailAccount.tenant_id == tenant_id,
        EmailAccount.smtp_host.isnot(None),
    )))).scalars().first()
    if acct:
        await email_service.send_via_account(acct, to, subject, body_text)
        return
    if email_service.is_configured():
        await email_service.send(to, subject, body_text)
        return
    raise RuntimeError("SMTP not configured")
