from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ECHO_", env_file=".env")

    db_path: str = "echo.db"
    shared_token: str = "dev-token"          # simple single-user access guard
    playlist_id: str = ""                    # the YouTube playlist to watch
    client_secret_file: str = "client_secret.json"
    token_file: str = "token.json"
    web_dir: str = str(Path(__file__).resolve().parent.parent / "web")
    home_region: str = ""                    # ISO 3166-1 alpha-2 (e.g. JP); flags region blocks
    snapshot_hour: int = 4                   # daily job hour (local)


settings = Settings()
