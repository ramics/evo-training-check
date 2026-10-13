"""Tests for amazebio.policyspec.

Three groups matter more than the rest:

* **Unspecified values** — an unstated threshold must produce `UNDETERMINED`, never a guess.
  If this regresses, the project silently invents a number and reports it as a finding.
* **Out-of-scope** — a record in a component the filter never acted on is `OUT_OF_SCOPE`, not
  `RETAINED`. Collapsing those two would erase the main Phase A finding.
* **The real specs** — the committed policies load, and the Evo pipeline behaves on fixtures
  the way the published prose says it should.
"""

from __future__ import annotations

import pathlib
import textwrap

import pytest

from amazebio.policyspec import (
    Outcome,
    PolicyError,
    Record,
    Unspecified,
    describe,
    evaluate,
    load_policy,
    load_policy_dir,
)

SPECS = pathlib.Path(__file__).resolve().parent.parent / "policies" / "specs"

MINIMAL = """
policy:
  id: t-literal
  model: Test
  reading: literal
  source: S-EVO1-PREPRINT
  scope:
    components: [IMG/VR]
  rules:
    - id: drop-families
      kind: remove_if_taxon_in
      source: S-EVO1-PREPRINT
      params:
        rank: family
        names: [Filoviridae]
"""


def write(tmp_path, text, name="p.yaml"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text))
    return p


class TestSchemaValidation:
    def test_minimal_policy_loads(self, tmp_path):
        policy = load_policy(write(tmp_path, MINIMAL))
        assert policy.id == "t-literal"
        assert policy.scope.components == ["IMG/VR"]
        assert policy.is_determined

    @pytest.mark.parametrize(
        ("mutation", "match"),
        [
            ("reading: sideways", "reading must be one of"),
            ("kind: remove_if_vibes", "unknown rule kind"),
        ],
    )
    def test_rejects_bad_values(self, tmp_path, mutation, match):
        key, _, value = mutation.partition(": ")
        text = MINIMAL.replace(
            f"{key}: literal" if key == "reading" else "kind: remove_if_taxon_in",
            f"{key}: {value}",
        )
        with pytest.raises(PolicyError, match=match):
            load_policy(write(tmp_path, text))

    def test_rejects_missing_rule_param(self, tmp_path):
        text = MINIMAL.replace("        rank: family\n", "")
        with pytest.raises(PolicyError, match="needs param"):
            load_policy(write(tmp_path, text))

    def test_rejects_unexpected_rule_param(self, tmp_path):
        text = MINIMAL.replace(
            "        names: [Filoviridae]", "        names: [X]\n        extra: 1"
        )
        with pytest.raises(PolicyError, match="unexpected param"):
            load_policy(write(tmp_path, text))

    def test_rejects_unknown_policy_field(self, tmp_path):
        with pytest.raises(PolicyError, match="unknown policy field"):
            load_policy(write(tmp_path, MINIMAL + "  surprise: yes\n"))

    def test_rejects_empty_scope(self, tmp_path):
        text = MINIMAL.replace("    components: [IMG/VR]", "    components: []")
        with pytest.raises(PolicyError, match="non-empty list"):
            load_policy(write(tmp_path, text))

    def test_rejects_duplicate_rule_ids(self, tmp_path):
        rule = MINIMAL[MINIMAL.index("    - id: drop-families") :]
        with pytest.raises(PolicyError, match="duplicate rule id"):
            load_policy(write(tmp_path, MINIMAL + rule))

    def test_rejects_file_without_policy_key(self, tmp_path):
        with pytest.raises(PolicyError, match="top-level `policy:`"):
            load_policy(write(tmp_path, "something_else: 1\n"))

    def test_rejects_invalid_yaml(self, tmp_path):
        with pytest.raises(PolicyError, match="not valid YAML"):
            load_policy(write(tmp_path, "policy: [unclosed\n"))


