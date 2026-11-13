#!/bin/bash
# Builds AcreageFinder.apk. Needs the Android SDK (build-tools 36.1.0, platform 36) in $SDK and a signing key:
#   ACREAGE_KEYSTORE=/path/acreage.jks ACREAGE_KSPASS=... bash build.sh
# The key and its password are never stored in this repo. Updates must be signed with the same key.
set -e
cd "$(dirname "$0")"
SDK=${SDK:-/tmp/claude-0/sdk}; BT=$SDK/build-tools/36.1.0; AJ=$SDK/platforms/android-36/android.jar
: "${ACREAGE_KEYSTORE:?set ACREAGE_KEYSTORE}"; : "${ACREAGE_KSPASS:?set ACREAGE_KSPASS}"
rm -rf out assets; mkdir -p out/classes out/gen assets
cp ../acreage.html assets/index.html; cp ../acreage-data.js ../history-data.js assets/
$BT/aapt2 compile --dir res -o out/res.zip
$BT/aapt2 link -I $AJ --manifest AndroidManifest.xml -o out/base.apk -A assets --java out/gen out/res.zip
javac -source 8 -target 8 -nowarn -Xlint:-options -bootclasspath $AJ -cp $AJ -d out/classes $(find src out/gen -name '*.java') 2>&1 | grep -v "JAVA_TOOL\|warning\|Note:" || true
$BT/d8 --release --min-api 24 --lib $AJ --output out $(find out/classes -name '*.class')
cp out/base.apk out/unsigned.apk; (cd out && zip -q unsigned.apk classes.dex)
$BT/zipalign -f -p 4 out/unsigned.apk out/aligned.apk
$BT/apksigner sign --ks "$ACREAGE_KEYSTORE" --ks-key-alias acreage --ks-pass env:ACREAGE_KSPASS --key-pass env:ACREAGE_KSPASS --out out/AcreageFinder.apk out/aligned.apk
$BT/apksigner verify out/AcreageFinder.apk && echo "APK signed OK"
ls -la out/AcreageFinder.apk
