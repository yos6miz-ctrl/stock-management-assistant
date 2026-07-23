from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol


@dataclass(frozen=True)
class MaterialChange:
    kind: str
    symbol: str
    previous_recommendation: str
    new_recommendation: str
    reason: str
    next_catalyst: str
    catalyst_timing: str
    suggested_action: str
    main_risk: str

    def to_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "symbol": self.symbol,
            "previous_recommendation": self.previous_recommendation,
            "new_recommendation": self.new_recommendation,
            "reason": self.reason,
            "next_catalyst": self.next_catalyst,
            "catalyst_timing": self.catalyst_timing,
            "suggested_action": self.suggested_action,
            "main_risk": self.main_risk,
        }


class ChangeNotifier(Protocol):
    def send(self, changes: tuple[MaterialChange, ...]) -> None:
        ...


class GmailSmtpNotifier:
    """Send plain-text material-change alerts through Gmail app passwords."""

    def __init__(
        self,
        *,
        sender: str,
        app_password: str,
        recipient: str,
        smtp_host: str = "smtp.gmail.com",
        smtp_port: int = 465,
    ):
        if not sender.strip():
            raise ValueError("GMAIL_SENDER is required")
        if not app_password.strip():
            raise ValueError("GMAIL_APP_PASSWORD is required")
        if not recipient.strip():
            raise ValueError("email recipient is required")
        self.sender = sender
        self.app_password = app_password
        self.recipient = recipient
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port

    def send(self, changes: tuple[MaterialChange, ...]) -> None:
        if not changes:
            return
        message = EmailMessage()
        message["Subject"] = "Stock agent: material recommendation changes"
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(_render_email(changes))
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(
            self.smtp_host,
            self.smtp_port,
            context=context,
            timeout=30,
        ) as smtp:
            smtp.login(self.sender, self.app_password)
            smtp.send_message(message)


def _render_email(changes: tuple[MaterialChange, ...]) -> str:
    sections = []
    for change in changes:
        sections.append(
            "\n".join(
                [
                    f"{change.symbol}: {change.kind}",
                    (
                        "Previous recommendation: "
                        f"{change.previous_recommendation}"
                    ),
                    f"New recommendation: {change.new_recommendation}",
                    f"Reason for the change: {change.reason}",
                    (
                        "Next catalyst and expected date: "
                        f"{change.next_catalyst} — {change.catalyst_timing}"
                    ),
                    f"Suggested action: {change.suggested_action}",
                    f"Main risk: {change.main_risk}",
                ]
            )
        )
    return "\n\n".join(sections) + "\n"
