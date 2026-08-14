import unittest
from datetime import datetime
from unittest.mock import MagicMock, Mock
from zoneinfo import ZoneInfo

from email_sender import (
    EMAIL_SUBJECT,
    EmailConfig,
    SmtpConfirmationEmailSender,
    build_confirmation_message,
)


APPOINTMENT_START = datetime(
    2026,
    8,
    17,
    15,
    30,
    tzinfo=ZoneInfo("Asia/Kolkata"),
)


class EmailSenderTest(unittest.TestCase):
    def test_confirmation_message_contains_required_details(self):
        message = build_confirmation_message(
            "jane@example.com",
            APPOINTMENT_START,
            "clinic@example.com",
        )

        body = message.get_content()
        self.assertEqual(message["Subject"], EMAIL_SUBJECT)
        self.assertEqual(message["To"], "jane@example.com")
        self.assertIn("BrightCare Clinic", body)
        self.assertIn("Monday, 17 August 2026 at 3:30pm", body)
        self.assertIn("Duration: 30 minutes", body)
        self.assertIn("Location: 12 Orchard Rd", body)
        self.assertIn("please message the clinic", body)

    def test_sender_uses_authenticated_starttls_without_real_email(self):
        smtp = MagicMock()
        smtp_context = MagicMock()
        smtp_context.__enter__.return_value = smtp
        smtp_factory = Mock(return_value=smtp_context)
        config = EmailConfig(
            smtp_host="smtp.example.com",
            smtp_port=587,
            smtp_username="clinic@example.com",
            smtp_password="test-password",
            from_address="clinic@example.com",
        )
        sender = SmtpConfirmationEmailSender(
            config,
            smtp_factory=smtp_factory,
        )

        sender.send_confirmation("jane@example.com", APPOINTMENT_START)

        smtp_factory.assert_called_once_with(
            "smtp.example.com",
            587,
            timeout=30,
        )
        smtp.starttls.assert_called_once()
        smtp.login.assert_called_once_with(
            "clinic@example.com",
            "test-password",
        )
        smtp.send_message.assert_called_once()


if __name__ == "__main__":
    unittest.main()
