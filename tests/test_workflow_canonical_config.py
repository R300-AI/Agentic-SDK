from __future__ import annotations

import unittest
from unittest.mock import patch

from agentic_sdk import (
    EvidenceCheckReflect,
    GenerativeAction,
    ModuleSpec,
    NextStepPlan,
    PassThroughPerceive,
    ResponseCheckReflect,
    SemanticRetrieve,
    TextPerceive,
    WorkflowConfig,
    build_workflow,
)

from support import FoundryOpenAILikeClient


TEST_MODEL = "foundry-openai-like"
TEST_API_KEY = "test-key"
TEST_BASE_URL = "https://example.openai.test/v1"


def _llm_params() -> dict[str, str]:
    return {"api_key": TEST_API_KEY, "base_url": TEST_BASE_URL, "model": TEST_MODEL}


class WorkflowCanonicalConfigTests(unittest.TestCase):
    def test_workflow_builds_from_clean_core_config_with_overrides(self) -> None:
        config = WorkflowConfig(
            description="從標準 config 建立 workflow。",
            modules={
                "perceive": ModuleSpec(kind="text"),
                "plan": ModuleSpec(kind="next_step"),
                "retrieve": ModuleSpec(kind="semantic"),
                "action": ModuleSpec(kind="generative"),
                "reflect": ModuleSpec(kind="response_check"),
            }
        )

        with patch(
            "agentic_sdk.llm.openai_compatible.OpenAI",
            side_effect=[
                FoundryOpenAILikeClient(),
                FoundryOpenAILikeClient(plan_sequence=["action"]),
                FoundryOpenAILikeClient(action_text="ok"),
                FoundryOpenAILikeClient(),
            ],
        ):
            workflow = build_workflow(
                config,
                module_overrides={
                    "perceive": TextPerceive(**_llm_params()),
                    "plan": NextStepPlan(**_llm_params()),
                    "action": GenerativeAction(**_llm_params()),
                    "reflect": ResponseCheckReflect(**_llm_params()),
                },
            )

        self.assertIsInstance(workflow.modules["perceive"], TextPerceive)
        self.assertIsInstance(workflow.modules["plan"], NextStepPlan)
        self.assertIsInstance(workflow.modules["retrieve"], SemanticRetrieve)
        self.assertIsInstance(workflow.modules["action"], GenerativeAction)
        self.assertIsInstance(workflow.modules["reflect"], ResponseCheckReflect)
        self.assertEqual("從標準 config 建立 workflow。", workflow.description)

    def test_workflow_config_with_llm_modules_requires_explicit_model_configuration(self) -> None:
        config = WorkflowConfig(modules={"perceive": ModuleSpec(kind="text")})

        with self.assertRaisesRegex(ValueError, "explicit model"):
            build_workflow(config)

    def test_top_level_exports_expose_canonical_names(self) -> None:
        self.assertTrue(issubclass(PassThroughPerceive, object))
        self.assertTrue(issubclass(TextPerceive, object))
        self.assertTrue(issubclass(NextStepPlan, object))
        self.assertTrue(issubclass(SemanticRetrieve, object))
        self.assertTrue(issubclass(GenerativeAction, object))
        self.assertTrue(issubclass(ResponseCheckReflect, object))
        self.assertTrue(issubclass(EvidenceCheckReflect, object))


if __name__ == "__main__":
    unittest.main()