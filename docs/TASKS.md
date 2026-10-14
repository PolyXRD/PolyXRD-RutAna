# PolyXRD-RutAna 原子任务卡（可机读 · 逐步可验收）

> 配套文档：`docs/PROJECT_PLAN.md`
> 执行规则（**必须遵守，否则尤其不能被低成本模型稳定执行**）：
>
> 1. **一次只做一张卡**，完成后再取下一张；卡写「禁止」的事一件不做。
> 2. 每张卡新增代码 **≤ 250 行**；单函数 **≤ 60 行**；单文件 **≤ 400 行**。超了就拆卡。
> 3. **不许改已有函数签名**。确需改动 → 另开一张卡。
> 4. 每张卡末尾的「验收命令」必须**原样执行并全绿**，输出粘贴进任务记录。
> 5. 所有随机过程（合成数据）必须 `seed=20260701`，保证可复现。
> 6. 工作环境固定：`D:/Project/XRD/python310/python.exe`（numpy 2.2.6 / scipy 1.15.3 / PySide6 6.11.2 / matplotlib 3.10.9 / pytest 已就绪）。
> 7. 根目录：`D:/Project/XRD/PolyXRD-RutAna`，包目录 `rutana/`。

---

## P0 · 立项与冻结（0.5 人日）

### T0.1 · 仓库骨架与依赖锁定

- **前置**：无
- **产出文件**：`requirements.txt`、`pytest.ini`、`rutana/__init__.py`、`rutana/version.py`、`tests/conftest.py`、`README.md`
- **契约**：
  ```python
  # rutana/version.py
  __version__: str = "0.1.0"
  ```
- **实现要点**
  1. `requirements.txt` 只写：`numpy==2.2.6`、`scipy==1.15.3`、`matplotlib==3.10.9`、`pytest`（GUI 阶段再加 PySide6）。
  2. `pytest.ini`：`testpaths = tests`、`addopts = -q --strict-markers`。
  3. `tests/conftest.py` 提供一个 fixture：
     ```python
     DATA_DIR = Path(__file__).parent / "data"
     PY = r"D:/Project/XRD/python310/python.exe"
     ```
  4. README 只写「这是什么 / 怎么跑 pytest / 卡 TODO 进度表」三段。
- **验收命令**
  ```
  cd /d/Project/XRD/PolyXRD-RutAna && D:/Project/XRD/python310/python.exe -m pytest -q
  ```
- **完成判据**：pytest 收集到 0 条失败（允许 "no tests ran"）；`python -c "import rutana"` 成功。
- **禁止**：此刻不要写任何算法代码，不要引入 pyside6。

---

### T0.2 · 标准条款逐字冻结 ⚠ 不可跳过

- **前置**：T0.1
- **产出文件**：`docs/STD_FREEZE.md`
- **实现要点**（这是「查资料」任务，不是编码任务）
  1. 打开 PROJECT_PLAN §2.3 的六个待核项 T1–T6，逐条填入 `STD_FREEZE.md`，每条三列：**原文摘录 | 条款号 | 我们软件怎么落地**。
  2. 优先来源：① 正式标准 PDF；② `openstd.samr.gov.cn` 的 GB/T 37054—2018 全文（同源委员会，背景/峰强口径常一致，可作交叉印证）；③ 二手摘要仅作参考，必须标注。
  3. 若某项在可获得的公开文本里查不到 → 写 `UNKNOWN`，并在后续任务清单里列出补齐计划。
- **卡内核验清单**（必须全部有答案）
  - [ ] 重复性限 / 再现性限的确切数值与适用条件
  - [ ] 净峰强度背景取法是否明文
  - [ ] K 是否强制过原点
  - [ ] 试验报告必备字段清单
  - [ ] 附录 A 干扰物清单
- **验收命令**
  ```
  cd /d/Project/XRD/PolyXRD-RutAna && test -f docs/STD_FREEZE.md && wc -l docs/STD_FREEZE.md
  ```
- **完成判据**：文件存在且 6 项全部有结论（哪怕是明确标 `UNKNOWN` + 说明）。
- **禁止**：不得凭猜测填数值；不确定就写 UNKNOWN 并注明出处缺口。

---

### T0.3 · 核心数据类型定义

