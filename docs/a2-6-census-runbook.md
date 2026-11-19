# Running the full census — a runbook

**For whoever picks up A2.6.** The owner approved the full set on 2026-10-27, over all 1,719
pinned viral families, after the timing probe in D-268. This file is what that probe bought:
the sizing is measured rather than estimated, and every trap below has already cost this
project a launch.

Read `AGENTS.md`'s "Running work on EC2" first. This does not replace it.

---

## 1. What is already fixed — do not redo it

| thing | state |
|---|---|
| thread oversubscription | fixed. `detect_profiles.py` takes `--search-cpus`; the launcher defaults to **1 per worker** and `check_cpu_budget` refuses a launch whose workers × threads exceed the instance's vCPUs (D-267) |
| logs from a run that never finishes | fixed. The instance copies `log-*.txt` to `results/a2-6/logs-<instance-id>/` every 10 minutes, armed before the slow work (D-233) |
| a probe publishing over the deliverable | fixed. `--band` implies no `--deliverable`, and the worker prints `not publishing: … is a rehearsal`. Verified on the instance, not just in code (D-232, D-268) |
| the silent empty manifest copy | fixed. The script `test -f artifacts/a1-4/index.json` after the copy and dies if it brought nothing |
| payload short of a runtime dependency | fixed. The script imports the shipped tool **and loads** the policy specs and manifests before any reading starts |

## 2. Sizing, measured

From the probe (one worker, `opengenome2` band `1:5`, one search thread):

| component | genes/record | search, 1 thread | a full stream pass |
|---|---|---|---|
| imgvr | 17.49 | **4.56 ms/gene** | ~6–7 min |
| imgpr | 30.77 | **5.22 ms/gene** | ~1 min |

Scaled to census depth, **OpenGenome2 is about 79 core-hours** — 73 of search, 5 of gene
calling, ~1 of streaming — which is **9.9 hours on eight vCPUs for that release alone.** The
published costing said 80 core-hours for *both* releases; it was out because its 2.19 ms/gene
was wall-clock at three threads, not core-time.

**OpenGenome's stage 2 is not measured.** It is the one number still missing, and it decides
whether that release fits the timer.

## 3. Do this first: probe stage 2

Ten minutes, publishes nothing, and it removes the last unknown:

```bash
pixi run -e dev python tools/ec2_detect_census.py --spot \
  --release opengenome --band 1:5 \
  --instance-type m6i.2xlarge \
  --hard-stop-minutes 120 --timeout-minutes 130
```

Read its `pfam/38.2: N hits above threshold in M min` line and its genes count, work out
ms/gene, and scale by 499/4 (stage 2's census multiple is 500, the probe band is 4 wide). If
that lands near 9–10 hours on eight cores, the sizing below holds. If it is much worse, raise
the timer *before* launching rather than discovering it at the ceiling.

## 4. Launch, one release at a time

**Run the two releases as two launches, not one.** The launcher will do both at once, but then
a failure in one wastes the other, and the first census attempt lost sixteen bands together.
Separate launches cost nothing extra and fail independently.

```bash
# release 1
pixi run -e dev python tools/ec2_detect_census.py --spot \
  --release opengenome2 \
  --instance-type r6i.2xlarge \
  --workers-per-release 8 --search-cpus 1 \
  --hard-stop-minutes 840 --timeout-minutes 850
```

Then the same with `--release opengenome`.

**On the instance type.** `r6i.2xlarge` is the default for memory: eight workers share the
machine and each holds its own sequence block. The probe ran **one** worker, so it did not test
eight-worker memory — that is the only unmeasured risk left, and the 64 GB machine removes it.
There is positive evidence the 32 GB `m6i.2xlarge` survives eight workers (the 2026-10-20 run
did, for fourteen hours, without dying), so it is defensible; it is simply not the choice to
make while something else is unverified.

**Eight vCPU is the account's ceiling.** Every `4xlarge` and larger is refused with a bare
`UnauthorizedOperation`, which reads exactly like having no permission at all.

## 5. Pre-flight, in order

1. **Tree clean and pushed.** The instance has no checkout, so the commit is the only thing
   that makes its tables traceable, and the launcher refuses a dirty tree.
2. **`pixi run -e dev check` green.** All nine steps.
3. **The manifests exist.** `corpora/results/a1-4/` must hold `index.json` — the first census
   attempt copied from a prefix that did not exist, `aws s3 cp --recursive` exited 0, and eight
   workers started on an empty directory.
4. **Rehearse the assembly against the shape this run will produce.** This is the step most
   likely to be skipped and it has already failed twice, both times *after* the compute was
   spent: eight census parts do not fit in memory where a sampled pass's did, and the assembler
   read the first pass's table for metadata where a census has no first pass. Build the right
   number of parts, for the right bands, with nothing else present, and run `--assemble`
   against them. A rehearsal that reuses the previous task's artefacts is worse than none,
   because it passes.
5. **`--print-user-data`** and read it. Confirm `--search-cpus 1` on every worker line.
6. **`--dry-run`** and expect `DryRunOperation`.
7. **Nothing else running.** Check for live instances tagged `Project=ClaudeSpike`.

## 6. While it runs — watch object storage, not the console

**The console is useless here.** It returned 0 bytes for the whole of the 34-minute probe, and
truncated or came back empty on all four earlier launches. Do not read silence from it as
anything.

Watch `s3://<bucket>/corpora/results/a2-6/logs-<instance-id>/`, which updates every 10 minutes.
The first upload lands about 10 minutes after boot; before that the instance is installing
wheels and staging the 418 MB Pfam download.

**Check the rate against the probe on the first chunk, not at the end.** A worker prints

```
chunk 0: 5,000 records, 68,787 genes (5,000 records read so far in 2.4 min)
```

If 5,000 records take much more than ~3 minutes to read, or the gap to the next chunk implies
far worse than ~4.6 ms/gene, stop and work out why. That is the whole point of having a
measured baseline.

The exit reason lands as its own small object, `results/a2-6/exit-<instance-id>-<epoch>.txt`.
`run complete` is what success looks like.

## 7. After

- `--assemble` the band parts, having already rehearsed it.
- Re-run A3.2 against the new tables and **keep A2.1's sampled tables beside them** — nothing
  silently replaces the other, and the two being comparable is part of the result.
- Mark the tables `estimate_kind: population`, and keep RVDB-prot's figures labelled as the
  lower bounds they remain. A reader comparing across registries would otherwise be comparing
  a census with a sample.
- Record the actual cost and wall clock against §2 above.

## 8. One thing the census cannot fix, and must say so

The census searches what the A1.4 manifests say survives the **published rules**, and those
rules are unresolvable against this component, so it searches essentially the whole released
FASTA: **2,957,495** imgvr records. Evo 2's training corpus is **2,653,047**. The difference,
**304,448**, is the material that did not reach training (A7.3, D-262, measured again in
D-268).

So about a tenth of what the census reads is records the model never trained on, and its
"surviving corpus" figures cover a population that includes them. Restricting to training
members needs the accession list from D-262's sequence join, which was scratch and died with
its container. **That is a prerequisite for a correctly scoped census, not an improvement to
one** — and until it exists, the census output has to carry this paragraph.

## 9. Housekeeping the owner's approval implies

A2.6 is deferred, and D-247 recorded that deferral as the owner's call — so reactivating it is
the owner's call too, and the pull request that does the work says so. Nothing else needs
claiming: the task cards and the board left the tree on 19 November 2026
(`working-record.md`).
