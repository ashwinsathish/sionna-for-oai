Sionna RT GUI
=============

An interactive GUI to simulate and visualize [Sionna RT](https://github.com/NVlabs/sionna-rt) scenes, paths, and radio maps.

![Sionna RT GUI screenshot](src/sionna_rt_gui/data/preview.webp)


Getting started
---------------

This project requires Python 3.10 or later. Sionna RT will be installed automatically as part of the dependencies.

### Installing from PyPI

```bash
pip install sionna-rt-gui
```

Then, start the GUI with:

```bash
sionna-rt-gui
```

Select a scene from Sionna RT's built-in scenes using the dropdown in the top-left corner, or by passing it as a command-line argument:

```bash
sionna-rt-gui path/to/scene.xml
```


### Installing from source

If you would like to tweak the GUI or build on top of it, you can clone this repository and install it from source:

```bash
python3 -m venv ./.venv
source ./.venv/bin/activate
pip install -r ./requirements.txt
```

Then, start the GUI with:

```bash
python ./scripts/run.py
```

GUI controls
------------

The left-hand window can be used to trigger and configure all simulation options for radio devices, radio maps, and paths.

Press <kbd>?</kbd> or <kbd>H</kbd> to show a help window listing supported keyboard shortcuts.

**Animations**: the position of radio devices can be animated over time. To do so,

1. Select the radio device to animate.
2. Use the transformation gizmo to place it in the scene.
3. In the Selection window, click 'Add current position'
4. Move the radio device to its next position and repeat until the trajectory is complete.

The device will move along the path when animation playback is enabled under the Animation section of the main window.


Command-line options
--------------------

### Configuration files

All available options and their defaults are defined in [`src/sionna_rt_gui/config.py`](src/sionna_rt_gui/config.py).

Almost all parameters can be set using YAML configuration files, see e.g. [`configs/sionna_rt_gui/example.yaml`](configs/sionna_rt_gui/example.yaml). Pass a config file with the `--config` argument:

```bash
sionna-rt-gui --config path/to/config.yaml
```

### Live reload mode

For development, use `--watch` to enable live code reloading:

```bash
python ./scripts/run.py --watch
```

This monitors source files and automatically reloads the GUI when changes are detected. You can also trigger a manual reload with <kbd>Shift</kbd> + <kbd>R</kbd>.



OAI channel export
------------------

Export ray-traced channels as .cir files for OpenAirInterface's RFsimulator
(EXTERNAL_CIR channel model). The GUI is useful for inspecting the scene, but
the OAI export is done from the command line: the exporter loads the same
Sionna RT scene, places one or more access points, traces a UE trajectory, and
writes one `.cir` file per access point.

### 1. Export a Sionna RT channel

The quickest end-to-end example is the built-in street canyon demo:

Run from this `sionna-rt-gui` repo:

```bash
cd /path/to/sionna-rt-gui
source .venv/bin/activate
MPLCONFIGDIR=/tmp/matplotlib python scripts/export_oai_cir.py --demo --out cir_out/
```

This uses Sionna RT's `simple_street_canyon_with_cars` scene with two demo AP
positions and a straight UE trajectory. It writes:

```text
cir_out/ap0_to_ue.cir
cir_out/ap1_to_ue.cir
```

These are real ray-traced Sionna RT channels, not synthetic dummy channels, but
the AP positions and UE path are demo values from `scripts/export_oai_cir.py`.

For a custom scene and path:

Run from this `sionna-rt-gui` repo:

```bash
MPLCONFIGDIR=/tmp/matplotlib python scripts/export_oai_cir.py \
    --scene scene.xml \
    --ap "0,10,5" \
    --ap "20,5,8" \
    --line "-10,0,1.5" "10,4,1.5" 50 \
    --fs 61.44e6 \
    --out cir_out/
```

You can also drive the UE trajectory from a CSV file:

Run from this `sionna-rt-gui` repo:

```bash
MPLCONFIGDIR=/tmp/matplotlib python scripts/export_oai_cir.py \
    --scene scene.xml \
    --ap "0,10,5" \
    --csv ue_trajectory.csv \
    --fs 61.44e6 \
    --out cir_out/
```

The CSV should contain time and position columns. The exporter accepts
`t`/`time`/`run_elapsed_s` for time and `x,y,z` or `x_xml_m,y_xml_m,z_xml_m` for
position.

Important: `--fs` must match the OAI run's sample rate. For the 106 PRB / 30
kHz OAI RFsimulator config below, use `--fs 61.44e6`.

`MPLCONFIGDIR=/tmp/matplotlib` is included because some shared or containerized
systems do not allow Matplotlib to write to `~/.config/matplotlib`. It is not a
channel parameter; it only points Matplotlib's cache/config files at a writable
temporary directory.

### 2. Run OAI with the exported CIR

If your OAI checkout has the `sionna_rfsim` helper folder and the
`EXTERNAL_CIR` channel model, the easiest path is one terminal:

Run from the OAI repo's `sionna_rfsim` directory:

```bash
cd /path/to/openairinterface5g/sionna_rfsim
./run_validation.sh /path/to/sionna-rt-gui/cir_out/ap0_to_ue.cir
```

This script starts both OAI processes, runs a short RFsimulator phy-test, stops
them, and prints PASS/FAIL. A successful run should show that OAI loaded the
`.cir` file, stepped through snapshots over time, and the UE decoded.

For example:

```text
[OK]   OAI loaded the Sionna CIR file
[OK]   Channel stepped through snapshots as the clock advanced
[OK]   UE synchronized and decoded over the Sionna channel
VALIDATION PASSED - the Sionna channel is driving OAI.
```

The `Killed` line printed by the script is expected when it stops the OAI
processes after the validation window.

### 3. Manual OAI run

Use this only if you want to keep the gNB and UE running in separate terminals.
First point OAI's channel config at your exported file:

Run from the OAI repo's `sionna_rfsim` directory:

```bash
cd /path/to/openairinterface5g/sionna_rfsim
sed -i 's#cir_file *= *".*";#cir_file       = "/path/to/sionna-rt-gui/cir_out/ap0_to_ue.cir";#' channelmod_external.conf
```

Terminal 1, gNB:

Run from the OAI build directory:

```bash
cd /path/to/openairinterface5g/cmake_targets/ran_build/build
sudo ./nr-softmodem -O ../../../sionna_rfsim/gnb_external.conf \
    --gNBs.[0].min_rxtxtime 6 \
    --phy-test \
    --rfsim \
    --rfsimulator.[0].serveraddr server \
    --rfsimulator.[0].options chanmod
```

Terminal 2, UE:

Run from the OAI build directory:

```bash
cd /path/to/openairinterface5g/cmake_targets/ran_build/build
sudo ./nr-uesoftmodem \
    --rfsim \
    --phy-test \
    --rfsimulator.[0].serveraddr 127.0.0.1
```

You do not run `run_validation.sh` at the same time as the manual two-terminal
commands. Use either the one-terminal validation script or the two manual
terminals.

### Synthetic CIR files

These are useful for testing the OAI bridge without ray tracing:

Run from this `sionna-rt-gui` repo:

```bash
python scripts/make_test_cir.py unit-tap --out cir/unit_tap.cir --fs 61.44e6
python scripts/make_test_cir.py ramp --out cir/ramp.cir --fs 61.44e6 --n 60 --period 0.5 --pl-start 0 --pl-end -40
```

### Tests

Run from this `sionna-rt-gui` repo:

```bash
python -m pytest test/test_oai_cir_export.py
```


Limitations
-----------

The following features are not supported in the GUI at the moment:

- Mesh-based radio maps


Acknowledgements
----------------

This project uses the [Polyscope](https://polyscope.run) and [Dear ImGui](https://github.com/ocornut/imgui) libraries with the [Bess Dark](https://github.com/shivang51/bess/blob/a74d78e78ee4678b03582181905e00c1094c3d18/src/Bess/src/settings/themes.cpp) theme.
Sionna RT scenes use map data from [OpenStreetMap](https://www.openstreetmap.org/copyright).


License
-------

Copyright (c) 2025-2026 NVIDIA Corporation. Licensed under the Apache License 2.0. See [LICENSE](LICENSE) for details.