class TestUnspecified:
    """An unstated value must never become a silent default."""

    SPEC = """
    policy:
      id: u-literal
      model: Test
      reading: literal
      source: S-ESM3-PREPRINT
      scope:
        components: [UniRef]
      rules:
        - id: drop-similar
          kind: remove_if_similar_to
          source: S-ESM3-PREPRINT
          params:
            seed_set: viral-denylist
            identity_threshold:
              unspecified: the source never states it
    """

    def test_parses_as_unspecified(self, tmp_path):
        policy = load_policy(write(tmp_path, self.SPEC))
        rule = policy.rules[0]
        assert isinstance(rule.params["identity_threshold"], Unspecified)
        assert rule.unspecified_params() == ["identity_threshold"]
        assert not policy.is_determined
        assert policy.unspecified() == {"drop-similar": ["identity_threshold"]}

    def test_evaluation_is_undetermined_not_a_guess(self, tmp_path):
        policy = load_policy(write(tmp_path, self.SPEC))
        record = Record(id="r1", component="UniRef", similarity_hits={"viral-denylist": 0.9})
        [decision] = evaluate(policy, [record])
        assert decision.outcome is Outcome.UNDETERMINED
        assert decision.outcome is not Outcome.REMOVED
        assert decision.outcome is not Outcome.RETAINED
        assert "does not state" in decision.why

    def test_unspecified_needs_a_reason(self, tmp_path):
        text = self.SPEC.replace("unspecified: the source never states it", "unspecified: ''")
        with pytest.raises(PolicyError, match="non-empty reason"):
            load_policy(write(tmp_path, text))

    def test_describe_flags_the_gap(self, tmp_path):
        rendered = describe(load_policy(write(tmp_path, self.SPEC)))
        assert "NOT FULLY DETERMINED" in rendered
        assert "UNSPECIFIED" in rendered


class TestScope:
    """Out-of-scope is not the same as retained. This distinction is the Phase A finding."""

    def test_record_outside_scope_is_out_of_scope(self, tmp_path):
        policy = load_policy(write(tmp_path, MINIMAL))
        record = Record(
            id="r1", component="NCBI-eukaryotic-genomes", taxonomy={"family": "Filoviridae"}
        )
        [decision] = evaluate(policy, [record])
        assert decision.outcome is Outcome.OUT_OF_SCOPE
        assert decision.outcome is not Outcome.RETAINED
        assert "not in this policy's scope" in decision.why

    def test_same_record_in_scope_is_removed(self, tmp_path):
        """The identical record, in the component the filter was pointed at, is removed.

        This pair is the finding in miniature: what decides the outcome is not the sequence but
        which file it was in.
        """
        policy = load_policy(write(tmp_path, MINIMAL))
        in_scope = Record(id="r1", component="IMG/VR", taxonomy={"family": "Filoviridae"})
        [decision] = evaluate(policy, [in_scope])
        assert decision.outcome is Outcome.REMOVED
        assert decision.rule_id == "drop-families"


