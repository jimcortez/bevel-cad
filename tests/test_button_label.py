"""Tests for the button_label part and its spicy/family variant."""

from __future__ import annotations

import math

import pytest
from cadquery.func import box, circle, extrude, face, fuse, intersect, text, wire
from cadquery.occ_impl.shapes import Location

from types import SimpleNamespace

from bevel_cad.config import load_layers

from tests.conftest import load_example

button_label = load_example("button_label")
ButtonLabelParams = button_label.ButtonLabelParams
build = button_label.build
build_button_label = button_label.build_button_label
build_stacked_button_label = button_label.build_stacked_button_label

# Parameter sets of the label variants that live in a separate project (rando_parts).
button_label_power = SimpleNamespace(STACKED_TEXT="POWER")
button_label_spicy_family = SimpleNamespace(LEFT_TEXT="spicy", RIGHT_TEXT="family")
button_label_volume = SimpleNamespace(
    LEFT_TEXT="Volume", RIGHT_TEXT="", TEXT_SIZE_MM=5.0, HOLE_DIAMETER_MM=7.0,
    _DEFAULTS={"button_label": {**button_label.DEFAULTS["button_label"], "left_text": "Volume", "right_text": "",
                                "text_size": 5.0, "hole_diameter": 7.0}},
)

_P = ButtonLabelParams()
CHAMFER_MM = _P.chamfer
CORNER_RADIUS_MM = _P.corner_radius
FONT = _P.font
HOLE_DIAMETER_MM = _P.hole_diameter
LEFT_TEXT = _P.left_text
TEXT_DEPTH_MM = _P.text_depth
TEXT_RAISE_MM = _P.text_raise
MARGIN_MM = _P.margin
PLATE_HEIGHT_MM = _P.height
PLATE_THICKNESS_MM = _P.thickness
TEXT_SIZE_MM = _P.text_size
LETTER_GAP_MM = _P.letter_gap


def _text_width(label: str) -> float:
    return text(label, TEXT_SIZE_MM, font=FONT).BoundingBox().xlen if label.strip() else 0.0


def _layout(left: str, right: str) -> dict[str, float]:
    """Expected plate width and element centers for [left][hole][right] with margins around each element."""
    widths = [w for w in (_text_width(left), HOLE_DIAMETER_MM, _text_width(right)) if w > 0]
    plate_width = sum(widths) + 2.0 * MARGIN_MM * len(widths)
    x = -plate_width / 2.0
    centers = []
    for w in widths:
        x += MARGIN_MM
        centers.append(x + w / 2.0)
        x += w + MARGIN_MM
    hole_idx = 1 if left.strip() else 0
    return {"width": plate_width, "hole_cx": centers[hole_idx], "widths": widths, "centers": centers}


@pytest.fixture(scope="module")
def label_parts():
    return build_button_label()


@pytest.fixture(scope="module")
def label_solid(label_parts):
    return label_parts.plate


@pytest.fixture(scope="module")
def spicy_family_solid():
    return build_button_label(
        left_text=button_label_spicy_family.LEFT_TEXT,
        right_text=button_label_spicy_family.RIGHT_TEXT,
    ).plate


