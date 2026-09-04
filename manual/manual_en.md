---
title: "Isoliner3D - a 3D window and volume tools for QGIS"
lang: en
toc-title: "Contents"
---

# What this is

![Relief with hillshading and three section fences across it, inside
a coordinate box with elevation labels.](images/viewer_fence_shaded.png){width=92%}

Isoliner3D shows the data of a project in three dimensions and computes
from it. Rasters become surfaces, multiband grids become watertight beds,
boreholes become coloured shafts, polygons with Z become bodies. Apart
from that there is a set of tools in the Processing panel: assembling a
bed grid, a block model, interpolation in volume, isosurfaces, volumes.

The module depends neither on the built-in 3D view of QGIS nor on Qt3D:
the drawing goes through libraries bundled with it, nothing extra to
install.

Interpolation in plan, contours, terrain and drawn sections stay with
the Isoliner plugin, of which Isoliner3D is a companion.

Requirements: QGIS 3.16 or newer, Qt5 or Qt6.

## Installation

**Plugins - Manage and Install Plugins - Install from ZIP**, choose
`isoliner3d.zip`. QGIS need not be restarted.

## Where to start

Without your own data: the tool **2.01 Demonstration boreholes in
volume** puts samples into the project, then **2.02 Interpolation of
points in volume** makes a cube out of them, and the viewer shows an
isosurface over that cube.

With your own: open the window from the toolbar, tick the layers in the
list and press refresh. A raster shows as a surface, polygons with Z as
a body.

# The data the module works with

The module handles several kinds of data, and half of the
misunderstandings come from mixing them up. Briefly: what each one is,
how it is stored in QGIS, who makes it and who consumes it.

## A surface

An ordinary raster where the value of a cell is an **elevation**: the
roof of a bed, the floor, the terrain, a water table. A single surface
has no volume: to get one a second surface is needed to bound the body
from below.

## A bed grid: a multiband raster

The same raster, but with several bands in an order that is the
convention of the module: **band 1 the roof, band 2 the floor**, then a
pair for every further bed. In a single-bed grid bands 3 and on are
parameters: grade, thickness, anything numeric.

A pair of bands is a body: their difference is the thickness, the
thickness times the cell area is the volume. That is why 1.02 can count
reserves and the scene can show a body.

A common confusion: **a bed grid is not a cube**. In a cube the bands
are levels along Z, in a bed grid they are the boundaries of a body.
Mistaking one for the other, the scene would draw a box at the zero
elevation, and it says so plainly.

## A cube of values

A raster whose bands are **horizontal slices along Z**, from the bottom
up. The Z layout - the elevation of the lowest slice and the step
between them - is written into the metadata, so the cube knows where it
stands in space.

A value in a cell of a cube is a parameter at a point in space: a
grade, a probability, a density. A cube is not a body: it is filled
with values everywhere, and a body appears once a cut-off is set.

## An isosurface

The boundary drawn through a cube at a given level: "where the grade
equals five per cent". A closed isosurface is a body, and a volume is
computed from it.

## Voxels

The same cube shown not by a smooth boundary but by the **little boxes
of the cells**. The difference is not in the data but in the honesty of
the display: an isosurface interpolates between the nodes and looks
smooth, a voxel shows exactly the resolution that exists.

Voxels also carry the boolean operations of 2.11: bodies are
rasterised into cells because an operation over cells always gives a
closed result.

## A block model

A layer of **points** - the centroids of the blocks - each with its own
fields: the volume of the block, the grade, the type of ore. This is
the familiar form of counting reserves: sum the volumes, weight the
grades, get the tonnage.

A block model is coarser than a cube by its nature: a block is either
wholly inside a contour or wholly outside. The difference between the
volume of the blocks and the volume of the shell is the measure of that
coarseness, and 2.12 prints it.

## A shell, that is, a body

A layer of **polygons with height** (MultiPolygonZ) where every polygon
is a triangle of the surface of a body. A closed shell bounds a volume,
and the volume is computed by an exact formula over the shell itself,
without cells.

The key property is **closedness**. A shell that is not closed has no
inside, no volume can be computed from it, and the tools refuse it. The
`closed` field in the attributes shows this for every body.

## Drawings on sections

Polygons and lines with real Z lying in the plane of a section. A
polygon is a body: the ring runs along the roof one way and along the
floor back, and two surfaces are taken from it (2.08). A line is one
surface (2.10).

The position of the sections is nowhere set: it is entirely in the
geometry, in the vertices. **A flat drawn section is no good**: its X
and Y are coordinates on the sheet, and there are no elevations at all.
The geometry type must be `PolygonZ` or `LineStringZ`.

## Holes and samples

Points with height and numeric fields. For interpolation what matters
is not the point as such but that the samples of one hole lie along a
stem: neighbours half a metre away along it and tens of metres away to
the side. That is why the check 2.05 can leave out a whole hole - an
estimate over a single sample flatters the model several times over.

## A texture

A picture of a map stretched over a surface in the scene: a plan, a
satellite image, a drawing. It is display only - nothing is computed
from a texture - but it shows where the model falls against a familiar
picture.

## An area mask

A polygon the result of the interpolation is clipped by. Between the
sections and beyond the data the surface goes where the interpolation
drew it; the mask says how far to trust that. In 2.08 and 2.10 a mask
can be tied to a particular bed or surface, or the tool can be asked to
take the area from the data themselves - the convex hull of their own
samples.

# The viewer

The list of project layers with checkboxes is on the left, the scene on
the right. A tick says what to show; the scene is built by the refresh
button, not by the tick itself - on a large project a rebuild takes
seconds, and doing it on every click is pointless.

Mouse: the left button rotates, the wheel zooms, the middle one pans.

## The coordinate system

The scene works in the coordinates of the project. The origin is shifted
to the middle of the extent of all visible layers: without that, numbers
of six digits lose precision on the graphics card and the model starts
to shiver.

The vertical scale is one for the whole scene. A common origin and a
common factor are computed over all visible layers at once and applied
alike to rasters, polygons, lines and points. That is why a section
fence lies on the surface it was built from at any exaggeration.

**Vertical exaggeration** stretches the elevations. It is a way of
looking, not a property of the data.

## Scene properties

Opened by a button on the toolbar. The sections are **View**,
**Clipping**, **Appearance** and **The coordinate box**. All the
settings are saved into the project.

Hillshading is not decoration: a surface coloured by a ramp is drawn
with vertex colours and no light at all, so the relief within one shade
is lost. The gradient background is on by default.

For a bed grid the **height band** is read as a place in the stack: a
roof band shows that bed and everything below it, a floor band shows
that bed and everything above it.

Bodies are lit by three sources. With a single one everything turned
away from it falls into shadow completely, and half of a bed body is
just that - the side walls and the floor - so the scene comes out dark.
The main source draws the shape, the second lights from the other side
at half strength, the third from below keeps the bottom from sinking.
The hillshading keeps a single source: with three it goes flatter, and
the relief within one shade of the ramp reads worse.

## The centre of rotation

The scene turns about the centre of the extent of the data, and that is
no way to look at a single detail: it leaves the frame faster than it
turns. A **right click** on the scene moves the centre of rotation to
the point you pointed at.

