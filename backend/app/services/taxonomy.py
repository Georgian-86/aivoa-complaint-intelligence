"""Pharmaceutical complaint domain taxonomy.

Single source of truth shared by the API, the LangGraph agent prompts and the
heuristic fallback engine. Grounded in:

  * 21 CFR 211.198  -- Complaint files (required record contents)
  * 21 CFR 211.192  -- Investigation of discrepancies
  * EU GMP Chapter 8 -- Complaints, quality defects and product recalls
  * ICH Q9(R1)      -- Quality risk management (severity x detectability x occurrence)
  * ICH Q10         -- Pharmaceutical quality system / CAPA

The vocabulary deliberately mirrors what a QA reviewer in an API (Active
Pharmaceutical Ingredient) or FDF (Finished Dosage Form) site would expect to
pick from, so the extracted values drop straight into a QMS record.
"""

from __future__ import annotations

from typing import Final

# ── Where a complaint entered the quality system ─────────────────────────────
COMPLAINT_SOURCES: Final[list[str]] = [
    "Customer Email",
    "Distributor / Wholesaler",
    "Medical Representative",
    "Contract Manufacturing Partner",
    "Regulatory Authority",
    "Healthcare Professional",
    "Patient / Consumer",
    "Internal QA Notification",
    "Call Centre",
]

# ── Nature of the alleged defect (21 CFR 211.198(a) "nature of complaint") ───
COMPLAINT_TYPES: Final[list[str]] = [
    "Foreign Particulate Matter",
    "Physical / Appearance Defect",
    "Packaging Defect",
    "Labelling Error",
    "Out of Specification (Assay / Potency)",
    "Impurity / Degradation",
    "Dissolution Failure",
    "Microbial Contamination",
    "Sterility Assurance Failure",
    "Container Closure Integrity",
    "Colour / Odour Variation",
    "Short Fill / Count Variance",
    "Product Mix-up / Wrong Product",
    "Cold Chain / Temperature Excursion",
    "Suspected Falsified Product",
    "Adverse Event / Lack of Efficacy",
    "Documentation / CoA Discrepancy",
    "Transit / Shipping Damage",
]

# ── GMP severity classification ──────────────────────────────────────────────
SEVERITIES: Final[list[str]] = ["Critical", "Major", "Minor"]

SEVERITY_DEFINITIONS: Final[dict[str, str]] = {
    "Critical": (
        "Defect that is potentially life-threatening or poses a serious risk to "
        "patient health. Includes product mix-up, wrong strength, sterility "
        "failure, microbial or cross contamination, and suspected falsified "
        "product. Triggers immediate escalation, health hazard evaluation and a "
        "parallel recall assessment."
    ),
    "Major": (
        "Genuine quality defect that is unlikely to be life-threatening but may "
        "compromise efficacy, compliance or patient confidence — for example a "
        "labelling error that does not misstate dose, out-of-specification "
        "assay within a non-critical range, or a significant appearance defect."
    ),
    "Minor": (
        "Cosmetic or trivial defect with no measurable impact on identity, "
        "strength, quality, purity or safety. Still logged and trended, because "
        "repeat minor events are a signal, not noise."
    ),
}

PRIORITIES: Final[list[str]] = ["P1 - Immediate", "P2 - High", "P3 - Normal", "P4 - Low"]

# Investigation turnaround targets in calendar days, by severity.
SEVERITY_TAT_DAYS: Final[dict[str, int]] = {"Critical": 3, "Major": 15, "Minor": 30}

SEVERITY_DEFAULT_PRIORITY: Final[dict[str, str]] = {
    "Critical": "P1 - Immediate",
    "Major": "P2 - High",
    "Minor": "P3 - Normal",
}

# ── Product families relevant to API + FDF manufacturers ─────────────────────
DOSAGE_FORMS: Final[list[str]] = [
    "Tablet",
    "Film-Coated Tablet",
    "Hard Gelatin Capsule",
    "Oral Solution",
    "Oral Suspension",
    "Lyophilised Powder for Injection",
    "Sterile Injectable Solution",
    "Pre-filled Syringe",
    "Topical Cream",
    "Ophthalmic Solution",
    "Active Pharmaceutical Ingredient (Bulk)",
    "Intermediate",
]

# ── Workflow states of a complaint record ────────────────────────────────────
COMPLAINT_STATUSES: Final[list[str]] = [
    "Draft",
    "Pending Triage",
    "Under Investigation",
    "CAPA Initiated",
    "Pending Closure Approval",
    "Closed",
    "Rejected - Not a Quality Complaint",
]

# ── Regulatory reportability decision points ─────────────────────────────────
REGULATORY_FLAGS: Final[dict[str, str]] = {
    "field_alert_report": (
        "21 CFR 314.81(b)(1) — FAR required within 3 working days for a "
        "distributed NDA/ANDA product showing a significant chemical, physical "
        "or other change, or bacteriological contamination."
    ),
    "adverse_event_report": (
        "21 CFR 310.305 / 314.80 — serious and unexpected adverse drug "
        "experience requires expedited reporting."
    ),
    "recall_assessment": (
        "EU GMP Chapter 8 — a health hazard evaluation and recall assessment "
        "must run in parallel with, not after, the investigation."
    ),
    "regulatory_notification": (
        "Competent authority notification where a confirmed critical defect "
        "affects distributed batches."
    ),
}