- **前置**：T0.1
- **产出文件**：`rutana/core/dtypes.py`
- **契约**
  ```python
  @dataclass(frozen=True)
  class Pattern:
      two_theta: np.ndarray      # 1D, float64, 升序
      intensity: np.ndarray      # 1D, float64, 与 two_theta 等长
      meta: dict = field(default_factory=dict)   # {"path","source_format","wavelength_anode"}

  @dataclass(frozen=True)
  class PeakMeasure:
      two_theta_at_max: float
      net_height: float
      net_area: float
      background_at_max: float
      fwhm: float
      snr: float
      ok: bool
      message: str
  ```
- **实现要点**：`__post_init__` 里做三项校验：等长、非空、`two_theta` 严格升序；违反抛 `ValueError`。
- **验收命令**
  ```
  D:/Project/XRD/python310/python.exe -m pytest tests/test_dtypes.py -q
  ```
- **完成判据**：测试覆盖「正常构造 / 长度不等报错 / 非升序报错」3 例并全绿。
- **禁止**：不要在这里做插值、单位换算。

---

## P1 · 数据层 + 虚拟实验室（1.5 人日）★地基

### T1.1 · 谱读取器

- **前置**：T0.3
- **产出文件**：`rutana/core/patterns.py`、`tests/data/fixture_basic.xy`
- **契约**
  ```python
  def load_pattern(path: str | Path) -> Pattern
  def clip(p: Pattern, tmin: float, tmax: float) -> Pattern
  def estimate_step(p: Pattern) -> float          # 中位数步长
  ```
- **实现要点**
  1. 支持两列空白/逗号分隔文本（`.xy .txt .dat .csv`），跳过 `#` / `//` 开头注释行，容忍表头（检测首行是否可 float）。
  2. `.ras`/`.raw`/`.uxd` 等二进制格式 **本卡不做**，遇未知扩展抛 `NotImplementedError("暂不支持的格式: {ext}")`。
  3. **可参考但不能直接依赖**：`D:/Project/XRD/PolyXRD-SynthPattern/xrd_synth_engine.py:825` 的 `load_measured()`（不要 import，照着写）。
  4. `clip` 用布尔掩码切片，不含端外插值。
- **验收命令**
  ```
  D:/Project/XRD/python310/python.exe -m pytest tests/test_patterns.py -q
  ```
- **完成判据**：① 读入 2 列 `xy` 正确；② 带表头 csv 正确；③ 非法行数不匹配报错；④ `clip` 后点数与区间一致（±1 点内）。
- **禁止**：不要 import 任何兄弟项目仓库路径。

---

### T1.2 · ★虚拟实验室（合成数据生成器）

- **前置**：T1.1（需 `Pattern`）
- **产出文件**：`tools/gen_virtual.py`、`tests/data/virtual/manifest.json`
- **契约**
  ```python
  def generate_mixture(wa_percent: float, *, seed: int, profile: dict) -> tuple[Pattern, dict]
  # profile: {"tmin":5.0,"tmax":90.0,"step":0.02,"U":..,"V":..,"W":..,"eta":..,
  #           "zero":..,"anode":"Cu","ka_ratio":0.5,"po_hkl":(1,0,1),"po_r":..,
  #           "size_nm":..,"noise_rel":..,"target_peak":50000}
  # 返回第二个 dict 为 truth: {"wa_nominal":float,"wr_nominal":float,"profile":{...}}
  ```
- **实现要点**
  1. **直接调用** `D:/Project/XRD/PolyXRD-SynthPattern/xrd_synth_engine.py` 的 `synthesize_multi_phase()` 出谱（该任务是离线生成，允许把兄弟目录加到 `sys.path`，**仅限本 tools 脚本**）。
  2. 内置锐钛型/金红石型 CIF **本卡先用临时占位**：目录下放两个最小 CIF（晶格参数写标准值、原子坐标手工列出即可），T3.1 再换成正式来源。
     - 锐钛型 `I41/amd` a=3.7845 c=9.5143，Ti (0,0,0)... 见 T3.1
     - 金红石型 `P42/mnm` a=4.5937 c=2.9587
  3. 生成 8 个配比：`[0.1, 1, 5, 25, 50, 75, 95, 99]`，固定 seed，写入 `tests/data/virtual/vNN.xy` + `truth.json`。
  4. 同时生成 **A 法专用窄窗谱**（24.5–28.5°，不含.B 法宽扫噪声）与 **B 法宽扫谱**（5–90°）两套。
- **验收命令**
  ```
  cd /d/Project/XRD/PolyXRD-RutAna && D:/Project/XRD/python310/python.exe tools/gen_virtual.py --out tests/data/virtual
  ```
