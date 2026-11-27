#!/usr/bin/env python3
"""Draw the README charts from the measured evaluation data.

  python3 docs/assets/make_charts.py        # reads evals/workflow-arms/evaluation.json, writes docs/assets/*.svg

Every figure is computed from evaluation.json with the same rounding as docs/evaluation.md: per-job cost to the
cent, minutes to a tenth, the per-user savings to the cent and whole minutes, and scaled figures as the per-user
figure times the number of users. Standard library only.
"""
import json
import os
from xml.sax.saxutils import escape

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "..", "evals", "workflow-arms", "evaluation.json")
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

THEMES = {
    "light": {"bg": "#ffffff", "fg": "#1f2328", "muted": "#59636e", "grid": "#d8dee4", "card": "#f6f8fa",
              "tierwise": "#257de0", "opus": "#f47230", "fable": "#00b894", "onbar": "#ffffff",
              "ramp": ["#257de0", "#1757ac", "#6aabf1", "#9dc8f7"]},
    "dark": {"bg": "#0d1117", "fg": "#e6edf3", "muted": "#9198a1", "grid": "#30363d", "card": "#161b22",
             "tierwise": "#338ced", "opus": "#e76624", "fable": "#00a888", "onbar": "#ffffff",
             "ramp": ["#338ced", "#1b64be", "#6aabf1", "#84b9f3"]},
}
NAME = {"tierwise": "Tierwise", "opus": "All-Opus", "fable": "All-Fable"}


# ---------------------------------------------------------------- figures

def load():
    with open(DATA) as f:
        d = json.load(f)["approaches"]
    def per_job(runs):
        usd = [round(r["research"]["usd"] + r["build"]["usd"], 2) for r in runs]
        mins = [round(r["research"]["minutes"] + r["build"]["minutes"], 1) for r in runs]
        mean_usd = round(sum(r["research"]["usd"] + r["build"]["usd"] for r in runs) / len(runs), 2)
        mean_min = round(sum(r["research"]["minutes"] + r["build"]["minutes"] for r in runs) / len(runs), 1)
        return mean_usd, mean_min, usd, mins
    def score(runs, stage):
        vals = [(r["judging"][stage]["opus_judge"] + r["judging"][stage]["fable_judge"]) / (2 * r["judging"][stage]["max_per_judge"]) * 100
                for r in runs]
        return sum(vals) / len(vals), vals
    f = {}
    for key, src in (("tierwise", "tierwise"), ("opus", "all-opus"), ("fable", "all-fable")):
        runs = d[src]["runs"]
        usd, mins, usd_runs, min_runs = per_job(runs)
        res, res_runs = score(runs, "research")
        bld, bld_runs = score(runs, "build")
        f[key] = {"usd": usd, "min": mins, "usd_runs": usd_runs, "min_runs": min_runs, "research": res, "research_runs": res_runs,
                  "build": bld, "build_runs": bld_runs, "hidden": [r["build"]["hidden_tests_passed"] for r in runs]}
    mix = {}
    for r in d["tierwise"]["runs"]:
        for stage in ("research", "build"):
            for model, usd in r[stage]["usd_by_model"].items():
                mix[model] = mix.get(model, 0) + usd / len(d["tierwise"]["runs"])
    f["mix"] = mix
    return f


def savings(f, base, budget=200):
    jobs = budget / f[base]["usd"]
    spend = round(jobs * f["tierwise"]["usd"], 2)
    base_min, t_min = round(jobs * f[base]["min"]), round(jobs * f["tierwise"]["min"])
    return {"jobs": jobs, "spend": spend, "saved": round(budget - spend, 2), "pct": (budget - spend) / budget * 100,
            "mult": f[base]["usd"] / f["tierwise"]["usd"], "t_jobs": budget / f["tierwise"]["usd"],
            "base_min": base_min, "t_min": t_min, "saved_min": base_min - t_min}


def hm(m):
    return f"{m // 60} h {m % 60:02d} min"


# ---------------------------------------------------------------- svg helpers

