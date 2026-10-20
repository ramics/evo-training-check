"""The viral assay register — task B2.2.

`DESIGN.md` §B2 calls the viral subset's small n the study's biggest statistical threat and
asks for a curated extension. D-010 then narrowed the task: establish first whether published
collections already give sufficient n, and extend only if they do not. This module is the
machinery for establishing it — placing each benchmark assay in the taxonomy, deciding whether
each model's filter would have excluded its protein's family, and counting the cells the §B5
regression actually has to work with.

**Why the organism is resolved rather than read off.** The benchmark's reference file carries a
free-text `source_organism` and a UniProt entry name, and neither is a taxonomic placement. The
denylists act on ICTV family and order, so an assay's exclusion status is a question about its
lineage, and a lineage guessed from a strain string is a guess. Resolution is therefore
two-tiered and both tiers are recorded per assay: **UniProt** for the entry's own organism
taxid, and, where UniProt no longer holds the entry, the benchmark's `source_organism` matched
against the pinned NCBI taxonomy. Four of the benchmark's viral entries are in the second tier
because UniProt has **deleted** them as "not part of a reference proteome" — a provenance fact
B2.4 needs and which nothing in the benchmark's own files records.

**Why exclusion status is not one variable.** §B5's regression takes model-exclusion-status as
the interaction term, and the two model families decide it by different machinery. Evo's
policies remove by taxon name, so an assay's status follows from its lineage and is settled
here. ESM3-open's remove by *sequence similarity* to a seed set, so no family name settles it
and an assay's status there is a computation over the target sequence, not a lookup. Treating
the two as one column would silently assert a placement for ESM3 that nothing computed.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterable, Mapping
from typing import Any

__all__ = [
    "VIRAL_ASSAY_ORGANISMS",
    "AssayPlacement",
    "AssayRegisterError",
    "Organism",
    "cross_tab",
    "place",
    "usable_n",
]


class AssayRegisterError(RuntimeError):
    """Raised when an assay cannot be placed from pinned inputs rather than guessed at."""


@dataclasses.dataclass(frozen=True, slots=True)
class Organism:
    """The organism an assay's target protein comes from, and where that was established.

    `source` is part of the record because the two tiers are not equally strong. `uniprot` is
    the entry's own organism. `proteingym-name` is the benchmark's free-text organism matched
    against the pinned NCBI taxonomy, used only where UniProt has deleted the entry, and it
    places the assay at whatever rank that name carries — which for a strain string can be
    coarser than the entry would have been.
    """

    taxid: int
    name: str
    accession: str | None
    source: str
    note: str = ""


#: Resolved 2026-10-20 against UniProt and the pinned NCBI taxonomy dump of 2023-04-01
#: (`amazebio.seeds.TAXDUMP_2023_04`). Pinned here rather than resolved afresh each run because
#: UniProt is a live service: a silently changed taxid would move an assay between the excluded
#: and retained arms of the §B5 contrast with nothing in the artefact saying so. The register
#: tool re-resolves and **refuses** on disagreement rather than taking the new value.
VIRAL_ASSAY_ORGANISMS: dict[str, Organism] = {
    "A0A140D2T1_ZIKV": Organism(
        64320, "Zika virus", None, "proteingym-name", "UniProt deleted A0A140D2T1"
    ),
    "A0A192B1T2_9HIV1": Organism(
        11676,
        "Human immunodeficiency virus 1",
        None,
        "proteingym-name",
        "UniProt deleted A0A192B1T2",
    ),
    "A0A2Z5U3Z0_9INFA": Organism(
        382835,
        "Influenza A virus (A/WSN/1933(H1N1))",
        None,
        "proteingym-name",
        "UniProt deleted A0A2Z5U3Z0",
    ),
    "A4D664_9INFA": Organism(
        370139,
        "Influenza A virus (A/green-winged teal/Ohio/175/1986(H2N1))",
        None,
        "proteingym-name",
        "UniProt deleted A4D664",
    ),
    "C6KNH7_9INFA": Organism(654811, "Influenza A virus", "C6KNH7", "uniprot"),
    "CAPSD_AAV2S": Organism(
        648242, "Adeno-associated virus 2 (isolate Srivastava/1982)", "P03135", "uniprot"
    ),
    "ENV_HV1B9": Organism(
        401671,
        "Human immunodeficiency virus type 1 group M subtype B (strain 89.6)",
        "Q73372",
        "uniprot",
    ),
    "ENV_HV1BR": Organism(
        11686,
        "Human immunodeficiency virus type 1 group M subtype B (isolate BRU/LAI)",
        "P03377",
        "uniprot",
    ),
    "HCP_LAMBD": Organism(2681611, "Escherichia phage lambda", "P68660", "uniprot"),
    "I6TAH8_I68A0": Organism(
        387139, "Influenza A virus (strain A/Aichi/2/1968 H3N2)", "I6TAH8", "uniprot"
    ),
    "NCAP_I34A1": Organism(
        211044, "Influenza A virus (strain A/Puerto Rico/8/1934 H1N1)", "P03466", "uniprot"
    ),
    "NRAM_I33A0": Organism(
        381518, "Influenza A virus (strain A/Wilson-Smith/1933 H1N1)", "P03470", "uniprot"
    ),
    "PA_I34A1": Organism(
        211044, "Influenza A virus (strain A/Puerto Rico/8/1934 H1N1)", "P03433", "uniprot"
    ),
    "POLG_CXB3N": Organism(103903, "Coxsackievirus B3 (strain Nancy)", "P03313", "uniprot"),
    "POLG_DEN26": Organism(
        31634, "Dengue virus type 2 (strain Thailand/16681/1984)", "P29990", "uniprot"
    ),
    "POLG_HCVJF": Organism(
        356411, "Hepatitis C virus genotype 2a (isolate JFH-1)", "Q99IB8", "uniprot"
    ),
    "POLG_PESV": Organism(
        523795,
        "Porcine enteric sapovirus (isolate Swine/United States/Cowden/1980)",
        "Q9QEJ5",
        "uniprot",
    ),
    "Q2N0S5_9HIV1": Organism(11676, "Human immunodeficiency virus type 1", "Q2N0S5", "uniprot"),
    "R1AB_SARS2": Organism(
        2697049, "Severe acute respiratory syndrome coronavirus 2", "P0DTD1", "uniprot"
    ),
    "RCRO_LAMBD": Organism(2681611, "Escherichia phage lambda", "P03040", "uniprot"),
    "RDRP_I33A0": Organism(
        381518, "Influenza A virus (strain A/Wilson-Smith/1933 H1N1)", "P03430", "uniprot"
    ),
    "REV_HV1H2": Organism(
        11706,
        "Human immunodeficiency virus type 1 group M subtype B (isolate HXB2)",
        "P04618",
        "uniprot",
    ),
    "RPC1_BP434": Organism(10712, "Enterobacteria phage 434", "P16117", "uniprot"),
    "RPC1_LAMBD": Organism(2681611, "Escherichia phage lambda", "P03034", "uniprot"),
    "SPIKE_SARS2": Organism(
        2697049, "Severe acute respiratory syndrome coronavirus 2", "P0DTC2", "uniprot"
    ),
    "TAT_HV1BR": Organism(
        11686,
        "Human immunodeficiency virus type 1 group M subtype B (isolate BRU/LAI)",
        "P04610",
        "uniprot",
    ),
    "VG08_BPP22": Organism(10754, "Salmonella phage P22", "P26748", "uniprot"),
    "VRPI_BPT7": Organism(10760, "Escherichia phage T7", "P03704", "uniprot"),
}

#: What a taxonomy with no node at a rank gets. Kept as its own value rather than folded into
#: "not excluded": a lineage carrying no family node is not a member of some other family, and
#: D-140 and D-141 both say why pooling such cases into a neighbouring stratum distorts the
#: interval. Several bacteriophage assays land here, and they are the within-study control.
NO_RANK = "(no node at this rank)"


@dataclasses.dataclass(frozen=True, slots=True)
class AssayPlacement:
    """One assay, placed in the taxonomy and against each policy's denylist."""

    dms_id: str
    uniprot_id: str
    organism: Organism
    family: str
    order: str
    #: policy id -> whether that policy's denylist names this assay's family or order.
    excluded_by: Mapping[str, bool]
    #: policy id -> why the status could not be read from taxonomy, where that is the case.
    undecidable_by: Mapping[str, str]
    selection_type: str
    msa_depth_category: str
    n_variants: int
    seq_len: int
    doi: str

    def to_dict(self) -> dict[str, Any]:
        d = dataclasses.asdict(self)
        d["excluded_by"] = dict(self.excluded_by)
        d["undecidable_by"] = dict(self.undecidable_by)
        return d


