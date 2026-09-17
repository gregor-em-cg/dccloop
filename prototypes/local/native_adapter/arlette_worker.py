"""Trusted Arlette visual-asset recipe v1; no executable recipe inputs.

Four-field requests: {operation, input:{path,sha256}|null, assets:[], parameters:{}}.
build_arlette_v1: null input; refine_arlette_v1: exact labelled native input.
Both accept ONLY height [.4,.9], width [.08,.18], projection [.11,.24],
globe_diameter [.08,.13], globe_spacing [.15,.25], brass_roughness [.08,.7],
acrylic_roughness [.01,.3], groove_depth [0,.002], material_mode clay|final.
Dimensions are metres. Omitted build parameters use frozen brief v1 defaults;
omitted refine parameters retain the input candidate's recorded values.
inspect_arlette_v1: editability_render boolean (default false), producing two
1200-square diagnostic renders of a final-material candidate in memory only.
render_arlette_v1: preview_px integer
64..1200, views unique nonempty subset full/detail/alternate/clay/cage.
All nonbuild operations require an exact input SHA. No assets are accepted:
geometry and shaders are procedural, and native dependencies must be packed.
Width/height/projection, shade diameter/spacing, and material roughness have
live drivers. Cut depth is a recorded geometry control applied by refinement.
Ordinary refinement rebuilds this finite component recipe, preserving input.
The single c4-geometry-refine job is an explicit exception: exact C3 bytes,
empty parameters and the canonical job path permit replacing only three shade
meshes. It preserves object/material/control state and reopens the saved result.
Path checks and disabled autoexec are explicitly not an OS sandbox.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import traceback

import bpy
import bmesh
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from native_adapter.worker import checked_path, checked_record, number, sha256, update_scene, write_json
from native_adapter.facet_candidate_v3 import build_faceted_globe
from native_adapter.fluted_candidate_v4 import build_fluted_globe


LABEL = "ARLETTE_VISUAL_PILOT"
RECIPE = "arlette-photo-construction-v1"
C4_JOB = "c4-geometry-refine"
C4_INPUT_SHA256 = "6e057c57b8d2f4df3332514e14027af03dae5d70c777089cccf410e5c4dde0e6"
C4_REVISION = "c4-continuous-longitudinal-lanes-elongated-diamond-panels"
C4_SHADES = tuple(f"Shade {index:02d} carved acrylic shell" for index in range(1, 4))
DEFAULTS = {"height": .60325, "width": .111125, "projection": .1435,
            "globe_diameter": .107, "globe_spacing": .189,
            "brass_roughness": .28, "acrylic_roughness": .06,
            "groove_depth": .0012, "material_mode": "clay"}
BOUNDS = {"height": (.4, .9), "width": (.08, .18), "projection": (.11, .24),
          "globe_diameter": (.08, .13), "globe_spacing": (.15, .25),
          "brass_roughness": (.08, .7), "acrylic_roughness": (.01, .3),
          "groove_depth": (0, .002)}
OPS = {"build_arlette_v1", "refine_arlette_v1", "inspect_arlette_v1", "render_arlette_v1"}
VIEWS = {"full", "detail", "alternate", "clay", "cage"}
REFERENCE_FACTS = {"height_m": .60325, "width_m": .111125,
                   "source": "Edward Martin SKU 300119 numeric dimensions; inches multiplied by .0254",
                   "projection": "inferred", "hidden_mounting_electrical": "visual approximation"}
CAPTURE_PROFILE = {
    "id": "arlette-fixed-studio-v1.1",
    "views": {
        "full": {"position": [-1.0, -2.5, .56], "target": [0, -.055, .301625], "scale": .775},
        "detail": {"position": [-.4, -1.3, .61], "target": [0, -.09, .454], "scale": .185},
        "alternate": {"position": [1.7, -2.4, .73], "target": [0, -.055, .301625], "scale": .775},
        "clay": {"position": [-1.0, -2.5, .56], "target": [0, -.055, .301625], "scale": .775},
        "cage": {"position": [-.4, -1.3, .61], "target": [0, -.09, .454], "scale": .185},
    },
    "resolution": [1200, 1200], "camera_type": "ORTHO", "engine": "CYCLES", "device": "CPU",
    "threads": 2, "samples": 32, "seed": 0, "denoising": True,
    "max_bounces": 12, "transmission_bounces": 10, "transparent_max_bounces": 12,
    "view_transform": "AgX", "exposure": -1.5, "gamma": 1,
    "film_transparent": False, "image_format": "PNG", "color_mode": "RGB", "color_depth": "8",
    "world": {"color": [.86, .89, .94, 1], "strength": .55},
    "lights": [{"position": [-.7, -.9, 1.0], "energy": 30, "size": [.7, 1.5]},
               {"position": [.6, -.55, .65], "energy": 17.5, "size": [.35, 1.1]},
               {"position": [-.55, .01, .48], "energy": 11.25, "size": [.2, .9]}],
    "wall": {"dimensions": [4, .01, 4], "position": [0, .015, .30],
             "base_color": [.85, .85, .85, 1], "roughness": .8},
    "overrides": {"clay": "neutral clay", "cage": "neutral clay with actual mesh wire overlay"},
    "eligible_for_product_review": True,
}


def validate(raw: dict, output: Path) -> dict:
    if not isinstance(raw, dict) or set(raw) != {"operation", "input", "assets", "parameters"}:
        raise ValueError("request requires exactly operation, input, assets, parameters")
    if raw["operation"] not in OPS:
        raise ValueError("unsupported trusted Arlette operation")
    source = checked_record(raw["input"]) if raw["input"] is not None else None
    if (raw["operation"] == "build_arlette_v1") != (source is None):
        raise ValueError("only initial Arlette build accepts null native input")
    if source and (source["path"].suffix.lower() != ".blend" or source["path"].is_relative_to(output)):
        raise ValueError("native source must be an immutable external .blend")
    if raw["assets"] != []:
        raise ValueError("Arlette v1 accepts no external assets")
    params = raw["parameters"]
    if not isinstance(params, dict):
        raise ValueError("parameters must be an object")
    if raw["operation"] in {"build_arlette_v1", "refine_arlette_v1"}:
        if set(params) - set(DEFAULTS):
            raise ValueError("unsupported Arlette construction parameter")
        params = dict(params)
        for key, value in params.items():
            if key == "material_mode":
                if value not in {"clay", "final"}:
                    raise ValueError("material_mode must be clay or final")
            else:
                params[key] = number(value, key, *BOUNDS[key])
    elif raw["operation"] == "inspect_arlette_v1":
        if set(params) - {"editability_render"} or type(params.get("editability_render", False)) is not bool:
            raise ValueError("Arlette inspection accepts only boolean editability_render")
        params = {"editability_render": params.get("editability_render", False)}
    else:
        if set(params) - {"preview_px", "views"}:
            raise ValueError("unsupported Arlette capture parameter")
        px = params.get("preview_px", 1200)
        if type(px) is not int or not 64 <= px <= 1200:
            raise ValueError("preview_px must be an integer 64..1200")
        views = params.get("views", ["full", "detail", "alternate", "clay", "cage"])
        if not isinstance(views, list) or not views or any(type(v) is not str or v not in VIEWS for v in views) or len(set(views)) != len(views):
            raise ValueError("unsupported or duplicate proof views")
        params = {"preview_px": px, "views": views}
    return {"operation": raw["operation"], "input": source, "assets": [], "parameters": params}


def dependencies() -> list:
    if bpy.data.libraries:
        raise ValueError("linked native libraries are unsupported")
    for name in ("sounds", "movieclips", "cache_files", "volumes"):
        if len(getattr(bpy.data, name, ())):
            raise ValueError("external dependency collection unsupported: " + name)
    for image in bpy.data.images:
        if image.source not in {"GENERATED", "VIEWER"} and not image.packed_file:
            raise ValueError("unpacked image dependency is forbidden: " + image.name)
    for font in bpy.data.fonts:
        if font.filepath and font.filepath != "<builtin>" and not font.packed_file:
            raise ValueError("external font dependency forbidden")
    return []


def open_native(request: dict) -> dict:
    source = request["input"]
    if sha256(source["path"]) != source["sha256"]:
        raise ValueError("candidate changed before open")
    bpy.ops.wm.open_mainfile(filepath=str(source["path"]), load_ui=False, use_scripts=False)
    if bpy.context.preferences.filepaths.use_scripts_auto_execute:
        raise ValueError("native automatic execution must be disabled")
    if bpy.context.scene.get("product_label") != LABEL or bpy.context.scene.get("trusted_recipe") != RECIPE:
        raise ValueError("unsupported native product recipe")
    dependencies()
    update_scene()
    return json.loads(bpy.context.scene["recipe_parameters_json"])


def add_driver(owner, path, control, expression: str, variables: dict, index=None):
    curve = owner.driver_add(path) if index is None else owner.driver_add(path, index)
    curve.driver.type = "SCRIPTED"
    for name, property_name in variables.items():
        variable = curve.driver.variables.new()
        variable.name = name
        variable.type = "SINGLE_PROP"
        variable.targets[0].id = control
        variable.targets[0].data_path = '["' + property_name + '"]'
    curve.driver.expression = expression


def link_object(name, data, parent=None):
    obj = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(obj)
    if parent:
        obj.parent = parent
    return obj


def mesh_object(name, vertices, faces, mat, parent=None, smooth=True):
    mesh = bpy.data.meshes.new(name + " editable mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = link_object(name, mesh, parent)
    obj.data.materials.append(mat)
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    obj["component_role"] = name
    return obj


def lathe(name, profile, mat, parent=None, location=(0, 0, 0), segments=64):
    """Closed solid profile; zero-radius tips use single vertices, not degenerate rings."""
    vertices, rings, faces = [], [], []
    for radius, z in profile:
        if radius == 0:
            rings.append([len(vertices)])
            vertices.append((0, 0, z))
        else:
            ring = []
            for i in range(segments):
                a = 2 * math.pi * i / segments
                ring.append(len(vertices))
                vertices.append((radius * math.cos(a), radius * math.sin(a), z))
            rings.append(ring)
    for lower, upper in zip(rings, rings[1:]):
        for i in range(segments):
            nxt = (i + 1) % segments
            if len(lower) == 1:
                faces.append((lower[0], upper[nxt], upper[i]))
            elif len(upper) == 1:
                faces.append((lower[i], lower[nxt], upper[0]))
            else:
                faces.append((lower[i], lower[nxt], upper[nxt], upper[i]))
    obj = mesh_object(name, vertices, faces, mat, parent)
    obj.location = location
    return obj


def cylinder(name, radius, depth, mat, parent=None, location=(0, 0, 0), axis="Z", bevel=.0006):
    bevel = min(bevel, radius * .2, depth * .2)
    profile = [(0, -depth / 2), (radius - bevel, -depth / 2), (radius, -depth / 2 + bevel),
               (radius, depth / 2 - bevel), (radius - bevel, depth / 2), (0, depth / 2)]
    obj = lathe(name, profile, mat, parent, location)
    if axis == "Y":
        obj.rotation_euler.x = math.pi / 2
    elif axis == "X":
        obj.rotation_euler.y = math.pi / 2
    return obj


def box(name, dimensions, location, mat, parent=None, bevel=.0008):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj = bpy.context.object
    obj.name = name
    for vertex in obj.data.vertices:
        vertex.co.x *= dimensions[0]
        vertex.co.y *= dimensions[1]
        vertex.co.z *= dimensions[2]
    obj.location = location
    obj.parent = parent
    obj.data.materials.append(mat)
    modifier = obj.modifiers.new("Manufactured edge rounding", "BEVEL")
    modifier.width = bevel
    modifier.segments = 3
    return obj


def make_materials(control, mode):
    def principled(name, color, roughness, metallic=0):
        mat = bpy.data.materials.new(name)
        mat.use_fake_user = True
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        return mat, bsdf
    clay, _ = principled("Arlette neutral clay", (.48, .49, .50, 1), .55)
    brass, bsdf = principled("Arlette satin natural brass", (.72, .51, .235, 1), .28, 1)
    add_driver(bsdf.inputs["Roughness"], "default_value", control, "r", {"r": "brass_roughness"})
    if "Anisotropic IOR Level" in bsdf.inputs:
        bsdf.inputs["Anisotropic IOR Level"].default_value = .55
        tangent = brass.node_tree.nodes.new("ShaderNodeTangent")
        tangent.direction_type = "RADIAL"
        tangent.axis = "Z"
        brass.node_tree.links.new(tangent.outputs["Tangent"], bsdf.inputs["Tangent"])
    texture = brass.node_tree.nodes.new("ShaderNodeTexNoise")
    texture.inputs["Scale"].default_value = 1
    texture.inputs["Detail"].default_value = 2
    coords = brass.node_tree.nodes.new("ShaderNodeTexCoord")
    mapping = brass.node_tree.nodes.new("ShaderNodeVectorMath")
    mapping.operation = "MULTIPLY"
    mapping.inputs[1].default_value = (240, 240, 4)
    brass.node_tree.links.new(coords.outputs["Generated"], mapping.inputs[0])
    brass.node_tree.links.new(mapping.outputs["Vector"], texture.inputs["Vector"])
    bump = brass.node_tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .2
    bump.inputs["Distance"].default_value = .000018
    brass.node_tree.links.new(texture.outputs["Fac"], bump.inputs["Height"])
    brass.node_tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    acrylic, clear = principled("Arlette clear carved acrylic IOR 1.49", (.99, .99, .985, 1), .06)
    clear.inputs["IOR"].default_value = 1.49
    clear.inputs["Transmission Weight"].default_value = 1
    add_driver(clear.inputs["Roughness"], "default_value", control, "r", {"r": "acrylic_roughness"})
    led, emitter = principled("Arlette estimated warm LED pole emitter", (1, .82, .49, 1), .28)
    emitter.inputs["Emission Color"].default_value = (1, .52, .14, 1)
    emitter.inputs["Emission Strength"].default_value = 80.0
    dark, _ = principled("Arlette recessed hardware dark brass", (.12, .07, .022, 1), .4, 1)
    return {"brass": brass if mode == "final" else clay,
            "acrylic": acrylic if mode == "final" else clay,
            "led": led if mode == "final" else clay,
            "dark": dark if mode == "final" else clay, "clay": clay}


def carved_globe(name, diameter, cut_depth, mat, parent):
    """Revision C3: explicit repeated planar cuts within smooth longitudinal bands."""
    vertices, faces, smooth = build_faceted_globe(diameter, cut_depth)
    globe = mesh_object(name, vertices, faces, mat, parent)
    for polygon, use_smooth in zip(globe.data.polygons, smooth):
        polygon.use_smooth = use_smooth
    globe["carving_kind"] = "ordered staggered triangular cuts with smooth longitudinal bands"
    globe["groove_depth_m"] = cut_depth
    globe["wall_thickness_at_equator_m"] = diameter * .04
    globe["pattern_estimated"] = True
    return globe


def _content_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _plain(value):
    """Stable values for the explicitly recorded native preservation surface."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, dict) or hasattr(value, "to_dict"):
        return {str(k): _plain(v) for k, v in dict(value).items()}
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, bpy.types.ID):
        return {"id_type": value.bl_rna.identifier, "name": value.name_full}
    if hasattr(value, "to_list"):
        return [_plain(v) for v in value.to_list()]
    try:
        return [_plain(v) for v in value]
    except TypeError:
        raise TypeError("unsupported preservation value: " + type(value).__name__)


