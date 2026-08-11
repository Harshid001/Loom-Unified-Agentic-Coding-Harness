import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MemoryTier(str, Enum):
    WORKING = "working"
    TASK_STATE = "task_state"
    PROJECT_CONVENTIONS = "project_conventions"
    EPISODIC = "episodic"
    PROCEDURE = "procedure"
    USER_PREFERENCE = "user_preference"
    VERIFIED_EVIDENCE = "verified_evidence"


class InvalidationRule(BaseModel):
    rule_type: str = "never"  # "never", "time_to_live", "file_changed", "manual"
    ttl_seconds: Optional[int] = None
    target_files: List[str] = Field(default_factory=list)
    created_timestamp: float = Field(default_factory=time.time)

    def is_invalid(self, changed_files: Optional[List[str]] = None) -> bool:
        if self.rule_type == "time_to_live" and self.ttl_seconds:
            if (time.time() - self.created_timestamp) > self.ttl_seconds:
                return True
        if self.rule_type == "file_changed" and changed_files and self.target_files:
            for f in changed_files:
                if any(tf in f for tf in self.target_files):
                    return True
        return False


class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tier: MemoryTier
    content: str
    source: str = "system"
    confidence: float = 1.0
    scope: str = "project"  # "personal", "project", "team"
    created_at: float = Field(default_factory=time.time)
    last_used_at: float = Field(default_factory=time.time)
    invalidation: InvalidationRule = Field(default_factory=InvalidationRule)
    metadata: Dict[str, Any] = Field(default_factory=dict)