def place(
    assay: Any,
    *,
    lineage: Mapping[str, str],
    denylists: Mapping[str, Any],
    similarity_policies: Mapping[str, str],
) -> AssayPlacement:
    """Place one assay: its lineage, and each policy's verdict on it.

    `denylists` maps policy id to a `misassignment.Denylist`; `similarity_policies` maps a
    policy id to the reason its verdict cannot be read from taxonomy at all. Every policy the
    project has must appear in one of the two, so that a policy added later cannot pass through
    this register with no verdict and no reason — which is how a missing arm becomes an
    apparently complete table.
    """
    organism = VIRAL_ASSAY_ORGANISMS.get(assay.uniprot_id)
    if organism is None:
        raise AssayRegisterError(
            f"{assay.dms_id}: no pinned organism for UniProt entry {assay.uniprot_id!r}. "
            "Resolve it and add it to VIRAL_ASSAY_ORGANISMS rather than letting the assay "
            "into the register unplaced: an unplaced assay silently joins the retained arm."
        )
    overlap = set(denylists) & set(similarity_policies)
    if overlap:
        raise AssayRegisterError(
            f"policies {sorted(overlap)} are declared both taxon-decidable and not; one of the "
            "two readings is wrong and the register must not pick"
        )
    family = lineage.get("family") or NO_RANK
    order = lineage.get("order") or NO_RANK
    return AssayPlacement(
        dms_id=assay.dms_id,
        uniprot_id=assay.uniprot_id,
        organism=organism,
        family=family,
        order=order,
        excluded_by={
            policy: bool(
                (family in d.families and family != NO_RANK)
                or (order in d.orders and order != NO_RANK)
            )
            for policy, d in sorted(denylists.items())
        },
        undecidable_by=dict(sorted(similarity_policies.items())),
        selection_type=assay.selection_type or "(not stated)",
        msa_depth_category=assay.msa_depth_category,
        n_variants=assay.n_variants,
        seq_len=assay.seq_len,
        doi=assay.doi,
    )


