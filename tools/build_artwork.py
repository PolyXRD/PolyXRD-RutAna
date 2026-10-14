"""PolyXRD RutAna 品牌资产生成器
=================================
参照 PolyXRD-CifCalc 的家族视觉血统（Pillow 纯代码绘制，可复现、颜色精确）。

设计血统（与家族严格一致）
--------------------------
- 品牌深色 #0F172A (slate-950) → 品牌蓝 #0284C7 (sky-600) 对角线渐变
- 家族符号 = 「白色正六边形」。本工具内部 motif =
  「金红石/锐钛矿双晶胞线框 + 蓝色衍射双峰（25.3° / 27.4° 两个峰）」
- 子工具强调色 = 青色 #22D3EE

产出（写入 <root>/resources/）
------------------------------
- app-icon.png        256×256   运行时窗口图标
- app-icon@2x.png     512×512   高分屏备份
- app-icon.ico        多分辨率  给 exe 资源使用
- crystal-mark.png    256×256   透明底深色 mark（浅色背景用）
- logo-horizontal.png 512×160   横向 logo：mark + 「PolyXRD RutAna」
- splash-screen.png   480×270   启动图（深色底 + logo + 版本 + tagline）
- hero-banner.png     1600×600  About 页头图

使用：
    python tools/build_artwork.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rutana.version import APP_TAGLINE, __version__  # noqa: E402

RES_DIR = ROOT / "resources"

# --------------------------------------------------------------------------- #
# 品牌常量（家族色，严格一致）
# --------------------------------------------------------------------------- #
BRAND_DARK = (15, 23, 42)        # #0F172A  slate-950  "Poly"
BRAND_BLUE = (2, 132, 199)       # #0284C7  sky-600    "XRD"
WHITE = (255, 255, 255)
SOFT = (226, 232, 240)           # #E2E8F0  slate-200
SLATE = (100, 116, 139)          # #64748B  slate-500
CYAN = (34, 211, 238)            # #22D3EE  子工具强调色
CYAN_LIGHT = (125, 211, 252)     # #7DD3FC
CYAN_DARK = (8, 145, 178)        # #0891B2  浅色背景上的青色词标

# 启动图 / 横幅的深空背景（与家族 splash 的墨青基调一致）
BG_INNER = (12, 48, 70)
BG_OUTER = (5, 12, 24)

FONT_BOLD = r"C:/Windows/Fonts/segoeuib.ttf"
FONT_SEMI = r"C:/Windows/Fonts/seguisb.ttf"
FONT_CN = r"C:/Windows/Fonts/msyh.ttc"

ICON_SIZES = [16, 24, 32, 48, 64, 128, 256]
COS30 = math.cos(math.radians(30.0))

# 双峰参数：对应锐钛型 101（25.3°，较强）与金红石型 110（27.4°，稍弱）
PEAK1_POS, PEAK1_REL = 0.30, 1.00
PEAK2_POS, PEAK2_REL = 0.70, 0.84
PEAK_SIGMA = 0.050


# --------------------------------------------------------------------------- #
# 基础几何 / 绘制工具
# --------------------------------------------------------------------------- #
def hex_points(cx: float, cy: float, r: float) -> list[tuple[float, float]]:
    """尖顶正六边形顶点（顶点在正上/正下）。"""
    return [
        (cx + r * math.cos(math.radians(-90 + 60 * k)),
         cy + r * math.sin(math.radians(-90 + 60 * k)))
        for k in range(6)
    ]


def draw_cell(draw: ImageDraw.ImageDraw, cx: float, cy: float,
              a: float, c: float, color, lw: int) -> None:
    """四方晶系晶胞线框：8 顶点 + 12 棱（等轴测投影）。

    a = 底面半宽，c = 半高。锐钛型 c/a≈2.5（竖长），金红石 c/a≈0.64（扁平）。
    """
    corners: dict[tuple[int, int, int], tuple[float, float]] = {}
    for xs in (-1, 1):
        for ys in (-1, 1):
            for zs in (-1, 1):
                px = (xs * a - zs * a) * COS30          # (x - z)·cos30
                py = (xs * a + zs * a) * 0.5 - ys * c   # (x + z)/2 - y
                corners[(xs, ys, zs)] = (cx + px, cy + py)
    # 12 条棱：每条只画一次（只连相差一个坐标的顶点对）
    for cell, p in corners.items():
        for axis in range(3):
            other = list(cell)
            other[axis] = -other[axis]
            other = tuple(other)
            if cell < other:
                draw.line([p, corners[other]], fill=color, width=lw)


def draw_double_peak(draw: ImageDraw.ImageDraw, x0: float, y0: float,
                     width: float, amp: float, color, lw: int) -> None:
    """蓝色衍射双峰：基线 + 两个高斯峰（25.3° / 27.4° 的抽象表达）。"""
    pts: list[tuple[float, float]] = [(x0, y0)]
    n = 140
    for i in range(n + 1):
        t = i / n
        g1 = PEAK1_REL * math.exp(-((t - PEAK1_POS) ** 2) / (2 * PEAK_SIGMA ** 2))
        g2 = PEAK2_REL * math.exp(-((t - PEAK2_POS) ** 2) / (2 * PEAK_SIGMA ** 2))
        pts.append((x0 + t * width, y0 - amp * (g1 + g2)))
    pts.append((x0 + width, y0))
    draw.line(pts, fill=color, width=lw, joint="curve")


def make_mark(size: int, hex_color, anatase_color, rutile_color,
              peak_color, hex_w_ratio: float = 0.070, glow: bool = False) -> Image.Image:
    """生成 RutAna 家族符号：六边形 + 双晶胞线框 + 衍射双峰（透明底 RGBA）。"""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    cx = cy = size / 2.0
    r = size * 0.44
    hex_w = max(2, int(round(size * hex_w_ratio)))
    pts = hex_points(cx, cy, r)
    cell_lw = max(2, int(size * 0.012))
    peak_lw = max(2, int(size * 0.030))

    def motif(d: ImageDraw.ImageDraw) -> None:
        # 锐钛型晶胞（竖长，I41/amd）居左上；金红石晶胞（扁平，P42/mnm）居右下
        draw_cell(d, cx - size * 0.10, cy - size * 0.03,
                  size * 0.085, size * 0.095, anatase_color, cell_lw)
        draw_cell(d, cx + size * 0.12, cy + size * 0.02,
                  size * 0.070, size * 0.045, rutile_color, cell_lw)
        # 衍射双峰横贯下三分之一
        draw_double_peak(d, cx - size * 0.24, cy + size * 0.27,
                         size * 0.48, size * 0.10, peak_color, peak_lw)

    if glow:
        gl = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        gd = ImageDraw.Draw(gl)
        gd.line(pts + [pts[0]], fill=hex_color, width=hex_w, joint="curve")
        motif(gd)
        gl = gl.filter(ImageFilter.GaussianBlur(max(2, size * 0.02)))
        im.alpha_composite(gl)

    d = ImageDraw.Draw(im)
    d.line(pts + [pts[0]], fill=hex_color, width=hex_w, joint="curve")
    motif(d)
    return im


def diagonal_gradient(size: int, c1, c2) -> Image.Image:
    """左上 → 右下 对角线渐变（低分辨率生成再放大，保证平滑）。"""
    small = Image.new("RGB", (96, 96))
    px = small.load()
    for y in range(96):
        for x in range(96):
            t = (x + y) / (2 * 95.0)
            px[x, y] = (round(c1[0] + (c2[0] - c1[0]) * t),
                        round(c1[1] + (c2[1] - c1[1]) * t),
                        round(c1[2] + (c2[2] - c1[2]) * t))
    return small.resize((size, size), Image.BICUBIC)


def radial_gradient(w: int, h: int, inner, outer) -> Image.Image:
    """径向渐变背景（中心亮 → 四周暗）。"""
    small = Image.new("RGB", (120, 68))
    px = small.load()
    cx, cy = 59.5, 33.0
    maxd = math.hypot(cx, cy)
    for y in range(68):
        for x in range(120):
            d = min(1.0, math.hypot(x - cx, y - cy) / maxd) ** 0.85
            px[x, y] = (round(inner[0] + (outer[0] - inner[0]) * d),
                        round(inner[1] + (outer[1] - inner[1]) * d),
                        round(inner[2] + (outer[2] - inner[2]) * d))
    return small.resize((w, h), Image.BICUBIC)


def rounded_mask(size: int, ratio: float = 0.22) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=int(size * ratio), fill=255)
    return m


def load_font(paths: list[str], size: int) -> ImageFont.FreeTypeFont:
    """按顺序尝试加载字体，全部失败时退回默认位图字体。"""
    for p in paths:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()  # type: ignore[return-value]


def draw_wordmark(draw: ImageDraw.ImageDraw, x: float, y_top: float,
                  segments: list[tuple[str, tuple[int, int, int]]],
                  font: ImageFont.FreeTypeFont) -> float:
    """按 segment 着色绘制词标，返回结束 x。"""
    for text, color in segments:
        draw.text((x, y_top), text, font=font, fill=color)
        x += draw.textlength(text, font=font)
    return x


# --------------------------------------------------------------------------- #
# 各类资产构建
# --------------------------------------------------------------------------- #
def build_icon() -> None:
    """应用图标：对角渐变底 + 发光 mark，256 / @2x / 多分辨率 ico。"""
    size = 512
    base = diagonal_gradient(size, BRAND_DARK, BRAND_BLUE).convert("RGBA")
    mark = make_mark(size, WHITE, CYAN, SOFT, CYAN_LIGHT, hex_w_ratio=0.075, glow=True)
    base.alpha_composite(mark)
    base.putalpha(rounded_mask(size, 0.22))

    RES_DIR.mkdir(parents=True, exist_ok=True)
    base.resize((512, 512), Image.LANCZOS).save(
        RES_DIR / "app-icon@2x.png", format="PNG", optimize=True)
    base.resize((256, 256), Image.LANCZOS).save(
        RES_DIR / "app-icon.png", format="PNG", optimize=True)
    base.save(RES_DIR / "app-icon.ico", format="ICO",
              sizes=[(s, s) for s in ICON_SIZES])
    print("[icon] app-icon.png / app-icon@2x.png / app-icon.ico")


def build_crystal_mark() -> None:
    """透明底、深色线条版家族符号（浅色背景 About / 文档用）。"""
    mark = make_mark(256, BRAND_DARK, BRAND_BLUE, BRAND_DARK, BRAND_BLUE,
                     hex_w_ratio=0.055)
    mark.save(RES_DIR / "crystal-mark.png", format="PNG", optimize=True)
    print("[mark] crystal-mark.png")


def build_logo_horizontal() -> None:
    """横向 logo 512×160：mark + 「PolyXRD │ RutAna」+ 标准号副标。"""
    SS = 4
    W, H = 512 * SS, 160 * SS
    mark_size = int(H * 0.72)
    font_size = int(H * 0.30)
    sub = "GB/T 30793—2014"

    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    mark = make_mark(mark_size, BRAND_DARK, BRAND_BLUE, BRAND_DARK, BRAND_BLUE,
                     hex_w_ratio=0.055)
    pad_x = int(H * 0.10)
    im.alpha_composite(mark, (pad_x, (H - mark_size) // 2))

    d = ImageDraw.Draw(im)
    font_big = load_font([FONT_BOLD], font_size)
    gap = int(H * 0.05)
    x_text = pad_x + mark_size + int(H * 0.12)
    seg_w = (d.textlength("PolyXRD ", font=font_big) + d.textlength("RutAna", font=font_big))
    while x_text + seg_w > W - int(H * 0.10) and font_size > 24:
        font_size = int(font_size * 0.95)
        font_big = load_font([FONT_BOLD], font_size)
        seg_w = d.textlength("PolyXRD ", font=font_big) + d.textlength("RutAna", font=font_big)
    y_big = int(H * 0.20)
    x_end = draw_wordmark(d, x_text, y_big,
                          [("PolyXRD ", BRAND_DARK), ("RutAna", CYAN_DARK)], font_big)
    font_sub = load_font([FONT_SEMI, FONT_CN], int(H * 0.115))
    d.text((x_text, y_big + int(H * 0.40)), sub, font=font_sub, fill=SLATE)
    del x_end

    im.resize((W // SS, H // SS), Image.LANCZOS).save(
        RES_DIR / "logo-horizontal.png", format="PNG", optimize=True)
    print("[logo] logo-horizontal.png (512x160)")


def build_splash() -> None:
    """启动图 480×270：深色底 + mark + 标题 + 版本 + tagline。"""
    W, H = 480, 270
    SS = 2
    w, h = W * SS, H * SS
    bg = radial_gradient(w, h, BG_INNER, BG_OUTER).convert("RGBA")

    mark = make_mark(int(h * 0.42), WHITE, CYAN, SOFT, CYAN_LIGHT,
                     hex_w_ratio=0.070, glow=True)
    bg.alpha_composite(mark, ((w - mark.size[0]) // 2, int(h * 0.015)))

    d = ImageDraw.Draw(bg)
    font_t = load_font([FONT_BOLD], int(h * 0.115))
    tw = d.textlength("PolyXRD ", font=font_t) + d.textlength("RutAna", font=font_t)
    draw_wordmark(d, (w - tw) / 2, int(h * 0.52),
                  [("PolyXRD ", SOFT), ("RutAna", CYAN_LIGHT)], font_t)

    font_v = load_font([FONT_SEMI], int(h * 0.055))
    ver = f"v{__version__}"
    d.text(((w - d.textlength(ver, font=font_v)) / 2, int(h * 0.665)),
           ver, font=font_v, fill=CYAN)

    font_c = load_font([FONT_CN, FONT_SEMI], int(h * 0.052))
    tw = d.textlength(APP_TAGLINE, font=font_c)
    d.text(((w - tw) / 2, int(h * 0.755)), APP_TAGLINE, font=font_c,
           fill=(130, 176, 205))

    bg.convert("RGB").resize((W, H), Image.LANCZOS).save(
        RES_DIR / "splash-screen.png", format="PNG", optimize=True)
    print("[splash] splash-screen.png (480x270)")


def build_hero() -> None:
    """About 页头图 1600×600：深空底 + 大 mark + 标题 + tagline。"""
    W, H = 1600, 600
    bg = radial_gradient(W, H, BG_INNER, BG_OUTER).convert("RGBA")

    mark = make_mark(int(H * 0.40), WHITE, CYAN, SOFT, CYAN_LIGHT,
                     hex_w_ratio=0.070, glow=True)
    bg.alpha_composite(mark, ((W - mark.size[0]) // 2, int(H * 0.03)))

    d = ImageDraw.Draw(bg)
    font_t = load_font([FONT_BOLD], int(H * 0.135))
    tw = d.textlength("PolyXRD ", font=font_t) + d.textlength("RutAna", font=font_t)
    draw_wordmark(d, (W - tw) / 2, int(H * 0.50),
                  [("PolyXRD ", SOFT), ("RutAna", CYAN_LIGHT)], font_t)

    font_c = load_font([FONT_CN, FONT_SEMI], int(H * 0.052))
    tw = d.textlength(APP_TAGLINE, font=font_c)
    d.text(((W - tw) / 2, int(H * 0.72)), APP_TAGLINE, font=font_c,
           fill=(130, 176, 205))

    font_s = load_font([FONT_SEMI], int(H * 0.042))
    sub = "Intensity-Ratio Method A  ·  Rietveld Full-Pattern Fit B  ·  GB/T 30793—2014"
    tw = d.textlength(sub, font=font_s)
    d.text(((W - tw) / 2, int(H * 0.83)), sub, font=font_s, fill=CYAN)

    bg.convert("RGB").save(RES_DIR / "hero-banner.png", format="PNG", optimize=True)
    print("[hero] hero-banner.png (1600x600)")


def build_all() -> None:
    RES_DIR.mkdir(parents=True, exist_ok=True)
    build_icon()
    build_crystal_mark()
    build_logo_horizontal()
    build_splash()
    build_hero()
    files = sorted(p.name for p in RES_DIR.iterdir() if p.is_file())
    print(f"\n[done] 共 {len(files)} 个资产: {files}")


if __name__ == "__main__":
    build_all()
