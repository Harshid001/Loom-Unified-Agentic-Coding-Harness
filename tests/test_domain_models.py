import pytest

from loom.business.models import RepoConnection, RepoProvider


class TestRepoConnection:
    def test_create_with_vault_token_ref(self):
        conn = RepoConnection.create(
            org_id="org_1",
            provider=RepoProvider.GITHUB,
            install_token_ref="vault:github_install_abc123",
            remote_url="https://github.com/acme/widgets",
        )
        assert conn.org_id == "org_1"
        assert conn.provider == RepoProvider.GITHUB
        assert conn.install_token_ref == "vault:github_install_abc123"

    def test_create_rejects_raw_token(self):
        with pytest.raises(ValueError, match="vault"):
            RepoConnection.create(
                org_id="org_1",
                provider=RepoProvider.GITHUB,
                install_token_ref="ghp_RAWTOKEN123",
            )

    def test_local_connection_requires_no_token_ref(self):
        conn = RepoConnection.create(
            org_id="org_1",
            provider=RepoProvider.LOCAL,
            install_token_ref="vault:local",
            repo_path="/srv/repos/widgets",
        )
        assert conn.provider == RepoProvider.LOCAL

    def test_spec_contract_fields(self):
        conn = RepoConnection.create(
            org_id="org_1",
            provider=RepoProvider.GITLAB,
            install_token_ref="vault:gitlab_bot_1",
        )
        dumped = conn.model_dump()
        for field in ("id", "org_id", "provider", "install_token_ref", "connected_at"):
            assert field in dumped
        assert "token" not in dumped
        assert not any("token=" in str(v) for v in dumped.values() if isinstance(v, str))