class TestRuleKinds:
    def _policy(self, tmp_path, rule_yaml):
        """Build a one-rule policy around `rule_yaml`, which is a YAML list item."""
        rules = textwrap.indent(textwrap.dedent(rule_yaml).strip(), "    ")
        text = (
            "policy:\n"
            "  id: k-literal\n"
            "  model: Test\n"
            "  reading: literal\n"
            "  source: S-EVO1-PREPRINT\n"
            "  scope:\n"
            "    components: [IMG/VR]\n"
            "  rules:\n" + rules + "\n"
        )
        path = tmp_path / "k.yaml"
        path.write_text(text)
        return load_policy(path)

    def test_keep_if_attribute_in(self, tmp_path):
        policy = self._policy(
            tmp_path,
            """
            - id: keep-hc
              kind: keep_if_attribute_in
              source: S-EVO1-PREPRINT
              params:
                attribute: confidence
                values: ["High-confidence"]
            """,
        )
        out = evaluate(
            policy,
            [
                Record(id="hc", component="IMG/VR", attributes={"confidence": "High-confidence"}),
                Record(id="lc", component="IMG/VR", attributes={"confidence": "Low-confidence"}),
                Record(id="none", component="IMG/VR"),
            ],
        )
        assert [d.outcome for d in out] == [Outcome.RETAINED, Outcome.REMOVED, Outcome.REMOVED]

    def test_keep_one_per(self, tmp_path):
        policy = self._policy(
            tmp_path,
            """
            - id: dedupe
              kind: keep_one_per
              source: S-EVO1-PREPRINT
              params:
                attribute: vOTU
            """,
        )
        out = evaluate(
            policy,
            [
                Record(id="a", component="IMG/VR", attributes={"vOTU": "v1"}),
                Record(id="b", component="IMG/VR", attributes={"vOTU": "v1"}),
                Record(id="c", component="IMG/VR", attributes={"vOTU": "v2"}),
            ],
        )
        assert [d.outcome for d in out] == [Outcome.RETAINED, Outcome.REMOVED, Outcome.RETAINED]

    def test_keep_if_host_occurrence_at_least(self, tmp_path):
        policy = self._policy(
            tmp_path,
            """
            - id: host-twice
              kind: keep_if_host_occurrence_at_least
              source: S-EVO1-PREPRINT
              params:
                host_class: prokaryotic
                count: 2
            """,
        )
        out = evaluate(
            policy,
            [
                Record(id="twice", component="IMG/VR", host_occurrences={"prokaryotic": 2}),
                Record(id="once", component="IMG/VR", host_occurrences={"prokaryotic": 1}),
                Record(id="never", component="IMG/VR"),
            ],
        )
        assert [d.outcome for d in out] == [Outcome.RETAINED, Outcome.REMOVED, Outcome.REMOVED]

    def test_remove_if_unspecific(self, tmp_path):
        policy = self._policy(
            tmp_path,
            """
            - id: unspecific
              kind: remove_if_unspecific
              source: S-EVO1-PREPRINT
              params:
                require_rank: realm
                ranks: [realm, kingdom, family]
                stop_taxa: [Riboviria]
            """,
        )
        out = evaluate(
            policy,
            [
                Record(
                    id="placed",
                    component="IMG/VR",
                    taxonomy={"realm": "Riboviria", "family": "Fam"},
                ),
                Record(id="stops-at-realm", component="IMG/VR", taxonomy={"realm": "Riboviria"}),
                Record(id="no-realm", component="IMG/VR", taxonomy={"family": "Fam"}),
            ],
        )
        assert [d.outcome for d in out] == [Outcome.RETAINED, Outcome.REMOVED, Outcome.REMOVED]

    def test_remove_if_similar_to_respects_threshold(self, tmp_path):
        policy = self._policy(
            tmp_path,
            """
            - id: similar
              kind: remove_if_similar_to
              source: S-ESM3-PREPRINT
              params:
                seed_set: viral-denylist
                identity_threshold: 0.5
            """,
        )
        out = evaluate(
            policy,
            [
                Record(id="above", component="IMG/VR", similarity_hits={"viral-denylist": 0.7}),
                Record(id="at", component="IMG/VR", similarity_hits={"viral-denylist": 0.5}),
                Record(id="below", component="IMG/VR", similarity_hits={"viral-denylist": 0.3}),
                Record(id="nohit", component="IMG/VR"),
            ],
        )
        assert [d.outcome for d in out] == [
            Outcome.REMOVED,
            Outcome.REMOVED,
            Outcome.RETAINED,
            Outcome.RETAINED,
        ]


