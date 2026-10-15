---
id: A1.7
title: Acquire and stage the IMG/VR release the filter was applied to
phase: A
status: in-progress
gate: false
depends_on: [A1.1]
blocks: [A7.2]
design_ref: "§A1, §A7"
deliverable: 1
owner: claude
---

# A1.7 — Acquire and stage the IMG/VR release the filter was applied to

**Design reference:** DESIGN.md §A1, §A7 · **Deliverable 1**

## Goal

Stage IMG/VR v4 — the **input** side of the only published exclusion procedure in this audit —
at its pinned version, from its own publisher, with the metadata the published rules read.

A1.2 staged both Evo releases, which are the filter's *output*. A7.1 then re-executed the
published predicates against that output and found the input missing: `policies/corpora.md` §2
states IMG/VR v4 is independently available at its pinned version, which is true and is not the
same as acquired. It is not in `policies/sources.json`, no tool stages it, and nothing in the
corpus bucket holds it. This task closes that gap, and it is a corpus acquisition on the scale of
A1.2 and A1.3 rather than an item inside another task (DECISIONS.md D-049).

## Why this is worth its own task

It is the single blocker for four distinct things, three of which A7.1 had to decline:

1. **The converse conformance check** — records the filter *removed* that its published rule does
   not call for. An over-broad filter is as much a mismatch between rule and practice as a leaky
   one, and §A7 asks for both directions. Without the input there is no denominator: a count of
   what is absent from a corpus cannot be taken from that corpus.
2. **Evo 2's conformance arm.** Its released IMG/VR FASTA carries `IMGVR_UViG_<taxon_oid>_<n>`
   accessions and no taxonomic lineage, so no published rule can be re-executed against it at
   all. With the input in hand the accessions become a join key and that arm opens.
3. **The three rules no release can test** (D-047): the high-confidence gate, the vOTU
   representative, and the prokaryotic-host count. All three read IMG/VR metadata — confidence
   label, vOTU id, host assignment — which travels with the database and not with either
   release. They are two thirds of the published procedure.
4. **A1.4 and the A2 detectors**, which need the pre-filter population to say what survived
   rather than only what is present.

## Steps

- Register the release in `policies/sources.json` with its publisher, version and retrieval date.
  Follow the paper's own pointer to the artefact rather than guessing a URL — D-019 records an
  HTTP 401 from a guessed namespace being indistinguishable from an absent artefact, and D-020
  records an HTTP 200 serving a bot challenge. **Verify content, not status codes.**
- Pin by the publisher's own checksum where one is published, as A1.3 did for UniRef (D-026,
  D-027). Where none is, record our own SHA-256 and state plainly that it attests the bytes have
  not changed since *this* acquisition and not that they are the bytes released — the separation
  D-040 drew for the unversioned benchmark files.
- Confirm the release is the one Evo 1 applied its procedure to, from Evo 1's own words, and
  record stated-versus-used where they differ. Evo 1 names IMG/VR v4; `src/amazebio/models.py`
  records ESM3's viral content as IMG/VR release 7, so the version in a sentence is not
  interchangeable with the version in a pipeline.
- Stage selectively by component, as A1.2 did, and stage the **metadata** deliberately rather
  than as a side effect: the per-record confidence label, vOTU assignment and host taxonomy are
  the reason this task exists, and a sequence-only stage would leave all four uses above blocked.
- Stream into object storage with verification before the upload completes. The corpus bucket
  withholds `s3:DeleteObject`, so an object that completes is permanent and an object claiming to
  be a release it has not been shown to be is worse than no object at all (D-026).
- Record the composition against the publisher's own stated counts, and report the gap where
  they disagree. A1.5 found documented archive sizes wrong by more than an order of magnitude;
  size downloads from `content-length`, not from documentation (D-040).
- Measure before deciding where to run the pass. A7.1's own measurement declined an EC2 launch
  because the format was splittable and the container managed 178 MB/s across sixteen readers
  (D-050); a gzip stream cannot be split and the answer may differ here. AGENTS.md's test is the
  one to apply, not the precedent to copy.

