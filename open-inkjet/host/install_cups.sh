#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
# Installs the filter, backend and PPD into a CUPS tree. Tested against CUPS 2.4.7 (see host/tests/cups_integration.py); needs root.
# The package is COPIED to <cups lib>/openinkjet-py so the unprivileged 'lp' user (which runs the filter) can import it even when this
# source tree lives in a private home directory; numpy and Pillow must be importable by the system python3.
# Usage: sudo ./install_cups.sh [/usr/lib/cups] [/usr/share/cups/model]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
lib="${1:-/usr/lib/cups}"; model="${2:-/usr/share/cups/model}"
py="$(command -v python3)"
wrap() {   # wrap <name> <entry function> <mode> <dest dir>
  cat > "$4/$1" <<EOF
#!$py
import sys
sys.path.insert(0, "$pkg")
from openinkjet.cups import $2
sys.exit($2())
EOF
  chmod "$3" "$4/$1"
}
pkg="$lib/openinkjet-py"
mkdir -p "$lib/filter" "$lib/backend" "$model" "$pkg"
rm -rf "$pkg/openinkjet"; cp -r "$here/openinkjet" "$pkg/openinkjet"; find "$pkg" -name __pycache__ -prune -exec rm -rf {} +; chmod -R a+rX "$pkg"
wrap oi_filter filter_main 0755 "$lib/filter"
wrap openinkjet backend_main 0700 "$lib/backend"     # mode 0700: CUPS runs such backends as root
install -m 0644 "$here/cups/openinkjet.ppd" "$model/openinkjet.ppd"
if command -v runuser >/dev/null && id lp >/dev/null 2>&1; then
  runuser -u lp -- "$py" -c "import sys; sys.path.insert(0, '$pkg'); import openinkjet.cups" \
    || { echo "WARNING: user lp cannot import openinkjet (needs python3-numpy and python3-pil for the system python3)"; exit 1; }
fi
echo "installed oi_filter, openinkjet backend and PPD under $lib and $model (package copied to $pkg)"
