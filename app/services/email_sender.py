"""Outbound email boundary for approved support answers."""

from typing import Protocol


class EmailDeliveryError(Exception):
    """The email transport did not confirm acceptance of a message."""


class EmailSender(Protocol):
    """Send one email and return only after the transport confirms acceptance."""

    async def send(self, *, to_email: str, subject: str, body: str) -> None: ...
