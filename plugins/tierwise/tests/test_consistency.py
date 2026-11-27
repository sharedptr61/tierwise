"""tierwise is self-contained: everything it names exists, and it names no other plugin's skills."""
import json
import os
import re
import unittest

from helpers import PLUGIN

SKILLS = {d for d in os.listdir(os.path.join(PLUGIN, "skills")) if os.path.isfile(os.path.join(PLUGIN, "skills", d, "SKILL.md"))}
AGENTS = {f[:-3] for f in os.listdir(os.path.join(PLUGIN, "agents")) if f.endswith(".md")}
USER_ONLY = {"terse", "commit-message", "debt", "compress-memory"}


def text_files():
    for base in ("agents", "skills", "templates", "bin", "hooks"):
        for dirpath, _, files in os.walk(os.path.join(PLUGIN, base)):
            for f in files:
                if f.endswith((".md", ".py", ".js", ".json")) or base == "bin" and "." not in f:
                    yield os.path.join(dirpath, f)


def frontmatter(path):
    with open(path) as f:
        text = f.read()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, f"no frontmatter in {path}"
    out = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out, text[m.end():]


class Consistency(unittest.TestCase):
    def test_every_tierwise_name_exists(self):
        missing = []
        for path in text_files():
            with open(path, errors="replace") as f:
                for name in re.findall(r"tierwise:([a-z][a-z-]*[a-z])", f.read()):
                    if name not in SKILLS | AGENTS | {"agent"}:
                        missing.append(f"{os.path.relpath(path, PLUGIN)}: tierwise:{name}")
        self.assertEqual(missing, [])

    def test_no_other_plugins_process_skills_are_named(self):
        hits = []
        for path in text_files():
            with open(path, errors="replace") as f:
                for i, line in enumerate(f, 1):
                    if re.search(r"\b(superpowers|ponytail):[a-z]", line):
                        hits.append(f"{os.path.relpath(path, PLUGIN)}:{i}")
        self.assertEqual(hits, [])

    def test_agent_preloads_are_tierwise_skills(self):
        for agent in AGENTS:
            fm, _ = frontmatter(os.path.join(PLUGIN, "agents", agent + ".md"))
            for skill in filter(None, (s.strip() for s in fm.get("skills", "").split(","))):
                self.assertTrue(skill.startswith("tierwise:") and skill.split(":", 1)[1] in SKILLS, f"{agent}: {skill}")

    def test_skills_have_names_descriptions_and_stay_short(self):
        for skill in SKILLS:
            fm, body = frontmatter(os.path.join(PLUGIN, "skills", skill, "SKILL.md"))
            self.assertEqual(fm.get("name"), skill)
            self.assertGreater(len(fm.get("description", "")), 40, skill)
            self.assertLess(len(body.splitlines()), 100, f"{skill} is long; it sits in context when loaded")
            self.assertNotIn("effort:", "" if skill in ("amend", "debug") else "\n".join(f"{k}:" for k in fm), skill)

    def test_user_invoked_skills_are_never_auto_loaded(self):
        for skill in USER_ONLY:
            fm, _ = frontmatter(os.path.join(PLUGIN, "skills", skill, "SKILL.md"))
            self.assertEqual(fm.get("disable-model-invocation"), "true", skill)

    def test_preloaded_skills_carry_no_effort(self):
        # A skill preloaded into an agent must not change that agent's pinned effort.
        for skill in ("tdd", "root-cause"):
            fm, _ = frontmatter(os.path.join(PLUGIN, "skills", skill, "SKILL.md"))
            self.assertNotIn("effort", fm, skill)

    def test_no_plugin_dependencies(self):
        # Tierwise is self-contained: security-guidance is recommended in the README, never required.
        with open(os.path.join(PLUGIN, ".claude-plugin", "plugin.json")) as f:
            manifest = json.load(f)
        for key in ("dependencies", "optionalDependencies"):
            self.assertNotIn(key, manifest)


if __name__ == "__main__":
    unittest.main()