def _properties(owner):
    return {key: _plain(owner[key]) for key in sorted(owner.keys())}


def _rna_values(owner):
    """Writable scalar/array settings; nested structures are captured explicitly."""
    value = {}
    for prop in owner.bl_rna.properties:
        if prop.is_readonly or prop.type in {"COLLECTION", "POINTER"}:
            continue
        value[prop.identifier] = _plain(getattr(owner, prop.identifier))
    return value


def _drivers(owner):
    animation = owner.animation_data
    if animation is None:
        return []
    return [{"path": curve.data_path, "index": curve.array_index, "mute": curve.mute,
             "type": curve.driver.type, "expression": curve.driver.expression,
             "use_self": curve.driver.use_self,
             "variables": [{"name": v.name, "type": v.type,
                            "targets": [{"id": _plain(t.id), "data_path": t.data_path,
                                         "transform_type": t.transform_type,
                                         "transform_space": t.transform_space,
                                         "bone_target": t.bone_target} for t in v.targets]}
                           for v in curve.driver.variables]}
            for curve in animation.drivers]


def _node_tree(tree):
    if tree is None:
        return None
    nodes = []
    for node in sorted(tree.nodes, key=lambda n: n.name):
        nodes.append({"name": node.name, "type": node.bl_idname, "settings": _rna_values(node),
                      "inputs": [{"identifier": s.identifier, "name": s.name,
                                  "value": _plain(s.default_value) if hasattr(s, "default_value") else None}
                                 for s in node.inputs]})
    return {"nodes": nodes, "links": sorted((link.from_node.name, link.from_socket.identifier,
                                               link.to_node.name, link.to_socket.identifier) for link in tree.links),
            "drivers": _drivers(tree)}