## Done when

- The release is registered in `policies/sources.json` and staged at a recorded, verified
  checksum, with stated-versus-used explicit wherever it could not be verified against the
  publisher's own figure.
- The staged component carries the per-record confidence label, vOTU assignment and host
  taxonomy, demonstrated by reading them back — not merely by the files being present.
- A composition artefact records counts per component against the publisher's stated counts.
- Which release Evo 1's procedure was applied to is established from Evo 1's own words, with any
  gap between stated and available versions recorded as a finding rather than smoothed over.
- Whether this is the real input or a proxy is stated as plainly as A1.1 stated it for the
  corpora, because every claim that depends on this inherits that verdict.

## What this task is not

- **Not the conformance work itself.** A7.1 owns the diff and is at `review`; the converse check
  and Evo 2's arm are follow-on work that this task unblocks. Keep the acquisition separate from
  the analysis, as A1.2 and A1.3 were kept separate from A7.1.
- **Not a scope widening of A1.4.** A1.4 also wants filter inputs; AGENTS.md is explicit that a
  task which turns out to be two tasks is split rather than quietly widened.
- **Not an excuse to acquire more than is needed.** One release, the components the published
  rules read. `pixi.toml`'s rule about unused pinned tools applies to unused pinned data too.

## State — 2026-10-15

`in-progress`. The acquisition tooling is **merged into `main`** (PR #8, branch
`ccr-2e82b91e-hou4gf`). Two things sit outside it:

- `claude/upbeat-shannon-wd4its` — current. The disk-spooling transfer path and its tests, and
  it carries the endpoint fix below so it can run a staging pass on its own.
- `claude/exciting-sagan-kqlqvf` — the documented-endpoint fix D-060 describes. `main` carries
  D-060's *decision* but not its *code*, which is why the branch above carries it too. Either
  branch landing closes that gap; whoever merges second will find it already applied.

Status is `in-progress` and not `blocked` on purpose: `blocked` in this schema means a task
dependency is unfinished, and `tools/board.py --check` rejects it here because A1.1 is done.
What holds this task is external, so it belongs in the waiting-on line below, which is what
the frontmatter contract is for.

**Blocked on one thing: a JGI account token.** JGI publishes the IMG/VR *inventory* without
authentication and withholds the *files*; every download endpoint returns HTTP 401
`{"detail":"Authentication credentials were not provided."}` (D-054). Registering an account
accepts a data-use policy on the project's behalf and mints a credential, so it is the project
owner's to do, not this session's. Everything that can be established without the bytes is
established and committed.

**Done, and reusable by whoever resumes:**

- The dataset is `Custom_MPI-IMG_VR`, taken from the portal's own redirect rather than guessed —
  the documented download page is a JavaScript application with no static links. The full
  inventory (42 files, 10 dated releases) is captured at
  `policies/captures/jgi-imgvr-inventory.json` and registered as `S-IMGVR-JGI-INVENTORY`.
- **All 20 files of the two candidate releases are pinned by the publisher's own md5, before
  this project holds any of the bytes** (`amazebio.imgvr.RELEASES`). That is the A1.3 standard
  rather than D-040's weaker self-attestation, and it is only possible because the inventory is
  public: the figure was recorded before anyone went looking for a match.
- **"IMG/VR v4" names two releases, not one** — 2022-09-20 and 2022-12-20 (D-052). They are
  byte-identical in nucleotides and host information and differ in the sequence-information
  table, which carries the confidence label and the vOTU assignment. They therefore agree on
  what Evo 1's host-count rule reads and disagree on what its high-confidence gate and vOTU
  representative read: two of the three rules A7.1 could not run.
- **The acquisition is 7.9 GB per release, not 128.7 GB** (D-053). Every conformance check is a
  set operation over accessions and metadata, so no nucleotides or proteins are staged. Both
  confidence variants are, and the unfiltered one is not optional: a gate that keeps
  high-confidence records cannot be audited against a file from which every record passes it.
