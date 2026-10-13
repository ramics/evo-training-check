#!/usr/bin/env python3
"""Generate tasks/BOARD.md from the frontmatter of tasks/*.md.

The task files are the single source of truth. BOARD.md is derived and should
never be hand-edited.

    python3 tools/board.py           # rewrite tasks/BOARD.md
    python3 tools/board.py --check   # validate only; non-zero exit on problems

Validation covers: unknown dependency IDs, dependency cycles, duplicate IDs,
bad status values, stale `blocks` lists, and status/dependency inconsistencies
(a task marked ready or further along while a dependency is unfinished).
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
TASKS = REPO / "tasks"
BOARD = TASKS / "BOARD.md"

STATUSES = ["blocked", "ready", "in-progress", "review", "done", "deferred"]
OPEN_STATUSES = {"blocked", "ready", "in-progress", "review"}
PHASES = {
    "A": "Phase A — filter audit",
    "B": "Phase B — capability audit",
    "C": "Phase C — leakage score",
    "X": "Cross-cutting",
}
LIST_FIELDS = {"depends_on", "blocks"}


class Problem(Exception):
    pass


def parse_frontmatter(path: pathlib.Path) -> dict:
    text = path.read_text()
    if not text.startswith("---\n"):
        raise Problem(f"{path.name}: missing YAML frontmatter")
    end = text.find("\n---", 4)
    if end == -1:
        raise Problem(f"{path.name}: unterminated frontmatter")
    meta: dict = {"_file": path.name}
    for line in text[4:end].splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise Problem(f"{path.name}: unparseable frontmatter line {line!r}")
        key, _, value = line.partition(":")
        key, value = key.strip(), value.strip()
        if key in LIST_FIELDS:
            inner = value.strip()
            if not (inner.startswith("[") and inner.endswith("]")):
                raise Problem(f"{path.name}: {key} must be a [bracketed, list]")
            meta[key] = [v.strip() for v in inner[1:-1].split(",") if v.strip()]
        elif value in ("true", "false"):
            meta[key] = value == "true"
        elif value == "null":
            meta[key] = None
        else:
            meta[key] = value.strip('"')
    return meta


def load() -> dict[str, dict]:
    tasks: dict[str, dict] = {}
    for path in sorted(TASKS.glob("*.md")):
        if path.name in ("BOARD.md", "README.md", "DECISIONS.md"):
            continue
        meta = parse_frontmatter(path)
        for field in ("id", "title", "phase", "status", "depends_on", "blocks"):
            if field not in meta:
                raise Problem(f"{path.name}: missing required field {field!r}")
        tid = meta["id"]
        if tid in tasks:
            raise Problem(f"duplicate task id {tid} in {path.name}")
        if meta["status"] not in STATUSES:
            raise Problem(f"{tid}: unknown status {meta['status']!r}")
        if meta["phase"] not in PHASES:
            raise Problem(f"{tid}: unknown phase {meta['phase']!r}")
        tasks[tid] = meta
    if not tasks:
        raise Problem("no task files found")
    return tasks


def validate(tasks: dict[str, dict]) -> list[str]:
    problems: list[str] = []

    for tid, t in tasks.items():
        for dep in t["depends_on"]:
            if dep not in tasks:
                problems.append(f"{tid}: depends on unknown task {dep}")

    expected: dict[str, list[str]] = {tid: [] for tid in tasks}
    for tid, t in tasks.items():
        for dep in t["depends_on"]:
            if dep in expected:
                expected[dep].append(tid)
    for tid, t in tasks.items():
        if sorted(t["blocks"]) != sorted(expected[tid]):
            problems.append(
                f"{tid}: stale `blocks` list — expected [{', '.join(sorted(expected[tid]))}]"
            )

    # cycles
    colour: dict[str, int] = {}

    def visit(tid: str, trail: list[str]) -> None:
        if colour.get(tid) == 2:
            return
        if colour.get(tid) == 1:
            problems.append("dependency cycle: " + " -> ".join([*trail, tid]))
            return
        colour[tid] = 1
        for dep in tasks[tid]["depends_on"]:
            if dep in tasks:
                visit(dep, [*trail, tid])
        colour[tid] = 2

    for tid in tasks:
        visit(tid, [])

    # status vs dependency consistency
    for tid, t in tasks.items():
        if t["status"] == "deferred":
            continue
        unfinished = [d for d in t["depends_on"] if d in tasks and tasks[d]["status"] != "done"]
        if t["status"] == "blocked" and not unfinished:
            problems.append(f"{tid}: marked blocked but all dependencies are done")
        if t["status"] != "blocked" and unfinished:
            problems.append(
                f"{tid}: marked {t['status']} but depends on unfinished " f"{', '.join(unfinished)}"
            )

    return problems


def fix_blocks(tasks: dict[str, dict]) -> int:
    """Rewrite each task's `blocks` line from the forward edges. Returns files changed."""
    expected: dict[str, list[str]] = {tid: [] for tid in tasks}
    for tid, t in tasks.items():
        for dep in t["depends_on"]:
            if dep in expected:
                expected[dep].append(tid)
    changed = 0
    for tid, t in tasks.items():
        want = sorted(expected[tid])
        if sorted(t["blocks"]) == want:
            continue
        path = TASKS / t["_file"]
        text = path.read_text()
        new_text, n = re.subn(
            r"^blocks: \[.*\]$", f"blocks: [{', '.join(want)}]", text, count=1, flags=re.M
        )
        if n:
            path.write_text(new_text)
            changed += 1
    return changed


