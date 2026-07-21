from __future__ import annotations

import importlib.util
import unittest
from unittest.mock import patch

from agentic_sdk.core import WorkflowState
from agentic_sdk.modules import GenerativeAction

from support import FoundryOpenAILikeClient


class CleanCoreBootstrapTests(unittest.TestCase):
    def test_gateway_is_not_part_of_core_sdk(self) -> None:
        self.assertIsNone(importlib.util.find_spec("agentic_sdk.gateway"))

    def test_capabilities_registry_is_not_part_of_core_sdk(self) -> None:
        self.assertIsNone(importlib.util.find_spec("agentic_sdk.capabilities"))

    def test_request_model_is_bound_explicitly_on_llm_module(self) -> None:
        client = FoundryOpenAILikeClient(action_text="ok")
        with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client) as openai_cls:
            action = GenerativeAction(
                api_key="gateway-key",
                base_url="https://example.openai.test/v1",
                model="request-model",
            )
            output = action(WorkflowState(user_message="hello"))

        openai_cls.assert_called_once_with(api_key="gateway-key", base_url="https://example.openai.test/v1")
        self.assertEqual("request-model", action.gen_ai_request_model)
        self.assertIsNone(output["next_module"])
        self.assertEqual("request-model", client.last_create_kwargs["model"])


if __name__ == "__main__":
    unittest.main()