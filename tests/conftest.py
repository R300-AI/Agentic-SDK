from __future__ import annotations

import os


# Test modules import the Flask app during collection, before fixtures can run.
# Keep their configuration deterministic and independent of developer Azure credentials.
os.environ.setdefault("PLAYGROUND_TEST_MODE", "true")