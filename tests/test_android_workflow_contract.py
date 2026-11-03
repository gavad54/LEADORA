from pathlib import Path
import re


def test_emulator_is_manually_managed_without_runner_post_boot_hooks():
    workflow = Path(".github/workflows/android-apk.yml").read_text(encoding="utf-8")
    assert "reactivecircus/android-emulator-runner" not in workflow
    assert '"$EMULATOR" -avd leadora_api30' in workflow
    assert '"emulator" "platforms;android-35"' in workflow
    assert '"$ANDROID_HOME/emulator/emulator"' in workflow
    assert '"publicHome"' in workflow
    assert '"authOverlay"' in workflow
    assert '"workspaceShell"' in workflow
    assert "production-smoke.txt" in workflow
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


def test_commercial_android_release_requires_live_public_home_acceptance():
    workflow = Path(".github/workflows/android-release.yml").read_text(encoding="utf-8")
    assert 'BASE_URL="https://leadora-web-production.up.railway.app"' in workflow
    assert '"$BASE_URL/api/health"' in workflow
    assert '"$BASE_URL/"' in workflow
    assert "Production public-home release gate" in workflow
    for required_check in (
        "public_home_present",
        "public_home_visible",
        "auth_overlay_hidden",
        "workspace_hidden",
        "public_login_action",
        "public_start_action",
        "startup_renders_public_home",
    ):
        assert required_check in workflow, (
            f"Commercial Android release must enforce {required_check}."
        )
    assert "Production public-home release gate failed" in workflow


def test_avd_home_is_set_before_avd_creation_and_emulator_launch():
    workflow = Path(".github/workflows/android-apk.yml").read_text(encoding="utf-8")
    configure_home = workflow.index('export ANDROID_AVD_HOME="$HOME/.android/avd"')
    create_avd = workflow.index('"$AVDMANAGER" create avd')
    launch_emulator = workflow.index('"$EMULATOR" -avd leadora_api30')
    assert configure_home < create_avd < launch_emulator, (
        "ANDROID_AVD_HOME must be configured before avdmanager creates the AVD "
        "and before the emulator tries to load it."
    )
    kvm_permission_check = workflow.index("sudo chmod 666 /dev/kvm")
    assert configure_home < kvm_permission_check < create_avd < launch_emulator, (
        "The ephemeral runner must receive KVM access before creating and launching the x86_64 AVD."
    )


def test_android_smoke_requires_webview_dom_render_diagnostics():
    activity = Path(
        "android/app/src/main/java/com/leadora/app/MainActivity.java"
    ).read_text(encoding="utf-8")
    workflow = Path(".github/workflows/android-apk.yml").read_text(encoding="utf-8")
    assert "LEADORA_WEBVIEW_DOM" in activity
    assert "LEADORA_WEBVIEW_CONSOLE" in activity
    assert "LEADORA_WEBVIEW_ERROR" in activity
    assert "android-webview-dom.txt" in workflow
    assert "visibleTextNodes" in activity
    assert "textLength=[1-9][0-9]*" in workflow
