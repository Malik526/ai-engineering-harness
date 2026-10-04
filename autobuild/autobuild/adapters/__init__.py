"""Provider adapters — the only code that knows a concrete provider's CLI.

Each module implements autobuild.agent_provider.AgentProvider for one provider
and is referenced from providers/registry.yaml. Orchestration code never
imports this package directly.
"""