def cross_tab(
    placements: Iterable[AssayPlacement], policy: str, attribute: str
) -> dict[str, dict[str, int]]:
    """`excluded`/`retained` against one assay attribute, for one policy.

    The §B5 regression's interaction term needs both arms populated at every level of the
    covariates it adjusts for. A covariate that is constant within an arm cannot be separated
    from the interaction, so the cross-tabulation is the thing that says whether the design is
    identifiable — not the total count.
    """
    out: dict[str, dict[str, int]] = {"excluded": {}, "retained": {}}
    for p in placements:
        arm = "excluded" if p.excluded_by.get(policy) else "retained"
        value = str(getattr(p, attribute))
        out[arm][value] = out[arm].get(value, 0) + 1
    return out


def usable_n(placements: Iterable[AssayPlacement], policy: str) -> dict[str, Any]:
    """Assays per arm, and the covariate levels that appear in only one of them.

    A level present in one arm only is a **confound**, not a small cell: within that level the
    arm is determined, so the regression cannot tell the covariate's effect from the effect
    being measured. Reporting it here, before any score is computed, is what lets B5.1 fix the
    analysis plan against a design it can actually identify.
    """
    rows = list(placements)
    excluded = [p for p in rows if p.excluded_by.get(policy)]
    retained = [p for p in rows if not p.excluded_by.get(policy)]
    confounded: dict[str, dict[str, list[str]]] = {}
    for attribute in ("selection_type", "msa_depth_category", "family"):
        tab = cross_tab(rows, policy, attribute)
        only_excluded = sorted(set(tab["excluded"]) - set(tab["retained"]))
        only_retained = sorted(set(tab["retained"]) - set(tab["excluded"]))
        confounded[attribute] = {
            "only_in_excluded_arm": only_excluded,
            "only_in_retained_arm": only_retained,
            "in_both_arms": sorted(set(tab["excluded"]) & set(tab["retained"])),
        }
    return {
        "policy": policy,
        "assays": len(rows),
        "excluded_arm": len(excluded),
        "retained_arm": len(retained),
        "distinct_families_excluded": len({p.family for p in excluded}),
        "distinct_families_retained": len({p.family for p in retained}),
        "covariate_overlap": confounded,
    }
