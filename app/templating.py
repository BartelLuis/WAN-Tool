from pathlib import Path

from fastapi.templating import Jinja2Templates

from app import models
from app.config import settings

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
templates.env.globals.update(
    app_title=settings.app_title,
    Leitungsart=models.Leitungsart,
    Technologie=models.Technologie,
    LeitungStatus=models.LeitungStatus,
    AnfrageStatus=models.AnfrageStatus,
    AngebotStatus=models.AngebotStatus,
)

_STATUS_FARBEN = {
    models.LeitungStatus.AKTIV: "success",
    models.LeitungStatus.GEPLANT: "secondary",
    models.LeitungStatus.BESTELLT: "info",
    models.LeitungStatus.IN_AUFBAU: "info",
    models.LeitungStatus.GESTOERT: "danger",
    models.LeitungStatus.GEKUENDIGT: "warning",
    models.LeitungStatus.AUSSER_BETRIEB: "dark",
    models.AnfrageStatus.ENTWURF: "secondary",
    models.AnfrageStatus.VERSENDET: "info",
    models.AnfrageStatus.ANGEBOTE_ERHALTEN: "primary",
    models.AnfrageStatus.ENTSCHIEDEN: "success",
    models.AnfrageStatus.BEAUFTRAGT: "success",
    models.AnfrageStatus.ABGEBROCHEN: "dark",
    models.AngebotStatus.ANGEFRAGT: "secondary",
    models.AngebotStatus.ANGEBOTEN: "primary",
    models.AngebotStatus.ABGELEHNT: "warning",
    models.AngebotStatus.BEAUFTRAGT: "success",
    models.AngebotStatus.KEIN_ANGEBOT: "dark",
}


def status_farbe(status: object) -> str:
    return _STATUS_FARBEN.get(status, "secondary")  # type: ignore[arg-type]


def euro(wert: object) -> str:
    if wert is None:
        return "-"
    return f"{float(wert):,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")


def datum(wert: object) -> str:
    if wert is None:
        return "-"
    return wert.strftime("%d.%m.%Y")  # type: ignore[attr-defined]


templates.env.filters["euro"] = euro
templates.env.filters["datum"] = datum
templates.env.globals["status_farbe"] = status_farbe
