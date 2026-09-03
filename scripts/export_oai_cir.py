#!/usr/bin/env python3
"""Export Sionna RT channels along a UE trajectory to OAI CIR files."""

from __future__ import annotations

import argparse
import os
import sys
from difflib import get_close_matches

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from sionna_rt_gui.oai_cir_export import (
    OaiCirFrame,
    OaiCirSeries,
    cir_to_oai_frame,
    slice_link_from_cir,
    write_oai_cir_file,
)


def _parse_xyz(text: str) -> list[float]:
    xyz = [float(v) for v in text.replace(" ", "").split(",")]
    if len(xyz) != 3:
        raise argparse.ArgumentTypeError(f"expected x,y,z, got {text!r}")
    return xyz


def _get_built_in_scenes(rt) -> dict[str, str]:
    scenes = {}
    for var_name in dir(rt.scene):
        var = getattr(rt.scene, var_name)
        if isinstance(var, str) and var.endswith(".xml"):
            scenes[var_name] = var
            base = os.path.splitext(os.path.basename(var))[0]
            scenes.setdefault(base, var)
    return scenes


def _resolve_scene_arg(scene_arg: str, rt) -> tuple[str, str | None]:
    if os.path.exists(scene_arg):
        return scene_arg, None

    built_in_scenes = _get_built_in_scenes(rt)
    normalized = os.path.splitext(os.path.basename(scene_arg))[0]
    for key in (scene_arg, normalized):
        if key in built_in_scenes and os.path.exists(built_in_scenes[key]):
            return built_in_scenes[key], key

    known_names = sorted(built_in_scenes)
    suggestions = get_close_matches(normalized, known_names, n=5)
    details = [
        f'scene "{scene_arg}" was not found',
        "Use an existing XML path or a built-in scene name.",
    ]
    if suggestions:
        details.append("Did you mean one of: " + ", ".join(suggestions) + "?")
    if "munich" in built_in_scenes:
        details.append(f'Example: --scene munich  (resolves to {built_in_scenes["munich"]})')
    raise FileNotFoundError("\n".join(details))


def _trajectory_from_csv(csv_path: str, period_s: float) -> np.ndarray:
    import csv

    def pick(row, *names):
        for n in names:
            if n in row and row[n] not in ("", None):
                return float(row[n])
        raise KeyError(names)

    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                t = pick(row, "t", "time", "run_elapsed_s")
                x = pick(row, "x", "x_xml_m")
                y = pick(row, "y", "y_xml_m")
                z = pick(row, "z", "z_xml_m")
            except (KeyError, ValueError):
                continue
            rows.append((t, x, y, z))
    if not rows:
        raise SystemExit(f"no usable rows in {csv_path}")
    rows.sort(key=lambda r: r[0])
    t = np.array([r[0] for r in rows])
    xyz = np.array([[r[1], r[2], r[3]] for r in rows])
    grid = np.arange(t[0], t[-1] + 1e-9, period_s)
    out = np.empty((grid.size, 3))
    for i in range(3):
        out[:, i] = np.interp(grid, t, xyz[:, i])
    return out