The picture does **not** change: the place of the camera is derived
from the centre, the distance and two angles, so a plain move of the
centre would carry the view away. Here the distance and the angles are
recomputed back, and the camera stays exactly where it was. Only the
point the rotation goes about changes. A right click **beyond the area of the data** puts
the centre back on the whole scene - that is the "show me everything".
A click that misses the object but falls within the area leaves the
centre alone: that is an ordinary near miss on a thin body, and a reset
there would look like the view walking off on its own. The boundary is
drawn with a quarter of the extent to spare.

If the scene fills the frame and there is no way to click beyond the
area, use **Centre of rotation - the whole scene** in the menu of the
scene list.

To look at a detail: fly to the layer, right-click the place, switch
the orbit on. The rotation will go about the chosen point.

The right button is taken only on a click without movement: on a drag
the camera still keeps it. In drawing mode the right button undoes the
last vertex, and the centre is not moved there.

## Fly to and orbit

The right button on a row of the scene list offers **Fly to** and
**Orbit the current centre**. On a large site there is no way to find a small
object: it takes up a pixel, and spinning about the common centre of
the scene only leads away from it. Flying moves the centre of rotation
onto the layer itself and takes the distance of the camera from its
extent; orbiting aims at nothing: it turns about the current
centre. Were it to aim at the layer, the centre chosen by a click
would be wiped out.

The extent is taken from the layer and converted into the coordinates
of the scene: the scene lives shifted, its centre stands at zero, and
an extent taken as it is would lead the camera away by the whole shift.

## Layer properties

Opened by a double click on a layer in the list. Only the fields that
work in the chosen mode are shown.

## Where the colour comes from

The scene asks the data itself, in this order: the **`color`** field if
the layer has one, then the layer symbology asked per feature, then a
single colour for the whole layer.

# Isosurfaces and voxels

A cube of values is a multiband grid where a band is a horizontal level.
Tools 2.02, 2.06 and 2.07 write such grids.

Shells are set in a table: a row per level with its colour and opacity.
**Cap where the body meets the cube edge** closes the shell where the
body runs into the boundary; without it no volume can be computed.

The button on the toolbar puts the shells into a project layer, splitting
them into connected bodies and computing the volume of each. The volume
is computed by an exact formula over a watertight shell, not by summing
cells: the shell cuts the edge cells in half.

The button takes two modes: an isosurface over a cube and a bed body.
For a bed body every pair of bands gives its own body, and the level
field holds the number of the roof band. The body is built afresh
rather than taken from the scene: what is shown has its vertical
stretched by the exaggeration, the layers spaced down Z and the mesh
thinned to a vertex budget, so the volume of such a body is wrong by
exactly the factor the vertical is stretched by. The clipping, however,
is the one set in the scene.

The **holes** field counts torn edges - with them the volume is
meaningless. The **pinch** field counts self-touches, which do not
affect the volume.

# Exporting the scene

A button on the toolbar writes the scene to a file, the format chosen by
the extension. **GLB** carries colour and transparency and is good for
viewing; **STL** and **OBJ** are for CAD, where a watertight shell is
needed to make a solid from.

The spin button walks the camera around the model; the capture button
writes a full turn as PNG frames.

# The tools

All of them live in the Processing panel, in the groups **1. Bed and
block model** and **2. 3D interpolation**.

## 1.01 Assemble a bed grid



| Field | What it sets |
|---|---|
| **Roof (raster)** | The grid of the bed roof. Elevations in metres; the step and extent must match the floor, or there is nothing to compute the thickness from. |
| **Floor (raster, optional)** | The grid of the floor. Where the floor is above the roof the thickness comes out negative and the cell becomes a gap. |
| **Floor at the elevation, m** | Build the surface downwards to a constant elevation. That turns a DEM into a body that can be subtracted and intersected: mined-out parts of a pit, spoil heaps. Where the surface is NOT ABOVE the elevation there is no body, and such cells are cleared - otherwise the volume would be counted with a negative thickness. |
| **Or a thickness downwards, m** | Build downwards by a constant thickness from the surface itself. It suits a layer of even thickness: overburden, topsoil, fill. |
| **Parameters (rasters, band 1 is taken)** | Extra grids that will become separate bands: grade, density, domain. The first band of each is taken. |
| **Bed grid** | A multiband grid: band 1 the roof, band 2 the floor, then the parameters. Every other tool and the viewer read this order. |
| **Roof band** | The roof band in the source grid. Needed when the roof is not the first band but sits inside a multiband one. |
| **Bottom band** | The floor band in the source grid. Needed when the floor sits inside a multiband one. |

## 1.02 Bed calculator

| Field | What it sets |
|---|---|
| **Bed grid (band 1 roof, band 2 bottom)** | The bed grid from 1.01. The first band is the roof, the second the floor, and the thickness follows from them. |
| **Content band (empty - no content)** | The grade band. Empty means computing only volume and thickness, without reserves. |
| **Ore density, t/m³** | The ore density. The volume is multiplied by it to get mass: without it the report is in cubic metres rather than tonnes. |
| **Reserve contour (polygons, optional)** | Polygons outside which cells do not enter the computation: a computation block, a licence area. |
| **Bed grid with thickness and reserves** | The same bed grid with added bands of thickness and reserves per cell. |
| **Report (HTML)** | A summary over the contour: area, volume, mass, mean grade. Opens in a browser. |

## 1.03 Bed grid to a block model

| Field | What it sets |
|---|---|
| **Bed grid (band 1 roof, band 2 bottom)** | The bed grid from 1.01. The column between the roof and the floor is split into blocks. |
| **Ore density, t/m³** | The ore density, when there is no band for it. The block volume is multiplied by it. |
| **Reserve contour (polygons, optional)** | Polygons outside which blocks are not written out: a computation block, a licence area. |
| **Block model (centroids)** | A centroid point per block with its size, volume and mass. The usual QGIS vector machinery works from there. |
| **Density band (empty - use the value above)** | The density band in the grid. Empty means taking the single value set above for the whole bed. |
| **Vertical layers (column split)** | How many blocks to split the column into vertically. One block gives a model without vertical division, and the whole thickness then falls into a single layer. |

## 1.04 Surfaces to 3D (meshes)

| Field | What it sets |
|---|---|
| **Surface grids** | The grids to be given out as meshes. Each becomes a separate 2DM file. |
| **Z scale (vertical exaggeration)** | Vertical exaggeration. A bed of one metre over a kilometre cannot be seen without it, but volume can no longer be computed on such a mesh. |
| **Z offset** | A shift of all elevations along the vertical. Needed to separate the beds of a pile and see them apart. |
| **Z spacing (step per next grid)** | The spread of surfaces along the vertical. Otherwise the beds of a pile lie flush and fight for depth. |
| **Folder for meshes (2DM)** | Where to put the files. The file name is taken from the grid name. |
| **Node thinning (every Nth)** | Thinning of the nodes. Every second node is four times fewer triangles, and the shape of the bed looks the same. |
| **Elevation band (Z)** | The elevation band in the grid. For a bed grid it is the roof or the floor, depending on what to show. |

## 1.05 Domains to a bed band

