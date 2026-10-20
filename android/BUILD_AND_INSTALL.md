# LEADORA Android build

## Build

The GitHub Actions workflow at `.github/workflows/android-apk.yml` builds the debug APK with Java 17, Gradle 8.9, and the Android SDK.

## Output

- APK: `app/build/outputs/apk/debug/app-debug.apk`
- Published artifact: `LEADORA-Android-APK`
- Release assets: `LEADORA-Android.apk` and `LEADORA-Android.apk.sha256`

## Current implementation limits

This first Android package is a WebView client for `https://leadora-web-production.up.railway.app/`. It requires internet access and shares business data with the web application. It is not an offline-first native application. The CI artifact is debug-signed for testing; a production release requires a protected signing key and GitHub Actions secrets.
