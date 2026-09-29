from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import forms, schemas
from app.database import get_db
from app.models import Angebotsanfrage, Leitung, Leitungsart, LeitungStatus, Provider, Standort
from app.routers.common import hole_oder_404

router = APIRouter(prefix="/api", tags=["API"])


@router.get("/standorte", response_model=list[schemas.StandortOut])
def standorte(db: Session = Depends(get_db)):
    return db.scalars(select(Standort).order_by(Standort.name)).all()


@router.get("/provider", response_model=list[schemas.ProviderOut])
def provider(db: Session = Depends(get_db)):
    return db.scalars(select(Provider).order_by(Provider.name)).all()


@router.get("/leitungen", response_model=list[schemas.LeitungOut])
def leitungen(db: Session = Depends(get_db), art: str = "", status: str = ""):
    stmt = select(Leitung).order_by(Leitung.bezeichnung)
    if (art_enum := forms.to_enum(Leitungsart, art)) is not None:
        stmt = stmt.where(Leitung.art == art_enum)
    if (status_enum := forms.to_enum(LeitungStatus, status)) is not None:
        stmt = stmt.where(Leitung.status == status_enum)
    return db.scalars(stmt).all()


@router.get("/leitungen/{leitung_id}", response_model=schemas.LeitungOut)
def leitung(leitung_id: int, db: Session = Depends(get_db)):
    return hole_oder_404(db, Leitung, leitung_id)


@router.get("/anfragen", response_model=list[schemas.AnfrageOut])
def anfragen(db: Session = Depends(get_db)):
    return db.scalars(select(Angebotsanfrage).order_by(Angebotsanfrage.id.desc())).all()


@router.get("/anfragen/{anfrage_id}", response_model=schemas.AnfrageOut)
def anfrage(anfrage_id: int, db: Session = Depends(get_db)):
    return hole_oder_404(db, Angebotsanfrage, anfrage_id)
