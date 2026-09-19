"""Reference data so the register, dashboard and duplicate detector are alive
on first run. Every record is a plausible market complaint for an API / FDF
manufacturer; none of it is real.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.complaint import AuditEvent, Complaint

logger = logging.getLogger(__name__)


def _d(days_ago: int) -> date:
    return date.today() - timedelta(days=days_ago)


SEED: list[dict] = [
    dict(
        days_ago=2,
        complaint_source="Distributor / Wholesaler",
        customer_name="Meridian Pharma Distribution, Hyderabad",
        customer_contact="qa@meridianpharma.example",
        customer_country="India",
        product_name="Ceftrioxam 1 g Injection",
        product_strength="1 g",
        dosage_form="Lyophilised Powder for Injection",
        batch_number="CFX23A417",
        manufacturing_date=_d(410),
        expiry_date=_d(-320),
        quantity_affected=42,
        quantity_unit="vials",
        market_country="India",
        complaint_type="Foreign Particulate Matter",
        description=(
            "Pharmacy reported visible black fibrous particulate suspended in the "
            "reconstituted solution of 42 vials from a single carton. Particles were "
            "observed against a white background under standard inspection lighting. "
            "Affected vials have been segregated and are available for collection."
        ),
        severity="Critical",
        priority="P1 - Immediate",
        status="Under Investigation",
        ai_risk_score=82.0,
        ai_risk_band="Severe",
        sample_available=True,
    ),
    dict(
        days_ago=5,
        complaint_source="Healthcare Professional",
        customer_name="St. Alban's Teaching Hospital Pharmacy",
        customer_contact="pharmacy@stalbans.example",
        customer_country="United Kingdom",
        product_name="Metformin Hydrochloride Prolonged Release 1000 mg",
        product_strength="1000 mg",
        dosage_form="Film-Coated Tablet",
        batch_number="MET4419B",
        manufacturing_date=_d(300),
        expiry_date=_d(-430),
        quantity_affected=3,
        quantity_unit="bottles",
        market_country="United Kingdom",
        complaint_type="Physical / Appearance Defect",
        description=(
            "Three bottles contained tablets with capping and lamination of the film "
            "coat. Approximately 10% of tablets in each bottle are affected. No patient "
            "harm reported."
        ),
        severity="Major",
        priority="P2 - High",
        status="CAPA Initiated",
        ai_risk_score=51.0,
        ai_risk_band="High",
        sample_available=True,
    ),
    dict(
        days_ago=9,
        complaint_source="Customer Email",
        customer_name="Nordvik Apotek AS",
        customer_contact="kvalitet@nordvikapotek.example",
        customer_country="Norway",
        product_name="Amoxicillin Oral Suspension 250 mg/5 ml",
        product_strength="250 mg/5 ml",
        dosage_form="Oral Suspension",
        batch_number="AMX7781",
        manufacturing_date=_d(210),
        expiry_date=_d(-150),
        quantity_affected=1,
        quantity_unit="bottles",
        market_country="Norway",
        complaint_type="Colour / Odour Variation",
        description=(
            "Customer reported the reconstituted suspension had an atypical sharp odour "
            "and a noticeably darker shade than previous purchases. Product was used for "
            "two doses before the complaint was raised; no adverse effect reported."
        ),
        severity="Major",
        priority="P2 - High",
        status="Pending Closure Approval",
        ai_risk_score=44.0,
        ai_risk_band="Moderate",
        sample_available=False,
    ),
    dict(
        days_ago=14,
        complaint_source="Contract Manufacturing Partner",
        customer_name="Helix CDMO, Singapore",
        customer_contact="qa.helix@helixcdmo.example",
        customer_country="Singapore",
        product_name="Atorvastatin Calcium API",
        product_strength="Bulk API",
        dosage_form="Active Pharmaceutical Ingredient (Bulk)",
        batch_number="ATC2291",
        manufacturing_date=_d(180),
        expiry_date=_d(-720),
        quantity_affected=25,
        quantity_unit="kg",
        market_country="Singapore",
        complaint_type="Out of Specification (Assay / Potency)",
        description=(
            "Incoming QC at the customer site reported assay of 97.2% against a "
            "specification of 98.0-102.0%. Result confirmed on re-test from a second "
            "sampling point of the same drum."
        ),
        severity="Major",
        priority="P2 - High",
        status="Under Investigation",
        ai_risk_score=56.0,
        ai_risk_band="High",
        sample_available=True,
    ),
    dict(
        days_ago=21,
        complaint_source="Patient / Consumer",
        customer_name="R. Almeida",
        customer_contact="r.almeida@mail.example",
        customer_country="Portugal",
        product_name="Ibuprofen 400 mg",
        product_strength="400 mg",
        dosage_form="Film-Coated Tablet",
        batch_number="IBU5502",
        manufacturing_date=_d(260),
        expiry_date=_d(-500),
        quantity_affected=1,
        quantity_unit="packs",
        market_country="Portugal",
        complaint_type="Packaging Defect",
        description=(
            "Two blister pockets in a 24-tablet pack were empty on opening. Foil was "
            "intact with no sign of tampering."
        ),
        severity="Minor",
        priority="P3 - Normal",
        status="Closed",
        ai_risk_score=17.0,
        ai_risk_band="Low",
        sample_available=True,
    ),
    dict(
        days_ago=36,
        complaint_source="Distributor / Wholesaler",
        customer_name="Meridian Pharma Distribution, Hyderabad",
        customer_contact="qa@meridianpharma.example",
        customer_country="India",
        product_name="Ceftrioxam 1 g Injection",
        product_strength="1 g",
        dosage_form="Lyophilised Powder for Injection",
        batch_number="CFX23A417",
        manufacturing_date=_d(410),
        expiry_date=_d(-320),
        quantity_affected=6,
        quantity_unit="vials",
        market_country="India",
        complaint_type="Foreign Particulate Matter",
        description=(
            "Earlier report of dark particulate matter observed in six vials from the same "
            "consignment. Reported by the same distributor warehouse QA team."
        ),
        severity="Critical",
        priority="P1 - Immediate",
        status="Under Investigation",
        ai_risk_score=79.0,
        ai_risk_band="Severe",
        sample_available=True,
    ),
    dict(
        days_ago=48,
        complaint_source="Medical Representative",
        customer_name="Field report — Northern Region",
        customer_contact="field.north@internal.example",
        customer_country="India",
        product_name="Levothyroxine Sodium 50 mcg",
        product_strength="50 mcg",
        dosage_form="Tablet",
        batch_number="LEV1180",
        manufacturing_date=_d(340),
        expiry_date=_d(-260),
        quantity_affected=12,
        quantity_unit="strips",
        market_country="India",
        complaint_type="Labelling Error",
        description=(
            "Carton declares 50 mcg while the blister foil overprint reads 25 mcg on "
            "twelve strips from one shipper. Strength on the tablet itself could not be "
            "verified visually."
        ),
        severity="Critical",
        priority="P1 - Immediate",
        status="Pending Triage",
        ai_risk_score=76.0,
        ai_risk_band="Severe",
        sample_available=True,
    ),
    dict(
        days_ago=23,
        complaint_source="Internal QA Notification",
        customer_name="Warehouse QA — Site B",
        customer_contact="warehouse.qa@internal.example",
        customer_country="India",
        product_name="Insulin Glargine 100 IU/ml",
        product_strength="100 IU/ml",
        dosage_form="Pre-filled Syringe",
        batch_number="ING9043",
        manufacturing_date=_d(120),
        expiry_date=_d(-540),
        quantity_affected=240,
        quantity_unit="syringes",
        market_country="India",
        complaint_type="Cold Chain / Temperature Excursion",
        description=(
            "Data logger for shipment SHP-2291 recorded 14 hours above 8 °C with a peak "
            "of 16.4 °C during transit. Consignment quarantined on receipt pending "
            "stability impact assessment."
        ),
        severity="Major",
        priority="P2 - High",
        status="CAPA Initiated",
        ai_risk_score=61.0,
        ai_risk_band="High",
        sample_available=True,
    ),
]


def seed_if_empty() -> int:
    """Insert reference complaints when the register is empty. Idempotent."""
    db = SessionLocal()
    try:
        existing = db.execute(select(Complaint.id).limit(1)).first()
        if existing:
            return 0

        year = date.today().year
        # A realistic register is not 100% AI-assisted; a third of records are
        # still typed straight into the form by the analyst.
        channels = ["document", "email", "manual", "document", "text", "manual", "document", "email"]
        for index, row in enumerate(SEED, start=1):
            days_ago = row.pop("days_ago")
            created = datetime.now(timezone.utc) - timedelta(days=days_ago)
            severity = row.get("severity", "Minor")
            tat = {"Critical": 3, "Major": 15, "Minor": 30}[severity]
            received = _d(days_ago)

            complaint = Complaint(
                reference=f"CMP-{year}-{index:04d}",
                complaint_date=received,
                date_received=received,
                due_date=received + timedelta(days=tat),
                intake_channel=channels[(index - 1) % len(channels)],
                created_at=created,
                updated_at=created,
                ai_confidence=0.86,
                ai_summary=(
                    f"{row.get('complaint_source')} reported "
                    f"{(row.get('complaint_type') or 'a defect').lower()} affecting "
                    f"{row.get('product_name')}, batch {row.get('batch_number')}. "
                    f"Classified {severity}."
                ),
                **row,
            )
            db.add(complaint)
            db.flush()
            db.add(
                AuditEvent(
                    complaint_id=complaint.id, actor="system.seed", actor_type="human",
                    action="created", detail="Reference record loaded for demonstration.",
                    created_at=created,
                )
            )
        db.commit()
        logger.info("seeded %s reference complaints", len(SEED))
        return len(SEED)
    except Exception:  # noqa: BLE001
        db.rollback()
        logger.exception("seeding failed")
        return 0
    finally:
        db.close()
