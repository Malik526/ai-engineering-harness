<!--
Notification body rendered by autobuild/notification_format.py with Python
string.Template ($name / ${name}). This comment is stripped before rendering.
Fields come from notification.schema.json; see docs/NOTIFICATION_CONTRACT.md.
-->
${project} Autobuild — ${implementation_id} ${event_title}

STATUS
${status}${stop_reason}

IMPLEMENTATION
${implementation_title}

WHAT CHANGED
${summary}

PROVIDERS
Implementer: ${implementer}
Reviewer: ${reviewer}
Attempts: ${attempts}; review cycles: ${cycles}; rollovers: ${rollovers}

VALIDATION
${validation}

BROWSER
${browser}

REVIEW
${review}

FIXES DURING REVIEW
${fixes}

GIT
Branch: ${branch}
Commit: ${commit}

NEXT
${next_step}

HUMAN ACTION
${human_action}

PROTECTED BRANCHES
${protected}
