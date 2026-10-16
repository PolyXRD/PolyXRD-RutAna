# PolyXRD RutAna

**GB/T 30793—2014《X-射线衍射法测定二氧化钛颜料中锐钛型与金红石型比率》专用测定工具。**

PolyXRD 家族成员：PolyXRD（数据分析）· PolyXRD-Converter（格式转换）·
PolyXRD-SynthPattern（谱图合成）· PolyXRD-CifCalc（CIF 工具）· **RutAna（本项目，晶型比率测定）**。

## 这是什么

RutAna 只做一件事：按 GB/T 30793—2014 给出合规、可复现、可出报告的
锐钛型/金红石型比率测定。

- **A 法（强度比值法）**：测锐钛型 (101) 25.30° 与金红石型 (110) 27.44°（Cu Kα）
  净峰强度，`w_a = 1/(1 + K·I_r/I_a) × 100%`；K 由 ≥3 个标准混合点
  多点标定（默认过原点最小二乘，`K = Σxy/Σx²`），R² < 0.995 报警。
- **B 法（Rietveld 全谱拟合法）**：5–90° 全谱拟合（变量投影：scale+Chebyshev 背景
  线性解析，zero/U,V,W/η 非线性 LM），内置锐钛型/金红石型 CIF
  （COD 7206075 / 9001681），Hill–Howard 定量 `W_p ∝ S·Z·M·V`，
  合格判据 **Rwp ≤ 10%**。虚拟样 round-trip：Rwp 2.1–3.5%，回收误差 ≤0.09pp。
- **B 法择优取向（March–Dollase）精修**（v1.4.0，默认开启）：按
  `W = (r²cos²α + r⁻¹sin²α)^(−3/2)` 精修每相择优取向参数 r（锐钛默认
  择优面 (001)、金红石 (110)，边界 0.2–5.0；r=1 为无择优）。峰枚举缓存
  键不含 r、前向时按明细廉价重加权，单样本耗时与关闭版同量级；四样真实
  数据实证 Rwp 不劣化、定量最差相对误差 2.85%（见
  docs/VALIDATION_v1.0.0.md §v1.4.0）。
- **启动画面**（v1.4.0）：PyInstaller bootloader splash —— onefile 解压
  阶段（冷启动数秒）即显示品牌启动图，主窗口就绪后自动关闭，解决
  exe 冷启动 >6s 无窗口问题。
- 结果为**两晶相相对比率**，不含无定形包膜（TiO₂ 颜料的 Al/Si/Zr 包膜不在结果内）。

核心模块：`rutana/core/`（patterns 读取 · background 背景 · peakmeasure 净峰 ·
method_a K 标定与结果 · smooth 可选平滑 · plot 绘图 · profile/ 前向模型 ·
refine/ 精修引擎与 QPA）；CLI：`rutana/cli/rutana.py`；
GUI（PySide6，中/英/日）：`rutana/gui/`；
虚拟实验室与基准：`tools/gen_virtual.py`、`tools/bench.py`、`tools/bench_b.py`。

### CLI 用法

```bash
# 已知 K 值
D:/Project/XRD/python310/python.exe -m rutana.cli.rutana a-method \
    --sample tests/data/virtual/v50.xy --K 1.0 --json out.json

# 由 3 个标定混合物现场标定（文件:质量比）
D:/Project/XRD/python310/python.exe -m rutana.cli.rutana a-method \
    --sample sample.xy --calib c25.xy:0.3333 c50.xy:1.0 c75.xy:3.0 \
    --repeat sample_2nd.xy --json out.json --png spectrum.png
```

### GUI 启动

```bash
D:/Project/XRD/python310/python.exe -m rutana.gui
```

## 版次与注册（v1.5.0）

RutAna 有两个版次，构建期定版（`rutana/edition.py`），运行期只读：

| | 注册版（Setup 安装包） | 内部评估版（单文件 exe） |
|---|---|---|
| 产物 | `PolyXRD-RutAna-vX.Y.Z-Setup.exe` | `PolyXRD-RutAna-vX.Y.Z.exe` |
| 注册机制 | ✅（含 `rutana.gui.registration`） | ❌（spec excludes 彻底排除） |
| 未注册启动 | 每次弹窗：「本软件未注册，版权所有，禁止用于商业用途。如需注册请联系 sshztx@outlook.com」，点「确定」后可正常继续使用，点「输入注册码」注册后不再提示 | — |
| 帮助菜单 | 含「输入注册码 (&R)…」 | 无注册项 |
| 状态栏最右 | 已注册：显示注册的「单位部门名称」；未注册：显示「未注册」 | 显示「内部评估版本」 |

