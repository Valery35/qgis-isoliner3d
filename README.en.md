# Isoliner3D

[Русская версия](README.md) · **English**

[![Install in QGIS](https://img.shields.io/badge/Install%20in%20QGIS-blue.svg)](https://plugins.qgis.org/plugins/isoliner3d/)
[![Plugin page](https://img.shields.io/badge/Plugin%20page-0f766e.svg)](https://www.informpp.ru/%D0%B3%D0%BB%D0%B0%D0%B2%D0%BD%D0%B0%D1%8F-%D1%81%D1%82%D1%80%D0%B0%D0%BD%D0%B8%D1%86%D0%B0/qgis-isoliner3d)

A QGIS plugin that shows a geological model in three dimensions and computes
reserves from a block model: surfaces from rasters, watertight bed bodies,
boreholes, cross-sections, maps draped as textures.

![Relief with an OpenStreetMap texture draped over it and three beds as bodies underneath. All in one scene.](docs/screenshot.png)

Rendering runs on pyqtgraph and PyOpenGL bundled inside the plugin. The
built-in QGIS 3D view and Qt3D are not used, and there are no external
dependencies.

A companion to the [Isoliner](https://plugins.qgis.org/plugins/grid_isolines/)
kriging and contouring toolset and to [Topoliner](https://plugins.qgis.org/plugins/topoliner/), topology
cleaning. Together they cover the way from observation points to a
volumetric model: Isoliner builds grids and isolines, Topoliner tidies
the contours, Isoliner3D shows the result in three dimensions and
computes reserves.

## Why

A roof, a bottom, boreholes and a section exist separately and come together
only in the geologist's head. Isoliner3D assembles them into one scene: bed
bodies, borehole stems running through them, the section drawing in its
place in space and a map draped over the relief.

## The 3D window

- Surfaces from the project rasters, each in its own colour, with vertical
  exaggeration and Z spacing.
- Bed bodies from multiband grids: band 1 roof, band 2 bottom, a side skirt
  along the boundary of the actual data.
- Boreholes as stems, the intervals coloured by stratigraphic position, a
  mast with a label above the collar, labels thinned automatically.
- A section plane with the intersection trace over surfaces and a section
  contour over bodies.
- Polyhedra, TIN and MultiPolygon Z as volumetric bodies.
- Maps draped as a texture with shading from the normal: an orthophoto, a
  tiled basemap, a geological map with its own symbology. The resolution is
  set separately and does not depend on the mesh density.
- The section drawing draped onto the ribbon, several sections at once.
- Click query: the layer name, the coordinates, all band values, the
- A cube of values is shown as an isosurface at a cutoff: a closed body fit for volume computation.
- Shells in a table: level, colour and opacity per row, a cap at the cube edge.
- Cube clipping by surfaces: everything above the terrain or outside the bed is dropped before building.
- Export to GLB with the coordinate box, tick labels and the same colouring as on screen.
- A coordinate box: labelled ticks, a grid on chosen planes, a north arrow.
- Clipping by surfaces above and below: in the scene and in the block model.
- Cleaning an isosurface: smoothing the steps and dropping small parts.
- A body is cut by a contour, a corridor and a range of elevations, and the cut is capped.
- A cube of values is cut by a wall along a line: a vertical section coloured by value.
- A cube of values is shown as voxels: a cell as a box, coloured by grade interval. Only visible faces are built and neighbouring faces of one interval merge, so a cube of millions of cells stays light.
- Colour comes from the layer styling: a raster ramp, categories and graduated classes of a vector. A class unticked in the legend does not reach the scene.
- Points are shown as a circle, a square, a diamond, a triangle or a cross. The circle is on screen and reads at any distance, the flat shapes lie in plan and are hidden by a surface.
- Points are labelled from a layer field. Labels have a halo, are thinned and their number is capped.
- The scene lives in the project CRS: layers in other systems are reprojected, just as on the map canvas.
- The elevation of a vector layer comes from the geometry, from a field or from a surface. When draped, the value is read at every vertex, and where there is no data the feature is cut away.
- The layer order follows the map tree, the upper layer is drawn over the lower one. The list follows the tree by itself.
- Clipping the scene by a contour or a line: the piece inside, everything but it, a side of the line, a corridor of a given width along the profile. Both surfaces and vectors are cut.
- Markup right in the scene: a contour and a line are drawn by clicks on the surface and saved as a project layer.
- The scene is computed by the «Rebuild the scene» button, the visibility ticks only record what to show.
- A parallel projection and a top view as a plan.
  thickness.
- A PNG snapshot for reports.

## Tools

The Processing toolbox, the **Bed and block model** group. They compute on
NumPy and GDAL and need no kriging.

| Tool | What it does | Output |
|---|---|---|
| 1.01 Assemble a bed grid | A roof, a bottom and parameters into one raster | A bed grid |
| 1.02 Bed calculator | Thickness, volume, ore and metal tonnage, grade | A grid and an HTML report |
| 1.03 Bed grid to a block model | A centroid per cell, a vertical split of the column | Points |
| 1.04 Surfaces to 3D (meshes) | Export of grids to the 2DM format (MDAL) | Mesh layers |
| 1.05 Domains to a bed band | Area polygons as an extra grid band | A bed grid |
| 1.06 Reserve difference (write-off) | The difference of two block models per cell | Points |
| 1.07 Create sample data (demo) | Bodies with Z: a bed, a pile, a cube, a tetrahedron | A layer |
| 1.08 A map for a texture (demo) | A check map with a grid and fields | A raster |

The **Interpolation in three dimensions** group works with a cube of
values: a grid band is a horizontal level.

| Tool | What it does | Output |
|---|---|---|
| 2.01 Demonstration boreholes in three dimensions | A folded bed, a lens or a steep vein, sampled by intervals | Points |
| 2.02 Interpolation of points in three dimensions | Nearest neighbour and inverse distances with anisotropy | A cube of values |
| 2.03 Cube to a block model | A centroid per occupied cell, block size and volume | Points |
| 2.04 Cube body as voxels | A body above the cutoff as cell boxes, one feature per interval | MULTIPOLYGON Z |
| 2.05 Check of the interpolation | Leave one sample or one hole out, error and bias | Residual points |
| 2.06 Kriging in three dimensions | Weights from a variogram measured on the data | A cube and a variance cube |

A bed grid assembled by the first tool is read by the 3D window as a body:
computed and looked at right away.

## Performance

The grids that are read and the maps that are rendered are cached, so a
repeated scene rebuild comes from memory. On a scene of six surfaces and
312 thousand triangles that is 0.02 seconds instead of 0.77. Large grids are
thinned automatically while the shape of the surface is preserved.

The scene rebuild counters are shown in the window, and the breakdown by
phase (reading, meshes, colouring, vectors, scene assembly) goes to the QGIS
message log.

## Language

The interface is bilingual, Russian and English. The language comes from the
QGIS locale. Coverage is enforced by a test: a string without a translation
will not pass.

## The website page

The `site/` folder holds a self-contained page,
`isoliner3d_landing.html`: the figures are embedded in the file, the
language switch works without a reload, and there are no external requests.
It is built by `tools/make_figures.py` and `tools/build_site.py`.

## Installation

From the QGIS plugin catalogue or from a ZIP: **Plugins - Manage and Install
Plugins - Install from ZIP**. No QGIS restart is needed.

Requirements: QGIS 3.16 or newer, Qt5 or Qt6.

## Documentation

The PDF manual ships with the plugin: `isoliner3d/doc/Isoliner3D.pdf` (RU)
and `Isoliner3D_en.pdf` (EN). The **Plugins - Isoliner3D - Help** entry opens
it in the interface language.

The manual source: [manual/manual.md](manual/manual.md) and
[manual/manual_en.md](manual/manual_en.md), the PDF is built by
`manual/build_pdf.sh`.

Development rules: [AGENTS.md](AGENTS.md).
Change history: [CHANGELOG.md](CHANGELOG.md).

## Development

Headless tests, no QGIS required:

```
python isoliner3d/tests/test_mesh3d.py
python isoliner3d/tests/test_polyhedral.py
python isoliner3d/tests/test_viewer3d.py
python isoliner3d/tests/test_viewer3d_static.py
python isoliner3d/tests/test_i18n.py
python isoliner3d/tests/test_algorithms_static.py
python isoliner3d/tests/test_prof.py
python isoliner3d/tests/test_cache.py
python isoliner3d/tests/test_texmesh.py
python isoliner3d/tests/test_flakes.py
```

The core (`mesh3d.py`, `polyhedral.py`, `demo_map.py`) is pure NumPy with no
QGIS imports. `viewer3d.py` and `texmesh.py` import Qt, QGIS and pyqtgraph
lazily, so the modules load headless. `algorithms.py` imports QGIS at the
top level and is checked statically, by parsing the AST.

## License

GNU GPL version 2 or later, see [LICENSE](LICENSE).

© 2026 Inform++ LLC ([informpp.ru](https://www.informpp.ru/)).
