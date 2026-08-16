"""SIDRA AI - self-hosted, local-first AI platform for SIDRA STUDIO.

v0.1 scope: safe local AI foundation + GitHub read-only ingestion.

Hard invariants for this version:

* GitHub access is read-only. No write/mutation capability exists in this
  package (see ``sidra_ai.ingestion.github_client``).
* All ingested repository/web content is untrusted DATA and never an
  instruction authority (see ``sidra_ai.security``).
* No paid external LLM API is a required dependency
  (see ``sidra_ai.models``).
* The private API binds to localhost by default
  (see ``sidra_ai.config.settings``).
"""

__version__ = "0.1.0"

__all__ = ["__version__"]
