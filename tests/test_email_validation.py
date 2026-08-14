import unittest

from email_validation import normalize_email_address


class EmailValidationTest(unittest.TestCase):
    def test_valid_email_is_normalized(self):
        self.assertEqual(
            normalize_email_address("  Jane@Example.COM  "),
            "Jane@example.com",
        )

    def test_malformed_addresses_are_rejected(self):
        for value in ("john@", "john.gmail.com", "hello", "@gmail.com"):
            with self.subTest(value=value):
                self.assertIsNone(normalize_email_address(value))


if __name__ == "__main__":
    unittest.main()
