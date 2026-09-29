from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Leitungsart(str, enum.Enum):
    WAN = "WAN"
    TK = "TK"


class Technologie(str, enum.Enum):
    MPLS = "MPLS"
    SD_WAN = "SD-WAN"
    ETHERNET = "Ethernet / Standleitung"
    GLASFASER = "Glasfaser"
    DSL = "DSL / VDSL"
    SDSL = "SDSL"
    KABEL = "Kabel (DOCSIS)"
    MOBILFUNK = "Mobilfunk (LTE/5G)"
    RICHTFUNK = "Richtfunk"
    SATELLIT = "Satellit"
    SIP_TRUNK = "SIP-Trunk"
    ISDN_PMX = "ISDN Primaermultiplex"
    ISDN_S0 = "ISDN Basisanschluss"
    ANALOG = "Analoganschluss"
    SONSTIGE = "Sonstige"


class LeitungStatus(str, enum.Enum):
    GEPLANT = "geplant"
    BESTELLT = "bestellt"
    IN_AUFBAU = "in Aufbau"
    AKTIV = "aktiv"
    GESTOERT = "gestoert"
    GEKUENDIGT = "gekuendigt"
    AUSSER_BETRIEB = "ausser Betrieb"


class AnfrageStatus(str, enum.Enum):
    ENTWURF = "Entwurf"
    VERSENDET = "versendet"
    ANGEBOTE_ERHALTEN = "Angebote erhalten"
    ENTSCHIEDEN = "entschieden"
    BEAUFTRAGT = "beauftragt"
    ABGEBROCHEN = "abgebrochen"


class AngebotStatus(str, enum.Enum):
    ANGEFRAGT = "angefragt"
    ANGEBOTEN = "angeboten"
    ABGELEHNT = "abgelehnt"
    BEAUFTRAGT = "beauftragt"
    KEIN_ANGEBOT = "kein Angebot"


class TimestampMixin:
    erstellt_am: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    geaendert_am: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class Standort(TimestampMixin, Base):
    __tablename__ = "standorte"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    kurzzeichen: Mapped[str | None] = mapped_column(String(20))
    strasse: Mapped[str | None] = mapped_column(String(160))
    plz: Mapped[str | None] = mapped_column(String(10))
    ort: Mapped[str | None] = mapped_column(String(120))
    land: Mapped[str] = mapped_column(String(60), default="Deutschland")
    ansprechpartner: Mapped[str | None] = mapped_column(String(120))
    telefon: Mapped[str | None] = mapped_column(String(60))
    notizen: Mapped[str | None] = mapped_column(Text)

    @property
    def anschrift(self) -> str:
        teile = [self.strasse, " ".join(filter(None, [self.plz, self.ort])), self.land]
        return ", ".join(t for t in teile if t)

    def __str__(self) -> str:
        return self.name


class Provider(TimestampMixin, Base):
    __tablename__ = "provider"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    kundennummer: Mapped[str | None] = mapped_column(String(60))
    ansprechpartner: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(160))
    telefon: Mapped[str | None] = mapped_column(String(60))
    webseite: Mapped[str | None] = mapped_column(String(200))
    stoerungshotline: Mapped[str | None] = mapped_column(String(60))
    notizen: Mapped[str | None] = mapped_column(Text)

    def __str__(self) -> str:
        return self.name


class Leitung(TimestampMixin, Base):
    __tablename__ = "leitungen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bezeichnung: Mapped[str] = mapped_column(String(160))
    art: Mapped[Leitungsart] = mapped_column(Enum(Leitungsart), default=Leitungsart.WAN)
    technologie: Mapped[Technologie] = mapped_column(
        Enum(Technologie), default=Technologie.SONSTIGE
    )
    status: Mapped[LeitungStatus] = mapped_column(
        Enum(LeitungStatus), default=LeitungStatus.GEPLANT
    )

    provider_id: Mapped[int | None] = mapped_column(ForeignKey("provider.id", ondelete="SET NULL"))
    standort_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("standorte.id", ondelete="SET NULL")
    )
    standort_b_id: Mapped[int | None] = mapped_column(
        ForeignKey("standorte.id", ondelete="SET NULL")
    )

    provider: Mapped[Provider | None] = relationship()
    standort_a: Mapped[Standort | None] = relationship(foreign_keys=[standort_a_id])
    standort_b: Mapped[Standort | None] = relationship(foreign_keys=[standort_b_id])

    # Technische Daten
    bandbreite_down_mbit: Mapped[int | None] = mapped_column(Integer)
    bandbreite_up_mbit: Mapped[int | None] = mapped_column(Integer)
    sprachkanaele: Mapped[int | None] = mapped_column(Integer)
    rufnummernblock: Mapped[str | None] = mapped_column(String(160))
    circuit_id: Mapped[str | None] = mapped_column(String(120))
    anschlusskennung: Mapped[str | None] = mapped_column(String(120))
    ip_transfernetz: Mapped[str | None] = mapped_column(String(120))
    ip_lan_netz: Mapped[str | None] = mapped_column(String(120))
    router_typ: Mapped[str | None] = mapped_column(String(120))
    sla: Mapped[str | None] = mapped_column(String(120))

    # Kaufmaennische Daten
    vertragsnummer: Mapped[str | None] = mapped_column(String(120))
    kosten_monatlich: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    kosten_einmalig: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    vertragsbeginn: Mapped[date | None] = mapped_column(Date)
    vertragsende: Mapped[date | None] = mapped_column(Date)
    kuendigungsfrist_monate: Mapped[int | None] = mapped_column(Integer)
    verlaengerung_monate: Mapped[int | None] = mapped_column(Integer)

    notizen: Mapped[str | None] = mapped_column(Text)

    anfrage_id: Mapped[int | None] = mapped_column(
        ForeignKey("angebotsanfragen.id", ondelete="SET NULL")
    )
    anfrage: Mapped[Angebotsanfrage | None] = relationship(back_populates="leitungen")

    @property
    def bandbreite_text(self) -> str:
        if self.bandbreite_down_mbit is None and self.bandbreite_up_mbit is None:
            return "-"
        down = self.bandbreite_down_mbit or 0
        up = self.bandbreite_up_mbit or 0
        return f"{down} / {up} Mbit/s"

    def __str__(self) -> str:
        return self.bezeichnung


