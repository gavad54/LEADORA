# LEADORA Android build

## Build

The GitHub Actions workflow at `.github/workflows/android-apk.yml` builds the debug APK with Java 17, Gradle 8.9, and the Android SDK.

## Output

- APK: `app/build/outputs/apk/debug/app-debug.apk`
- Published artifact: `LEADORA-Android-APK`
- Release assets: `LEADORA-Android.apk` and `LEADORA-Android.apk.sha256`

## Current implementation limits

This first Android package is a WebView client for `https://leadora-web-production.up.railway.app/`. It requires internet access and shares business data with the web application. It is not an offline-first native application. The CI artifact is debug-signed for testing; a production release requires a protected signing key and GitHub Actions secrets.


## Signed commercial release workflow

The workflow `.github/workflows/android-release.yml` creates a release APK signed with the company's own Android keystore. It intentionally fails before building if signing secrets are missing.

Configure these repository Actions secrets in GitHub (Settings → Secrets and variables → Actions):

- `ANDROID_KEYSTORE_BASE64`: base64-encoded private `.jks` or `.keystore` file.
- `ANDROID_KEYSTORE_PASSWORD`: keystore password.
- `ANDROID_KEY_ALIAS`: exact key alias.
- `ANDROID_KEY_PASSWORD`: private key password.

Generate and retain the signing key securely outside the repository; never commit the keystore or passwords. Keep an offline encrypted backup. Losing the key can prevent publishing upgrades under the same Android application identity. Do not use a random CI-generated key for a commercial app.

After setting the secrets, open Actions → Build signed LEADORA Android release → Run workflow, supply a new release tag and name, and verify the release APK checksum. The current assistant session cannot create or retrieve the owner's private signing key or configure GitHub secrets, so a commercial signature cannot be produced until the repository owner supplies these secrets.

The release workflow proves the APK signature cryptographically in CI, but a real-device install, upgrade, login, tenant isolation and end-to-end business acceptance still require a physical Android device and owner/operator acceptance.
