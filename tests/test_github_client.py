from unittest.mock import AsyncMock

import httpx
import pytest

from loom.integrations.ci_bot import CIBotConfig, CIBotProvider, GitHubCIBot
from loom.integrations.github_client import (
    GitHubAPIClient,
    GitHubAuthError,
    GitHubBranchExistsError,
    GitHubPROpenError,
    resolve_vault_token,
)


def test_resolve_vault_token(monkeypatch):
    monkeypatch.setenv("LOOM_VAULT_GITHUB_INSTALL_1", "ghp_vaultsecret123")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_generic123")

    # Vault prefix resolved to matching env
    assert resolve_vault_token("vault:github_install_1") == "ghp_vaultsecret123"
    # Unmatched vault ref falls back to GITHUB_TOKEN
    assert resolve_vault_token("vault:nonexistent") == "ghp_generic123"
    # Direct token
    assert resolve_vault_token("raw_token_xyz") == "raw_token_xyz"


@pytest.mark.asyncio
async def test_github_client_create_branch_and_pr():
    # Mock httpx responses
    client = GitHubAPIClient(token="ghp_test_token")

    async def mock_handler(request: httpx.Request):
        url = str(request.url)
        if url.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "abc123def456"}})
        elif url.endswith("/git/refs"):
            return httpx.Response(201, json={"ref": "refs/heads/loom/fix/1-test", "object": {"sha": "abc123def456"}})
        elif url.endswith("/pulls"):
            return httpx.Response(
                201,
                json={
                    "number": 42,
                    "html_url": "https://github.com/acme/repo/pull/42",
                    "state": "open",
                    "title": "[Loom] Fix: Test Issue",
                },
            )
        elif url.endswith("/labels"):
            return httpx.Response(200, json=[{"name": "loom:automated"}])
        return httpx.Response(404, json={"message": "Not Found"})

    transport = httpx.MockTransport(mock_handler)
    client._http = httpx.AsyncClient(transport=transport)

    branch_res = await client.create_branch("acme/repo", "loom/fix/1-test", "main")
    assert branch_res["ref"] == "refs/heads/loom/fix/1-test"

    pr_res = await client.create_pull_request(
        repo="acme/repo",
        title="[Loom] Fix: Test Issue",
        body="PR body",
        head="loom/fix/1-test",
        base="main",
        labels=["loom:automated"],
    )
    assert pr_res["number"] == 42
    assert pr_res["html_url"] == "https://github.com/acme/repo/pull/42"


@pytest.mark.asyncio
async def test_github_client_auth_error():
    client = GitHubAPIClient(token="invalid_token")

    async def mock_handler(request: httpx.Request):
        return httpx.Response(401, json={"message": "Bad credentials"})

    transport = httpx.MockTransport(mock_handler)
    client._http = httpx.AsyncClient(transport=transport)

    with pytest.raises(GitHubAuthError):
        await client.get_default_branch_sha("acme/repo", "main")


@pytest.mark.asyncio
async def test_github_client_branch_exists():
    client = GitHubAPIClient(token="ghp_test")

    async def mock_handler(request: httpx.Request):
        url = str(request.url)
        if url.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "abc123"}})
        return httpx.Response(422, json={"message": "Reference already exists"})

    transport = httpx.MockTransport(mock_handler)
    client._http = httpx.AsyncClient(transport=transport)

    with pytest.raises(GitHubBranchExistsError):
        await client.create_branch("acme/repo", "loom/fix/existing", "main")


@pytest.mark.asyncio
async def test_github_client_pr_already_exists():
    client = GitHubAPIClient(token="ghp_test")

    async def mock_handler(request: httpx.Request):
        return httpx.Response(422, json={"message": "A pull request already exists for acme:branch."})

    transport = httpx.MockTransport(mock_handler)
    client._http = httpx.AsyncClient(transport=transport)

    with pytest.raises(GitHubPROpenError):
        await client.create_pull_request("acme/repo", "title", "body", "branch", "main")


@pytest.mark.asyncio
async def test_preview_pr_vs_create_pr():
    mock_api = AsyncMock()
    mock_api.create_pull_request.return_value = {
        "number": 101,
        "html_url": "https://github.com/org/repo/pull/101",
    }

    bot = GitHubCIBot(
        config=CIBotConfig(
            provider=CIBotProvider.GITHUB,
            org_id="org_1",
            repo_full_name="org/repo",
            api_base_url="https://api.github.com",
            install_token_ref="vault:key",
        ),
        api_client=mock_api,
    )

    # 1. Preview PR generates template only (no create_pull_request API call)
    preview = bot.preview_pr(
        run_id="run_preview_1",
        issue_title="Bug in calculation",
        issue_number=5,
        patch_diff="+ x = 1",
        confidence_score=0.96,
        verification_passed=True,
    )
    assert preview["action"] == "preview"
    assert "body" in preview
    assert "branch" in preview
    assert "pr_url" not in preview
    assert mock_api.create_pull_request.call_count == 0

    # 2. Create PR makes outbound call and returns real PR metadata
    created = await bot.create_pr(
        run_id="run_create_1",
        issue_title="Bug in calculation",
        issue_number=5,
        patch_diff="+ x = 1",
        confidence_score=0.96,
        verification_passed=True,
    )
    assert created["action"] == "created"
    assert created["pr_number"] == 101
    assert created["pr_url"] == "https://github.com/org/repo/pull/101"
    assert mock_api.create_pull_request.call_count == 1