class TestCommittedSpecs:
    """The real specs in policies/specs/ must load and behave as the published prose reads."""

    def test_all_specs_load(self):
        policies = load_policy_dir(SPECS)
        assert {"evo1-literal", "esm3-open-literal"} <= set(policies)

    def test_evo_policy_scope_is_the_viral_component_only(self):
        policy = load_policy_dir(SPECS)["evo1-literal"]
        assert policy.scope.components == ["IMG/VR"]
        assert not policy.scope.covers("NCBI-eukaryotic-genomes")
        assert not policy.scope.covers("GTDB")

    def test_evo_policy_is_fully_determined(self):
        assert load_policy_dir(SPECS)["evo1-literal"].is_determined

    def test_esm3_policy_is_not_determined(self):
        policy = load_policy_dir(SPECS)["esm3-open-literal"]
        assert not policy.is_determined
        assert set(policy.unspecified()) == {
            "remove-viral-denylist-hits",
            "remove-select-agent-denylist-hits",
        }

    def test_evo_pipeline_on_fixtures(self):
        """A record for each outcome the published pipeline can produce."""
        policy = load_policy_dir(SPECS)["evo1-literal"]
        hc = {"confidence": "High-confidence"}
        records = [
            # survives every step: high confidence, unique vOTU, two prokaryotic sightings,
            # not denylisted, placed below realm
            Record(
                id="phage-ok",
                component="IMG/VR",
                attributes={**hc, "vOTU": "v1"},
                taxonomy={"realm": "Duplodnaviria", "family": "Straboviridae"},
                host_occurrences={"prokaryotic": 5},
            ),
            # denylisted family
            Record(
                id="filo",
                component="IMG/VR",
                attributes={**hc, "vOTU": "v2"},
                taxonomy={"realm": "Riboviria", "family": "Filoviridae"},
                host_occurrences={"prokaryotic": 3},
            ),
            # only ever seen once in a prokaryotic host
            Record(
                id="one-sighting",
                component="IMG/VR",
                attributes={**hc, "vOTU": "v3"},
                taxonomy={"realm": "Duplodnaviria", "family": "Straboviridae"},
                host_occurrences={"prokaryotic": 1},
            ),
            # the same filovirus sequence, sitting in a host genome the filter never saw
            Record(
                id="filo-eve-in-host-genome",
                component="NCBI-eukaryotic-genomes",
                attributes={**hc, "vOTU": "v4"},
                taxonomy={"realm": "Riboviria", "family": "Filoviridae"},
                host_occurrences={"prokaryotic": 0},
            ),
        ]
        by_id = {d.record_id: d for d in evaluate(policy, records)}
        assert by_id["phage-ok"].outcome is Outcome.RETAINED
        assert by_id["filo"].outcome is Outcome.REMOVED
        assert by_id["filo"].rule_id == "remove-denylisted-families"
        assert by_id["one-sighting"].outcome is Outcome.REMOVED
        assert by_id["one-sighting"].rule_id == "keep-prokaryotic-host-twice"
        # The finding, as a test: the filter removes this family from the viral files and never
        # looks at the host genomes that carry it.
        assert by_id["filo-eve-in-host-genome"].outcome is Outcome.OUT_OF_SCOPE

    def test_every_rule_cites_a_source(self):
        for policy in load_policy_dir(SPECS).values():
            for rule in policy.rules:
                assert rule.source, f"{policy.id}/{rule.id} cites no source"

    def test_describe_renders_every_spec(self):
        for policy in load_policy_dir(SPECS).values():
            rendered = describe(policy)
            assert policy.model in rendered
            assert all(r.id in rendered for r in policy.rules)


class TestReadingKinds:
    """The rule kinds A0.3 added for the charitable and strict readings."""

    def _policy(self, tmp_path, rule_yaml):
        """Build a one-rule charitable policy around `rule_yaml`, a YAML list item."""
        rules = textwrap.indent(textwrap.dedent(rule_yaml).strip(), "    ")
        text = (
            "policy:\n"
            "  id: t-charitable\n"
            "  model: Test\n"
            "  reading: charitable\n"
            "  source: S-EVO1-PREPRINT\n"
            "  scope:\n"
            "    components: [IMG/VR]\n"
            "  rules:\n" + rules + "\n"
        )
        path = tmp_path / "t.yaml"
        path.write_text(text)
        return load_policy(path)

    def test_remove_if_host_class_in_fires_on_any_occurrence(self, tmp_path):
        policy = self._policy(
            tmp_path,
            """
                    - id: euk
                      kind: remove_if_host_class_in
                      source: S-EVO2-PREPRINT
                      params:
                        host_classes: [eukaryotic]
            """,
        )
        out = {
            d.record_id: d
            for d in evaluate(
                policy,
                [
                    # one eukaryotic sighting is enough, even alongside many prokaryotic ones
                    Record(
                        id="mixed",
                        component="IMG/VR",
                        host_occurrences={"prokaryotic": 9, "eukaryotic": 1},
                    ),
                    Record(id="prok", component="IMG/VR", host_occurrences={"prokaryotic": 9}),
                    # a recorded zero is not evidence of a host
                    Record(id="zero", component="IMG/VR", host_occurrences={"eukaryotic": 0}),
                    Record(id="unknown", component="IMG/VR"),
                ],
            )
        }
        assert out["mixed"].outcome is Outcome.REMOVED
        assert out["prok"].outcome is Outcome.RETAINED
        assert out["zero"].outcome is Outcome.RETAINED
        assert out["unknown"].outcome is Outcome.RETAINED

    def test_host_evidence_exclusive_requires_positive_evidence(self, tmp_path):
        """The strict reading's point: absence of host evidence is not prokaryotic evidence."""
        policy = self._policy(
            tmp_path,
            """
                    - id: exclusive
                      kind: keep_if_host_evidence_exclusive
                      source: S-EVO1-PREPRINT
                      params:
                        host_class: prokaryotic
            """,
        )
        out = {
            d.record_id: d
            for d in evaluate(
                policy,
                [
                    Record(id="prok", component="IMG/VR", host_occurrences={"prokaryotic": 2}),
                    Record(
                        id="mixed",
                        component="IMG/VR",
                        host_occurrences={"prokaryotic": 9, "eukaryotic": 1},
                    ),
                    Record(id="none", component="IMG/VR"),
                ],
            )
        }
        assert out["prok"].outcome is Outcome.RETAINED
        assert out["mixed"].outcome is Outcome.REMOVED
        assert out["none"].outcome is Outcome.REMOVED
        assert "no host evidence at all" in out["none"].why

    def test_remove_if_element_detected(self, tmp_path):
        policy = self._policy(
            tmp_path,
            """
                    - id: elements
                      kind: remove_if_element_detected
                      source: S-EVO2-PREPRINT
                      params:
                        element_classes: [endogenous-viral-element, provirus]
            """,
        )
        out = {
            d.record_id: d
            for d in evaluate(
                policy,
                [
                    Record(
                        id="eve", component="IMG/VR", detected_elements=["endogenous-viral-element"]
                    ),
                    # prophage is not in the listed classes: phage retention is deliberate
                    Record(id="prophage", component="IMG/VR", detected_elements=["prophage"]),
                    Record(id="clean", component="IMG/VR"),
                ],
            )
        }
        assert out["eve"].outcome is Outcome.REMOVED
        assert out["prophage"].outcome is Outcome.RETAINED
        assert out["clean"].outcome is Outcome.RETAINED


