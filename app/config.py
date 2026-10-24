import os
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    """Configuration from environment variables (or a local .env file).

    Secrets can also be read from files: when SECRETS_DIR is set, a file named
    after the field (e.g. <SECRETS_DIR>/db_password) provides its value. This is
    how Kubernetes mounts them, so they never appear in the process environment.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "bugtracker"
    db_user: str = "bugtracker"
    db_password: SecretStr = SecretStr("")
    # Full URL override, used by tests (e.g. sqlite).
    database_url: str | None = None

    secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    # Set to true when the app is served over HTTPS.
    cookie_secure: bool = False

    enable_docs: bool = False

    def sqlalchemy_url(self) -> URL | str:
        if self.database_url:
            return self.database_url
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings(_secrets_dir=os.environ.get("SECRETS_DIR") or None)
