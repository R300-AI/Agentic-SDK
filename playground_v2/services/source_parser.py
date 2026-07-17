from __future__ import annotations

import ast
from dataclasses import dataclass


@dataclass(frozen=True)
class ParsedWorkflowSource:
    workflow_name: str
    profile_hint: str | None
    supported_subset: bool


def detect_source_origin(python_source: str) -> str:
    if "WorkflowSettings" in python_source and "Workflow" in python_source:
        return "agentic_sdk_python"
    if "from agentic_sdk" in python_source and "Workflow(" in python_source:
        return "agentic_sdk_python"
    return "unknown"


def parse_supported_source(python_source: str) -> ParsedWorkflowSource:
    try:
        tree = ast.parse(python_source)
    except SyntaxError:
        return ParsedWorkflowSource("Untitled Agent", None, False)

    workflow_name = "Untitled Agent"
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node.func) == "WorkflowSettings":
            for keyword in node.keywords:
                if keyword.arg == "name" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    workflow_name = keyword.value.value
        if isinstance(node, ast.Call) and _call_name(node.func) == "Workflow":
            for keyword in node.keywords:
                if keyword.arg == "workflow_name" and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                    workflow_name = keyword.value.value

    return ParsedWorkflowSource(
        workflow_name=workflow_name,
        profile_hint=_profile_hint(python_source),
        supported_subset=detect_source_origin(python_source) == "agentic_sdk_python" and workflow_name != "Untitled Agent",
    )


def _call_name(func: ast.expr) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _profile_hint(python_source: str) -> str | None:
    prefix = "# Playground V2 profile hint:"
    for line in python_source.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return None