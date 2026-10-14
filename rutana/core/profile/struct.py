"""vendor: 倒易基矢与结构因子计算（T3.2）。

Vendored from PolyXRD-SynthPattern xrd_synth_engine.py — © 2026 PolyXRD Team,
dual-licensed (Academic/Commercial)，家族内复用。
复制范围: reciprocal_basis / compute_peaks（原样，含 po 择优取向与 wavelengths 参数）。
完整倒易点枚举自动包含多重性，|F|² 在全晶胞原子集合上计算。
"""
from __future__ import annotations

import math

import numpy as np

from rutana.core.profile.cif import ATOMIC_SCATTERING, ATOMIC_Z, CifStructure
from rutana.core.profile.shape import march_dollase_weight

# 峰位合并容差(度)
TWO_THETA_TOL = 1e-3
# 与 SynthPattern v1.2.1 一致的缺省扫描窗口
DEFAULT_TWO_MIN = 10.0
DEFAULT_TWO_MAX = 90.0


def reciprocal_basis(a: float, b: float, c: float,
                     al: float, be: float, ga: float):
    """由晶胞参数计算倒易基矢 (a*, b*, c*)，单位 1/Å。"""
    al = math.radians(al); be = math.radians(be); ga = math.radians(ga)
    va = np.array([a, 0.0, 0.0])
    vb = np.array([b * math.cos(ga), b * math.sin(ga), 0.0])
    cx = c * math.cos(be)
    cy = c * (math.cos(al) - math.cos(be) * math.cos(ga)) / math.sin(ga)
    cz = c * math.sqrt(max(0.0,
        1 - math.cos(al) ** 2 - math.cos(be) ** 2 - math.cos(ga) ** 2
        + 2 * math.cos(al) * math.cos(be) * math.cos(ga))) / math.sin(ga)
    vc = np.array([cx, cy, cz])
    V = float(np.dot(va, np.cross(vb, vc)))
    a_star = np.cross(vb, vc) / V
    b_star = np.cross(vc, va) / V
    c_star = np.cross(va, vb) / V
    return a_star, b_star, c_star


