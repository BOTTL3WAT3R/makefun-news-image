#!/usr/bin/env python3
"""Sum up 17 November 2026's world news in one image.

A deterministic, standard-library-only program that draws a one-page
news poster (masthead, six story panels, ticker) with its own tiny
rasterizer and bitmap font, and writes it as a 1024x1024 PNG to
$MAKEFUN_OUTPUT_DIR/entry.png (default /output).

No randomness, no clock, no environment input to the drawing: two
runs always produce byte-identical output.
"""

import math
import os
import struct
import zlib

# ---------------------------------------------------------------- canvas

SS = 2                      # supersampling factor
W = 1024                    # final image width/height
SW = W * SS                 # supersampled width/height

NAVY = (22, 41, 77)
NAVY_DARK = (13, 24, 48)
CREAM = (243, 236, 219)
PANEL = (251, 246, 233)
INK = (24, 30, 43)
RED = (200, 53, 43)
GOLD = (224, 169, 46)
STEEL = (127, 168, 201)
WATER = (62, 111, 163)
GREY = (138, 148, 166)
ROBOT = (94, 108, 130)


class Canvas:
    def __init__(self, color):
        self.px = bytearray(bytes(color) * (SW * SW))

    def _span(self, row, x0, x1, pat):
        # fill pixels [x0, x1) on supersampled row `row`; pat is one pixel
        if x1 <= x0:
            return
        if x0 < 0:
            x0 = 0
        if x1 > SW:
            x1 = SW
        if x1 <= x0:
            return
        base = (row * SW + x0) * 3
        n = x1 - x0
        self.px[base:base + 3 * n] = pat * n

    def rect(self, x, y, w, h, color):
        """Filled rectangle in final-image coordinates."""
        pat = bytes(color)
        X, Y = int(x * SS), int(y * SS)
        Wd, H = int(w * SS), int(h * SS)
        for row in range(Y, Y + H):
            if 0 <= row < SW:
                self._span(row, X, X + Wd, pat)

    def circle(self, cx, cy, r, color):
        pat = bytes(color)
        CX, CY, R = cx * SS, cy * SS, r * SS
        R = int(R)
        for dy in range(-R, R + 1):
            row = int(CY) + dy
            if not (0 <= row < SW):
                continue
            half = math.isqrt(R * R - dy * dy)
            self._span(row, int(CX) - half, int(CX) + half + 1, pat)

    def ring(self, cx, cy, r_out, r_in, color):
        pat = bytes(color)
        CX, CY = cx * SS, cy * SS
        RO, RI = int(r_out * SS), int(r_in * SS)
        for dy in range(-RO, RO + 1):
            row = int(CY) + dy
            if not (0 <= row < SW):
                continue
            ho = math.isqrt(RO * RO - dy * dy)
            if abs(dy) < RI:
                hi = math.isqrt(RI * RI - dy * dy)
                self._span(row, int(CX) - ho, int(CX) - hi, pat)
                self._span(row, int(CX) + hi, int(CX) + ho + 1, pat)
            else:
                self._span(row, int(CX) - ho, int(CX) + ho + 1, pat)

    def ellipse(self, cx, cy, rx, ry, color):
        pat = bytes(color)
        CX, CY = cx * SS, cy * SS
        RX, RY = rx * SS, ry * SS
        for dy in range(-int(RY), int(RY) + 1):
            row = int(CY) + dy
            if not (0 <= row < SW):
                continue
            t = 1.0 - (dy / RY) ** 2
            if t < 0:
                continue
            half = int(RX * math.sqrt(t))
            self._span(row, int(CX) - half, int(CX) + half + 1, pat)

    def polygon(self, points, color):
        """Filled polygon; points are (x, y) in final coordinates."""
        pat = bytes(color)
        pts = [(x * SS, y * SS) for x, y in points]
        ys = [p[1] for p in pts]
        y0, y1 = int(min(ys)), int(max(ys))
        n = len(pts)
        for row in range(y0, y1 + 1):
            if not (0 <= row < SW):
                continue
            yc = row + 0.5
            xs = []
            for i in range(n):
                xa, ya = pts[i]
                xb, yb = pts[(i + 1) % n]
                if ya == yb:
                    continue
                if (ya <= yc < yb) or (yb <= yc < ya):
                    xs.append(xa + (yc - ya) * (xb - xa) / (yb - ya))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                self._span(row, int(xs[i]), int(xs[i + 1]) + 1, pat)

    def line(self, x1, y1, x2, y2, w, color):
        """Thick line with round caps."""
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length == 0:
            self.circle(x1, y1, w / 2, color)
            return
        nx, ny = -dy / length * w / 2, dx / length * w / 2
        self.polygon([(x1 + nx, y1 + ny), (x2 + nx, y2 + ny),
                      (x2 - nx, y2 - ny), (x1 - nx, y1 - ny)], color)
        self.circle(x1, y1, w / 2, color)
        self.circle(x2, y2, w / 2, color)

    def arc(self, cx, cy, r, a0, a1, w, color):
        """Arc from angle a0 to a1 (degrees, 0 = east, CCW positive in
        screen space where +y is down, so positive angles go clockwise
        visually). Stamped with small circles."""
        steps = max(4, int(abs(a1 - a0) * r / 3))
        for i in range(steps + 1):
            a = math.radians(a0 + (a1 - a0) * i / steps)
            self.circle(cx + r * math.cos(a), cy + r * math.sin(a),
                        w / 2, color)


