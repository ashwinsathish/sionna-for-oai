import numpy as np
import pytest

from sionna_rt_gui.oai_cir_export import (
    OaiCirFrame,
    OaiCirSeries,
    cir_to_oai_frame,
    link_path_gain,
    read_oai_cir_file,
    slice_link_from_cir,
    write_oai_cir_file,
)

FS = 61.44e6


def test_unit_tap_equals_awgn():
    amp = 0.5 + 0.0j
    frame = cir_to_oai_frame(np.array([amp]), np.array([0.0]), FS)
    assert frame.channel_offset == 0
    assert np.isclose(np.sum(np.abs(frame.taps) ** 2), 1.0)
    assert np.isclose(np.abs(frame.taps[0]), 1.0, atol=1e-5)
    assert np.isclose(10.0 ** (frame.path_loss_db / 20.0), abs(amp), rtol=1e-5)


def test_bulk_delay_goes_to_channel_offset():
    delay = 1e-6
    frame = cir_to_oai_frame(np.array([1.0 + 0j]), np.array([delay]), FS)
    assert frame.channel_offset == int(np.floor(delay * FS))
    assert np.argmax(np.abs(frame.taps)) <= 1


def test_path_loss_reflects_total_power():
    a = 0.1
    frame = cir_to_oai_frame(np.array([a + 0j, a + 0j]), np.array([0.0, 0.0]), FS)
    assert np.isclose(10.0 ** (frame.path_loss_db / 20.0), 2 * a, rtol=1e-4)


def test_normalized_taps_times_gain_reconstruct_channel():
    rng = np.random.default_rng(3)
    amps = (rng.normal(size=5) + 1j * rng.normal(size=5)) * 1e-3
    delays = rng.uniform(0, 0.5e-6, size=5)
    frame = cir_to_oai_frame(amps, delays, FS, channel_length=64)
    reconstructed = frame.taps * 10.0 ** (frame.path_loss_db / 20.0)

    residual = delays - frame.channel_offset / FS
    lags = np.arange(64)
    raw = (amps[:, None] * np.sinc(lags[None, :] - residual[:, None] * FS)).sum(0)
    np.testing.assert_allclose(reconstructed, raw, rtol=1e-4, atol=1e-9)


def test_max_taps_truncation_keeps_strongest():
    rng = np.random.default_rng(4)
    amps = (rng.normal(size=20) + 1j * rng.normal(size=20)) * 1e-3
    delays = rng.uniform(0, 2e-6, size=20)
    full = cir_to_oai_frame(amps, delays, FS, channel_length=200)
    trunc = cir_to_oai_frame(amps, delays, FS, channel_length=200, max_taps=10)
    assert np.count_nonzero(trunc.taps) <= 10
    assert np.isclose(np.sum(np.abs(trunc.taps) ** 2), 1.0, atol=1e-5)
    assert full.channel_length == trunc.channel_length


def test_dead_link_is_safe():
    frame = cir_to_oai_frame(np.array([]), np.array([]), FS, channel_length=8)
    assert frame.path_loss_db <= -200.0
    assert np.all(frame.taps == 0)
    assert frame.channel_length == 8


def test_dynamic_range_drops_weak_paths():
    amps = np.array([1.0 + 0j, 1e-9 + 0j])
    delays = np.array([0.0, 1e-6])
    frame = cir_to_oai_frame(amps, delays, FS, dynamic_range_db=60.0)
    assert frame.channel_offset == 0


def test_slice_link_from_cir():
    rng = np.random.default_rng(5)
    a = (rng.normal(size=(2, 1, 3, 1, 4, 1))
         + 1j * rng.normal(size=(2, 1, 3, 1, 4, 1))).astype(np.complex64)
    tau = rng.uniform(0, 1e-6, size=(2, 3, 4)).astype(np.float32)
    amps, delays = slice_link_from_cir(a, tau, rx_index=1, tx_index=2)
    np.testing.assert_array_equal(amps, a[1, 0, 2, 0, :, 0])
    np.testing.assert_array_equal(delays, tau[1, 2, :])
    assert link_path_gain(amps) > 0


def test_file_roundtrip(tmp_path):
    rng = np.random.default_rng(6)
    frames = []
    for _ in range(5):
        amps = (rng.normal(size=6) + 1j * rng.normal(size=6)) * 1e-3
        delays = rng.uniform(0, 0.8e-6, size=6)
        frames.append(cir_to_oai_frame(amps, delays, FS, channel_length=48))
    series = OaiCirSeries(
        sampling_rate_hz=FS,
        snapshot_period_s=0.1,
        carrier_hz=3.7e9,
        channel_length=48,
        frames=frames,
    )
    path = str(tmp_path / "run.cir")
    write_oai_cir_file(path, series)
    loaded = read_oai_cir_file(path)

    assert loaded.sampling_rate_hz == FS
    assert loaded.channel_length == 48
    assert loaded.snapshot_period_s == 0.1
    assert loaded.carrier_hz == 3.7e9
    assert len(loaded.frames) == 5
    for orig, got in zip(frames, loaded.frames):
        assert got.channel_offset == orig.channel_offset
        assert np.isclose(got.path_loss_db, orig.path_loss_db, rtol=1e-5)
        np.testing.assert_allclose(got.taps, orig.taps, rtol=1e-5, atol=1e-7)


def test_bad_magic_rejected(tmp_path):
    path = str(tmp_path / "bad.cir")
    with open(path, "wb") as f:
        f.write(b"NOTACIR_" + b"\x00" * 40)
    with pytest.raises(ValueError):
        read_oai_cir_file(path)
