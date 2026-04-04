from __future__ import annotations

import json
from pathlib import Path

from app.core.models import PolicyModel, policy_from_dict, to_json


DEFAULT_POLICY_FILE = "default_policy.json"


class PolicyEngine:
    def __init__(self, policy_path: Path) -> None:
        self.policy_path = policy_path

    def load(self) -> PolicyModel:
        if not self.policy_path.exists():
            policy = PolicyModel()
            self.save(policy)
            return policy
        return policy_from_dict(json.loads(self.policy_path.read_text()))

    def save(self, policy: PolicyModel) -> None:
        self.policy_path.parent.mkdir(parents=True, exist_ok=True)
        self.policy_path.write_text(to_json(policy))
