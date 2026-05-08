"""Core redaction engine: detect entities with Presidio, replace with consistent fakes."""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Iterable

from faker import Faker
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from refinery.recognizers import custom_recognizers

log = logging.getLogger(__name__)

logging.getLogger("tldextract").setLevel(logging.ERROR)

DEFAULT_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "CREDIT_CARD",
    "IBAN_CODE",
    "IP_ADDRESS",
    "URL",
    "LOCATION",
    "DATE_TIME",
    "NRP",
    "CRYPTO",
    "US_SSN",
    "US_DRIVER_LICENSE",
    "US_PASSPORT",
    "US_ITIN",
    "US_BANK_NUMBER",
    "MEDICAL_LICENSE",
    "MEDICAL_RECORD_NUMBER",
    "HEALTH_PLAN_NUMBER",
]


@dataclass
class RedactionResult:
    text: str
    mapping: dict[str, dict[str, str]] = field(default_factory=dict)

    def merge_mapping_into(self, target: dict[str, dict[str, str]]) -> None:
        for entity, pairs in self.mapping.items():
            target.setdefault(entity, {}).update(pairs)


def _seed_for(entity_type: str, original: str) -> int:
    h = hashlib.sha256(f"{entity_type}::{original}".encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


class Redactor:
    """Detects PII/PHI and replaces with consistent fake values.

    The same `(entity_type, original_value)` always maps to the same fake within
    a single Redactor instance. Pass an existing mapping in to extend it across
    runs (e.g., loaded from a sidecar JSON file).
    """

    def __init__(
        self,
        entities: Iterable[str] | None = None,
        score_threshold: float = 0.4,
        mapping: dict[str, dict[str, str]] | None = None,
        locale: str = "en_US",
    ) -> None:
        self.entities = list(entities) if entities is not None else list(DEFAULT_ENTITIES)
        self.score_threshold = score_threshold
        self.mapping: dict[str, dict[str, str]] = mapping or {}
        self._faker_locale = locale
        self._analyzer = self._build_analyzer()

    def _build_analyzer(self) -> AnalyzerEngine:
        provider = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }
        )
        nlp_engine = provider.create_engine()
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers(nlp_engine=nlp_engine)
        for r in custom_recognizers():
            registry.add_recognizer(r)
        return AnalyzerEngine(nlp_engine=nlp_engine, registry=registry)

    def _fake_for(self, entity_type: str, original: str) -> str:
        existing = self.mapping.get(entity_type, {}).get(original)
        if existing is not None:
            return existing

        faker = Faker(self._faker_locale)
        faker.seed_instance(_seed_for(entity_type, original))

        generators = {
            "PERSON": faker.name,
            "EMAIL_ADDRESS": faker.email,
            "PHONE_NUMBER": faker.phone_number,
            "CREDIT_CARD": faker.credit_card_number,
            "IBAN_CODE": faker.iban,
            "IP_ADDRESS": faker.ipv4,
            "URL": faker.url,
            "LOCATION": faker.city,
            "DATE_TIME": lambda: faker.date(),
            "NRP": faker.country,
            "CRYPTO": lambda: faker.sha256()[:34],
            "US_SSN": faker.ssn,
            "US_DRIVER_LICENSE": lambda: faker.bothify("?#######").upper(),
            "US_PASSPORT": lambda: faker.bothify("?########").upper(),
            "US_ITIN": lambda: faker.bothify("9##-##-####"),
            "US_BANK_NUMBER": faker.bban,
            "MEDICAL_LICENSE": lambda: faker.bothify("??#######").upper(),
            "MEDICAL_RECORD_NUMBER": lambda: f"MRN-{faker.numerify('########')}",
            "HEALTH_PLAN_NUMBER": lambda: faker.bothify("???-########").upper(),
        }
        gen = generators.get(entity_type, lambda: f"[{entity_type}]")
        fake = gen()
        self.mapping.setdefault(entity_type, {})[original] = fake
        return fake

    def redact(self, text: str, language: str = "en") -> RedactionResult:
        if not text:
            return RedactionResult(text=text, mapping={})

        results = self._analyzer.analyze(
            text=text,
            language=language,
            entities=self.entities,
            score_threshold=self.score_threshold,
        )
        results = sorted(results, key=lambda r: (r.start, -r.end))

        out_parts: list[str] = []
        cursor = 0
        last_end = 0
        run_mapping: dict[str, dict[str, str]] = {}

        for r in results:
            if r.start < last_end:
                continue
            out_parts.append(text[cursor:r.start])
            original = text[r.start:r.end]
            fake = self._fake_for(r.entity_type, original)
            run_mapping.setdefault(r.entity_type, {})[original] = fake
            out_parts.append(fake)
            cursor = r.end
            last_end = r.end

        out_parts.append(text[cursor:])
        redacted = "".join(out_parts)

        replacements: list[tuple[str, str]] = []
        for entity_pairs in self.mapping.values():
            for original, fake in entity_pairs.items():
                if original and original != fake and original not in fake:
                    replacements.append((original, fake))
        replacements.sort(key=lambda p: len(p[0]), reverse=True)
        for original, fake in replacements:
            if original in redacted:
                redacted = redacted.replace(original, fake)
                etype = self._entity_type_for(original)
                run_mapping.setdefault(etype, {})[original] = fake

        return RedactionResult(text=redacted, mapping=run_mapping)

    def _entity_type_for(self, original: str) -> str:
        for etype, pairs in self.mapping.items():
            if original in pairs:
                return etype
        return "UNKNOWN"
