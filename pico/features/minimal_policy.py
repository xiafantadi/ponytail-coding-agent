"""Pure domain model for minimal-change policy decisions."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum


MINIMAL_POLICY_VERSION = "minimal-policy-v1"


class PolicyMode(str, Enum):
    OFF = "off"
    OBSERVE = "observe"
    ENFORCE = "enforce"


DECISION_LADDER = (
    "do not implement",
    "reuse repository code",
    "standard library",
    "platform-native capability",
    "existing dependency",
    "minimal custom code",
)

SAFETY_RETENTION_ITEMS = (
    "input validation",
    "data-security error handling",
    "security controls",
    "permission controls",
    "accessibility",
    "explicit requirements",
    "non-trivial logic tests",
)

_RULE_TEXT = "\n".join(
    (
        "Minimal change policy:",
        "- Prefer, in order: do not implement; reuse repository code; standard library; "
        "platform-native capability; existing dependency; minimal custom code.",
        "- Preserve input validation, data-security error handling, security controls, "
        "permission controls, accessibility, explicit requirements, and non-trivial logic tests.",
        "- Do not remove safety behavior or required tests to reduce token or line count.",
    )
)


@dataclass
class MinimalChangePolicy:
    mode: PolicyMode = PolicyMode.OFF
    policy_version: str = MINIMAL_POLICY_VERSION
    observations: list[str] = field(default_factory=list)

    def __post_init__(self):
        self.mode = self._parse_mode(self.mode)
        self.policy_version = str(self.policy_version or MINIMAL_POLICY_VERSION)
        self.observations = self._unique(self.observations)

    @classmethod
    def from_mode(cls, mode):
        return cls(mode=cls._parse_mode(mode))

    @classmethod
    def from_dict(cls, data):
        data = dict(data or {})
        return cls(
            mode=data.get("mode", PolicyMode.OFF.value),
            policy_version=data.get("policy_version", MINIMAL_POLICY_VERSION),
            observations=data.get("observations", []),
        )

    @staticmethod
    def _parse_mode(mode):
        if isinstance(mode, PolicyMode):
            return mode
        try:
            return PolicyMode(str(mode).strip().lower())
        except ValueError as exc:
            raise ValueError("mode must be one of: off, observe, enforce") from exc

    @staticmethod
    def _unique(values):
        result = []
        for value in values or ():
            value = str(value).strip()
            if value and value not in result:
                result.append(value)
        return result

    def set_mode(self, mode):
        parsed = self._parse_mode(mode)
        self.mode = parsed
        return self

    def observe(self, opportunities):
        if self.mode is PolicyMode.OBSERVE:
            self.observations = self._unique((*self.observations, *(opportunities or ())))
        return tuple(self.observations)

    def prompt_text(self):
        return _RULE_TEXT if self.mode is PolicyMode.ENFORCE else ""

    @property
    def rule_hash(self):
        payload = f"{self.policy_version}\n{_RULE_TEXT}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def prefix_hash(self):
        payload = f"{self.mode.value}\n{self.policy_version}\n{self.rule_hash}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def prompt_metadata(self):
        return {
            "mode": self.mode.value,
            "policy_version": self.policy_version,
            "rule_chars": len(self.prompt_text()),
            "rule_hash": self.rule_hash,
            "prompt_rules_injected": self.mode is PolicyMode.ENFORCE,
            "prefix_policy_hash": self.prefix_hash(),
        }

    def to_dict(self):
        return {
            "mode": self.mode.value,
            "policy_version": self.policy_version,
            "observations": list(self.observations),
            "rule_hash": self.rule_hash,
        }
