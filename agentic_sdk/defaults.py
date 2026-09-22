from __future__ import annotations

DEFAULT_WORKFLOW_NAME = "default"
DEFAULT_SESSION_ID = "default"

DEFAULT_RETRIEVED_CONTENT_KEY = "latest_retrieved_content"
DEFAULT_NO_MATCHING_ENTRIES_MESSAGE = "No matching entries."
DEFAULT_NO_RETRIEVED_CONTEXT_MESSAGE = "No matching memory or knowledge entries."

# What the person is told when one module could not do its job. Written for
# them, never for the developer — the exception goes in the entry metadata.
DEFAULT_MODULE_FAILURE_MESSAGES = {
    "perceive": "Unable to understand the input right now.",
    "plan": "Unable to plan the next step right now.",
    "retrieve": "Unable to look anything up right now.",
    "action": "Unable to produce an answer right now.",
    "reflect": "Unable to check the result right now.",
}

SEMANTIC_RETRIEVE_DEFAULT_TOP_K = 3
SEMANTIC_RETRIEVE_DEFAULT_SAVED_PATH = "./tmp"
SEMANTIC_RETRIEVE_DEFAULT_INDEX_DIRNAME = "vectorstore"
SEMANTIC_RETRIEVE_DEFAULT_SOURCE_DIRNAME = "source-files"