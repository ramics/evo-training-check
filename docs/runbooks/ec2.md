# Running work on EC2

This is the EC2 runbook, lifted out of `AGENTS.md` so the operating manual stays short.
It is binding on anything that launches an instance. The project owner keeps the same rules
in the project settings; where the two differ, ask rather than guess.


> **Before you launch anything: a remote run must be observable from its first minute, or it is
> not a run, it is a bet.** Three things, all of them prerequisites rather than improvements, and
> all of them verified working before the launch that depends on them:
>
> 1. **It logs where you can always see it**, which means object storage, not the instance's
>    disk and not the console. A log that is uploaded when the work finishes tells you nothing
>    while the work is running and nothing at all if it never finishes.
> 2. **It heartbeats on an interval**, from a loop that runs independently of whether the work
>    succeeds, fails or is killed. The question a heartbeat has to answer is *how far did it
>    get*, and it has to answer it for a run that was killed as readily as for one that ended.
> 3. **You check on it often**, rather than finding out at the end. A run nobody looked at for
>    fourteen hours is fourteen hours you cannot get back.
>
> This is a standing rule because it has already been paid for twice. D-127: two runs died
> thirty-one seconds in and the quiet console looked exactly like a long pass still working.
> D-233: the A2.6 census spent fourteen hours on two machines and published nothing whatsoever —
> no result, no exit note, not one log line — because its hard stop powers the machine off from
> outside the script and every publishing path it had ran only on completion. About five
> dollars (D-234), and no evidence of how far it read. The detail behind all three points is in *Make a
> long run report to object storage* below; this box is here because that detail was already
> written when the census ignored it.

**Launch an instance sparingly, and only when being in-region is the point.** The test is whether
the work is bound by data movement that is free inside `us-east-1` and metered outside it — reading
the staged corpora is the case that qualifies, because a full pass over them is tens of gigabytes.
Compute that would run acceptably in the session container does not qualify, and neither does
convenience. An instance costs money, leaves a resource that can be forgotten, and cannot be
inspected once running: assume you get one shot at `UserData` and nothing else.

A1.3 learned the following the hard way. `tools/ec2_count.py` is the worked example.

**What the account's policy allows, and what it does not.** `ec2:RunInstances` is permitted, but
only with a `Project=ClaudeSpike` tag and a non-empty `Owner` tag, from an allowlisted instance
type, with volumes of 200 GB or less in `gp3`/`gp2`. Omit the tags and the refusal is a bare
`UnauthorizedOperation`, which reads exactly like not having permission at all — that misreading
cost a round trip. `iam:*` is denied, so you cannot create, inspect or list roles and instance
profiles; the `AmazebioStager` instance profile and the matching `iam:PassRole` grant already exist
and are the only way an instance gets AWS credentials. Do not try to supply credentials another
way: the session's own are injected by a proxy and never exposed to it, so they cannot be copied
onto a machine, and a presigned URL cannot be generated for the same reason.

**You cannot talk to the instance.** `ssm:SendCommand` is denied, no key pair exists, and
`ec2:AuthorizeSecurityGroupIngress` is denied, so there is no shell, no SSH and no inbound
connection. Everything the instance will do must be decided before launch and written into
`UserData`. Results come back by the instance writing them to S3. Progress comes back through
`ec2:GetConsoleOutput`, which is allowed, best-effort, and empty for the first minute or so.

**Make it terminate itself, and terminate it anyway.** Pass
`InstanceInitiatedShutdownBehavior="terminate"` at launch — `ec2:ModifyInstanceAttribute` is denied,
so it cannot be set afterwards, and without it a self-shutdown merely stops the instance and keeps
billing its volume. Then also call `ec2:TerminateInstances` from the launcher in a `finally`, because
a `UserData` that fails before its own `shutdown` would otherwise leave the instance running
indefinitely. Both, not either.

**Pick the interpreter explicitly.** Amazon Linux 2023 ships Python 3.9 as `python3`, and this
project needs 3.12; `datetime.UTC` alone is 3.11+. Install `python3.12` and invoke it by name. A
run that trusts `python3` dies on an `ImportError` about half a minute in, having read nothing.

**Make a long run report to object storage, and do not trust silence.** `GetConsoleOutput` does
keep recording well after boot — verified 2026-10-17, with per-cell progress lines arriving 103
minutes in — so it is a real channel, just a best-effort one with no guarantee of freshness. What
it cannot do is distinguish a process that has died from one that is printing nothing: on
2026-10-16 two runs died 31 seconds in, the console held only their boot output, and that looked
exactly like a long pass with a quiet console. Four hours were spent on that reading, and the
correction is in D-127.

The other channels are genuinely closed here: `cloudwatch:GetMetricStatistics` and
`ec2:GetConsoleScreenshot` are both denied, on top of the SSH and SSM denials above, and
`DescribeInstanceStatus` only reports that the OS is alive. One channel that *is* allowed and
worth knowing: `ec2:DescribeInstanceAttribute` returns the instance's `UserData`, which settles
what a running instance was actually told to do.

