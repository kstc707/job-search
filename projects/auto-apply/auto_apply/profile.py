"""Build and validate the UserProfile JSON that `apply-with-custom-resume` requires.

Tsenta attaches a custom resume PDF verbatim but fills every ATS form field from this
profile, so a wrong or incomplete profile means wrong answers on the application even
when the PDF is perfect.
"""

from __future__ import annotations

import copy
from typing import Any

# (dotted path, human label). Paths into the profile `data` object returned by
# get-resume-profile. A value counts as missing when absent, None, or "".
REQUIRED_FIELDS: list[tuple[str, str]] = [
    ("personalInformation.firstName", "first name"),
    ("personalInformation.lastName", "last name"),
    ("personalInformation.email", "email"),
    ("personalInformation.phone", "phone"),
    ("personalInformation.city", "city"),
    ("personalInformation.state", "state"),
    ("personalInformation.country", "country"),
    ("workAuthorization.isAuthorizedToWork", "work authorization"),
    ("workAuthorization.needsSponsorship", "sponsorship answer"),
]
REQUIRED_LISTS: list[tuple[str, str]] = [
    ("education", "education"),
    ("workExperience", "work experience"),
]


def extract_profile_data(payload: dict[str, Any]) -> dict[str, Any]:
    """Accept a get-resume-profile tool response in any common shape and return `data`.

    Shapes handled: the raw tool output {"tool": ..., "result": {..., "data": {...}}},
    the `result` object, or the `data` object itself.
    """
    node = payload
    if "result" in node and isinstance(node["result"], dict):
        node = node["result"]
    if "data" in node and isinstance(node["data"], dict):
        node = node["data"]
    if "personalInformation" not in node:
        raise ValueError("not a Tsenta resume profile: no personalInformation section")
    return copy.deepcopy(node)


def _get(data: dict[str, Any], dotted: str) -> Any:
    node: Any = data
    for key in dotted.split("."):
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def missing_fields(data: dict[str, Any]) -> list[str]:
    """Labels of required fields that are empty. An empty list means apply-ready."""
    missing = [label for path, label in REQUIRED_FIELDS if _get(data, path) in (None, "")]
    missing += [label for path, label in REQUIRED_LISTS if not _get(data, path)]
    return missing


def build_apply_profile(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the profile to send as `profile`, or raise if a required field is empty."""
    data = extract_profile_data(payload)
    missing = missing_fields(data)
    if missing:
        raise ValueError("profile is missing: " + ", ".join(missing))
    return data


def set_path(data: dict[str, Any], dotted: str, value: Any) -> None:
    """Set an existing profile field by dotted path. Refuses unknown paths so a typo
    cannot silently add a field the ATS form never reads."""
    keys = dotted.split(".")
    node: Any = data
    for key in keys[:-1]:
        if not isinstance(node, dict) or key not in node:
            raise ValueError(f"unknown profile path: {dotted}")
        node = node[key]
    if not isinstance(node, dict) or keys[-1] not in node:
        raise ValueError(f"unknown profile path: {dotted}")
    node[keys[-1]] = value
