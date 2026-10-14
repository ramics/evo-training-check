#!/usr/bin/env python3
"""Extract and verify the quotations inside `policies/specs/*.yaml` — task X1.4.

`tools/policies.py` verifies every blockquote in `policies/*.md` against the source it cites.
The spec files quote the same published prose, in rule `note:` fields and in the `#` comment
headers, and until this module nothing checked those. The specs are what downstream tasks
actually execute, so an unchecked quotation there is worse than one in the prose store.

Normalisation, source loading and text extraction are `tools/policies.py`'s, deliberately
reused rather than reimplemented: two normalisers that drift apart would mean a quote passing
in one store and failing in the other.

Two things differ from the markdown store and both are extraction problems:

**There is no citation marker.** A quotation's source is a field on the enclosing rule, so
attribution comes from the YAML structure. This module composes the YAML to a node tree, which
keeps line numbers, and walks it carrying the nearest enclosing `source:` downward — so a rule
note is checked against that rule's source, while `scope.note` falls back to the policy's.

**Quotations are inline and nest.** A note re-quotes inner double quotes as single quotes:
`"...labeled as 'High-confidence' according to..."` quotes a source that reads `labeled as
"High-confidence"`. So quote characters are folded together before comparison — `'` and `"`
become one character on both sides. The cost is that this check cannot see a changed quote
character; the alternative is not checking nested quotations at all, and a quote character is
not a difference in wording. Case, by contrast, *is* checked: see `policies.normalise`.

Pairing is the hazard A0.3 hit by hand — a naive extractor pairs one quotation's closing mark
with the next one's opening mark and reports nonsense. Guarded structurally: an odd number of
quote marks in a text unit is an error, not something to pair around.

Comment quotations are attributed to the union of the sources the file cites, rather than to
one. A comment is commentary and sits nowhere in particular in the structure; the `note:`
fields are the operative text and are attributed exactly. The check on a comment quotation is
therefore that it appears in *some* source this policy is built from, which is weaker, and
stated here so nobody reads it as the stronger claim.
"""

from __future__ import annotations

import dataclasses
import importlib.util
import pathlib
import sys

import yaml