- **注册码**：由开发方根据用户提供的「单位部门名称」生成（离线 HMAC-SHA256，
  与 PolyXRD 家族出码工具互通）。**如需注册请联系 sshztx@outlook.com**，
  告知单位部门名称即可获取注册码；拿到后在软件内「帮助 → 输入注册码」粘贴。
- **开发方出码**：用 PolyXRD-Reg 的 `dist\PolyXRD-RegTool.exe`（界面版）
  或 `make_reg_code.py`（命令行），详见 `D:\Project\XRD\PolyXRD-Reg\README.md`。
- **注册状态文件**：`%APPDATA%\PolyXRD\Registration\PolyXRD_RutAna.json`；
  每次启动重新校验注册码，手改 JSON 伪造「已注册」无效；卸载软件不删除
  该文件，重装后注册仍在。
- 构建：内部评估版 `build_exe.bat`；注册版 `build_setup.bat`
  （PyInstaller onedir + Inno Setup 安装包，可指定安装位置、开始菜单/桌面
  快捷方式、可卸载）。GitHub Release 提供 Setup 安装版。

## 怎么跑 pytest

```bash
cd /d/Project/XRD/PolyXRD-RutAna && D:/Project/XRD/python310/python.exe -m pytest -q
```

依赖锁定见 `requirements.txt`（numpy 2.2.6 / scipy 1.15.3 / matplotlib 3.10.9 /
PySide6 6.11.2 / pytest）。虚拟样基准数据由 `tools/gen_virtual.py` 生成
（seed=20260701，可复现）：

```bash
D:/Project/XRD/python310/python.exe tools/gen_virtual.py --out tests/data/virtual
D:/Project/XRD/python310/python.exe tools/bench.py --method a    # A 法 8 配比 round-trip
D:/Project/XRD/python310/python.exe tools/bench_b.py             # B 法 8 配比 round-trip
```

> **口径注记**：A 法黄金基线 `tests/golden/method_a_roundtrip.json` 由**窄窗谱**
> `v50.xy` 冻结（B 法基线对应 `tests/data/virtual_b/` 宽扫谱）。`v50_wide.xy`
> 的噪声实现不同，结果与窄窗基线允许 ~0.02pp 级差异，逐位比对请用对应谱源。

## 任务进度表

| 卡 | 内容 | 状态 |
|---|---|---|
| T0.1 | 仓库骨架与依赖锁定 | ✅ |
| T0.2 | 标准条款逐字冻结（STD_FREEZE.md） | ✅（重复性限按 §9.1 原文修正为 0.18%） |
| T0.3 | 核心数据类型 dtypes | ✅ |
| T1.1 | 谱读取器 patterns | ✅ |
| T1.2 | 虚拟实验室 gen_virtual | ✅ |
| T1.3 | 谱图绘制 plot | ✅ |
| T2.1–T2.7 | A 法全链（背景/净峰/K 标定/结果/基准/CLI/平滑） | ✅ |
| T3.1–T3.3 | B 法前向模型 + 内置 CIF | ✅ |
| T4.1–T4.6, T4.8 | B 法精修引擎 + QPA + 性能 | ✅ |
| T4.7 | 晶胞/择优取向精修 | ✅（v1.0.0：每相 a,c 缩放精修；v1.4.0：March–Dollase 择优取向 r 精修，默认开） |
| T5.x | 合规判定 / 报告导出 / 台账 | ✅（GUI 导出 HTML/CSV/PNG） |
| T6.x | PySide6 GUI + 三语 i18n + 关于/版权 | ✅ |
| T7.x | QA 两轮回归 + 打包验证 | ✅（实样 L3 交叉验证待实验排期） |

## 许可

双许可（Academic / Commercial），见 `LICENSE` 与 `LICENSE-CN`。
商用联系：sshztx@outlook.com · https://github.com/PolyXRD
