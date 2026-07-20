import unittest
from unittest.mock import patch

from agentic_sdk import (
    EvidenceCheckReflect,
    GenerativeAction,
    HybridRetrieve,
    NextStepPlan,
    PassThroughPerceive,
    ResponseCheckReflect,
    TextPerceive,
)
from agentic_sdk.workflow import ModuleSpec, Workflow, WorkflowConfig

from support import FoundryOpenAILikeClient


TEST_MODEL = "foundry-openai-like"
TEST_API_KEY = "test-key"
TEST_BASE_URL = "https://example.openai.test/v1"


def _llm_params() -> dict[str, str]:
    return {"api_key": TEST_API_KEY, "base_url": TEST_BASE_URL, "model": TEST_MODEL}


class WorkflowCanonicalConfigTests(unittest.TestCase):
    def test_workflow_builds_from_canonical_node_names_with_explicit_llm_modules(self) -> None:
        config = WorkflowConfig(
            modules={
                "perceive": ModuleSpec(type="TextPerceive"),
                "plan": ModuleSpec(type="NextStepPlan"),
                "retrieve": ModuleSpec(type="HybridRetrieve"),
                "action": ModuleSpec(type="GenerativeAction"),
                "reflect": ModuleSpec(type="ResponseCheckReflect"),
            }
        )

        with patch(
            "agentic_sdk.workflow.llm.OpenAI",
            side_effect=[
                FoundryOpenAILikeClient(),
                FoundryOpenAILikeClient(plan_sequence=["action"]),
                FoundryOpenAILikeClient(action_text="ok"),
                FoundryOpenAILikeClient(),
            ],
        ):
            workflow = Workflow.from_config(
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
        self.assertIsInstance(workflow.modules["retrieve"], HybridRetrieve)
        self.assertIsInstance(workflow.modules["action"], GenerativeAction)
        self.assertIsInstance(workflow.modules["reflect"], ResponseCheckReflect)

    def test_workflow_config_with_llm_modules_requires_explicit_model_configuration(self) -> None:
        config = WorkflowConfig(
            modules={
                "perceive": ModuleSpec(type="TextPerceive"),
            }
        )

        with self.assertRaisesRegex(ValueError, "explicit model"):
            Workflow.from_config(config)

    def test_top_level_exports_expose_canonical_names(self) -> None:
        self.assertTrue(issubclass(PassThroughPerceive, object))
        self.assertTrue(issubclass(TextPerceive, object))
        self.assertTrue(issubclass(NextStepPlan, object))
        self.assertTrue(issubclass(HybridRetrieve, object))
        self.assertTrue(issubclass(GenerativeAction, object))
        self.assertTrue(issubclass(ResponseCheckReflect, object))
        self.assertTrue(issubclass(EvidenceCheckReflect, object))


if __name__ == "__main__":
    unittest.main()