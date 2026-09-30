"""Sicherheits- und Mandantentests."""

from __future__ import annotations

from app.models import (
    AuditEintrag,
    Benutzer,
    Leitung,
    Leitungsart,
    Mandant,
    MandantArt,
    Provider,
    Rolle,
    Standort,
)
from tests.conftest import (
    PASSWORT,
    absenden,
    anmelden,
    benutzer_anlegen,
    csrf_holen,
    mandant_anlegen,
)


def _grunddaten(db):
    kreis = mandant_anlegen(db, "Musterkreis", "KR-MK", MandantArt.KREIS)
    gemeinde = mandant_anlegen(db, "Musterhausen", "GEM-MH", MandantArt.GEMEINDE, kreis)
    stadt = mandant_anlegen(db, "Musterstadt", "ST-MS", MandantArt.STADT)
    return kreis, gemeinde, stadt


def _leitung(db, mandant: Mandant, bezeichnung: str) -> Leitung:
    leitung = Leitung(mandant_id=mandant.id, bezeichnung=bezeichnung, art=Leitungsart.WAN)
    db.add(leitung)
    db.commit()
    db.refresh(leitung)
    return leitung


# ------------------------------------------------------------------ Anmeldung


def test_ohne_anmeldung_umleitung_auf_login(client):
    antwort = client.get("/leitungen", follow_redirects=False)
    assert antwort.status_code == 303
    assert antwort.headers["location"] == "/login"


def test_api_ohne_anmeldung_liefert_401(client):
    assert client.get("/api/leitungen").status_code == 401


def test_anmeldung_und_zugriff(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)

    assert anmelden(client, "sachbearbeiter").status_code == 303
    assert client.get("/leitungen").status_code == 200


def test_falsches_passwort_wird_abgewiesen(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)

    antwort = anmelden(client, "sachbearbeiter", "falsch")
    assert antwort.status_code == 401
    assert "Benutzername oder Passwort" in antwort.text


def test_konto_wird_nach_fehlversuchen_gesperrt(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)

    for _ in range(5):
        anmelden(client, "sachbearbeiter", "falsch")

    # Auch mit korrektem Passwort bleibt der Zugang bis zum Ablauf der Sperre zu.
    antwort = anmelden(client, "sachbearbeiter")
    assert antwort.status_code == 401
    assert "gesperrt" in antwort.text

    db.expire_all()
    assert db.query(Benutzer).filter_by(benutzername="sachbearbeiter").one().gesperrt_bis


def test_unbekannter_benutzer_liefert_gleiche_meldung(client):
    antwort = anmelden(client, "existiert-nicht")
    assert antwort.status_code == 401
    assert "Benutzername oder Passwort" in antwort.text


def test_deaktiviertes_konto_verliert_sitzung_sofort(client, db):
    _, gemeinde, _ = _grunddaten(db)
    konto = benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter")
    assert client.get("/leitungen").status_code == 200

    konto.aktiv = False
    db.commit()

    antwort = client.get("/leitungen", follow_redirects=False)
    assert antwort.status_code == 303


def test_passwortwechsel_wird_erzwungen(client, db):
    _, gemeinde, _ = _grunddaten(db)
    konto = benutzer_anlegen(db, "neuling", gemeinde)
    konto.passwort_aendern = True
    db.commit()

    anmelden(client, "neuling")
    antwort = client.get("/leitungen", follow_redirects=False)
    assert antwort.status_code == 303
    assert antwort.headers["location"] == "/passwort"

    ergebnis = absenden(
        client,
        "/passwort",
        {
            "altes_passwort": PASSWORT,
            "neues_passwort": "Neues!Passwort987",
            "wiederholung": "Neues!Passwort987",
        },
        referenz="/passwort",
    )
    assert ergebnis.status_code == 303
    assert client.get("/leitungen").status_code == 200