- A verification of A7.1 fell out of step one (D-055): Evo 1's own Table S3 publishes 2,653,046
  records, 36,236 M bases and 13,658 mean length for this component, against A7.1's census of
  2,653,047 / 36,236.0 / 13,658.3. The `+1` is unexplained and reported, not rounded away. The
  check now runs inside `tools/conformance_diff.py` rather than living in prose.

**Both v4 releases are the audited input** (D-056), chosen by the project owner rather than by
this task. One of them is on tape: 2022-09-20 is `RESTORED` and downloadable immediately,
2022-12-20 is `BACKUP_COMPLETE` and needs an asynchronous restore request first, so A1.7
completes in two passes.

**What is left — one command, once the token exists:**

```bash
python3 tools/stage_imgvr.py --inventory   # no token; checks live listing against the pins
python3 tools/stage_imgvr.py --stage       # both releases, metadata only, verify then upload
```

`tools/stage_imgvr.py` is written, linted and tested on every path that does not need the
credential: the inventory check runs clean against the live listing (42 files, 0 problems), the
token guard reports what to do, and the tape-restore path requests and polls rather than
failing. What has never executed is the authenticated download itself. Authentication is a
Bearer token in the `Authorization` header, read from JGI's own API spec rather than guessed.

### Where the token comes from, and one caveat (added from the A1.4 session, 2026-10-15)

Established from JGI's live API spec (`files.jgi.doe.gov/swagger.json`, version 202610.92006.17)
and its SSO site, because the login service changed on **27 July 2026** and the old
`signon.jgi.doe.gov` is retired — a URL recalled rather than checked would have been wrong.

- **Getting it:** log in to the Data Portal (`https://data.jgi.doe.gov`), click the avatar in the
  upper right, then **"Copy My Session Token"**. The API's own parameter is named *SSO session
  token* with pattern `^Bearer \S+$`, so the value pasted into `JGI_API_TOKEN` is the token
  alone — `stage_imgvr.py` adds the `Bearer ` prefix itself.
- **Accounts now need ORCID.** Non-JGI users authenticate through an ORCID iD with 2FA enabled,
  associated with the JGI account. The project owner has done this.
- **The caveat: it is a browser *session* token, not a long-lived API key.** This task stages
  7.9 GB per release across **two passes with an asynchronous tape restore between them**
  (2022-12-20 is `BACKUP_COMPLETE`). A token that expires during the restore wait will surface as
  HTTP 401, which this tool's own guard reports as a missing credential. Whoever resumes should
  read a mid-run 401 as "expired, re-copy the token" before concluding anything about
  permissions, and consider whether the restore wait should be a separate invocation rather than
  a poll inside one long-lived run.
- **The download host is a separate service, and the endpoint did need changing** (corrected
  2026-10-15, D-060). `files.jgi.doe.gov/filedownload/` answers 401 unauthenticated, which this
  line first read as "live, no change needed". It answers 401 to *every* method and its `Allow`
  header reads `POST, OPTIONS`, while this tool was sending a GET. The publisher's download API
  has its own spec at `files-download.jgi.doe.gov/apidoc/?format=openapi`, and its documented
  single-file read is `GET /download_files/{jamo_id}/` — `Allow: GET, HEAD, OPTIONS`. The tool
  now builds that URL through `amazebio.imgvr.download_url`. Because this endpoint checks
  authentication before method, the old form would have failed as a 401, which is what the
  tool's own guard reports as a missing credential.

**Waiting on the project owner:** a JGI credential that is **not intercepted on the way out**.
Nothing else.

