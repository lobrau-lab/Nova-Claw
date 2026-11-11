---
name: static-decision-router
description: Creates, manages, and expands deterministic if-condition routing trees and fast decision tables for static, unchanging rules and established project decisions.
---
# Static Decision Router (Token-Saving Logic Engine)

1. **Deterministic Bypass First**: If an answer or behavior is static and locked, route it immediately through an `if` statement or lookup dictionary (`core/static_router.py`). Never send a query to an LLM if a rule handles it.
2. **Zero Ingestion Cost**: Pre-compiled regex patterns, normalized string matching, and direct key lookups execute in microseconds and consume 0 LLM prompt/completion tokens.
3. **Continuous Extension**: When a decision is finalized during conversation, register the condition and response into the persistent rule registry via `manage_static_rules`.