- **完成判据**：目录下出现 16 个 `.xy` + `manifest.json`；**人眼复核**：用 matplotlib 画 `v50.xy`，锐钛型 25.3° 与金红石型 27.4° 两峰清晰、位置误差 < 0.05°。
- **保存产物**：把这张 PNG 存 `tests/data/virtual/_preview.png`。
- **禁止**：不要在这一步纠结 CIF 精度；占位 CIF 即可，位置正确就放行。

---

### T1.3 · 谱图绘制工具（调试/肉眼验收用）

- **前置**：T1.1
- **产出文件**：`rutana/core/plot.py`
- **契约**
  ```python
  def plot_overlay(pairs: list[tuple[str, Pattern]], title: str, out_png: str | Path) -> None
  def plot_fit(obs: Pattern, calc: Pattern, diff: Pattern, out_png: str | Path) -> None
  ```
- **实现要点**：matplotlib `Agg` 后端（避免 GUI 依赖）；`plot_fit` 用 2:1 子图，上 obs/calc，下 diff。
- **验收命令**
  ```
  D:/Project/XRD/python310/python.exe -m pytest tests/test_plot.py -q
  ```
- **完成判据**：调用后 PNG 文件存在且非空（>5 KB）。

---

## P2 · A 法闭环（2.5 人日）→ **第 4 人日可交付实验室**

### T2.1 · 背景估计

- **前置**：T1.1
- **产出文件**：`rutana/core/background.py`
- **契约**
  ```python
  @dataclass(frozen=True)
  class BgConfig: mode: str = "linear_edges"; edge_frac: float = 0.10; poly_deg: int = 1
  def estimate_background(p: Pattern, cfg: BgConfig) -> np.ndarray
  ```
- **实现要点**
  1. `linear_edges`：取窗口两端各 `edge_frac` 比例点做稳健平均（用中位数抗离群），两点连直线。
  2. `poly`：对两端点拟合 `poly_deg` 次多项式（≥2 阶需至少 4 个边缘点）。
  3. **返回结果必须与输入等长**，允许出现负值背景（不裁剪）。
- **验收命令**
  ```
  D:/Project/XRD/python310/python.exe -m pytest tests/test_background.py -q
  ```
- **完成判据**：对「直线背景 + 单峰」的合成谱，`mode=linear_edges` 估计的背景在峰位处误差 < 1% of 背景真值；常数背景 1000 复现为 1000±1。

---

### T2.2 · 净峰强度测量

- **前置**：T2.1、T1.1
- **产出文件**：`rutana/core/peakmeasure.py`
- **契约**
  ```python
  def measure_peak(p: Pattern, expected: float, tol: float = 0.4,
                   cfg: BgConfig = BgConfig()) -> PeakMeasure
  # expected: 标称峰位(2θ)，如 25.30 / 27.44；tol 为搜索容忍(度)
  ```
- **实现要点**
  1. 在 `[expected-tol, expected+tol]` 内取最大值位置 → `two_theta_at_max`。
  2. `net_height = I_max − B(two_theta_at_max)`。
  3. `net_area = Σ (I_i − B_i) · Δ2θ`，积分范围 = 该仅_SOURCE窗口内（与 T1.2 的窄窗一致）。
  4. `fwhm`：从峰位向两侧找 `I = B + net_height/2` 的线性插值交点。
  5. `snr = net_height / robust_sigma(残差)`；`ok = snr >= 4.0 and 净高>0`；不满足写清楚 `message`。
  6. **不做任何平滑**（平滑留 T2.7，且必须标定/样品两侧对称使用）。
- **验收命令**
  ```
  D:/Project/XRD/python310/python.exe -m pytest tests/test_peakmeasure.py -q
  ```
- **完成判据**：T1.2 生成的 `v50` 谱上，锐钛型峰位测得在 `25.30±0.05`，金红石型在 `27.44±0.05`；两者 `net_height > 0`、`snr > 10`。

---

### T2.3 · A 法 K 值标定

- **前置**：T2.2
- **产出文件**：`rutana/core/method_a.py`
- **契约**
  ```python
  @dataclass(frozen=True)
  class CalibPoint: ma_over_mr: float; ia_over_ir: float
  @dataclass(frozen=True)
  class CalibResult: K: float; intercept: float; r2: float; n_points: int; K_forced0: float
  def calibrate_k(points: list[CalibPoint], force_zero: bool = True) -> CalibResult
  ```
