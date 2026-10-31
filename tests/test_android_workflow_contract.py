from pathlib import Path
import re


def test_emulator_runner_skips_flaky_automatic_animation_settings():
    workflow = Path(".github/workflows/android-apk.yml").read_text(encoding="utf-8")
    assert re.search(r"(?m)^\s*disable-animations:\s*false\s*$", workflow), (
        "The emulator action's automatic settings writes have failed with ADB "
        "Broken pipe; keep them disabled and let the smoke script control checks."
    )


def test_emulator_evidence_reports_the_configured_api_level():
    workflow = Path(".github/workflows/android-apk.yml").read_text(encoding="utf-8")
    api_level = re.search(r"(?m)^\s*api-level:\s*(\d+)\s*$", workflow)
    evidence = re.search(r"(?m)^\s*printf 'result=PASS\\npackage=.*?api_level=(\d+)", workflow)
    assert api_level, "Android emulator API level must be explicit."
    assert evidence, "Successful emulator evidence must record its API level."
    assert evidence.group(1) == api_level.group(1), (
        f"Emulator runs API {api_level.group(1)} but evidence claims API {evidence.group(1)}."
    )