| Field | What it sets |
|---|---|
| **Bed grid** | The bed grid a domain band will be added to. |
| **Domain polygons** | Domain polygons: ore types, sites, zones. A cell takes the code of the domain it falls into. |
| **Bed grid with a domain band** | The same grid with an added domain band. Filters for the computation and colouring of the scene work from it. |
| **Domain code field (numeric, optional)** | The numeric field with the domain code. Empty means numbering the polygons in order. |

## 1.06 Reserve difference (write-off)

| Field | What it sets |
|---|---|
| **The "before" model (centroids)** | The block model at the start of the period. Comparison goes by matching blocks, so both models must be built on one grid. |
| **The "after" model (centroids)** | The block model at the end of the period. A block absent from it counts as mined out entirely. |
| **Difference (centroids)** | Centroids with the difference per block. The sum of the field over the layer is the write-off for the period. |
| **Reserve field** | The reserve field whose difference is computed: mass, volume, metal. |

## 1.07 Create sample data (demo)

| Field | What it sets |
|---|---|
| **Example** | What exactly to create: a bed body, a pile of folded beds, a cube or a tetrahedron. The map for a texture has moved to the separate tool 1.08. |
| **Extent (map view) - placement and size** | Where to put the example and of what size. Empty means taking the extent of the view window. |
| **Thickness, map units** | The bed thickness in map units. Whether the body is visible at the usual vertical scale depends on it. |
| **Bed body resolution (cells per side)** | How many cells the side of the body is split into. Finer means a smoother shape and more triangles. |
| **Output as TIN (triangulate)** | Triangulate the body. Without it the faces come out quadrilateral, and not every viewer shows those. |
| **Body (demo)** | A layer with bodies: polygons with Z, fit for the scene and for volume computation. |
| **Base elevation (floor), map units** | The elevation of the floor. The pile is built upwards from it. |
| **Beds in the suite** | How many beds in the pile. Each lies as its own body with its own grade. |

## 1.08 A map for a texture (demo)

| Field | What it sets |
|---|---|
| **Extent (when no grid is set)** | The bounds of the map when no grid is set. Empty means taking the extent of the view window. |
| **Map: by the extent of a grid (raster)** | The raster whose extent the map is made to. Needed so the texture lands exactly on an existing grid. |
| **Map (demo)** | A picture for a texture: it can be stretched over a surface in the viewer. |
| **Map: image side, pixels** | The side of the picture in pixels. Larger means a sharper texture and a heavier file. |
| **Map: graticule cells** | How many cells of the coordinate grid to draw on the map. |
| **Map: bed fields** | How many bed fields to draw on the map. |

## 2.01 Demonstration boreholes in three dimensions

| Field | What it sets |
|---|---|
| **Deposit type** | A folded and dipping bed shows the main point: cube levels cut the deposit across. A lens is isotropic and the simplest, a vein is the opposite extreme. |
| **Holes** | The grid is jittered rather than regular: a regular one gives interpolation too easy a task. |
| **Sample length, m** | A sample longer than the thickness of the deposit will miss it between the readings. On a bed of twenty six metres, ten metres is already a lot. |
| **Site extent** | The site the boreholes are placed on. Empty means a kilometre from the origin, which is written to the log. |
| **Surface elevation, m** | The mean elevation of the ground surface. Collars are placed on a gentle relief around it. |
| **Drilling depth, m** | The drilling depth down from the surface. The proportions of the body are taken from it as well. |
| **Sampling noise, a share** | The share of lognormal sampling noise. Zero gives data without noise, where the model itself is visible. |
| **The random seed** | The same seed gives the same data: with it methods can be compared on an unchanged sample set. |
| **Samples with grades** | Samples with the fields hole, from_m, to_m, grade, truth, zone. |
| **Core grade above background** | The core grade above background. The boundary of the body is where the grade falls to half of it. |
| **Background in the host rock** | The background in the host rock. The cutoff that separates the body is computed from it and from the core grade. |
| **Overall grade trend, a share** | The overall grade trend across the site. It is there so the data does not reduce to a single body. |
| **Share of holes stopped short** | The share of holes stopped short. It is there so the cube has places without data, as on real exploration. |
| **Hole inclination, degrees** | The tilt of the holes from the vertical. Zero gives vertical boreholes. |

## 2.02 Interpolating points in 3D

Computes a value at the nodes of a volume grid from points with elevation.

Anisotropy is the ratio of the vertical scale to the horizontal one. Without it the nearest point turns out to be the neighbouring borehole rather than the neighbouring sample at the same place in plan.

Nodes with fewer points within the radius than needed stay a gap: emptiness beats an invented value.

Neighbours are gathered by sectors: the circle around the node is split into equal parts and each gives its share of the nearest points. Without this, under anisotropy all the neighbours land in one borehole, because a sample in the hole is hundreds of times closer than the neighbouring hole, and inverse distances degenerate into nearest neighbour. One sector switches the split off.

The elevation source is set separately. A flat layer gives a zero Z at every point, so taking it from the geometry will not do: all the samples would land in one plane. An elevation field suits a computed elevation, and depth below a surface suits samples that record a depth rather than an elevation. A point whose elevation could not be obtained is left out, and the number of those is written to the log.

| Field | What it sets |
|---|---|
| **Points with an elevation** | The layer of samples. The elevation comes from the geometry, from a field or from a surface, which is set below. |
| **The value field** | The numeric field whose value is spread through the cube: grade, concentration, moisture. On the demonstration data from 2.01 it is grade rather than hole: otherwise the cube comes out of borehole numbers. |
| **Elevation source** | A flat layer gives a zero Z at every point. Taking it from the geometry would put every sample in one plane and the cube would be meaningless. |
| **Elevation or depth field** | For elevation from a field this is the elevation itself, for depth it is the depth measured down from the surface. |
| **Surface the depth is measured from** | The grid the depth is measured from. Needed by soil and similar samples, which record a depth rather than an elevation. |
| **The method** | Nearest neighbour gives steps and suits checking the data. Inverse distances give a smoothed field. |
| **Step in plan, m (0 means from the data)** | Zero takes a fifth of the distance between places in plan. Finer is pointless: there is no data in between anyway, and the node count grows as a square. |
| **Vertical step, m (0 means from the data)** | Zero takes half the sampling step. Coarser means merging neighbouring samples and losing the difference with depth. |
| **Largest number of points (0 means from the data)** | Zero takes one more than the number of samples at one place in plan. More means mixing all the levels at once and smoothing an anomaly with depth away. |
| **A cube of values** | A multiband grid: a band is a horizontal level, and the elevation of the first level and the step go into the metadata. |
| **Anisotropy (0 means from the data)** | Zero measures the variogram on the data and takes the ratio of the vertical range to the plan one. This is the case where no guessing is needed. A value of your own sets the scale by hand: a large one smooths along the vertical, a small one keeps the difference with depth. |
| **The search radius, m (0 is automatic)** | Zero takes a quarter of the data extent. A node with too few points within the radius stays a gap. |
| **The power of the inverse distances** | The larger the power, the more a near point outweighs the far ones. Two is the usual choice. |
| **The smallest number of points** | A node with fewer points within the radius than this stays a gap: emptiness beats an invented value. |
| **Search sectors (0 means from the data)** | Zero takes it from the data: boreholes need the split, or all the neighbours land in one hole, while for samples in plan it only tears the field. A sector boundary runs as a ray from the node, and the set of neighbours changes across it in a jump: hence the stars on soil samples. |