class Angebotsanfrage(TimestampMixin, Base):
    __tablename__ = "angebotsanfragen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titel: Mapped[str] = mapped_column(String(160))
    art: Mapped[Leitungsart] = mapped_column(Enum(Leitungsart), default=Leitungsart.WAN)
    status: Mapped[AnfrageStatus] = mapped_column(
        Enum(AnfrageStatus), default=AnfrageStatus.ENTWURF
    )

    standort_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("standorte.id", ondelete="SET NULL")
    )
    standort_b_id: Mapped[int | None] = mapped_column(
        ForeignKey("standorte.id", ondelete="SET NULL")
    )
    standort_a: Mapped[Standort | None] = relationship(foreign_keys=[standort_a_id])
    standort_b: Mapped[Standort | None] = relationship(foreign_keys=[standort_b_id])

    wunsch_technologie: Mapped[Technologie | None] = mapped_column(Enum(Technologie))
    wunsch_down_mbit: Mapped[int | None] = mapped_column(Integer)
    wunsch_up_mbit: Mapped[int | None] = mapped_column(Integer)
    wunsch_sprachkanaele: Mapped[int | None] = mapped_column(Integer)
    wunsch_laufzeit_monate: Mapped[int | None] = mapped_column(Integer)
    wunsch_termin: Mapped[date | None] = mapped_column(Date)
    abgabefrist: Mapped[date | None] = mapped_column(Date)
    anforderungen: Mapped[str | None] = mapped_column(Text)
    notizen: Mapped[str | None] = mapped_column(Text)

    angebote: Mapped[list[Angebot]] = relationship(
        back_populates="anfrage", cascade="all, delete-orphan", order_by="Angebot.id"
    )
    leitungen: Mapped[list[Leitung]] = relationship(back_populates="anfrage")

    def __str__(self) -> str:
        return self.titel


class Angebot(TimestampMixin, Base):
    __tablename__ = "angebote"
    __table_args__ = (UniqueConstraint("anfrage_id", "provider_id", name="uq_anfrage_provider"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anfrage_id: Mapped[int] = mapped_column(
        ForeignKey("angebotsanfragen.id", ondelete="CASCADE")
    )
    provider_id: Mapped[int] = mapped_column(ForeignKey("provider.id", ondelete="CASCADE"))

    anfrage: Mapped[Angebotsanfrage] = relationship(back_populates="angebote")
    provider: Mapped[Provider] = relationship()

    status: Mapped[AngebotStatus] = mapped_column(
        Enum(AngebotStatus), default=AngebotStatus.ANGEFRAGT
    )
    angebotsnummer: Mapped[str | None] = mapped_column(String(120))
    angefragt_am: Mapped[date | None] = mapped_column(Date)
    eingegangen_am: Mapped[date | None] = mapped_column(Date)
    gueltig_bis: Mapped[date | None] = mapped_column(Date)

    technologie: Mapped[Technologie | None] = mapped_column(Enum(Technologie))
    bandbreite_down_mbit: Mapped[int | None] = mapped_column(Integer)
    bandbreite_up_mbit: Mapped[int | None] = mapped_column(Integer)
    sprachkanaele: Mapped[int | None] = mapped_column(Integer)
    kosten_monatlich: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    kosten_einmalig: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    laufzeit_monate: Mapped[int | None] = mapped_column(Integer)
    bereitstellung_wochen: Mapped[int | None] = mapped_column(Integer)
    sla: Mapped[str | None] = mapped_column(String(120))
    dokument_link: Mapped[str | None] = mapped_column(String(300))
    notizen: Mapped[str | None] = mapped_column(Text)

    @property
    def tco(self) -> Decimal | None:
        """Gesamtkosten ueber die angebotene Laufzeit."""
        if self.kosten_monatlich is None:
            return None
        laufzeit = self.laufzeit_monate or 0
        return self.kosten_monatlich * laufzeit + (self.kosten_einmalig or Decimal(0))
