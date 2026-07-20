from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from agentic_sdk.config import Settings
from agentic_sdk.gateway.app import _healthcheck_openai_endpoint, create_app
from agentic_sdk.gateway.routes_chat import _build_action
from agentic_sdk.workflow import WorkflowState

from support import FoundryOpenAILikeClient


class GatewayBootstrapTests(unittest.TestCase):
    def test_settings_do_not_expose_global_model_default(self) -> None:
        self.assertNotIn("openai_model", Settings.model_fields)

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

        with patch("agentic_sdk.gateway.app.load_first_model_from_keyvault", side_effect=inject_keyvault_model):
            with patch("agentic_sdk.gateway.app._healthcheck_openai_endpoint", return_value={"reachable": False, "url": "https://example.openai.test/v1/models", "error": "skip"}):
                app = create_app(settings)
                with TestClient(app) as client:
                    self.assertEqual(str(client.app.state.openai_client.base_url), "https://example.openai.test/v1/")

    def test_gateway_request_model_is_bound_to_client_not_module(self) -> None:
        client = FoundryOpenAILikeClient(action_text="ok")
        settings = Settings()
        settings.openai_api_key = "gateway-key"
        settings.openai_api_base_url = "https://example.openai.test/v1"
        with patch("agentic_sdk.workflow.llm.OpenAI", return_value=client) as openai_cls:
            action = _build_action(settings, "request-model")

            output = action(WorkflowState(user_message="hello"))

        openai_cls.assert_called_once_with(api_key="gateway-key", base_url="https://example.openai.test/v1")
        self.assertEqual("request-model", action.gen_ai_request_model)
        self.assertIsNone(output["next_module"])
        self.assertEqual("request-model", client.last_create_kwargs["model"])


if __name__ == "__main__":
    unittest.main()