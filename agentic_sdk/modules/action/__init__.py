from agentic_sdk.modules.action.direct_answer import DirectAnswerAction
from agentic_sdk.modules.action.generative import GenerativeAction


class StructuredAction(GenerativeAction):
    pass


__all__ = ["DirectAnswerAction", "GenerativeAction", "StructuredAction"]