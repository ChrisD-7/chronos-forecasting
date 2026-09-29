#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
# Installs the filter, backend and PPD into a CUPS tree. UNTESTED on a real CUPS system (none in the build sandbox).
# CUPS runs backends as root; review bin/ before installing. Usage: sudo ./install_cups.sh [/usr/lib/cups] [/usr/share/cups/model]
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
lib="${1:-/usr/lib/cups}"; model="${2:-/usr/share/cups/model}"
install -m 0755 "$here/bin/oi_filter" "$lib/filter/oi_filter"
install -m 0700 "$here/bin/openinkjet" "$lib/backend/openinkjet"      # backends with mode 0700 run as root
install -m 0644 "$here/cups/openinkjet.ppd" "$model/openinkjet.ppd"
echo "installed. NOTE: bin/ scripts import openinkjet from $here; keep that directory in place or copy the package next to them."