class Svg:
    def __init__(self, w, h, t):
        self.w, self.h, self.t, self.parts = w, h, t, []

    def add(self, s):
        self.parts.append(s)

    def text(self, x, y, s, size=14, fill=None, weight=400, anchor="start", mono=False):
        fam = MONO if mono else FONT
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{fam}" font-size="{size}" font-weight="{weight}" '
                 f'fill="{fill or self.t["fg"]}" text-anchor="{anchor}">{escape(s)}</text>')

    def rect(self, x, y, w, h, fill, r=0, extra=""):
        self.add(f'<rect x="{x:.1f}" y="{y:.1f}" width="{max(w, 0):.1f}" height="{h:.1f}" rx="{r}" fill="{fill}" {extra}/>')

    def line(self, x1, y1, x2, y2, stroke, width=1, extra=""):
        self.add(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{stroke}" stroke-width="{width}" {extra}/>')

    def render(self, title):
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" viewBox="0 0 {self.w} {self.h}" '
                f'role="img" aria-label="{escape(title)}"><title>{escape(title)}</title>'
                f'<rect width="100%" height="100%" rx="12" fill="{self.t["bg"]}"/>' + "".join(self.parts) + "</svg>\n")


def bars_panel(s, x0, y0, w, title, sub, rows, vmax, fmt, ticks, tick_fmt):
    """One small-multiple: title, three horizontal bars, run spread for Tierwise, value labels."""
    t = s.t
    s.text(x0, y0, title, 17, weight=600)
    s.text(x0 + w, y0, sub, 12, t["muted"], anchor="end")
    left, right, top, row_h, gap = 92, 92, y0 + 22, 30, 16
    x = lambda v: x0 + left + v / vmax * (w - left - right)
    bottom = top + len(rows) * (row_h + gap) - gap
    for tv in ticks:
        s.line(x(tv), top - 4, x(tv), bottom + 4, t["grid"])
        s.text(x(tv), bottom + 22, tick_fmt(tv), 11, t["muted"], anchor="middle", mono=True)
    for i, (key, val, runs) in enumerate(rows):
        y = top + i * (row_h + gap)
        s.text(x0, y + row_h / 2 + 5, NAME[key], 14, weight=700 if key == "tierwise" else 400)
        s.rect(x0 + left, y, x(val) - x0 - left, row_h, t[key], 5)
        end = x(val)
        if runs and len(runs) > 1:
            lo, hi = x(min(runs)), x(max(runs))
            s.line(lo, y + row_h / 2, hi, y + row_h / 2, t["fg"], 1.5, 'opacity="0.6"')
            for v in runs:
                s.add(f'<circle cx="{x(v):.1f}" cy="{y + row_h / 2:.1f}" r="3.6" fill="{t["bg"]}" stroke="{t["fg"]}" stroke-width="1.6"/>')
            end = max(end, hi + 4)
        s.text(end + 9, y + row_h / 2 + 5, fmt(val), 13, weight=600, mono=True)
    return bottom + 22


# ---------------------------------------------------------------- charts

def banner(f):
    w, h = 1200, 330
    s = Svg(w, h, {"bg": "#0f1b2d", "fg": "#eef3fb"})
    s.add('<defs><filter id="glow" x="-20%" y="-40%" width="140%" height="180%"><feGaussianBlur stdDeviation="6" result="b"/>'
          '<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>')
    s.text(56, 86, "Tierwise", 52, "#eef3fb", 700)
    s.text(56, 124, "The right model for every step of your Claude Code work.", 21, "#a9b8cf")
    t, o, fa = f["tierwise"], f["opus"], f["fable"]
    kpis = [
        (f"{round((1 - t['usd'] / fa['usd']) * 100)}%", "lower cost", f"vs all-Fable: ${t['usd']:.2f} vs ${fa['usd']:.2f} a job"),
        (f"{fa['min'] / t['min']:.1f}×", "faster", f"vs all-Fable: {t['min']:.1f} vs {fa['min']:.1f} min a job"),
        (f"{min(t['hidden'])}/19", "hidden tests", "passed in every run"),
        (f"{round(t['research'])}/100", "research score", f"level with all-Opus ({round(o['research'])})"),
    ]
    cw = (w - 112) / 4
    for i, (big, label, sub) in enumerate(kpis):
        x = 56 + i * cw
        s.rect(x, 162, cw - 16, 130, "#16263d", 12)
        s.add(f'<text x="{x + 22:.1f}" y="226" font-family="{FONT}" font-size="46" font-weight="700" fill="#39ff14" '
              f'filter="url(#glow)">{escape(big)}</text>')
        s.text(x + 22, 254, label, 15, "#eef3fb", 600)
        s.text(x + 22, 276, sub, 12.5, "#a9b8cf")
    return s.render("Tierwise headline results: cost, speed, hidden tests and research quality against single-model Claude Code")


