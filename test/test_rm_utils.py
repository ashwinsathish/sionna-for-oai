#
# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
import drjit as dr
import mitsuba as mi
import numpy as np
import pytest

from sionna_rt_gui.rm_utils import radio_map_texture, radio_map_colorbar_to_image


@pytest.mark.parametrize("db_scale", [True, False])
def test_radio_map_texture(db_scale: bool):
    rng = dr.random.Philox4x32Generator(seed=1234)

    rm_values = rng.uniform(mi.TensorXf, shape=(100, 100))
    texture, alpha = radio_map_texture(
        rm_values, db_scale=db_scale, rm_cmap="magma", vmin=-100, vmax=0
    )
    assert texture.shape == (100, 100, 3)
    assert alpha.shape == (100, 100)


def test_colorbar_image():
    image = radio_map_colorbar_to_image(cmap="magma", vmin=-100, vmax=0, dpi=100)
    # Exact width depends on the matplotlib version's text metrics (672 px on
    # some, 670 on others), so assert the shape loosely rather than pinning it.
    assert image.ndim == 3 and image.shape[0] == 66 and image.shape[2] == 4
    assert 650 <= image.shape[1] <= 700
    assert np.mean(image[:, :, :3]) > 0.15
    assert np.mean(image[:, :, -1]) > 0.3
