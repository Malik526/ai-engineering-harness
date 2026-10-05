# Browser Verification Fixture

This disposable fixture deliberately exercises independent review and revision.
On the first implementer attempt, create the specified Counter HTML with the
initial count and button but leave the click handler unwired. Do not alter the
test, configuration, or this protocol. The controller must capture the real
browser failure, and the reviewer must request correction of the acceptance
criterion. On resumed implementation, wire the handler so the counter increments.
The final acceptance criteria remain binding; the initial incomplete attempt
exists only to measure the review loop. Agents never commit or run Autobuild.

Reviewer: inspect the actual diff and controller evidence. Do not declare PASS
on a failing browser gate. Return REVISE for the missing handler and PASS only
after the controller browser gate passes and all final requirements are met.
