"""Development gateway for Playground V1.

This adapter keeps the legacy React playground runnable without putting Gateway
code back into the clean `agentic_sdk` core package.
"""

from playground_v1_gateway.app import create_app

__all__ = ["create_app"]