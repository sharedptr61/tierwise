#!/usr/bin/env python3
"""Draw the Tierwise routing flowchart (docs/assets/flow-light.svg and flow-dark.svg).

  python3 docs/assets/make_flowchart.py

Every branch follows the plugin's own rules: bin/mlib/route.py (classes, risk tiers, plan, agents, checks),
bin/mlib/flow.py (the gate and the debugging ladder) and bin/mlib/guard.py (what every agent start must pass).
Standard library only.
"""
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"

THEMES = {
    "light": {"bg": "#ffffff", "card": "#f6f8fa", "line": "#d0d7de", "fg": "#1f2328", "muted": "#59636e",
              "arrow": "#8c959f", "accent": "#257de0", "ok": "#1a7f37", "bad": "#cf222e",
              "fable": ("#1757ac", "#ffffff"), "opus": ("#257de0", "#ffffff"), "sonnet": ("#84b9f3", "#0b1f3a"),
              "haiku": ("#cce3fd", "#0b1f3a"),
              "tiers": [("#eaeef2", "#1f2328"), ("#ddf4ff", "#0a3069"), ("#fff1c2", "#4d2d00"), ("#ffebe9", "#82071e")]},
    "dark": {"bg": "#0d1117", "card": "#161b22", "line": "#30363d", "fg": "#e6edf3", "muted": "#9198a1",
             "arrow": "#6e7681", "accent": "#4493f8", "ok": "#3fb950", "bad": "#f85149",
             "fable": ("#1b64be", "#ffffff"), "opus": ("#338ced", "#ffffff"), "sonnet": ("#6aabf1", "#0b1f3a"),
             "haiku": ("#b6d5f8", "#0b1f3a"),
             "tiers": [("#2d333b", "#e6edf3"), ("#0c2d6b", "#cae8ff"), ("#4b3a00", "#f8e3a1"), ("#5d0f12", "#ffdcd7")]},
}
W, H = 1200, 1330


class Svg:
    def __init__(self, t):
        self.t, self.p = t, []

    def text(self, x, y, s, size=14, fill=None, weight=400, anchor="start"):
        self.p.append(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FONT}" font-size="{size}" font-weight="{weight}" '
                      f'fill="{fill or self.t["fg"]}" text-anchor="{anchor}">{escape(s)}</text>')

    def rect(self, x, y, w, h, fill, stroke=None, r=10, dash=False):
        extra = f' stroke="{stroke}" stroke-width="1.5"' if stroke else ""
        extra += ' stroke-dasharray="5 4"' if dash else ""
        self.p.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="{r}" fill="{fill}"{extra}/>')

    def arrow(self, pts, label=None, color=None, lx=None, ly=None):
        d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        c = color or self.t["arrow"]
        self.p.append(f'<path d="{d}" fill="none" stroke="{c}" stroke-width="2" marker-end="url(#ah-{c[1:]})"/>')
        if label:
            self.text(lx, ly, label, 12.5, c, 600)

    def chip(self, x, y, model, label):
        bg, fg = self.t[model]
        w = 6.9 * len(label) + 22
        self.rect(x, y, w, 24, bg, r=12)
        self.text(x + w / 2, y + 16.5, label, 12.5, fg, 600, "middle")
        return x + w + 8

    @staticmethod
    def node_height(lines, chips):
        rows = (1 + sum(1 for _, label in chips if label == "\n")) if chips else 0
        return 26 + 8 + 19 * len(lines) + (rows * 32 + 4 if rows else 0) + 14

    def node(self, x, y, w, step, title, lines=(), chips=(), dash=False, h=None):
        """Draw a card sized to its content (or at least h); return its bottom edge."""
        t = self.t
        h = max(h or 0, self.node_height(lines, chips))
        self.rect(x, y, w, h, t["card"], t["line"], dash=dash)
        ty = y + 26
        if step:
            self.text(x + 18, ty, step, 12, t["accent"], 700)
            self.text(x + 18 + 8.2 * len(step) + 6, ty, title, 15.5, weight=700)
        else:
            self.text(x + 18, ty, title, 15.5, weight=700)
        ly = ty + 22
        for line in lines:
            self.text(x + 18, ly, line, 13, t["muted"])
            ly += 19
        cx, cy = x + 18, ly + 2
        for model, label in chips:
            if label == "\n":
                cx, cy = x + 18, cy + 32
                continue
            cx = self.chip(cx, cy, model, label)
        return y + h

    def render(self, title):
        markers = "".join(
            f'<marker id="ah-{c[1:]}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
            f'<path d="M0,0 L10,5 L0,10 z" fill="{c}"/></marker>'
            for c in {self.t["arrow"], self.t["ok"], self.t["bad"]})
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
                f'aria-label="{escape(title)}"><title>{escape(title)}</title><defs>{markers}</defs>'
                f'<rect width="100%" height="100%" rx="12" fill="{self.t["bg"]}"/>' + "".join(self.p) + "</svg>\n")


