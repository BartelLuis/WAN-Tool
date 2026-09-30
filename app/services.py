from __future__ import annotations

import csv
import io
from collections.abc import Iterable
from datetime import date

from sqlalchemy.orm import Session

from app.models import (
    Angebot,
    AngebotStatus,
    Angebotsanfrage,
    AnfrageStatus,
    Leitung,
    LeitungStatus,
)

CSV_SPALTEN = [
    "ID",
    "Bezeichnung",
    "Art",
    "Technologie",
    "Status",
    "Provider",
    "Standort A",
    "Standort B",
    "Down (Mbit/s)",
    "Up (Mbit/s)",
    "Sprachkanaele",
    "Rufnummernblock",
    "Circuit-ID",
    "Anschlusskennung",
    "Transfernetz",
    "LAN-Netz",
    "SLA",
    "Vertragsnummer",
    "Kosten monatlich",
    "Kosten einmalig",
    "Vertragsbeginn",
    "Vertragsende",
    "Kuendigungsfrist (Monate)",
]


def leitungen_csv(leitungen: Iterable[Leitung]) -> str:
    puffer = io.StringIO()
    writer = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_SPALTEN)
    for leitung in leitungen:
        writer.writerow(
            [
                leitung.id,
                leitung.bezeichnung,
                leitung.art.value,
                leitung.technologie.value,
                leitung.status.value,
                leitung.provider.name if leitung.provider else "",
                leitung.standort_a.name if leitung.standort_a else "",
                leitung.standort_b.name if leitung.standort_b else "",
                leitung.bandbreite_down_mbit or "",
                leitung.bandbreite_up_mbit or "",
                leitung.sprachkanaele or "",
                leitung.rufnummernblock or "",
                leitung.circuit_id or "",
                leitung.anschlusskennung or "",
                leitung.ip_transfernetz or "",
                leitung.ip_lan_netz or "",
                leitung.sla or "",
                leitung.vertragsnummer or "",
                leitung.kosten_monatlich or "",
                leitung.kosten_einmalig or "",
                leitung.vertragsbeginn or "",
                leitung.vertragsende or "",
                leitung.kuendigungsfrist_monate or "",
            ]
        )
    return puffer.getvalue()


def anfragetext(anfrage: Angebotsanfrage, angebot: Angebot | None = None) -> str:
    """Erzeugt einen versandfertigen Text fuer die Angebotsanfrage."""
    anrede = "Sehr geehrte Damen und Herren,"
    if angebot and angebot.provider.ansprechpartner:
        anrede = f"Hallo {angebot.provider.ansprechpartner},"

    zeilen = [
        anrede,
        "",
        f"wir bitten um ein Angebot fuer folgende {anfrage.art.value}-Leitung:",
        "",
        f"Vorgang: {anfrage.titel}",
    ]
    if anfrage.standort_a:
        zeilen.append(f"Standort A: {anfrage.standort_a.name} ({anfrage.standort_a.anschrift})")
    if anfrage.standort_b:
        zeilen.append(f"Standort B: {anfrage.standort_b.name} ({anfrage.standort_b.anschrift})")
    if anfrage.wunsch_technologie:
        zeilen.append(f"Gewuenschte Technologie: {anfrage.wunsch_technologie.value}")
    if anfrage.wunsch_down_mbit or anfrage.wunsch_up_mbit:
        zeilen.append(
            f"Bandbreite: {anfrage.wunsch_down_mbit or 0} / {anfrage.wunsch_up_mbit or 0} Mbit/s"
        )
    if anfrage.wunsch_sprachkanaele:
        zeilen.append(f"Sprachkanaele: {anfrage.wunsch_sprachkanaele}")
    if anfrage.wunsch_laufzeit_monate:
        zeilen.append(f"Vertragslaufzeit: {anfrage.wunsch_laufzeit_monate} Monate")
    if anfrage.wunsch_termin:
        zeilen.append(f"Gewuenschter Bereitstellungstermin: {anfrage.wunsch_termin:%d.%m.%Y}")
    if anfrage.anforderungen:
        zeilen += ["", "Weitere Anforderungen:", anfrage.anforderungen]
    if anfrage.abgabefrist:
        zeilen += ["", f"Bitte senden Sie uns Ihr Angebot bis zum {anfrage.abgabefrist:%d.%m.%Y}."]
    zeilen += [
        "",
        "Bitte weisen Sie einmalige und monatliche Kosten, Laufzeit, Bereitstellungszeit und SLA separat aus.",
        "",
        "Mit freundlichen Gruessen",
    ]
    return "\n".join(zeilen)


def angebot_beauftragen(db: Session, angebot: Angebot) -> Leitung:
    """Setzt ein Angebot auf 'beauftragt' und legt die dokumentierte Leitung an."""
    anfrage = angebot.anfrage
    for anderes in anfrage.angebote:
        if anderes.id != angebot.id and anderes.status != AngebotStatus.KEIN_ANGEBOT:
            anderes.status = AngebotStatus.ABGELEHNT
    angebot.status = AngebotStatus.BEAUFTRAGT
    anfrage.status = AnfrageStatus.BEAUFTRAGT

    leitung = Leitung(
        bezeichnung=anfrage.titel,
        art=anfrage.art,
        technologie=angebot.technologie or anfrage.wunsch_technologie,
        status=LeitungStatus.BESTELLT,
        provider_id=angebot.provider_id,
        standort_a_id=anfrage.standort_a_id,
        standort_b_id=anfrage.standort_b_id,
        bandbreite_down_mbit=angebot.bandbreite_down_mbit or anfrage.wunsch_down_mbit,
        bandbreite_up_mbit=angebot.bandbreite_up_mbit or anfrage.wunsch_up_mbit,
        sprachkanaele=angebot.sprachkanaele or anfrage.wunsch_sprachkanaele,
        kosten_monatlich=angebot.kosten_monatlich,
        kosten_einmalig=angebot.kosten_einmalig,
        kuendigungsfrist_monate=3,
        sla=angebot.sla,
        notizen=f"Angelegt aus Angebotsanfrage #{anfrage.id} am {date.today():%d.%m.%Y}.",
        anfrage_id=anfrage.id,
    )
    if angebot.laufzeit_monate:
        leitung.verlaengerung_monate = 12
    db.add(leitung)
    db.commit()
    db.refresh(leitung)
    return leitung
