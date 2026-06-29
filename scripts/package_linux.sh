#!/usr/bin/env bash
#
# Build distro packages for the Linux desktop bundle: .deb, .rpm and .flatpak.
# Run AFTER the PyInstaller onedir exists at dist/ArchitectureValidator/ (i.e.
# after scripts/build_desktop.sh or the CI "Build with PyInstaller" step).
#
#   VERSION=1.0.0 ./scripts/package_linux.sh
#
# Outputs (repo root, fixed names so CI can attach them):
#   architecture-validator-desktop-linux.deb
#   architecture-validator-desktop-linux.rpm
#   architecture-validator-desktop-linux.flatpak
#
# Requires: fpm (deb/rpm) and flatpak + flatpak-builder (flatpak). Set
# SKIP_FLATPAK=1 to skip the flatpak on a box without flatpak-builder.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

APP_ID="com.architecture.ArchitectureValidator"
PKG_NAME="architecture-validator"
VERSION="${VERSION:-${1:-0.0.0}}"
ONEDIR="dist/ArchitectureValidator"
ICON_SRC="Media/icon/icon_1024.png"
ICON_SVG="Media/icon/icon.svg"
OUT_DEB="architecture-validator-desktop-linux.deb"
OUT_RPM="architecture-validator-desktop-linux.rpm"
OUT_FLATPAK="architecture-validator-desktop-linux.flatpak"

[ -d "$ONEDIR" ] || { echo "ERROR: $ONEDIR not found — build the app first (scripts/build_desktop.sh)." >&2; exit 1; }

echo "==> Packaging $PKG_NAME $VERSION"

# ---------------------------------------------------------------------------
# Stage the install tree shared by .deb and .rpm:
#   /opt/ArchitectureValidator        the PyInstaller onedir
#   /usr/bin/architecture-validator   thin launcher onto the onedir
#   /usr/share/{applications,icons,metainfo}   desktop integration
# ---------------------------------------------------------------------------
STAGE="$(mktemp -d)"
FP_STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE" "$FP_STAGE"' EXIT

mkdir -p "$STAGE/opt" "$STAGE/usr/bin" \
         "$STAGE/usr/share/applications" \
         "$STAGE/usr/share/icons/hicolor/1024x1024/apps" \
         "$STAGE/usr/share/metainfo"

cp -r "$ONEDIR" "$STAGE/opt/ArchitectureValidator"

cat > "$STAGE/usr/bin/$PKG_NAME" <<'EOF'
#!/bin/sh
# Installed by the .deb/.rpm — runs the PyInstaller onedir under /opt.
exec /opt/ArchitectureValidator/ArchitectureValidator "$@"
EOF
chmod 0755 "$STAGE/usr/bin/$PKG_NAME"

cp "packaging/linux/$APP_ID.desktop"      "$STAGE/usr/share/applications/$APP_ID.desktop"
cp "packaging/linux/$APP_ID.metainfo.xml" "$STAGE/usr/share/metainfo/$APP_ID.metainfo.xml"
cp "$ICON_SRC"                            "$STAGE/usr/share/icons/hicolor/1024x1024/apps/$APP_ID.png"

COMMON_FPM=(
  -s dir
  -n "$PKG_NAME"
  -v "$VERSION"
  --license "MIT"
  --maintainer "Architecture Validator <noreply@architecture.local>"
  --url "https://github.com/alexmasso96/Embeded-Software-Architecture-Validation"
  --description "Embedded Software Architecture Validation desktop app (pywebview + FastAPI + React)."
  --category "Development"
)

# Dependency package names differ between Debian and Fedora families. These
# carry pywebview's GTK3 + WebKit2GTK backend, which PyInstaller cannot bundle.
# VALIDATE on a real install — names drift across releases.
echo "==> 1/3  .deb"
rm -f "$OUT_DEB"
fpm "${COMMON_FPM[@]}" -t deb \
  --depends "gir1.2-webkit2-4.1" \
  --depends "libwebkit2gtk-4.1-0" \
  --deb-no-default-config-files \
  -p "$OUT_DEB" \
  -C "$STAGE" opt usr

echo "==> 2/3  .rpm"
rm -f "$OUT_RPM"
# Stop rpmbuild from auto-generating Requires from the bundled .so's (PyInstaller
# ships its own libs; the auto-scan would emit bogus system deps).
fpm "${COMMON_FPM[@]}" -t rpm \
  --depends "webkit2gtk4.1" \
  --rpm-rpmbuild-define "_build_id_links none" \
  --rpm-rpmbuild-define "__requires_exclude_from ^/opt/ArchitectureValidator/.*$" \
  -p "$OUT_RPM" \
  -C "$STAGE" opt usr

if [ "${SKIP_FLATPAK:-0}" = "1" ]; then
  echo "==> 3/3  .flatpak  (SKIPPED via SKIP_FLATPAK=1)"
else
  echo "==> 3/3  .flatpak"
  rm -f "$OUT_FLATPAK"
  cp -r "$ONEDIR"                           "$FP_STAGE/ArchitectureValidator"
  cp "packaging/linux/$APP_ID.desktop"      "$FP_STAGE/"
  cp "packaging/linux/$APP_ID.metainfo.xml" "$FP_STAGE/"
  cp "$ICON_SRC"                            "$FP_STAGE/icon_1024.png"
  # Scalable icon for AppStream: `appstreamcli compose` (run by flatpak-builder
  # when a metainfo file is present) rejects the 1024px-only raster as
  # "icon-not-found"; a hicolor scalable SVG renders to the sizes it wants.
  cp "$ICON_SVG"                            "$FP_STAGE/icon.svg"
  cp "packaging/flatpak/$APP_ID.yml"        "$FP_STAGE/manifest.yml"

  # --disable-rofiles-fuse: CI runners often lack FUSE. --install-deps-from pulls
  # the org.gnome.Platform/Sdk runtime referenced by the manifest.
  ( cd "$FP_STAGE"
    flatpak-builder --user --force-clean --disable-rofiles-fuse \
      --install-deps-from=flathub --repo=repo build manifest.yml )
  flatpak build-bundle "$FP_STAGE/repo" "$REPO_ROOT/$OUT_FLATPAK" "$APP_ID"
fi

echo
echo "Done. Artifacts:"
ls -1 "$OUT_DEB" "$OUT_RPM" 2>/dev/null || true
[ "${SKIP_FLATPAK:-0}" = "1" ] || ls -1 "$OUT_FLATPAK" 2>/dev/null || true