- **实现要点**
  1. `force_zero=True` → `K = Σ x y / Σ x²`；同时**总是**额外算一份带截距 OLS，回填 `intercept` 与 `r2`（用于报警）。
  2. `n_points < 3` → 抛 `ValueError("K 值标定至少需要 3 个标准混合点")`；这是**硬性要求**，不给例外。
  3. `r2 < 0.995` → 结果仍返回，但供上层报警。
- **验收命令**
  ```
  D:/Project/XRD/python310/python.exe -m pytest tests/test_method_a_calib.py -q
  ```
- **完成判据**：输入严格线性数据 `y = 1.234·x`（5 点）→ `K_forced0 == 1.234 ± 1e-6`，`r2 > 0.9999`；输入 2 点 → 抛 `ValueError`。

---

### T2.4 · A 法结果计算

- **前置**：T2.3
- **产出文件**：同 `rutana/core/method_a.py`（增量）
- **契约**
  ```python
  @dataclass(frozen=True)
  class RatioResult: wa: float; wr: float; K: float; ia: float; ir: float
  def compute_ratio(ia: float, ir: float, K: float) -> RatioResult
  def combine_duplicates(r1: RatioResult, r2: RatioResult, limit: float) -> dict
  ```
- **实现要点**
  1. `wa = 1/(1 + K*ir/ia) * 100`；`wr = 100 - wa`；`ia<=0 或 ir<0` 抛 ValueError。
  2. `combine_duplicates` 返回：`{"wa_mean","abs_diff","within_limit","limit"}`，`within_limit = abs_diff <= limit`。
  3. **repeatability limit 的默认值从 `STD_FREEZE.md` 取**，本卡先写 `DEFAULT_ABS_LIMIT = 0.15`（并在代码注释标注「待 T0.2 核对」）。
  4. 结果保留两位小数（内部保留全精度，只在报告层四舍五入）。
- **验收命令**
  ```
  D:/Project/XRD/python310/python.exe -m pytest tests/test_method_a_result.py -q
  ```
- **完成判据**：K=1 且 ia=ir → wa=50.000；K=2、ir/ia=1 → wa=33.333±1e-3；双平行 95.10/95.20 → abs_diff=0.10、within_limit=True。

---

### T2.5 · A 法 round-trip 验收 ★（虚拟样闭环）

- **前置**：T1.2、T2.2、T2.3、T2.4
- **产出文件**：`tools/bench.py`、`tests/golden/method_a_roundtrip.json`
- **实现要点**
  1. `bench.py` 全流程：读 `tests/data/virtual/manifest.json` → 对每个配比用 A 法窗口测两峰 → 用 3 个人造标定点（25/50/75%）算 K → 反算 w_a → 与 `truth.json` 比对。
  2. 输出 Markdown 表格到 `stdout` 并写 `bench_report.md`。
  3. 首版生成 `golden/method_a_roundtrip.json` 作为基线**冻结**，后续任何重构不得让偏差变差。
- **验收命令**
  ```
  cd /d/Project/XRD/PolyXRD-RutAna && D:/Project/XRD/python310/python.exe tools/bench.py --method a
  ```
- **完成判据**（8 个配比全部满足）
  - `wa ≥ 95%`：`|Δ| ≤ 0.30` 个百分点
  - `wa < 95%`：`|Δ| ≤ max(0.5 个百分点, 2% 相对)`
  - 若不满足 → **先修点到满足，不许放宽阈值**（唯一例外：0.1% 配比的 SNR 不足，可记录为「检出限外」但需人眼确认谱图确有可见峰）。
- **禁止**：不许用 real data 绕过；不许调 seed。

---

### T2.6 · A 法 CLI

- **前置**：T2.5
- **产出文件**：`rutana/cli/rutana.py`
- **契约**（argparse 子命令）
  ```
  rutana a-method --sample S.xy [--K <float>] [--calib c1.xy:0.25 c2.xy:1.0 c3.xy:4.0]
                  [--repeat S2.xy] [--json out.json] [--png out.png]
  ```
- **实现要点**：`--K` 与 `--calib` 互斥且必须给其一；`--calib` 参数格式 `path:ma_over_mr`。输出人类可读表格 + 可选 JSON。
- **验收命令**
  ```
  cd /d/Project/XRD/PolyXRD-RutAna &&
  D:/Project/XRD/python310/python.exe -m rutana.cli.rutana a-method \
      --sample tests/data/virtual/v50_wide.xy --K 1.0 --json /tmp/a50.json
  ```
- **完成判据**：退出码 0；`/tmp/a50.json` 含 `wa/wr/K/ia/ir` 键；与 T2.5 同谱结果一致（±1e-6）。

