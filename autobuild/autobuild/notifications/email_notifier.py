"""Notifier that emails the rendered notification over SMTP.

Settings come from `notifications.email`; the password is read from the
environment variable it names and never stored in config, state or logs.
Delivery failures raise to the caller, which records them without letting them
affect the run's persisted state.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from autobuild.notifications.notification_format import format_notification


class EmailNotifier:
    def __init__(self, settings: dict[str, Any], timeout: float = 30):
        self.settings = settings
        self.timeout = timeout

    def message(self, payload: dict[str, Any]) -> EmailMessage:
        text = format_notification(payload)
        message = EmailMessage()
        message["Subject"] = text.splitlines()[0]
        message["From"] = self.settings["from"]
        message["To"] = ", ".join(self.settings["to"])
        message.set_content(text)
        return message

    def send(self, payload: dict[str, Any]) -> None:
        settings = self.settings
        security = settings.get("security", "starttls")
        port = settings.get("smtp_port", 465 if security == "ssl" else 587)
        context = ssl.create_default_context()
        connect = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
        kwargs = {"context": context} if security == "ssl" else {}
        with connect(settings["smtp_host"], port, timeout=self.timeout, **kwargs) as client:
            if security == "starttls":
                client.starttls(context=context)
            if settings.get("username_env"):
                username, password = os.environ.get(settings["username_env"]), os.environ.get(settings.get("password_env", ""))
                if not username or not password:
                    raise RuntimeError(f"SMTP credentials missing: set {settings['username_env']} and {settings.get('password_env')}")
                client.login(username, password)
            client.send_message(self.message(payload))