class TestWildcardScopeAndRuleComponents:
    def test_wildcard_scope_covers_unnamed_components(self, tmp_path):
        policy = load_policy(
            write(
                tmp_path,
                """
                policy:
                  id: t-strict
                  model: Test
                  reading: strict
                  source: S-EVO2-PREPRINT
                  scope:
                    components: ["*"]
                  rules:
                    - id: elements
                      kind: remove_if_element_detected
                      source: S-EVO2-PREPRINT
                      params:
                        element_classes: [provirus]
                """,
            )
        )
        assert policy.scope.is_corpus_wide
        assert policy.scope.covers("a-component-nobody-enumerated")
        out = evaluate(
            policy, [Record(id="x", component="whatever", detected_elements=["provirus"])]
        )
        assert out[0].outcome is Outcome.REMOVED

    def test_rule_components_narrow_within_a_wildcard_scope(self, tmp_path):
        """A viral-taxonomy predicate must not be applied to a bacterial genome record."""
        policy = load_policy(
            write(
                tmp_path,
                """
                policy:
                  id: t-strict
                  model: Test
                  reading: strict
                  source: S-EVO2-PREPRINT
                  scope:
                    components: ["*"]
                  rules:
                    - id: unspecific
                      kind: remove_if_unspecific
                      components: [IMG/VR]
                      source: S-EVO1-PREPRINT
                      params:
                        require_rank: realm
                        ranks: [realm, family]
                        stop_taxa: []
                """,
            )
        )
        out = {
            d.record_id: d
            for d in evaluate(
                policy,
                [
                    # no viral realm, but the rule does not reach this component
                    Record(id="bacterium", component="GTDB", taxonomy={"phylum": "Bacillota"}),
                    Record(id="viral-unplaced", component="IMG/VR", taxonomy={}),
                ],
            )
        }
        # in scope, examined, nothing removed it — not the same claim as out_of_scope
        assert out["bacterium"].outcome is Outcome.RETAINED
        assert out["viral-unplaced"].outcome is Outcome.REMOVED

    def test_rule_components_must_be_a_non_empty_list(self, tmp_path):
        with pytest.raises(PolicyError, match="non-empty list"):
            load_policy(
                write(
                    tmp_path,
                    """
                    policy:
                      id: t-literal
                      model: Test
                      reading: literal
                      source: S-EVO1-PREPRINT
                      scope:
                        components: [IMG/VR]
                      rules:
                        - id: drop
                          kind: remove_if_taxon_in
                          components: []
                          source: S-EVO1-PREPRINT
                          params:
                            rank: family
                            names: [Filoviridae]
                    """,
                )
            )