def draw(theme):
    t = THEMES[theme]
    s = Svg(t)
    # Title and legend
    s.text(48, 56, "How Tierwise routes a task", 24, weight=700)
    s.text(48, 82, "Your main session stays on Opus. Every other step goes to an agent with a pinned model and effort.", 14, t["muted"])
    lx = 48
    s.text(lx, 116, "Models:", 13, t["muted"], 600)
    lx += 62
    for model, label in (("fable", "Fable"), ("opus", "Opus"), ("sonnet", "Sonnet"), ("haiku", "Haiku")):
        lx = s.chip(lx, 100, model, label)
    s.text(lx + 4, 116, "darker = stronger model", 13, t["muted"])

    cx = W / 2
    # Prompt
    s.rect(cx - 90, 140, 180, 40, t["accent"], r=20)
    s.text(cx, 166, "Your prompt", 15, "#ffffff", 700, "middle")
    s.arrow([(cx, 180), (cx, 204)])
    # 1 Classify
    y = s.node(150, 206, 900, "1", "Classify the task",
               ["Rules read the prompt and the files it names: question · trivial edit · local fix · feature · bulk ·",
                "investigation · high-risk. A model is asked only when the rules are unsure."],
               [("haiku", "Haiku: tie-break label only")])
    s.arrow([(cx, y), (cx, y + 24)])
    # 2 Risk tier
    y += 26
    s.rect(150, y, 900, 112, t["card"], t["line"])
    s.text(168, y + 26, "2", 12, t["accent"], 700)
    s.text(182, y + 26, "Rate the risk", 15.5, weight=700)
    s.text(300, y + 26, "from the paths and words in the prompt; it can rise during a task, never fall", 13, t["muted"])
    tiers = [("R0", "docs and tests", "no review needed"), ("R1", "everyday code", "Opus review"),
             ("R2", "shared code, APIs, deps", "+ security review"), ("R3", "auth, secrets, payments,", "migrations, infra")]
    bx = 168
    for i, (tier, d1, d2) in enumerate(tiers):
        bg, fg = t["tiers"][i]
        s.rect(bx, y + 42, 208, 56, bg, r=8)
        s.text(bx + 12, y + 64, tier, 15, fg, 800)
        s.text(bx + 46, y + 64, d1, 12.5, fg)
        s.text(bx + 46, y + 84, d2, 12.5, fg)
        bx += 218
    y += 112
    # Three lanes
    split, lanes = y + 22, y + 52
    s.arrow([(cx, y), (cx, split), (210, split), (210, lanes - 2)])
    s.arrow([(cx, split), (600, lanes - 2)])
    s.arrow([(cx, split), (990, split), (990, lanes - 2)])
    lane_h = Svg.node_height(["a", "b"], [("opus", "x")])
    s.node(48, lanes, 324, "", "Question", ["A scout looks things up; the main", "session answers. No code changes."],
           [("haiku", "Scout: Haiku"), ("opus", "Answer: Opus")], h=lane_h)
    s.node(392, lanes, 416, "", "Trivial edit · local fix",
           ["The main session edits directly, test first;", "local fixes find the root cause before changing code."],
           [("opus", "Main session: Opus"), ("haiku", "Scout: Haiku")], h=lane_h)
    s.node(828, lanes, 324, "3", "Plan first",
           ["Feature · bulk · investigation · high-risk.", "At R2 and above the plan is reviewed."],
           [("fable", "Planner: Fable"), ("opus", "Plan review: Opus")], h=lane_h)
    lane_bottom = lanes + lane_h
    s.arrow([(990, lane_bottom), (990, lane_bottom + 26)])
    build_bottom = s.node(828, lane_bottom + 28, 324, "4", "Build in units",
                          ["Independent units in parallel worktrees;", "high-risk core logic never below Opus."],
                          [("sonnet", "Builders: Sonnet"), ("\n", "\n"), ("haiku", "Mechanical bulk at R0–R1: Haiku"),
                           ("\n", "\n"), ("opus", "R3 core logic: Opus")])
    # Converge on the gate
    gate = build_bottom + 46
    s.arrow([(600, lane_bottom), (600, gate - 2)])
    s.arrow([(990, build_bottom), (990, build_bottom + 22), (720, build_bottom + 22), (720, gate - 2)])
    gate_bottom = s.node(392, gate, 416, "5", "Verify before it can finish",
                         ["Syntax · secret scan · your tests · type checks;", "static analysis at R2+, threat model at R3."])
    gate_mid = gate + (gate_bottom - gate) / 2
    # Pass -> reviews -> done
    rev = gate_bottom + 46
    s.arrow([(520, gate_bottom), (520, rev - 2)], "checks pass", t["ok"], 532, gate_bottom + 28)
    rev_bottom = s.node(48, rev, 680, "6", "Review by risk tier",
                        ["Fresh-context reviewers see the diff and the spec, never the author's reasoning."],
                        [("opus", "R1: Reviewer, Opus"), ("\n", "\n"), ("opus", "R2: Reviewer, Opus"),
                         ("opus", "Security reviewer, Opus"), ("\n", "\n"), ("opus", "R3: Security reviewer, Opus"),
                         ("fable", "Principal review, Fable")])
    s.arrow([(388, rev_bottom), (388, rev_bottom + 26)])
    s.rect(248, rev_bottom + 28, 280, 44, t["accent"], r=22)
    s.text(388, rev_bottom + 56, "Done · ledger and savings", 15, "#ffffff", 700, "middle")
    # Fail -> ladder
    s.arrow([(808, gate_mid), (850, gate_mid), (850, rev - 2)], "checks fail", t["bad"], 860, gate_mid + 30)
    s.rect(748, rev, 404, 224, t["card"], t["bad"], dash=True)
    s.text(766, rev + 26, "Debugging ladder", 15.5, weight=700)
    s.text(766, rev + 46, "climbs only when the same failure repeats", 12.5, t["muted"])
    rungs = [("1", "opus", "Retry, effort high"), ("2", "opus", "Debugger, fresh context"), ("3", "fable", "Principal"),
             ("4", "fable", "Principal, maximum effort")]
    ry = rev + 58
    for n, model, label in rungs:
        s.text(770, ry + 17, n, 13, t["muted"], 700)
        s.chip(790, ry, model, f"{label}: {model.capitalize()}")
        ry += 32
    s.text(770, ry + 17, "5", 13, t["muted"], 700)
    s.text(790, ry + 17, "Stop and ask you, with the diagnosis", 13, weight=600)
    s.arrow([(1152, rev + 112), (1176, rev + 112), (1176, gate_mid), (808, gate_mid)], None, t["arrow"])
    s.text(1170, gate_mid - 10, "fix, verify again", 12, t["muted"], 600, "end")
    end = max(rev_bottom + 72, rev + 224)
    global H
    H = end + 96
    # Guard band
    s.rect(48, end + 26, 1104, 46, t["card"], t["line"])
    s.text(66, end + 55, "Guard on every agent start:", 13.5, t["accent"], 700)
    s.text(258, end + 55, "the right model and effort · Haiku never judges · nothing below Opus at R3 · caps on Fable escalations · "
                      "a per-task budget", 13, t["muted"])
    return s.render("How Tierwise routes a task: classify, rate the risk, plan, build, verify, review, and the debugging ladder")


def main():
    for theme in THEMES:
        with open(os.path.join(HERE, f"flow-{theme}.svg"), "w") as f:
            f.write(draw(theme))
    print("wrote flow-light.svg, flow-dark.svg")


if __name__ == "__main__":
    main()
