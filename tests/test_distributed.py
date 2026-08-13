import json

import pytest

from loom.infra.distributed import RedisCoordinator, RedisRateLimiter, RunMetadata


class FakePipeline:
    def __init__(self, client):
        self.client = client
        self.ops = []

    def zremrangebyscore(self, *args):
        self.ops.append(("zremrangebyscore", args))
        return self

    def zcard(self, *args):
        self.ops.append(("zcard", args))
        return self

    def zadd(self, *args):
        self.ops.append(("zadd", args))
        return self

    def expire(self, *args):
        self.ops.append(("expire", args))
        return self

    async def execute(self):
        return (0, 0, 1, 1)


class FakeRedis:
    def pipeline(self):
        return FakePipeline(self)

    async def ping(self):
        return True


@pytest.mark.asyncio
async def test_rate_limiter_allows_when_redis_is_below_limit(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://test")
    limiter = RedisRateLimiter(RedisCoordinator("redis://test"))
    limiter.coordinator._client = FakeRedis()
    assert await limiter.allow("127.0.0.1") is True


def test_run_metadata_is_structured():
    metadata = RunMetadata(
        run_id="run_1",
        org_id="org_1",
        repo_path="/workspace/repo",
        status="queued",
        sandbox_tier="B",
        created_at=1.0,
    )
    assert metadata.run_id == "run_1"
    assert metadata.sandbox_tier == "B"


def test_control_payload_is_json_serializable():
    payload = {"action": "pause", "payload": {"snapshot_id": None}}
    assert json.loads(json.dumps(payload))["action"] == "pause"