class TestThreeReadings:
    """A0.3: three readings per policy, and the spread between them is the finding."""

    def test_every_model_has_all_three_readings(self):
        policies = load_policy_dir(SPECS)
        by_model: dict[str, set[str]] = {}
        for policy in policies.values():
            by_model.setdefault(policy.model, set()).add(policy.reading)
        assert by_model, "no specs found"
        for model, readings in by_model.items():
            assert readings == {"literal", "charitable", "strict"}, model

    def test_reading_ids_are_frozen(self):
        """Downstream tasks reference readings by id; renaming one silently rewires them."""
        assert set(load_policy_dir(SPECS)) == {
            "evo1-literal",
            "evo1-charitable",
            "evo1-strict",
            "esm3-open-literal",
            "esm3-open-charitable",
            "esm3-open-strict",
        }

    def test_the_spread_on_one_record_in_a_host_genome(self):
        """The headline Phase A contrast, as a test.

        One endogenous filoviral element in a vertebrate reference genome — the motivating case
        in DESIGN.md §2. The literal and charitable readings never look at the component it sits
        in; the strict reading removes it on the published predicate.
        """
        policies = load_policy_dir(SPECS)
        record = Record(
            id="filo-eve-in-host-genome",
            component="NCBI-eukaryotic-genomes",
            attributes={"confidence": "High-confidence", "vOTU": "v1"},
            taxonomy={"realm": "Riboviria", "family": "Filoviridae"},
            detected_elements=["endogenous-viral-element"],
        )
        outcomes = {
            reading: evaluate(policies[f"evo1-{reading}"], [record])[0]
            for reading in ("literal", "charitable", "strict")
        }
        assert outcomes["literal"].outcome is Outcome.OUT_OF_SCOPE
        assert outcomes["charitable"].outcome is Outcome.OUT_OF_SCOPE
        assert outcomes["strict"].outcome is Outcome.REMOVED
        assert outcomes["strict"].rule_id == "remove-eukaryote-infecting-elements"

    def test_the_spread_on_one_viral_record_with_mixed_host_evidence(self):
        """A record the published proxy retains and both broader readings do not."""
        policies = load_policy_dir(SPECS)
        record = Record(
            id="mixed-host-phage-like",
            component="IMG/VR",
            attributes={"confidence": "High-confidence", "vOTU": "v1"},
            taxonomy={"realm": "Duplodnaviria", "family": "Straboviridae"},
            host_occurrences={"prokaryotic": 4, "eukaryotic": 1},
        )
        out = {
            reading: evaluate(policies[f"evo1-{reading}"], [record])[0]
            for reading in ("literal", "charitable", "strict")
        }
        assert out["literal"].outcome is Outcome.RETAINED
        assert out["charitable"].outcome is Outcome.REMOVED
        assert out["charitable"].rule_id == "remove-eukaryotic-host-evidence"
        assert out["strict"].outcome is Outcome.REMOVED

    def test_esm3_threshold_range_across_readings(self):
        """Literal is undecidable; the other two bound the sweep A7.1 needs."""
        policies = load_policy_dir(SPECS)
        assert not policies["esm3-open-literal"].is_determined
        assert policies["esm3-open-charitable"].is_determined
        assert policies["esm3-open-strict"].is_determined

        # a weak hit: below the charitable threshold, above the strict one
        weak = Record(
            id="weak-hit",
            component="UniRef",
            similarity_hits={"viral-denylist": 0.42, "viral-annotated-all": 0.42},
        )
        assert evaluate(policies["esm3-open-literal"], [weak])[0].outcome is Outcome.UNDETERMINED
        assert evaluate(policies["esm3-open-charitable"], [weak])[0].outcome is Outcome.RETAINED
        assert evaluate(policies["esm3-open-strict"], [weak])[0].outcome is Outcome.REMOVED

    def test_esm3_broader_readings_reach_unnamed_components(self):
        policies = load_policy_dir(SPECS)
        rec = Record(
            id="in-an-unnamed-database",
            component="some-other-training-database",
            similarity_hits={"viral-denylist": 0.95, "viral-annotated-all": 0.95},
        )
        assert evaluate(policies["esm3-open-literal"], [rec])[0].outcome is Outcome.OUT_OF_SCOPE
        assert evaluate(policies["esm3-open-charitable"], [rec])[0].outcome is Outcome.REMOVED
        assert evaluate(policies["esm3-open-strict"], [rec])[0].outcome is Outcome.REMOVED