def _assert_fill_mates_with_plate(parts) -> None:
    """text_fill is a valid body that sits in the plate's pockets: flush with the front face,
    text_depth deep, no overlap with the plate, and plate + fill together close the pockets."""
    plate, fill = parts.plate, parts.text_fill
    assert fill.isValid()
    assert fill.Volume() > 0
    fbb = fill.BoundingBox()
    assert fbb.zmax == pytest.approx(PLATE_THICKNESS_MM + TEXT_RAISE_MM, abs=1e-6)
    assert fbb.zmin == pytest.approx(PLATE_THICKNESS_MM - TEXT_DEPTH_MM, abs=1e-6)
    pbb = plate.BoundingBox()
    assert fbb.xmin > pbb.xmin and fbb.xmax < pbb.xmax
    assert fbb.ymin > pbb.ymin and fbb.ymax < pbb.ymax
    assert intersect(plate, fill).Volume() == pytest.approx(0.0, abs=1e-6)
    assert fuse(plate, fill).Volume() == pytest.approx(plate.Volume() + fill.Volume(), rel=1e-4)
    # The proud portion above the front face is exactly text_raise tall and matches the pocket footprint.
    above = box(fbb.xlen + 10, fbb.ylen + 10, TEXT_RAISE_MM)
    abb = above.BoundingBox()  # cadquery.func.box is not centred on every axis; place it via its own bbox
    above = above.moved(Location((fbb.center.x - abb.center.x, fbb.center.y - abb.center.y, PLATE_THICKNESS_MM - abb.zmin)))
    # intersect() on a multi-solid compound only reports one lump; sum the letters.
    proud = sum(intersect(letter, above).Volume() for letter in fill.Solids())
    # OCC compound volumes differ from the per-solid sum by ~0.1%, hence the loose tolerance.
    assert proud == pytest.approx(fill.Volume() * TEXT_RAISE_MM / (TEXT_DEPTH_MM + TEXT_RAISE_MM), rel=5e-3)

    assy = parts.to_assembly()
    names = [name for name, node in assy.traverse() if node.obj is not None]
    assert {"plate", "text_fill"} <= set(names)


def _assert_hole_pierces(solid, hole_cx: float) -> None:
    probe = extrude(face(wire(circle(0.25 * HOLE_DIAMETER_MM))), (0, 0, 3 * PLATE_THICKNESS_MM))
    probe = probe.moved(Location((hole_cx, 0, -PLATE_THICKNESS_MM)))
    assert intersect(solid, probe).Volume() == pytest.approx(0.0, abs=1e-6)


def _assert_gap_is_solid(solid, gap_lo: float, gap_hi: float) -> None:
    """The strip between two adjacent elements is full-thickness material, inset from the front chamfer."""
    assert gap_hi - gap_lo == pytest.approx(2.0 * MARGIN_MM, abs=1e-6)
    gap_w = 2.0 * MARGIN_MM - 0.2
    probe_h = PLATE_HEIGHT_MM - 2.0 * (CHAMFER_MM + 0.2)
    probe = box(gap_w, probe_h, PLATE_THICKNESS_MM).moved(Location(((gap_lo + gap_hi) / 2.0, 0, 0)))
    assert intersect(solid, probe).Volume() == pytest.approx(gap_w * probe_h * PLATE_THICKNESS_MM, rel=1e-3)


def test_build_is_valid_single_solid(label_solid):
    assert label_solid.isValid()
    assert len(label_solid.Solids()) == 1


def test_bounding_box_matches_params(label_solid):
    bb = label_solid.BoundingBox()
    assert bb.xlen == pytest.approx(_layout(LEFT_TEXT, "")["width"], abs=1e-3)
    assert bb.ylen == pytest.approx(PLATE_HEIGHT_MM, abs=1e-3)
    assert bb.zlen == pytest.approx(PLATE_THICKNESS_MM, abs=1e-3)


def test_hole_pierces_plate_on_right(label_solid):
    lay = _layout(LEFT_TEXT, "")
    assert lay["hole_cx"] > 0  # hole sits in the right half
    _assert_hole_pierces(label_solid, lay["hole_cx"])


def test_gap_between_text_and_hole_is_two_margins(label_solid):
    lay = _layout(LEFT_TEXT, "")
    text_right = lay["centers"][0] + lay["widths"][0] / 2.0
    hole_left = lay["hole_cx"] - HOLE_DIAMETER_MM / 2.0
    _assert_gap_is_solid(label_solid, text_right, hole_left)


