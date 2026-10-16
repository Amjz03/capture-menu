"""Draws a stylised game frame (sky, mountains, city, road, HUD) for mockups."""
import random, math
from PySide6 import QtGui, QtCore
from PySide6.QtCore import Qt, QPointF, QRectF

PALETTES = {
    "dusk":   dict(sky=["#0b1033", "#3a1c5c", "#c2456b", "#f6a35c"], sun="#ffd38a", far="#2a1840", mid="#1a1030", city="#120a22", road="#16121f", glow="#ffb36b"),
    "neon":   dict(sky=["#04020f", "#120a3a", "#3b0f5c", "#7a1a7a"], sun="#ff4fd8", far="#1a0f3a", mid="#100828", city="#07041a", road="#0c0a18", glow="#30e0ff"),
    "desert": dict(sky=["#3a7bd5", "#6fa8e8", "#b9d7f2", "#f3e2c0"], sun="#fff6d8", far="#c99a6b", mid="#a8744a", city="#6b4a33", road="#4a3a30", glow="#fff1c2"),
    "forest": dict(sky=["#0f2a3a", "#1f5163", "#5f9a8a", "#cfe3c4"], sun="#f4ffd9", far="#2f5a4a", mid="#1d4034", city="#12291f", road="#1a221d", glow="#e9ffb0"),
    "snow":   dict(sky=["#5a6f8f", "#8ea4c4", "#c9d6e8", "#eef3f9"], sun="#ffffff", far="#a9b8cf", mid="#7d8fab", city="#4d5c75", road="#3a4459", glow="#ffffff"),
    "ember":  dict(sky=["#1a0505", "#4a0d0d", "#a3261a", "#f2712b"], sun="#ffcf6b", far="#3a0e0e", mid="#260808", city="#170404", road="#140707", glow="#ff9a3c"),
}

def ridge(p, w, h, base, amp, color, seed, step=40):
    rnd = random.Random(seed)
    path = QtGui.QPainterPath(QPointF(0, h)); y = base
    for x in range(0, w + step, step):
        y = base - abs(math.sin(x / (w / 3.1) + seed)) * amp - rnd.random() * amp * 0.35
        path.lineTo(x, y)
    path.lineTo(w, h); path.closeSubpath()
    p.fillPath(path, QtGui.QColor(color))

