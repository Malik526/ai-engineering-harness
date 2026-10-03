<!--
Notification body rendered by autobuild/notification_format.py with Python
string.Template ($name / ${name}). This comment is stripped before rendering.
Fields come from notification.schema.json; see docs/NOTIFICATION_CONTRACT.md.
-->
${project} Autonomous Build — ${implementation_id} ${status}

STATUS
${status}

IMPLEMENTATION
${implementation_title}

WHAT CHANGED
${summary}

VALIDATION
${validation}

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
