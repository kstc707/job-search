# Writing skills

A comparison of [Matt Pocock's skills](https://github.com/mattpocock/skills) (MIT) with this repo's own, and how to
write skills the way his are written.

Visual version with charts and annotated examples: [Skill-Writing-Guide.pdf](Skill-Writing-Guide.pdf) (12 pages).

Read in order:

1. [Why they look different](01-why-they-look-different.md): ten concrete differences, with numbers, and what
   your skills already do better.
2. [Every term explained](02-every-term-explained.md): the files and frontmatter fields of a skill, then every
   term in Matt's `writing-for-agents` vocabulary in plain language.
3. [Tutorial and examples](03-tutorial-and-examples.md): one skill built from scratch, before/after rewrites of
   lines from `tsenta-apply` and `sai-resume-tailor`, practice exercises, a cheat sheet.

The skill that applies all of this is [`.claude/skills/writing-skills`](../../.claude/skills/writing-skills/SKILL.md).
Use it by asking to write or review a skill, or by typing `/writing-skills`. Its linter runs on any skill folder:

```
python3 .claude/skills/writing-skills/scripts/lint_skill.py .claude/skills/tsenta-apply
```
