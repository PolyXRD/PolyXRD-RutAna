"""T4.5 验收 · QPA 测试：★酸检（81.37% / 50%）/ Z 反算 / 异常。"""
from __future__ import annotations

from pathlib import Path

import pytest

from rutana.core.profile.cif import parse_cif
from rutana.core.refine.qpa import (
    formula_mass,
    infer_z,
    qpa_inputs_from_cif,
    qpa_weights,
    to_ratio,
)

DATA = Path(__file__).resolve().parent.parent / "rutana" / "data"


def test_acid_test_equal_scales_81_37():
    """★酸检 1: S_锐 = S_金 = 1.0 -> w_锐 = 81.37% ± 0.01。"""
    ws = qpa_weights([("anatase", 1.0, 4, 136.3, 79.87),
                      ("rutile", 1.0, 2, 62.42, 79.87)])
    wa, wr = to_ratio(ws, 0, 1)
    assert wa == pytest.approx(81.37, abs=0.01)
    assert wr == pytest.approx(100.0 - 81.37, abs=0.01)


def test_acid_test_ratio_4_368_gives_50():
    """★酸检 2: S_锐/S_金 = 1/4.368 -> w_锐 = 50.00% ± 0.01。"""
    ws = qpa_weights([("anatase", 1.0, 4, 136.3, 79.87),
                      ("rutile", 4.368, 2, 62.42, 79.87)])
    wa, wr = to_ratio(ws, 0, 1)
    assert wa == pytest.approx(50.0, abs=0.01)
    assert wr == pytest.approx(50.0, abs=0.01)


def test_weights_sum_to_one():
    ws = qpa_weights([("a", 2.0, 4, 136.3, 79.87),
                      ("r", 1.0, 2, 62.42, 79.87)])
    assert sum(w.weight for w in ws) == pytest.approx(1.0, abs=1e-12)


def test_all_zero_scale_raises():
    with pytest.raises(ValueError):
        qpa_weights([("a", 0.0, 4, 136.3, 79.87),
                     ("r", 0.0, 2, 62.42, 79.87)])


def test_invalid_inputs_raise():
    with pytest.raises(ValueError):
        qpa_weights([("a", -1.0, 4, 136.3, 79.87)])
    with pytest.raises(ValueError):
        qpa_weights([("a", 1.0, 0, 136.3, 79.87)])
    with pytest.raises(ValueError):
        qpa_weights([])


def test_infer_z_from_builtin_cifs():
    st_a = parse_cif(DATA / "anatase.cif")
    st_r = parse_cif(DATA / "rutile.cif")
    assert infer_z(st_a, "O2 Ti") == 4
    assert infer_z(st_r, "O2 Ti") == 2


def test_qpa_inputs_from_cifs():
    st_a = parse_cif(DATA / "anatase.cif")
    st_r = parse_cif(DATA / "rutile.cif")
    za, va, ma = qpa_inputs_from_cif(st_a, "O2 Ti")
    zr, vr, mr = qpa_inputs_from_cif(st_r, "O2 Ti")
    assert (za, zr) == (4, 2)
    assert abs(va - 136.3) < 1.0 and abs(vr - 62.42) < 0.5
    assert abs(ma - 79.87) < 0.05 and abs(mr - 79.87) < 0.05


def test_formula_mass_tio2():
    assert formula_mass("TiO2") == pytest.approx(79.87, abs=0.05)
    assert formula_mass("O2 Ti") == pytest.approx(79.87, abs=0.05)
