import os
import unittest
from unittest.mock import patch

from environment_config import (
    PROJECT_ENV_FILE,
    load_project_environment,
    required_environment_variable,
)


class EnvironmentConfigTest(unittest.TestCase):
    def setUp(self):
        load_project_environment.cache_clear()

    def tearDown(self):
        load_project_environment.cache_clear()

    def test_required_value_loads_project_env_once(self):
        with patch("environment_config.load_dotenv") as mocked_load_dotenv:
            with patch.dict(os.environ, {"TEST_SETTING": "configured"}, clear=True):
                self.assertEqual(
                    required_environment_variable("TEST_SETTING"), "configured"
                )
                self.assertEqual(
                    required_environment_variable("TEST_SETTING"), "configured"
                )

        mocked_load_dotenv.assert_called_once_with(
            dotenv_path=PROJECT_ENV_FILE,
            override=False,
        )

    def test_missing_required_value_raises_clear_error(self):
        with patch("environment_config.load_dotenv"):
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaisesRegex(
                    ValueError,
                    "Missing required environment variable: TEST_SETTING",
                ):
                    required_environment_variable("TEST_SETTING")


if __name__ == "__main__":
    unittest.main()
