# Source review and clean-room boundary

This portfolio repository was created separately from the private Coral checkout. No files or Git history were copied wholesale. The implementation is newly written, small, and based on reviewed design concepts rather than importing the production modules.

| Private Coral Core source reviewed | Review finding | Public treatment |
| --- | --- | --- |
| `coral_core/database.py` | SQLite lifecycle and migration code is coupled to many private domain stores; its default path is local data. | No production file copied. Replaced with a small SQLite store using an injected path and two demo tables. |
| `coral_core/memory.py` | Durable memory behavior is useful, but the implementation is large and includes personal-memory concepts and production schema. | No production file copied. Replaced with one fictional memory record shape and a local table. |
| `coral_core/context.py` | Includes identity loading and prompt/context text with personal references. | Excluded. Replaced with a generic bounded context function and synthetic request. |
| `coral_core/turn_context.py` | Provides provenance, packet, and digest concepts but is coupled to broader production contracts. | No production file copied. Reimplemented a small character-bounded context and SHA-256 digest. |
| `coral_core/disclosure.py` | Central disclosure concepts are relevant; its compatibility defaults and production source registry are not suitable for this demo. | Reimplemented the strictest-class rule; unknown and missing classifications fail closed to local-only. |
| `coral_core/model_routing.py` | Production provider configuration and routing are coupled to real adapters, environment settings, and research storage. | Excluded. Replaced with metadata-only synthetic local/remote providers and deterministic eligibility selection. |
| `coral_core/operation_receipts.py` | Read-only receipt projection captures useful metadata-only audit ideas but depends on production receipt formats. | No production file copied. Reimplemented minimal durable SQLite receipts with references and digests only. |

The clean-room version contains no production database, identity or persona file, research result, log, private document, avatar/mobile code, third-party asset, credential, or live provider adapter. The demo's fictional team and schedule are invented solely for this example.
