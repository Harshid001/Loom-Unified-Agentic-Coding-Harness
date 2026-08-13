import json

from cryptography.fernet import Fernet

from loom.api.webhooks import WebhookEngine, WebhookSubscription
from loom.api.late_hardening import apply_late_hardening


def test_webhook_secret_encrypted_at_rest(tmp_path, monkeypatch):
    monkeypatch.setenv("LOOM_ENV", "development")
    monkeypatch.setenv("LOOM_WEBHOOK_SECRET_KEY", Fernet.generate_key().decode())
    engine = WebhookEngine(storage_dir=str(tmp_path / "webhooks"))
    apply_late_hardening(type("Module", (), {"app": type("App", (), {"add_middleware": lambda *_: None})()})())

    subscription = WebhookSubscription(
        id="sub_1",
        org_id="org_1",
        url="https://example.com/webhook",
        secret="plaintext-secret",
    )
    engine.register(subscription)

    raw = json.loads((tmp_path / "webhooks" / "subscriptions.json").read_text(encoding="utf-8"))
    assert raw[0]["secret"] != "plaintext-secret"
    assert raw[0]["secret"].startswith("enc:")
