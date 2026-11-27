#!/usr/bin/env python3
"""Render the Tierwise overview images (docs/assets/overview/*.png, 1280x640: GitHub's social-preview size).

  python3 docs/assets/make_overview.py

Each image is an HTML page screenshotted with a headless Chromium or Chrome found on PATH. Every number comes from
evals/workflow-arms/evaluation.json through make_charts.py, with the same rounding as the README and
docs/evaluation.md.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from html import escape

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_charts as mc  # noqa: E402

OUT = os.path.join(HERE, "overview")
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
NEON = "#39ff14"

BASE_CSS = f"""
* {{ box-sizing: border-box; margin: 0; }}
html, body {{ width: 1280px; height: 640px; overflow: hidden; }}
body {{ font-family: {FONT}; padding: 64px 72px; display: flex; flex-direction: column; gap: 28px; }}
.dark {{ background: radial-gradient(circle at 85% 10%, #1b3157 0%, #0f1b2d 45%, #0b1422 100%); color: #eef3fb; }}
.light {{ background: linear-gradient(160deg, #ffffff 0%, #eef4fc 100%); color: #15181e; }}
.brand {{ font-size: 26px; font-weight: 800; letter-spacing: -0.01em; display: flex; align-items: center; gap: 12px; }}
.mark {{ width: 34px; height: 34px; border-radius: 9px; display: grid; grid-template-rows: repeat(4, 1fr); gap: 3px; padding: 6px; }}
.dark .mark {{ background: #16263d; }} .light .mark {{ background: #e3edfb; }}
.mark i {{ display: block; border-radius: 2px; }}
h1 {{ font-size: 58px; line-height: 1.05; font-weight: 800; letter-spacing: -0.025em; }}
.sub {{ font-size: 24px; line-height: 1.35; }}
.dark .sub {{ color: #a9b8cf; }} .light .sub {{ color: #4a5568; }}
.foot {{ margin-top: auto; font-size: 18px; display: flex; justify-content: space-between; }}
.dark .foot {{ color: #8fa3c0; }} .light .foot {{ color: #59636e; }}
.chip {{ display: inline-block; padding: 7px 16px; border-radius: 999px; font-weight: 700; font-size: 18px; }}
.fable {{ background: #1757ac; color: #fff; }} .opus {{ background: #257de0; color: #fff; }}
.sonnet {{ background: #84b9f3; color: #0b1f3a; }} .haiku {{ background: #cce3fd; color: #0b1f3a; }}
"""

MARK = '<span class="mark"><i class="fable"></i><i class="opus"></i><i class="sonnet"></i><i class="haiku"></i></span>'


def page(theme, body, extra_css=""):
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>{BASE_CSS}{extra_css}</style></head>"
            f"<body class='{theme}'><div class='brand'>{MARK}Tierwise</div>{body}"
            f"<div class='foot'><span>Claude Code plugin · MIT</span><span>github.com/sharedptr61/tierwise</span></div>"
            f"</body></html>")


def hero(f, theme):
    t, o, fa = f["tierwise"], f["opus"], f["fable"]
    kpis = [(f"{round((1 - t['usd'] / fa['usd']) * 100)}%", "lower cost than all-Fable"),
            (f"{fa['min'] / t['min']:.1f}×", "faster than all-Fable"),
            (f"{min(t['hidden'])}/19", "hidden tests, every run"),
            (f"{round(t['research'])}/100", f"research, level with all-Opus ({round(o['research'])})")]
    big = NEON if theme == "dark" else "#0a7d1f"
    cards = "".join(f"<div class='k'><div class='kb'>{escape(b)}</div><div class='kl'>{escape(l)}</div></div>" for b, l in kpis)
    css = (f".kpis {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 18px; }}"
           f".k {{ border-radius: 16px; padding: 24px 22px; }} .dark .k {{ background: rgba(22,38,61,.85); }}"
           f".light .k {{ background: #ffffff; box-shadow: 0 2px 10px rgb(15 27 45 / .08); }}"
           f".kb {{ font-size: 54px; font-weight: 800; color: {big}; letter-spacing: -0.02em; "
           f"{'text-shadow: 0 0 18px rgb(57 255 20 / .45);' if theme == 'dark' else ''} }}"
           f".kl {{ font-size: 18px; margin-top: 6px; }} .dark .kl {{ color: #c6d3e6; }} .light .kl {{ color: #4a5568; }}")
    body = ("<h1>The right model for every step<br>of your Claude Code work.</h1>"
            "<div class='sub'>Fable plans, Opus reviews and guards high-risk code, Sonnet and Haiku do the volume.</div>"
            f"<div class='kpis'>{cards}</div>")
    return page(theme, body, css)


def flow(f):
    steps = [("Classify", "7 task kinds", [("haiku", "Haiku if unsure")]),
             ("Rate risk", "R0 → R3", []),
             ("Plan", "features, high risk", [("fable", "Fable")]),
             ("Build", "units in parallel", [("sonnet", "Sonnet"), ("opus", "Opus at R3")]),
             ("Verify", "tests, secrets, syntax", []),
             ("Review", "by risk tier", [("opus", "Opus"), ("fable", "Fable at R3")])]
    cells = []
    for i, (title, sub, chips) in enumerate(steps):
        ch = "".join(f"<span class='chip {m}'>{escape(l)}</span>" for m, l in chips)
        cells.append(f"<div class='s'><div class='n'>{i + 1}</div><div class='st'>{escape(title)}</div>"
                     f"<div class='ss'>{escape(sub)}</div><div class='sc'>{ch}</div></div>")
    css = (".flow { display: grid; grid-template-columns: repeat(6, 1fr); gap: 14px; }"
           ".s { background: rgba(22,38,61,.85); border-radius: 16px; padding: 20px 16px; min-height: 230px; position: relative; }"
           ".n { font-size: 15px; font-weight: 800; color: #4493f8; } .st { font-size: 24px; font-weight: 800; margin-top: 6px; }"
           ".ss { font-size: 16px; color: #a9b8cf; margin-top: 6px; } .sc { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; align-items: flex-start; }"
           ".sc .chip { font-size: 15px; padding: 6px 12px; }"
           ".s:not(:last-child)::after { content: '→'; position: absolute; right: -14px; top: 92px; color: #6e86a8; font-size: 22px; }"
           ".loop { font-size: 19px; color: #c6d3e6; } .loop b { color: #ff8a80; }")
    body = ("<h1>How Tierwise routes a task</h1>"
            f"<div class='flow'>{''.join(cells)}</div>"
            "<div class='loop'><b>Checks fail?</b> The debugging ladder climbs only when the same failure repeats: "
            "retry → Opus debugger → Fable principal → ask you.</div>")
    return page("dark", body, css)


def models(f):
    mix = f["mix"]
    total = sum(mix.values())
    rows = [("fable", "Fable", "Plans, judgement, high-risk review"), ("opus", "Opus", "Review, security, high-risk code"),
            ("sonnet", "Sonnet", "Builders, research and analysis"), ("haiku", "Haiku", "Lookups and test runs")]
    html_rows = ""
    for k, name, role in rows:
        share = mix.get(k, 0) / total * 100
        pct = "<1%" if share < 1 else f"{share:.0f}%"
        html_rows += (f"<div class='r'><span class='chip {k}'>{name}</span><span class='role'>{escape(role)}</span>"
                      f"<span class='bar'><i class='{k}' style='width:{max(share, 1.2):.1f}%'></i></span><span class='p'>{pct}</span></div>")
    css = (".rows { display: grid; gap: 16px; } .r { display: grid; grid-template-columns: 130px 460px 1fr 70px; align-items: center; gap: 18px; }"
           ".r .chip { text-align: center; } .role { font-size: 21px; } .bar { height: 22px; border-radius: 11px; background: #e3edfb; overflow: hidden; }"
           ".bar i { display: block; height: 100%; border-radius: 11px; } .p { font-size: 22px; font-weight: 800; text-align: right; }")
    body = ("<h1>Each step goes to the model it needs</h1>"
            f"<div class='sub'>Share of Tierwise's ${total:.2f} per job, measured. Premium models are spent where they decide quality.</div>"
            f"<div class='rows'>{html_rows}</div>")
    return page("light", body, css)


def cost(f):
    t, o, fa = f["tierwise"], f["opus"], f["fable"]
    rows = [("Tierwise", t["usd"], "#257de0"), ("All-Opus", o["usd"], "#f47230"), ("All-Fable", fa["usd"], "#00b894")]
    bars = "".join(f"<div class='r'><span class='lab'>{n}</span><span class='bar'><i style='width:{v / 40 * 100:.1f}%;background:{c}'></i></span>"
                   f"<span class='v'>${v:.2f}</span></div>" for n, v, c in rows)
    css = (".rows { display: grid; gap: 22px; } .r { display: grid; grid-template-columns: 170px 1fr 120px; align-items: center; gap: 18px; }"
           ".lab { font-size: 24px; font-weight: 700; } .bar { height: 46px; } .bar i { display: block; height: 100%; border-radius: 0 10px 10px 0; }"
           ".v { font-size: 26px; font-weight: 800; } h1 span { color: " + NEON + "; text-shadow: 0 0 18px rgb(57 255 20 / .4); }")
    body = (f"<h1>Same work. <span>{round((1 - t['usd'] / fa['usd']) * 100)}% less</span> than all-Fable.</h1>"
            f"<div class='sub'>API cost per job, measured on identical research and build jobs. "
            f"{t['min']:.1f} min vs {fa['min']:.1f} min.</div><div class='rows'>{bars}</div>")
    return page("dark", body, css)


def savings(f):
    sv = mc.savings(f, "fable")
    css = ("h1 { font-size: 46px; } .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; } .c { background: #ffffff; border-radius: 18px; padding: 16px 26px; "
           "box-shadow: 0 2px 10px rgb(15 27 45 / .08); } .cl { font-size: 18px; color: #4a5568; } .cb { font-size: 48px; font-weight: 800; "
           "letter-spacing: -0.02em; color: #0a7d1f; margin-top: 2px; } .cs { font-size: 17px; color: #4a5568; margin-top: 2px; }")
    cards = [("Each user, same work", f"${sv['saved']:.2f}", f"saved of $200 ({sv['pct']:.1f}%): it costs ${sv['spend']:.2f}"),
             ("Each user, waiting time", mc.hm(sv["saved_min"]).replace(" min", "m").replace(" h ", "h "),
              f"less waiting ({sv['saved_min'] / sv['base_min'] * 100:.1f}%)"),
             ("1,000 users", f"${sv['saved'] * 1000:,.0f}", f"saved, {sv['saved_min'] * 1000 / 60:,.0f} hours less waiting"),
             ("2,000 users", f"${sv['saved'] * 2000:,.0f}", f"saved, {sv['saved_min'] * 2000 / 60:,.0f} hours less waiting")]
    html_cards = "".join(f"<div class='c'><div class='cl'>{escape(a)}</div><div class='cb'>{escape(b)}</div><div class='cs'>{escape(c)}</div></div>"
                         for a, b, c in cards)
    body = ("<h1>$200 of all-Fable work costs $" + f"{sv['spend']:.2f}" + " with Tierwise</h1>"
            f"<div class='grid'>{html_cards}</div>")
    return page("light", body, css)


def browser():
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    sys.exit("make_overview.py needs Chromium or Chrome on PATH to render the images.")


def main():
    f = mc.load()
    pages = {"tierwise-overview-hero-dark": hero(f, "dark"), "tierwise-overview-hero-light": hero(f, "light"),
             "tierwise-overview-flow": flow(f), "tierwise-overview-models": models(f),
             "tierwise-overview-cost": cost(f), "tierwise-overview-savings": savings(f)}
    os.makedirs(OUT, exist_ok=True)
    exe = browser()
    with tempfile.TemporaryDirectory() as tmp:
        for name, html in pages.items():
            src = os.path.join(tmp, name + ".html")
            with open(src, "w") as fh:
                fh.write(html)
            subprocess.run([exe, "--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--window-size=1280,640",
                            f"--screenshot={os.path.join(OUT, name + '.png')}", "file://" + src],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("wrote", os.path.relpath(os.path.join(OUT, name + ".png"), os.path.join(HERE, "..", "..")))


if __name__ == "__main__":
    main()
