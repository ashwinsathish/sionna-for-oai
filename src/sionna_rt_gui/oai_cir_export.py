"""Export Sionna RT channel impulse responses to OpenAirInterface."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

import numpy as np

MAGIC = b"OAICIRv1"
_HEADER_STRUCT = struct.Struct("<8s d i i i i d d")
_RECORD_HEADER = struct.Struct("<i i d")

DEFAULT_DYNAMIC_RANGE_DB = 60.0


@dataclass
class OaiCirFrame:
    channel_offset: int # bulk delay [whole samples]
    path_loss_db: float # amplitude gain; linear = 10**(db/20)
    taps: np.ndarray # complex64, unit-energy, [channel_length]

    @property
    def channel_length(self) -> int:
        return int(self.taps.shape[-1])


def link_path_gain(amps: np.ndarray) -> float:
    amps = np.asarray(amps).reshape(-1)
    return float(np.sum(np.abs(amps) ** 2))


def cir_to_oai_frame(
    amps: np.ndarray,
    delays_s: np.ndarray,
    sampling_rate_hz: float,
    *,
    channel_length: int | None = None,
    max_taps: int | None = None,
    dynamic_range_db: float | None = DEFAULT_DYNAMIC_RANGE_DB,
    min_path_loss_db: float = -300.0,
) -> OaiCirFrame:
    amps = np.asarray(amps, dtype=np.complex128).reshape(-1)
    delays_s = np.asarray(delays_s, dtype=np.float64).reshape(-1)
    n = min(amps.size, delays_s.size)
    amps, delays_s = amps[:n], delays_s[:n]

    valid = (
        np.isfinite(amps)
        & np.isfinite(delays_s)
        & (delays_s >= 0.0)
        & (np.abs(amps) > 0.0)
    )
    amps, delays_s = amps[valid], delays_s[valid]

    total_gain = link_path_gain(amps)
    if amps.size == 0 or total_gain <= 0.0:
        return OaiCirFrame(
            channel_offset=0,
            path_loss_db=float(min_path_loss_db),
            taps=np.zeros(max(1, channel_length or 1), dtype=np.complex64),
        )

    if dynamic_range_db is not None:
        peak = np.max(np.abs(amps))
        keep = np.abs(amps) >= peak * 10.0 ** (-dynamic_range_db / 20.0)
        amps, delays_s = amps[keep], delays_s[keep]
        total_gain = link_path_gain(amps)

    fs = float(sampling_rate_hz)
    channel_offset = int(np.floor(np.min(delays_s) * fs))
    residual_s = delays_s - channel_offset / fs

    if channel_length is None:
        max_residual_samples = float(np.max(residual_s) * fs)
        channel_length = int(np.ceil(max_residual_samples)) + 12
    channel_length = max(1, int(channel_length))

    lags = np.arange(channel_length, dtype=np.float64)
    g = np.sinc(lags[None, :] - residual_s[:, None] * fs)
    taps = (amps[:, None] * g).sum(axis=0)

    if max_taps is not None and 0 < max_taps < taps.size:
        keep_idx = np.argpartition(np.abs(taps) ** 2, -max_taps)[-max_taps:]
        truncated = np.zeros_like(taps)
        truncated[keep_idx] = taps[keep_idx]
        taps = truncated

    tap_energy = float(np.sum(np.abs(taps) ** 2))
    if tap_energy <= 0.0:
        return OaiCirFrame(
            channel_offset=channel_offset,
            path_loss_db=float(min_path_loss_db),
            taps=np.zeros(channel_length, dtype=np.complex64),
        )

    taps_normalized = taps / np.sqrt(tap_energy)
    path_loss_db = max(10.0 * np.log10(tap_energy), float(min_path_loss_db))

    return OaiCirFrame(
        channel_offset=channel_offset,
        path_loss_db=float(path_loss_db),
        taps=taps_normalized.astype(np.complex64),
    )


def slice_link_from_cir(
    a: np.ndarray,
    tau: np.ndarray,
    rx_index: int,
    tx_index: int,
    *,
    rx_ant: int = 0,
    tx_ant: int = 0,
    time_step: int = 0,
) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(a)
    tau = np.asarray(tau)
    amps = a[rx_index, rx_ant, tx_index, tx_ant, :, time_step]
    if tau.ndim == 3:
        delays = tau[rx_index, tx_index, :]
    elif tau.ndim == 5:
        delays = tau[rx_index, rx_ant, tx_index, tx_ant, :]
    else:
        raise ValueError(f"unexpected tau rank {tau.ndim}; expected 3 or 5")
    return np.asarray(amps), np.asarray(delays)


@dataclass
class OaiCirSeries:
    sampling_rate_hz: float
    snapshot_period_s: float
    carrier_hz: float
    channel_length: int
    frames: list[OaiCirFrame] = field(default_factory=list)
    nb_tx: int = 1
    nb_rx: int = 1


def write_oai_cir_file(path: str, series: OaiCirSeries) -> None:
    L = int(series.channel_length)
    n = len(series.frames)
    with open(path, "wb") as f:
        f.write(
            _HEADER_STRUCT.pack(
                MAGIC,
                float(series.sampling_rate_hz),
                int(series.nb_tx),
                int(series.nb_rx),
                L,
                n,
                float(series.snapshot_period_s),
                float(series.carrier_hz),
            )
        )
        for i, frame in enumerate(series.frames):
            taps = np.asarray(frame.taps, dtype=np.complex64).reshape(-1)
            expected = series.nb_rx * series.nb_tx * L
            if taps.size != expected:
                fixed = np.zeros(expected, dtype=np.complex64)
                fixed[: min(expected, taps.size)] = taps[: min(expected, taps.size)]
                taps = fixed
            f.write(_RECORD_HEADER.pack(i, int(frame.channel_offset), float(frame.path_loss_db)))
            f.write(taps.tobytes())


def read_oai_cir_file(path: str) -> OaiCirSeries:
    with open(path, "rb") as f:
        magic, fs, nb_tx, nb_rx, L, n, period, carrier = _HEADER_STRUCT.unpack(
            f.read(_HEADER_STRUCT.size)
        )
        if magic != MAGIC:
            raise ValueError(f"bad magic {magic!r}; not an OAICIRv1 file")
        frames: list[OaiCirFrame] = []
        tap_count = nb_rx * nb_tx * L
        tap_bytes = tap_count * np.dtype(np.complex64).itemsize
        for _ in range(n):
            _idx, channel_offset, path_loss_db = _RECORD_HEADER.unpack(
                f.read(_RECORD_HEADER.size)
            )
            taps = np.frombuffer(f.read(tap_bytes), dtype=np.complex64).copy()
            frames.append(
                OaiCirFrame(
                    channel_offset=int(channel_offset),
                    path_loss_db=float(path_loss_db),
                    taps=taps,
                )
            )
    return OaiCirSeries(
        sampling_rate_hz=float(fs),
        snapshot_period_s=float(period),
        carrier_hz=float(carrier),
        channel_length=int(L),
        frames=frames,
        nb_tx=int(nb_tx),
        nb_rx=int(nb_rx),
    )
