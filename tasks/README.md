# The task protocol

Read `../AGENTS.md` first. This file covers the mechanics only.

## Files

| File | Role |
|---|---|
| `BOARD.md` | **Generated.** Status of everything, what's unblocked, gates, critical path. |
| `DECISIONS.md` | Append-only log of resolved ambiguities. |
| `<ID>-<slug>.md` | One unit of work. Frontmatter is the data; the body is the brief. |

## The one command

```bash
python3 ../tools/board.py          # regenerate BOARD.md
python3 ../tools/board.py --check  # validate graph + board freshness (CI runs this)
```

Task files are the single source of truth. The board is derived. If they disagree, the board
is stale — regenerate it, don't edit it.

## ID scheme

`<phase><design-section>.<n>` — e.g. `A2.3` is the third task under `DESIGN.md` §A2.
`X` covers cross-cutting work with no single design section.

IDs are **stable and never reused**. Commits, write-ups and `DECISIONS.md` entries reference
them, so renumbering silently breaks history. If a task dies, mark it `deferred` with a note;
don't delete the file.

## Lifecycle

```
blocked ──> ready ──> in-progress ──> review ──> done
                                   └─> deferred   (explicitly not run)
```

- **blocked** — at least one dependency is not `done`. Set automatically in spirit, manually
  in practice; `--check` flags disagreements.
- **ready** — all dependencies `done`. Free to pick up.
- **in-progress** — claimed. Set `owner:` at the same time and commit immediately, so
  parallel workers see the claim before duplicating it.
- **review** — work believed complete, Done-when criteria awaiting confirmation.
- **done** — every Done-when criterion demonstrably met. See AGENTS.md "Definition of done".
- **deferred** — `DESIGN.md` declines this work (§4). Kept visible so it reaches the paper as
  named future work.

## Adding a task

1. Pick the next free `<phase><section>.<n>`.
2. Copy an existing file's frontmatter block; fill every field.
3. Set `depends_on`, then add the reverse edge to each dependency's `blocks` list. `--check`
   will tell you if you missed one.
4. Body sections: **Goal** (why this exists), **Steps** (what to do), **Done when**
   (checkable criteria), **Notes**.
5. Regenerate the board. Commit task file + board together.

## Writing a good Done-when

Criteria must be checkable by someone who didn't do the work. Prefer the specific:

- ✅ "One published leaderboard number reproduced end-to-end."
- ✅ "Thresholds were fixed and recorded before results were inspected."
- ❌ "Detection works."
- ❌ "Corpus looks right."

Where a task makes a methodological commitment, the Done-when is where it becomes auditable.
That is the point of the format.