def export_trajectory(
    scene,
    ap_positions_xml: list[list[float]],
    ue_positions_xml: np.ndarray,
    *,
    sampling_rate_hz: float,
    snapshot_period_s: float,
    carrier_hz: float,
    max_depth: int = 5,
    channel_length: int | None = None,
    max_taps: int | None = None,
    out_dir: str = "cir_out",
    ap_names: list[str] | None = None,
) -> list[str]:
    from sionna import rt

    scene.frequency = carrier_hz
    scene.tx_array = rt.PlanarArray(num_rows=1, num_cols=1, pattern="iso", polarization="V")
    scene.rx_array = scene.tx_array

    for name in list(scene.transmitters.keys()):
        scene.remove(name)
    for name in list(scene.receivers.keys()):
        scene.remove(name)

    def xyz(p):
        return [float(p[0]), float(p[1]), float(p[2])]

    ap_names = ap_names or [f"ap{i}" for i in range(len(ap_positions_xml))]
    for name, pos in zip(ap_names, ap_positions_xml):
        scene.add(rt.Transmitter(name, position=xyz(pos)))
    scene.add(rt.Receiver("ue", position=xyz(ue_positions_xml[0])))

    solver = rt.PathSolver()
    n_links = len(ap_positions_xml)
    per_link_frames: list[list[OaiCirFrame]] = [[] for _ in range(n_links)]

    if channel_length is None:
        probe = np.linspace(0, len(ue_positions_xml) - 1, num=min(8, len(ue_positions_xml))).astype(int)
        max_len = 1
        for idx in probe:
            scene.receivers["ue"].position = xyz(ue_positions_xml[idx])
            a, tau = solver(scene, max_depth=max_depth).cir(normalize_delays=False, out_type="numpy")
            for link in range(n_links):
                amps, delays = slice_link_from_cir(a, tau, rx_index=0, tx_index=link)
                frame = cir_to_oai_frame(amps, delays, sampling_rate_hz, max_taps=max_taps)
                max_len = max(max_len, frame.channel_length)
        channel_length = max_len
        print(f"[export] auto channel_length = {channel_length} taps")

    for step, ue_pos in enumerate(ue_positions_xml):
        scene.receivers["ue"].position = xyz(ue_pos)
        a, tau = solver(scene, max_depth=max_depth).cir(normalize_delays=False, out_type="numpy")
        for link in range(n_links):
            amps, delays = slice_link_from_cir(a, tau, rx_index=0, tx_index=link)
            per_link_frames[link].append(
                cir_to_oai_frame(amps, delays, sampling_rate_hz, channel_length=channel_length, max_taps=max_taps)
            )
        if (step + 1) % 20 == 0 or step == len(ue_positions_xml) - 1:
            print(f"[export] snapshot {step + 1}/{len(ue_positions_xml)}")

    os.makedirs(out_dir, exist_ok=True)
    written = []
    for link, name in enumerate(ap_names):
        series = OaiCirSeries(
            sampling_rate_hz=sampling_rate_hz,
            snapshot_period_s=snapshot_period_s,
            carrier_hz=carrier_hz,
            channel_length=channel_length,
            frames=per_link_frames[link],
        )
        path = os.path.join(out_dir, f"{name}_to_ue.cir")
        write_oai_cir_file(path, series)
        gains = [f.path_loss_db for f in per_link_frames[link]]
        print(f"[export] {path}: {len(series.frames)} snapshots, path_loss_db {min(gains):.1f}..{max(gains):.1f}")
        written.append(path)
    return written


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scene", help="scene XML path or built-in scene name; omit with --demo")
    p.add_argument("--demo", action="store_true", help="built-in street canyon demo")
    p.add_argument("--ap", action="append", default=[], metavar="x,y,z", help="access-point position (repeatable)")
    p.add_argument("--csv", help="CSV trajectory with x,y,z columns")
    p.add_argument("--line", nargs=3, metavar=("A", "B", "N"), help='"x,y,z" "x,y,z" num_points')
    p.add_argument("--fs", type=float, default=61.44e6, help="OAI sampling rate [Hz]")
    p.add_argument("--period", type=float, default=0.1, help="snapshot period [s]")
    p.add_argument("--carrier", type=float, default=3.7e9, help="carrier [Hz]")
    p.add_argument("--max-depth", type=int, default=5)
    p.add_argument("--channel-length", type=int, default=None)
    p.add_argument("--max-taps", type=int, default=None)
    p.add_argument("--out", default="cir_out")
    args = p.parse_args()

    from sionna import rt

    if args.demo:
        scene = rt.load_scene(rt.scene.simple_street_canyon_with_cars)
        ap_xml = [[-32.0, 10.0, 32.0], [20.0, 5.0, 25.0]]
    else:
        if not args.scene:
            p.error("--scene is required unless --demo")
        if not args.ap:
            p.error("at least one --ap is required with --scene")
        try:
            scene_path, scene_alias = _resolve_scene_arg(args.scene, rt)
        except FileNotFoundError as e:
            p.error(str(e))
        if scene_alias is not None:
            print(f'[export] scene "{args.scene}" resolved as "{scene_alias}" -> {scene_path}')
        else:
            print(f"[export] scene {scene_path}")
        scene = rt.load_scene(scene_path)
        ap_xml = [_parse_xyz(a) for a in args.ap]
    ap_names = [f"ap{i}" for i in range(len(ap_xml))]

    if args.csv:
        ue_xml = _trajectory_from_csv(args.csv, args.period)
    elif args.line:
        a = np.array(_parse_xyz(args.line[0]))
        b = np.array(_parse_xyz(args.line[1]))
        ue_xml = np.linspace(a, b, int(args.line[2]))
    elif args.demo:
        ue_xml = np.linspace([-19.0, -1.0, 1.5], [15.0, 2.0, 1.5], 30)
    else:
        p.error("provide a trajectory: --csv, --line, or --demo")

    print(f"[export] {len(ap_xml)} APs, {len(ue_xml)} UE snapshots, fs={args.fs/1e6:.2f} Msps")
    written = export_trajectory(
        scene,
        ap_xml,
        ue_xml,
        sampling_rate_hz=args.fs,
        snapshot_period_s=args.period,
        carrier_hz=args.carrier,
        max_depth=args.max_depth,
        channel_length=args.channel_length,
        max_taps=args.max_taps,
        out_dir=args.out,
        ap_names=ap_names,
    )
    print(f"[export] wrote {len(written)} CIR file(s) to {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
