# Demo scenarios

All memories are fictional and live in `src/coral_portfolio/demo.py`.

| Memory | Label |
|---|---|
| The team reviews its launch checklist every Thursday at 10am. | `cloud_allowed` |
| The team orders packaging from Northwind Supply. | `cloud_allowed` |
| The team lead is negotiating a raise and wants that kept private. | `local_only` |
| The quarterly review moved to the last Friday of the month. | *(never labeled)* |

| Command | What happens |
|---|---|
| `coral-demo --prefer cloud --ask "Who supplies our packaging?"` | Only the public memory is retrieved, so the preferred cloud route is allowed. |
| `coral-demo --prefer cloud --ask "Is the team lead negotiating a raise?"` | The private memory is retrieved, so the request is forced local. |
| `coral-demo --ask "When is the quarterly review?"` | The unlabeled memory is treated as private, so the request stays local. |
| `coral-demo --no-local --ask "Is the team lead negotiating a raise?"` | Nothing is eligible, so the request is denied, no model is called, and a receipt is still written. |
| `coral-demo --ask "What's the weather?"` | No memory is relevant, so nothing private enters the context. |
