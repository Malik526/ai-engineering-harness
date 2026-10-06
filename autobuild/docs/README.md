# Autobuild Documentation

Start with [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md), then
[operations/RUNNER.md](operations/RUNNER.md) to run it.

| Folder | What lives there | Documents |
| --- | --- | --- |
| [architecture/](architecture/) | How the system is built: roles, run flow, states, phases, providers | [ARCHITECTURE.md](architecture/ARCHITECTURE.md), [PROVIDERS.md](architecture/PROVIDERS.md) |
| [operations/](operations/) | How to run and configure it: `autobuild run/resume/stop/evidence`, governance, rollover, browser gates | [RUNNER.md](operations/RUNNER.md), [BROWSER_GATES.md](operations/BROWSER_GATES.md) |
| [contracts/](contracts/) | Interfaces other parts rely on: run artifacts, remote stop, notifications | [ARTIFACT_CONTRACT.md](contracts/ARTIFACT_CONTRACT.md), [CONTROL_CONTRACT.md](contracts/CONTROL_CONTRACT.md), [NOTIFICATION_CONTRACT.md](contracts/NOTIFICATION_CONTRACT.md) |
| [safety/](safety/) | Trust boundaries and the rules the controller enforces | [SAFETY_MODEL.md](safety/SAFETY_MODEL.md), [AUTONOMY_POLICY.md](safety/AUTONOMY_POLICY.md), [VALIDATION_CONFINEMENT.md](safety/VALIDATION_CONFINEMENT.md) |
| [evaluations/](evaluations/) | Measured results per milestone, including live runs and known limits | `EVALUATION_0_<n>.md` |
| [decisions/](decisions/) | Architecture decision records (ADRs), numbered | `NNNN-<title>.md` |

New documents go into one of these folders; `tests/test_docs_consistency.py`
fails if a document is added at this level or a relative link breaks.