def compute_peaks(struct: CifStructure,
                  wavelength: float = 1.5406,
                  two_min: float = DEFAULT_TWO_MIN,
                  two_max: float = DEFAULT_TWO_MAX,
                  po=None, wavelengths=None):
    """返回 (list[(two_theta, |F|²·LP, d)], skipped_elements)。

    wavelengths: resolve_wavelengths() 的结果。None -> 单色光。
    po: (h, k, l, r) 择优取向 —— (hkl) 为择优面法向, r 为 March–Dollase 参数。
    完整倒易点枚举 -> 强度求和即自动包含多重性。
    """
    a, b, c, al, be, ga = struct.cell
    ast, bst, cst = reciprocal_basis(a, b, c, al, be, ga)

    # 预计算每原子的散射参数
    zs, a1, a2, a3, a4, b1, b2, b3, b4 = [], [], [], [], [], [], [], [], []
    xs, ys, zs_, occs, Bs = [], [], [], [], []
    skipped = []
    for (elem, x, y, z, occ, B) in struct.atoms:
        coeff = ATOMIC_SCATTERING.get(elem)
        if coeff is None or elem not in ATOMIC_Z:
            skipped.append(elem)
            continue
        Z = ATOMIC_Z[elem]
        zs.append(Z)
        # 展开 4 项 Gaussian 系数
        a1.append(coeff[0][0]); a2.append(coeff[1][0])
        a3.append(coeff[2][0]); a4.append(coeff[3][0])
        b1.append(coeff[0][1]); b2.append(coeff[1][1])
        b3.append(coeff[2][1]); b4.append(coeff[3][1])
        xs.append(x); ys.append(y); zs_.append(z)
        occs.append(occ); Bs.append(B)
    if not zs:
        raise ValueError(f"无可用散射因子: {struct.name} (跳过 {skipped})")

    Z = np.array(zs, float)
    A = np.array([a1, a2, a3, a4], float)        # shape (4, natom)
    Bc = np.array([b1, b2, b3, b4], float)
    X = np.array([xs, ys, zs_], float)           # (3, natom)
    OCC = np.array(occs, float)
    BW = np.array(Bs, float)
    # 相消干涉的反射理论上 |F|²=0, 浮点残差约 1e-32 相对量级。
    # 按 s=0 处的最大可能 |F|² 设相对阈值滤掉"数值噪声峰"。
    f_ref_sq = float(np.sum(Z * OCC)) ** 2
    tol_i = max(f_ref_sq * 1e-9, 1e-300)

    comps = wavelengths if wavelengths is not None else [(float(wavelength), 1.0)]
    max_g = 2 * math.sin(math.radians(two_max / 2)) / min(w for w, _ in comps)
    min_g = 2 * math.sin(math.radians(two_min / 2)) / max(w for w, _ in comps)
    min_recip = min(np.linalg.norm(ast), np.linalg.norm(bst), np.linalg.norm(cst))
    H = int(math.ceil(max_g / min_recip)) + 2
    H = max(H, 6)

    # 择优取向方向 (笛卡尔单位矢量; hkl 的法向即其倒易矢量)
    po_vec, po_r, po_neutral = None, 1.0, True
    if po is not None:
        ph, pk, pl, po_r = po
        po_r = float(po_r)
        if po_r <= 0:
            raise ValueError("March–Dollase r 必须 > 0")
        _v = int(ph) * ast + int(pk) * bst + int(pl) * cst
        _nv = float(np.linalg.norm(_v))
        if _nv <= 0:
            raise ValueError("择优取向面指数 (h k l) 无效")
        po_vec = _v / _nv
        po_neutral = abs(po_r - 1.0) < 1e-12

    peaks: dict[int, list] = {}
    for h in range(-H, H + 1):
        for k in range(-H, H + 1):
            for l in range(-H, H + 1):
                if h == 0 and k == 0 and l == 0:
                    continue
                rlv = h * ast + k * bst + l * cst
                g = math.sqrt(float(rlv @ rlv))
                if g < min_g - 1e-9 or g > max_g + 1e-9:
                    continue
                s2 = (g / 2.0) ** 2
                # f_j = Z_j - 41.78214*s2 * sum_i a_i exp(-b_i s2)
                fs = Z - 41.78214 * s2 * np.sum(A * np.exp(-Bc * s2), axis=0)
                # F = sum f * occ * exp(2πi (h·r)) * exp(-B s2)
                g_dot_r = h * X[0] + k * X[1] + l * X[2]
                phase = np.exp(2j * math.pi * g_dot_r) * np.exp(-BW * s2)
                F = np.sum(fs * OCC * phase)
                i_hkl = (F.real ** 2 + F.imag ** 2)
                if i_hkl <= tol_i:
                    continue
                # 择优取向权重 (r=1 时严格为 1.0)
                wpo = 1.0
                if po_vec is not None and not po_neutral:
                    ca = float(rlv @ po_vec) / g
                    wpo = march_dollase_weight(ca, po_r)
                    if wpo <= 0:
                        continue
                # Kα 双线: 每条分量各自满足 Bragg 关系 -> 各自一个衍射角
                for wl, wgt in comps:
                    s_arg = wl * g / 2
                    if s_arg >= 1.0:
                        continue
                    theta = math.asin(s_arg)
                    two_theta = math.degrees(2 * theta)
                    if two_theta < two_min - 1e-9 or two_theta > two_max + 1e-9:
                        continue
                    lp = (1 + math.cos(2 * theta) ** 2) / (math.sin(theta) ** 2 * math.cos(theta))
                    val = i_hkl * lp * wgt * wpo
                    if val <= 0:
                        continue
                    key = round(two_theta / TWO_THETA_TOL)
                    if key in peaks:
                        peaks[key][0] += val
                    else:
                        peaks[key] = [val, two_theta, 1.0 / g]

    out = []
    for v in peaks.values():
        if v[0] <= 0:
            continue
        out.append((v[1], v[0], v[2]))
    out.sort(key=lambda t: t[0])
    return out, skipped
