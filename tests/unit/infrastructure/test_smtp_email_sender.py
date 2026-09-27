"""SMTP adapter treats server acceptance as success and refusal as failure."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
from app.messaging.smtp import SMTPEmailSender
from app.services.email_sender import EmailDeliveryError


def test_smtp_sender_uses_starttls_and_submits_message() -> None:
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {}
    sender = SMTPEmailSender(
        host="smtp.example.com",
        port=587,
        from_email="support@example.com",
        username="support",
        password="secret",
    )

    with patch("app.messaging.smtp.smtplib.SMTP", return_value=smtp):
        asyncio.run(
            sender.send(to_email="customer@example.com", subject="Re: Refund", body="Hello")
        )

    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with("support", "secret")
    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "customer@example.com"
    assert message["From"] == "support@example.com"
    assert message.get_content().strip() == "Hello"


def test_smtp_sender_rejects_refused_recipient() -> None:
    smtp = MagicMock()
    smtp.__enter__.return_value = smtp
    smtp.send_message.return_value = {"customer@example.com": (550, b"Rejected")}
    sender = SMTPEmailSender(host="smtp.example.com", port=587, from_email="support@example.com")

    with patch("app.messaging.smtp.smtplib.SMTP", return_value=smtp):
        with pytest.raises(EmailDeliveryError, match="rejected the recipient"):
            asyncio.run(sender.send(to_email="customer@example.com", subject="Hi", body="Hello"))
