import unittest
from unittest.mock import MagicMock, patch

from ads_mcp.tools import experiments


class TestExperimentLifecycle(unittest.TestCase):
    def test_schedule_requires_explicit_confirmation(self):
        with self.assertRaisesRegex(ValueError, "confirm=true"):
            experiments.schedule_experiment("123", "customers/123/experiments/1")

    @patch("ads_mcp.utils.get_googleads_client")
    def test_schedule_calls_google_only_after_confirmation(self, get_client):
        client = MagicMock()
        service = MagicMock()
        client.get_service.return_value = service
        get_client.return_value = client
        result = experiments.schedule_experiment("123", "customers/123/experiments/1", confirm=True)
        service.schedule_experiment.assert_called_once_with(resource_name="customers/123/experiments/1")
        self.assertEqual(result["status"], "SCHEDULED")
