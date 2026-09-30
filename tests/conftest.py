"""Gemeinsame Testvorrichtungen.

Standardmaessig laeuft die Suite gegen SQLite. In der CI wird ueber
``TEST_DATABASE_URL`` zusaetzlich gegen MySQL getestet.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

_tmp = Path(tempfile.mkdtemp(prefix="wantool-test-"))
os.environ.setdefault("DATABASE_URL_OVERRIDE", f"sqlite:///{_tmp / 'test.db'}")
os.environ.setdefault("TEST_DATABASE_URL", os.environ["DATABASE_URL_OVERRIDE"])
os.environ["DATABASE_URL_OVERRIDE"] = (
    os.environ.get("TEST_DATABASE_URL") or os.environ["DATABASE_URL_OVERRIDE"]
)
os.environ.setdefault("SESSION_SECRET", "testgeheimnis-mindestens-32-zeichen-lang!!")
os.environ.setdefault("UMGEBUNG", "test")
os.environ.setdefault("COOKIE_SECURE", "false")
os.environ.setdefault("ADMIN_PASSWORT", "Start!Passwort123")
os.environ.setdefault("START_MANDANT_NAME", "Musterland")
os.environ.setdefault("START_MANDANT_KENNZEICHEN", "KR-ML")
os.environ.setdefault("START_MANDANT_ART", "Kreis")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Benutzer, Mandant, MandantArt, Rolle  # noqa: E402
from app.security import hash_passwort  # noqa: E402

PASSWORT = "Test!Passwort123"


@pytest.fixture(autouse=True)
def frische_datenbank() -> Iterator[None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def db() -> Iterator:
    verbindung = engine.connect()
    if engine.dialect.name == "mysql":
        verbindung = verbindung.execution_options(isolation_level="READ COMMITTED")
    sitzung = SessionLocal(bind=verbindung)
    try:
        yield sitzung
    finally:
        sitzung.close()
        verbindung.close()


@pytest.fixture
def client() -> Iterator[TestClient]:
    # Der Lifespan wird bewusst nicht gestartet: die Tabellen legt die Fixture an.
    with TestClient(app, base_url="http://testserver") as testclient:
        yield testclient


def mandant_anlegen(
    db,
    name: str,
    kennzeichen: str,
    art: MandantArt = MandantArt.GEMEINDE,
    uebergeordnet: Mandant | None = None,
) -> Mandant:
    mandant = Mandant(
        name=name,
        kennzeichen=kennzeichen,
        art=art,
        uebergeordnet_id=uebergeordnet.id if uebergeordnet else None,
    )
    db.add(mandant)
    db.commit()
    db.refresh(mandant)
    return mandant


def benutzer_anlegen(
    db,
    benutzername: str,
    mandant: Mandant,
    rolle: Rolle = Rolle.BEARBEITER,
    sieht_untergeordnete: bool = False,
) -> Benutzer:
    konto = Benutzer(
        benutzername=benutzername,
        name=benutzername.title(),
        passwort_hash=hash_passwort(PASSWORT),
        rolle=rolle,
        mandant_id=mandant.id,
        sieht_untergeordnete=sieht_untergeordnete,
        passwort_aendern=False,
    )
    db.add(konto)
    db.commit()
    db.refresh(konto)
    return konto


def csrf_holen(client: TestClient, pfad: str = "/login") -> str:
    antwort = client.get(pfad)
    inhalt = antwort.text
    marke = 'name="csrf_token" value="'
    start = inhalt.index(marke) + len(marke)
    return inhalt[start : inhalt.index('"', start)]


def anmelden(client: TestClient, benutzername: str, passwort: str = PASSWORT):
    token = csrf_holen(client)
    return client.post(
        "/login",
        data={"benutzername": benutzername, "passwort": passwort, "csrf_token": token},
        follow_redirects=False,
    )


def absenden(client: TestClient, pfad: str, daten: dict, referenz: str = "/"):
    """Sendet ein Formular inklusive gueltigem CSRF-Token."""
    daten = dict(daten)
    daten["csrf_token"] = csrf_holen(client, referenz)
    return client.post(pfad, data=daten, follow_redirects=False)
