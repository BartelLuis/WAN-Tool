import logging
import time
from contextlib import asynccontextmanager
from datetime import date, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import Base, engine, get_db
from app.models import Angebotsanfrage, AnfrageStatus, Leitung, LeitungStatus, Provider, Standort
from app.routers import anfragen, api, leitungen, provider, standorte
from app.templating import templates

logger = logging.getLogger("wantool")


def init_db(versuche: int = 30, pause: float = 2.0) -> None:
    for versuch in range(1, versuche + 1):
        try:
            Base.metadata.create_all(engine)
            return
        except OperationalError as exc:
            logger.warning("Datenbank nicht erreichbar (%s/%s): %s", versuch, versuche, exc)
            time.sleep(pause)
    raise RuntimeError("Datenbankverbindung konnte nicht aufgebaut werden.")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title=settings.app_title, lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")

app.include_router(standorte.router)
app.include_router(provider.router)
app.include_router(leitungen.router)
app.include_router(anfragen.router)
app.include_router(api.router)


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    stichtag = date.today() + timedelta(days=120)
    kennzahlen = {
        "standorte": db.scalar(select(func.count(Standort.id))) or 0,
        "provider": db.scalar(select(func.count(Provider.id))) or 0,
        "leitungen": db.scalar(select(func.count(Leitung.id))) or 0,
        "aktiv": db.scalar(
            select(func.count(Leitung.id)).where(Leitung.status == LeitungStatus.AKTIV)
        )
        or 0,
        "kosten": db.scalar(
            select(func.coalesce(func.sum(Leitung.kosten_monatlich), 0)).where(
                Leitung.status == LeitungStatus.AKTIV
            )
        ),
        "offene_anfragen": db.scalar(
            select(func.count(Angebotsanfrage.id)).where(
                Angebotsanfrage.status.notin_(
                    [AnfrageStatus.BEAUFTRAGT, AnfrageStatus.ABGEBROCHEN]
                )
            )
        )
        or 0,
    }

    auslaufend = db.scalars(
        select(Leitung)
        .where(Leitung.vertragsende.is_not(None), Leitung.vertragsende <= stichtag)
        .order_by(Leitung.vertragsende)
    ).all()
    letzte_anfragen = db.scalars(
        select(Angebotsanfrage).order_by(Angebotsanfrage.id.desc()).limit(5)
    ).all()
    nach_status = db.execute(
        select(Leitung.status, func.count(Leitung.id)).group_by(Leitung.status)
    ).all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "kennzahlen": kennzahlen,
            "auslaufend": auslaufend,
            "letzte_anfragen": letzte_anfragen,
            "nach_status": nach_status,
        },
    )
