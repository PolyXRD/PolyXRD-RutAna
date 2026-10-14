"""HTML 报告生成（自包含：图片 base64 内嵌，浏览器直接打开/打印）。

报告字段对齐 GB/T 30793—2014 试验报告要求：样品信息 / 测定条件 / 结果 /
判定，附谱图 PNG 与标准依据说明。文案经 i18n 三语。
"""

from __future__ import annotations

import base64
import datetime
import html
from typing import Sequence

from rutana.i18n import tr
from rutana.version import APP_NAME, __version__

_STYLE = """
  body{ font-family:"Segoe UI","Microsoft YaHei",system-ui,sans-serif;
        color:#1e293b; background:#f1f5f9; margin:0; line-height:1.6; }
  .page{ max-width:760px; margin:24px auto; background:#fff; border:1px solid #e2e8f0;
         border-radius:14px; padding:28px 32px; box-shadow:0 8px 28px rgba(15,23,42,.08); }
  h1{ font-size:20px; color:#0F172A; margin:0 0 4px; }
  .meta{ font-size:12px; color:#64748B; margin-bottom:16px; }
  h2{ font-size:13px; color:#0284C7; text-transform:uppercase;
      letter-spacing:1px; border-bottom:1px solid #e2e8f0; padding-bottom:4px; }
  table{ width:100%; border-collapse:collapse; font-size:13px; }
  td{ padding:4px 6px; border-bottom:1px solid #f1f5f9; }
  td.k{ color:#64748B; width:38%; }
  td.v{ font-weight:600; text-align:right; }
  .verdict{ font-size:15px; font-weight:700; color:#0284C7; }
  img{ max-width:100%; border:1px solid #e2e8f0; border-radius:8px; margin-top:8px; }
  .foot{ font-size:11px; color:#94A3B8; margin-top:18px; text-align:center; }
"""


def build_html_report(*, sample: str, file_name: str,
                      rows: Sequence[tuple[str, str]],
                      verdict: str, png_b64: str) -> str:
    """构建自包含 HTML 报告。

    参数
    ----
    sample    样品名（默认取谱图文件名主干）。
    file_name 谱图文件路径或名称。
    rows      (标签, 值) 行列表，标签须已本地化。
    verdict   判定文字（已本地化）。
    png_b64   谱图 PNG 的 base64（可为空串，缺图时不渲染 img）。
    """
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row_html = "".join(
        f"<tr><td class='k'>{html.escape(k)}</td>"
        f"<td class='v'>{html.escape(v)}</td></tr>"
        for k, v in rows
    )
    img_html = f"<img src='data:image/png;base64,{png_b64}' alt='pattern'>" if png_b64 else ""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{html.escape(tr('report.title'))} · {html.escape(sample)}</title>
<style>{_STYLE}</style>
</head>
<body>
  <div class="page">
    <h1>{html.escape(tr('report.title'))}</h1>
    <div class="meta">{html.escape(APP_NAME)} v{__version__} ·
      {html.escape(tr('report.generated', ts=now))}</div>

    <h2>{html.escape(tr('report.sample'))}</h2>
    <table>
      <tr><td class="k">{html.escape(tr('report.sample'))}</td>
          <td class="v">{html.escape(sample)}</td></tr>
      <tr><td class="k">{html.escape(tr('report.file'))}</td>
          <td class="v">{html.escape(file_name)}</td></tr>
    </table>

    <h2>{html.escape(tr('report.results'))}</h2>
    <table>{row_html}</table>

    <h2>{html.escape(tr('report.verdict'))}</h2>
    <p class="verdict">{html.escape(verdict)}</p>

    {img_html}

    <div class="foot">{html.escape(tr('report.standard'))}<br>
      © 2026 PolyXRD Team</div>
  </div>
</body>
</html>
"""
