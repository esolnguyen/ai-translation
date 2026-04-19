"""Use-case layer — application logic.

Depends only on ``rag.domain`` and ``collections.abc``/stdlib. Defines the
ports (``use_cases.ports``) that adapters must implement; never imports any
adapter directly.
"""

from __future__ import annotations
