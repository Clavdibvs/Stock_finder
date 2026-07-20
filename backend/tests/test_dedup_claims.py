"""Dedup: articoli quasi identici, 100 copie = 1 origine; rumor resta rumor."""
from __future__ import annotations

from datetime import UTC, datetime

from app.claims.dedup import (
    content_hash, hamming_distance, is_near_duplicate, normalize_url, simhash,
)
from app.claims.graph import assign_duplicate_family, compute_narrative_stats, confirm_claim
from app.models import Claim, Document, Security


def _doc(security_id: int, url: str, title: str, excerpt: str,
         level: int = 8, seen: datetime | None = None) -> Document:
    return Document(
        security_id=security_id, url_canonical=url, title=title, excerpt=excerpt,
        source_level=level, first_seen_at=seen or datetime.now(UTC),
        published_at=seen or datetime.now(UTC),
    )


class TestNormalizeUrl:
    def test_strips_tracking(self):
        a = normalize_url("https://Example.com/news/story/?utm_source=x&utm_campaign=y&fbclid=z")
        b = normalize_url("https://example.com/news/story")
        assert a == b

    def test_keeps_meaningful_params(self):
        a = normalize_url("https://example.com/q?id=123&utm_source=x")
        assert "id=123" in a and "utm_source" not in a


class TestNearDuplicates:
    TEXT = ("La società ha annunciato risultati positivi dello studio di Fase 2 "
            "con endpoint primario raggiunto in 193 pazienti e profilo di "
            "sicurezza favorevole secondo il comunicato ufficiale.")

    def test_exact_hash(self):
        assert content_hash(self.TEXT) == content_hash(self.TEXT + "  ")

    def test_near_duplicate_detected(self):
        variant = self.TEXT.replace("secondo il comunicato ufficiale",
                                    "come riportato dal comunicato ufficiale")
        assert is_near_duplicate(self.TEXT, variant)

    def test_different_articles_not_duplicates(self):
        other = ("Il produttore di semiconduttori ha presentato ricavi trimestrali "
                 "in calo del 12% con margini compressi e guidance ridotta per "
                 "l'intero esercizio fiscale in corso.")
        assert not is_near_duplicate(self.TEXT, other)
        assert hamming_distance(simhash(self.TEXT), simhash(other)) > 8


class TestHundredDuplicates:
    def test_hundred_copies_one_origin(self, db):
        """Cento riscritture della stessa notizia = UNA origine informativa."""
        sec = Security(name="Test Corp", is_demo=True)
        db.add(sec)
        db.flush()
        origin = _doc(sec.id, "https://origin.com/story", "Notizia originale importante",
                      "Il contenuto della notizia originale con molti dettagli rilevanti "
                      "sull'operazione societaria annunciata oggi.", level=3)
        db.add(origin)
        db.flush()
        assign_duplicate_family(db, origin)
        for i in range(100):
            copy = _doc(sec.id, f"https://copysite{i}.com/rewrite?utm_source=feed{i}",
                        "Notizia originale importante",
                        "Il contenuto della notizia originale con molti dettagli rilevanti "
                        "sull'operazione societaria annunciata oggi.", level=10)
            db.add(copy)
            db.flush()
            assign_duplicate_family(db, copy)
        db.flush()
        stats = compute_narrative_stats(db, sec.id)
        assert stats.total_documents == 101
        assert stats.duplicate_documents == 100
        assert stats.independent_origins == 1  # non 101

    def test_two_origins_counted(self, db):
        sec = Security(name="Two Origins Corp", is_demo=True)
        db.add(sec)
        db.flush()
        d1 = _doc(sec.id, "https://a.com/1", "Prima notizia sull'acquisizione",
                  "Testo completamente diverso che parla di trattative in corso "
                  "per una possibile acquisizione della società da parte di un fondo.")
        d2 = _doc(sec.id, "https://b.com/2", "Analisi dei conti trimestrali",
                  "Approfondimento indipendente sui margini, sulla cassa disponibile "
                  "e sulla sostenibilità del debito della società nel prossimo anno.")
        for d in (d1, d2):
            db.add(d)
            db.flush()
            assign_duplicate_family(db, d)
        stats = compute_narrative_stats(db, sec.id)
        assert stats.independent_origins == 2


class TestRumorStaysRumor:
    def test_duplicate_cannot_confirm(self, db):
        """Un duplicato non promuove MAI un rumor a fatto."""
        sec = Security(name="Rumor Corp", is_demo=True)
        db.add(sec)
        db.flush()
        rumor_doc = _doc(sec.id, "https://news.com/rumor", "Voci di acquisizione",
                         "Secondo fonti anonime la società sarebbe in trattative.", level=6)
        db.add(rumor_doc)
        db.flush()
        assign_duplicate_family(db, rumor_doc)
        claim = Claim(security_id=sec.id, subject="Acquirente", predicate="tratterebbe",
                      object="acquisizione", status="rumor", confirmation_level=6,
                      evidence_span="sarebbe in trattative", source_document_id=rumor_doc.id)
        db.add(claim)
        db.flush()

        dup = _doc(sec.id, "https://copy.com/rumor?utm_source=x", "Voci di acquisizione",
                   "Secondo fonti anonime la società sarebbe in trattative.", level=10)
        db.add(dup)
        db.flush()
        assign_duplicate_family(db, dup)
        assert dup.is_duplicate
        confirm_claim(db, claim, dup)
        assert claim.status == "rumor"  # resta rumor

    def test_secondary_source_cannot_confirm(self, db):
        sec = Security(name="Rumor2 Corp", is_demo=True)
        db.add(sec)
        db.flush()
        claim = Claim(security_id=sec.id, subject="X", predicate="farebbe", object="Y",
                      status="rumor", confirmation_level=6, evidence_span="span di prova valido")
        db.add(claim)
        db.flush()
        blog = _doc(sec.id, "https://blog.com/op", "Un'opinione diversa e originale",
                    "Testo di un blog che ripete la voce senza fonti primarie originali.",
                    level=8)
        db.add(blog)
        db.flush()
        assign_duplicate_family(db, blog)
        confirm_claim(db, claim, blog)
        assert claim.status == "rumor"

    def test_primary_source_confirms(self, db):
        sec = Security(name="Confirm Corp", is_demo=True)
        db.add(sec)
        db.flush()
        claim = Claim(security_id=sec.id, subject="X", predicate="acquisisce", object="Y",
                      status="rumor", confirmation_level=6, evidence_span="span di prova valido")
        db.add(claim)
        db.flush()
        filing = _doc(sec.id, "https://sec.gov/8k", "8-K merger agreement",
                      "La società ha stipulato un merger agreement definitivo con "
                      "l'acquirente per un corrispettivo in contanti.", level=1)
        db.add(filing)
        db.flush()
        assign_duplicate_family(db, filing)
        confirm_claim(db, claim, filing)
        assert claim.status == "fatto"
        assert claim.confirmation_level == 1
