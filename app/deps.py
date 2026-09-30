"""Abhaengigkeiten fuer Anmeldung, Rollenpruefung und Mandantentrennung."""

from __future__ import annotations

from typing import Annotated, TypeVar

from fastapi import Depends, HTTPException, Request
from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.database import Base, get_db
from app.models import Benutzer, Mandant

T = TypeVar("T", bound=Base)


def aktueller_benutzer(request: Request, db: Session = Depends(get_db)) -> Benutzer:
    benutzer_id = request.session.get("benutzer_id")
    if benutzer_id is None:
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    benutzer = db.get(Benutzer, benutzer_id)
    if benutzer is None or not benutzer.aktiv:
        request.session.clear()
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    return benutzer


Angemeldet = Annotated[Benutzer, Depends(aktueller_benutzer)]


def schreibrecht(benutzer: Angemeldet) -> Benutzer:
    if not benutzer.darf_schreiben:
        raise HTTPException(status_code=403, detail="Nur Lesezugriff fuer diese Rolle.")
    return benutzer


def verwaltungsrecht(benutzer: Angemeldet) -> Benutzer:
    if not benutzer.darf_verwalten:
        raise HTTPException(status_code=403, detail="Verwaltungsrechte erforderlich.")
    return benutzer


def adminrecht(benutzer: Angemeldet) -> Benutzer:
    if not benutzer.ist_admin:
        raise HTTPException(status_code=403, detail="Administratorrechte erforderlich.")
    return benutzer


Bearbeiter = Annotated[Benutzer, Depends(schreibrecht)]
Verwalter = Annotated[Benutzer, Depends(verwaltungsrecht)]
Administrator = Annotated[Benutzer, Depends(adminrecht)]


def sichtbare_mandanten(db: Session, benutzer: Benutzer) -> set[int] | None:
    """IDs der einsehbaren Mandanten. ``None`` bedeutet: alle (nur Administrator)."""
    if benutzer.ist_admin:
        return None
    if not benutzer.sieht_untergeordnete:
        return {benutzer.mandant_id}
    mandant = db.get(Mandant, benutzer.mandant_id)
    return mandant.nachfahren_ids() if mandant else {benutzer.mandant_id}


def beschraenke(stmt: Select, modell: type[T], db: Session, benutzer: Benutzer) -> Select:
    """Schraenkt eine Abfrage auf die fuer den Benutzer sichtbaren Mandanten ein."""
    ids = sichtbare_mandanten(db, benutzer)
    if ids is None:
        return stmt
    return stmt.where(modell.mandant_id.in_(ids))


def darf_sehen(db: Session, benutzer: Benutzer, mandant_id: int) -> bool:
    ids = sichtbare_mandanten(db, benutzer)
    return ids is None or mandant_id in ids


def darf_bearbeiten(db: Session, benutzer: Benutzer, mandant_id: int) -> bool:
    """Geschrieben wird nur im eigenen Mandanten; Admins duerfen ueberall."""
    if benutzer.ist_admin:
        return True
    return mandant_id == benutzer.mandant_id


def hole_im_mandanten(db: Session, modell: type[T], obj_id: int, benutzer: Benutzer) -> T:
    obj = db.get(modell, obj_id)
    if obj is None or not darf_sehen(db, benutzer, obj.mandant_id):
        # Kein Unterschied zwischen "fehlt" und "fremder Mandant": keine Existenzpreisgabe.
        raise HTTPException(status_code=404, detail="Datensatz nicht gefunden.")
    return obj


def hole_bearbeitbar(db: Session, modell: type[T], obj_id: int, benutzer: Benutzer) -> T:
    obj = hole_im_mandanten(db, modell, obj_id, benutzer)
    if not darf_bearbeiten(db, benutzer, obj.mandant_id):
        raise HTTPException(status_code=403, detail="Datensatz gehoert einem anderen Mandanten.")
    return obj


def auswahl_mandanten(db: Session, benutzer: Benutzer) -> list[Mandant]:
    """Mandanten, die im Formular als Zuordnung angeboten werden."""
    stmt = select(Mandant).where(Mandant.aktiv.is_(True)).order_by(Mandant.name)
    if not benutzer.ist_admin:
        stmt = stmt.where(Mandant.id == benutzer.mandant_id)
    return list(db.scalars(stmt))
