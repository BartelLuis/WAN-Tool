import secrets
from urllib.parse import quote_plus

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Datenbank ---
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3307
    mysql_database: str = "wantool"
    mysql_user: str = "wantool"
    mysql_password: str = ""
    database_url_override: str = ""

    # --- Betrieb ---
    app_title: str = "WAN- & TK-Leitungsdokumentation"
    behoerde: str = "Kommunale IT"
    umgebung: str = "produktion"
    docs_aktiv: bool = False

    # --- Sitzung und Anmeldung ---
    session_secret: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    session_cookie: str = "wantool_session"
    session_leerlauf_minuten: int = 20
    session_maximal_minuten: int = 480
    cookie_secure: bool = True
    vertraue_proxy_header: bool = False
    erlaubte_hosts_roh: str = "*"

    passwort_mindestlaenge: int = 12
    max_fehlversuche: int = 5
    sperrdauer_minuten: int = 15

    # --- Ersteinrichtung beim allerersten Start ---
    start_mandant_name: str = "Muster"
    start_mandant_kennzeichen: str = "MUSTER"
    start_mandant_art: str = "Sonstige"
    admin_benutzer: str = "admin"
    admin_passwort: str = ""

    @field_validator("umgebung")
    @classmethod
    def _umgebung_klein(cls, wert: str) -> str:
        return wert.strip().lower()

    @property
    def ist_produktion(self) -> bool:
        return self.umgebung == "produktion"

    @property
    def erlaubte_hosts(self) -> list[str]:
        return [h.strip() for h in self.erlaubte_hosts_roh.split(",") if h.strip()] or ["*"]

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"mysql+pymysql://{quote_plus(self.mysql_user)}:{quote_plus(self.mysql_password)}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}?charset=utf8mb4"
        )


settings = Settings()
