#!/usr/bin/env bash
set -e
GAME_DIR="$HOME/Desktop/kart"
if [ ! -f "$GAME_DIR/kart_simulator.py" ]; then
  printf 'Game file missing: %s\n' "$GAME_DIR/kart_simulator.py"
  exit 1
fi
mkdir -p "$HOME/.local/share/applications"
cat > "$GAME_DIR/start_kart.sh" <<'LAUNCH'
#!/usr/bin/env bash
cd "$HOME/Desktop/kart" || exit 1
# Inherit the desktop session display rather than assuming a display number.
exec /usr/bin/python3 kart_simulator.py
LAUNCH
chmod +x "$GAME_DIR/start_kart.sh"
ICON="$GAME_DIR/kart-icon.svg"
cat > "$ICON" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">
<rect width="256" height="256" rx="52" fill="#14243d"/>
<path d="M64 256 105 0h46l41 256" fill="#465369"/>
<path d="M128 0v35m0 20v35" stroke="#fff1a8" stroke-width="6"/>
<rect x="48" y="147" width="33" height="62" rx="9" fill="#0a101b"/>
<rect x="175" y="147" width="33" height="62" rx="9" fill="#0a101b"/>
<path d="M87 129h82l20 75H67z" fill="#ef3c4e"/>
<ellipse cx="128" cy="127" rx="30" ry="35" fill="#2868cc"/>
<ellipse cx="128" cy="87" rx="30" ry="26" fill="#84492e"/>
<path d="M93 83c0-49 70-49 70 0v10H93z" fill="#ff4050"/>
<rect x="86" y="199" width="84" height="13" rx="6" fill="#e4edf5"/>
<rect x="111" y="173" width="34" height="28" rx="4" fill="#a0adbd"/>
<path d="M115 180h26m-26 7h26m-26 7h26" stroke="#3f4d62" stroke-width="3"/>
<circle cx="211" cy="49" r="22" fill="#ffd24a"/><text x="211" y="59" font-size="29" text-anchor="middle" fill="#9c6500" font-family="sans-serif" font-weight="bold">$</text>
</svg>
SVG
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || printf '%s/Desktop' "$HOME")"
mkdir -p "$DESKTOP_DIR"
ENTRY="$HOME/.local/share/applications/joystick-kart.desktop"
cat > "$ENTRY" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Joystick Kart
Name[ko]=카트 시뮬레이터
Comment=20-second joystick kart racing game
Exec="$GAME_DIR/start_kart.sh"
Path=$GAME_DIR
Icon=$ICON
Terminal=false
Categories=Game;
StartupNotify=false
EOF
chmod +x "$ENTRY"
cp "$ENTRY" "$DESKTOP_DIR/Joystick-Kart.desktop"
chmod +x "$DESKTOP_DIR/Joystick-Kart.desktop"
if command -v gio >/dev/null 2>&1; then
  gio set "$DESKTOP_DIR/Joystick-Kart.desktop" metadata::trusted true 2>/dev/null || true
fi
printf '\nInstalled: %s/Joystick-Kart.desktop\n' "$DESKTOP_DIR"
printf 'Click Joystick Kart on the Raspberry Pi desktop.\n'