---

### T2.7 · 可选平滑与 QA 输出（最后再做）

- **前置**：T2.6（**必须放最后**，避免影响已冻结的 golden）
- **产出文件**：`rutana/core/smooth.py`，增量改 `peakmeasure.py`
- **契约**
  ```python
  @dataclass(frozen=True)
  class SmoothConfig: enabled: bool = False; window: int = 5; polyorder: int = 2
  def savitzky_golay(y: np.ndarray, cfg: SmoothConfig) -> np.ndarray
  ```
- **实现要点**：默认 `enabled=False`。**平滑参数必须写进工程存档 JSON**，标定与样品必须同参。
- **验收命令**：`python -m pytest tests/test_smooth.py -q && python tools/bench.py --method a`
- **完成判据**：① 默认关闭时 bench 结果与 T2.5 冻结基线**逐点一致**；② 开启后 SNR 提升、峰位漂移 < 0.01°。

---

## P3 · B 法前向模型（1 人日）

### T3.1 · 内置 CIF 选取与落库

- **前置**：无（可与 P2 并行）
- **产出文件**：`rutana/data/anatase.cif`、`rutana/data/rutile.cif`、`docs/CIF_SOURCE.md`
- **实现要点**
  1. 从本地 `D:/Project/XRD/PolyXRD/cod_data/COD_inorganics.sqlite` 取 CIF（`phases.cif_gz` 列是 gzip 内联的原 CIF，`zlib.decompress` 即得）。
     - 候选（已查到）：锐钛型 `I 41/a m d`：5000223 / 7206075 / 1530151；金红石型 `P 42/m n m`：4102355 / 9001681 / 1530150。
  2. **择优判据**：用 `PDF2_2004.sqlite` 里对应的 TiO₂ 卡片（锐钛型 21-1272 / 金红石型 21-1276，待核）的 d-I 列表打分，
     选**最强 5 个峰的相对强度偏差 RMS 最小**的那个 COD 条目。
  3. 落盘后在 `docs/CIF_SOURCE.md` 写清 COD ID、晶格参数、来源、选取理由与打分表。
- **验收命令**
  ```
  D:/Project/XRD/python310/python.exe -m pytest tests/test_builtin_cif.py -q
  ```
- **完成判据**：两个 CIF 可被 `parse_cif` 正确解析；计算出的最强 5 线 d 值与 PDF 卡偏差 **< 0.5%**；最强相对强度排序与卡片**一致**。

---

### T3.2 · 计算 profile 层（vendor 纯函数）

- **前置**：T3.1
- **产出文件**：`rutana/core/profile/{cif.py,struct.py,shape.py,forward.py}`
- **实现要点**
  1. 从 `xrd_synth_engine.py` **复制**（保留版权声明）以下纯函数到对应文件：
     - `cif.py`: `ATOMIC_SCATTERING`、`ATOMIC_Z`、`parse_symop`、`expand_symmetry`、`parse_cif`、`CifStructure`
     - `struct.py`: `reciprocal_basis`、`compute_peaks`（返回 `(2θ, |F|²·LP, d)`）
     - `shape.py`: `_pv_peak`、`pseudo_voigt_grid`、`caglioti`、`march_dollase_weight`、`resolve_wavelengths`
  2. **新增** `forward.py`（本卡真正的新代码）：
     ```python
     @dataclass(frozen=True)
     class ProfileParams: zero: float=0.0; U: float=0.0; V: float=0.0; W: float=0.02
                          eta: float=0.5; anode: str|None="Cu"; ka_ratio: float=0.5
                          po_r: dict|None=None            # {phase_name: (h,k,l,r)}
     def compute_phase_profile(struct, grid, prm: ProfileParams, tmin, tmax) -> np.ndarray
     ```
     **必须：不做任何归一化、不加背景、不加噪声**，返回任意单位的 phase-only 曲线。
  3. 同仓附带一条对拍测试（可选 skip，环境变量 `RUTANA_HAS_SYNTH=1` 时才跑）：同一 struct/grid/参数下，本实现与 `xrd_synth_engine.pseudo_voigt_grid` 的输出**逐点相对误差 < 1e-9**。
- **验收命令**
  ```
  D:/Project/XRD/python310/python.exe -m pytest tests/test_forward.py -q
  ```
- **完成判据**：① 对拍测试通过；② `compute_phase_profile` 返回的最强峰位置与期望 ±0.02°；③ 输出全为非负且最大值 > 0。