_POLICIES_PATH = pathlib.Path(__file__).resolve().parent / "policies.py"
_spec = importlib.util.spec_from_file_location("amazebio_policies_tool", _POLICIES_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - layout error, not logic
    raise RuntimeError(f"cannot load {_POLICIES_PATH}")
policies = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(policies)

REPO = pathlib.Path(__file__).resolve().parent.parent

QUOTE_CHARS = "\"'"
QUOTE_SENTINEL = '"'


class SpecQuoteError(Exception):
    pass


@dataclasses.dataclass(frozen=True, slots=True)
class Quotation:
    """One quotation found in a spec file, with the sources it may be checked against."""

    line: int
    text: str
    sources: tuple[str, ...]
    where: str  # "note" or "comment", for the error message


def fold(text: str) -> str:
    """`policies.match_key`, plus folding the two quote characters together.

    Applied to both the quotation and the source text, so the fold cannot make a wrong
    quotation match a different wording — only a different quote character.
    """
    out = policies.match_key(text)
    for ch in QUOTE_CHARS:
        out = out.replace(ch, QUOTE_SENTINEL)
    return out


def _sentence_initial_variants(needle: str) -> list[str]:
    """The quotation, and the same with its first letter's case flipped.

    A fragment quoted at the start of a sentence gets a capital it does not have in the
    source — `"Almost exclusively" stays unquantified` quotes text reading "almost
    exclusively". English sentence capitalisation is not a difference in wording, so the
    first character is matched either way. Only the first: a changed capital anywhere else
    is the error X1.4 exists to catch, and the one it found in `corpora.md`.
    """
    if not needle or not needle[0].isalpha():
        return [needle]
    flipped = needle[0].swapcase() + needle[1:]
    return [needle, flipped]


def quoted_spans(text: str, *, context: str) -> list[tuple[str, str | None]]:
    """Quotation spans in one text unit, each with an inline source override if marked.

    Returns (span, source_id_or_None), pairing quote marks left to right. A quotation whose
    source is not the enclosing rule's is marked inline with the same syntax the markdown
    store uses — `[source: S-ESM3-HF-OPEN] "data related to viruses has been removed"` — and
    the marker nearest before the opening quote wins.
    """
    positions = [i for i, ch in enumerate(text) if ch == '"']
    if len(positions) % 2:
        raise SpecQuoteError(
            f"{context}: odd number of double-quote marks ({len(positions)}), so the "
            "quotations cannot be paired. A quotation must open and close, and in a spec file "
            "a double-quoted span is a verbatim quotation — write our own phrasing in single "
            "quotes so it is not checked against a source it never came from."
        )
    spans: list[tuple[str, str | None]] = []
    previous_close = -1
    for open_at, close_at in zip(positions[0::2], positions[1::2], strict=True):
        span = text[open_at + 1 : close_at].strip()
        # Only a marker in the gap since the last quotation closed can apply to this one,
        # so a marker does not leak forward onto quotations it was not written for.
        markers = policies.MARKER.findall(text[previous_close + 1 : open_at])
        previous_close = close_at
        if span:
            spans.append((span, markers[-1][0] if markers else None))
    return spans


def _comment_blocks(path: pathlib.Path) -> list[tuple[int, str]]:
    """Contiguous runs of `#` comment lines, joined, with the line the run starts on."""
    blocks: list[tuple[int, str]] = []
    run: list[str] = []
    start = 0
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw.strip()
        if stripped.startswith("#"):
            if not run:
                start = n
            run.append(stripped.lstrip("#").strip())
        elif run:
            blocks.append((start, " ".join(run).strip()))
            run = []
    if run:
        blocks.append((start, " ".join(run).strip()))
    return blocks


def _walk(node: yaml.Node, inherited: str | None, found: list[tuple[int, str, str | None]]) -> None:
    """Collect (line, note_text, source) from a composed YAML tree, inheriting `source:`."""
    if isinstance(node, yaml.MappingNode):
        source = inherited
        for key, value in node.value:
            if (
                isinstance(key, yaml.ScalarNode)
                and key.value == "source"
                and isinstance(value, yaml.ScalarNode)
            ):
                source = value.value
        for key, value in node.value:
            if not isinstance(key, yaml.ScalarNode):
                continue
            if key.value == "note" and isinstance(value, yaml.ScalarNode):
                found.append((value.start_mark.line + 1, value.value, source))
            else:
                _walk(value, source, found)
    elif isinstance(node, yaml.SequenceNode):
        for item in node.value:
            _walk(item, inherited, found)


def _attribute(marked: str | None, primary: str | None, cited: list[str]) -> tuple[str, ...]:
    """The sources a quotation may be checked against, most specific first.

    An explicit inline marker is exact and does not fall back: a marker is an assertion about
    provenance, so a typo'd or unretrieved id must fail as that, rather than quietly passing
    because the text also happens to appear in another source the file cites.
    """
    if marked:
        return (marked,)
    ordered = ([primary] if primary else []) + [s for s in cited if s != primary]
    return tuple(ordered)


def spec_quotations(path: pathlib.Path) -> list[Quotation]:
    """Every quotation in one spec file, with the sources it may be checked against."""
    text = path.read_text(encoding="utf-8")
    root = yaml.compose(text)
    if root is None:
        raise SpecQuoteError(f"{path.name}: empty spec")

    notes: list[tuple[int, str, str | None]] = []
    _walk(root, None, notes)

    cited = sorted({source for _, _, source in notes if source})
    policy_source = None
    if isinstance(root, yaml.MappingNode):
        for key, value in root.value:
            if isinstance(key, yaml.ScalarNode) and key.value == "policy":
                _walk(value, None, [])
                if isinstance(value, yaml.MappingNode):
                    for k2, v2 in value.value:
                        if (
                            isinstance(k2, yaml.ScalarNode)
                            and k2.value == "source"
                            and isinstance(v2, yaml.ScalarNode)
                        ):
                            policy_source = v2.value
    if policy_source and policy_source not in cited:
        cited = sorted({*cited, policy_source})

    quotations: list[Quotation] = []
    for line, note, source in notes:
        # The enclosing rule's source first, then the file's other cited sources. A note
        # legitimately quotes across sources — the charitable ESM3 reading quotes the model
        # card to say why it is *not* following it — so exact attribution would fail on
        # faithful quotations. The matched source is reported, and the check still catches a
        # paraphrase: the text must appear verbatim in a source this policy is built from.
        for span, marked in quoted_spans(note, context=f"{path.name}:{line}"):
            quotations.append(
                Quotation(line, span, _attribute(marked, source or policy_source, cited), "note")
            )
    for line, block in _comment_blocks(path):
        for span, marked in quoted_spans(block, context=f"{path.name}:{line} (comment)"):
            quotations.append(Quotation(line, span, _attribute(marked, None, cited), "comment"))
    return quotations


def verify(
    specs_dir: pathlib.Path,
    *,
    verbose: bool = False,
) -> tuple[list[str], int]:
    """Check every quotation in every spec. Returns (problems, number verified)."""
    sources = policies.load_sources()
    text_cache: dict[str, str] = {}

    def source_text(sid: str) -> str | None:
        if sid in text_cache:
            return text_cache[sid]
        entry = sources.get(sid)
        if entry is None or entry["status"] != "retrieved" or not entry.get("capture"):
            return None
        path = REPO / entry["capture"]
        if not path.exists():
            return None
        text_cache[sid] = fold(policies.extract(path))
        return text_cache[sid]

    problems: list[str] = []
    verified = 0
    for spec in sorted(specs_dir.glob("*.yaml")):
        try:
            quotations = spec_quotations(spec)
        except (SpecQuoteError, yaml.YAMLError) as exc:
            problems.append(str(exc))
            continue
        for q in quotations:
            where = f"{spec.name}:{q.line}"
            if not q.sources:
                problems.append(f"{where}: quotation with no source to check it against")
                continue
            usable = [sid for sid in q.sources if source_text(sid) is not None]
            if not usable:
                problems.append(
                    f"{where}: quotation cites {', '.join(q.sources)}, none of which is a "
                    "retrieved, stored source. A quotation may only cite text somebody read."
                )
                continue
            needles = _sentence_initial_variants(fold(q.text))
            matched = next(
                (sid for sid in usable if any(n in (source_text(sid) or "") for n in needles)),
                None,
            )
            if matched is None:
                problems.append(
                    f"{where}: quoted text does not appear in "
                    f"{' or '.join(usable)}: {q.text[:80]!r}. Either the wording is wrong or "
                    "the source is."
                )
                continue
            verified += 1
            if verbose:
                print(f"  ok {where} ({q.where}) -> {matched}")
    return problems, verified


def main() -> int:
    problems, verified = verify(REPO / "policies" / "specs", verbose="--verbose" in sys.argv)
    for p in problems:
        print(f"problem: {p}", file=sys.stderr)
    print(f"spec quotations: {verified} verified, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
