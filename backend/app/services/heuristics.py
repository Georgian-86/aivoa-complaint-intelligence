"""Deterministic extraction + risk engine.

Two jobs:

* **Fallback.** When no GROQ_API_KEY is present, or the model call fails, the
  product still works end to end. A reviewer evaluating this repository can
  clone and run it without credentials and still see the full workflow.
* **Guardrail.** Even when the LLM is available, the regex layer recovers
  identifiers (batch/lot codes, dates, strengths, e-mail addresses) that small
  models routinely mangle, and the rule-based severity floor prevents an
  under-classification of a patient-safety event — a failure mode that is
  unacceptable in this domain.

The two engines are *merged*, not switched: LLM values win on prose fields,
regex wins on identifiers when the LLM is unsure.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from app.services.taxonomy import (
    CRITICAL_ESCALATION_KEYWORDS,
    DEFECT_KEYWORDS,
    DEFECT_SEVERITY_PRIOR,
    SEVERITY_DEFAULT_PRIORITY,
    SEVERITY_TAT_DAYS,
)

# ── Regex atoms ──────────────────────────────────────────────────────────────
RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
RE_PHONE = re.compile(r"(?:\+\d{1,3}[\s-]?)?(?:\d[\s-]?){9,13}\d")
RE_BATCH = re.compile(
    r"(?:batch|lot)\s*(?:no\.?|number|code|#)?\s*[:#.\-]?\s*(?:is\s+)?"
    r"([A-Z0-9][A-Z0-9\-/]{3,19})",
    re.IGNORECASE,
)
# Words that follow "batch"/"lot" in prose and must never be read as a code.
BATCH_STOPWORDS = {
    "NUMBER", "NUMBERS", "CODE", "CODES", "DETAILS", "RECORD", "RECORDS", "SIZE",
    "MANUFACTURING", "PRINTED", "ABOVE", "BELOW", "SAME", "THIS", "THAT", "FROM",
    "WITH", "AFFECTED", "CONCERNED", "QUANTITY", "PRODUCT", "EXPIRY", "DATE",
}
RE_BATCH_BARE = re.compile(r"\b([A-Z]{1,3}\d{4,8}[A-Z]?)\b")
RE_STRENGTH = re.compile(
    r"\b(\d+(?:\.\d+)?)\s?(mg/ml|mcg/ml|mg|mcg|µg|g|ml|iu|%|w/v|w/w)\b", re.IGNORECASE
)
# Countable presentation units only — deliberately excludes mg/ml/g so a
# strength expression ("1 g Injection") is never mistaken for a quantity.
RE_QTY = re.compile(
    r"\b(\d{1,6}(?:[.,]\d+)?)\s*(units?|tablets?|capsules?|vials?|bottles?|packs?|strips?|"
    r"ampoules?|syringes?|blisters?|sachets?|boxes|cartons?|drums?|containers?|kg)\b",
    re.IGNORECASE,
)
# Ordered most- to least-specific: an explicit "affected" quantity outranks a
# generic "quantity received", which is a different number entirely.
RE_QTY_AFFECTED = re.compile(
    r"(?:quantity\s*affected|affected\s*quantity|units?\s*affected|quantity\s*involved)"
    r"\s*[:\-]?\s*(?:is\s+)?(\d{1,6}(?:[.,]\d+)?)\s*([A-Za-z]{2,12})?",
    re.IGNORECASE,
)
RE_QTY_LABELLED = re.compile(
    r"(?:quantity|qty)\s*(?:received|supplied|shipped)?\s*[:\-]\s*(\d{1,6}(?:[.,]\d+)?)\s*([A-Za-z]{2,12})?",
    re.IGNORECASE,
)
RE_DATE_ISO = re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b")
RE_DATE_DMY = re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b")
RE_DATE_TEXT = re.compile(
    r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{4})\b",
    re.IGNORECASE,
)
RE_NUM_MONTH_YEAR = re.compile(r"\b(0?[1-9]|1[0-2])[/\-.](20\d{2})\b")
RE_MONTH_YEAR = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{4})\b", re.IGNORECASE
)

_MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], start=1
)}

LABELLED_DATE_HINTS = {
    "manufacturing_date": ("mfg", "manufactur", "mfd", "made on", "production date"),
    "expiry_date": ("exp", "expiry", "expiration", "use before", "best before", "retest date"),
    "complaint_date": ("complaint date", "reported on", "date of complaint", "observed on", "incident date"),
    "date_received": ("received on", "date received", "receipt date", "logged on"),
}

PRODUCT_HINTS = ("product", "drug", "medicine", "item", "material", "preparation", "brand")

# Dosage form lexicon — ordered most- to least-specific so "Lyophilised Powder
# for Injection" is not swallowed by the bare token "injection".
DOSAGE_PATTERNS: list[tuple[str, tuple[str, ...]]] = [
    ("Lyophilised Powder for Injection", ("lyophilis", "lyophiliz", "powder for injection", "freeze-dried")),
    ("Pre-filled Syringe", ("pre-filled syringe", "prefilled syringe", "pfs")),
    ("Sterile Injectable Solution", ("injectable solution", "solution for injection", "injection solution")),
    ("Ophthalmic Solution", ("ophthalmic", "eye drop")),
    ("Film-Coated Tablet", ("film-coated tablet", "film coated tablet", "coated tablet")),
    ("Hard Gelatin Capsule", ("hard gelatin", "capsule")),
    ("Oral Suspension", ("oral suspension", "suspension")),
    ("Oral Solution", ("oral solution", "syrup")),
    ("Topical Cream", ("cream", "ointment", "topical")),
    ("Active Pharmaceutical Ingredient (Bulk)", ("active pharmaceutical ingredient", "bulk api", " api ", "drug substance")),
    ("Intermediate", ("intermediate",)),
    ("Tablet", ("tablet",)),
]

# Markets seen in the site's distribution network. A small closed list beats a
# fuzzy place-name matcher for a field that feeds a regulatory assessment.
COUNTRY_LEXICON: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("India", ("india", "hyderabad", "mumbai", "bengaluru", "bangalore", "chennai", "delhi", "cdsco")),
    ("United Kingdom", ("united kingdom", "england", "scotland", "wales", " uk ", "london", "mhra")),
    ("United States", ("united states", " usa", " u.s.", "new jersey", "california")),
    ("Germany", ("germany", "berlin", "munich")),
    ("Norway", ("norway", "oslo", " as ")),
    ("Portugal", ("portugal", "lisbon", "porto")),
    ("Singapore", ("singapore",)),
    ("Japan", ("japan", "tokyo", "pmda")),
    ("Brazil", ("brazil", "anvisa")),
    ("Australia", ("australia", "tga")),
)


HEADER_TOKENS = ("from:", "to:", "cc:", "bcc:", "subject:", "date:", "sent:", "ref:")
KEY_VALUE_LINE = re.compile(r"^[A-Za-z][\w .()/-]{2,28}\s*[:\-]\s*\S")


def _prose_blocks(text: str) -> list[str]:
    """Split a document into narrative blocks, discarding header and form rows.

    Two passes, because the two source shapes differ: an e-mail separates
    paragraphs with a blank line, while a PDF form emits one line per visual
    row, so a blank-line split returns the whole page as a single block.
    """

    def usable(block: str) -> bool:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        if not lines:
            return False
        header_like = sum(1 for ln in lines if ln.lower().lstrip().startswith(HEADER_TOKENS))
        keyed = sum(1 for ln in lines if KEY_VALUE_LINE.match(ln.strip()))
        return header_like == 0 and keyed <= len(lines) / 2

    blocks = [b.strip() for b in text.split("\n\n") if len(b.strip()) >= 90]
    candidates = [b for b in blocks if usable(b)]
    if len(candidates) >= 2:
        return candidates

    # Second pass: rebuild blocks from consecutive prose lines.
    rebuilt: list[str] = []
    buffer: list[str] = []
    for raw in text.split("\n"):
        line = raw.strip()
        is_prose = bool(line) and not KEY_VALUE_LINE.match(line) \
            and not line.lower().startswith(HEADER_TOKENS) \
            and not (line.isupper() and len(line) < 60)
        if is_prose:
            buffer.append(line)
            continue
        if buffer:
            joined = " ".join(buffer)
            if len(joined) >= 90:
                rebuilt.append(joined)
            buffer = []
    if buffer and len(" ".join(buffer)) >= 90:
        rebuilt.append(" ".join(buffer))

    return rebuilt or candidates or blocks


def _field(value, confidence: float, evidence: str | None, source: str = "regex") -> dict:
    return {
        "value": value,
        "confidence": round(confidence, 2),
        "evidence": (evidence or "")[:140] or None,
        "source": source,
    }


def _line_containing(text: str, needle: str) -> str | None:
    for line in text.split("\n"):
        if needle.lower() in line.lower():
            return line.strip()[:140]
    return None


# ── Date parsing ─────────────────────────────────────────────────────────────
def parse_date(token: str) -> date | None:
    token = token.strip()
    if not token:
        return None
    m = RE_DATE_ISO.search(token)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = RE_DATE_TEXT.search(token)
    if m:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
        except (ValueError, KeyError):
            return None
    m = RE_DATE_DMY.search(token)
    if m:
        a, b, c = int(m.group(1)), int(m.group(2)), int(m.group(3))
        year = c + 2000 if c < 100 else c
        # Day-first unless impossible (the sample corpus is EU/IN formatted).
        day, month = (a, b) if a > 12 else (b, a) if b > 12 else (a, b)
        try:
            return date(year, month, day)
        except ValueError:
            return None
    m = RE_MONTH_YEAR.search(token)
    if m:
        try:
            return date(int(m.group(2)), _MONTHS[m.group(1).lower()[:3]], 1)
        except (ValueError, KeyError):
            return None
    # "03/2025" — month/year only, common on cartons for Mfg and Exp.
    m = RE_NUM_MONTH_YEAR.search(token)
    if m:
        try:
            return date(int(m.group(2)), int(m.group(1)), 1)
        except ValueError:
            return None
    return None


def _find_labelled_date(text: str, hints: tuple[str, ...]) -> tuple[date | None, str | None]:
    for line in text.split("\n"):
        low = line.lower()
        if any(h in low for h in hints):
            parsed = parse_date(line)
            if parsed:
                return parsed, line.strip()[:140]
    return None, None


# ── Defect classification ────────────────────────────────────────────────────
def classify_defect(text: str) -> tuple[str | None, float, str | None]:
    low = text.lower()
    for defect, keywords in DEFECT_KEYWORDS:
        for kw in keywords:
            if kw in low:
                return defect, 0.72, _line_containing(text, kw)
    return None, 0.0, None


def detect_severity(text: str, defect: str | None) -> tuple[str, float, list[dict]]:
    """Rule-based severity with a hard patient-safety floor."""
    low = text.lower()
    drivers: list[dict] = []

    prior = DEFECT_SEVERITY_PRIOR.get(defect or "", "Minor")
    severity = prior
    if defect:
        drivers.append(
            {"factor": f"Defect class: {defect}", "weight": 0.5,
             "evidence": f"Baseline classification for this defect family is {prior}."}
        )

    hit = next((k for k in CRITICAL_ESCALATION_KEYWORDS if k in low), None)
    if hit:
        severity = "Critical"
        drivers.append(
            {"factor": "Reported patient harm or medical intervention", "weight": 0.95,
             "evidence": _line_containing(text, hit) or hit}
        )

    scope_hit = next((k for k in (
        "multiple batch", "several batch", "other batches", "entire consignment",
        "whole shipment", "same packaging campaign", "all batches",
    ) if k in low), None)
    if scope_hit:
        drivers.append({"factor": "Multi-batch / consignment-wide exposure", "weight": 0.6,
                        "evidence": _line_containing(text, scope_hit)})
        if severity == "Minor":
            severity = "Major"

    route_hit = next((k for k in (
        "injection", "injectable", "vial", "infusion", "sterile", "ophthalmic", "parenteral",
    ) if k in low), None)
    if route_hit:
        drivers.append({"factor": "Sterile / parenteral route raises intrinsic risk", "weight": 0.55,
                        "evidence": _line_containing(text, route_hit)})
        if severity == "Minor":
            severity = "Major"

    vulnerable_hit = next((k for k in (
        "paediatric", "pediatric", "infant", "neonat", "child",
    ) if k in low), None)
    if vulnerable_hit:
        drivers.append({"factor": "Vulnerable patient population", "weight": 0.6,
                        "evidence": _line_containing(text, vulnerable_hit)})
        if severity == "Minor":
            severity = "Major"

    confidence = 0.8 if drivers else 0.35
    return severity, confidence, drivers


SEVERITY_BASE_SCORE = {"Critical": 78.0, "Major": 48.0, "Minor": 18.0}


def score_risk(severity: str, drivers: list[dict], text: str) -> tuple[float, str]:
    score = SEVERITY_BASE_SCORE.get(severity, 20.0)
    score += sum(d.get("weight", 0) for d in drivers) * 6.0
    if len(text) < 180:
        score -= 4.0  # thin report: less certainty, not less risk — small nudge only
    score = max(0.0, min(100.0, score))
    band = (
        "Severe" if score >= 75 else "High" if score >= 50 else "Moderate" if score >= 25 else "Low"
    )
    return round(score, 1), band


def regulatory_flags(severity: str, defect: str | None, text: str) -> list[str]:
    low = text.lower()
    flags: list[str] = []
    if severity == "Critical":
        flags += ["recall_assessment", "field_alert_report"]
    # Reuse the tightened patient-harm lexicon: an institution name is not an
    # adverse event, and a false FAR trigger costs a regulatory filing.
    if any(k in low for k in CRITICAL_ESCALATION_KEYWORDS):
        flags.append("adverse_event_report")
    if defect in {"Microbial Contamination", "Sterility Assurance Failure", "Suspected Falsified Product"}:
        flags.append("regulatory_notification")
    return sorted(set(flags))


# ── Full heuristic extraction ────────────────────────────────────────────────
def extract_fields(text: str, channel: str = "document") -> dict[str, dict]:
    fields: dict[str, dict] = {}

    # Source channel
    low = text.lower()
    # Weighted vote rather than first-match: complaint e-mails routinely mention
    # several actors ("our distributor reported that a hospital pharmacy...").
    source_signals: list[tuple[str, tuple[str, ...], float]] = [
        ("Contract Manufacturing Partner", ("cdmo", "contract manufactur", "toll manufactur", "supplier quality"), 3.0),
        ("Regulatory Authority", ("cdsco", "regulatory authority", "competent authority", "inspectorate", "mhra", "us fda"), 3.0),
        ("Distributor / Wholesaler", ("distribut", "wholesal", "depot", "stockist", "consignment"), 2.0),
        ("Healthcare Professional", ("pharmacist", "hospital pharmacy", "physician", "clinician", "dispensary", "chief pharmacist"), 1.8),
        ("Medical Representative", ("medical representative", "field report", "field force"), 2.5),
        # "warehouse QA" is deliberately absent: a distributor's own warehouse QA
        # team raising a complaint is still an external complaint.
        ("Internal QA Notification", ("internal qa", "site qa", "qa notification", "internal notification"), 2.5),
        ("Patient / Consumer", ("i bought", "i purchased", "my pack", "consumer"), 1.5),
    ]
    scores: dict[str, float] = {}
    evidence_for: dict[str, str | None] = {}
    for label, keywords, weight in source_signals:
        hits = [k for k in keywords if k in low]
        if hits:
            scores[label] = len(hits) * weight
            evidence_for[label] = _line_containing(text, hits[0])
    if scores:
        detected_source = max(scores, key=scores.get)
        confidence = min(0.9, 0.5 + 0.1 * scores[detected_source])
        evidence = evidence_for[detected_source]
    else:
        detected_source = "Customer Email" if channel in {"email", "text"} else "Customer Email"
        confidence, evidence = 0.4, None
    fields["complaint_source"] = _field(detected_source, confidence, evidence)

    # Contact
    if (m := RE_EMAIL.search(text)):
        fields["customer_contact"] = _field(m.group(0), 0.95, _line_containing(text, m.group(0)))

    # Customer name — explicit label, then mail header, then sign-off block.
    name_patterns = (
        # The separator is optional: a PDF table cell often loses its colon.
        (r"(?:complaint\s+raised\s+by|reported\s+by|raised\s+by|complainant|contact\s+person)"
         r"\s*[:\-]?\s+([^\n,;|]{3,60})", 0.85),
        (r"^from\s*:\s*([^<\n|]{3,60})", 0.7),
        (r"(?:regards|sincerely|thanks|thank you)[,\s]*\n+([A-Z][\w.'\- ]{2,50})", 0.62),
    )
    # Walk *every* match of each pattern: the first hit is often a section
    # heading ("1. COMPLAINANT DETAILS") that has to be skipped in favour of
    # the real value further down.
    for pattern, confidence in name_patterns:
        matched = False
        for m in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
            name = m.group(1).strip().strip('".,')
            looks_like_heading = name.isupper() or name.lower() in {"details", "information"}
            if (
                name and "@" not in name and not looks_like_heading
                and any(ch.islower() for ch in name)
                and not name.lower().startswith(("the ", "our "))
            ):
                fields["customer_name"] = _field(name, confidence, m.group(0)[:140])
                matched = True
                break
        if matched:
            break

    # Batch / lot — a labelled code that contains at least one digit.
    batch_value: str | None = None
    batch_evidence: str | None = None
    batch_confidence = 0.0
    for match in RE_BATCH.finditer(text):
        candidate = match.group(1).upper().strip(".,;:")
        if candidate in BATCH_STOPWORDS or not any(ch.isdigit() for ch in candidate):
            continue
        batch_value, batch_evidence, batch_confidence = candidate, match.group(0), 0.93
        break
    if batch_value is None and (m := RE_BATCH_BARE.search(text)):
        batch_value = m.group(1).upper()
        batch_evidence = _line_containing(text, m.group(1))
        batch_confidence = 0.45
    if batch_value:
        fields["batch_number"] = _field(batch_value, batch_confidence, batch_evidence)

    # Strength
    if (m := RE_STRENGTH.search(text)):
        fields["product_strength"] = _field(
            f"{m.group(1)} {m.group(2).lower()}", 0.8, _line_containing(text, m.group(0))
        )

    # Product name — a labelled line beats guessing; otherwise take the proper
    # noun phrase immediately preceding a strength expression
    # ("... a pack of Ibuprofen 400 mg tablets" -> "Ibuprofen").
    for line in text.split("\n"):
        low_line = line.lower()
        if any(h in low_line for h in PRODUCT_HINTS) and ":" in line:
            candidate = line.split(":", 1)[1].split("\n")[0].strip()
            if 2 < len(candidate) < 90 and not candidate.lower().startswith(("concerned", "details")):
                fields["product_name"] = _field(candidate, 0.75, line.strip()[:140])
                break
    if fields.get("product_name", {}).get("value") in (None, ""):
        m = re.search(
            r"\b([A-Z][a-z]{3,}(?:[ ]+[A-Z][a-z]{2,}){0,2})[ ]+\d+(?:\.\d+)?[ ]?"
            r"(?:mg|mcg|g|ml|iu|%)\b",
            text,
        )
        if m:
            fields["product_name"] = _field(m.group(1).strip(), 0.55, m.group(0)[:140])

    # Dosage form
    for form_name, keywords in DOSAGE_PATTERNS:
        hit = next((k for k in keywords if k in low), None)
        if hit:
            fields["dosage_form"] = _field(form_name, 0.72, _line_containing(text, hit.strip()))
            break

    # Country of origin / destination market
    for country, keywords in COUNTRY_LEXICON:
        hit = next((k for k in keywords if k in low), None)
        if hit:
            evidence = _line_containing(text, hit.strip())
            fields["customer_country"] = _field(country, 0.6, evidence)
            fields["market_country"] = _field(country, 0.5, evidence)
            break

    # Dates
    for key, hints in LABELLED_DATE_HINTS.items():
        parsed, evidence = _find_labelled_date(text, hints)
        if parsed:
            fields[key] = _field(parsed.isoformat(), 0.85, evidence)

    # Complaint date — a narrative opener ("On 12 September 2026, our QA team
    # observed…") is stronger evidence of when the defect was seen than the
    # e-mail header, which only tells us when it was reported.
    if "complaint_date" not in fields:
        narrative = re.search(
            r"\bon\s+((?:\d{1,2}\s+\w+\s+\d{4})|(?:\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}))"
            # `[^.]` rather than `[^.\n]`: the sentence often wraps mid-clause.
            r"[^.]{0,130}?(observ|identif|found|notic|report|inspect|detect)",
            text, re.IGNORECASE)
        if narrative and (parsed := parse_date(narrative.group(1))):
            fields["complaint_date"] = _field(parsed.isoformat(), 0.78, narrative.group(0)[:140])

    if "complaint_date" not in fields:
        header = re.search(r"^date\s*:\s*(.+)$", text, re.IGNORECASE | re.MULTILINE)
        if header and (parsed := parse_date(header.group(1))):
            fields["complaint_date"] = _field(parsed.isoformat(), 0.6, header.group(0)[:140])

    # Quantity — an explicitly labelled "Quantity affected: 38 vials" beats the
    # first number in the document every time.
    for pattern, confidence in (
        (RE_QTY_AFFECTED, 0.9),
        (RE_QTY_LABELLED, 0.7),
        (RE_QTY, 0.58),
    ):
        qty_match = pattern.search(text)
        if not qty_match:
            continue
        try:
            amount = float(qty_match.group(1).replace(",", ""))
        except (ValueError, IndexError):
            continue
        unit = (qty_match.group(2) or "units").lower().rstrip(".")
        fields["quantity_affected"] = _field(
            amount, confidence, _line_containing(text, qty_match.group(0))
        )
        fields["quantity_unit"] = _field(unit if unit.isalpha() else "units", confidence, None)
        break

    # Defect type
    defect, conf, evidence = classify_defect(text)
    if defect:
        fields["complaint_type"] = _field(defect, conf, evidence)

    # Description — the first substantive narrative paragraph. Mail headers,
    # salutations and key:value blocks are not a defect description.
    candidates = _prose_blocks(text)
    # Score the candidates: defect vocabulary earns points, covering-letter
    # boilerplate loses them. "We are writing to raise a formal complaint" is
    # not a description of a defect.
    OBSERVATION = re.compile(
        r"\b(observ|identif|found|noticed|detect|visible|defect|discolo|particul|"
        r"empty|broken|leak|missing|reading|result|assay|excursion|contamina|"
        r"mismatch|declares?|overprint)\w*", re.I)
    BOILERPLATE = re.compile(
        r"\b(we are writing|formal (?:market )?complaint|on behalf of|please (?:find|confirm)|"
        r"kindly|look forward|thank you|regards)\b", re.I)

    def _score(block: str) -> float:
        return (
            2.0 * len(OBSERVATION.findall(block))
            - 1.5 * len(BOILERPLATE.findall(block))
            + min(len(block), 700) / 700.0
        )

    best = max(candidates, key=_score) if candidates else None
    body = best or text[:600]
    confidence = 0.68 if best and _score(best) > 2 else 0.45 if best else 0.25
    fields["description"] = _field(re.sub(r"\s+", " ", body)[:900], confidence, None)

    # Sample availability
    positive = re.search(
        r"(sample|retain\w*|returned unit|affected (?:unit|vial|pack|strip|tablet)\w*|stock|product)"
        r"[^.\n]{0,80}?(available for collection|available|enclosed|attached|segregated|quarantin\w*|"
        r"isolated|held|retained|ready for (?:collection|dispatch)|courier)",
        low,
    )
    negative = re.search(
        r"(no sample|sample (?:is )?not available|sample was discarded|discarded|disposed|"
        r"consumed|already used|not retained)",
        low,
    )
    if negative:
        fields["sample_available"] = _field(False, 0.75, _line_containing(text, negative.group(0)[:20]))
    elif positive:
        fields["sample_available"] = _field(True, 0.72, _line_containing(text, positive.group(0)[:20]))

    # Received date defaults to today when the channel is live intake
    if "date_received" not in fields:
        fields["date_received"] = _field(date.today().isoformat(), 0.4, None, source="default")

    for key in (
        "customer_name", "customer_contact", "customer_country", "product_name",
        "product_strength", "dosage_form", "batch_number", "manufacturing_date",
        "expiry_date", "quantity_affected", "quantity_unit", "market_country",
        "complaint_type", "complaint_date", "date_received", "description",
        "sample_available", "complaint_source",
    ):
        fields.setdefault(key, _field(None, 0.0, None, source="none"))

    return fields


def default_priority(severity: str) -> str:
    return SEVERITY_DEFAULT_PRIORITY.get(severity, "P3 - Normal")


def tat_days(severity: str) -> int:
    return SEVERITY_TAT_DAYS.get(severity, 30)


def fallback_root_causes(defect: str | None, severity: str) -> list[dict]:
    library: dict[str, list[dict]] = {
        "Foreign Particulate Matter": [
            {"category": "Machine — Equipment Failure or Wear", "hypothesis":
             "Wear debris or gasket shedding from the filling line contaminated the product stream.",
             "likelihood": 0.4, "investigation_step":
             "Inspect filling line gaskets and sieves for the batch; review preventive maintenance records."},
            {"category": "Material — Raw Material / Component Quality", "hypothesis":
             "Incoming primary packaging component carried particulate not detected at inspection.",
             "likelihood": 0.35, "investigation_step":
             "Retrieve component CoA and retained samples; re-inspect the same component lot."},
            {"category": "Mother Nature — Environment / Utilities", "hypothesis":
             "Cleanroom particulate excursion during the fill window.",
             "likelihood": 0.25, "investigation_step":
             "Review environmental monitoring and differential pressure trends for the fill date."},
        ],
        "Labelling Error": [
            {"category": "Method — Procedure or Process Design", "hypothesis":
             "Artwork revision was not propagated to the packaging line master.",
             "likelihood": 0.45, "investigation_step":
             "Compare approved artwork revision against the line-clearance record for the batch."},
            {"category": "Man — Training / Human Error", "hypothesis":
             "Line clearance was performed without verifying the label reel identity.",
             "likelihood": 0.35, "investigation_step":
             "Review line clearance checklist signatures and operator training records."},
            {"category": "Machine — Equipment Failure or Wear", "hypothesis":
             "Vision inspection system failed to reject the mislabelled units.",
             "likelihood": 0.2, "investigation_step":
             "Pull vision system challenge test results for that shift."},
        ],
        "Microbial Contamination": [
            {"category": "Mother Nature — Environment / Utilities", "hypothesis":
             "Loss of environmental control or water system excursion during manufacture.",
             "likelihood": 0.4, "investigation_step":
             "Review EM data, water system TOC/bioburden trends and HVAC alarms for the batch window."},
            {"category": "Method — Procedure or Process Design", "hypothesis":
             "Inadequate sanitisation hold time or cleaning validation gap.",
             "likelihood": 0.35, "investigation_step":
             "Verify cleaning validation status and the executed sanitisation record."},
            {"category": "Distribution / Storage Conditions", "hypothesis":
             "Container closure compromised in transit allowing ingress.",
             "likelihood": 0.25, "investigation_step":
             "Inspect the returned unit seal integrity and review the shipping lane data logger."},
        ],
    }
    generic = [
        {"category": "Method — Procedure or Process Design", "hypothesis":
         "A process or procedural control did not perform as designed for this batch.",
         "likelihood": 0.4, "investigation_step":
         "Review the batch manufacturing record against the master formula for deviations."},
        {"category": "Material — Raw Material / Component Quality", "hypothesis":
         "An incoming material or component lot contributed to the defect.",
         "likelihood": 0.35, "investigation_step":
         "Trace component lot genealogy and review incoming inspection results."},
        {"category": "Not Attributable — Insufficient Evidence", "hypothesis":
         "Evidence is currently insufficient to assign a cause; a complaint sample is required.",
         "likelihood": 0.25, "investigation_step":
         "Request the complaint sample and perform comparative testing against the retained sample."},
    ]
    return library.get(defect or "", generic)


def fallback_capa(defect: str | None, severity: str) -> list[dict]:
    urgent = severity == "Critical"
    return [
        {"type": "correction", "action":
         "Place the implicated batch on quality hold and quarantine remaining stock at the "
         "distributor and warehouse pending investigation outcome.",
         "owner_function": "Quality Assurance", "due_in_days": 1 if urgent else 3,
         "effectiveness_check": "Stock status report confirming zero saleable quantity of the batch."},
        {"type": "corrective", "action":
         f"Complete the root cause investigation for the reported {defect or 'defect'} and "
         "extend the assessment to all batches sharing the implicated component or line.",
         "owner_function": "Quality Assurance", "due_in_days": tat_days(severity),
         "effectiveness_check": "Investigation report approved with a confirmed or eliminated root cause."},
        {"type": "preventive", "action":
         "Update the relevant in-process control or inspection step and retrain the affected "
         "shift, then trend the defect category for two subsequent campaigns.",
         "owner_function": "Production", "due_in_days": 45,
         "effectiveness_check": "No recurrence of the same defect category across the next two campaigns."},
    ]


def fallback_summary(form: dict) -> str:
    product = form.get("product_name") or "the reported product"
    strength = f" {form['product_strength']}" if form.get("product_strength") else ""
    batch = form.get("batch_number") or "an unidentified batch"
    defect = (form.get("complaint_type") or "a quality defect").lower()
    severity = form.get("severity") or "pending"
    source = form.get("complaint_source") or "the complainant"
    return (
        f"{source} reported {defect} affecting {product}{strength}, batch {batch}. "
        f"Initial GMP classification is {severity}; the batch should be placed on hold and "
        f"the complaint sample requested for comparative testing against the retained sample."
    )
