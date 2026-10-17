"""v1.6.0 多格式谱图读取验收。

真实样本来自只读目录 D:/Project/XRD/XRData；本机缺少真实样本的格式使用明确
标注的合成样本。数值 oracle 是同家族 PolyXRD-Converter 源码。
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

from rutana.core.patterns import load_pattern
from rutana.core.peakmeasure import measure_peak

XRDATA = Path("D:/Project/XRD/XRData")
CONVERTER_SRC = Path("D:/Project/XRD/PolyXRD-Converter/src")
GOLDEN = Path(__file__).parent / "golden" / "formats_real.json"


REAL_FORMATS = (
    ("Shimadzu Data/Std/Si/Si.RAW", "raw", "shimadzu_raw"),
    ("Shimadzu Data/Std/Si/Si.ORG", "raw", "shimadzu_raw"),
    ("Shimadzu Data/Std/Si/Si.RSM", "raw", "shimadzu_raw"),
    ("Shimadzu Data/Std/Si/Si.RBG", "raw", "shimadzu_raw"),
    ("Shimadzu Data/Std/Si/Si.RFI", "raw", "shimadzu_raw"),
    ("Shimadzu Data/ENVCAL/053/053.RAX", "raw", "shimadzu_raw"),
    ("Shimadzu Data/Crynity/CRYN/CRYN.RLZ", "raw", "shimadzu_raw"),
    ("csuHJW/data001：TiO2双相.raw", "raw", "rigaku_raw"),
    ("IUCr/BAUXITE.RAW", "raw", "scintag_raw2"),
    ("IUCr/BAUXITE.mdi", "mdi", None),
    ("IUCr/gsas/bauxite.gss", "gsas", None),
)


RAW_TEXT_PAIRS = (
    ("smz geshi/1. Si.RAW", "smz geshi/1. Si.txt"),
    ("csuHJW/data001：TiO2双相.raw", "csuHJW/txt/data001：TiO2双相_raw.txt"),
    ("IUCr/BAUXITE.RAW", "IUCr/txt/BAUXITE_raw.txt"),
)


def _real(relative: str) -> Path:
    path = XRDATA / relative
    if not path.exists():
        pytest.skip(f"真实样本不在本机: {path}")
    return path


def _assert_pattern_sane(pattern) -> None:
    assert pattern.two_theta.size > 1
    assert np.all(np.diff(pattern.two_theta) > 0)
    assert np.all(np.isfinite(pattern.two_theta))
    assert np.all(np.isfinite(pattern.intensity))
    assert np.all(pattern.intensity >= 0)
    assert -180.0 <= float(pattern.two_theta[0]) < float(pattern.two_theta[-1]) <= 720.0


@pytest.mark.parametrize("relative,format_key,variant", REAL_FORMATS)
def test_real_format_coverage(relative: str, format_key: str, variant: str | None) -> None:
    """真实 RAW 变体、岛津伴随扩展、MDI 与 GSS 都能产生有效谱图。"""
    pattern = load_pattern(_real(relative))
    _assert_pattern_sane(pattern)
    assert pattern.meta["format_key"] == format_key
    assert pattern.meta["num_points"] == pattern.two_theta.size
    if variant is not None:
        assert pattern.meta["raw_variant"] == variant
    for key in ("path", "source_format", "layout", "wavelength_anode"):
        assert key in pattern.meta


def _synthetic_files(root: Path) -> dict[Path, str]:
    """构造本地缺真实样本的格式；所有谱共用 20–21.98°、100 点真值。"""
    n = 100
    x = 20.0 + 0.02 * np.arange(n)
    y = 100.0 + 7.0 * np.arange(n)
    q = 4.0 * np.pi * np.sin(np.radians(x) / 2.0) / 1.5406
    result: dict[Path, str] = {}

    def put(name: str, text: str, key: str) -> Path:
        path = root / name
        path.write_text(text, encoding="utf-8", newline="")
        result[path] = key
        return path

    # GSAS FXYE；同一内容覆盖五种扩展名。
    bank = ["Synthetic GSAS FXYE", "BANK 1 FXYE 100 101 2000 2 3980"]
    bank += [f"{round(xx * 100):d} {yy:.1f} 1.0" for xx, yy in zip(x, y)]
    for ext in ("gsas", "gss", "gsa", "gda", "fxye"):
        put(f"synth.{ext}", "\n".join(bank) + "\n", "gsas")

    # FullProf DAT 与 Jade 两行头 TXT 验证旧四扩展的特征嗅探分流。
    put("synth_fp.dat", "lambda 1.5406\n20.0 0.02 21.98\n" +
        "\n".join(f"{v:.1f}" for v in y) + "\n", "fp_dat")
    jade_values = [" ".join(f"{v:.1f}" for v in y[i:i + 10]) for i in range(0, n, 10)]
    put("synth_jade.txt", "Synthetic Jade\n20 0.02 2 CU 1.5406 21.98 100\n" +
        "\n".join(jade_values) + "\n", "jade_txt")

    ras = ["*RAS_DATA_START", "*RAS_HEADER_START", "*XRAY_WAVELENGTH 1.5406",
           "*RAS_HEADER_END", "*RAS_INT_START"]
    ras += [f"{xx:.3f} {yy:.1f}" for xx, yy in zip(x, y)]
    ras += ["*RAS_INT_END"]
    put("synth.ras", "\n".join(ras) + "\n", "ras")

    profile = "\n".join(f"{xx:.3f} {yy:.1f}" for xx, yy in zip(x, y)) + "\n"
    rasx = root / "synth.rasx"
    with zipfile.ZipFile(rasx, "w") as archive:
        archive.writestr("Data0/Profile0.txt", b"\xef\xbb\xbf" + profile.encode())
        archive.writestr(
            "Data0/MesurementConditions0.xml",
            "<Setup><Wavelength>1.5406</Wavelength></Setup>",
        )
    result[rasx] = "ras"

    put("synth.xye", "# synthetic xye\n" +
        "\n".join(f"{xx:.3f} {yy:.1f} 1.0" for xx, yy in zip(x, y)) + "\n", "xye")
    put("synth.qye", "# wavelength 1.5406\n" +
        "\n".join(f"{qq:.6f} {yy:.1f}" for qq, yy in zip(q, y)) + "\n", "xye")
    put("synth.chi", "Fit2d exchange format v1.0\nArray: chi_2theta\n2-theta I\n" +
        "\n".join(f"{xx:.3f} {yy:.1f}" for xx, yy in zip(x, y)) + "\n", "chi")
    put("synth.qchi", "Fit2d exchange format v1.0\nArray: q\nq 1.5406\n" +
        "\n".join(f"{qq:.6f} {yy:.1f}" for qq, yy in zip(q, y)) + "\n", "chi")

    xml = (
        "<?xml version='1.0'?><xrdMeasurement>"
        "<positions axis='2Theta'><startPosition>20</startPosition>"
        "<endPosition>21.98</endPosition></positions>"
        f"<intensities>{' '.join(str(float(v)) for v in y)}</intensities>"
        "</xrdMeasurement>"
    )
    put("synth.xrdml", xml, "xrdml")
    put("synth.xml", xml, "xrdml")
    brml = root / "synth.brml"
    with zipfile.ZipFile(brml, "w") as archive:
        archive.writestr("Experiment0/Data.xml", xml)
    result[brml] = "brml"

    json_path = root / "synth.json"
    json_path.write_text(json.dumps({
        "two_theta": x.tolist(), "intensity": y.tolist(), "wavelength": 1.5406,
        "metadata": {"origin": "synthetic"},
    }), encoding="utf-8")
    result[json_path] = "json"
    put("synth.smz", "\n".join(f"{xx:.3f} {yy:.1f}" for xx, yy in zip(x, y)) + "\n",
        "smz")
    return result


def test_synthetic_format_coverage(tmp_path: Path) -> None:
    """本地无真实 RAS/XYE/CHI/XRDML/BRML/JSON/SMZ 时以合成样本覆盖。"""
    samples = _synthetic_files(tmp_path)
    assert len(samples) == 18
    for path, expected_key in samples.items():
        pattern = load_pattern(path)
        _assert_pattern_sane(pattern)
        assert pattern.meta["format_key"] == expected_key, path.name
        assert pattern.two_theta.size == 100
        assert pattern.two_theta[0] == pytest.approx(20.0, abs=1e-3)
        assert pattern.two_theta[-1] == pytest.approx(21.98, abs=1e-3)


@pytest.mark.parametrize("raw_rel,text_rel", RAW_TEXT_PAIRS)
def test_raw_ascii_cross_format_consistency(raw_rel: str, text_rel: str) -> None:
    """三厂商 RAW 与 ASCII 导出逐点对齐。

    角度容差 5e-4° 来自 Converter 对 Rigaku float32 头的验收口径；三组当前
    实测最大偏差均仅 2.84e-14°。强度允许整体标度差，故归一化后比较。
    """
    raw = load_pattern(_real(raw_rel))
    text = load_pattern(_real(text_rel))
    assert raw.two_theta.size == text.two_theta.size
    assert np.allclose(raw.two_theta, text.two_theta, atol=5e-4, rtol=0)
    raw_peak = float(raw.two_theta[int(np.argmax(raw.intensity))])
    text_peak = float(text.two_theta[int(np.argmax(text.intensity))])
    assert raw_peak == pytest.approx(text_peak, abs=5e-4)
    assert np.allclose(
        raw.intensity / float(np.max(raw.intensity)),
        text.intensity / float(np.max(text.intensity)),
        atol=1e-7,
        rtol=1e-7,
    )


def test_converter_oracle_matches_vendored_reader(tmp_path: Path) -> None:
    """真实与合成格式均与 PolyXRD-Converter 原项目逐点对拍。"""
    if not CONVERTER_SRC.is_dir():
        pytest.skip("PolyXRD-Converter 源码不在本机，跳过 oracle 对拍")
    sys.path.insert(0, str(CONVERTER_SRC))
    try:
        from polyxrd_converter.loader import load_pattern as converter_load
    except Exception as exc:  # noqa: BLE001 - 外部 oracle 可选
        pytest.skip(f"PolyXRD-Converter 无法 import: {exc}")

    real_samples = (
        "Shimadzu Data/Std/Si/Si.RAW",
        "csuHJW/data001：TiO2双相.raw",
        "IUCr/BAUXITE.RAW",
        "IUCr/BAUXITE.mdi",
        "IUCr/gsas/bauxite.gss",
    )
    samples = [_real(relative) for relative in real_samples]
    samples.extend(_synthetic_files(tmp_path))
    for path in samples:
        actual = load_pattern(path)
        oracle = converter_load(path)
        assert np.allclose(actual.two_theta, oracle.two_theta, atol=1e-12, rtol=0), path
        assert np.allclose(actual.intensity, oracle.intensity, atol=1e-12, rtol=0), path


def test_real_format_golden_freeze() -> None:
    """真实代表文件的点数、轴端点与最强峰冻结；轴容差覆盖 float32 舍入。"""
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for name, expected in golden.items():
        pattern = load_pattern(_real(expected["path"]))
        peak = int(np.argmax(pattern.intensity))
        assert pattern.two_theta.size == expected["num_points"], name
        assert pattern.two_theta[0] == pytest.approx(expected["two_theta_start"], abs=5e-6)
        assert pattern.two_theta[-1] == pytest.approx(expected["two_theta_end"], abs=5e-6)
        assert pattern.two_theta[peak] == pytest.approx(expected["peak_two_theta"], abs=5e-6)
        assert pattern.intensity[peak] == pytest.approx(expected["peak_intensity"], abs=1e-6)


def test_unsupported_extension_keeps_error_contract(tmp_path: Path) -> None:
    with pytest.raises(NotImplementedError, match=r"暂不支持的格式: \.uxd"):
        load_pattern(tmp_path / "unknown.uxd")


@pytest.mark.parametrize(
    "name,payload",
    (("empty.xye", b""), ("truncated.raw", b"RAW2\x01\x00"),
     ("garbled.xrdml", b"<xrdMeasurement><broken>")),
)
def test_malformed_inputs_raise_readable_error(tmp_path: Path, name: str, payload: bytes) -> None:
    path = tmp_path / name
    path.write_bytes(payload)
    with pytest.raises(ValueError) as caught:
        load_pattern(path)
    assert str(caught.value).strip()


def test_truncated_shimadzu_raw_is_rejected(tmp_path: Path) -> None:
    source = _real("Shimadzu Data/Std/Si/Si.RAW")
    target = tmp_path / "truncated.raw"
    target.write_bytes(source.read_bytes()[:-40])
    with pytest.raises(ValueError, match="角度轴不可信.*导出为文本格式"):
        load_pattern(target)


def test_unconfident_bruker_axis_is_rejected() -> None:
    source = _real("csuHJW/data035：硬质合金深冷处理后WC相的残余应力.raw")
    with pytest.raises(ValueError, match="RAW 角度轴不可信.*导出为文本格式"):
        load_pattern(source)


def test_memory_error_becomes_readable_value_error(tmp_path: Path, monkeypatch) -> None:
    """超大文件导致的 MemoryError 不穿透 GUI 导入循环。"""
    import rutana.core.patterns as patterns

    source = tmp_path / "huge.json"
    source.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(patterns, "load_vendor_pattern", lambda _path: (_ for _ in ()).throw(
        MemoryError("synthetic")))
    with pytest.raises(ValueError, match="文件过大.*内存不足"):
        patterns.load_pattern(source)


def test_new_raw_connects_to_method_a_peak_measurement() -> None:
    """新格式不是“只能打开”：Rigaku TiO2 RAW 可直接跑 A 法的两峰测量路径。"""
    pattern = load_pattern(_real("csuHJW/data001：TiO2双相.raw"))
    anatase = measure_peak(pattern, 25.3, 0.6)
    rutile = measure_peak(pattern, 27.4, 0.6)
    assert anatase.ok and rutile.ok
    assert anatase.net_area > 0 and rutile.net_area > 0