## 2.03 Cube to a block model

| Field | What it sets |
|---|---|
| **Cube of values (bands are levels)** | A cube of values from 2.02: bands are levels, the elevation of the first level and the step live in the metadata. |
| **Apply the cutoff** | Without a cutoff every cell with data is written out, with one only those not below it. |
| **Cutoff** | The value below which a cell does not reach the model. |
| **Computation contour** | Polygons outside which cells are not written out: a computation block, a licence area. |
| **Clip above (surface)** | The surface above: the points below it stay. That is how everything above the ground surface or above the bed roof is cut off. |
| **Clip below (surface)** | The surface below: the points above it stay. Together with the upper one only the bed is left. |
| **Block model** | A centroid point per occupied cell with the block size, volume and value. |
| **Colour intervals (0 means no classes)** | How many intervals to split the value into. The interval number goes into the cls field and suits colouring. |
| **Density, t/m3 (0 means no conversion)** | With a density given, mass is added to every block in the dens and ore_t fields. |

## 2.04 Cube body as voxels

| Field | What it sets |
|---|---|
| **Cube of values (bands are levels)** | A cube of values from 2.02: bands are levels, the elevation of the first level and the step live in the metadata. |
| **Cutoff** | A cell not below the cutoff counts as a body. For the demonstration data the cutoff is printed by 2.01. |
| **Computation contour** | Polygons outside which cells do not reach the body: a computation block, a licence area. |
| **Colour intervals (0 means a single body)** | Zero builds one body. Several intervals give a feature each, and the body can be coloured by grade. Not read when own bounds are given. |
| **Own interval bounds, space separated** | Own interval bounds, space separated: 0 5 10 15. They set the split instead of equal shares. A comma inside a number is a decimal mark. Order and repeats do not matter. A cell above the last bound stays in the last interval, it must not be lost. |
| **Interval names, comma separated** | Interval names, comma separated: low, medium, high. They go into the name field. Missing ones stay empty, extra ones are dropped. |
| **Merge neighbouring faces** | Merging makes the layer many times lighter but tears the boundary of the body with T-junctions. Such a body can neither be measured by volume nor cut in the scene: the cut stays open, there is nothing to cap it with. For volumes and cuts clear the flag. |
| **Remove edge pinches** | A pinch is two cells touching along a single diagonal. It is not a hole, but its edge belongs to four faces and a watertightness check rejects such a body. |
| **Body as voxels** | MULTIPOLYGON Z, one feature per colour interval. Fields cls, vmin, vmax, faces and shell. |

## 2.05 Check of the interpolation

| Field | What it sets |
|---|---|
| **Points with an elevation** | The same layer of samples that goes into 2.02. The check runs on the samples themselves, no cube is needed for it. |
| **The value field** | The value field the cube is built from. That is what we check. On the demonstration data from 2.01 it is grade. |
| **Elevation source** | The elevation source must match the one set in 2.02, otherwise a different arrangement of points is checked. |
| **Elevation or depth field** | For elevation from a field this is the elevation itself, for depth it is the depth measured down from the surface. |
| **Surface the depth is measured from** | The grid the depth is measured from. The same one as in 2.02. |
| **Borehole field (empty means one sample at a time)** | The borehole number. With it the whole hole is removed from the set and the check measures the ability to hit between holes. Without it one sample is removed, the neighbours come from the same hole, and the error comes out several times smaller than the real one. |
| **The method** | The method you intend to use in 2.02. The check is there to choose between them by numbers rather than by eye. |
| **Largest number of points (0 means from the data)** | Zero takes one more than the number of samples at one place in plan. This is the same choice as in 2.02. |
| **Check residuals** | Samples with the fields value, model, resid and aresid. They show not only how large the miss is but where it happened. |
| **The anisotropy (vertical to horizontal)** | The ratio of the vertical scale to the horizontal one. It is picked exactly by the error of this check. |
| **The search radius, m (0 is automatic)** | Zero takes a quarter of the data extent. A sample with no points around it stays unchecked. |
| **The power of the inverse distances** | The power of inverse distances. It is picked by the error of this check together with the anisotropy. |
| **The smallest number of points** | A sample with fewer points around it than this stays unchecked and does not enter the error. |
| **Search sectors (0 means from the data)** | Zero takes it from the data: boreholes need the split, or all the neighbours land in one hole, while for single samples in plan it only tears the field. |

## 2.06 Kriging in three dimensions

| Field | What it sets |
|---|---|
| **Points with an elevation** | The same layer of samples that goes into 2.02. The elevation is set below in the same way. |
| **The value field** | The numeric field whose value is spread through the cube. On the demonstration data from 2.01 it is grade. |
| **Elevation source** | A flat layer gives a zero Z at every point. Taking it from the geometry would put every sample in one plane and the cube would be meaningless. |
| **Elevation or depth field** | For elevation from a field this is the elevation itself, for depth it is the depth measured down from the surface. |
| **Surface the depth is measured from** | The grid the depth is measured from. Needed by samples that record a depth rather than an elevation. |
| **Reference surface (flattening)** | The roof or the floor of the bed. With it the vertical is counted from the surface and the computation runs along the bedding. The variogram is measured in the flattened coordinates already: measuring it in absolute ones and computing in flattened ones would give a model that does not belong to this data. |
| **Floor for the thickness fraction** | The second surface. With it the elevation becomes a fraction of the thickness: zero at the roof, one at the floor. |
| **Step in plan, m (0 means from the data)** | Zero takes a fifth of the distance between places in plan. Finer is pointless: there is no data in between anyway, and the node count grows as a square. |
| **Vertical step, m (0 means from the data)** | Zero takes half the sampling step. Coarser means merging neighbouring samples and losing the difference with depth. |
| **Neighbours per node** | Neighbours per node. Kriging solves a system the size of their number, so the cost grows as a cube: sixteen is the usual choice, thirty two is already noticeably dearer. |
| **Measure the variogram on the data** | The variogram is measured on the data itself: the range from the plan measurement, the nugget from the vertical one. Setting three numbers by eye is pointless, measuring them was the whole idea. |
| **A cube of values** | A cube of values: a band is a horizontal level. |
| **Cube of the estimation variance** | A cube of the estimation variance, of the same size. Zero at a sample, growing away from the data. It is a map of trust, and it is the one thing kriging always gives, whatever the density of the grid. |
| **Variogram model** | The kind of model. The difference between them is small, what matters more is the behaviour near zero: the gaussian one gives too smooth a field where the data is noisy. |
| **Nugget effect** | The scatter that does not fall even between neighbouring samples: sampling error and variability finer than the grid. Read only when the automatic measurement is off. |
| **Sill** | The overall scatter of the data the variogram reaches at large distances. |
| **Range, m** | The distance beyond which samples know nothing about each other. |
| **Anisotropy (0 means from the data)** | Zero takes the ratio of the vertical range to the plan one, measured on the data. This is the case where no guessing is needed. |
| **The search radius, m (0 is automatic)** | Zero takes a quarter of the data extent. A node with too few points within the radius stays a gap. |
| **Search sectors (0 means from the data)** | Zero takes it from the data: boreholes need the split, or all the neighbours land in one hole, while for samples in plan it only tears the field. A sector boundary runs as a ray from the node, and the set of neighbours changes across it in a jump: hence the stars on soil samples. |

