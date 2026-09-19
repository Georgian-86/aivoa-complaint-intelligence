"""The deterministic engine is both the no-key fallback and the guardrail on
the LLM, so it carries real tests rather than smoke checks."""

from datetime import date

import pytest

from app.services import heuristics
from app.services.taxonomy import DEFECT_SEVERITY_PRIOR


class TestDateParsing:
    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("2026-09-12", date(2026, 9, 12)),
            ("12 September 2026", date(2026, 9, 12)),
            ("12/09/2026", date(2026, 9, 12)),
            ("03/2025", date(2025, 3, 1)),        # month/year printed on a carton
            ("Jan 2027", date(2027, 1, 1)),
            ("not a date", None),
        ],
    )
    def test_parses(self, raw, expected):
        assert heuristics.parse_date(raw) == expected

    def test_day_first_when_unambiguous(self):
        # 14/09 can only be day-first; the corpus is EU/IN formatted.
        assert heuristics.parse_date("14/09/2026") == date(2026, 9, 14)


class TestBatchExtraction:
    def test_labelled_batch_wins(self, particulate_email):
        fields = heuristics.extract_fields(particulate_email)
        assert fields["batch_number"]["value"] == "CFX24B902"
        assert fields["batch_number"]["confidence"] >= 0.9

    def test_prose_word_is_not_a_batch_code(self):
        fields = heuristics.extract_fields(
            "The batch number on the box is IBU6610 and the expiry is 08/2027. "
            "Two blister pockets were empty on opening the pack of 24 tablets."
        )
        assert fields["batch_number"]["value"] == "IBU6610"

    def test_no_batch_returns_none(self):
        fields = heuristics.extract_fields("The tablets tasted unusual. Nothing else to report here.")
        assert fields["batch_number"]["value"] is None


class TestQuantity:
    def test_affected_beats_received(self):
        fields = heuristics.extract_fields(
            "Quantity received : 75 kg (3 drums)\nQuantity affected : 25 kg (drum 2 of 3)"
        )
        assert fields["quantity_affected"]["value"] == 25.0
        assert fields["quantity_unit"]["value"] == "kg"

    def test_strength_is_not_a_quantity(self):
        fields = heuristics.extract_fields(
            "Product: Ceftrioxam 1 g Injection. Quantity affected: 38 vials from four cartons."
        )
        assert fields["quantity_affected"]["value"] == 38.0


class TestSeverity:
    def test_patient_harm_forces_critical(self):
        severity, _c, drivers = heuristics.detect_severity(
            "The patient required hospitalisation after the infusion.", "Packaging Defect"
        )
        assert severity == "Critical"
        assert any("patient harm" in d["factor"].lower() for d in drivers)

    def test_institution_name_is_not_patient_harm(self):
        """'St. Alban's Teaching Hospital' is a complainant, not an adverse event."""
        severity, _c, drivers = heuristics.detect_severity(
            "Reported by St. Alban's Teaching Hospital Pharmacy. Two cartons had a smudged label.",
            "Labelling Error",
        )
        assert severity == DEFECT_SEVERITY_PRIOR["Labelling Error"]
        assert not any("patient harm" in d["factor"].lower() for d in drivers)

    def test_sterile_route_escalates_minor(self):
        severity, _c, _d = heuristics.detect_severity(
            "Slight discolouration noticed on the vial label of this injection.",
            "Physical / Appearance Defect",
        )
        assert severity == "Major"

    def test_score_band_boundaries(self):
        assert heuristics.score_risk("Minor", [], "x" * 500)[1] == "Low"
        assert heuristics.score_risk("Critical", [], "x" * 500)[1] == "Severe"


class TestDescription:
    def test_mail_headers_are_not_the_description(self, particulate_email):
        fields = heuristics.extract_fields(particulate_email)
        description = fields["description"]["value"]
        assert "Subject:" not in description
        assert "particulate matter" in description.lower()

    def test_boilerplate_opener_loses_to_observation(self, particulate_email):
        fields = heuristics.extract_fields(particulate_email)
        assert not fields["description"]["value"].startswith("We are writing")


class TestSourceDetection:
    def test_distribution_outranks_hospital_mention(self, particulate_email):
        fields = heuristics.extract_fields(particulate_email)
        assert fields["complaint_source"]["value"] == "Distributor / Wholesaler"


class TestTabularDocuments:
    """PDF and Word forms emit one line per visual cell, so a label and its
    value arrive on separate lines. The pipeline re-pairs them before
    extraction; this is the shape most real complaint forms arrive in."""

    FORM = (
        "1. COMPLAINANT DETAILS\n"
        "Complaint raised by\nDr. Helen Marsh, Chief Pharmacist\n"
        "Country\nUnited Kingdom\n"
        "2. PRODUCT CONCERNED\n"
        "Product Name\nLevothyroxine Sodium Tablets\n"
        "Strength\n50 mcg\n"
        "Batch No.\nLEV2604A\n"
        "Exp. Date\nJan 2027\n"
        "Quantity affected\n14 strips\n"
        "3. DESCRIPTION OF DEFECT\n"
        "During a routine dispensary stock check our technician identified that the outer "
        "carton declares a strength of 50 mcg while the blister foil overprint reads 25 mcg."
    )

    def _fields(self):
        from app.services.documents import normalise
        return heuristics.extract_fields(normalise(self.FORM))

    def test_orphan_labels_are_paired(self):
        from app.services.documents import pair_orphan_labels
        paired = pair_orphan_labels("Batch No.\nLEV2604A\nStrength\n50 mcg")
        assert "Batch No: LEV2604A" in paired

    def test_values_extract_from_a_tabular_form(self):
        fields = self._fields()
        assert fields["product_name"]["value"] == "Levothyroxine Sodium Tablets"
        assert fields["batch_number"]["value"] == "LEV2604A"
        assert fields["quantity_affected"]["value"] == 14.0
        assert fields["product_strength"]["value"] == "50 mcg"

    def test_section_heading_is_not_mistaken_for_a_name(self):
        """'1. COMPLAINANT DETAILS' precedes the real 'Complaint raised by' row."""
        assert self._fields()["customer_name"]["value"] == "Dr. Helen Marsh"


class TestRegulatoryFlags:
    def test_hospital_in_an_organisation_name_does_not_trigger_a_far(self):
        flags = heuristics.regulatory_flags(
            "Major", "Labelling Error",
            "Reported by St. Alban's Teaching Hospital Pharmacy. Carton strength mismatch.",
        )
        assert "adverse_event_report" not in flags

    def test_actual_harm_triggers_adverse_event_reporting(self):
        flags = heuristics.regulatory_flags(
            "Critical", "Foreign Particulate Matter",
            "A patient developed a febrile reaction and required hospitalisation.",
        )
        assert {"adverse_event_report", "recall_assessment", "field_alert_report"} <= set(flags)

    def test_driver_evidence_quotes_the_phrase_that_fired(self):
        _s, _c, drivers = heuristics.detect_severity(
            "Batch No: LEV2604A\nWe request an assessment of whether other batches are affected.",
            "Labelling Error",
        )
        scope = next(d for d in drivers if "Multi-batch" in d["factor"])
        assert "other batches" in scope["evidence"].lower()
