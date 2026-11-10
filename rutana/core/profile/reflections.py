"""带 (hkl) 标注的衍射反射枚举（主峰参数表用）。

为什么单独一份枚举
------------------
拟合热路径走 :func:`rutana.core.profile.struct.compute_peaks`：为了速度，它把
同位置的 Kα 双线与简并反射按 2θ 合并成 ``(2θ, |F|²·LP, d)``，**丢弃了晶面
指数**。而「主峰参数」表要显示 (hkl)，所以这里提供同口径的明细版本：

- 散射因子 / 结构因子 / Lorentz-Polarization / Kα 权重与 ``compute_peaks``
  逐式一致（同一份 Cromer-Mann 表、同一个 41.78214·s² 修正、同一个 LP 式）；
- 合并同位置反射时保留**贡献最大**的那条 hkl（四方晶系里 (hkl) 与 (khl)
  简并时取枚举顺序上的第一条），其余计入强度总和；
- 不含择优取向（主峰表只描述结构本身，PO 属于样品/制样效应）。

交叉校验见 ``tests/test_phasepeak.py``：同一谱上本函数的 (2θ, 强度) 与
``compute_peaks`` 在容差内一致，避免两份实现漂移。
"""

from __future__ import annotations

import math

import numpy as np

from rutana.core.profile.cif import ATOMIC_SCATTERING, ATOMIC_Z, CifStructure
from rutana.core.profile.struct import TWO_THETA_TOL, reciprocal_basis

#: 反射枚举时的 2θ 缺省窗口（度），与 struct.DEFAULT_TWO_MIN/MAX 同口径
DEFAULT_TWO_MIN = 5.0
DEFAULT_TWO_MAX = 90.0


def _hkl_rank(hkl: tuple[int, int, int]) -> tuple:
    """同一 d 值上多个等价指数时的显示优先级（越小越优先）。

    四方/立方晶系里 (hkl)、(khl) 与各种符号组合的 d 完全相同，|F|² 也相同，
    卡片惯例是「l 取正、h/k 取大」（如锐钛 101 而不是 01-1、金红石 110 而不是
    1-10）。这里用一个小排序键把这个惯例固化下来，强度并列时按它选。
    """
    h, k, l = hkl
    return (0 if l >= 0 else 1, -(abs(h) + abs(k)), -max(h, k), -min(h, k), l)