## 2.07 MBA in volume

Builds a cube of values from scattered points with multilevel B-splines.

A coarse lattice approximates the data, the residual is approximated by a lattice twice as fine, and so on level by level. No system of equations is solved: the work is linear in the number of points, and on hundreds of thousands of measurements the method computes where kriging stalls.

The method approximates rather than estimates. It does not hit the measured values exactly and gives no estimation error. Next to kriging it is good as a trend, which is then refined by kriging the residuals.

Beyond the cloud of points the surface goes anywhere: the edge coefficients have no data. Clip the result by a contour or by surfaces.

| Field | What it sets |
|---|---|
| **Points with an elevation** | Measured points: borehole samples, intervals, anything with an elevation and a value. |
| **The value field** | The field with the value spread through the volume. |
| **Elevation source** | Where the elevation of a sample comes from: the geometry height, a field, or a depth below a surface. |
| **Elevation or depth field** | The field of elevation or depth, when it is not in the geometry. |
| **Surface the depth is measured from** | The surface the depth is measured from. |
| **Initial lattice in plan** | The initial lattice in plan: the method starts from it and doubles it at every level. A finer start gives a better first approximation but takes more memory. |
| **Initial lattice down the vertical** | The initial lattice down the vertical. Exploration data is elongated and the lattice need not be cubic: kilometres in plan and metres in thickness are different things. A smaller number here both stretches the influence along the bed and saves memory. |
| **Levels** | How many times to double the lattice. Every level picks up what the previous one could not: the residual falls fast, while the memory of the last level grows as a cube. |
| **Cube step in plan (0 means from the data)** | The cube step in plan. Zero takes it from the sampling net. |
| **Cube step down the vertical (0 means from the data)** | The cube step down the vertical. Zero takes it from the net. |
| **A cube of values** | A multiband grid: a band is a horizontal level of the cube. It is read by 2.03, 2.04 and the scene. |
| **Stop by residual (0 means all levels)** | Stopping by residual: once the largest deviation from the measured values falls below it, no further levels are built. Zero means build them all. |
| **Smallest value (empty means no bound)** | The smallest possible value: a grade is never below zero, while the method does leave the range. What leaves is pressed to the bound, and a plateau appears where the overshoot was - the shape is lost there. Leave it empty if there is no bound. |
| **Largest value (empty means no bound)** | The largest possible value. The number of clamped nodes goes to the log: it shows whether the model is any good. |
## 2.08 Beds from sections

Builds a grid of beds from the outlines drawn on sections.

Every ring runs along the roof one way and along the floor back, so two surfaces are taken from it. They are interpolated over the area with multilevel B-splines, and the space between the sections is filled.

The position of the sections is taken from the geometry itself, from the vertices of the outlines. The lines of the sections need not be given separately. A flat drawn section is no good: it has no real elevations.

The output is a multiband grid: a roof and a floor per bed. The scene shows such a grid as a bed body, and 1.02 and 1.03 compute the thickness, the blocks and the volumes from it.

The floor of the upper bed and the roof of the lower one are one and the same boundary if the geologist drew them as one line. Such a boundary is built once from both sets of points: built separately, they drift apart between the sections, and the model gets a gap or an overlap that the section does not have. The threshold of the gluing is set by the tolerance.

The area mask clips the result: between the sections there is no data, and the mask says how far to trust the surfaces.

Between the sections the surface goes where the interpolation put it: there is no data there. Where the sections cross, the elevations on them must agree. The disagreements are counted and go to the log together with the coordinates of the place where they are largest: with a number alone there is nowhere to look for the vertex that slipped.

| Field | What it sets |
|---|---|
| **Outlines on sections (polygons with Z)** | A layer of outlines on sections: polygons with real Z. The position of the sections is taken from the geometry itself, from the vertices of the outline, and is never asked for. A flat drawn section is no good: its X and Y are coordinates on the sheet and there are no elevations at all. The geometry type must be PolygonZ or MultiPolygonZ. |
| **The field of the bed number** | The field of the bed number. Every bed gives two bands in the grid: a roof and a floor. |
| **This bed only (empty means all)** | The number of the bed, if only one is wanted. Empty means all. |
| **Grid step, m (0 means from the data)** | The step of the grid over the area. Zero takes a two-hundredth of the extent. |
| **Area mask (polygons, optional)** | A polygon layer the result is clipped by. Outside it there is no grid at all. Between the sections there are no data, and the surface goes where the interpolation drew it: the mask says how far to trust that. Usually it is the outline of a working, a pit or a block. Empty - the grid covers the whole extent of the contours. |
| **Grid of the beds** | A multiband grid: a roof and a floor per bed, in order of the numbers. The scene shows such a grid as a bed body, 1.02 computes the thickness from it and 1.03 the blocks and the volumes. |
| **Levels** | Levels in the multilevel approximation. Few levels give a smooth surface, many bring it closer to the elevations on the sections. |
| **Contact gluing tolerance, m** | The tolerance within which the floor of the upper bed and the roof of the lower one count as one surface and are built once. Two surfaces built independently drift apart between the sections, and the model gets a gap or an overlap that the section does not have. Zero switches the gluing off: then every surface is its own. |
| **Margin outwards from the mask, m** | A margin outwards from the mask. The bed usually continues beyond the outline of a working, and clipping exactly along it would cut away what the data do hold. |

## 2.09 A demonstration drift (demo)

Creates a potash working with drawings of the walls, fan holes and grooves.

The beds and the grades are set by formulas, the sampling noise is added separately, so the set has a known answer. The true volumes of the beds are printed to the log: build the body with 2.08 and compare.

The working is a drift with crosscuts across it. Two walls of the drift give parallel sections, the crosscuts give intersections where the elevations must agree, and between them an area is left for the interpolation to fill.

There are three beds: KrII, AB and V. The set deliberately holds the cases the model stumbles on. The floor of KrII and the roof of AB are drawn as one line - the contact gluing must recognise them and build one surface. Between AB and V there is a parting, and no contact there. Inside AB a lens is drawn under the same bed number - it must not touch the boundary of the body. Bed V pinches out and does not reach the far crosscut at all, so without clipping by its own sections it will be stretched over the whole area.

There are two grades, KCl and the insoluble residue. They are tied in reverse: where there is more sylvite there is less residue. On a pair of bands it is visible how several parameters live in one grid at once.