def test_back_face_is_flat_and_unchamfered(label_solid):
    """The bottom (-Z) face should be the full rounded-rect outline: no chamfer on the back."""
    plate_width = _layout(LEFT_TEXT, "")["width"]
    slab = box(plate_width, PLATE_HEIGHT_MM, 0.5).moved(Location((0, 0, 0.25)))
    corner_loss = (4.0 - math.pi) * CORNER_RADIUS_MM**2
    hole_loss = math.pi * (HOLE_DIAMETER_MM / 2.0) ** 2
    expected = (plate_width * PLATE_HEIGHT_MM - corner_loss - hole_loss) * 0.5
    assert intersect(label_solid, slab).Volume() == pytest.approx(expected, rel=1e-4)


def test_text_fill_mates_with_plate(label_parts):
    _assert_fill_mates_with_plate(label_parts)
    # The fill is the letters only: far less than a full-width slab of pocket depth,
    # but it is what closes the pockets (plate + fill has no pockets left).
    lay = _layout(LEFT_TEXT, "")
    text_w = lay["widths"][0]
    assert label_parts.text_fill.Volume() < text_w * PLATE_HEIGHT_MM * TEXT_DEPTH_MM
    text_cx = lay["centers"][0]
    slab = box(text_w, PLATE_HEIGHT_MM - 2 * (CHAMFER_MM + 0.2), TEXT_DEPTH_MM - 0.05)
    slab = slab.moved(Location((text_cx, 0, PLATE_THICKNESS_MM - TEXT_DEPTH_MM)))
    closed = fuse(label_parts.plate, label_parts.text_fill)
    expected = text_w * (PLATE_HEIGHT_MM - 2 * (CHAMFER_MM + 0.2)) * (TEXT_DEPTH_MM - 0.05)
    assert intersect(closed, slab).Volume() == pytest.approx(expected, rel=1e-3)


def test_spicy_family_fill_covers_both_words():
    parts = build_button_label(
        left_text=button_label_spicy_family.LEFT_TEXT,
        right_text=button_label_spicy_family.RIGHT_TEXT,
    )
    _assert_fill_mates_with_plate(parts)
    lay = _layout(button_label_spicy_family.LEFT_TEXT, button_label_spicy_family.RIGHT_TEXT)
    fbb = parts.text_fill.BoundingBox()
    # Fill spans from the left word to the right word, across the hole.
    assert fbb.xmin < lay["hole_cx"] - HOLE_DIAMETER_MM / 2.0
    assert fbb.xmax > lay["hole_cx"] + HOLE_DIAMETER_MM / 2.0


def test_material_removed_for_hole_and_text(label_solid):
    plate_width = _layout(LEFT_TEXT, "")["width"]
    prism_volume = plate_width * PLATE_HEIGHT_MM * PLATE_THICKNESS_MM
    hole_volume = math.pi * (HOLE_DIAMETER_MM / 2.0) ** 2 * PLATE_THICKNESS_MM
    assert label_solid.Volume() < prism_volume - hole_volume


def test_spicy_family_variant_layout(spicy_family_solid):
    left, right = button_label_spicy_family.LEFT_TEXT, button_label_spicy_family.RIGHT_TEXT
    lay = _layout(left, right)
    assert spicy_family_solid.isValid()
    assert len(spicy_family_solid.Solids()) == 1
    bb = spicy_family_solid.BoundingBox()
    assert bb.xlen == pytest.approx(lay["width"], abs=1e-3)
    assert bb.ylen == pytest.approx(PLATE_HEIGHT_MM, abs=1e-3)

    # Hole is between the two texts, with a two-margin solid strip on each side.
    (lw, hw, rw), (lc, hc, rc) = lay["widths"], lay["centers"]
    assert lc < hc < rc
    _assert_hole_pierces(spicy_family_solid, hc)
    _assert_gap_is_solid(spicy_family_solid, lc + lw / 2.0, hc - hw / 2.0)
    _assert_gap_is_solid(spicy_family_solid, hc + hw / 2.0, rc - rw / 2.0)