---

### T3.3 · 两相混合合成验证

- **前置**：T3.2、T1.2
- **产出文件**：`tests/test_forward_mix.py`、PNG
- **实现要点**：用已有 T1.2 的虚拟谱做**反向交叉**：把 `forward` 按 truth 配比算出的曲线与 `xrd_synth_engine.synthesize_multi_phase` 的曲线（关闭噪声/背景）做高度相关 comparison。
- **验收命令**：`python -m pytest tests/test_forward_mix.py -q`
- **完成判据**：两者在去除整体标度后（各自除以其最大值）逐点相对偏差 RMS **< 2%**。

---

## P4 · B 法精修引擎（4 人日）★最高风险区

### T4.1 · 线性层：scale + Chebyshev 背景

- **前置**：T3.2
- **产出文件**：`rutana/core/refine/linear.py`
- **契约**
  ```python
  def chebyshev_basis(two_theta: np.ndarray, n_terms: int) -> np.ndarray  # shape (N, n_terms)
  def solve_linear(basis_phases: np.ndarray, grid, yobs: np.ndarray,
                   sigma: np.ndarray|None, n_bg: int = 3
                   ) -> tuple[np.ndarray, np.ndarray]   # (coeffs, ycalc)
  # coeffs = [S_phase1, S_phase2, ..., b_0, b_1, ...]  （相位在前，背景在后）
  ```
- **实现要点**
  1. `x = 2·(2θ − 2θmin)/(2θmax − 2θmin) − 1` 映射到 [−1,1]；`T_0=1, T_1=x, T_{n+1}=2xT_n − T_{n−1}`。
  2. 设计矩阵 `A = [P_1, P_2, ..., bg_cols]`，用 `scipy.linalg.lstsq` 解；可选 `sigma` 加权（左右乘 1/σ）。
  3. **约束**（简单可靠）：解完后若某 `S_p < 0`，把该相移出设计矩阵重解一轮；仍为负则该相 scale 置 0 并在结果里标 `phase_dropped`。
- **验收命令**：`python -m pytest tests/test_linear.py -q`
- **完成判据**：已知 `S=[3.0, 1.0]`、`bg=[500, 0, 0]` 的合成 clean 曲线（**不含噪声**）→ 恢复 `S` 相对误差 < 1e-6；加 1% 高斯噪声后 < 2%。

---

### T4.2 · R 因子

- **前置**：T4.1
- **产出文件**：`rutana/core/refine/rfactors.py`
- **契约**
  ```python
  @dataclass(frozen=True)
  class RFactors: rwp: float; rp: float; rexp: float; chi2: float; rbragg: float|None
  def compute_rfactors(yobs, ycalc, *, n_params, sigma=None, include_bg=True) -> RFactors
  ```
- **实现要点**
  1. `sigma` 缺省按计数统计 `σ=√max(yobs,1)`。
  2. `Rwp = 100·√(Σw(yo−yc)² / Σw·yo²)`；`Rp = 100·Σ|yo−yc| / Σ yo`；`Rexp = √((N−P)/Σw·yo²)`；`χ²=(Rwp/Rexp)²`。
  3. `rbragg` 本卡返回 `None`（需各相积分强度，留到 T4.6）。
  4. 文档注释里明确写「采用 GSAS-II 口径：背景计入」，并把与 FullProf 的口径差异写进 `docs/STD_FREEZE.md`。
- **验收命令**：`python -m pytest tests/test_rfactors.py -q`
- **完成判据**：`ycalc == yobs` → Rwp=0；常数一半 → Rwp=50.0±0.01；分母为 0 时抛 ValueError。

---

### T4.3 · LM 优化器（自写，60 行）

- **前置**：T4.1、T4.2
- **产出文件**：`rutana/core/refine/lm.py`
- **契约**
  ```python
  @dataclass(frozen=True)
  class LMResult: x: np.ndarray; success: bool; n_iter: int; cost: float; message: str
  def lm_minimize(residual_fn, x0: np.ndarray, *, bounds=None, max_iter=60,
                  ftol=1e-8, xtol=1e-8, lambda0=1e-3) -> LMResult
  # residual_fn(x) -> 1D 残差向量；Jacobian 用中心差分，步长 1e-4·max(1,|x|)
  ```