def glance(f, theme):
    t = THEMES[theme]
    w, h = 1200, 500
    s = Svg(w, h, t)
    pw, gx = (w - 56 * 2 - 48) / 2, 56
    cols = [gx, gx + pw + 48]
    yb = bars_panel(s, cols[0], 52, pw, "Cost per job", "lower is better",
                    [(k, f[k]["usd"], f[k]["usd_runs"]) for k in ("tierwise", "opus", "fable")], 40,
                    lambda v: f"${v:.2f}", [0, 10, 20, 30, 40], lambda v: f"${v:g}")
    bars_panel(s, cols[1], 52, pw, "Time per job", "lower is better",
               [(k, f[k]["min"], f[k]["min_runs"]) for k in ("tierwise", "opus", "fable")], 70,
               lambda v: f"{v:.1f} min", [0, 20, 40, 60], lambda v: f"{v:g}")
    y2 = yb + 52
    bars_panel(s, cols[0], y2, pw, "Research quality", "blind score of 100 · higher is better",
               [(k, f[k]["research"], f[k]["research_runs"]) for k in ("tierwise", "opus", "fable")], 100,
               lambda v: f"{v:.1f}", [0, 25, 50, 75, 100], lambda v: f"{v:g}")
    bars_panel(s, cols[1], y2, pw, "Build quality", "blind score, % of max · higher is better",
               [(k, f[k]["build"], f[k]["build_runs"]) for k in ("tierwise", "opus", "fable")], 100,
               lambda v: f"{v:.1f}%", [0, 25, 50, 75, 100], lambda v: f"{v:g}%")
    s.text(56, h - 20, "Tierwise: average of 3 runs (line and dots show the individual runs). All-Opus and all-Fable: 1 run each. "
                       "Same jobs, prompts, starting code and hidden tests.", 12, t["muted"])
    return s.render("Cost, time, research quality and build quality: Tierwise against all-Opus and all-Fable")


def savings_chart(f, theme):
    t = THEMES[theme]
    w, h = 1200, 430
    s = Svg(w, h, t)
    sv = savings(f, "fable")
    s.text(56, 52, "One user, the same work: $200 of all-Fable usage", 20, weight=700)
    s.text(56, 76, "Measured cost and time per job, applied to the work a $200 all-Fable budget pays for "
                   f"({sv['jobs']:.2f} jobs).", 13, t["muted"])
    # money bars
    left, right, x0, x1 = 210, 250, 56, w - 56
    x = lambda v, vmax: x0 + left + v / vmax * (x1 - x0 - left - right)
    s.text(x0, 122, "API cost", 15, weight=600)
    rows = [("Without Tierwise", "all-Fable", 200.0, "fable", "$200.00"),
            ("With Tierwise", "average of 3 runs", sv["spend"], "tierwise", f"${sv['spend']:.2f}")]
    for i, (label, sub, v, key, val) in enumerate(rows):
        y = 138 + i * 48
        s.text(x0, y + 17, label, 14, weight=600)
        s.text(x0, y + 34, sub, 12, t["muted"])
        s.rect(x0 + left, y, x(v, 200) - x0 - left, 34, t[key], 5)
        s.text(x(v, 200) + 10, y + 23, val, 14, weight=600, mono=True)
        if key == "tierwise":
            s.text(x(v, 200) + 10 + 8.6 * len(val) + 18, y + 23, f"saves ${sv['saved']:.2f} ({sv['pct']:.1f}%)", 14, t["tierwise"], 700)
    # time bars
    s.text(x0, 262, "Waiting time", 15, weight=600)
    rows = [("Without Tierwise", "all-Fable", sv["base_min"], "fable"), ("With Tierwise", "average of 3 runs", sv["t_min"], "tierwise")]
    for i, (label, sub, v, key) in enumerate(rows):
        y = 278 + i * 48
        s.text(x0, y + 17, label, 14, weight=600)
        s.text(x0, y + 34, sub, 12, t["muted"])
        s.rect(x0 + left, y, x(v, sv["base_min"]) - x0 - left, 34, t[key], 5)
        s.text(x(v, sv["base_min"]) + 10, y + 23, hm(v), 14, weight=600, mono=True)
        if key == "tierwise":
            s.text(x(v, sv["base_min"]) + 10 + 8.6 * len(hm(v)) + 18, y + 23,
                   f"saves {hm(sv['saved_min'])} ({sv['saved_min'] / sv['base_min'] * 100:.1f}%)", 14, t["tierwise"], 700)
    s.text(56, h - 18, f"The same $200 pays for {sv['t_jobs']:.1f} jobs with Tierwise instead of {sv['jobs']:.1f}: "
                       f"{sv['mult']:.2f}× the work. Waiting time is wall-clock agent time, not time spent reviewing.", 12, t["muted"])
    return s.render("Savings for one user: the same work costs $200 on all-Fable and less with Tierwise, with less waiting time")


