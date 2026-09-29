from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models import (
    AngebotStatus,
    AnfrageStatus,
    Leitungsart,
    LeitungStatus,
    Technologie,
)


class Basis(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class StandortOut(Basis):
    id: int
    name: str
    kurzzeichen: str | None
    strasse: str | None
    plz: str | None
    ort: str | None
    land: str
    ansprechpartner: str | None
    telefon: str | None


class ProviderOut(Basis):
    id: int
    name: str
    kundennummer: str | None
    ansprechpartner: str | None
    email: str | None
    telefon: str | None
    stoerungshotline: str | None


class LeitungOut(Basis):
    id: int
    bezeichnung: str
    art: Leitungsart
    technologie: Technologie
    status: LeitungStatus
    provider: ProviderOut | None
    standort_a: StandortOut | None
    standort_b: StandortOut | None
    bandbreite_down_mbit: int | None
    bandbreite_up_mbit: int | None
    sprachkanaele: int | None
    rufnummernblock: str | None
    circuit_id: str | None
    anschlusskennung: str | None
    ip_transfernetz: str | None
    ip_lan_netz: str | None
    sla: str | None
    vertragsnummer: str | None
    kosten_monatlich: Decimal | None
    kosten_einmalig: Decimal | None
    vertragsbeginn: date | None
    vertragsende: date | None
    kuendigungsfrist_monate: int | None


class AngebotOut(Basis):
    id: int
    provider: ProviderOut
    status: AngebotStatus
    angebotsnummer: str | None
    angefragt_am: date | None
    eingegangen_am: date | None
    gueltig_bis: date | None
    technologie: Technologie | None
    bandbreite_down_mbit: int | None
    bandbreite_up_mbit: int | None
    kosten_monatlich: Decimal | None
    kosten_einmalig: Decimal | None
    laufzeit_monate: int | None
    bereitstellung_wochen: int | None
    sla: str | None
    tco: Decimal | None


class AnfrageOut(Basis):
    id: int
    titel: str
    art: Leitungsart
    status: AnfrageStatus
    standort_a: StandortOut | None
    standort_b: StandortOut | None
    wunsch_technologie: Technologie | None
    wunsch_down_mbit: int | None
    wunsch_up_mbit: int | None
    wunsch_laufzeit_monate: int | None
    abgabefrist: date | None
    angebote: list[AngebotOut]
