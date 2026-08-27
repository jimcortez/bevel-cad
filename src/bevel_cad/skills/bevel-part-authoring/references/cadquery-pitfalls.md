# CadQuery / OCC pitfalls (learned on real prints)

## Booleans on closed sweeps corrupt the solid
Sweeping a profile around a **closed** path (rings, knots, loops) and then cutting or fusing
anything into it frequently yields an invalid/non-watertight result: OCC's boolean sees the
seam face twice. Fix at the *path* level: open the loop before sweeping (drop a short arc /
insert a gap at point level, then sweep an open path), then do booleans. Never boolean the
closed sweep itself.

## Guide-curve sweeps tilt the last section
Sweeping with an auxiliary spine (`makeSweep(..., auxSpine=...)`) along a torsional path can
tilt the final cross-section by tens of degrees. If the end face must be planar/perpendicular
(mating joints, pins), over-extend the path and trim the end with a plane cut afterwards.

## Fuse, then prove it is one lump
After fusing many solids, count solids (`len(shape.Solids())`). Two lumps that merely touch
export as one STL but print as two pieces. `bevel_cad.mesh.fuse.fuse_part_solids` raises on
that; `bevel inspect` reports `components`.

## Watertightness is a mesh property — check the mesh you export
`shape.isValid()` can be True while the tessellated STL has open edges. Always run
`bevel inspect <bundle>/<stem>.stl` (and the per-body STLs). `boundary_edges > 0` = leak.

## Chamfer/fillet ordering
Chamfer the outer perimeter *before* cutting pockets/holes into a face; afterwards the face
selector picks up pocket walls and the chamfer fails or spreads.

## `cadquery.func.box` is not centred on every axis
`box(w, l, h)` from the functional API sits with its base at z = 0. Use
`cq.Workplane("XY").box(...)` when you want an origin-centred block, or place shapes by
their own `BoundingBox()` rather than assuming symmetry.

## Compound volumes vs. per-solid volumes
`Compound.Volume()` and the sum of `Solid.Volume()` differ by ~0.1 % when solids touch.
Compare with a loose tolerance or sum the solids explicitly.

## Text
`text(label, size, font=...)` returns a compound of faces (one per glyph). Extrude it for
letters; centre by its bounding box (the compound is not centred at the origin). Missing
glyphs give empty geometry instead of an error.

## SLA/resin parts
Hollow or cupped geometry traps resin and creates suction; add vents/drain paths at the
lowest point of the printed orientation before calling a part done.

## Tolerances
`rendering.tolerance` (mm) / `angular_tolerance` control STL/GLB tessellation. 0.001/0.05 is
fine for prints; the viewer uses coarser `viewer.tolerance` for speed.