def draw_scene(w, h, pal="dusk", seed=1, hud=True, title="Reach the safehouse"):
    P = PALETTES[pal]; rnd = random.Random(seed)
    img = QtGui.QImage(w, h, QtGui.QImage.Format_ARGB32_Premultiplied)
    p = QtGui.QPainter(img); p.setRenderHint(QtGui.QPainter.Antialiasing)
    horizon = h * 0.58
    g = QtGui.QLinearGradient(0, 0, 0, horizon)
    for i, c in enumerate(P["sky"]): g.setColorAt(i / (len(P["sky"]) - 1), QtGui.QColor(c))
    p.fillRect(0, 0, w, int(horizon) + 2, g)
    # stars for dark skies
    if pal in ("neon", "dusk", "ember"):
        for _ in range(140):
            c = QtGui.QColor(255, 255, 255, rnd.randint(40, 160)); p.setPen(c)
            p.drawPoint(QPointF(rnd.random() * w, rnd.random() * horizon * 0.55))
    # sun with glow
    sx, sy = w * (0.3 + 0.4 * rnd.random()), horizon - h * 0.12
    rg = QtGui.QRadialGradient(sx, sy, h * 0.35)
    glow = QtGui.QColor(P["glow"]); glow.setAlpha(120); rg.setColorAt(0, glow); glow.setAlpha(0); rg.setColorAt(1, glow)
    p.fillRect(0, 0, w, h, rg)
    p.setPen(Qt.NoPen); p.setBrush(QtGui.QColor(P["sun"])); p.drawEllipse(QPointF(sx, sy), h * 0.06, h * 0.06)
    ridge(p, w, h, horizon - h * 0.05, h * 0.16, P["far"], seed)
    ridge(p, w, h, horizon + h * 0.02, h * 0.09, P["mid"], seed + 3, 30)
    # city skyline with lit windows
    x = 0
    while x < w:
        bw = rnd.randint(int(w * 0.02), int(w * 0.05)); bh = rnd.randint(int(h * 0.06), int(h * 0.26))
        r = QRectF(x, horizon + h * 0.05 - bh, bw, bh + h); p.fillRect(r, QtGui.QColor(P["city"]))
        lit = QtGui.QColor(P["glow"]); lit.setAlpha(170)
        for wy in range(int(r.top()) + 6, int(horizon + h * 0.05) - 4, 9):
            for wx in range(int(r.left()) + 4, int(r.right()) - 4, 8):
                if rnd.random() < 0.28: p.fillRect(QRectF(wx, wy, 3, 4), lit)
        x += bw + rnd.randint(0, int(w * 0.012))
    # ground + road in perspective
    ground_top = horizon + h * 0.05
    gg = QtGui.QLinearGradient(0, ground_top, 0, h); gg.setColorAt(0, QtGui.QColor(P["mid"])); gg.setColorAt(1, QtGui.QColor("#050508"))
    p.fillRect(QRectF(0, ground_top, w, h - ground_top), gg)
    vx = w * 0.5
    road = QtGui.QPolygonF([QPointF(vx - w * 0.02, ground_top), QPointF(vx + w * 0.02, ground_top), QPointF(w * 0.92, h), QPointF(w * 0.08, h)])
    p.setBrush(QtGui.QColor(P["road"])); p.drawPolygon(road)
    for i in range(14):
        t0, t1 = (i / 14) ** 2, ((i + 0.45) / 14) ** 2
        y0, y1 = ground_top + (h - ground_top) * t0, ground_top + (h - ground_top) * t1
        hw0, hw1 = 1 + 7 * t0, 1 + 7 * t1
        lane = QtGui.QColor(P["glow"]); lane.setAlpha(200)
        p.setBrush(lane); p.drawPolygon(QtGui.QPolygonF([QPointF(vx - hw0, y0), QPointF(vx + hw0, y0), QPointF(vx + hw1, y1), QPointF(vx - hw1, y1)]))
    # a car silhouette with tail lights
    cx, cy = w * 0.5, h * 0.86
    p.setBrush(QtGui.QColor("#0a0a0e")); p.drawRoundedRect(QRectF(cx - w * 0.09, cy - h * 0.07, w * 0.18, h * 0.09), 18, 18)
    p.drawRoundedRect(QRectF(cx - w * 0.06, cy - h * 0.12, w * 0.12, h * 0.07), 20, 20)
    for dx in (-1, 1):
        tl = QtGui.QRadialGradient(cx + dx * w * 0.07, cy - h * 0.035, w * 0.03)
        tl.setColorAt(0, QtGui.QColor(255, 40, 40, 230)); tl.setColorAt(1, QtGui.QColor(255, 0, 0, 0))
        p.setBrush(tl); p.drawEllipse(QPointF(cx + dx * w * 0.07, cy - h * 0.035), w * 0.03, w * 0.03)
    if hud:
        f = QtGui.QFont("Noto Sans"); f.setPixelSize(int(h * 0.022)); f.setBold(True); p.setFont(f)
        p.setPen(QtGui.QColor(255, 255, 255, 230)); p.drawText(QPointF(w * 0.03, h * 0.07), title.upper())
        f.setBold(False); f.setPixelSize(int(h * 0.017)); p.setFont(f); p.setPen(QtGui.QColor(255, 255, 255, 170))
        p.drawText(QPointF(w * 0.03, h * 0.1), "Distance 1.2 km")
        for i, (frac, col) in enumerate([(0.72, "#e8f0ff"), (0.45, "#5fd4ff")]):
            r = QRectF(w * 0.03, h * (0.13 + i * 0.025), w * 0.16, h * 0.01)
            p.setPen(Qt.NoPen); p.setBrush(QtGui.QColor(255, 255, 255, 50)); p.drawRoundedRect(r, 3, 3)
            p.setBrush(QtGui.QColor(col)); p.drawRoundedRect(QRectF(r.x(), r.y(), r.width() * frac, r.height()), 3, 3)
        # minimap
        mc, mr = QPointF(w * 0.93, h * 0.68), h * 0.08
        p.setBrush(QtGui.QColor(0, 0, 0, 120)); p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 120), 2)); p.drawEllipse(mc, mr, mr)
        p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 90), 3)); p.drawLine(QPointF(mc.x(), mc.y() + mr * 0.9), QPointF(mc.x() + mr * 0.2, mc.y() - mr * 0.8))
        p.setPen(Qt.NoPen); p.setBrush(QtGui.QColor("#ffd34d")); p.drawEllipse(QPointF(mc.x() + mr * 0.35, mc.y() - mr * 0.45), 5, 5)
        p.setBrush(QtGui.QColor("white")); p.drawPolygon(QtGui.QPolygonF([QPointF(mc.x(), mc.y() - 9), QPointF(mc.x() + 6, mc.y() + 6), QPointF(mc.x() - 6, mc.y() + 6)]))
        # speed
        f.setPixelSize(int(h * 0.05)); f.setBold(True); p.setFont(f); p.setPen(QtGui.QColor(255, 255, 255, 235))
        p.drawText(QRectF(w * 0.80, h * 0.78, w * 0.17, h * 0.06), Qt.AlignRight | Qt.AlignVCenter, "142")
        f.setPixelSize(int(h * 0.016)); f.setBold(False); p.setFont(f); p.setPen(QtGui.QColor(255, 255, 255, 170))
        p.drawText(QRectF(w * 0.80, h * 0.84, w * 0.17, h * 0.03), Qt.AlignRight | Qt.AlignVCenter, "KM/H")
    p.end()
    return img