So anything that runs longer than a few minutes writes a heartbeat to object storage on an
interval and publishes each measurement as it is taken — `esm3_calibrate.py` is the worked
example, and it took three attempts to apply that to every stage rather than only to the one that
had just failed. A step with no heartbeat is a step whose silence means nothing at all.

It is the worked example for the second half of that more than the first, measured 2026-10-19
(D-192): in `--measure caps` the heartbeat is written once before a reading's slack cell and the
interval heartbeat covers only the corpus pass, so through a 35-minute cell it does not move —
`written_at` read 18:46 while the run was demonstrably alive at 19:43. What made that run
observable was the artefact growing as each cell published. Both halves are the rule; only one of
them is implemented everywhere, so check which one a mode gives you before reading its silence.

**A log uploaded on exit is not a channel.** A2.6's census workers redirect stdout to a file on
the instance and upload it when the worker finishes, which gives you nothing at all while it
runs — the console stops recording after boot, and the parts appear only as each band completes.
That is the same silence as a dead process. Upload the log on the heartbeat interval, not at the
end, and do it from whichever loop is already running rather than from a handler that a hard
failure skips.

**The boot-armed shutdown timer works, and it also blocks the immediate shutdown — cancel it
first.** Arm `shutdown -h +N` in `UserData` before anything that can fail; observed 2026-10-16, it
fires on time, four hours after a watcher had been killed and the launcher could no longer
terminate anything, and EC2 reports it in `StateTransitionReason` as `User initiated` — the same
wording as a manual termination, and **not** `Server.SpotInstanceTermination`, so that field
distinguishes a reclaim from a shutdown but not a shutdown from a human.

The trap is the other direction. **`shutdown -h now` does nothing while that timer is pending**:
systemd already has a shutdown scheduled and the immediate one does not replace it. So a script
that fails in thirty seconds sits idle until the timer fires, burning the whole window, and from
outside — no console after boot, no artefact, process alive, status checks `ok` — that is
indistinguishable from a long pass still working. It cost two launches and most of a day to
diagnose as exactly that (D-127). Run `shutdown -c` before `shutdown -h now`, keep
`systemctl --no-block poweroff` and `halt -p` as fallbacks, and route every exit path through one
helper; `tools/ec2_similarity.py`'s `die` is the worked example.

**Ship the payload by derivation, not by hand.** The instance has no checkout, so the launcher
tars up a list of files. Twice — 2026-10-16 and 2026-10-17 — a module was added to a tool's
imports and not to that list, and the instance died on an `ImportError` about half a minute in,
having read nothing. Derive the first-party import closure from the source and test it, as
`tests/test_ec2_similarity.py` does, and import the shipped tool on the instance **before** the
long work starts: on the instance a missing import costs an hour and a launch, and in a test it
costs a second.

**An import closure is not a dependency closure.** A2.6 spent four launches on this in one
afternoon, each one dying in five or six minutes. The closure walk finds what a source
*imports*; it cannot find what a source *reads*, and it cannot find an import that happens
inside a function. The payload shipped no `policies/specs`, so eight workers died on `no
policy specs found` — nothing imports a YAML directory. Then the specs shipped and the
workers died again, because `policyspec` imports `yaml` inside `load_policy_dir` rather than
at module scope, so the payload imported cleanly and failed on the first policy read, and no
wheel carried PyYAML. Two things fix the class rather than the instance. Walk the shipped
sources with `ast` for *every* third-party import, map each to the wheel that provides it,
and fail the test on one that is not mapped. And unpack the payload into a bare directory in
a test and run it there with nothing else on the path — `tests/test_ec2_detect_census.py`
does both, and the second is the only check that fails for the same reasons the instance
does. The pre-flight on the instance should likewise *load* what the run needs — the policy
specs, the manifests — not merely import the module.

**Parallel workers on one instance must not share an output name.** A2.6 runs eight bands of
one release at once and every worker publishes to the same durable prefix. Anything named for
the release alone is written eight times: the run manifest loses seven, and eight different
index bodies under one key are refused outright by the commit-keyed copy (D-216) — *after*
each worker's six hours, not before. Put the band in the name. A1.5 hit the same shape with
two staging passes, which is why `detect_profiles` already named its manifest per release;
one more level of parallelism needed one more level of naming.

**`aws s3 cp --recursive` over an empty prefix exits 0.** A2.6's first launch copied the A1.4
manifests from `s3://bucket/results/a1-4/` with the bucket prefix missing, the copy reported
success, and the workers started on an empty directory. A copy that must bring something is
followed by a `test -f` on something it must have brought.

**Bring the logs back yourself; the console will not.** Across those four launches
`GetConsoleOutput` truncated mid-way through staging twice and returned empty twice, including
for ten minutes after the instance that needed reading had terminated. Tee the whole script to
a file, give each worker its own log, and have the `die` helper upload all of them before it
powers off. Write the exit reason as its own small object too: it is the one thing you always
want and the cheapest thing to lose.

