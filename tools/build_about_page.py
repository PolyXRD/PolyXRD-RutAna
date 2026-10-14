"""生成 PolyXRD RutAna「关于」HTML 页面
====================================
读取 <root>/resources/ 下的品牌资产，图片以 base64 内嵌，产出自包含的
`docs/about.html`（可直接双击/预览/分享，不依赖外部文件）。

家族卡片为三张：PolyXRD / PolyXRD Converter / PolyXRD RutAna（本工具，
标注「GB/T 30793—2014 晶型比率专用」）。

使用：
    python tools/build_about_page.py
"""

from __future__ import annotations

import base64
import mimetypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rutana.version import __version__  # noqa: E402

RES = ROOT / "resources"
OUT = ROOT / "docs" / "about.html"


def data_uri(name: str) -> str:
    """把资源图片编码为 data URI（缺失时返回空串）。"""
    p = RES / name
    if not p.exists():
        return ""
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>关于 PolyXRD RutAna</title>
<style>
  :root{ --dark:#0F172A; --blue:#0284C7; --cyan:#0891B2; --slate:#64748B; --line:#e2e8f0;
         --ink:#1e293b; --soft:#64748b; }
  *{ box-sizing:border-box; }
  body{ margin:0; font-family:"Segoe UI","Microsoft YaHei",system-ui,-apple-system,sans-serif;
        background:#f1f5f9; color:var(--ink); line-height:1.6; }
  .hero{ position:relative; height:220px; background:#0b1a2b url("__HERO__") center/cover no-repeat; }
  .hero .ov{ position:absolute; inset:0; background:linear-gradient(180deg, rgba(5,12,24,.15), rgba(241,245,249,.15) 75%, #f1f5f9); }
  .wrap{ max-width:820px; margin:-70px auto 48px; padding:0 20px; position:relative; z-index:2; }
  .card{ background:#fff; border:1px solid var(--line); border-radius:18px;
         box-shadow:0 14px 40px rgba(15,23,42,.10); padding:30px 30px 24px; text-align:center; }
  .logo{ width:320px; max-width:78%; margin:0 auto 16px; display:block; }
  .ver{ font-size:13px; color:var(--soft); margin:0 0 12px; }
  .tag{ font-size:19px; font-weight:700; color:var(--dark); margin:6px 0 4px; }
  .sub{ font-size:13px; color:var(--cyan); margin:0 0 16px; letter-spacing:.3px; }
  .chips{ display:flex; flex-wrap:wrap; gap:8px; justify-content:center; margin:6px 0 4px; }
  .chip{ font-size:12px; color:#0E7490; background:#ecfeff; border:1px solid #cffafe;
         padding:4px 12px; border-radius:999px; }
  hr{ border:none; border-top:1px solid var(--line); margin:22px 0; }
  h2{ font-size:14px; color:var(--slate); font-weight:600; text-transform:uppercase;
      letter-spacing:1.5px; margin:0 0 12px; text-align:center; }
  .assets{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; margin-top:8px; }
  .asset{ background:#f8fafc; border:1px solid var(--line); border-radius:12px; padding:14px; text-align:center; }
  .asset img{ max-width:100%; display:block; margin:0 auto 8px; border-radius:10px; }
  .asset .name{ font-size:11px; color:var(--soft); }
  .icon-row{ display:flex; gap:20px; align-items:center; justify-content:center; }
  .icon-row img{ border-radius:14px; }
  .family{ display:grid; grid-template-columns:repeat(3,1fr); gap:14px; text-align:left; }
  .fcard{ background:#f8fafc; border:1px solid var(--line); border-radius:12px; padding:16px 18px; }
  .fcard b{ color:var(--dark); }
  .fcard .d{ font-size:13px; color:#334155; margin:4px 0; }
  .fcard .f{ font-size:12px; color:var(--soft); }
  .fcard.self{ border:2px solid var(--cyan); background:#f0fdff; }
  .badge{ display:inline-block; font-size:11px; color:#0E7490; background:#cffafe;
          border-radius:999px; padding:2px 10px; margin-top:8px; }
  .foot{ text-align:center; font-size:12px; color:var(--soft); margin-top:18px; }
  .foot a{ color:var(--blue); text-decoration:none; }
  .splashbox{ background:#0b1a2b; border-radius:14px; padding:14px; display:inline-block; }
  .splashbox img{ display:block; border-radius:8px; }
  @media (max-width:720px){ .family{ grid-template-columns:1fr; } .wrap{ margin-top:-40px; } }
</style>
</head>
<body>
  <div class="hero"><div class="ov"></div></div>

  <div class="wrap">
    <div class="card">
      <img class="logo" src="__LOGO__" alt="PolyXRD RutAna">
      <p class="ver">版本 v__VERSION__</p>
      <p class="tag">GB/T 30793—2014 锐钛型/金红石型比率测定工具</p>
      <p class="sub">强度比值法 A · Rietveld 全谱拟合 B · 标准合规判定</p>
      <div class="chips">
        <span class="chip">强度比值法 A</span>
        <span class="chip">Rietveld 全谱拟合 B</span>
        <span class="chip">GB/T 30793—2014</span>
      </div>

      <hr>
      <h2>品牌资产</h2>
      <div class="assets">
        <div class="asset">
          <div class="icon-row">
            <img src="__ICON__" width="72" height="72" alt="app icon">
            <img src="__MARK__" width="56" height="56" alt="crystal mark">
          </div>
          <div class="name">应用图标 · 家族符号</div>
        </div>
        <div class="asset">
          <div class="splashbox"><img src="__SPLASH__" width="330" alt="splash"></div>
          <div class="name">启动图 480×270</div>
        </div>
      </div>

      <hr>
      <h2>PolyXRD 家族</h2>
      <div class="family">
        <div class="fcard">
          <b>PolyXRD</b>
          <div class="d">X 射线衍射仪数据分析软件</div>
          <div class="f">物相识别 · 峰拟合 · Rietveld 精修 · 离线数据库</div>
        </div>
        <div class="fcard">
          <b>PolyXRD Converter</b>
          <div class="d">XRD 谱图格式互转工具</div>
          <div class="f">多厂商二进制 RAW 解析 · xy/txt/dat/csv/xrdml 互转</div>
        </div>
        <div class="fcard self">
          <b>PolyXRD RutAna</b>
          <div class="d">锐钛型/金红石型晶型比率测定工具</div>
          <div class="f">A 法强度比值 · B 法 Rietveld 全谱拟合 · 双平行判定</div>
          <span class="badge">GB/T 30793—2014 晶型比率专用</span>
        </div>
      </div>

      <div class="foot">
        PolyXRD Team · 2026 &nbsp;·&nbsp;
        <a href="mailto:sshztx@outlook.com">sshztx@outlook.com</a> &nbsp;·&nbsp;
        <a href="https://github.com/PolyXRD">github.com/PolyXRD</a><br>
        © 2026 PolyXRD Team · 版权所有
      </div>
    </div>
  </div>
</body>
</html>
"""


def build() -> None:
    """渲染模板并写出自包含 docs/about.html。"""
    html = (TEMPLATE
            .replace("__HERO__", data_uri("hero-banner.png"))
            .replace("__LOGO__", data_uri("logo-horizontal.png"))
            .replace("__ICON__", data_uri("app-icon.png"))
            .replace("__MARK__", data_uri("crystal-mark.png"))
            .replace("__SPLASH__", data_uri("splash-screen.png"))
            .replace("__VERSION__", __version__))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(html, encoding="utf-8")
    print(f"[about] wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    build()