def _mesh_content(mesh):
    return {"name": mesh.name, "vertices": [list(v.co) for v in mesh.vertices],
            "edges": [list(edge.vertices) for edge in mesh.edges],
            "polygons": [{"vertices": list(p.vertices), "smooth": p.use_smooth,
                          "material_index": p.material_index} for p in mesh.polygons],
            "materials": [m.name if m else None for m in mesh.materials],
            "custom_properties": _properties(mesh)}


def c4_preservation_snapshot():
    """Measured native values, excluding only replaced shade mesh data/revision.

    Fingerprints cover all object identity/parent/transform/custom properties,
    object drivers/modifier settings/material slots, non-acrylic mesh geometry,
    material nodes/values/links/drivers, scene controls/units, world and render
    settings, and the unchanged literal comparison profile. This is a finite
    audit surface for the known C3 recipe, not a general .blend equivalence test.
    """
    update_scene()
    objects, meshes = {}, {}
    for obj in sorted(bpy.context.scene.objects, key=lambda o: o.name):
        objects[obj.name] = {
            "type": obj.type, "parent": obj.parent.name if obj.parent else None,
            "parent_type": obj.parent_type, "parent_bone": obj.parent_bone,
            "location": list(obj.location), "rotation_mode": obj.rotation_mode,
            "rotation_euler": list(obj.rotation_euler), "rotation_quaternion": list(obj.rotation_quaternion),
            "scale": list(obj.scale), "delta_location": list(obj.delta_location),
            "delta_rotation_euler": list(obj.delta_rotation_euler), "delta_scale": list(obj.delta_scale),
            "matrix_parent_inverse": [list(row) for row in obj.matrix_parent_inverse],
            "matrix_world": [list(row) for row in obj.matrix_world],
            "hide_render": obj.hide_render, "hide_viewport": obj.hide_viewport,
            "custom_properties": _properties(obj), "drivers": _drivers(obj),
            "modifiers": [{"type": m.type, "settings": _rna_values(m)} for m in obj.modifiers],
            "constraints": [{"type": c.type, "settings": _rna_values(c)} for c in obj.constraints],
            "material_slots": [{"link": s.link, "material": s.material.name if s.material else None} for s in obj.material_slots],
        }
        if obj.type == "MESH" and obj.name not in C4_SHADES:
            meshes[obj.name] = _mesh_content(obj.data)
    materials = {mat.name: {"settings": _rna_values(mat), "properties": _properties(mat),
                            "nodes": _node_tree(mat.node_tree), "drivers": _drivers(mat)}
                 for mat in sorted(bpy.data.materials, key=lambda m: m.name)}
    scene = bpy.context.scene
    props = _properties(scene)
    props.pop("construction_revision", None)
    return {"objects": objects, "non_acrylic_meshes": meshes, "materials": materials,
            "scene_properties_except_construction_revision": props,
            "unit_settings": _rna_values(scene.unit_settings), "render": _rna_values(scene.render),
            "image_settings": _rna_values(scene.render.image_settings),
            "view_settings": _rna_values(scene.view_settings), "cycles": _rna_values(scene.cycles),
            "world": {"name": scene.world.name, "settings": _rna_values(scene.world),
                      "nodes": _node_tree(scene.world.node_tree)} if scene.world else None,
            "capture_profile": CAPTURE_PROFILE, "external_dependencies": dependencies()}


