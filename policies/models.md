# The Phase B model inventory — verified checkpoint by checkpoint

What each checkpoint is, who may use it, how it is obtained, and what its developers state
about exclusion. This is the evidence half of task B1.1; the machine-readable half is
`src/amazebio/models.py` and the artefact is `artifacts/b1-1/inventory.json`.

`DESIGN.md` §B1 opens by saying to verify every exclusion policy from primary sources and to
trust no secondary source, that document included. So §B1's own model table is not the input
here. Each row below was re-derived from the stored sources, and three of them came out
differently from the table — recorded in §6.

The exclusion *policies* are `evo.md`, `esm3-open.md`, `esm-c.md` and `esm2.md`; they are not
restated here. This file covers identity, licence, access and role, which is what B1.2 needs
and what nothing else in the store records.

---

## 1. ESM-2 — positive control, two sizes

**Checkpoints:** `esm2_t33_650M_UR50D` (650M, 33 layers) and `esm2_t36_3B_UR50D` (3B, 36
layers). Both from the repository's own checkpoint table, which also gives the direct download
route:

[source: S-ESM2-REPO, model table]
> `esm2_t33_650M_UR50D`        | 33           | 650M        | UR50/D 2021_04

[source: S-ESM2-REPO, model table]
> `esm2_t36_3B_UR50D`          | 36           | 3B          | UR50/D 2021_04

**Corpus:** UniRef50 2021_04, UR50/D — UniRef90 members resampled per training update. Pinned
and argued in `esm2.md` §2, §4 and §6; not repeated here.

**Licence:** MIT, from the repository's own licence file:

[source: S-ESM2-LICENSE]
> Copyright (c) Meta Platforms, Inc. and affiliates.

and the model card agrees (`license: mit`).

**Access:** three routes, all first-party. Direct download from
`dl.fbaipublicfiles.com/fair-esm/models/<checkpoint>.pt` per the table above; `torch.hub`:

[source: S-ESM2-REPO]
> model, alphabet = torch.hub.load("facebookresearch/esm:main", "esm2_t33_650M_UR50D")

or the HuggingFace mirror, which is the route B1.2 will take because it is the one
`transformers` loads:

[source: S-ESM2-HF-650M]
> [esm2_t33_650M_UR50D](https://huggingface.co/facebook/esm2_t33_650M_UR50D) | 33 | 650M

**Exclusion:** none stated, and that is the point of including it. But see `esm2.md` §6: ESM-2
is not *unfiltered*. A de-novo-protein filter with published parameters removed an unquantified
share of the release, for stated reasons that are about generalisation rather than biosecurity.
A write-up calling ESM-2 unfiltered would be wrong; "no biosecurity exclusion" is the claim the
sources support.

## 2. ESM3-open — the protein-level test condition

**Checkpoint:** `esm3-sm-open-v1`. The weights are open and the rest of the family is not:

[source: S-ESM3-REPO]
> The code for ESM3 is available from Github and weights for esm3-sm-open-v1 is available on [Hugging Face](https://huggingface.co/collections/biohub/esm3-model-family). Other weights are available when the model is accessed through Biohub.

**Licence:** MIT. The model card points at the repository's licence file, which is stored
(S-ESM-LICENSE):

[source: S-ESM3-HF-OPEN]
> This repository is under a MIT [license](https://github.com/evolutionaryscale/esm/blob/main/LICENSE.md).

**Access:** HuggingFace `biohub/esm3-sm-open-v1`, loaded through the `esm` package
(`pip install esm`).

**Exclusion:** similarity-based, across every training database. See `esm3-open.md`; the
"related to viruses" versus "unique to viruses" gap in §1 of that file is the single most
load-bearing sentence in this store.

**Parameter count: not stated by any retrieved first-party source.** This is the finding in
this file. The ESM3 family table gives three flagship sizes and does not list the open
checkpoint at all:

[source: S-ESM3-REPO, ESM3 Family table]
> | esm3-small-2024-08 | 1.4B | 2024-08 |  |

The table's rows are `esm3-large-2024-03` (98B), `esm3-medium-2024-08` (7B),
`esm3-small-2024-08` (1.4B) and their 2024-03 counterparts. `esm3-sm-open-v1` appears in the
prose above the table as the open checkpoint and nowhere in it, so neither its size nor which
flagship checkpoint it corresponds to is established by its own developers' retrieved
documentation. The model card states corpus scale and token counts but no parameter count.

The figure everyone uses — 1.4B — traces to a *different lab* describing it:

[source: S-ESMC-PREPRINT, p110]
> We compare the performance of the ESMC models to existing open source protein language models ESM2 650M

— where the sentence continues "and ESM3 1.4B Open". That is the ESM-C authors'
characterisation of someone else's model, which makes it a secondary source as to ESM3, and
§B1 step 0 rules it out for exactly this purpose. The inference is almost certainly right. It
is still an inference, so `params` is recorded as unstated, and anything in a write-up that
turns on ESM3-open's size needs the Science version of record (S-ESM3-SCIENCE, unretrieved)
or the model's own config.

Two further gaps on this checkpoint, both already logged: no training corpus was released, so
Phase A audits a proxy (A1.1, DECISIONS.md D-017), and the MMseqs2 identity threshold — the
filter's one free parameter — is unpublished.

## 3. ESM-C — second positive control

**Checkpoint:** `ESMC-600M`. The family is 300M, 600M and 6B, with the smaller two described
as overtrained variants for local inference:

[source: S-ESMC-HF-600M]
> The ESMC 6B model has 6 billion parameters, with 80 layers and 2.37e23 training flops. We additionally release overtrained 300M and 600M parameter variants of ESMC for local inference and finetuning.

600M is chosen over 6B because it is what a 24 GB GPU runs comfortably and because the role is
a second viruses-included comparison, not a capability ceiling. If the comparison later wants
the 6B model, that is a compute decision, not a re-verification.

**Licence:** MIT plus a third-party notice (`license: mit, other`, with the notice linked from
the card). The repository licence is stored and is MIT, Chan Zuckerberg Biohub (S-ESM-LICENSE).

**Access:** HuggingFace `biohub/ESMC-600M`, and in `transformers` from v5.16.0:

[source: S-ESM-REPO]
> Codebase, model weights, and model variants for ESMC are available through [Hugging Face](https://huggingface.co/collections/biohub/esmc-model-family).

There is also a hosted platform route with API tokens. B1.2 should not use it: §4 permits
zero-shot scoring only, and sending assay sequences to a developer's own API both leaves the
harness unconstrained and discloses what we are scoring.

**Exclusion:** none stated; viral content present and pinned at IMG/VR release 7, largely
bacteriophage. See `esm-c.md`, including §5 — the 600M and 6B cards are byte-identical, so no
card evidences anything variant-specific, and the corpus claim rests on the preprint.

## 4. Evo 2 — the nucleotide-level test condition

**Checkpoint:** `evo2_7b` (32 layers, 7B), with `evo2_40b` as the Tier 2 entry:

[source: S-EVO2-HF-7B]
> | [evo2_7b](https://huggingface.co/arcinstitute/evo2_7b) | 32 | 7B  |

Note that the card lists two families — checkpoints trained to 1M sequence length, and 8192-
context base checkpoints (`evo2_7b_base`, `evo2_40b_base`, `evo2_1b_base`). They are different
checkpoints and the identifiers differ by one suffix. Phase B uses `evo2_7b`.

**Licence:** Apache-2.0, on the card (`license: apache-2.0`) and in the repository's licence
file:

[source: S-EVO2-LICENSE]
> Version 2.0, January 2004

**Access:** HuggingFace `arcinstitute/evo2_7b` through the `evo2` package. The hardware
requirement is stated, and it separates the two sizes:

[source: S-EVO2-REPO]
> The 40B, 20B, and 1B models require FP8 via [Transformer Engine](https://github.com/NVIDIA/TransformerEngine) for numerical accuracy and a Nvidia Hopper GPU. The 7B models can run in bfloat16 without Transformer Engine on any supported GPU.

[source: S-EVO2-REPO]
> **Note:** The 40B model requires multiple H100 GPUs. Vortex automatically handles device placement, splitting the model across available CUDA devices.

So 7B needs a GPU but not a Hopper one; 40B needs several H100s. That is the whole Tier 2
question and §5 records how it was settled.

There is also a hosted inference route:

[source: S-EVO2-REPO]
> You can run Evo 2 without any installation using the [Nvidia Hosted API](https://build.nvidia.com/arc/evo2-40b).

Not used, for the same two reasons as ESM-C's platform: §4 requires the harness to be
constrained in code, and a hosted endpoint cannot be.

**Exclusion:** label-based, eukaryote-infecting viruses, phage retained. See `evo.md` — in
particular that the procedure exists only in Evo 1 and that none of the ten formulations says
what happens to viral-derived sequence inside retained eukaryotic genomes.

## 5. Tier 2, and the compute envelope

`DESIGN.md` §B1 names Evo 2 40B, Nucleotide Transformer and ProGen2 as Tier 2 "if compute
allows". Two separate answers:

**Nucleotide Transformer and ProGen2 are not in the inventory at all**, because nothing about
either has been retrieved into `sources.json`. §B1 step 0 forbids inheriting a training-data
claim from `DESIGN.md`, so they cannot be added as rows — adding them is an acquisition task
with its own ID, not an inventory entry.

**Evo 2 40B turns on what this account may launch**, which is measured rather than assumed.
`tools/ec2_capability.py` dry-runs `RunInstances` across a fixed list of instance types;
nothing is launched, because `DryRun=True` authorizes the request and then refuses it. The
measurement is in `artifacts/b1-1/ec2-capability/allowlist.json`.

As measured on 2026-10-14, after the project owner added a GPU allowance in response to the
first probe: `g5.xlarge` and `g6.xlarge` are permitted — one 24 GB accelerator — alongside
`t3.micro/large/xlarge`, `c6i.large/xlarge/2xlarge`, `m6i.xlarge/2xlarge` and
`r6i.xlarge/2xlarge`. No Hopper and no multi-GPU type is permitted.

So **every Tier 1 checkpoint is runnable and Evo 2 40B is not**, on the developers' own stated
requirement of multiple H100s with FP8 (§4). That settles Tier 2 on a measurement rather than
a judgement call, which is the only reason it is recorded here rather than left to whoever
reaches B1.2. The decision and its cost reasoning are DECISIONS.md D-034.

The snapshot carries its date for a reason: this is an account policy, it changed once during
this task, and a stale reading of it would silently misreport what is possible. Re-run the
probe rather than citing this paragraph.

## 6. Where this diverges from `DESIGN.md` §B1

Three differences, which is why the re-verification was worth doing rather than inheriting the
table:

1. **§B1 lists "ESM-2 650M and 3B" and "ESM-C (open release)" without identifiers.** Resolved
   above to `esm2_t33_650M_UR50D`, `esm2_t36_3B_UR50D` and `ESMC-600M`. "Open release" is
   ambiguous for ESM-C: all three sizes are openly downloadable, so the phrase does not pick
   one out, and the choice of 600M is this task's, recorded here rather than implied.
2. **§B1 writes ESM3-open as `esm3-sm-open-v1` and Phase B needs its size.** §2 above: no
   first-party source states it.
3. **§B1's Tier 2 list cannot be verified as written.** §5 above.

None of these changes the design. They change what can be *said*, which is the standard §7 sets
for Phase A and which Phase B inherits by sharing the same model list.