def test_schwaches_passwort_wird_abgelehnt(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter")

    antwort = absenden(
        client,
        "/passwort",
        {"altes_passwort": PASSWORT, "neues_passwort": "kurz", "wiederholung": "kurz"},
        referenz="/passwort",
    )
    assert antwort.status_code == 400
    assert "Vorgaben" in antwort.text or "erfuellt nicht" in antwort.text


# ----------------------------------------------------------------------- CSRF


def test_post_ohne_csrf_token_wird_abgewiesen(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter")

    antwort = client.post(
        "/standorte/speichern",
        data={"mandant_id": str(gemeinde.id), "name": "Ohne Token"},
        follow_redirects=False,
    )
    assert antwort.status_code == 403


def test_post_mit_fremdem_csrf_token_wird_abgewiesen(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter")

    antwort = client.post(
        "/standorte/speichern",
        data={"mandant_id": str(gemeinde.id), "name": "Falsch", "csrf_token": "x" * 43},
        follow_redirects=False,
    )
    assert antwort.status_code == 403


# ------------------------------------------------------------ Sicherheitskopf


def test_sicherheitskopfzeilen_sind_gesetzt(client):
    kopf = client.get("/login").headers
    assert "default-src 'none'" in kopf["content-security-policy"]
    assert kopf["x-frame-options"] == "DENY"
    assert kopf["x-content-type-options"] == "nosniff"
    assert kopf["referrer-policy"] == "no-referrer"


def test_keine_externen_quellen_in_der_oberflaeche(client):
    assert "cdn." not in client.get("/login").text


def test_api_dokumentation_ist_abgeschaltet(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter")

    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


# ---------------------------------------------------------- Mandantentrennung


def test_fremder_mandant_ist_nicht_sichtbar(client, db):
    _, gemeinde, stadt = _grunddaten(db)
    benutzer_anlegen(db, "gemeinde-ma", gemeinde)
    eigene = _leitung(db, gemeinde, "Rathaus Musterhausen")
    fremde = _leitung(db, stadt, "Rathaus Musterstadt")

    anmelden(client, "gemeinde-ma")

    seite = client.get("/leitungen").text
    assert "Rathaus Musterhausen" in seite
    assert "Rathaus Musterstadt" not in seite

    assert client.get(f"/leitungen/{eigene.id}").status_code == 200
    # 404 statt 403: die Existenz fremder Datensaetze wird nicht preisgegeben.
    assert client.get(f"/leitungen/{fremde.id}").status_code == 404
    assert client.get(f"/api/leitungen/{fremde.id}").status_code == 404


def test_schreiben_in_fremden_mandanten_ist_untersagt(client, db):
    _, gemeinde, stadt = _grunddaten(db)
    benutzer_anlegen(db, "gemeinde-ma", gemeinde)
    anmelden(client, "gemeinde-ma")

    antwort = absenden(
        client,
        "/standorte/speichern",
        {"mandant_id": str(stadt.id), "name": "Fremdeintrag"},
    )
    assert antwort.status_code == 403
    assert db.query(Standort).filter_by(name="Fremdeintrag").count() == 0


def test_kreis_sieht_untergeordnete_gemeinde(client, db):
    kreis, gemeinde, stadt = _grunddaten(db)
    benutzer_anlegen(db, "kreis-ma", kreis, sieht_untergeordnete=True)
    _leitung(db, gemeinde, "Rathaus Musterhausen")
    _leitung(db, stadt, "Rathaus Musterstadt")

    anmelden(client, "kreis-ma")
    seite = client.get("/leitungen").text
    assert "Rathaus Musterhausen" in seite
    assert "Rathaus Musterstadt" not in seite


def test_kreis_darf_untergeordnete_nicht_bearbeiten(client, db):
    kreis, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "kreis-ma", kreis, sieht_untergeordnete=True)
    fremde = _leitung(db, gemeinde, "Rathaus Musterhausen")

    anmelden(client, "kreis-ma")
    assert client.get(f"/leitungen/{fremde.id}").status_code == 200
    assert client.get(f"/leitungen/{fremde.id}/bearbeiten").status_code == 403


def test_administrator_sieht_alle_mandanten(client, db):
    _, gemeinde, stadt = _grunddaten(db)
    benutzer_anlegen(db, "zentral-admin", gemeinde, rolle=Rolle.ADMIN)
    _leitung(db, gemeinde, "Rathaus Musterhausen")
    _leitung(db, stadt, "Rathaus Musterstadt")

    anmelden(client, "zentral-admin")
    seite = client.get("/leitungen").text
    assert "Rathaus Musterhausen" in seite
    assert "Rathaus Musterstadt" in seite


def test_verknuepfung_ueber_mandantengrenze_wird_abgelehnt(client, db):
    _, gemeinde, stadt = _grunddaten(db)
    benutzer_anlegen(db, "zentral-admin", gemeinde, rolle=Rolle.ADMIN)
    fremder_standort = Standort(mandant_id=stadt.id, name="Fremdstandort")
    db.add(fremder_standort)
    db.commit()

    anmelden(client, "zentral-admin")
    antwort = absenden(
        client,
        "/leitungen/speichern",
        {
            "mandant_id": str(gemeinde.id),
            "bezeichnung": "Unzulaessig",
            "standort_a_id": str(fremder_standort.id),
        },
    )
    assert antwort.status_code == 400
    assert db.query(Leitung).filter_by(bezeichnung="Unzulaessig").count() == 0


# --------------------------------------------------------------------- Rollen


def test_leser_darf_nicht_schreiben(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "nur-lesen", gemeinde, rolle=Rolle.LESER)
    anmelden(client, "nur-lesen")

    assert client.get("/leitungen").status_code == 200
    antwort = absenden(
        client, "/standorte/speichern", {"mandant_id": str(gemeinde.id), "name": "Neu"}
    )
    assert antwort.status_code == 403
    assert db.query(Standort).count() == 0


def test_bearbeiter_erreicht_verwaltung_nicht(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter")
    assert client.get("/verwaltung/benutzer").status_code == 403


def test_mandant_admin_darf_keine_administratoren_anlegen(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "orts-admin", gemeinde, rolle=Rolle.MANDANT_ADMIN)
    anmelden(client, "orts-admin")

    antwort = absenden(
        client,
        "/verwaltung/benutzer/speichern",
        {
            "benutzername": "neuer-admin",
            "name": "Neuer Admin",
            "rolle": Rolle.ADMIN.value,
            "mandant_id": str(gemeinde.id),
            "aktiv": "1",
        },
        referenz="/verwaltung/benutzer",
    )
    assert antwort.status_code == 403
    assert db.query(Benutzer).filter_by(benutzername="neuer-admin").count() == 0


def test_mandant_admin_darf_keine_fremden_konten_anlegen(client, db):
    _, gemeinde, stadt = _grunddaten(db)
    benutzer_anlegen(db, "orts-admin", gemeinde, rolle=Rolle.MANDANT_ADMIN)
    anmelden(client, "orts-admin")

    antwort = absenden(
        client,
        "/verwaltung/benutzer/speichern",
        {
            "benutzername": "fremd",
            "name": "Fremd",
            "rolle": Rolle.LESER.value,
            "mandant_id": str(stadt.id),
            "aktiv": "1",
        },
        referenz="/verwaltung/benutzer",
    )
    assert antwort.status_code == 403


def test_nur_administrator_legt_mandanten_an(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "orts-admin", gemeinde, rolle=Rolle.MANDANT_ADMIN)
    anmelden(client, "orts-admin")

    antwort = absenden(
        client,
        "/verwaltung/mandanten/speichern",
        {"name": "Neues Amt", "kennzeichen": "AMT-N", "art": MandantArt.AMT.value, "aktiv": "1"},
        referenz="/verwaltung/mandanten",
    )
    assert antwort.status_code == 403
    assert db.query(Mandant).filter_by(name="Neues Amt").count() == 0


# ---------------------------------------------------------------- Audit-Log


def test_aenderungen_werden_protokolliert(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter")

    absenden(
        client,
        "/standorte/speichern",
        {"mandant_id": str(gemeinde.id), "name": "Rathaus", "land": "Deutschland"},
    )

    eintraege = db.query(AuditEintrag).all()
    aktionen = {e.aktion for e in eintraege}
    assert "anmeldung" in aktionen
    assert "gespeichert" in aktionen
    gespeichert = next(e for e in eintraege if e.aktion == "gespeichert")
    assert gespeichert.benutzername == "sachbearbeiter"
    assert gespeichert.mandant_id == gemeinde.id


def test_fehlanmeldung_wird_protokolliert(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter", "falsch")

    assert db.query(AuditEintrag).filter_by(aktion="anmeldung_fehlgeschlagen").count() == 1


# ----------------------------------------------------- Fachlicher Ablauf


def test_beauftragung_legt_leitung_im_richtigen_mandanten_an(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter")

    absenden(
        client,
        "/provider/speichern",
        {"mandant_id": str(gemeinde.id), "name": "Beispielcarrier"},
    )
    provider = db.query(Provider).one()

    absenden(
        client,
        "/anfragen/speichern",
        {
            "mandant_id": str(gemeinde.id),
            "titel": "WAN Rathaus",
            "art": Leitungsart.WAN.value,
            "status": "Entwurf",
        },
    )
    anfrage_id = client.get("/api/anfragen").json()[0]["id"]

    absenden(
        client,
        f"/anfragen/{anfrage_id}/provider-hinzufuegen",
        {"provider_ids": str(provider.id)},
        referenz=f"/anfragen/{anfrage_id}",
    )
    angebot_id = client.get(f"/api/anfragen/{anfrage_id}").json()["angebote"][0]["id"]

    absenden(
        client,
        f"/anfragen/{anfrage_id}/angebote/{angebot_id}/speichern",
        {"status": "angeboten", "kosten_monatlich": "750,00", "laufzeit_monate": "36"},
        referenz=f"/anfragen/{anfrage_id}/angebote/{angebot_id}",
    )
    absenden(
        client,
        f"/anfragen/{anfrage_id}/angebote/{angebot_id}/beauftragen",
        {},
        referenz=f"/anfragen/{anfrage_id}",
    )

    leitung = db.query(Leitung).one()
    assert leitung.mandant_id == gemeinde.id
    assert leitung.provider_id == provider.id
    assert str(leitung.kosten_monatlich) == "750.00"


def test_csv_export_enthaelt_nur_eigene_leitungen(client, db):
    _, gemeinde, stadt = _grunddaten(db)
    benutzer_anlegen(db, "gemeinde-ma", gemeinde)
    _leitung(db, gemeinde, "Eigene Leitung")
    _leitung(db, stadt, "Fremde Leitung")

    anmelden(client, "gemeinde-ma")
    inhalt = client.get("/leitungen/export.csv").text
    assert "Eigene Leitung" in inhalt
    assert "Fremde Leitung" not in inhalt


def test_doppelter_name_je_mandant_erlaubt(client, db):
    _, gemeinde, stadt = _grunddaten(db)
    benutzer_anlegen(db, "zentral-admin", gemeinde, rolle=Rolle.ADMIN)
    anmelden(client, "zentral-admin")

    for mandant in (gemeinde, stadt):
        antwort = absenden(
            client, "/standorte/speichern", {"mandant_id": str(mandant.id), "name": "Rathaus"}
        )
        assert antwort.status_code == 303

    assert db.query(Standort).filter_by(name="Rathaus").count() == 2

    # Innerhalb eines Mandanten bleibt der Name eindeutig.
    antwort = absenden(
        client, "/standorte/speichern", {"mandant_id": str(gemeinde.id), "name": "Rathaus"}
    )
    assert antwort.status_code == 409


def test_abmelden_beendet_die_sitzung(client, db):
    _, gemeinde, _ = _grunddaten(db)
    benutzer_anlegen(db, "sachbearbeiter", gemeinde)
    anmelden(client, "sachbearbeiter")

    token = csrf_holen(client, "/")
    assert client.post("/abmelden", data={"csrf_token": token}).status_code == 200
    assert client.get("/leitungen", follow_redirects=False).status_code == 303