def refine_c4_geometry(request, request_path, output, previous):
    expected_job = Path(__file__).resolve().parents[1] / "product/arlette/run/jobs" / C4_JOB
    if request_path.parent != expected_job or output != expected_job / "output":
        raise ValueError("C4 geometry operation requires the exact canonical C4 job paths")
    if request["operation"] != "refine_arlette_v1" or request["input"]["sha256"] != C4_INPUT_SHA256 or request["parameters"] != {}:
        raise ValueError("C4 geometry operation requires exact C3 bytes and unchanged parameters")
    if bpy.context.scene.get("construction_revision") != "c3-facet-aligned-triangles-smooth-bands-annular-pole-light":
        raise ValueError("C4 geometry requires the preserved C3 construction")
    objects = [bpy.data.objects.get(name) for name in C4_SHADES]
    if any(obj is None or obj.type != "MESH" or obj.data.users != 1 for obj in objects):
        raise ValueError("C4 requires exactly three independent existing shade meshes")
    if {o.name for o in bpy.context.scene.objects if "carved acrylic shell" in o.name} != set(C4_SHADES):
        raise ValueError("C4 shade inventory changed")
    before = c4_preservation_snapshot()
    write_json(output / "c4-preservation-before.json", before)
    original_meshes = {obj.name: _content_sha(_mesh_content(obj.data)) for obj in objects}
    vertices, faces, smooth = build_fluted_globe(previous["globe_diameter"], previous["groove_depth"])
    for obj in objects:
        old = obj.data
        mesh = bpy.data.meshes.new(obj.name + " C4 continuous flutes editable mesh")
        mesh.from_pydata(vertices, [], faces)
        mesh.update()
        for material in old.materials:
            mesh.materials.append(material)
        for polygon, flag in zip(mesh.polygons, smooth):
            polygon.use_smooth = flag
        mesh["geometry_recipe"] = C4_REVISION
        mesh["pattern_estimated"] = True
        mesh["groove_depth_control_retained_m"] = previous["groove_depth"]
        mesh["diagonal_valley_depth_factor"] = .4
        obj.data = mesh
        bpy.data.meshes.remove(old)
    bpy.context.scene["construction_revision"] = C4_REVISION
    after = c4_preservation_snapshot()
    write_json(output / "c4-preservation-after.json", after)
    if before != after:
        raise RuntimeError("C4 changed preserved native state: " + ", ".join(k for k in before if before[k] != after[k]))
    candidate = output / "candidate.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), check_existing=False, relative_remap=False)
    saved_sha = sha256(candidate)
    # Reopen actual saved bytes under disabled autoexec, not an in-memory claim.
    open_native({"input": {"path": candidate, "sha256": saved_sha}})
    reopened = c4_preservation_snapshot()
    write_json(output / "c4-preservation-readback.json", reopened)
    if after != reopened:
        raise RuntimeError("C4 saved readback changed preserved state: " + ", ".join(k for k in after if after[k] != reopened[k]))
    report = technical()
    shade_checks = [g for g in report["geometry"] if g["name"] in C4_SHADES]
    if len(shade_checks) != 3 or any(g["non_manifold_edges"] or g["zero_area_faces"] or g.get("connected_components") != 1 for g in shade_checks):
        raise RuntimeError("C4 actual saved shade topology failed")
    report["refinement"] = {"method": "exact C3 input; replace only three acrylic mesh datablocks in place",
        "input_parameters": previous, "updated_parameters": json.loads(bpy.context.scene["recipe_parameters_json"]),
        "geometry_revision": C4_REVISION,
        "preservation": {"before_sha256": _content_sha(before), "after_sha256": _content_sha(after),
                         "readback_sha256": _content_sha(reopened), "equal": before == after == reopened,
                         "section_sha256": {k: _content_sha(v) for k, v in before.items()},
                         "candidate_sha256_at_readback": saved_sha,
                         "original_mesh_sha256": original_meshes,
                         "new_mesh_sha256": {obj.name: _content_sha(_mesh_content(obj.data)) for obj in bpy.context.scene.objects if obj.name in C4_SHADES},
                         "saved_candidate_reopened": True,
                         "allowed_changes": ["three acrylic mesh datablocks", "scene construction_revision"],
                         "legacy_object_metadata": "C3 object carving_kind is retained; C4 mesh geometry_recipe and scene construction_revision identify the new geometry"}}
    return candidate, report