# ------------------------------------------------------------------ font
# 5x7 bitmap glyphs, drawn by hand for this poster. All text is caps.

GLYPHS = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "##..#", "#.#.#", "#..##", "#..##", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"),
    "Y": ("#...#", ".#.#.", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."),
    "2": (".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    ":": (".....", "..#..", "..#..", ".....", "..#..", "..#..", "....."),
    ";": (".....", "..#..", "..#..", ".....", "..#..", "..#..", ".#..."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    "'": ("..#..", "..#..", ".....", ".....", ".....", ".....", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "\u2022": (".....", ".....", ".###.", ".###.", ".###.", ".....", "....."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
}


def text_width(s, cell, tracking=0):
    if not s:
        return 0
    return len(s) * (6 * cell + tracking) - tracking


def draw_text(cv, x, y, s, cell, color, tracking=0):
    """Draw text with top-left at (x, y); cell = glyph cell size in
    final-image pixels. Returns the x just past the text."""
    cx = x
    for ch in s:
        glyph = GLYPHS[ch]
        for row_i, row in enumerate(glyph):
            for col_i, bit in enumerate(row):
                if bit == "#":
                    cv.rect(cx + col_i * cell, y + row_i * cell,
                            cell, cell, color)
        cx += 6 * cell + tracking
    return cx


def draw_text_centered(cv, cx, y, s, cell, color, tracking=0):
    x = cx - text_width(s, cell, tracking) // 2
    return draw_text(cv, x, y, s, cell, color, tracking)


# ----------------------------------------------------------------- icons
# Each icon draws inside a 120x76 box whose top-left is (x, y).

def _waves(cv, x, y, w, color):
    """Two rows of scalloped wave lines."""
    for row_y in (y, y + 9):
        xx = x
        while xx < x + w - 10:
            cv.arc(xx + 5, row_y + 4, 5, 180, 360, 2, color)
            xx += 11


def icon_bridge(cv, x, y):
    # suspension bridge, middle span broken, burst at the break
    deck_y = y + 42
    for tx in (x + 16, x + 96):                      # towers
        cv.rect(tx, y + 10, 8, 48, NAVY)
        cv.rect(tx - 2, y + 20, 12, 3, NAVY)
        cv.rect(tx - 2, y + 32, 12, 3, NAVY)
    cv.line(x + 19, y + 12, x + 4, deck_y, 2, NAVY)     # cables
    cv.line(x + 19, y + 12, x + 52, deck_y, 2, NAVY)
    cv.line(x + 99, y + 12, x + 68, deck_y, 2, NAVY)
    cv.line(x + 99, y + 12, x + 116, deck_y, 2, NAVY)
    cv.rect(x + 2, deck_y, 50, 5, NAVY)                 # left deck
    cv.rect(x + 68, deck_y, 50, 5, NAVY)                # right deck
    cv.polygon([(x + 52, deck_y + 5), (x + 68, deck_y + 5),
                (x + 66, deck_y + 16), (x + 55, deck_y + 13)], NAVY)
    cv.polygon([(x + 56, deck_y + 22), (x + 66, deck_y + 24),
                (x + 64, deck_y + 30), (x + 57, deck_y + 28)], NAVY)
    for i in range(8):                                  # burst
        a = math.radians(i * 45)
        cv.line(x + 60 + 6 * math.cos(a), y + 33 + 6 * math.sin(a),
                x + 60 + 15 * math.cos(a), y + 33 + 15 * math.sin(a),
                3, RED)
    cv.circle(x + 60, y + 33, 6, GOLD)
    _waves(cv, x + 4, y + 60, 112, WATER)


def icon_tanker(cv, x, y):
    # carrier silhouette behind, tanker in front, spiked mine ahead
    cv.polygon([(x + 0, y + 26), (x + 62, y + 26), (x + 58, y + 34),
                (x + 6, y + 34)], GREY)                       # carrier hull
    cv.rect(x + 2, y + 22, 56, 4, GREY)                       # flight deck
    cv.rect(x + 44, y + 14, 6, 8, GREY)                       # island
    cv.polygon([(x + 34, y + 40), (x + 118, y + 40), (x + 110, y + 54),
                (x + 42, y + 54)], NAVY)                      # tanker hull
    cv.rect(x + 40, y + 36, 72, 4, NAVY)
    cv.rect(x + 48, y + 29, 14, 7, RED)                       # containers
    cv.rect(x + 64, y + 29, 14, 7, STEEL)
    cv.rect(x + 80, y + 29, 14, 7, GOLD)
    cv.rect(x + 102, y + 26, 7, 10, NAVY)                     # stern castle
    for i in range(8):                                        # mine spikes
        a = math.radians(i * 45 + 22)
        cv.line(x + 24 + 6 * math.cos(a), y + 50 + 6 * math.sin(a),
                x + 24 + 11 * math.cos(a), y + 50 + 11 * math.sin(a),
                2, RED)
    cv.circle(x + 24, y + 50, 7, RED)
    cv.circle(x + 24, y + 50, 3, NAVY_DARK)
    _waves(cv, x + 38, y + 60, 80, WATER)


def icon_plane(cv, x, y):
    # airliner seen from the front, climbing past a sun disc
    cv.circle(x + 88, y + 24, 17, GOLD)
    cv.ellipse(x + 56, y + 40, 8, 24, NAVY)                   # fuselage
    cv.polygon([(x + 50, y + 38), (x + 6, y + 56), (x + 8, y + 62),
                (x + 52, y + 50)], NAVY)                      # left wing
    cv.polygon([(x + 62, y + 38), (x + 106, y + 56), (x + 104, y + 62),
                (x + 60, y + 50)], NAVY)                      # right wing
    cv.polygon([(x + 50, y + 58), (x + 38, y + 68), (x + 40, y + 72),
                (x + 54, y + 66)], NAVY)                      # tail left
    cv.polygon([(x + 62, y + 58), (x + 74, y + 68), (x + 72, y + 72),
                (x + 58, y + 66)], NAVY)                      # tail right
    cv.circle(x + 30, y + 54, 4, NAVY)                        # engines
    cv.circle(x + 82, y + 54, 4, NAVY)
    cv.ellipse(x + 56, y + 24, 4, 6, STEEL)                   # cockpit


def icon_jet(cv, x, y):
    # fighter from above; radar arcs sweeping from the right
    cv.polygon([(x + 40, y + 4), (x + 46, y + 22), (x + 68, y + 46),
                (x + 68, y + 52), (x + 48, y + 46), (x + 47, y + 58),
                (x + 54, y + 68), (x + 54, y + 72), (x + 40, y + 66),
                (x + 26, y + 72), (x + 26, y + 68), (x + 33, y + 58),
                (x + 32, y + 46), (x + 12, y + 52), (x + 12, y + 46),
                (x + 34, y + 22)], NAVY)
    cv.ellipse(x + 40, y + 26, 4, 9, STEEL)                   # canopy
    for r in (10, 18, 26):
        cv.arc(x + 96, y + 62, r, 180, 265, 3, RED)
    cv.circle(x + 96, y + 62, 3, RED)


def icon_robot(cv, x, y):
    # robot head inside a prohibition ring
    cv.line(x + 60, y + 14, x + 60, y + 22, 3, ROBOT)         # antenna
    cv.circle(x + 60, y + 11, 4, ROBOT)
    cv.rect(x + 36, y + 22, 48, 38, ROBOT)                    # head
    cv.rect(x + 31, y + 34, 5, 12, ROBOT)                     # ears
    cv.rect(x + 84, y + 34, 5, 12, ROBOT)
    cv.circle(x + 50, y + 38, 5, CREAM)                       # eyes
    cv.circle(x + 70, y + 38, 5, CREAM)
    for gx in (52, 59, 66):                                   # mouth grille
        cv.rect(x + gx, y + 50, 4, 6, NAVY_DARK)
    cv.ring(x + 60, y + 38, 36, 29, RED)                      # ring
    cv.line(x + 35, y + 13, x + 85, y + 63, 7, RED)           # slash


def icon_chart(cv, x, y):
    # falling chart arrow over a microchip
    pts = [(x + 4, y + 14), (x + 24, y + 26), (x + 38, y + 18),
           (x + 62, y + 46)]
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        cv.line(ax, ay, bx, by, 5, RED)
    cv.polygon([(x + 62, y + 46), (x + 47, y + 44), (x + 56, y + 30)],
               RED)                                           # arrowhead
    cv.rect(x + 78, y + 20, 34, 34, INK)                      # chip body
    cv.rect(x + 88, y + 30, 14, 14, CREAM)
    for i in range(3):                                        # pins
        py = y + 26 + i * 11
        cv.rect(x + 72, py, 6, 4, INK)
        cv.rect(x + 112, py, 6, 4, INK)
        px = x + 84 + i * 11
        cv.rect(px, y + 14, 4, 6, INK)
        cv.rect(px, y + 54, 4, 6, INK)


# ---------------------------------------------------------------- poster

PANELS = [
    (icon_bridge, ("UKRAINE STRIKES", "CRIMEA BRIDGE"),
     ("SPAN COLLAPSES; RUSSIA", "HITS KYIV BRIDGES")),
    (icon_tanker, ("TANKERS HIT", "MINES IN HORMUZ"),
     ("IRGC SAYS; THIRD US", "CARRIER ARRIVES")),
    (icon_plane, ("TRUMP IN MANILA", "FOR ASEAN"),
     ("THAILAND TRADE PACT", "SIGNED")),
    (icon_jet, ("JAPAN JETS", "SCRAMBLE"),
     ("RUSSIAN AIRCRAFT", "ENTER AIRSPACE")),
    (icon_robot, ("128 NATIONS", "KILLER ROBOTS"),
     ("GENEVA DEBATES BANNING", "AI WEAPONS")),
    (icon_chart, ("STOCKS SLIDE", "BEFORE NVIDIA"),
     ("TECH SELLS OFF BEFORE", "EARNINGS")),
]

TICKER_1 = ("ALSO: ", "PENTAGON FAILS 9TH STRAIGHT AUDIT \u2022 UK "
            "SANCTIONS SETTLEMENT FIRMS")
TICKER_2 = ("WEST URGES GAZA AID CROSSINGS OPEN \u2022 US MEASLES CASES "
            "HIGHEST SINCE 1991")


def compose():
    cv = Canvas(CREAM)

    # masthead
    cv.rect(0, 0, W, 176, NAVY)
    cv.rect(0, 176, W, 6, RED)
    draw_text_centered(cv, W // 2, 22, "THE WORLD IN ONE PICTURE", 3,
                       GOLD, tracking=6)
    draw_text_centered(cv, W // 2, 50, "17 NOVEMBER 2026", 10, CREAM)
    cv.rect(150, 146, 250, 3, RED)
    cv.rect(624, 146, 250, 3, RED)
    draw_text_centered(cv, W // 2, 134, "TUESDAY", 4, CREAM)

    # panels, 2 columns x 3 rows
    panel_w, panel_h = 484, 240
    xs = (20, 520)
    ys = (196, 452, 708)
    for i, (icon, headline, subline) in enumerate(PANELS):
        px, py = xs[i % 2], ys[i // 2]
        cv.rect(px, py, panel_w, panel_h, PANEL)
        cv.rect(px, py, panel_w, 2, NAVY)
        cv.rect(px, py + panel_h - 2, panel_w, 2, NAVY)
        cv.rect(px, py, 2, panel_h, NAVY)
        cv.rect(px + panel_w - 2, py, 2, panel_h, NAVY)
        icon(cv, px + panel_w // 2 - 60, py + 8)
        cv.rect(px + panel_w // 2 - 12, py + 90, 24, 3, RED)
        draw_text_centered(cv, px + panel_w // 2, py + 100,
                           headline[0], 5, INK)
        draw_text_centered(cv, px + panel_w // 2, py + 139,
                           headline[1], 5, INK)
        draw_text_centered(cv, px + panel_w // 2, py + 184,
                           subline[0], 3, NAVY)
        draw_text_centered(cv, px + panel_w // 2, py + 208,
                           subline[1], 3, NAVY)

    # ticker
    cv.rect(0, 964, W, 60, NAVY)
    line1_w = text_width(TICKER_1[0] + TICKER_1[1], 2)
    tx = (W - line1_w) // 2
    tx = draw_text(cv, tx, 976, TICKER_1[0], 2, GOLD)
    draw_text(cv, tx, 976, TICKER_1[1], 2, CREAM)
    draw_text_centered(cv, W // 2, 1000, TICKER_2, 2, CREAM)

    return cv


# -------------------------------------------------------------- png out

def downscale(cv):
    out = bytearray(W * W * 3)
    src = cv.px
    row_bytes = SW * 3
    for oy in range(W):
        r0 = (2 * oy) * row_bytes
        r1 = (2 * oy + 1) * row_bytes
        ob = oy * W * 3
        for ox in range(W):
            i0 = r0 + 6 * ox
            i1 = r1 + 6 * ox
            o = ob + 3 * ox
            out[o] = (src[i0] + src[i0 + 3] + src[i1] + src[i1 + 3]) >> 2
            out[o + 1] = (src[i0 + 1] + src[i0 + 4] +
                          src[i1 + 1] + src[i1 + 4]) >> 2
            out[o + 2] = (src[i0 + 2] + src[i0 + 5] +
                          src[i1 + 2] + src[i1 + 5]) >> 2
    return bytes(out)


def png_bytes(pixels):
    raw = bytearray()
    stride = W * 3
    for y in range(W):
        raw.append(0)
        raw += pixels[y * stride:(y + 1) * stride]
    comp = zlib.compress(bytes(raw), 9)

    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", W, W, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
            chunk(b"IDAT", comp) + chunk(b"IEND", b""))


def main():
    cv = compose()
    data = png_bytes(downscale(cv))
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "entry.png"), "wb") as fh:
        fh.write(data)


if __name__ == "__main__":
    main()