**Probe without the flag that publishes.** `detect_profiles --band` publishes a part that
`--assemble` reads as *the* result for that band, so a probe with `--limit-records` publishes
a part covering twenty records and claiming the whole band — and the coverage check still
passes, because the bands do tile. One reached the census prefix on 2026-10-20 and the store
has no delete. Either refuse the pair in code, which is what was done, or redirect the durable
destination for the probe.

**Rehearse the shape the run will produce, not the shape the last run produced.** A2.6's
assembly step failed twice in one day against the census's own shape, and both failures would
have landed *after* the search, with the compute already spent: once because eight census parts
do not fit in memory together where a sampled pass's did, and once because the assembler read
the first pass's table for metadata and a census has no first pass — its bands start at the
beginning and tile the whole rate. Neither is visible in a rehearsal that reuses the previous
task's artefacts, which is what makes that rehearsal worse than none: it passes. Build the
inputs the pending run will actually write — the right number of parts, the right bands, and
nothing else present — and run the downstream step against them before launching.

**A dry run authorizes; it does not execute.** `DryRun=True` checks permissions and parameters and
returns `DryRunOperation` on success, which is worth doing. It runs no `UserData`, so it cannot
catch a missing dependency, a wrong interpreter or a broken script. Those checks belong inside the
script.

**Carry provenance in, because the instance has none.** There is no git checkout on the instance, so
`amazebio.repro` cannot discover the commit and a manifest produced there is untraceable. The
launcher refuses to run from a dirty tree and passes the commit in explicitly; keep that. A result
that cannot be traced to the code that produced it is not citable, which is the whole point of
`repro`.

**A memory ceiling is not a reason to launch an instance.** A4.2 hit one: reproducing IMG/VR's own
marker search needs about 24 GB to hold the profile index in a single pass and the session container
has 16. The test in this section is data movement, and a memory bound is not that — splitting the
target database (`--splits 8` for geNomad, which is the same thing one rank down) made the search
fit and changed nothing about the result. Check whether the work can be split before concluding it
needs a bigger machine.

**Know the parallelism before choosing a size.** A gzip stream cannot be decompressed in parallel,
so one `.gz` file is one thread however many cores are present. For the UniRef tiers that caps
useful parallelism at one process per tier, and the largest tier sets the wall clock; a bigger
instance buys nothing. Work out the real ceiling first — the honest answer is often that a small
instance is the right one.

**The corpus bucket has no `s3:DeleteObject`.** Anything written there is permanent. That is
deliberate — it is what makes a staged corpus un-rewritable — but it means a bug that writes junk
writes it forever. Before a run that uploads, be sure about the keys it will produce; A1.3 left four
0-byte objects behind that cannot be removed.

**A rehearsal is the thing most likely to write junk there, because `--out` and the durable prefix
are decided separately.** `repro.run`'s `durable` is derived from the task id, so it cannot see
where the run was told to write: a probe from a scratch directory publishes to the real results
prefix under the names the deliverable will use. The fix is one line per tool — publish only when
`--out` resolves to the task's canonical `artifacts/<slug>`, claim `durable_exempt` otherwise, and
print why. `tools/detect_segmented.py`'s `durable_for` is the worked example.

**And when you fix something like that, fix the shape, not the tool.** A2.5 hit exactly this on
2026-10-19, the guard went into `detect_segmented.py`, and on 2026-10-20 A2.6 hit it again in
`detect_profiles.py` — permanently, in a bucket with no delete (D-193, then D-224). One tool was
guarded and four were not. Before closing an incident, grep for every call site with the same
shape and fix all of them, or say in the decision entry which ones you left and why.

**Never build an S3 client. Call `amazebio.objectstore.client()`.** It pins
`endpoint_url="https://s3.us-east-1.amazonaws.com"`, and `region_name` alone does not: boto3
resolves an S3 client with no explicit endpoint to the legacy global hostname `s3.amazonaws.com`,
which the egress proxy does not inject credentials for, so the request arrives unsigned and comes
back as a terse `AccessDenied` that looks exactly like a missing IAM grant. Most of a day went on
that in October, across three wrong theories about the account, and the owner was asked to loosen
permissions that were already correct. The tell: a real denial names
`arn:aws:iam::…:user/…`, and a signed-out one names nobody. Pass `config=` for a wider pool or a
longer retry chain rather than reaching for `boto3.client` to get one.
`tests/test_objectstore_writes.py` fails the build on a new bare client, so this is enforced
rather than remembered.

**Publish a result through `repro.run(durable=...)`, or through `objectstore.put_once`.** Not
`put_object`. The bucket's missing `s3:DeleteObject` is not immutability — `PutObject` on an
existing key succeeds and the earlier bytes stop being readable, which is D-216. Both paths write
the stable key and a `by-commit/<commit>/` twin a later run cannot reach, and both refuse before
writing anything when the same commit has already published different bytes, naming the object
and both digests. If that fires, something undeclared moved; find it rather than passing
`replace=`. A raw `put_object` is still right for a code payload or a heartbeat, which are not
results and are not cited.
