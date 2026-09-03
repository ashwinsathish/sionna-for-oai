#!/usr/bin/env bash
#
# Fetch and build the OAI side of the Sionna -> OAI channel bridge.
#
# The OAI source is NOT bundled in this repository: it is ~2.2 GB and carries
# its own licence. Instead we clone a fork of OpenAirInterface that already
# contains the EXTERNAL_CIR channel model (one commit on top of upstream
# `develop`), then build the two softmodems and the rfsimulator device.
#
# Usage:
#   ./scripts/setup_oai.sh                  # clone next to this repo and build
#   ./scripts/setup_oai.sh /path/to/oai     # clone/build at a chosen location
#
# Expect the first build to take 20-40 minutes. It needs sudo once, to install
# OAI's build dependencies.
set -euo pipefail

REPO_URL="${OAI_REPO_URL:-https://github.com/ashwinsathish/oai-sionna-channel.git}"
HERE="$(cd "$(dirname "$0")/.." && pwd)"
OAI_DIR="${1:-$(dirname "$HERE")/oai-sionna-channel}"

echo "=================================================================="
echo " OAI setup for the Sionna channel bridge"
echo "   source : $REPO_URL"
echo "   target : $OAI_DIR"
echo "=================================================================="

if [ -d "$OAI_DIR/.git" ]; then
  echo "[1/3] Existing checkout found, skipping clone."
else
  echo "[1/3] Cloning OAI (large: expect a few GB and several minutes)..."
  git clone "$REPO_URL" "$OAI_DIR"
fi

if [ ! -f "$OAI_DIR/sionna_rfsim/run_validation.sh" ]; then
  echo "ERROR: $OAI_DIR does not contain sionna_rfsim/."
  echo "       That folder carries the EXTERNAL_CIR patch and configs."
  echo "       Make sure you cloned the fork, not upstream OAI."
  exit 1
fi

echo "[2/3] Building gNB + UE + rfsimulator (20-40 min; sudo for dependencies)..."
cd "$OAI_DIR"
./cmake_targets/build_oai -I --gNB --nrUE -w SIMU --ninja

BUILD="$OAI_DIR/cmake_targets/ran_build/build"
for bin in nr-softmodem nr-uesoftmodem librfsimulator.so; do
  if [ ! -e "$BUILD/$bin" ]; then
    echo "ERROR: build finished but $bin is missing from $BUILD"
    exit 1
  fi
done

echo "[3/3] Build OK."
echo
echo "=================================================================="
echo " Done. Now run the end-to-end check:"
echo
echo "   cd $OAI_DIR/sionna_rfsim"
echo "   ./run_validation.sh"
echo
echo " It should print: VALIDATION PASSED"
echo "=================================================================="