As of 2026-10-15 the token exists and does not arrive (D-061). `JGI_API_TOKEN` is now in the
environment and it is a good credential: a three-segment RS256 JWT from
`auth.jgi.doe.gov/auth/realms/jgi-web`, issued 12:58 UTC and valid for about eleven more hours
when it was tested. The authenticated download fails anyway, and identically to having no
credential at all — `401 {"detail":"Authentication credentials were not provided."}`, which is
the *header absent* message, not the *token rejected* one. So the earlier advice in this file to
read a mid-run 401 as "expired, re-copy the token" does not apply to this 401, and following it
would have burned a round trip on a second token that would have been stripped like the first.

Three measurements locate the loss, and the last one settles it:

1. The request shape is the publisher's own. Its download spec declares one security scheme —
   `apiKey`, name `Authorization`, in `header`, pattern `^Bearer \S+$` — and that is what
   `amazebio.imgvr.download_url` and `stage_imgvr.py` send (D-060).
2. The token's **own issuer** also reports no credential: Keycloak's `userinfo` answers `401`
   with a bare `WWW-Authenticate: Bearer realm="jgi-web"` for the real token and for
   `Bearer notatoken` alike. A present-but-bad token gets `error="invalid_token"` and a
   description instead. Two JGI services on two hosts both see nothing.
3. The client does send it. The same header to a local server on `127.0.0.1` — not proxied —
   arrives intact at 1540 bytes, `Bearer ` plus the 1533-character token.

The session's egress proxy re-terminates TLS and is configured to inject credentials for
`*.jgi.doe.gov`. It is the only thing between the tool and the publisher, and the only thing
documented to rewrite that header for that host. What it injects does not authenticate, and it
does not pass ours through. **The fix is the project owner's: make the token reachable as the
plain environment variable `JGI_API_TOKEN` without the proxy also claiming `*.jgi.doe.gov` for
injection, then start a new session.** Not a different token, and not a different endpoint —
both of those have been ruled out by measurement rather than by assumption.

Do not attempt to route around it. Unsetting the proxy, disabling TLS verification or reaching
JGI off-policy are all forbidden by the environment and all wrong on their own terms: a corpus
acquired by evading the session's egress policy is not one this audit can cite.

**Changed while blocked** (branch `claude/upbeat-shannon-wd4its`): the transfer path is no
longer the one that was written. `download_verify_upload` accumulated each whole file in memory
and then joined it, so the 5.0 GB sequence-information table would have peaked at roughly twice
that against 15 GB of RAM — the first authenticated run would have died on it. Each file now
spools to disk and is deleted once uploaded, the run refuses to start if the spool filesystem
cannot hold the largest single file (that file plus headroom, not the 7.9 GB release total,
because only one is ever on disk), and the upload is `upload_file` rather than a `put_object`
whose 5 GiB single-PUT ceiling that file sits just under. Tests now cover the step that writes
to the no-delete bucket: verified bytes upload, an md5 mismatch or a listing/bytes disagreement
upload nothing, the spool file is removed either way, and a dry run moves nothing.

## Numbering

Opened as **A1.6** on 2026-10-15 and renumbered to **A1.7** the same day, before any other
file referenced it. The A1.4 track had already created an A1.6 — the ESM3 similarity-reading
pass, split out by their D-043 — and it reached `main` first. AGENTS.md forbids reusing a task
ID, so the collision had to be resolved one way or the other; theirs is the one cited from
`main`'s commits and from their D-043, which makes this the cheaper of the two to move. The
push that first created this file calls it A1.6; this section is how that commit resolves.

## Notes

`blocks` names **A7.2**, which is the task that consumes this one: the converse conformance
check, Evo 2's arm, and the three published rules no release can test. A7.2 was opened on
2026-10-15, after this file; an earlier version of this section said the follow-on work had no
task file yet, which is no longer true.

A7.2 depends on this task alone and not on A7.1, even though it builds on A7.1's code. A7.1 is
held at `review` by the A3.3 gate, which has nothing to do with whether A7.2 can start — so
A7.2 becomes `ready` the moment this task reaches `done`, and nothing else gates it.

_Record decisions in `tasks/DECISIONS.md`, not here. Keep this file's frontmatter current._
