"""SMTP confirmation email delivery for BrightCare Clinic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
import smtplib
import ssl
from typing import Any, Callable

from environment_config import required_environment_variable


EMAIL_SUBJECT = "BrightCare Clinic Appointment Confirmation"


@dataclass(frozen=True)
class EmailConfig:
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    from_address: str


def load_email_config() -> EmailConfig:
    """Load SMTP settings from the centralized project environment."""
    port_text = required_environment_variable("EMAIL_SMTP_PORT")
    try:
        smtp_port = int(port_text)
    except ValueError as error:
        raise ValueError("EMAIL_SMTP_PORT must be an integer") from error
    if not 1 <= smtp_port <= 65535:
        raise ValueError("EMAIL_SMTP_PORT must be between 1 and 65535")

    return EmailConfig(
        smtp_host=required_environment_variable("EMAIL_SMTP_HOST"),
        smtp_port=smtp_port,
        smtp_username=required_environment_variable("EMAIL_SMTP_USERNAME"),
        smtp_password=required_environment_variable("EMAIL_SMTP_PASSWORD"),
        from_address=required_environment_variable("EMAIL_FROM_ADDRESS"),
    )


def _format_time(value: datetime) -> str:
    period = "am" if value.hour < 12 else "pm"
    display_hour = value.hour % 12 or 12
    return f"{display_hour}:{value.minute:02d}{period}"


def build_confirmation_message(
    patient_email: str,
    appointment_start: datetime,
    from_address: str,
) -> EmailMessage:
    """Build the fixed, non-sensitive appointment confirmation message."""
    message = EmailMessage()
    message["Subject"] = EMAIL_SUBJECT
    message["From"] = from_address
    message["To"] = patient_email
    appointment_date = appointment_start.strftime("%A, %d %B %Y")
    appointment_time = _format_time(appointment_start)
    message.set_content(
        "Your appointment with BrightCare Clinic is confirmed for "
        f"{appointment_date} at {appointment_time}.\n\n"
        "Duration: 30 minutes\n"
        "Location: 12 Orchard Rd\n\n"
        "If you need to cancel, please message the clinic."
    )
    return message


@dataclass
class SmtpConfirmationEmailSender:
    """Send real confirmation messages through authenticated STARTTLS SMTP."""

    config: EmailConfig
    smtp_factory: Callable[..., Any] = smtplib.SMTP

    def send_confirmation(
        self,
        patient_email: str,
        appointment_start: datetime,
    ) -> None:
        message = build_confirmation_message(
            patient_email,
            appointment_start,
            self.config.from_address,
        )
        tls_context = ssl.create_default_context()
        with self.smtp_factory(
            self.config.smtp_host,
            self.config.smtp_port,
            timeout=30,
        ) as smtp:
            smtp.ehlo()
            smtp.starttls(context=tls_context)
            smtp.ehlo()
            smtp.login(
                self.config.smtp_username,
                self.config.smtp_password,
            )
            smtp.send_message(message)
