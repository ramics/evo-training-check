# The working record, and how to read a citation into it

Figures, contracts and docstrings throughout this repository cite two kinds of identifier:

- **Task ids** — `A2.1`, `A7.5`, `B3.2`, `X1.8`. One unit of work, with its pre-registered
  criteria, its state and what it delivered.
- **Decision ids** — `D-075`, `D-245`, `D-261`. One resolved ambiguity, appended to a log and
  never edited afterwards, so a figure can be read against what was known when it was fixed.

Both resolve into the working record: 80 task cards, the 12,156-line append-only decision log,
and the board generated from the cards. **It was removed from the tree on 19 November 2026**, to
keep the project management out of the way of someone reading the work. It was not deleted, and
the citations still resolve.

## Reading it

In git history, at commit `fbc8b41267e381899ff396903c7f249907fad71c`:

```bash
git show fbc8b41:tasks/DECISIONS.md | less                  # the whole log
git show fbc8b41:tasks/BOARD.md                             # the board as it stood
git show fbc8b41 --stat -- tasks/ | head                    # what was there
git log --all --oneline -- tasks/DECISIONS.md | tail -5      # when the log began
git checkout fbc8b41 -- tasks/                              # restore it into a working tree
```

A copy also sits in the project's own files under `working-record/`, which is the easier route if
you have those files but not the repository.

## What carries the record now

- **`../results/README.md`** — every published figure with the contract that defines it, the tool
  that computed it, the artefact it lives in, and the task and decision ids that fixed it. This
  is the file to update when a figure changes.
- **`status.md`** — what is done, what is open, and which gates are closed.
- **`../metrics/`** — the frozen output contracts, still the authoritative definitions. The only
  thing that changed is where a change to one gets recorded.

Decisions from here on are recorded in the project thread where the work is discussed, and in
`../results/README.md` wherever they bear on a published figure. The log existed so that a number
could be read against what was known when it was fixed. Keeping the old ids resolvable does that
job; growing the file past 12,000 lines was not doing it.
