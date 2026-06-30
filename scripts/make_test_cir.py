#!/usr/bin/env python3
"""Generate synthetic OAICIRv1 files for testing the OAI EXTERNAL_CIR model."""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sionna_rt_gui.oai_cir_export import (
    OaiCirFrame,
    OaiCirSeries,
    write_oai_cir_file,
)


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("mode", choices=["unit-tap", "los", "ramp"])
    p.add_argument("--out", required=True)
    p.add_argument("--fs", type=float, default=61.44e6)
    p.add_argument("--carrier", type=float, default=3.7e9)
    p.add_argument("--period", type=float, default=0.1)
    p.add_argument("--channel-length", type=int, default=16)
    p.add_argument("--path-loss-db", type=float, default=0.0)
    p.add_argument("--offset", type=int, default=0)
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--pl-start", type=float, default=0.0)
    p.add_argument("--pl-end", type=float, default=-40.0)
    args = p.parse_args()

    L = args.channel_length

    def unit_frame(path_loss_db: float, offset: int) -> OaiCirFrame:
        taps = np.zeros(L, dtype=np.complex64)
        taps[0] = 1.0
        return OaiCirFrame(channel_offset=offset, path_loss_db=path_loss_db, taps=taps)

    if args.mode == "unit-tap":
        frames = [unit_frame(0.0, 0)]
    elif args.mode == "los":
        frames = [unit_frame(args.path_loss_db, args.offset)]
    else:
        pls = np.linspace(args.pl_start, args.pl_end, args.n)
        frames = [unit_frame(float(pl), args.offset) for pl in pls]

    series = OaiCirSeries(
        sampling_rate_hz=args.fs,
        snapshot_period_s=args.period,
        carrier_hz=args.carrier,
        channel_length=L,
        frames=frames,
    )
    write_oai_cir_file(args.out, series)
    pls = [f.path_loss_db for f in frames]
    print(
        f"[make_test_cir] {args.mode}: {len(frames)} snapshot(s), L={L}, "
        f"path_loss_db {min(pls):.1f}..{max(pls):.1f} -> {args.out}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
