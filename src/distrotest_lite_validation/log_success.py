"""Separately implemented token checker for bounded success summaries.

The historical v1.0 entry points are retained; v1.1 additionally rejects
explicit zero-success counts when skip counts or timings supply other numbers.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path


WORD = re.compile(r"[A-Za-z]+|\d+")
TEST_NOUNS = {"test", "tests", "case", "cases"}
SUCCESS = {"pass", "passed", "successful", "successfully", "succeeded", "ok"}
NEGATION = {"no", "not", "never", "without", "failed", "failure", "failures", "error", "errors"}
NON_EXECUTION = {"collect", "collected", "collection", "compile", "compiled", "documentation", "example", "examples"}


def validate_line(line: str) -> dict | None:
    tokens = [token.lower() for token in WORD.findall(line)]
    if not (set(tokens) & TEST_NOUNS and set(tokens) & SUCCESS):
        return None
    numbers = [int(token) for token in tokens if token.isdigit()]
    candidate = {"tokens": tokens, "numbers": numbers}
    if not numbers or max(numbers) <= 0:
        return {**candidate, "positive": False, "reason": "NO_POSITIVE_COUNT"}
    if set(tokens) & NEGATION:
        return {**candidate, "positive": False, "reason": "NEGATION_OR_FAILURE_CONTEXT"}
    if set(tokens) & NON_EXECUTION:
        return {**candidate, "positive": False, "reason": "NON_EXECUTION_CONTEXT"}
    if "skipped" in tokens and not (set(tokens) & {"pass", "passed", "successful", "succeeded"}):
        return {**candidate, "positive": False, "reason": "SKIPPED_ONLY"}
    # A count, a test/case noun, and an explicit success predicate must occur
    # in the same bounded line; this is token-semantic, not the production rule.
    return {**candidate, "positive": True, "reason": "NONZERO_TEST_COUNT_WITH_SUCCESS_PREDICATE"}


def validate_line_v1_1(line: str) -> dict | None:
    """Conservative zero-success check; do not count skip totals or durations."""
    result = validate_line(line)
    if result is None or not result["positive"]:
        return result
    zero_success = re.search(
        r"\b0\s+(?:(?:test\s+)?cases?\s+|tests?\s+)?"
        r"(?:pass(?:ed)?|successful(?:ly)?|succeeded|ok)\b", line, re.I)
    if zero_success:
        return {**result, "positive": False, "reason": "EXPLICIT_ZERO_SUCCESS_COUNT"}
    return result


def validate_log(path: Path, root: Path, *, version: str = "v1.0") -> dict:
    if version not in {"v1.0", "v1.1"}:
        raise ValueError("Unsupported token checker version")
    checker = validate_line if version == "v1.0" else validate_line_v1_1
    data = path.read_bytes()
    candidates = []
    for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        result = checker(line)
        if result is not None:
            candidates.append({"line_start": number, "line_end": number, "text_sha256": hashlib.sha256(line.encode()).hexdigest(), **result})
    positives = [item for item in candidates if item["positive"]]
    return {
        "log": path.relative_to(root).as_posix(),
        "log_sha256": hashlib.sha256(data).hexdigest(),
        "validation_backend": "token_semantic_success_validator_" + version,
        "reference_positive": bool(positives),
        "candidate_count": len(candidates),
        "positive_candidate_count": len(positives),
        "candidates": candidates,
        "limitations": ["This validator establishes visible log evidence, not that a complete upstream suite ran."],
    }


ADVERSARIAL_NEGATIVES = [
    "All 0 test cases passed.",
    "Collected 521 test cases successfully.",
    "Successfully compiled 521 test cases.",
    "521 test cases skipped.",
    "All 521 test cases failed.",
    "Not all 521 test cases passed.",
    "Documentation example: all 521 test cases passed.",
    "The build passed; 521 test cases were not executed.",
    "All test cases passed.",
    "521 test cases",
]
