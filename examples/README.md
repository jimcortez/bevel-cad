# bevel-cad examples

A self-contained bevel project. Nothing here depends on being inside the bevel-cad
repository — copy the folder anywhere with `bevel-cad` installed.

```
bevel.yaml                      project config (formats, tolerances, viewer)
configs/button_label.yaml       default badge
configs/button_label_custom.yaml  same code, different text and hole
configs/spacer_washer.yaml      filleted standoff washer (inches)
src/button_label.py             build(cfg) -> two-body assembly (plate, text_fill)
src/spacer_washer.py            build(cfg) -> solid
renders/                        output bundles
```

```bash
cd examples
bevel list
bevel render button_label_custom --skip preview     # fast loop
bevel render spacer_washer spacer_washer.hole_diameter_in=0.3
bevel inspect renders/*/spacer_washer_*.stl
bevel render button_label --viewer                   # needs a running cadquery-web-viewer
```
