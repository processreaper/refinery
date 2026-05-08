"""Custom recognizers for PHI/PII not covered well by Presidio defaults."""

from presidio_analyzer import Pattern, PatternRecognizer


def medical_record_number() -> PatternRecognizer:
    patterns = [
        Pattern(
            name="mrn_labelled",
            regex=r"\b(?:MRN|Medical\s+Record(?:\s+Number)?|Patient\s+ID)[:#\s]*([A-Z0-9-]{5,15})\b",
            score=0.85,
        ),
        Pattern(
            name="mrn_bare",
            regex=r"\bMRN[-:]?\s?\d{5,10}\b",
            score=0.75,
        ),
    ]
    return PatternRecognizer(
        supported_entity="MEDICAL_RECORD_NUMBER",
        patterns=patterns,
        context=["mrn", "medical", "record", "patient", "chart"],
    )


def health_plan_number() -> PatternRecognizer:
    patterns = [
        Pattern(
            name="health_plan_labelled",
            regex=r"\b(?:Health\s+Plan|Member\s+ID|Policy(?:\s+Number)?)[:#\s]*([A-Z0-9-]{6,20})\b",
            score=0.7,
        ),
    ]
    return PatternRecognizer(
        supported_entity="HEALTH_PLAN_NUMBER",
        patterns=patterns,
        context=["health", "plan", "insurance", "policy", "member"],
    )


def us_ssn_strong() -> PatternRecognizer:
    """Catches XXX-XX-XXXX in any SSN-like context.

    Presidio's stock US_SSN recognizer is conservative and misses many
    obvious labelled SSNs; this fills the gap.
    """
    patterns = [
        Pattern(
            name="ssn_dashed",
            regex=r"\b(?!000|666|9\d{2})\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b",
            score=0.7,
        ),
    ]
    return PatternRecognizer(
        supported_entity="US_SSN",
        patterns=patterns,
        context=["ssn", "social", "security"],
    )


def custom_recognizers():
    return [medical_record_number(), health_plan_number(), us_ssn_strong()]
