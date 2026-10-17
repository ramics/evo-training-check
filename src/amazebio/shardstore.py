"""A staged, checksummed sample of a corpus tier, so the corpus pass is paid once.

D-122 and D-123: the corpus pass over UniRef100 costs about 52 minutes whatever the sample
rate, and it is currently paid on every launch because the tool can only rebuild its target
shards from the full tier. The broad arm's sweep is about 1,296 search core-hours, which is
162 instance-hours against a 260-minute shutdown timer that cannot be extended after launch
— so it is dozens of launches, and dozens of corpus passes.

Staging the sample fixes that, and the robustness argument matters more than the ~$6.50: a
spot reclaim destroys an in-flight corpus pass along with the searches it was feeding, which
is what happened to the first in-region run. With the sample staged, a reclaim costs only the
search in flight.

Three things the manifest carries beyond the shard keys, each because leaving it out would
make the staged sample un-citable:

**The denominators.** The rates D-109 reports need the cluster count the sample was drawn
from — 350,950,053 for UniRef100 2023_02, reconciling with the publisher's own count (D-100)
— and the viral-seeded count. Those are products of the corpus pass, so a run that skips the
pass must read them from here or it has a numerator with no denominator.

**The seed set it pairs with.** The seeds come from the same pass. A sample staged without
the seed set it was produced alongside invites a later run to pair shards with a seed FASTA
built from a different release or taxonomy pin, which would be undetectable in the output.

**A checksum per object.** The corpus bucket has no `DeleteObject`, so a bad staged shard
cannot be removed, only superseded — which means the only protection against silently
searching against the wrong bytes is to verify them on load and refuse.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from amazebio.repro import sha256_file

#: Bumped when the manifest's meaning changes, not its contents. A loader that does not know
#: the version refuses rather than guessing which fields it can trust.
MANIFEST_VERSION = 1

MANIFEST_NAME = "manifest.json"


class ShardStoreError(RuntimeError):
    """A staged sample that cannot be trusted. Always fatal: the alternative is searching
    against bytes nobody can identify, and reporting the result as a measurement."""


@dataclass(frozen=True)
class StagedObject:
    """One staged file, by its key and what it should hash to."""

    key: str
    sha256: str
    bytes: int

    def verify(self, path: Path) -> None:
        if not path.exists():
            raise ShardStoreError(f"{self.key} did not arrive at {path}")
        size = path.stat().st_size
        if size != self.bytes:
            raise ShardStoreError(
                f"{self.key}: staged as {self.bytes:,} bytes, local copy is {size:,}"
            )
        digest = sha256_file(path)
        if digest != self.sha256:
            raise ShardStoreError(
                f"{self.key}: sha256 {digest} does not match the staged {self.sha256}. "
                "Refusing to search against bytes that are not the ones recorded."
            )


@dataclass(frozen=True)
class StagedShard(StagedObject):
    """A staged shard, with the sample statistics the reporting needs."""

    index: int = -1
    clusters: int = 0
    residues: int = 0


@dataclass
class ShardManifest:
    """What a staged sample is, precisely enough to use it without the corpus pass."""

    release: str
    tier: str
    sample_rate: int
    buckets: int
    corpus_clusters: int
    #: Kept as `viral_seeded_clusters` even though D-139 renamed the generic counters:
    #: this field is not a generic count but a fact about *this* staged sample, which the
    #: broad arm drew with viral seeds, and it is a key in an already-staged manifest that
    #: cannot be rewritten. A1.8 reads this sample rather than drawing its own.
    viral_seeded_clusters: int
    seed_fasta: StagedObject
    shards: list[StagedShard]
    #: The full `SeedCounts` dict from the pass that produced this sample. The two scalars
    #: above are the denominators the reporting needs and are kept as fields because they are
    #: cited directly; this carries everything else the pass measured — the
    #: representative-versus-member gap among them (D-092, D-100) — so a run that skips the
    #: pass reports what was measured rather than a default that reads like a zero.
    seed_counts: dict[str, Any] | None = None
    code_commit: str | None = None
    taxdump_pin: str | None = None
    created_at: str = field(
        default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    )
    version: int = MANIFEST_VERSION

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_json(cls, text: str | bytes) -> ShardManifest:
        raw = json.loads(text)
        version = raw.get("version")
        if version != MANIFEST_VERSION:
            raise ShardStoreError(
                f"staged sample declares manifest version {version!r}, this code knows "
                f"{MANIFEST_VERSION}. Refusing rather than guessing which fields still mean "
                "what they did."
            )
        try:
            seed = StagedObject(**raw["seed_fasta"])
            shards = [StagedShard(**s) for s in raw["shards"]]
        except (KeyError, TypeError) as exc:
            raise ShardStoreError(f"staged manifest is missing or malformed: {exc}") from exc
        known = {f for f in cls.__dataclass_fields__ if f not in ("seed_fasta", "shards")}
        return cls(
            seed_fasta=seed,
            shards=shards,
            **{k: v for k, v in raw.items() if k in known},
        )

    def shard_count(self) -> int:
        return len(self.shards)

    def residues(self) -> int:
        return sum(s.residues for s in self.shards)

    def clusters(self) -> int:
        return sum(s.clusters for s in self.shards)

    def check_self_consistent(self) -> None:
        """Catch a manifest that is internally impossible before anything is downloaded."""
        if self.buckets != len(self.shards):
            raise ShardStoreError(
                f"manifest declares {self.buckets} buckets but lists {len(self.shards)} shards"
            )
        indices = sorted(s.index for s in self.shards)
        if indices != list(range(self.buckets)):
            raise ShardStoreError(f"shard indices are not 0..{self.buckets - 1}: {indices}")
        if self.clusters() > self.corpus_clusters:
            raise ShardStoreError(
                f"sample holds {self.clusters():,} clusters, more than the "
                f"{self.corpus_clusters:,} it was drawn from"
            )
        if self.viral_seeded_clusters > self.corpus_clusters:
            raise ShardStoreError("more viral-seeded clusters than clusters")
        if self.seed_counts:
            # `seeded` is what `SeedCounts.to_dict` emits since D-139 renamed the counters to
            # be denylist-neutral; `viral_seeded` is what the already-staged 2.5% sample
            # manifest carries, and that object cannot be rewritten — the corpus bucket has no
            # DeleteObject. Both spellings are accepted rather than bumping the manifest
            # version, because a version bump makes `from_json` refuse the staged manifest
            # outright, and that manifest is the input the A1.8 pass reads.
            for field_names, scalar in (
                (("clusters",), self.corpus_clusters),
                (("seeded", "viral_seeded"), self.viral_seeded_clusters),
            ):
                carried = next(
                    (
                        self.seed_counts[name]
                        for name in field_names
                        if self.seed_counts.get(name) is not None
                    ),
                    None,
                )
                field_name = field_names[0]
                if carried is not None and carried != scalar:
                    raise ShardStoreError(
                        f"manifest disagrees with itself: seed_counts[{field_name!r}] is "
                        f"{carried:,} but the field says {scalar:,}"
                    )


def sample_prefix(release: str, tier: str, sample_rate: int) -> str:
    """Where a staged sample lives, keyed by everything that changes its contents.

    The sample rate is in the path rather than only in the manifest: the bucket cannot delete,
    so two rates must be able to coexist, and a path that collided would overwrite a staged
    sample with a differently-drawn one of the same name.
    """
    return f"samples/a1-6/{tier}/{release}/rate{sample_rate}"


def plan_uploads(
    prefix: str,
    shard_paths: Iterable[Path],
    seed_fasta: Path,
) -> list[tuple[Path, str]]:
    """Local file to key, for every object a staging run will write.

    Returned rather than uploaded so a caller can show the keys and refuse before writing
    anything: in a bucket with no `DeleteObject`, the moment to be sure about a key is before
    the `PutObject`, not after.
    """
    plan = [(seed_fasta, f"{prefix}/{seed_fasta.name}")]
    plan += [(p, f"{prefix}/{p.name}") for p in shard_paths]
    return plan


def describe(path: Path, key: str) -> StagedObject:
    return StagedObject(key=key, sha256=sha256_file(path), bytes=path.stat().st_size)


def describe_shard(path: Path, key: str, index: int, clusters: int, residues: int) -> StagedShard:
    return StagedShard(
        key=key,
        sha256=sha256_file(path),
        bytes=path.stat().st_size,
        index=index,
        clusters=clusters,
        residues=residues,
    )


def verify_all(manifest: ShardManifest, local: dict[str, Path]) -> None:
    """Verify every staged object against its recorded digest, or raise.

    All of them, not a sample: the whole point is that nothing downstream has to wonder which
    bytes it searched.
    """
    manifest.check_self_consistent()
    missing = [o.key for o in [manifest.seed_fasta, *manifest.shards] if o.key not in local]
    if missing:
        raise ShardStoreError(f"staged objects were not fetched: {missing}")
    manifest.seed_fasta.verify(local[manifest.seed_fasta.key])
    for shard in manifest.shards:
        shard.verify(local[shard.key])


def existing_keys(client: Any, bucket: str, prefix: str) -> set[str]:
    """Keys already under a staging prefix, so a run can refuse to overwrite one."""
    keys: set[str] = set()
    token: str | None = None
    while True:
        kwargs: dict[str, Any] = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        page = client.list_objects_v2(**kwargs)
        keys.update(o["Key"] for o in page.get("Contents", []))
        if not page.get("IsTruncated"):
            return keys
        token = page.get("NextContinuationToken")
