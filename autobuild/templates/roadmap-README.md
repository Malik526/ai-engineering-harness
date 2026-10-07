# Implementation Roadmap

This directory holds human-approved implementation briefs for Autobuild. The
project's narrative roadmap and current state remain in their existing project
documents; this index only tracks executable implementation units.

## Layout

```text
README.md
<milestone>/
  <implementation-id>-<short-name>.md
```

Create briefs from the installed Autobuild
`templates/implementation-brief.md`. A planner discusses and refines the work
with the user first, then writes a `status: ready` brief only after explicit
approval. When the project requires a clean Git tree for Autobuild, review and
commit the approved roadmap changes before running `autobuild run --dry-run`.
The planner does not commit or start the run automatically.

## Implementations

No approved Autobuild briefs yet.
