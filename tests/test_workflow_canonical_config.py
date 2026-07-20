import unittest

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

        workflow = Workflow.from_config(
            config,
            module_overrides={
                "perceive": TextPerceive(client=FoundryOpenAILikeClient()),
                "plan": NextStepPlan(client=FoundryOpenAILikeClient(plan_sequence=["action"])),
                "action": GenerativeAction(client=FoundryOpenAILikeClient(action_text="ok")),
                "reflect": ResponseCheckReflect(client=FoundryOpenAILikeClient()),
            },
        )

        self.assertIsInstance(workflow.modules["perceive"], TextPerceive)
        self.assertIsInstance(workflow.modules["plan"], NextStepPlan)
        self.assertIsInstance(workflow.modules["retrieve"], HybridRetrieve)
        self.assertIsInstance(workflow.modules["action"], GenerativeAction)
        self.assertIsInstance(workflow.modules["reflect"], ResponseCheckReflect)

    def test_workflow_config_with_llm_modules_requires_explicit_client_injection(self) -> None:
        config = WorkflowConfig(
            modules={
                "perceive": ModuleSpec(type="TextPerceive"),
            }
        )

        with self.assertRaisesRegex(ValueError, "user-injected OpenAI client"):
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