# ── Canonical root-cause categories (used for trending) ──────────────────────
ROOT_CAUSE_CATEGORIES: Final[list[str]] = [
    "Man — Training / Human Error",
    "Machine — Equipment Failure or Wear",
    "Material — Raw Material / Component Quality",
    "Method — Procedure or Process Design",
    "Measurement — Analytical Method / Instrument",
    "Mother Nature — Environment / Utilities",
    "Supplier / Contract Manufacturer",
    "Distribution / Storage Conditions",
    "Not Attributable — Insufficient Evidence",
]

# Defect type → prior probability of each severity band. Used by the heuristic
# engine and injected into the LLM prompt as calibration context so the model
# is anchored on site precedent rather than inventing a scale.
DEFECT_SEVERITY_PRIOR: Final[dict[str, str]] = {
    "Microbial Contamination": "Critical",
    "Sterility Assurance Failure": "Critical",
    "Product Mix-up / Wrong Product": "Critical",
    "Suspected Falsified Product": "Critical",
    "Container Closure Integrity": "Critical",
    "Adverse Event / Lack of Efficacy": "Critical",
    "Foreign Particulate Matter": "Major",
    "Out of Specification (Assay / Potency)": "Major",
    "Impurity / Degradation": "Major",
    "Dissolution Failure": "Major",
    "Labelling Error": "Major",
    "Cold Chain / Temperature Excursion": "Major",
    "Short Fill / Count Variance": "Major",
    "Packaging Defect": "Minor",
    "Physical / Appearance Defect": "Minor",
    "Colour / Odour Variation": "Minor",
    "Documentation / CoA Discrepancy": "Minor",
    "Transit / Shipping Damage": "Minor",
}

# Keyword lexicon for the deterministic fallback classifier. Ordered by
# specificity — first match wins.
DEFECT_KEYWORDS: Final[list[tuple[str, tuple[str, ...]]]] = [
    ("Sterility Assurance Failure", ("sterility", "non-sterile", "sterile failure", "media fill")),
    ("Microbial Contamination", ("microbial", "mould", "mold", "fungal", "bacterial", "bioburden", "endotoxin")),
    ("Product Mix-up / Wrong Product", ("wrong product", "mix-up", "mixup", "different product", "incorrect product", "wrong strength")),
    ("Suspected Falsified Product", ("counterfeit", "falsified", "spurious", "tamper")),
    ("Container Closure Integrity", ("leak", "seal broken", "closure", "cracked vial", "breach")),
    ("Foreign Particulate Matter", ("particle", "particulate", "black spot", "foreign matter", "fibre", "fiber", "glass", "metal shaving")),
    ("Out of Specification (Assay / Potency)", ("assay", "potency", "out of specification", "oos", "content uniformity")),
    ("Impurity / Degradation", ("impurity", "degradation", "degradant", "related substance", "discolor")),
    ("Dissolution Failure", ("dissolution", "disintegration", "not dissolving")),
    ("Cold Chain / Temperature Excursion", ("cold chain", "temperature excursion", "frozen", "above 25", "refrigerat")),
    ("Labelling Error", ("label", "labelling", "labeling", "artwork", "misprint", "expiry printed")),
    ("Packaging Defect", ("blister", "carton", "packaging", "cap", "seal", "foil", "pack")),
    ("Short Fill / Count Variance", ("short fill", "under fill", "missing tablet", "count", "fewer")),
    ("Adverse Event / Lack of Efficacy", ("adverse", "side effect", "hospital", "rash", "reaction", "no relief", "ineffective", "lack of efficacy")),
    ("Colour / Odour Variation", ("colour", "color", "odour", "odor", "smell", "discoloured")),
    ("Physical / Appearance Defect", ("broken", "chipped", "cracked tablet", "crumbl", "sticking", "capping", "powder")),
    ("Documentation / CoA Discrepancy", ("coa", "certificate of analysis", "document", "batch record")),
    ("Transit / Shipping Damage", ("transit", "shipping", "damaged carton", "crushed")),
]

# Deliberately excludes the bare word "hospital" — complainant organisations are
# routinely named "... Teaching Hospital", and an institution name is not a
# patient-harm signal. Only phrases that describe harm or intervention qualify.
CRITICAL_ESCALATION_KEYWORDS: Final[tuple[str, ...]] = (
    "hospitalis", "hospitaliz", "admitted to hospital", "required hospital",
    "taken to hospital", "death", "died", "fatal", "anaphyla", "injury",
    "injured", "seizure", "unconscious", "emergency room", "admitted to icu",
    "life-threatening", "serious adverse", "adverse reaction", "febrile reaction",
    "overnight observation", "required medical", "medical attention",
)
