# Synthetic workflow example

All values below are fictional and are also used by `src/coral_portfolio/demo.py`.

- Stored local memory: “The example team reviews its launch checklist every Thursday.”
- User request: “When does the example team review its launch checklist?”
- Context assembly: includes the request and retrieved memory, subject to a character budget.
- Disclosure check: `cloud_allowed` permits either configured route; `local_only` permits only local.
- Route: provider metadata selects an eligible route. The demo does not invoke either provider.
- Receipt: SQLite stores the selected provider, disclosure class, policy version, source reference, and context digest. It does not store the request, memory text, or model output.
