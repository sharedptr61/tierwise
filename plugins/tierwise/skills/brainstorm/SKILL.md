---
name: brainstorm
description: Turn an under-specified or high-risk (R3) request into an approved design before any planning or code. Use when the routing card names it, or when you cannot say what "done" means for the request.
---

# Brainstorm before building

Start by sorting what you know. If everything that matters is in the request, say so in one line and continue; do not interview the user for the sake of it.

1. **Look before you ask.** Read the code and project files first. Never ask what the repository already answers.
2. **First message.** If the request is detailed, restate it in a short paragraph with what you found. If not, ask one open question about the biggest unknown and say why it matters. Offer "or I can go ahead with my best reading".
3. **One question per message.** Prefer a concrete proposal over an open question once you know the user's goal. Keep what the user said apart from what you are proposing.
4. **Two or three approaches,** in a message of their own: trade-offs, your recommendation and why.
5. **Write the design** to `.tierwise/specs/<task-id>-<topic>.md`: intent, goals, non-goals, constraints, the approaches and the chosen one, decisions the user made, what is left to the planner. A small change gets a short design.
6. **Gate.** No code, scaffolding or installs until the user approves the design. A spike to try something is allowed if you label it throwaway; keeping its output goes through the gate again.
7. **Hand over.** Record the main decisions with `${CLAUDE_SKILL_DIR}/../../bin/state decision "..."`, then route to `tierwise:planner` with the design's path as the spec.

At R3, the design also lists what could go wrong (abuse, data loss, irreversible steps), so the planner's threat model starts from it.
