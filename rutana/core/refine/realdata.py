"""真实数据推荐配置（v1.0.0）—— 由岛津 XRD-019 数据集实证标定。

背景：v0.1.0 的默认精修配置面向合成数据（Chebyshev 背景、无不对称/无高角
衰减、晶胞固定）。在真实粉末谱（20–120°、石墨单色器、压片装样）上实测，
以下配置把 Rwp 从 ~10.6% 压到 9.3–9.7%，定量误差 ≤0.3pp：
  - tent 背景 80 节点（大弯背景）
  - 低角不对称尾 asym≈0.05、经验高角衰减 B≈0.2
  - 每相晶胞 a,c 缩放精修（T4.7，实测 |Δ|<0.07%，主要吸收零偏残差）
  - Kα2 无需释放（石墨单色器，kr 稳在 0.5）
  - 积分强度口径（ProfileParams.integrated=True，Hill–Howard 标准要求）

v1.0.0 后期决定性修复：Caglioti 角度口径改为 tanθ（forward.caglioti_2theta），
Rwp 进一步 10.97% → 9.31–9.75%，定量最差相对误差 3.61% → 2.62%，
实证与决策记录见 docs/VALIDATION_v1.0.0.md §B。

v1.4.0：新增 refine_po=True（March–Dollase 择优取向 r 精修）。四样实证
Rwp 不劣化（最大 +0.00pp）、定量最差相对误差 2.85%（≤3% 判据），精修出的
r≈1.005–1.017 表明该数据集无明显择优取向——开关注释成本为零，默认开启；
对照表见 docs/VALIDATION_v1.0.0.md §v1.4.0，实验脚本 tools/diag_po.py。

合成数据基准（bench_b / 黄金基线）继续用默认配置（cheb + 无扩展项，
refine_po=False），保证虚拟实验室回归基线不漂移；两套口径的差异记录在
VALIDATION 文档。
"""
from __future__ import annotations

from dataclasses import replace

from rutana.core.profile.forward import ProfileParams
from rutana.core.refine.nonlinear import RefineConfig

# 真实粉末谱（Cu Kα，常规实验室衍射仪）推荐初值
REAL_PROFILE_PARAMS = ProfileParams(
    zero=0.03,
    U=0.036,
    V=-0.040,
    W=0.030,
    eta=0.54,
    anode="Cu",
    ka_ratio=0.5,
    asym=0.048,
    bfactor=0.20,
    integrated=True,
)

# 真实粉末谱推荐精修配置（tent 背景 80 节点 + eta/asym/bfactor/晶胞精修）
# 注意：eta 必须释放（实测收敛 ~0.68，固定 0.54 会差 1.8pp）；V 允许为负
# （实测 -0.04）—— 二者需同时满足，缺一不可，实证见 docs/VALIDATION_v1.0.0.md。
# v1.4.0：refine_po=True（March–Dollase 择优取向 r 精修，四样实证 Rwp 不
# 劣化、定量最差相对误差 2.85% ≤3%，精修出的 r≈1.005–1.017 表明该数据集
# 无明显择优取向；开关注释成本为零，默认开，见 docs/VALIDATION_v1.0.0.md
# §v1.4.0 与 tools/diag_po.py）。
REAL_REFINE_CONFIG = RefineConfig(
    refine_zero=True,
    refine_uvw=True,
    refine_eta=True,
    n_bg=80,
    bg_mode="tent",
    refine_asym=True,
    refine_bfactor=True,
    refine_cell=True,
    refine_po=True,
    tmin=18.0,
    tmax=122.0,
    max_iter=60,
    backend="scipy",   # trf 后端（x_scale="jac"）：关联形状参数上比自写 LM
                       # 稳健。注：v0.1.0 的「U,V→0 角点陷阱」主因是 Caglioti
                       # 的 tan 2θ 语义错误（已修，见 forward.caglioti_2theta），
                       # 修正后 LM 也能收敛，但 trf 仍更快更稳，保留为默认。
)


def real_config(**overrides) -> RefineConfig:
    """以 REAL_REFINE_CONFIG 为底、按 kwargs 覆盖字段的便捷构造。"""
    return replace(REAL_REFINE_CONFIG, **overrides)


def real_params(**overrides) -> ProfileParams:
    """以 REAL_PROFILE_PARAMS 为底、按 kwargs 覆盖字段的便捷构造。"""
    return replace(REAL_PROFILE_PARAMS, **overrides)
