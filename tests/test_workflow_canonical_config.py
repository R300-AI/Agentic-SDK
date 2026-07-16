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


class WorkflowCanonicalConfigTests(unittest.TestCase):
    def test_workflow_builds_from_canonical_node_names(self) -> None:
        config = WorkflowConfig(
            modules={
                "perceive": ModuleSpec(type="TextPerceive"),
                "plan": ModuleSpec(type="NextStepPlan"),
                "retrieve": ModuleSpec(type="HybridRetrieve"),
                "action": ModuleSpec(type="GenerativeAction"),
                "reflect": ModuleSpec(type="ResponseCheckReflect"),
            }
        )

        workflow = Workflow.from_config(config)

        self.assertIsInstance(workflow.modules["perceive"], TextPerceive)
        self.assertIsInstance(workflow.modules["plan"], NextStepPlan)
        self.assertIsInstance(workflow.modules["retrieve"], HybridRetrieve)
        self.assertIsInstance(workflow.modules["action"], GenerativeAction)
        self.assertIsInstance(workflow.modules["reflect"], ResponseCheckReflect)

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