def pole_light_ring(name, major, minor, center_z, mat, parent):
    vertices, faces = [], []
    around, section = 64, 12
    for i in range(around):
        a = 2 * math.pi * i / around
        for j in range(section):
            b = 2 * math.pi * j / section
            radius = major + minor * math.cos(b)
            vertices.append((radius * math.cos(a), radius * math.sin(a), center_z + minor * math.sin(b)))
    for i in range(around):
        for j in range(section):
            faces.append((i*section+j, ((i+1)%around)*section+j,
                          ((i+1)%around)*section+(j+1)%section, i*section+(j+1)%section))
    return mesh_object(name, vertices, faces, mat, parent)


def build(parameters: dict, output: Path) -> Path:
    p = {**DEFAULTS, **parameters}
    for name, bounds in BOUNDS.items():
        p[name] = number(p[name], name, *bounds)
    if p["globe_diameter"] > p["width"]:
        raise ValueError("globe diameter cannot exceed overall width")
    if p["globe_spacing"] <= p["globe_diameter"] * 1.38:
        raise ValueError("spacing leaves no connector clearance")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for mat in list(bpy.data.materials):
        bpy.data.materials.remove(mat)
    for image in list(bpy.data.images):
        if image.source != "VIEWER":
            bpy.data.images.remove(image)
    scene = bpy.context.scene
    scene["product_label"] = LABEL
    scene["trusted_recipe"] = RECIPE
    scene["recipe_parameters_json"] = json.dumps(p, sort_keys=True)
    scene["reference_facts_json"] = json.dumps(REFERENCE_FACTS, sort_keys=True)
    scene["construction_revision"] = "c3-facet-aligned-triangles-smooth-bands-annular-pole-light"
    scene["native_role"] = "Editable visual asset; approximated hidden mounting and optical internals"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1
    control = link_object("Arlette Controls", None)
    control.empty_display_type = "PLAIN_AXES"
    control.empty_display_size = .03
    for name, value in p.items():
        control[name] = value
        if name in BOUNDS:
            control.id_properties_ui(name).update(min=BOUNDS[name][0], max=BOUNDS[name][1], description=name.replace("_", " ") + (" in metres" if name not in {"brass_roughness", "acrylic_roughness"} else ""))
    control["edit_note"] = "Dimensions, globe diameter/spacing and roughness update live; groove depth/material mode use trusted refine operation."
    rig = link_object("Arlette Dimension Rig", None)
    for index, key in enumerate(("width", "projection", "height")):
        add_driver(rig, "scale", control, f"d/{p[key]:.12g}", {"d": key}, index)
    mats = make_materials(control, p["material_mode"])
    g = p["globe_diameter"]
    spacing = p["globe_spacing"]
    globe_y = -(p["projection"] - g / 2)
    bottom_z = .076 * g / .107
    pole_z = g * .45
    geometry_scale = g / .107
    for index in range(3):
        assembly = link_object(f"Shade {index + 1:02d} assembly", None, rig)
        assembly.location = (0, globe_y, bottom_z + index * spacing)
        add_driver(assembly, "location", control, f"{bottom_z:.12g}+{index}*s", {"s": "globe_spacing"}, 2)
        for axis in range(3):
            add_driver(assembly, "scale", control, f"g/{g:.12g}", {"g": "globe_diameter"}, axis)
        carved_globe(f"Shade {index + 1:02d} carved acrylic shell", g, p["groove_depth"], mats["acrylic"], assembly)
        # Cups follow the flattened poles; rounded collars remain separate editable components.
        for sign, side in ((-1, "lower"), (1, "upper")):
            cup = [(0, pole_z), (.0233 * geometry_scale, pole_z),
                   (.0228 * geometry_scale, pole_z + .001 * geometry_scale),
                   (.013 * geometry_scale, pole_z + .003 * geometry_scale),
                   (0, pole_z + .003 * geometry_scale)]
            if sign == -1:
                cup = [(r, -z) for r, z in cup[::-1]]
            lathe(f"Shade {index + 1:02d} {side} shallow brass cup", cup, mats["brass"], assembly)
            base = pole_z + .003 * geometry_scale
            collar = [(0, base), (.010 * geometry_scale, base),
                      (.013 * geometry_scale, base + .003 * geometry_scale),
                      (.014 * geometry_scale, base + .010 * geometry_scale),
                      (.013 * geometry_scale, base + .016 * geometry_scale),
                      (.0095 * geometry_scale, base + .022 * geometry_scale),
                      (0, base + .022 * geometry_scale)]
            if index == 0 and sign == -1:
                collar = [(0, -bottom_z), (.004 * geometry_scale, -bottom_z + .0008 * geometry_scale),
                          (.010 * geometry_scale, -bottom_z + .004 * geometry_scale),
                          (.013 * geometry_scale, -base - .013 * geometry_scale),
                          (.014 * geometry_scale, -base - .008 * geometry_scale),
                          (.012 * geometry_scale, -base), (0, -base)]
            elif sign == -1:
                collar = [(r, -z) for r, z in collar[::-1]]
            lathe(f"Shade {index + 1:02d} {side} rounded brass collar", collar, mats["brass"], assembly)
            cylinder(f"Shade {index + 1:02d} {side} warm LED pole disk", .016 * geometry_scale,
                     .0012 * geometry_scale, mats["led"], assembly, (0, 0, sign * (pole_z - .006 * geometry_scale)), bevel=.0002)
            pole_light_ring(f"Shade {index + 1:02d} {side} annular warm pole light", .019 * geometry_scale,
                            .0008 * geometry_scale, sign * (pole_z - .008 * geometry_scale), mats["led"], assembly)
        # Unseen wiring is approximated within the pole modules. The optional
        # exposed center spine created a visible refraction absent in photos.
    end_factor = .45 + .025 / .107
    for index in range(2):
        rod = cylinder(f"Exposed narrow linking rod {index + 1:02d}", .0045, 1, mats["brass"], rig,
                       (0, globe_y, bottom_z + (index + .5) * spacing), bevel=.0005)
        add_driver(rod, "location", control, f"{bottom_z:.12g}+{index + .5}*s", {"s": "globe_spacing"}, 2)
        add_driver(rod, "scale", control, f"s-2*{end_factor:.12g}*g", {"s": "globe_spacing", "g": "globe_diameter"}, 2)
    plate_z = p["height"] - p["width"] / 2
    cylinder("Circular wall backplate", p["width"] / 2, .010, mats["brass"], rig, (0, -.005, plate_z), "Y", .0012)
    cylinder("Raised concentric mounting disk", .030, .006, mats["brass"], rig, (0, -.013, plate_z), "Y", .001)
    arm_front = globe_y + .008
    cylinder("Horizontal cylindrical mounting standoff", .0155, abs(arm_front + .016), mats["brass"], rig,
             (0, (arm_front - .016) / 2, plate_z), "Y", .0012)
    cylinder("Rounded clevis pivot pin", .0085, .027, mats["brass"], rig, (0, globe_y + .002, plate_z), "X", .001)
    for sign in (-1, 1):
        box(f"Clevis cheek {sign:+d}", (.0035, .014, .026), (sign * .0095, globe_y + .002, plate_z - .003), mats["brass"], rig)
    stem_bottom = bottom_z + 2 * spacing + pole_z + .025 * geometry_scale
    stem_top = plate_z - .008
    if stem_top <= stem_bottom:
        raise ValueError("parameters leave no top attachment clearance")
    cylinder("Top vertical attachment neck", .0045, stem_top - stem_bottom, mats["brass"], rig,
             (0, globe_y, (stem_top + stem_bottom) / 2), bevel=.0004)
    screw = cylinder("Visible wallplate side retaining screw", .0025, .002, mats["brass"], rig,
                     (-p["width"] / 2, -.005, plate_z + .015), "X", .0002)
    # Keep the side screw recessed within the published envelope.
    screw.location.x = -p["width"] / 2 + .001
    update_scene()
    dependencies()
    output_candidate = output / "candidate.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(output_candidate), check_existing=False, relative_remap=False)
    return output_candidate


