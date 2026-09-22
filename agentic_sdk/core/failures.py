from __future__ import annotations


class EndpointUnavailable(RuntimeError):
    """The inference service would not answer at all.

    Raised by the layer that talks to the endpoint, so the rest of the SDK can
    tell this apart from a model that answered badly without having to know
    which provider it was talking to. The endpoint layer has already retried by
    the time this is raised.

    It lives in a module of its own, importing nothing, because both the core
    and the endpoint layer need to name it and the two already import each
    other by way of memory.
    """
