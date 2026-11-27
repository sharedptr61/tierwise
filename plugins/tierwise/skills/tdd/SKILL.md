---
name: tdd
description: Test-first development for any change to behaviour - a feature, a bug fix, a refactor. Use before writing implementation code. Covers the failing-test-first cycle, what makes a test worth having, and what to report.
---

# Test first

**Rule: no production code without a test that failed first, for the reason you expected.** If you wrote code before its test, set it aside and start from the test; do not keep it "as a reference" and test around it. Exceptions (a throwaway spike, generated code, pure configuration) need the user's say-so.

## The cycle

1. **Red.** Write one small test for one behaviour, named for that behaviour. Use real code; mock only what is slow or outside your control.
2. **Watch it fail.** Run it. It must *fail* (an assertion), not *error* (a typo, an import), and the message must be the one you predicted. A test that passes at once tests nothing new: fix the test.
3. **Green.** Write the least code that makes it pass. No extras for later.
4. **Run the whole suite,** not just your file. Name any failure you see, even one you did not cause.
5. **Refactor** only while green, and run the suite again.

**Bugs:** first write a test that reproduces the bug and fails. Prove it with `${CLAUDE_SKILL_DIR}/../../bin/red-green --cmd "<test command>" --tests <test file>`: the test must fail on the task's base and pass on your change.

## A test worth having

- Before writing it, name the production change that would make it fail. If none would, do not write it.
- Work out expected values by hand, never by calling the code under test.
- Do not assert constants, wording or the mock itself; those break on harmless edits and catch no bugs.
- Mock only the slow or external layer, and give mocks the real data shapes.
- Never add a method to production code only so a test can call it.
- Finally, imagine breaking the code (flip a condition, drop a line): some test must fail.

## Report

State the red evidence (the test, and the failure message it gave) and the green evidence (the suite command and its result). The completion gate re-runs the checks; your report says what you saw.