def bounds(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    points = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
    low = [min(v[i] for v in points) for i in range(3)]
    high = [max(v[i] for v in points) for i in range(3)]
    return {"min": low, "max": high, "dimensions": [high[i] - low[i] for i in range(3)]}


def envelope():
    items = [bounds(obj) for obj in bpy.context.scene.objects if obj.type == "MESH" and not obj.name.startswith("CAPTURE ")]
    low = [min(item["min"][i] for item in items) for i in range(3)]
    high = [max(item["max"][i] for item in items) for i in range(3)]
    return {"min": low, "max": high, "dimensions": [high[i] - low[i] for i in range(3)]}


def technical():
    update_scene()
    geometry = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in sorted(bpy.context.scene.objects, key=lambda o: o.name):
        if obj.type != "MESH" or obj.name.startswith("CAPTURE "):
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            item = {"name": obj.name, "vertices": len(mesh.vertices), "polygons": len(mesh.polygons),
                             "non_manifold_edges": sum(not edge.is_manifold for edge in bm.edges),
                             "zero_area_faces": sum(face.calc_area() <= 1e-14 for face in bm.faces),
                             "world_bounds": bounds(obj)}
            if bpy.context.scene.get("construction_revision") == C4_REVISION and obj.name in C4_SHADES:
                remaining = set(bm.verts)
                components = 0
                while remaining:
                    components += 1
                    stack = [remaining.pop()]
                    while stack:
                        current = stack.pop()
                        for edge in current.link_edges:
                            neighbor = edge.other_vert(current)
                            if neighbor in remaining:
                                remaining.remove(neighbor)
                                stack.append(neighbor)
                item.update(connected_components=components, geometry_recipe=obj.data.get("geometry_recipe"),
                            actual_mesh_sha256=_content_sha(_mesh_content(obj.data)),
                            smooth_faces=sum(p.use_smooth for p in mesh.polygons),
                            flat_faces=sum(not p.use_smooth for p in mesh.polygons))
            geometry.append(item)
        finally:
            bm.free()
            evaluated.to_mesh_clear()
    control = bpy.data.objects.get("Arlette Controls")
    if control is None:
        raise ValueError("Arlette editable controls missing")
    editability = []
    for name, index in (("width", 0), ("height", 2), ("projection", 1)):
        old = float(control[name])
        before = envelope()["dimensions"][index]
        try:
            control[name] = old * 1.02
            update_scene()
            changed = envelope()["dimensions"][index]
        finally:
            control[name] = old
            update_scene()
        restored = envelope()["dimensions"][index]
        editability.append({"control": name, "original": old, "perturbed": old * 1.02,
                            "before_dimension": before, "perturbed_dimension": changed,
                            "restored_dimension": restored, "changed": abs(changed - before) > 1e-7,
                            "restored": abs(restored - before) < 1e-7, "saved_perturbation": False})
    old_roughness = float(control["brass_roughness"])
    before_roughness = roughness_socket()
    try:
        control["brass_roughness"] = min(.7, old_roughness + .15)
        update_scene()
        changed_roughness = roughness_socket()
    finally:
        control["brass_roughness"] = old_roughness
        update_scene()
    restored_roughness = roughness_socket()
    editability.append({"control": "brass_roughness", "original": old_roughness,
                        "perturbed": min(.7, old_roughness + .15),
                        "before_socket": before_roughness, "perturbed_socket": changed_roughness,
                        "restored_socket": restored_roughness,
                        "changed": abs(changed_roughness - before_roughness) > 1e-7,
                        "restored": abs(restored_roughness - before_roughness) < 1e-7,
                        "saved_perturbation": False})
    sphere = bpy.data.objects.get("Shade 02 carved acrylic shell")
    for name, axis in (("globe_diameter", 0), ("globe_spacing", 2)):
        old = float(control[name])
        before = bounds(sphere)["dimensions"][axis] if name == "globe_diameter" else bounds(sphere)["min"][axis]
        try:
            control[name] = old * 1.02
            update_scene()
            changed = bounds(sphere)["dimensions"][axis] if name == "globe_diameter" else bounds(sphere)["min"][axis]
        finally:
            control[name] = old
            update_scene()
        restored = bounds(sphere)["dimensions"][axis] if name == "globe_diameter" else bounds(sphere)["min"][axis]
        editability.append({"control": name, "original": old, "perturbed": old * 1.02,
                            "before_measurement": before, "perturbed_measurement": changed,
                            "restored_measurement": restored, "changed": abs(changed - before) > 1e-7,
                            "restored": abs(restored - before) < 1e-7, "saved_perturbation": False})
    materials = []
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        bsdf = mat.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            materials.append({"name": mat.name, "roughness": bsdf.inputs["Roughness"].default_value,
                              "metallic": bsdf.inputs["Metallic"].default_value,
                              "transmission_weight": bsdf.inputs["Transmission Weight"].default_value,
                              "ior": bsdf.inputs["IOR"].default_value})
    return {"provenance_kind": "actual_product_execution", "product_label": LABEL, "trusted_recipe": RECIPE,
            "blender_version": bpy.app.version_string, "background": bool(bpy.app.background),
            "autoexec_enabled": bool(bpy.context.preferences.filepaths.use_scripts_auto_execute),
            "autoexec_fail": bool(bpy.app.autoexec_fail), "native_file_loaded": bpy.data.filepath,
            "geometry": geometry, "product_envelope_m": envelope(),
            "shade_count": len([o for o in geometry if "carved acrylic shell" in o["name"]]),
            "object_driver_count": sum(len(obj.animation_data.drivers) if obj.animation_data else 0 for obj in bpy.context.scene.objects),
            "control_properties": {key: control[key] for key in DEFAULTS}, "editability": editability,
            "materials": materials, "external_dependencies": dependencies(),
            "reference_facts": REFERENCE_FACTS,
            "assumptions": ["Inferred mounting depth and hidden electrical details", "Estimated acrylic wall thickness and carving pattern", "Warm pole emission is a visual approximation, not measured photometry", "Procedural microbrush uses generated coordinates with estimated frequency; it is not measured surface metrology"],
            "sandbox_claim": False}


def point_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def roughness_socket():
    mat = bpy.data.materials["Arlette satin natural brass"]
    evaluated = mat.evaluated_get(bpy.context.evaluated_depsgraph_get())
    return float(evaluated.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value)


def capture(request, output, *, diagnostic=False):
    params = open_native(request)
    if diagnostic and params["material_mode"] != "final":
        raise ValueError("rendered material editability requires the final-material candidate")
    report = technical()
    scene = bpy.context.scene
    for obj in list(scene.objects):
        if obj.type in {"LIGHT", "CAMERA"} or obj.name.startswith("CAPTURE "):
            bpy.data.objects.remove(obj, do_unlink=True)
    world = bpy.data.worlds.new("CAPTURE neutral studio")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (.86, .89, .94, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .55
    scene.world = world
    for name, position, energy, size, size_y in (
        ("key strip", (-.7, -.9, 1.0), CAPTURE_PROFILE["lights"][0]["energy"], .7, 1.5),
        ("fill strip", (.6, -.55, .65), CAPTURE_PROFILE["lights"][1]["energy"], .35, 1.1),
        ("rim strip", (-.55, .01, .48), CAPTURE_PROFILE["lights"][2]["energy"], .2, .9),
    ):
        data = bpy.data.lights.new("CAPTURE " + name, "AREA")
        data.energy = energy
        data.shape = "RECTANGLE"
        data.size = size
        data.size_y = size_y
        obj = link_object("CAPTURE " + name, data)
        obj.location = position
        point_at(obj, (0, -.08, .30))
    wall = bpy.data.materials.new("CAPTURE neutral wall")
    wall.use_nodes = True
    wall.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.85, .85, .85, 1)
    wall.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = .8
    box("CAPTURE wall", (4, .01, 4), (0, .015, .30), wall, bevel=0)
    camera_data = bpy.data.cameras.new("CAPTURE fixed comparison camera")
    camera_data.type = "ORTHO"
    camera = link_object("CAPTURE fixed comparison camera", camera_data)
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.cycles.seed = 0
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 10
    scene.cycles.transparent_max_bounces = 12
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    px = 1200 if diagnostic else request["parameters"]["preview_px"]
    scene.render.resolution_x = px
    scene.render.resolution_y = px
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = CAPTURE_PROFILE["exposure"]
    scene.view_settings.gamma = 1
    fixed = CAPTURE_PROFILE["views"]
    native_meshes = [obj for obj in scene.objects if obj.type == "MESH" and not obj.name.startswith("CAPTURE ")]
    original_slots = {obj.name: list(obj.data.materials) for obj in native_meshes}
    clay = bpy.data.materials["Arlette neutral clay"]
    wire_material = bpy.data.materials.new("CAPTURE cage edge material")
    wire_material.use_nodes = True
    wire_material.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (.035, .05, .065, 1)
    cage_objects = []
    for obj in native_meshes:
        if "carved acrylic shell" not in obj.name:
            continue
        duplicate = obj.copy()
        duplicate.data = obj.data.copy()
        duplicate.name = "CAPTURE cage " + obj.name
        scene.collection.objects.link(duplicate)
        duplicate.data.materials.clear()
        duplicate.data.materials.append(wire_material)
        wire = duplicate.modifiers.new("Actual mesh wire cage", "WIREFRAME")
        wire.thickness = .000055
        wire.use_replace = True
        wire.use_even_offset = True
        duplicate.hide_render = True
        cage_objects.append(duplicate)
    captures = []
    control = bpy.data.objects["Arlette Controls"]
    original_width, original_roughness = float(control["width"]), float(control["brass_roughness"])
    diagnostic_states = []
    selected_views = ["editability-baseline", "editability-perturbed"] if diagnostic else request["parameters"]["views"]
    try:
        for view in selected_views:
            if view == "editability-perturbed":
                control["width"] = original_width * 1.1
                control["brass_roughness"] = min(.7, max(.48, original_roughness + .2))
                update_scene()
            config = fixed["full" if diagnostic else "detail" if view == "cage" else "full" if view == "clay" else view]
            camera.location = config["position"]
            camera_data.ortho_scale = config["scale"]
            point_at(camera, config["target"])
            for obj in native_meshes:
                obj.data.materials.clear()
                for mat in ([clay] if view in {"clay", "cage"} else original_slots[obj.name]):
                    obj.data.materials.append(mat)
            for obj in cage_objects:
                obj.hide_render = view != "cage"
            if diagnostic:
                diagnostic_states.append({"view": view, "width_control": float(control["width"]),
                                          "brass_roughness_control": float(control["brass_roughness"]),
                                          "brass_roughness_socket": roughness_socket(), "product_envelope_m": envelope()})
            scene.render.filepath = str(output / (view + ".png"))
            bpy.ops.render.render(write_still=True)
            captures.append({"view": view, "camera": config, "path": view + ".png",
                             "material_override": "neutral clay" if view in {"clay", "cage"} else None,
                             "actual_mesh_wire_overlay": view == "cage"})
    finally:
        control["width"], control["brass_roughness"] = original_width, original_roughness
        update_scene()
    profile = json.loads(json.dumps(CAPTURE_PROFILE))
    profile["resolution"] = [px, px]
    if diagnostic:
        profile.update(id="arlette-editability-diagnostic-v1", eligible_for_product_review=False)
    profile_hash = hashlib.sha256(json.dumps(profile, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
    report["capture"] = {"candidate_sha256": request["input"]["sha256"],
                         "comparison_settings_version": CAPTURE_PROFILE["id"], "views": captures,
                         "profile": profile, "profile_sha256": profile_hash,
                         "engine": "CYCLES", "device": "CPU", "samples": 32, "seed": 0,
                         "resolution": [px, px], "view_transform": "AgX", "exposure": -1.5,
                         "native_file_resaved": False, "saved_native_changes": False, "human_approval": None}
    if diagnostic:
        report["rendered_editability"] = {"states": diagnostic_states,
                                          "restored_width_control": float(control["width"]),
                                          "restored_roughness_control": float(control["brass_roughness"]),
                                          "restored_roughness_socket": roughness_socket(),
                                          "restored_product_envelope_m": envelope(),
                                          "saved_native_changes": False, "human_approval": None}
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parser.parse_args(argv)
    output = checked_path(args.output)
    if output in {Path("/"), Path.home(), Path.cwd()}:
        raise ValueError("output must be a dedicated private directory")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("private output must be initially empty")
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    write_json(output / "worker-start.json", {"pid": os.getpid(), "started_at_unix": started, "kind": "actual_product_execution"})
    request_path = checked_path(args.request, file=True)
    if request_path.is_relative_to(output):
        raise ValueError("request must be outside output")
    request = validate(json.loads(request_path.read_text()), output)
    if not bpy.app.background or bpy.context.preferences.filepaths.use_scripts_auto_execute:
        raise ValueError("background and disabled automatic execution required")
    operation = request["operation"]
    candidate = None
    if operation == "build_arlette_v1":
        candidate = build(request["parameters"], output)
        report = technical()
    elif operation == "refine_arlette_v1":
        previous = open_native(request)
        if request_path.parent.name == C4_JOB or output.parent.name == C4_JOB:
            candidate, report = refine_c4_geometry(request, request_path, output, previous)
        else:
            previous_report = technical()
            candidate = build({**previous, **request["parameters"]}, output)
            report = technical()
            report["refinement"] = {"input_parameters": previous, "updated_parameters": json.loads(bpy.context.scene["recipe_parameters_json"]),
                                    "before_envelope": previous_report["product_envelope_m"], "method": "trusted finite component recipe rebuild"}
    elif operation == "inspect_arlette_v1":
        if request["parameters"]["editability_render"]:
            report = capture(request, output, diagnostic=True)
        else:
            open_native(request)
            report = technical()
    else:
        report = capture(request, output)
    if request["input"] and sha256(request["input"]["path"]) != request["input"]["sha256"]:
        raise RuntimeError("immutable native source changed")
    report["worker_seconds"] = time.time() - started
    report["input_preservation"] = {"unchanged": True, "sha256": request["input"]["sha256"]} if request["input"] else None
    base = {"operation": operation, "provenance_kind": "actual_product_execution",
            "input_sha256": request["input"]["sha256"] if request["input"] else None,
            "output_candidate": {"path": str(candidate), "sha256": sha256(candidate)} if candidate else None,
            "technical": report}
    write_json(output / "report.json", base)
    artifacts = [{"path": str(path.relative_to(output)), "sha256": sha256(path), "bytes": path.stat().st_size}
                 for path in sorted(output.rglob("*")) if path.is_file()]
    write_json(output / "result.json", {**base, "artifacts": artifacts})
    print(json.dumps({"operation": operation, "result": str(output / "result.json")}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
