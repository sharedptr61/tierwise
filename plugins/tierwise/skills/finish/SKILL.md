---
name: finish
description: Decide how finished work on a branch is integrated - merge locally, push and open a pull request, or keep it - after the checks pass. Use at the end of a task whose work is on its own branch or worktree.
---

# Finish a branch

1. **Green first.** Run the full test command. If anything fails, show the failures and stop here.
2. **Where am I?** `git rev-parse --git-dir` and `--git-common-dir` differ inside a linked worktree; note its path now. On a detached HEAD there is no local merge.
3. **Confirm the base branch** with the user ("this branched from main, correct?").
4. **Offer exactly these, and wait for the choice:**
   1. Merge into the base branch locally.
   2. Push the branch and open a pull request.
   3. Keep the branch as it is.

   Never offer to discard work. Discard only if the user asks, and only after they type the word `discard`.
5. **Merge:** from the main checkout, update the base branch, merge, and run the tests on the merged result. If they fail, stop and leave everything in place. If they pass, remove the worktree (only one Tierwise or the native worktree tool created) and delete the branch with `git branch -d`.
6. **Pull request:** `git push -u origin <branch>`, then open the request with the forge's CLI or give the user its URL. Keep the worktree.
7. **Keep:** say where the branch and worktree are.

Never use `--force` to remove a worktree or to push. If git refuses to remove a worktree (uncommitted files), show the files and let the user decide.
