import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, cast

import httpx

logger = logging.getLogger("loom.integrations.github_client")


class GitHubAPIError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None, error_code: str = "GITHUB_API_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code


class GitHubAuthError(GitHubAPIError):
    def __init__(self, message: str = "GitHub authentication failed"):
        super().__init__(message, status_code=401, error_code="AUTH_FAILED")


class GitHubBranchExistsError(GitHubAPIError):
    def __init__(self, message: str = "Branch already exists"):
        super().__init__(message, status_code=409, error_code="BRANCH_EXISTS")


class GitHubPROpenError(GitHubAPIError):
    def __init__(self, message: str = "Pull request already exists for this branch"):
        super().__init__(message, status_code=409, error_code="PR_ALREADY_EXISTS")


class GitHubPushError(GitHubAPIError):
    def __init__(self, message: str = "Git push rejected"):
        super().__init__(message, status_code=500, error_code="PUSH_REJECTED")


def resolve_vault_token(token_ref: str) -> str:
    """Resolve a vault-prefixed secret reference to an actual secret token.

    Tokens are looked up from environment variables in order:
    1. LOOM_VAULT_<REF_NAME_UPPER>
    2. GITHUB_TOKEN / GH_TOKEN if generic ref
    3. Direct token value if non-vault ref provided in test mode
    """
    if not token_ref:
        return os.getenv("GITHUB_TOKEN", os.getenv("GH_TOKEN", ""))

    if token_ref.startswith("vault:"):
        key_name = token_ref[len("vault:") :]
        env_var_name = f"LOOM_VAULT_{key_name.upper().replace('-', '_').replace('.', '_')}"
        val = os.getenv(env_var_name)
        if val:
            return val
        # Fallback to standard github token env
        return os.getenv("GITHUB_TOKEN", os.getenv("GH_TOKEN", ""))

    return token_ref