- **实现要点**
  1. 标准 LM：解 `(JᵀJ + λ·diag(JᵀJ))·δ = −Jᵀr`；成功降代价则 `λ/=3`，否则 `λ*=3` 重试。
  2. `bounds` 用**参数裁剪**（每步后 clip），简单可靠，不用投影梯度。
  3. 收敛判据：连续两迭代代价相对改善 < ftol 或 |δ| < xtol 或达 max_iter。
  4. 失败兜底：λ>1e8 时退出，`success=False`，返回当前最优 x 与原因。
- **验收命令**：`python -m pytest tests/test_lm.py -q`
- **完成判据**：① Rosenbrock 函数（2 参数，初值 [−1.2,1]）在 60 代内收敛到 cost < 1e-6；② 线性最小二乘解析可解问题上结果与 `lstsq` 相对差 < 1e-4；③ `max_iter=1` 时确实只迭代 1 次。

---

### T4.4 · 非线性层（变量投影）

- **前置**：T4.1、T4.2、T4.3、T3.2
- **产出文件**：`rutana/core/refine/nonlinear.py`
- **契约**
  ```python
  @dataclass(frozen=True)
  class RefineConfig: refine_zero=True; refine_uvw=True; refine_eta=False
                      n_bg=3; max_iter=40; sigma=None
  @dataclass(frozen=True)
  class RefineResult: params: ProfileParams; scales: np.ndarray; bg: np.ndarray
                      ycalc: np.ndarray; rf: RFactors; success: bool; history: list[float]
  def refine(phases: list[CifStructure], pat: Pattern, prm0: ProfileParams,
             cfg: RefineConfig) -> RefineResult
  ```
- **实现要点（核心：变量投影）**
  1. `residual_fn(x)`：`x` 只含**非线性参数**（zero, U, V, W[, eta]）；内部：由 x 重建 grids → `compute_phase_profile` → 调 `solve_linear` 解析出 scale 与背景 → 返回加权残差。
  2. 初始基线：先跑一次 `solve_linear`（x=x0）得到初值代价，作为 LM 起点。
  3. 边界：`zero ∈ [−0.5, 0.5]`、`U,V,W ∈ [0, 5]`、`eta ∈ [0.05, 1]`。**W 必须 ≥ 1e-4**，防止 FWHM 退化成 0 导致除零。
  4. `history` 记录每次迭代的 Rwp，用于画收敛曲线。
- **验收命令**：`python -m pytest tests/test_refine_basic.py -q`
- **完成判据**：用 T1.2 的 `v50_wide`（5–90°）做评测，**不释放 eta**（`refine_eta=False`）：
  - 收敛成功（`success=True`）
  - **Rwp ≤ 10%**（首次可能不达标，允许调 default `n_bg` 至 4–5，**不许调数据或 seed**）
  - 两条历史曲线输出到 `tests/out/refine_v50.png`

---

### T4.5 · QPA 定量换算 ★酸检卡

- **前置**：T4.4
- **产出文件**：`rutana/core/refine/qpa.py`
- **契约**
  ```python
  @dataclass(frozen=True)
  class PhaseWeight: name: str; scale: float; Z: int; volume: float; mass: float; weight: float
  def qpa_weights(weights: list[tuple[str,float,int,float,float]]) -> list[PhaseWeight]
  # tuple = (name, scale, Z(晶胞内formula数), cell_volume, formula_mass)
  def to_ratio(ws: list[PhaseWeight], i_anatase: int, i_rutile: int) -> tuple[float,float]
  ```
- **实现要点**
  1. `weight_p = S_p·Z_p·V_p·M_p / Σ_q S_q Z_q V_q M_q`，并归一化使 Σ=1。
  2. `Z` / `V` / `M` 从 CIF 解析：锐钛型 I41/amd **Z=4**、V≈136.3 Å³；金红石型 P42/mnm **Z=2**、V≈62.42 Å³；M(TiO₂)=79.87。
  3. `Z` 从 `_symmetry_cell_Z`? 不可靠时按「空间群一般/特殊位置多重度 × 原子数」**由 CIF 原子数 + 空间群多重度反算**，并在测试里断言结果等于 4 / 2。
- **★酸检（必须写成测试）**
  ```
  S_锐 = S_金 = 1.0  →  w_锐 应 = 4·136.3/(4·136.3 + 2·62.42) ≈ 0.8137 → 81.37%
  S_锐/S_金 = 1/4.368  →  w_锐 ≈ 50.00%
  ```
- **验收命令**：`python -m pytest tests/test_qpa.py -q`
- **完成判据**：酸检两式通过（±0.01 个百分点）；scale 全零时抛 ValueError；Z 反算结果等于 4 与 2。