def test_volume_variant_small_text_and_hole_on_right():
    v = button_label_volume
    parts = build_button_label(
        left_text=v.LEFT_TEXT, right_text=v.RIGHT_TEXT, text_size=v.TEXT_SIZE_MM, hole_diameter=v.HOLE_DIAMETER_MM
    )
    plate, fill = parts.plate, parts.text_fill
    assert plate.isValid() and len(plate.Solids()) == 1

    text_w = text(v.LEFT_TEXT, v.TEXT_SIZE_MM, font=FONT).BoundingBox().xlen
    plate_width = 4.0 * MARGIN_MM + text_w + v.HOLE_DIAMETER_MM
    bb = plate.BoundingBox()
    assert bb.xlen == pytest.approx(plate_width, abs=1e-3)
    assert bb.ylen == pytest.approx(PLATE_HEIGHT_MM, abs=1e-3)

    # 7mm hole on the right, with its own margin to the plate edge.
    hole_cx = plate_width / 2.0 - MARGIN_MM - v.HOLE_DIAMETER_MM / 2.0
    assert hole_cx > 0
    probe = extrude(face(wire(circle(0.25 * v.HOLE_DIAMETER_MM))), (0, 0, 3 * PLATE_THICKNESS_MM))
    probe = probe.moved(Location((hole_cx, 0, -PLATE_THICKNESS_MM)))
    assert intersect(plate, probe).Volume() == pytest.approx(0.0, abs=1e-6)
    ring = extrude(face(wire(circle(v.HOLE_DIAMETER_MM / 2.0 + 0.5)), wire(circle(v.HOLE_DIAMETER_MM / 2.0 + 0.1))), (0, 0, 1.0))
    ring = ring.moved(Location((hole_cx, 0, 0.5)))
    assert intersect(plate, ring).Volume() == pytest.approx(ring.Volume(), rel=1e-3)  # material right outside the hole

    # Fill is the small "Vol" text, in the left half, flush with the front face.
    fbb = fill.BoundingBox()
    assert fill.isValid() and fill.Volume() > 0
    assert fbb.xmax < hole_cx - v.HOLE_DIAMETER_MM / 2.0
    assert fbb.xlen == pytest.approx(text_w, abs=1e-6)
    assert fbb.ylen < v.TEXT_SIZE_MM  # 5mm em size renders shorter than 5mm
    assert fbb.zmax == pytest.approx(PLATE_THICKNESS_MM + TEXT_RAISE_MM, abs=1e-6)
    assert fbb.zmin == pytest.approx(PLATE_THICKNESS_MM - TEXT_DEPTH_MM, abs=1e-6)
    assert intersect(plate, fill).Volume() == pytest.approx(0.0, abs=1e-6)