def gate_line(tasks: dict[str, dict], tid: str) -> str:
    t = tasks[tid]
    downstream = sorted(t["blocks"])
    held = [d for d in downstream if tasks[d]["status"] != "done"]
    mark = "PASSED" if t["status"] == "done" else "HOLDING"
    tail = f" — holds {', '.join(held)}" if held and mark == "HOLDING" else ""
    return f"- **{tid}** {t['title']} · `{mark}`{tail}"


def render(tasks: dict[str, dict], problems: list[str]) -> str:
    total = len(tasks)
    counts = {s: sum(1 for t in tasks.values() if t["status"] == s) for s in STATUSES}
    done = counts["done"]

    ready = sorted(
        (t for t in tasks.values() if t["status"] == "ready"),
        key=lambda t: t["id"],
    )
    active = sorted(
        (t for t in tasks.values() if t["status"] in ("in-progress", "review")),
        key=lambda t: t["id"],
    )
    gates = sorted(t["id"] for t in tasks.values() if t.get("gate"))

    out: list[str] = []
    out.append("# Board\n")
    out.append(
        "<!-- GENERATED by tools/board.py from tasks/*.md frontmatter. Do not hand-edit. -->\n"
    )
    out.append(
        f"**{done}/{total} done** · "
        + " · ".join(f"{s} {counts[s]}" for s in STATUSES if counts[s])
        + "\n"
    )

    if problems:
        out.append("## ⚠ Graph problems\n")
        for p in problems:
            out.append(f"- {p}")
        out.append("")

    out.append("## Gates\n")
    out.append(
        "Gates block their downstream tasks regardless of how convenient that is. "
        "Do not work past a `HOLDING` gate.\n"
    )
    for tid in gates:
        out.append(gate_line(tasks, tid))
    out.append("")

    out.append("## In progress\n")
    if active:
        for t in active:
            owner = t.get("owner", "unassigned")
            out.append(f"- **{t['id']}** {t['title']} · `{t['status']}` · {owner}")
    else:
        out.append("_Nothing in progress._")
    out.append("")

    out.append("## Ready to pick up\n")
    if ready:
        for t in ready:
            flag = " · **GATE**" if t.get("gate") else ""
            out.append(f"- **{t['id']}** {t['title']}{flag} → `{t['_file']}`")
    else:
        out.append("_Nothing unblocked._")
    out.append("")

    out.append("## All tasks\n")
    for phase, label in PHASES.items():
        rows = sorted((t for t in tasks.values() if t["phase"] == phase), key=lambda t: t["id"])
        if not rows:
            continue
        out.append(f"### {label}\n")
        out.append("| ID | Task | Status | Blocked on | Ref |")
        out.append("|---|---|---|---|---|")
        for t in rows:
            unfinished = [d for d in t["depends_on"] if d in tasks and tasks[d]["status"] != "done"]
            title = t["title"] + (" **(gate)**" if t.get("gate") else "")
            out.append(
                f"| [{t['id']}]({t['_file']}) | {title} | `{t['status']}` | "
                f"{', '.join(unfinished) or '—'} | {t.get('design_ref', '')} |"
            )
        out.append("")

    out.append("## Critical path\n")
    out.append("Longest dependency chain to each deliverable-bearing endpoint, by task count:\n")
    depth_cache: dict[str, tuple[int, list[str]]] = {}

    def chain(tid: str) -> tuple[int, list[str]]:
        if tid in depth_cache:
            return depth_cache[tid]
        depth_cache[tid] = (1, [tid])  # cycle guard
        best: list[str] = []
        for dep in tasks[tid]["depends_on"]:
            if dep in tasks:
                _, path = chain(dep)
                if len(path) > len(best):
                    best = path
        result = (len(best) + 1, [*best, tid])
        depth_cache[tid] = result
        return result

    endpoints = [t["id"] for t in tasks.values() if not t["blocks"]]
    for tid in sorted(endpoints, key=lambda x: -chain(x)[0]):
        n, path = chain(tid)
        out.append(f"- **{tid}** ({n}): {' → '.join(path)}")
    out.append("")

    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="validate only, do not write")
    ap.add_argument(
        "--fix-blocks",
        action="store_true",
        help="rewrite every task's `blocks` list from the `depends_on` edges, then regenerate. "
        "Reverse edges are derivable, so maintaining them by hand only creates drift.",
    )
    args = ap.parse_args()

    try:
        tasks = load()
    except Problem as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.fix_blocks:
        fixed = fix_blocks(tasks)
        print(f"rewrote `blocks` in {fixed} task file(s)")
        tasks = load()

    problems = validate(tasks)

    if args.check:
        for p in problems:
            print(f"problem: {p}", file=sys.stderr)
        if BOARD.exists() and BOARD.read_text() != render(tasks, problems):
            print("problem: BOARD.md is stale — run tools/board.py", file=sys.stderr)
            return 1
        print(f"checked {len(tasks)} tasks, {len(problems)} problems")
        return 1 if problems else 0

    BOARD.write_text(render(tasks, problems))
    print(f"wrote {BOARD.relative_to(REPO)} ({len(tasks)} tasks, {len(problems)} problems)")
    for p in problems:
        print(f"problem: {p}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
