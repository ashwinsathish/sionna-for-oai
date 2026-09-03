Sionna for OAI
==============

Drive a **real 5G network stack with a ray-traced radio channel**.

This replaces OpenAirInterface's built-in statistical channel models (AWGN,
Rician, TDL) with a site-specific channel computed by
[Sionna RT](https://github.com/NVlabs/sionna-rt). You export the channel along
a receiver trajectory to a file, and OAI replays it while a gNB and a UE run a
real 5G link over it.

No radio hardware, no 5G core, no GUI needed — two processes on one machine and
text logs with SNR, BLER and throughput.

> Built on [NVlabs/sionna-rt-gui](https://github.com/NVlabs/sionna-rt-gui); the
> original interactive scene viewer is still here and documented in
> [`docs/GUI.md`](docs/GUI.md).


How it works
------------

```
Sionna RT scene              .cir file                 OAI rfsimulator
receiver moves along    ->   snapshots of the     ->   gNB  <-- IQ -->  UE
a trajectory                 channel over time         channel applied per snapshot
```

Each snapshot holds the sample-spaced channel taps plus the path loss and the
propagation delay at that instant. OAI steps through them as its clock advances,
so the link quality changes exactly as the receiver moves through the scene.

**This is offline replay:** the whole trajectory is ray-traced up front. Nothing
during the run can change the channel. That makes runs perfectly reproducible.


Requirements
------------

- Linux, Python 3.10+
- An NVIDIA GPU is recommended for ray tracing (CPU works, slower)
- ~40 GB disk and 20-40 minutes for the one-time OAI build


Setup
-----

**1. Python side**

```bash
git clone https://github.com/ashwinsathish/sionna-for-oai.git
cd sionna-for-oai
python3 -m venv .venv && ./.venv/bin/pip install -e .
```

**2. OAI side** (one command, then go get a coffee)

```bash
./scripts/setup_oai.sh
```

This clones a fork of OpenAirInterface that already carries the `EXTERNAL_CIR`
channel model and builds the gNB, the UE and the rfsimulator. OAI itself is not
bundled here — it is ~2.2 GB and has its own licence.

To build somewhere specific: `./scripts/setup_oai.sh /path/to/oai`


Testing it
----------

### The quick check (about a minute)

```bash
cd ../oai-sionna-channel/sionna_rfsim
./run_validation.sh
```

This runs a real gNB + UE link over a built-in test channel whose path loss
ramps from 0 to −40 dB, then prints:

```
[OK]   OAI loaded the Sionna CIR file: 60 snapshots, 16 taps, fs 61.440 Msps
[OK]   Channel stepped through 17 snapshots as the clock advanced
       t=0.80s -> snapshot 1/60:  path_loss  -0.7 dB
       t=8.50s -> snapshot 17/60: path_loss -11.5 dB
[OK]   UE synchronized and decoded over the Sionna channel
 VALIDATION PASSED - the Sionna channel is driving OAI.
```

The three checks mean: OAI is reading your channel file rather than a textbook
model; the channel changes over time as the receiver moves; and a real 5G link
ran over it. A `Killed` line is normal — that is the script stopping OAI.

### With a real ray-traced channel

Export a channel, then feed it to the same script:

```bash
# from this repo
./.venv/bin/python scripts/export_oai_cir.py --demo --out cir_out/ --fs 61.44e6

# then
cd ../oai-sionna-channel/sionna_rfsim
./run_validation.sh ~/sionna-for-oai/cir_out/ap0_to_ue.cir
```

`--demo` uses a built-in street-canyon scene. For your own scene and path:

```bash
./.venv/bin/python scripts/export_oai_cir.py \
    --scene path/to/scene.xml \
    --ap 10,0,7 --ap 30,0,7 \
    --line "0,0,1.5" "40,0,1.5" 100 \
    --fs 61.44e6 --period 0.1 --out cir_out/
```

`--line START END N` walks a straight path; `--csv file.csv` replays a recorded
trajectory with `x,y,z` columns; `--ap` is repeatable, one file per access point
is written.

**`--fs` must match OAI's sample rate.** For the bundled 106 PRB / 30 kHz config
that is `61.44e6`. Wrong `--fs` puts the taps at the wrong delays.


Licence
-------

Apache-2.0, inherited from
[NVlabs/sionna-rt-gui](https://github.com/NVlabs/sionna-rt-gui). OAI is
separately licensed and is not distributed here.