class GitHubAPIClient:
    """Outbound async client for GitHub REST API interactions, modelled on SlackNotifier."""

    def __init__(
        self,
        token: Optional[str] = None,
        token_ref: Optional[str] = None,
        base_url: str = "https://api.github.com",
        http_client: Optional[httpx.AsyncClient] = None,
        timeout: float = 15.0,
    ):
        self.base_url = base_url.rstrip("/")
        self._token = token or resolve_vault_token(token_ref or "")
        self._http = http_client
        self._timeout = timeout

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                headers={
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "User-Agent": "Loom-Agentic-Harness",
                },
            )
        return self._http

    async def close(self) -> None:
        if self._http:
            await self._http.aclose()
            self._http = None

    def _auth_headers(self) -> Dict[str, str]:
        if not self._token:
            raise GitHubAuthError("Missing GitHub authentication token")
        return {"Authorization": f"Bearer {self._token}"}

    async def get_default_branch_sha(self, repo: str, branch: str = "main") -> str:
        """Get the latest commit SHA of the base branch."""
        client = await self._ensure_client()
        url = f"{self.base_url}/repos/{repo}/git/ref/heads/{branch}"
        try:
            resp = await client.get(url, headers=self._auth_headers())
        except httpx.RequestError as exc:
            raise GitHubAPIError(f"Network error connecting to GitHub: {exc}", error_code="NETWORK_ERROR") from exc

        if resp.status_code == 401 or resp.status_code == 403:
            raise GitHubAuthError(f"GitHub authentication failed: {resp.text}")
        if resp.status_code == 404:
            raise GitHubAPIError(f"Base branch '{branch}' or repository '{repo}' not found", status_code=404)
        if resp.status_code != 200:
            raise GitHubAPIError(f"Failed to fetch branch reference: {resp.text}", status_code=resp.status_code)

        data = cast(Dict[str, Any], resp.json())
        object_data = data.get("object")
        if not isinstance(object_data, dict):
            raise GitHubAPIError("GitHub returned an invalid branch reference payload", status_code=resp.status_code)
        sha = object_data.get("sha")
        if not isinstance(sha, str):
            raise GitHubAPIError("GitHub returned an invalid branch SHA", status_code=resp.status_code)
        return sha

    async def create_branch(self, repo: str, branch: str, base_branch: str = "main") -> Dict[str, Any]:
        """Create a new branch reference from base_branch."""
        sha = await self.get_default_branch_sha(repo, base_branch)
        client = await self._ensure_client()
        url = f"{self.base_url}/repos/{repo}/git/refs"
        payload = {"ref": f"refs/heads/{branch}", "sha": sha}

        try:
            resp = await client.post(url, json=payload, headers=self._auth_headers())
        except httpx.RequestError as exc:
            raise GitHubAPIError(f"Network error creating branch: {exc}", error_code="NETWORK_ERROR") from exc

        if resp.status_code == 422:
            raise GitHubBranchExistsError(f"Branch '{branch}' already exists in '{repo}'")
        if resp.status_code == 401 or resp.status_code == 403:
            raise GitHubAuthError(f"Authentication failed creating branch: {resp.text}")
        if resp.status_code not in (200, 201):
            raise GitHubAPIError(f"Failed to create branch: {resp.text}", status_code=resp.status_code)

        return cast(Dict[str, Any], resp.json())

    async def create_pull_request(
        self,
        repo: str,
        title: str,
        body: str,
        head: str,
        base: str = "main",
        draft: bool = False,
        labels: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Open a pull request on GitHub."""
        client = await self._ensure_client()
        url = f"{self.base_url}/repos/{repo}/pulls"
        payload = {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
            "draft": draft,
        }

        try:
            resp = await client.post(url, json=payload, headers=self._auth_headers())
        except httpx.RequestError as exc:
            raise GitHubAPIError(f"Network error creating PR: {exc}", error_code="NETWORK_ERROR") from exc

        if resp.status_code == 422:
            err_text = resp.text.lower()
            if "already exists" in err_text or "a pull request already exists" in err_text:
                raise GitHubPROpenError(f"A pull request already exists for branch '{head}'")
            raise GitHubAPIError(f"Validation failed creating PR: {resp.text}", status_code=422)
        if resp.status_code in (401, 403):
            raise GitHubAuthError(f"Authentication failed creating PR: {resp.text}")
        if resp.status_code not in (200, 201):
            raise GitHubAPIError(f"Failed to create PR: {resp.text}", status_code=resp.status_code)

        pr_data = cast(Dict[str, Any], resp.json())
        pr_number = pr_data.get("number")

        # Add labels if provided and PR creation succeeded
        if labels and pr_number:
            try:
                label_url = f"{self.base_url}/repos/{repo}/issues/{pr_number}/labels"
                await client.post(label_url, json={"labels": labels}, headers=self._auth_headers())
            except Exception as label_err:
                logger.warning(f"Failed to apply labels to PR #{pr_number}: {label_err}")

        return pr_data

    def commit_and_push_patch(
        self,
        repo_path: str,
        branch_name: str,
        commit_message: str,
        remote_name: str = "origin",
    ) -> Dict[str, Any]:
        """Commit the local patch to a new branch and push to remote."""
        try:
            # Create and switch to new branch
            subprocess.run(
                ["git", "checkout", "-b", branch_name],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            # Stage changes
            subprocess.run(
                ["git", "add", "-A"],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            # Commit
            subprocess.run(
                ["git", "commit", "-m", commit_message],
                cwd=repo_path,
                check=True,
                capture_output=True,
                text=True,
            )
            # Push
            push_res = subprocess.run(
                ["git", "push", "-u", remote_name, branch_name],
                cwd=repo_path,
                capture_output=True,
                text=True,
            )
            if push_res.returncode != 0:
                raise GitHubPushError(f"Push failed: {push_res.stderr}")

            return {"branch": branch_name, "status": "pushed"}
        except subprocess.CalledProcessError as exc:
            raise GitHubPushError(f"Git operation failed: {exc.stderr or exc.stdout or str(exc)}") from exc
