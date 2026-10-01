#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
# Installs the filter, backend and PPD into a CUPS tree. Tested against CUPS 2.4.7 (see host/tests/cups_integration.py); needs root.
# The installed files are small wrappers that import the openinkjet package from THIS directory, so keep it in place (and readable by
# the 'lp' user for the filter; the backend runs as root).
# Usage: sudo ./install_cups.sh [/usr/lib/cups] [/usr/share/cups/model]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
lib="${1:-/usr/lib/cups}"; model="${2:-/usr/share/cups/model}"
py="$(command -v python3)"
wrap() {   # wrap <name> <entry function> <mode> <dest dir>
  cat > "$4/$1" <<EOF
#!$py
import sys
sys.path.insert(0, "$here")
from openinkjet.cups import $2
sys.exit($2())
EOF
  chmod "$3" "$4/$1"
}
mkdir -p "$lib/filter" "$lib/backend" "$model"
wrap oi_filter filter_main 0755 "$lib/filter"
wrap openinkjet backend_main 0700 "$lib/backend"     # mode 0700: CUPS runs such backends as root
install -m 0644 "$here/cups/openinkjet.ppd" "$model/openinkjet.ppd"
echo "installed oi_filter, openinkjet backend and PPD under $lib and $model (package dir: $here)"