def compute_reflections(struct: CifStructure, wavelength: float = 1.540598,
                        two_min: float = DEFAULT_TWO_MIN,
                        two_max: float = DEFAULT_TWO_MAX,
                        wavelengths=None
                        ) -> list[tuple[float, float, float, tuple[int, int, int]]]:
    """枚举结构在给定窗口内的衍射反射（带晶面指数）。

    返回 ``[(two_theta, d, intensity, (h, k, l)), ...]``（按 2θ 升序）：

    - ``two_theta``：该 hkl 的布拉格角（度，未加零点偏移）；
    - ``d``：晶面间距 (Å)；
    - ``intensity``：``|F|²·LP·Kα权重``（任意单位，与 ``compute_peaks`` 同口径，
      同一 2θ 位置的简并反射已求和）；
    - ``(h, k, l)``：该位置贡献最大的反射指数。

    ``wavelengths`` 为 ``resolve_wavelengths()`` 的结果；None 表示单色光
    （只取 ``wavelength``）。
    """
    a, b, c, al, be, ga = struct.cell
    ast, bst, cst = reciprocal_basis(a, b, c, al, be, ga)

    # ---- 每原子散射参数（与 struct.compute_peaks 同序拉平）----
    zs, a1, a2, a3, a4, b1, b2, b3, b4 = [], [], [], [], [], [], [], [], []
    xs, ys, zs_, occs, Bs = [], [], [], [], []
    skipped: list[str] = []
    for (elem, x, y, z, occ, B) in struct.atoms:
        coeff = ATOMIC_SCATTERING.get(elem)
        if coeff is None or elem not in ATOMIC_Z:
            skipped.append(elem)
            continue
        zs.append(ATOMIC_Z[elem])
        a1.append(coeff[0][0]); a2.append(coeff[1][0])
        a3.append(coeff[2][0]); a4.append(coeff[3][0])
        b1.append(coeff[0][1]); b2.append(coeff[1][1])
        b3.append(coeff[2][1]); b4.append(coeff[3][1])
        xs.append(x); ys.append(y); zs_.append(z)
        occs.append(occ); Bs.append(B)
    if not zs:
        raise ValueError(f"无可用散射因子: {struct.name} (跳过 {skipped})")

    Z = np.array(zs, float)
    A = np.array([a1, a2, a3, a4], float)
    Bc = np.array([b1, b2, b3, b4], float)
    X = np.array([xs, ys, zs_], float)
    OCC = np.array(occs, float)
    BW = np.array(Bs, float)
    f_ref_sq = float(np.sum(Z * OCC)) ** 2
    tol_i = max(f_ref_sq * 1e-9, 1e-300)

    comps = wavelengths if wavelengths is not None else [(float(wavelength), 1.0)]
    max_g = 2 * math.sin(math.radians(two_max / 2)) / min(w for w, _ in comps)
    min_g = 2 * math.sin(math.radians(two_min / 2)) / max(w for w, _ in comps)
    min_recip = min(np.linalg.norm(ast), np.linalg.norm(bst), np.linalg.norm(cst))
    H = max(math.ceil(max_g / min_recip) + 2, 6)

    #: key -> [2θ, 强度合计, d, 最强 hkl, 该 hkl 的强度, 该 hkl 的显示优先级]
    bucket: dict[int, list] = {}
    for h in range(-H, H + 1):
        for k in range(-H, H + 1):
            for l in range(-H, H + 1):
                if h == 0 and k == 0 and l == 0:
                    continue
                # 只枚举规范半空间（h>0，或 h=0 时 k>0，或 h=k=0 时 l>0）：
                # (hkl) 与 (-h,-k,-l) 是同一族衍射面的 Friedel 对，强度相同，
                # 取半空间既避免重复计数，也让表里的指数是惯用的正指数写法。
                if not (h > 0 or (h == 0 and (k > 0 or (k == 0 and l > 0)))):
                    continue
                rlv = h * ast + k * bst + l * cst
                g = math.sqrt(float(rlv @ rlv))
                if g < min_g - 1e-9 or g > max_g + 1e-9:
                    continue
                s2 = (g / 2.0) ** 2
                fs = Z - 41.78214 * s2 * np.sum(A * np.exp(-Bc * s2), axis=0)
                g_dot_r = h * X[0] + k * X[1] + l * X[2]
                phase = np.exp(2j * math.pi * g_dot_r) * np.exp(-BW * s2)
                F = np.sum(fs * OCC * phase)
                i_hkl = F.real ** 2 + F.imag ** 2
                if i_hkl <= tol_i:
                    continue
                for wl, wgt in comps:
                    s_arg = wl * g / 2
                    if s_arg >= 1.0:
                        continue
                    theta = math.asin(s_arg)
                    two_theta = math.degrees(2 * theta)
                    if two_theta < two_min - 1e-9 or two_theta > two_max + 1e-9:
                        continue
                    lp = (1 + math.cos(2 * theta) ** 2) / (
                        math.sin(theta) ** 2 * math.cos(theta))
                    val = i_hkl * lp * wgt
                    if val <= 0:
                        continue
                    key = round(two_theta / TWO_THETA_TOL)
                    entry = bucket.get(key)
                    if entry is None:
                        bucket[key] = [two_theta, val, 1.0 / g, (h, k, l), val,
                                       _hkl_rank((h, k, l))]
                        continue
                    entry[1] += val
                    # 强度并列时用显示优先级打破平局（d 相同的等价指数）
                    if (val > entry[4] + 1e-12 or (
                            abs(val - entry[4]) <= 1e-12 * max(abs(val), 1.0)
                            and _hkl_rank((h, k, l)) < entry[5])):
                        entry[3] = (h, k, l)
                        entry[4] = val
                        entry[5] = _hkl_rank((h, k, l))

    out = [(e[0], e[2], e[1], e[3]) for e in bucket.values()]
    out.sort(key=lambda t: t[0])
    return out