---

### T4.6 · B 法 round-trip 验收 ★

- **前置**：T4.4、T4.5
- **产出文件**：扩充 `tools/bench.py` --method b、`tests/golden/method_b_roundtrip.json`
- **验收命令**
  ```
  cd /d/Project/XRD/PolyXRD-RutAna && D:/Project/XRD/python310/python.exe tools/bench.py --method b
  ```
- **完成判据**（8 个配比）
  - 全部配比 **Rwp ≤ 10%**（这是标准硬条款）
  - `wa ≥ 95%`：`|Δ| ≤ 0.30` 个百分点；`wa < 95%`：`|Δ| ≤ max(0.5 个百分点, 2% 相对)`
  - 输出 `bench_report_b.md` 与每个配比的拟合图 PNG
- **失败处理顺序**：① 检查是否有 `Z` 或 `V` 单位错；② 提高背景项数；③ 检查临界零偏是否被 `zero` 吸收；④ **最后**才考虑放 `eta`。每一步都要在 `docs/DEBUG_LOG.md` 记一笔。

---

### T4.7 · 可选：晶胞/择优/高级参数（本卡属 v1.1，**v1 可跳过**）

- **前置**：T4.6 全绿
- **产出文件**：扩展 `ProfileParams`（`cell_a`、`cell_c` per phase、`po_r`）
- **实现要点**：晶胞变了要重算 `compute_peaks`（每次迭代重算，注意性能）；择优取向用已有 `march_dollase_weight`。
- **完成判据**：引入后 `bench.py --method b` 结果**不比 T4.6 冻结基线差**。

---

### T4.8 · 性能与健壮性

- **前置**：T4.6
- **产出文件**：`forward.py` 增量、`tests/test_perf.py`
- **实现要点**：每个峰只在其 `±(8·FWHM + 0.05°)` 的窗口内计算（替代全网格向量化），并做 naive 与 windowed 的一致性测试。
- **完成判据**：单次前向耗时 < 20 ms（4250 点、两物相）；一次完整精修（≤40 代）< 15 s；windowed 与全网格逐点偏差 RMS < 1e-6·max。

---

## P5–P7 · 合规、报告、GUI、交付（3.5–6 人日）

> 以下阶段建议等 P2/P4 稳定后再开卡细化；先列出卡片边界，避免过早设计。

| 卡 | 内容 | 完成判据 |
|---|---|---|
| T5.1 | `compliance.py`：Rwp≤10%、双平行重复限、有效位数、QA 汇总 | 每条对应一份「合规/不合规/降级」判定，单测覆盖三态 |
| T5.2 | 工程存档 JSON（含全部方法参数）+ SQLite 台账 | 同一工程重开结果**逐位复现** |
| T5.3 | HTML 报告模板（按 `STD_FREEZE.md` 字段清单）+ CSV + PNG | 浏览器打开打印预览无缺字段；`wa+wr=100.00` 恒等 |
| T6.1 | GUI 主窗口、项目管理、参数持久化 | 打开→导入→出结果三击可达 |
| T6.2 | A 法面板（窗口参数、K 标定表、结果卡） | 与 CLI 结果一致（±1e-6） |
| T6.3 | B 法面板（相清单、精修开关、残差图、R 因子） | 与 CLI 一致；精修失败有降级提示而非崩溃 |
| T6.4 | 导出/设置/关于 | 报告、CSV、PNG 三导出可用 |
| T7.1 | 基准集（≥60 条虚拟样）持续回归 | 全绿且 `bench_report.md` 自动生成 |
| T7.2 | 实样 L3 交叉（A vs B vs GSAS-II） | A/B ≤1%abs；与 GSAS-II ≤1.5%abs |
| T7.3 | PyInstaller 打包 + 冒烟 | 干净机器上 exe 可启动并完成一次 A 法流程 |
| T7.4 | 用户手册 + 实验室作业指导书 | 覆盖制样、扫描条件、K 标定周期、干扰物处理 |

---

## 附：任务卡模板（新开卡请用这个格式）

```
### T<stage>.<n> · <动词短语>
- **前置**：<卡 ID 列表>
- **产出文件**：<确切路径>
- **契约**：```python <函数签名 + 返回类型 + 抛什么异常> ```
- **实现要点**：<编号步骤，含公式、参考文件行号、边界值>
- **验收命令**：<一条可直接复制的命令>
- **完成判据**：<带数字的判据，能被自动化判定>
- **禁止**：<本卡不许碰的东西>
```
