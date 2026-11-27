# Review reference

- Every non-trivial diff is reviewed in a fresh context. A different model is added where the author's blind spots matter most: Fable's plan is reviewed by Opus (R2/R3); Opus-written R3 diffs are reviewed by Fable (principal).
- The reviewer is never weaker than the author and never shares the author's context. Give it the review package path and nothing else.
- No model reviews its own code. When the main session runs on Fable, the R3 code review goes to `tierwise:reviewer` (Opus) at xhigh instead of the principal; the gate reads the session's model from its transcript and requires that.
- A finding names a file, a line and a concrete failing scenario. Reviewers report correctness, security and requirement gaps, not style. A reviewer asked for gaps usually finds some; chasing all of them breeds over-engineering. Confirm each finding against the code before acting.
- After fixes, the checks run again and one review scoped to the fix follows.

## Handling findings (from Tierwise's reviewers, other tools or the user)

1. Read all of them first. If any is unclear, ask about all the unclear ones before changing anything; they may be related.
2. For each: restate what it asks, check it against the code, and decide whether it is right for this codebase.
3. Reply with the fix or the technical reason, never with thanks or "you're right". If a finding is wrong (breaks something, misses context, contradicts a recorded decision), push back with evidence: a test, a line of code, the decision in `.tierwise/decisions.md`. If you were wrong, say so in one line and fix it.
4. A request to add something "properly" or more generally: grep for real uses first. Unused means propose removing it instead.
5. Fix one finding at a time, blocking ones first, each with its test.
6. A finding that contradicts a decision the user made goes to the user, not into the code.
- The gate knows a review happened when a Tierwise reviewer, security-reviewer or principal delivers its report after the last change. For an exception (for example, the user reviewed it), record it: `state record-review code|security|principal`.
- The ledger records the model that actually ran each review. If a safety classifier re-ran it on an older Opus, the ledger notes it and the final report must say so.
- A model's review is not a human review. At R3 the system prepares the evidence and recommends that a person signs off.
