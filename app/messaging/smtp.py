"""SMTP implementation of the outbound email boundary."""

import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from app.services.email_sender import EmailDeliveryError


class SMTPEmailSender:
    """Submit messages through SMTP, using STARTTLS when configured."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        from_email: str,
        username: str = "",
        password: str = "",
        starttls: bool = True,
        timeout: float = 30.0,
    ) -> None:
        if not host.strip() or not from_email.strip() or port <= 0 or timeout <= 0:
            raise ValueError("SMTP host, sender address, port and timeout must be configured")
        self._host = host
        self._port = port
        self._from_email = from_email
        self._username = username
        self._password = password
        self._starttls = starttls
        self._timeout = timeout

    async def send(self, *, to_email: str, subject: str, body: str) -> None:
        await asyncio.to_thread(self._send_sync, to_email, subject, body)

    def _send_sync(self, to_email: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from_email
        message["To"] = to_email
        message["Subject"] = " ".join(subject.split())
        message.set_content(body)

        try:
            with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as smtp:
                if self._starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if self._username:
                    smtp.login(self._username, self._password)
                refused = smtp.send_message(message)
                if refused:
                    raise EmailDeliveryError("SMTP rejected the recipient")
        except EmailDeliveryError:
            raise
        except smtplib.SMTPAuthenticationError as error:
            raise EmailDeliveryError("SMTP authentication failed") from error
        except (smtplib.SMTPException, OSError) as error:
            raise EmailDeliveryError("SMTP delivery failed") from error
