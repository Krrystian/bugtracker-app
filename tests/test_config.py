import secrets

from app.config import Settings


def test_secrets_are_read_from_files(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.delenv("DB_PASSWORD", raising=False)
    key = secrets.token_urlsafe(48)
    (tmp_path / "secret_key").write_text(key)
    (tmp_path / "db_password").write_text("from-file")

    settings = Settings(_secrets_dir=str(tmp_path), _env_file=None)

    assert settings.secret_key.get_secret_value() == key
    assert settings.db_password.get_secret_value() == "from-file"
