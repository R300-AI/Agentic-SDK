from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from agentic_sdk.config import Settings
from agentic_sdk.gateway.app import _healthcheck_openai_endpoint, create_app


class GatewayBootstrapTests(unittest.TestCase):
    def test_healthcheck_skips_placeholder_local_openai(self) -> None:
        settings = Settings()

        with patch("agentic_sdk.gateway.app.httpx.get") as http_get:
            result = _healthcheck_openai_endpoint(settings, object())

        http_get.assert_not_called()
        self.assertFalse(result["reachable"])
        self.assertIn("placeholder", str(result["error"]))

    def test_models_route_rejects_placeholder_local_openai(self) -> None:
        settings = Settings()
        app = create_app(settings)

        with TestClient(app) as client:
            response = client.get("/v1/models")

        self.assertEqual(response.status_code, 503)
        self.assertIn("upstream", response.json()["detail"])

    def test_lifespan_rebuilds_openai_client_after_keyvault_load(self) -> None:
        settings = Settings()

        def inject_keyvault_model(current_settings: Settings) -> None:
            current_settings.openai_api_base_url = "https://example.openai.test/v1"
            current_settings.openai_api_key = "kv-key"
            current_settings.openai_model = "kv-model"

        with patch("agentic_sdk.gateway.app.load_first_model_from_keyvault", side_effect=inject_keyvault_model):
            with patch("agentic_sdk.gateway.app._healthcheck_openai_endpoint", return_value={"reachable": False, "url": "https://example.openai.test/v1/models", "error": "skip"}):
                app = create_app(settings)
                with TestClient(app) as client:
                    self.assertEqual(str(client.app.state.openai_client.base_url), "https://example.openai.test/v1/")


if __name__ == "__main__":
    unittest.main()