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
    activation_source: str = "default"
    updated_at: str = ""
    stored_rule_hash: str = field(default="", repr=False)

    def __post_init__(self):
        self.mode = self._parse_mode(self.mode)
        self.policy_version = str(self.policy_version or MINIMAL_POLICY_VERSION)
        self.observations = self._unique(self.observations)
        self.activation_source = str(self.activation_source or "default")
        self.updated_at = str(self.updated_at or "")
        self.stored_rule_hash = str(self.stored_rule_hash or "")

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
            activation_source=data.get("activation_source", "default"),
            updated_at=data.get("updated_at", ""),
            stored_rule_hash=data.get("rule_hash", ""),
        )

    @classmethod
    def normalize_session_state(cls, data=None, created_at=""):
        raw = dict(data or {}) if isinstance(data, dict) else {}
        policy = cls.from_dict(raw)
        if not str(raw.get("activation_source", "")).strip():
            policy.activation_source = "legacy-session" if raw else "default"
        if not str(raw.get("updated_at", "")).strip():
            policy.updated_at = str(created_at or "")
        return policy.to_dict()

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

    def set_mode(
        self,
        mode,
        *,
        activation_source=None,
        updated_at=None,
        policy_version=None,
    ):
        parsed = self._parse_mode(mode)
        self.mode = parsed
        if policy_version is not None:
            self.policy_version = str(policy_version or MINIMAL_POLICY_VERSION)
            self.stored_rule_hash = ""
        if activation_source is not None:
            self.activation_source = str(activation_source or "default")
        if updated_at is not None:
            self.updated_at = str(updated_at or "")
        return self

    def observe(self, opportunities):
        if self.mode is PolicyMode.OBSERVE:
            self.observations = self._unique((*self.observations, *(opportunities or ())))
        return tuple(self.observations)

    def prompt_text(self):
        return _RULE_TEXT if self.effective_mode is PolicyMode.ENFORCE else ""

    def compatibility_prompt_text(self):
        if self.is_compatible:
            return ""
        return (
            "Minimal policy compatibility notice: saved policy version "
            f"{self.policy_version} is unsupported; policy rules are disabled for this runtime."
        )

    @property
    def is_compatible(self):
        return self.policy_version == MINIMAL_POLICY_VERSION

    @property
    def effective_mode(self):
        return self.mode if self.is_compatible else PolicyMode.OFF

    @property
    def compatibility_status(self):
        return "compatible" if self.is_compatible else "unsupported-version"

    @property
    def compatibility_notice(self):
        return self.compatibility_prompt_text()

    @property
    def rule_hash(self):
        if not self.is_compatible:
            return self.stored_rule_hash
        payload = f"{self.policy_version}\n{_RULE_TEXT}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def prefix_hash(self):
        payload = (
            f"{self.mode.value}\n{self.effective_mode.value}\n{self.policy_version}\n"
            f"{self.compatibility_status}\n{self.rule_hash}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def prompt_metadata(self):
        return {
            "mode": self.mode.value,
            "effective_mode": self.effective_mode.value,
            "policy_version": self.policy_version,
            "activation_source": self.activation_source,
            "updated_at": self.updated_at,
            "rule_chars": len(self.prompt_text()),
            "rule_hash": self.rule_hash,
            "prompt_rules_injected": self.effective_mode is PolicyMode.ENFORCE,
            "prefix_policy_hash": self.prefix_hash(),
            "compatibility_status": self.compatibility_status,
            "compatibility_notice": self.compatibility_notice,
            "compatibility_notice_injected": not self.is_compatible,
        }

    def checkpoint_metadata(self):
        return {
            "mode": self.mode.value,
            "effective_mode": self.effective_mode.value,
            "policy_version": self.policy_version,
            "rule_hash": self.rule_hash,
            "compatibility_status": self.compatibility_status,
        }

    def resume_metadata(self, checkpoint=None):
        current = {
            key: value
            for key, value in self.prompt_metadata().items()
            if key in {"mode", "effective_mode", "policy_version", "rule_hash"}
        }
        current.update(
            {
                "activation_source": self.activation_source,
                "updated_at": self.updated_at,
                "compatibility_status": self.compatibility_status,
                "compatibility_notice": self.compatibility_notice,
            }
        )
        saved = dict((checkpoint or {}).get("minimal_policy", {}) or {})
        current["checkpoint_match"] = (
            all(saved.get(key) == current.get(key) for key in ("mode", "effective_mode", "policy_version", "rule_hash"))
            if saved
            else None
        )
        current["checkpoint_policy"] = saved
        return current

    def to_dict(self):
        return {
            "mode": self.mode.value,
            "policy_version": self.policy_version,
            "activation_source": self.activation_source,
            "updated_at": self.updated_at,
            "observations": list(self.observations),
            "rule_hash": self.rule_hash,
        }
