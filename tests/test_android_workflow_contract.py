from pathlib import Path
import re


def test_emulator_is_manually_managed_without_runner_post_boot_hooks():
    workflow = Path(".github/workflows/android-apk.yml").read_text(encoding="utf-8")
    assert "reactivecircus/android-emulator-runner" not in workflow
    assert "emulator -avd leadora_api30" in workflow
    assert "adb wait-for-device" in workflow
    assert 'getprop sys.boot_completed' in workflow
    assert "settings put system screen_off_timeout" not in workflow


def test_emulator_evidence_reports_the_configured_api_level():
    workflow = Path(".github/workflows/android-apk.yml").read_text(encoding="utf-8")
    api_level = re.search(r'(?m)^\s*ANDROID_API_LEVEL:\s*"(\d+)"\s*$', workflow)
    evidence = re.search(r"api_level=%s", workflow)
    assert api_level, "Android emulator API level must be explicit."
    assert evidence, "Successful emulator evidence must record its API level."


def test_commercial_android_release_is_restricted_to_main_branch():
    workflow = Path(".github/workflows/android-release.yml").read_text(encoding="utf-8")
    assert re.search(
        r"(?m)^  release:\n    if: github\.ref == 'refs/heads/main'$",
        workflow,
    ), "Signed commercial releases must only run from the reviewed main branch."