| Field | What it sets |
|---|---|
| **Extent (where to put the drift)** | Where to put the drift. Empty means the extent of the map view: the example lands where you are looking. |
| **Length of the drift, m** | The length of the drift. It decides how much area is left between the walls and the crosscuts - the very place where there is no data and the interpolation works. |
| **Width of the working, m** | The width of the working: the distance between the walls. Two walls give parallel sections a couple of metres apart. |
| **Crosscuts across** | Crosscuts across the drift. Each gives another pair of walls, and where they cross the walls of the drift the elevations must agree. Without crosscuts there is nothing to check that on. |
| **Sample length, m** | The length of a sample in a hole and the step of a groove across the thickness. A sample longer than the bed will miss it between the measurements. |
| **Sampling noise, a share** | The share of lognormal sampling noise. Zero gives data without noise: on them the model itself is visible rather than the scatter. |
| **Wall drawings (polygons with Z)** | Wall drawings: polygons with real Z, the input for 2.08. |
| **Samples of the holes** | Samples of the fan holes: points with grades, the input for 2.06 and 2.07. |
| **Grooves across the thickness** | Grooves across the thickness of a bed on the walls: intervals with grades. |
| **The random seed** | The same seed gives the same set. With it the methods are compared on unchanged data. |
| **Draw a lens inside bed AB** | Draw a lens inside bed AB under the same bed number. It must not touch the boundary of the body, and that is exactly what is being checked. |


### What it is for

There is usually nothing to check a model against: nobody has seen the
real bedding, and to the eye an honest model and an invention look
equally convincing. This set **has a known answer**. The beds and the
grades are set by formulas, the sampling noise is added separately, the
true volumes go to the log, and beside every measurement lies the value
without noise. So what you build shows not "close enough" but the size
of the miss.

### What is inside

A drift with two crosscuts. The two walls give parallel sections, the
crosscuts give intersections where the elevations must agree, and
between them an area is left for the interpolation to fill.

Three beds, with the awkward cases planted on purpose: the floor of
KrII and the roof of AB are drawn as **one line** and must be glued;
between AB and V there is a parting of about a metre and no contact at
all; inside AB a **lens** is drawn under the same bed number and must
not touch the boundary; bed V **pinches out** and does not reach the
far crosscut.

### The numbers to expect

With the default settings the true volumes are 5662, 7764 and 1390
cubic metres. A body built from the drawings by 2.08, clipped by its
own sections, agrees with them to tenths of a per cent. The contact of
KrII and AB differs by 0.016 m and is glued, the contact of AB and V by
0.83 m and is not.

## 2.10 Surfaces from cross sections

Builds surfaces from the lines drawn on sections.

A line on a section is one surface, not a body: it need not be split into a roof and a floor, every vertex is already a point in space. Rings and bodies are the business of 2.08.

This is how a designed surface is put together from cross profiles, a fault plane from its traces on a series of sections, a horizon from the boundary of a member. The difference of two bands gives the volume of the works: where too much was filled and where too little.

The position of the sections is taken from the geometry itself, from the vertices of the lines. They need not be given separately. A flat drawn section is no good: it has no real marks.

Before the fitting a flat trend is removed: without it the error of the method grows with the mark itself rather than with its spread.

Where the sections cross, the marks on them must agree. The disagreement is counted and goes to the log together with the coordinates of the place where it is largest.

| Field | What it sets |
|---|---|
| **Lines on sections (with Z)** | A layer of lines on sections: lines with real Z. A cross profile of an embankment, the trace of a fault, the boundary of a member - anything drawn on a section as one line rather than a ring. The position of the sections is taken from the geometry itself, from the vertices, and is asked for nowhere. A flat drawn section is no good: its X and Y are coordinates on the sheet, and there are no marks at all. |
| **Field of the surface name** | Field of the surface name. Every surface gives its own band in the grid: that way a roof and a floor, a design and a survey, or several horizons are built in one run. Empty - all the lines count as one surface. |
| **This surface only (empty - all)** | The name of the surface if only one is wanted. Empty - all of them. |
| **Grid step, m (0 means from the data)** | The step of the grid over the area. Zero takes a two-hundredth of the extent. |
| **Area mask (polygons, optional)** | A polygon layer the result is clipped by. Between the sections there is no data, and the surface goes where the interpolation drew it: the mask says how far to trust that. |
| **Field of the surface name in the mask (empty - one mask for all)** | The field that ties a mask polygon to a surface. A polygon with an empty value clips them all. |
| **Surfaces (grid)** | A multiband grid: a band per surface, in the order of the names. The difference of two bands is the volume of the works: where too much was filled and where too little. |
| **Levels** | Levels in the multilevel approximation. Few levels give a smooth surface, many bring it closer to the marks on the sections. |
| **Clip every surface by its own sections** | Clip every surface by the area of its OWN sections: the convex hull of its points plus the margin. The designed embankment is not defined beyond the last profile, and continuing it there is invention. |
| **Margin outwards from the mask, m** | A margin outwards from the mask. A surface usually continues beyond the outermost section, and clipping exactly along it would cut away what the data do hold. |


### What it is for

A ring on a section is a body with a roof and a floor, and 2.08 deals
with it. A **line** is one surface, and it needs no splitting: every
vertex is already a point in space.

Hence the uses. Cross profiles of an embankment every hundred metres
give the designed surface, and its difference with the survey is the
volume of the works. The trace of a fault on a series of sections gives
its plane; the boundary of a member gives a horizon.

### What accuracy to expect

On a test embankment - a crest of six metres, slopes of one in two,
profiles every hundred metres - the restored surface departed from the
designed one by 0.18 m at the worst place and by 0.03 m on average, and
the volume of the fill agreed with the true one to three per cent.

The accuracy is decided by how often the sections are spaced, and no
computation mends that. Beyond the outermost section the surface is not
defined, and continuing it there is invention: that is what the
clipping by own sections is for.

## 2.11 Boolean operations on shells

Subtracts, unites and intersects two bodies.

This is how mining is accounted for: the shell of a mined-out chamber is subtracted from the shell of an ore body and the remaining reserves come out. An intersection gives what fell inside a zone, a union takes two bodies as one.

The work goes not over meshes but over cells: both shells are turned into the occupancy of a common cube, the operation is done over the occupancy, and the result is turned back into a body. An exact operation over meshes cuts triangles against each other and on touches regularly gives a result that is not closed, and no volume can be taken from it.

The price of this decision: the body comes out stepped, and the accuracy is limited by the cell. The error follows the surface area and falls with the cell: on a ten-metre cube a cell of 0.5 m gave a volume error of five per cent, 0.25 m two and a half, 0.1 m landed exactly. The memory meanwhile grows as a cube.

The shells on input must be closed: one that is not has no inside, and there is nothing to tell what is within. A shell that is not closed on input is refused with the object named.

| Field | What it sets |
|---|---|
| **The first body (polygons with Z)** | The first body: a closed shell from a layer of polygons with Z. The shells button in the viewer and the tool 2.04 give such layers. |
| **The second body (polygons with Z)** | The second body. For a difference this is what is cut out of the first: a mined-out chamber, a flooded zone. |
| **Action** | A difference leaves of the first body what the second does not hold. A union takes both, an intersection only the common part. |
| **Side of the cell, m** | The side of the cell. It sets the accuracy: the error follows the surface area and halves with every halving of the cell. On a ten-metre cube a cell of 0.5 m gave a volume error of 5 per cent, 0.25 m two and a half, 0.1 m landed exactly. The memory grows as a cube, so do not take it finer than needed. |
| **The result (bodies)** | The bodies of the result: polygons with Z, the volume of each in the attributes. The shell is always closed, so the volume can be computed from it. |


