#!/bin/bash
# Rebuilds icon.png, AppIcon.icns and the web favicon from make_icon.swift.
set -euo pipefail
cd "$(dirname "$0")"
swift make_icon.swift
rm -rf AppIcon.iconset && mkdir AppIcon.iconset
for s in 16 32 128 256 512; do
  sips -z $s $s icon.png --out AppIcon.iconset/icon_${s}x${s}.png >/dev/null
  sips -z $((s*2)) $((s*2)) icon.png --out AppIcon.iconset/icon_${s}x${s}@2x.png >/dev/null
done
iconutil -c icns AppIcon.iconset -o AppIcon.icns && rm -rf AppIcon.iconset
sips -z 256 256 icon.png --out ../src/moodscroll/static/icon.png >/dev/null