def test_power_variant_is_tall_with_stacked_letters():
    letters = list(button_label_power.STACKED_TEXT)
    parts = build_stacked_button_label(button_label_power.STACKED_TEXT)
    _assert_fill_mates_with_plate(parts)
    solid = parts.plate
    assert solid.isValid()
    assert len(solid.Solids()) == 1

    boxes = [text(ch, TEXT_SIZE_MM, font=FONT).BoundingBox() for ch in letters]
    max_h = max(bb.ylen for bb in boxes)
    column_h = len(letters) * max_h + (len(letters) - 1) * LETTER_GAP_MM
    plate_len = 4.0 * MARGIN_MM + HOLE_DIAMETER_MM + column_h

    bb = solid.BoundingBox()
    assert bb.xlen == pytest.approx(PLATE_HEIGHT_MM, abs=1e-3)  # skinny
    assert bb.ylen == pytest.approx(plate_len, abs=1e-3)  # tall
    assert bb.ylen > 2.0 * bb.xlen
    assert bb.zlen == pytest.approx(PLATE_THICKNESS_MM, abs=1e-3)

    # Hole at the top, centered on X.
    hole_cy = plate_len / 2.0 - MARGIN_MM - HOLE_DIAMETER_MM / 2.0
    probe = extrude(face(wire(circle(0.25 * HOLE_DIAMETER_MM))), (0, 0, 3 * PLATE_THICKNESS_MM))
    probe = probe.moved(Location((0, hole_cy, -PLATE_THICKNESS_MM)))
    assert intersect(solid, probe).Volume() == pytest.approx(0.0, abs=1e-6)

    # Each letter row has material removed from the top face (engraved), and the
    # gaps between rows are untouched full-thickness material.
    column_top = hole_cy - HOLE_DIAMETER_MM / 2.0 - 2.0 * MARGIN_MM
    pitch = max_h + LETTER_GAP_MM
    row_probe_vol = (PLATE_HEIGHT_MM - 2 * MARGIN_MM) * max_h * PLATE_THICKNESS_MM
    for i in range(len(letters)):
        row_cy = column_top - max_h / 2.0 - i * pitch
        row = box(PLATE_HEIGHT_MM - 2 * MARGIN_MM, max_h, PLATE_THICKNESS_MM).moved(Location((0, row_cy, 0)))
        assert intersect(solid, row).Volume() < row_probe_vol - 1.0
        if i + 1 < len(letters):
            gap_cy = row_cy - max_h / 2.0 - LETTER_GAP_MM / 2.0
            gap = box(PLATE_HEIGHT_MM - 2 * MARGIN_MM, LETTER_GAP_MM - 0.2, PLATE_THICKNESS_MM)
            gap = gap.moved(Location((0, gap_cy, 0)))
            expected = (PLATE_HEIGHT_MM - 2 * MARGIN_MM) * (LETTER_GAP_MM - 0.2) * PLATE_THICKNESS_MM
            assert intersect(solid, gap).Volume() == pytest.approx(expected, rel=1e-3)


def test_build_from_config_uses_button_label_block():
    cfg = load_layers(
        project_config=None, user_config=False,
        part_defaults=button_label_volume._DEFAULTS,
        dotlist=["button_label.left_text=Mute", "button_label.hole_diameter=9"],
    ).cfg
    assy = build(cfg)
    names = [name for name, node in assy.traverse() if node.obj is not None]
    assert names[:2] == ["plate", "text_fill"]
    plate = assy.children[0].obj
    text_w = text("Mute", button_label_volume.TEXT_SIZE_MM, font=FONT).BoundingBox().xlen
    assert plate.BoundingBox().xlen == pytest.approx(4.0 * MARGIN_MM + text_w + 9.0, abs=1e-3)


def test_negative_text_raise_rejected():
    with pytest.raises(ValueError, match="text_raise"):
        build_button_label(text_raise=-0.1)


def test_stacked_invalid_parameters_raise():
    with pytest.raises(ValueError, match="stacked_text"):
        build_stacked_button_label("  ")
    with pytest.raises(ValueError, match="text_size"):
        build_stacked_button_label("W", text_size=40.0)


def test_right_text_only():
    solid = build_button_label(left_text="", right_text="family").plate
    lay = _layout("", "family")
    assert solid.isValid()
    assert solid.BoundingBox().xlen == pytest.approx(lay["width"], abs=1e-3)
    assert lay["hole_cx"] < 0  # hole sits in the left half
    _assert_hole_pierces(solid, lay["hole_cx"])


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"left_text": "   ", "right_text": ""}, "left_text"),
        ({"text_depth": PLATE_THICKNESS_MM}, "text_depth"),
        ({"chamfer_mm": PLATE_THICKNESS_MM / 2.0}, "chamfer_mm"),
        ({"hole_diameter": PLATE_HEIGHT_MM}, "hole_diameter"),
        ({"corner_radius": PLATE_HEIGHT_MM / 2.0}, "corner_radius"),
        ({"text_size": 40.0}, "text_size"),
    ],
)
def test_invalid_parameters_raise(kwargs, match):
    with pytest.raises(ValueError, match=match):
        build_button_label(**kwargs)
