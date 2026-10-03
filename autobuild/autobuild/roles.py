"""The engineering roles autobuild coordinates. Roles are fixed; which provider
fills each one is configuration (see provider_registry.py)."""

PLANNER = "planner"
IMPLEMENTER = "implementer"
REVIEWER = "reviewer"

ROLES: tuple[str, ...] = (PLANNER, IMPLEMENTER, REVIEWER)