### Why over cells

An exact operation over meshes cuts triangles against each other. On
touches - and in geology bodies touch all the time - it regularly gives
degenerate faces and a result that is not closed, and no volume can be
taken from that. Here both shells are turned into the occupancy of a
common cube, the operation is done over the occupancy, and the result
becomes a body again. It is stepped, but always closed.

### The price

The accuracy is limited by the cell, and the error follows the
**surface area** rather than the volume. On two ten-metre cubes with a
shift (intersection 500, union 1500, difference 500 cubic metres) a
cell of 0.5 m gave five per cent, 0.25 m two and a half, 0.1 m landed
exactly. The memory meanwhile grows as a cube.

### What is checked on input

The shells must be closed, and that is checked by counting edges rather
than by the fill having worked. A hole in a **side** wall is invisible
to an upward ray: a vertical face is never crossed by it, and the
volume would be computed over a torn body in silence.

## 2.12 Selection by a shell

Selects the features that fell into a closed shell and computes a summary over them.

That is how reserves are obtained: a block model, the shell of an ore body or of a mined-out zone, and out come the volume, the tonnage and the volume-weighted grade of the selection. Selecting the outside gives the remainder without building a difference of bodies.

Not only points can be selected. Lines and polygons with height go the same way: holes that pierced the body, traces of workings, shells of other bodies.

A point counts as inside by the parity rule: a ray is sent up from it, and if the shell is crossed an odd number of times the point is inside. No cells are needed for that, and the answer comes out exact rather than to within a cell, as with the boolean operations.

For lines and polygons the vertices are looked at. A segment that goes right through the body between two of its own vertices is not caught by vertices - the sampling step along is there for that.

The volume of the selected blocks is checked against the volume of the shell itself: the difference shows how coarse the model is for this body.

The shell must be closed: one that is not has no inside.

| Field | What it sets |
|---|---|
| **What to select (features with Z)** | What to select: points, lines or polygons with height. A block model from 2.03 and 1.03, samples, traces of workings, shells of other bodies - as long as the geometry has Z. |
| **The shell (polygons with Z)** | The closed shell the selection is made by: an ore body, a mined-out zone, a block of reserves. The shells button in the viewer, 2.04 and 2.11 give such shells. |
| **What to keep** | Entirely inside - every vertex of the feature is inside the shell. Crosses - at least one is: that is how holes and workings going right through the body are caught. Outside - the remainder, everything that does not cross. |
| **Field of the block volume** | The field of the block volume, if a block model is being selected. With it the volume of the selection is computed and checked against the volume of the shell itself: the difference shows how coarse the model is for this body. |
| **Field of the grade** | The field of the grade. The mean over the selection is weighted by volume rather than plain: blocks come in different sizes, and a plain mean gives the small ones too much say. |
| **Selected features** | The selected features with all their own fields. The summary goes to the log. |
| **Sampling step along lines, m (0 - vertices)** | The sampling step along lines and around the edge of polygons. Without it only the vertices are looked at, and a segment that goes right through the body between two of its own vertices will not be found. Zero - vertices only. |
| **Density, t/m3 (0 - no tonnage)** | The density of the ore. With it the volume turns into tonnes and the grade into the tonnage of metal. |


### What it is for

This is the last link of the chain: a cube of values - a block model -
a selection by a shell - the volume, the tonnage and the
volume-weighted grade. Selecting the outside gives the remainder after
mining without building a difference of bodies.

Not only points can be selected: lines and polygons with height go the
same way.

### The check worth attention

The volume of the selected blocks is compared with the volume of the
shell itself, and the difference is printed. That is not a check of
correctness but a measure of how **coarse the block model** is for this
body: a block is either wholly inside or wholly outside, there is no
third case.

### The limit of the method

For lines and polygons the vertices are looked at. A segment that goes
right through the body between two of its own vertices is not caught by
vertices - the sampling step along is there for that.

## 2.13 A shell from a bed grid

Builds a closed shell of a bed body from a grid: the roof, the floor and the skirt between them.

The shells button in the viewer does the same, but there it is a manual step. As a tool it becomes part of a processing model, and the chain "surface - body - subtract what is mined out - count the reserves" runs as a whole.

The shell is closed, so 2.11 and 2.12 take it, and the volume is computed by an exact formula over the shell itself.

The volume here and the volume from 1.02 differ by about one per cent: the shell runs through the centres of the cells, while 1.02 counts whole cells. These are different boundaries of one area, not a dispute of methods.

| Field | What it sets |
|---|---|
| **Bed grid** | A bed grid: a roof band and a floor band. 1.01 gives one from two surfaces or from a single one built downwards, and 2.08 from the drawings on sections. |
| **Roof band** | The roof band. The next one counts as the floor: that is how a bed grid is built. In a multi-bed grid this is the choice of bed. |
| **Bodies of the bed** | The bodies of the bed: polygons with Z, the volume of each in the attributes. 2.11 and 2.12 take them next. |
| **Thinning of the mesh** | Thinning of the mesh. One means as it is; two takes every second cell and gives four times fewer triangles. The volume changes little, but fine detail is cut away. |

# From drawings on sections to a body

The tool **2.08 Beds from sections**, for when the holes are few and
the sections are drawn.


### What it is for

The shells button in the viewer does the same, but there it is a manual
step: a processing model will not repeat it. As a tool the chain
"surface - body - subtract what is mined out - count the reserves" runs
as a whole.

### About the volume

The volume here and the volume from 1.02 differ by about one per cent:
the shell runs through the centres of the cells, while 1.02 counts
whole cells. On a test DEM of 101 by 101 with a cut-off elevation it
came to 39524 cubic metres over the shell against 40309 over the cells
- two per cent, all of it around the edge.

## Where the coordinates come from

From the geometry of the outlines, and from nowhere else. An outline on
a three-dimensional section is a polygon whose every vertex has X, Y
and Z. X and Y run along the line of the section, Z is the elevation.
The tool works out the plane of the outline from those vertices, taking
the direction from the largest spread of the points in plan. The lines
of the sections need not be given separately: they are already in the
data.

A flat drawn section is no good: its X and Y are coordinates on the
sheet, not on the ground, and there are no elevations at all. The
geometry type must be `PolygonZ` or `MultiPolygonZ`.

## How the roof and the floor are taken

The ring of the outline is sampled across, along the line of the
section: at every step the upper point of the ring and the lower one.
Splitting the ring in half is not allowed - only a fence is built that
way, with the top running forward and the bottom back, while a
hand-drawn outline has its vertices in any order.

It is these two surfaces that are interpolated, not the body as a
whole. A roof and a floor are ordinary surfaces, and the problem about
them has a solution for any layout of sections.

Before the fitting a flat trend is removed from the elevations. Without
that the error of the method grows with the elevation itself rather
than with its spread: on a roof around minus two hundred and fifty
metres with a spread of eighty centimetres the surface went off by
fourteen metres, and no number of levels mended it.

## The contact of neighbouring beds

The floor of the upper bed and the roof of the lower one are one and
the same boundary if the geologist drew them as one line. Built
separately, they drift apart between the sections, and the model gets a
gap or an overlap that the section does not have.

