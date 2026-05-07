"""
SMTP mail helpers.
"""
import asyncio
import logging
import os
import smtplib
import time as _time
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr

logger = logging.getLogger(__name__)

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("SMTP_FROM", "") or SMTP_USER
SMTP_DISPLAY_NAME = os.getenv("SMTP_DISPLAY_NAME", "Virtual Company Simulator")
SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() == "true"


def _send_email(to_email: str, subject: str, html_body: str) -> None:
    """Send an HTML email synchronously, retrying transient SMTP/network failures."""
    msg = MIMEMultipart("alternative")
    msg["From"] = formataddr((str(Header(SMTP_DISPLAY_NAME, "utf-8")), SMTP_FROM))
    msg["To"] = to_email
    msg["Subject"] = Header(subject, "utf-8")
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    last_err: Exception | None = None
    for attempt in range(3):
        try:
            if SMTP_USE_SSL:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.sendmail(SMTP_FROM, to_email, msg.as_string())
            else:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
                    server.starttls()
                    server.login(SMTP_USER, SMTP_PASSWORD)
                    server.sendmail(SMTP_FROM, to_email, msg.as_string())
            return
        except (OSError, smtplib.SMTPException) as exc:
            last_err = exc
            if attempt < 2:
                _time.sleep(2)
    if last_err:
        raise last_err


async def send_verification_email(to_email: str, token: str) -> None:
    """Send a registration verification email. Raises when SMTP is unavailable."""
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASSWORD:
        raise RuntimeError("SMTP is not configured")

    html = f"""\
<div style="max-width:480px;margin:0 auto;font-family:sans-serif;color:#334155;">
  <h2 style="color:#2563EB;">Registration Verification Code</h2>
  <p>You are registering a Virtual Company Simulator account. Your verification code is:</p>
  <div style="font-size:32px;font-weight:bold;letter-spacing:6px;
              color:#2563EB;background:#F1F5F9;padding:16px;
              border-radius:8px;text-align:center;">{token}</div>
  <p style="margin-top:16px;font-size:13px;color:#94A3B8;">
    The code is valid for 5 minutes. If you did not request this, ignore this email.
  </p>
</div>"""

    try:
        await asyncio.to_thread(_send_email, to_email, "Virtual Company registration code", html)
        logger.info("Verification email sent to %s", to_email)
    except Exception:
        logger.exception("Failed to send verification email to %s", to_email)
        raise