def mix_chart(f, theme):
    t = THEMES[theme]
    w, h = 1200, 200
    s = Svg(w, h, t)
    order = [("opus", "Opus"), ("fable", "Fable"), ("sonnet", "Sonnet"), ("haiku", "Haiku")]
    total = sum(f["mix"].values())
    s.text(56, 48, f"Where Tierwise's ${total:.2f} per job goes", 18, weight=700)
    s.text(w - 56, 48, "average of 3 runs", 12, t["muted"], anchor="end")
    x, bw = 56.0, w - 112
    for i, (k, label) in enumerate(order):
        v = f["mix"].get(k, 0)
        seg = v / total * bw
        s.rect(x, 66, max(seg - 2, 1), 40, t["ramp"][i], 4)
        if seg > 60:
            s.text(x + 10, 92, f"{round(v / total * 100)}%", 14, t["onbar"], 700, mono=True)
        x += seg
    lx = 56
    for i, (k, label) in enumerate(order):
        v = f["mix"].get(k, 0)
        s.rect(lx, 128, 12, 12, t["ramp"][i], 3)
        share = "<1%" if v / total < 0.01 else f"{round(v / total * 100)}%"
        s.text(lx + 20, 139, f"{label}  ${v:.2f} · {share}", 14)
        lx += 230
    prem = (f["mix"]["opus"] + f["mix"]["fable"]) / total * 100
    s.text(56, 178, f"Opus and Fable take {prem:.0f}% of the spend, on the steps that decide quality; "
                    f"Sonnet and Haiku do the rest for ${f['mix'].get('sonnet', 0) + f['mix'].get('haiku', 0):.2f}.", 13, t["muted"])
    return s.render("Tierwise spend per job by model")


def main():
    f = load()
    out = {"banner.svg": banner(f)}
    for theme in THEMES:
        out[f"glance-{theme}.svg"] = glance(f, theme)
        out[f"savings-{theme}.svg"] = savings_chart(f, theme)
        out[f"mix-{theme}.svg"] = mix_chart(f, theme)
    for name, svg in out.items():
        with open(os.path.join(HERE, name), "w") as fh:
            fh.write(svg)
    t, o, fa = f["tierwise"], f["opus"], f["fable"]
    for base in ("fable", "opus"):
        sv = savings(f, base)
        print(f"vs {base}: spend ${sv['spend']:.2f}, saved ${sv['saved']:.2f} ({sv['pct']:.1f}%), {sv['mult']:.2f}x work, "
              f"time {sv['base_min']}->{sv['t_min']} min, saved {sv['saved_min']} min; "
              f"1,000 users ${sv['saved'] * 1000:,.0f} / {sv['saved_min'] * 1000 / 60:,.1f} h; "
              f"2,000 users ${sv['saved'] * 2000:,.0f} / {sv['saved_min'] * 2000 / 60:,.1f} h")
    print(f"per job: tierwise ${t['usd']} {t['min']} min; opus ${o['usd']} {o['min']}; fable ${fa['usd']} {fa['min']}")
    print(f"research {t['research']:.1f} {[round(x) for x in t['research_runs']]} opus {o['research']:.1f} fable {fa['research']:.1f}; "
          f"build {t['build']:.1f} {[round(x, 1) for x in t['build_runs']]} opus {o['build']:.1f} fable {fa['build']:.1f}")
    print("wrote", ", ".join(sorted(out)))


if __name__ == "__main__":
    main()
