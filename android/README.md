# Shikhbo Android App

A WebView-based Android app that wraps the Shikhbo web app.

## Quick build (Capacitor)

```bash
cd android
npm install
npx cap add android
npx cap sync
npx cap open android   # opens Android Studio
```

Build a release APK in Android Studio → Build → Generate Signed APK.

## Environment

Set `WEB_APP_URL` in `capacitor.config.json` to your deployed web app URL.