The tool brings the samples of neighbouring beds together and measures
the spread of the elevations. If it is within the **contact gluing
tolerance**, the boundary is built once from both sets of points and
put into both bands: the gap is then zero by construction. If it is
larger, the surfaces are built separately and a warning goes to the log
with the coordinates of the place where the disagreement is largest.
Go there and look in your own layer of outlines: usually one vertex has
slipped.

For this the beds are ordered by their bedding, from the top down,
rather than by the name of the field: numbers come as text, and then
"10" stands between "1" and "2".

## A lens inside a bed

The outlines of one section plane are taken together, by their outer
boundary: the roof follows the topmost of them, the floor the lowest.
A lens or a parting drawn inside a bed under the same number therefore
does not touch the boundary of the body. Their samples used to be
pooled together, and the cloud of the roof held both the real roof and
the top of the lens: the interpolation got two answers in one place and
ran the surface between them.

If the lens is wanted as a body of its own, give it its own bed number.

Outlines of different sections are never merged this way. A
disagreement at one place in plan between two sections is data, and it
must be seen rather than hidden by taking the outermost.

## How far to trust the surface

The grid is built over the whole extent of the outlines, and beyond the
sections the surface goes where the interpolation put it. The **area
mask** says how far to trust that: outside it there is no grid at all.
Usually it is the outline of a working, a pit or a block. The **margin
outwards from the mask** is left because the bed continues beyond the
outline of a working, and clipping exactly along it would cut away what
the data do hold.

## A mask for one bed

The mask need not be common to all. If a **field of the bed number** is
set on the mask layer, a polygon clips the bed whose number it carries,
and a polygon with an empty value clips them all. This is what to use
when one bed has shorter sections than its neighbours.

The checkbox **clip every bed by its own sections** does the same
without drawing: the convex hull of the bed's own samples plus the
margin. In a pit with four walls a bed met on three of them used to
take the whole area; with its own hull it takes 39 per cent against 64
for its neighbours.

A hull is convex, and no dent can come out of it: for a bed on three
walls of a rectangular pit it covers the whole rectangle, because the
middle lies inside. That is what the per-bed mask polygon is for.

## The order of the work

1. Outlines of the beds on sections: polygons with real Z.
2. **2.08 Beds from sections**. Set the field of the bed number and
   leave "This bed only" empty: all the beds are built in one run, on a
   common grid. In separate runs every bed gets its own extent and its
   own step, and the contacts between them no longer meet.
3. The log: the thickness over the area must lie within the thickness
   on the sections, and the lines about the contacts must show
   centimetres rather than decimetres.
4. The grid into the scene, the **Bed body** mode. The shells button
   puts the bodies into a project layer, with the volume in the
   attributes.
5. Thickness, volume and reserves come from **1.02 Bed calculator**,
   the block model from **1.03**.

What is worth knowing beforehand. The accuracy is decided by how often
the sections are spaced, and no computation can mend that: between two
sections there is no data.

The volume of a body from the shells button and the volume from 1.02
will not agree exactly. The mesh runs through the centres of the cells,
1.02 counts whole cells, and the difference is the half-cells around
the perimeter: about one per cent on a grid of two hundred cells, and
noticeably more on a coarse one.

# Typical tasks

Six chains that come round again and again in the work. Numbers with a
dot are Isoliner3D tools, names without a number are the neighbouring
Isoliner.

## From boreholes to reserves

1. Samples with grades in a point layer, the elevation in the geometry
   or in a field.
2. **2.05 Cross-validation** to choose the parameters. Leave out a
   whole hole, not a single sample: a neighbouring sample in the same
   hole almost repeats the one left out, and the error comes out lower
   than the real one.
3. **2.02 Interpolation of points in volume** or **2.07 MBA in
   volume** for the cube of values.
4. The cube into the scene, isosurface mode. Clipping by the terrain
   and by the licence outline is in the scene properties.
5. The **shells into a project layer** button: bodies with the volume
   of each.

## From horizons to a bed

1. In Isoliner the **roof** and the **floor** are interpolated in plan.
2. **1.01 Assemble a bed grid** - a multiband grid.
3. **1.03 Bed into a block model** - blocks with volume and mass.
4. The same grid shows in the scene as a bed body, without any
   conversion.

## A section on the drawing and in volume

The section fence built by Isoliner is polygons with real Z, and it
goes into the scene as it is; the colour of the beds comes from the
`color` field. The point is a check by eye: the fence lies on the
surfaces it was built from.

## What has changed between surveys

Two models of the same area from different times, then **1.06 Reserve
difference**.

## Showing it to someone who is not a geologist

**GLB** for a browser, Blender or Windows; PNG frames of a turn for a
video; **STL** or **OBJ** for CAD. For CAD switch on the cap at the
cube edge: an open shell will show as a mesh but will not become a
solid.

## Checking the data before the model

**2.05** leaving out one sample, and the same leaving out a whole hole.
The difference between the two errors tells what the model rests on.

Measured on the demonstration deposit, samples every five metres down
the hole: with a 100 m grid of holes the ratio is 0.9, with 200 m it is
1.6, with 400 m it is 2.6. The error per sample hardly changes with the
grid - a neighbour down the hole is always close by. The error per hole
grows with the distance between the holes, and that one is the real
one.

The figures are for the demonstration data; yours will differ. What
matters is the ratio and how it changes as the grid gets denser.

# Neighbouring plugins

**Isoliner** - interpolation in plan, contours, terrain, drawn sections,
borehole graphics. Isoliner3D reads what it builds.

**Topoliner** - topographic constructions.

# Licence and developer

Isoliner3D is developed by **Inform++ LLC**, Perm —
[www.informpp.ru](https://www.informpp.ru/).

The module is distributed under the **GNU General Public License,
version 2 or, at your option, any later version** (GPL-2.0-or-later).
You are free to use, study, modify and pass it on; when passing on a
modified version you must keep the same licence and open the source. The
full text of the licence is in the `LICENSE` file inside the module.

The program is distributed in the hope that it will be useful, but
**with no warranty whatsoever**, including the implied warranty of
fitness for a particular purpose. Responsibility for the results rests
with whoever applies them: every model is an approximation, and
decisions about reserves and mining are made by a specialist, not by a
program.

The bundled pyqtgraph and PyOpenGL libraries carry their own licences,
compatible with the GPL.

## Where to look

The **About the plugin** button on the toolbar, and the menu item of
the same name, show the version and the links, open the changelog and
the log of the module.

The log is started when the module loads, next to the QGIS profile, as
`isoliner3d.log`. Every step goes into it, not only failures. The lines
the tools print go there as well, not only into the Processing window:
a picture of the log used to show that a run took half a second and not
a single number to judge the result by.

| Where | What for |
|---|---|
| [www.informpp.ru](https://www.informpp.ru/) | about the developer and the other products |
| [Source code](https://github.com/Valery35/qgis-isoliner3d) | builds, history, texts |
| [Report a bug](https://github.com/Valery35/qgis-isoliner3d/issues) | if something works wrong |

When reporting a bug, attach the version from the window title and the
lines from the log: with them the cause is found in one go.
