#!/usr/bin/env python3
"""Generate docs/setup-diagram.svg: PC <-> router <-> Raspberry Pi 3 + USB webcam.

Edit this script and re-run it instead of editing the SVG by hand:
    python3 docs/make_setup_diagram.py
"""
from pathlib import Path
from xml.sax.saxutils import escape

W, H = 1000, 560
FONT = "DejaVu Sans, Verdana, Arial, Helvetica, sans-serif"
INK = "#1f2328"
MUTED = "#57606a"

out = []


def add(s):
    out.append(s)


def text(x, y, s, size=14, weight="normal", anchor="start", color=INK, style=""):
    add(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" '
        f'text-anchor="{anchor}" fill="{color}" {style}>{escape(s)}</text>')


def box(x, y, w, h, fill, stroke, title, lines, dashed=False, title_size=16):
    dash = ' stroke-dasharray="6 4"' if dashed else ""
    add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{fill}" '
        f'stroke="{stroke}" stroke-width="2"{dash}/>')
    text(x + 14, y + 26, title, size=title_size, weight="bold")
    for i, line in enumerate(lines):
        text(x + 14, y + 52 + i * 22, line, size=13.5)


def line(points, color=INK, width=2.5, dashed=False, arrow=None):
    pts = " ".join(f"{px},{py}" for px, py in points)
    dash = ' stroke-dasharray="7 5"' if dashed else ""
    mk = ""
    if arrow == "end":
        mk = ' marker-end="url(#arrow)"'
    elif arrow == "start":
        mk = ' marker-start="url(#arrow-rev)"'
    add(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"'
        f'{dash}{mk}/>')


add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
    f'viewBox="0 0 {W} {H}" font-family="{FONT}">')
add('<title>Lab setup: PC and Raspberry Pi 3 on wired Ethernet, USB webcam on the Pi</title>')
add('<defs>'
    '<marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" '
    'markerHeight="8" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#0969da"/></marker>'
    '<marker id="arrow-rev" viewBox="0 0 10 10" refX="1" refY="5" markerWidth="8" '
    'markerHeight="8" orient="auto"><path d="M10,0 L0,5 L10,10 z" fill="#1a7f37"/></marker>'
    '</defs>')
# White card so the figure stays readable in GitHub dark mode too.
add(f'<rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14" fill="#ffffff" stroke="#d0d7de"/>')
text(W / 2, 34, "Lab setup: PC, Raspberry Pi 3 and USB webcam", size=19, weight="bold",
     anchor="middle")

# --- main boxes -----------------------------------------------------------------
PC = (30, 60, 300, 250)
PI = (670, 60, 300, 250)
RT = (420, 82, 160, 64)
box(*PC, "#ddf4ff", "#0969da", "PC (Ubuntu, x86-64)", [
    "• CMake + aarch64 cross toolchain",
    "• writes the microSD image (dd + cmp)",
    "• belt_ui.py: Python web server",
    "• browser: http://localhost:8080",
    "• SSH client (key login)",
])
box(*PI, "#dafbe1", "#1a7f37", "Raspberry Pi 3 Model B", [
    "• Yocto image (systemd), on microSD",
    "• Dropbear SSH server",
    "• belt_counter (C, V4L2)",
    "• reads /dev/video0 (uvcvideo)",
    "• gets its IP address by DHCP",
    "• undervolt-watch service",
])
add(f'<rect x="{RT[0]}" y="{RT[1]}" width="{RT[2]}" height="{RT[3]}" rx="10" '
    f'fill="#f6f8fa" stroke="#6e7781" stroke-width="2"/>')
text(RT[0] + RT[2] / 2, RT[1] + 27, "Router / switch", size=15, weight="bold", anchor="middle")
text(RT[0] + RT[2] / 2, RT[1] + 48, "DHCP server", size=13, anchor="middle", color=MUTED)

# --- Ethernet cables ---------------------------------------------------------------
ey = RT[1] + RT[3] / 2
line([(PC[0] + PC[2], ey), (RT[0], ey)], color="#6e7781", width=5)
line([(RT[0] + RT[2], ey), (PI[0], ey)], color="#6e7781", width=5)
text((PC[0] + PC[2] + RT[0]) / 2, ey - 10, "Ethernet", size=13, anchor="middle", color=MUTED)
text((RT[0] + RT[2] + PI[0]) / 2, ey - 10, "Ethernet", size=13, anchor="middle", color=MUTED)
text((RT[0] + RT[2] + PI[0]) / 2, ey + 20, "100 Mbit/s", size=12, anchor="middle", color=MUTED)

# --- SSH data flow (logical, it travels over the cables above) ---------------------
x0, x1 = PC[0] + PC[2], PI[0]
y_to_pi, y_to_pc = 210, 270
line([(x0, y_to_pi), (x1, y_to_pi)], color="#0969da", width=2.5, arrow="end")
text((x0 + x1) / 2, y_to_pi - 26, "over SSH: copy the program,", size=13, anchor="middle",
     color="#0969da")
text((x0 + x1) / 2, y_to_pi - 9, "start it, send commands", size=13, anchor="middle",
     color="#0969da")
line([(x0, y_to_pc), (x1, y_to_pc)], color="#1a7f37", width=2.5, arrow="start")
text((x0 + x1) / 2, y_to_pc - 26, "over SSH: object list for every frame", size=13,
     anchor="middle", color="#1a7f37")
text((x0 + x1) / 2, y_to_pc - 9, "+ video frames for the browser", size=13, anchor="middle",
     color="#1a7f37")

# --- devices under the Pi ----------------------------------------------------------
PWR = (670, 380, 130, 104)
CAM = (815, 380, 155, 104)
box(*PWR, "#fff8c5", "#9a6700", "Power supply", ["5 V, 2 A (rated)", "micro-USB"], title_size=14)
box(*CAM, "#fff8c5", "#9a6700", "USB webcam", ["UVC class", "YUYV 320×240", "30 frames/s"],
    title_size=14)
for bx in (PWR, CAM):
    cx = bx[0] + bx[2] / 2
    line([(cx, PI[1] + PI[3]), (cx, bx[1])], color=INK, width=2.5)
text(PWR[0] + PWR[2] / 2 + 8, 350, "power", size=12, color=MUTED)
text(CAM[0] + CAM[2] / 2 + 8, 350, "USB", size=12, color=MUTED)

# --- optional serial console (dashed) ---------------------------------------------
SER = (330, 380, 250, 82)
box(*SER, "#ffffff", "#8250df", "USB-serial adapter, 3.3 V", [
    "optional: boot console", "to Pi pins 6 GND, 8 TXD, 10 RXD"], dashed=True, title_size=14)
line([(180, PC[1] + PC[3]), (180, SER[1] + SER[3] / 2), (SER[0], SER[1] + SER[3] / 2)],
     color="#8250df", width=2, dashed=True)
text(188, 350, "USB", size=12, color=MUTED)
line([(SER[0] + SER[2], SER[1] + SER[3] / 2), (640, SER[1] + SER[3] / 2), (640, 290),
      (PI[0], 290)], color="#8250df", width=2, dashed=True)
text(632, 312, "GPIO header", size=12, anchor="end", color=MUTED)

# --- legend --------------------------------------------------------------------------
ly = 505
line([(40, ly), (80, ly)], color="#6e7781", width=5)
text(88, ly + 5, "cable", size=12.5, color=MUTED)
line([(150, ly), (190, ly)], color="#0969da", width=2.5, arrow="end")
text(198, ly + 5, "data flow (inside the Ethernet link)", size=12.5, color=MUTED)
line([(450, ly), (490, ly)], color="#8250df", width=2, dashed=True)
text(498, ly + 5, "optional, not needed for the demo", size=12.5, color=MUTED)
text(40, ly + 32, "No monitor or keyboard on the Pi: everything goes over SSH. "
     "Source: docs/make_setup_diagram.py", size=12, color=MUTED)

add("</svg>")

dst = Path(__file__).with_name("setup-diagram.svg")
dst.write_text("\n".join(out) + "\n", encoding="utf-8")
print(dst)
