"""Trusted, finite Blender operations for disposable adapter fixtures.

Run only via the adapter host. Path validation and --disable-autoexec are not
an operating-system sandbox; this module does not accept executable recipes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

import bpy
import bmesh
from mathutils import Vector


OPERATIONS = {
    "build_fixture_v1": {"width", "depth", "height", "hold_seconds"},
    "edit_width_v1": {"width", "hold_seconds"},
    "inspect_v1": {"hold_seconds"},
    "render_v1": {"preview_px", "hold_seconds", "views"},
}
FIXTURE_LABEL = "DEFECTIVE_PRIMITIVE"
VIEW_CONFIG = {
    "full": {"location": (2.8, -3.6, 2.4), "target": (0, 0, 0.5), "scale": 2.4},
    "detail": {"location": (2.0, -2.8, 1.5), "target": (0, 0, 0.55), "scale": 1.4},
    "alternate": {"location": (-2.6, -3.2, 1.4), "target": (0, 0, 0.5), "scale": 2.4},
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def checked_path(value: str, *, file: bool = False) -> Path:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise ValueError("path must be a nonempty string")
    path = Path(value)
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("paths must be absolute without parent traversal")
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError(f"symlink path is unsupported: {part}")
    if file and not path.is_file():
        raise ValueError(f"required file is missing: {path}")
    return path.resolve()


def checked_record(value: dict) -> dict:
    if not isinstance(value, dict) or set(value) != {"path", "sha256"}:
        raise ValueError("file records require exactly path and sha256")
    path = checked_path(value["path"], file=True)
    claimed = value["sha256"]
    if not isinstance(claimed, str) or len(claimed) != 64 or any(
        c not in "0123456789abcdef" for c in claimed
    ):
        raise ValueError("sha256 must be lowercase hexadecimal")
    measured = sha256(path)
    if measured != claimed:
        raise ValueError(f"stale or altered input: {path}")
    return {"path": path, "sha256": measured}


def number(value, label: str, lower: float, upper: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number")
    value = float(value)
    if not math.isfinite(value) or not lower <= value <= upper:
        raise ValueError(f"{label} must be within {lower}..{upper}")
    return value


def validate_request(raw: dict, output: Path) -> dict:
    if not isinstance(raw, dict) or set(raw) != {"operation", "input", "assets", "parameters"}:
        raise ValueError("request requires operation, input, assets and parameters")
    operation = raw["operation"]
    if operation not in OPERATIONS:
        raise ValueError("unsupported operation")
    source = checked_record(raw["input"]) if raw["input"] is not None else None
    if (operation == "build_fixture_v1") != (source is None):
        raise ValueError("only build_fixture_v1 accepts a null input")
    if source and source["path"].suffix.lower() != ".blend":
        raise ValueError("native input must have a .blend extension")
    if not isinstance(raw["assets"], list):
        raise ValueError("assets must be a list")
    assets = [checked_record(item) for item in raw["assets"]]
    if len({item["path"] for item in assets}) != len(assets):
        raise ValueError("duplicate asset declarations")
    for item in assets + ([source] if source else []):
        if item["path"].is_relative_to(output):
            raise ValueError("source input cannot reside in private output")
    parameters = raw["parameters"]
    if not isinstance(parameters, dict) or set(parameters) - OPERATIONS[operation]:
        raise ValueError("unsupported parameters")
    result = dict(parameters)
    for name, default in (("width", 0.8), ("depth", 0.35), ("height", 0.8)):
        result[name] = number(parameters.get(name, default), name, 0.05, 3.0)
    result["hold_seconds"] = number(parameters.get("hold_seconds", 0), "hold_seconds", 0, 60)
    preview = parameters.get("preview_px", 384)
    if isinstance(preview, bool) or not isinstance(preview, int) or not 64 <= preview <= 512:
        raise ValueError("preview_px must be an integer within 64..512")
    result["preview_px"] = preview
    views = parameters.get("views", ["full", "detail", "alternate"])
    if not isinstance(views, list) or not views or any(v not in VIEW_CONFIG for v in views):
        raise ValueError("views must contain supported view names")
    if len(set(views)) != len(views):
        raise ValueError("duplicate views")
    result["views"] = views
    return {"operation": operation, "input": source, "assets": assets, "parameters": result}


def assert_preserved(request: dict) -> list[dict]:
    records = request["assets"] + ([request["input"]] if request["input"] else [])
    observations = []
    for record in records:
        current = sha256(record["path"])
        if current != record["sha256"]:
            raise RuntimeError(f"immutable input changed: {record['path']}")
        observations.append({"path": str(record["path"]), "sha256": current, "unchanged": True})
    return observations


def update_scene() -> None:
    for obj in bpy.context.scene.objects:
        obj.update_tag()
    bpy.context.view_layer.update()
    bpy.context.scene.frame_set(bpy.context.scene.frame_current)
    bpy.context.evaluated_depsgraph_get().update()


def dependency_inventory(declared: list[dict], *, verify: bool = True) -> list[dict]:
    """Finite fixture contract: external images only; other file types fail closed."""
    if bpy.data.libraries:
        raise ValueError("linked libraries are not supported by fixture operations")
    for collection_name in ("movieclips", "sounds", "cache_files", "volumes"):
        if len(getattr(bpy.data, collection_name, ())):
            raise ValueError(f"external {collection_name} are unsupported")
    for font in bpy.data.fonts:
        if font.filepath and font.filepath != "<builtin>" and not font.packed_file:
            raise ValueError("external fonts are unsupported")
    approved = {item["path"]: item["sha256"] for item in declared}
    records = []
    seen = set()
    for image in bpy.data.images:
        if image.source in {"GENERATED", "VIEWER"}:
            continue
        if image.packed_file:
            records.append({"kind": "image", "name": image.name, "packed": True})
            continue
        if image.source != "FILE" or not image.filepath:
            raise ValueError(f"unsupported image source: {image.name}/{image.source}")
        path = checked_path(bpy.path.abspath(image.filepath), file=True)
        measured = sha256(path)
        if verify and approved.get(path) != measured:
            raise ValueError(f"undeclared or changed image dependency: {path}")
        seen.add(path)
        records.append({
            "kind": "image", "name": image.name, "packed": False,
            "stored_path": image.filepath, "resolved_path": str(path),
            "sha256": measured, "bytes": path.stat().st_size,
        })
    if verify and set(approved) != seen:
        raise ValueError("declared assets do not exactly match scene dependencies")
    return records


def open_source(request: dict) -> list[dict]:
    source = request["input"]
    if sha256(source["path"]) != source["sha256"]:
        raise ValueError("candidate changed immediately before scene open")
    bpy.ops.wm.open_mainfile(filepath=str(source["path"]), load_ui=False, use_scripts=False)
    if bpy.context.preferences.filepaths.use_scripts_auto_execute:
        raise RuntimeError("automatic script execution must remain disabled")
    if bpy.context.scene.get("adapter_fixture") != FIXTURE_LABEL:
        raise ValueError("fixture operation requires the labelled disposable fixture")
    update_scene()
    return dependency_inventory(request["assets"])


def material(name: str, color: tuple[float, ...], roughness: float):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def make_cube(name: str, location: tuple, dimensions: tuple, mat):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = dimensions
    obj.data.materials.append(mat)
    bevel = obj.modifiers.new("Editable edge rounding", "BEVEL")
    bevel.width = 0.035
    bevel.segments = 3
    return obj


def build_fixture(request: dict, output: Path) -> Path:
    if request["assets"]:
        raise ValueError("primitive creation does not accept external assets")
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablock in list(bpy.data.images):
        if datablock.source != "VIEWER":
            bpy.data.images.remove(datablock)
    scene = bpy.context.scene
    scene["adapter_fixture"] = FIXTURE_LABEL
    scene["fixture_purpose"] = "Intentionally narrow width 0.8; correction target 1.2. Not a product."
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    p = request["parameters"]
    control = bpy.data.objects.new("Control", None)
    scene.collection.objects.link(control)
    control.empty_display_type = "PLAIN_AXES"
    control["width"] = p["width"]
    control["depth"] = p["depth"]
    control["height"] = p["height"]
    control.id_properties_ui("width").update(min=0.05, max=3.0, description="Body width in metres")
    body_mat = material("Fixture neutral textured clay", (0.42, 0.45, 0.48, 1), 0.65)
    image = bpy.data.images.new("Procedural fixture checker", width=32, height=32, alpha=False)
    pixels = []
    for y in range(32):
        for x in range(32):
            value = 0.44 if (x // 8 + y // 8) % 2 else 0.48
            pixels.extend((value, value, value, 1.0))
    image.pixels = pixels
    image.filepath_raw = str(output / "asset.png")
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    external = bpy.data.images.load(str(output / "asset.png"), check_existing=False)
    external.name = "Fixture external texture"
    texture = body_mat.node_tree.nodes.new("ShaderNodeTexImage")
    texture.image = external
    body_mat.node_tree.links.new(texture.outputs["Color"], body_mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
    body = make_cube("DEFECTIVE_PRIMITIVE_body", (0, 0, p["height"] / 2 + 0.06), (p["width"], p["depth"], p["height"]), body_mat)
    driver = body.driver_add("scale", 0).driver
    driver.type = "SCRIPTED"
    variable = driver.variables.new()
    variable.name = "width"
    variable.type = "SINGLE_PROP"
    variable.targets[0].id = control
    variable.targets[0].data_path = '["width"]'
    driver.expression = "width"
    base_mat = material("Fixture base clay", (0.21, 0.23, 0.25, 1), 0.72)
    make_cube("Fixture_base", (0, 0, 0.03), (0.38, 0.30, 0.06), base_mat)
    update_scene()
    external.filepath = "//asset.png"
    candidate = output / "candidate.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), check_existing=False, relative_remap=False)
    return candidate


def edit_width(request: dict, output: Path) -> tuple[Path, dict]:
    before_dependencies = open_source(request)
    before = technical_report(request["assets"])
    copied = {}
    for image in bpy.data.images:
        if image.source != "FILE" or image.packed_file:
            continue
        original = checked_path(bpy.path.abspath(image.filepath), file=True)
        if original not in copied:
            destination = output / f"asset-{len(copied):03d}{original.suffix.lower()}"
            shutil.copyfile(original, destination)
            copied[original] = destination
        image.filepath = "//" + copied[original].name
    control = bpy.data.objects.get("Control")
    if control is None or "width" not in control:
        raise ValueError("editable width control is missing")
    control["width"] = request["parameters"]["width"]
    update_scene()
    candidate = output / "candidate.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(candidate), check_existing=False, relative_remap=False)
    return candidate, {"before": before, "source_dependencies": before_dependencies}


def object_bounds(obj) -> dict:
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    points = [evaluated.matrix_world @ Vector(corner) for corner in evaluated.bound_box]
    minimum = [min(v[i] for v in points) for i in range(3)]
    maximum = [max(v[i] for v in points) for i in range(3)]
    return {"min": minimum, "max": maximum, "dimensions": [maximum[i] - minimum[i] for i in range(3)]}


def technical_report(declared: list[dict], *, verify_dependencies: bool = True) -> dict:
    update_scene()
    geometry = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for obj in sorted(bpy.context.scene.objects, key=lambda item: item.name):
        if obj.type != "MESH":
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        bm = bmesh.new()
        try:
            bm.from_mesh(mesh)
            geometry.append({
                "name": obj.name, "vertices": len(mesh.vertices),
                "edges": len(mesh.edges), "polygons": len(mesh.polygons),
                "non_manifold_edges": sum(not edge.is_manifold for edge in bm.edges),
                "zero_area_faces": sum(face.calc_area() <= 1e-12 for face in bm.faces),
                "world_bounds": object_bounds(obj),
                "modifiers": [{"name": m.name, "type": m.type} for m in obj.modifiers],
            })
        finally:
            bm.free()
            evaluated.to_mesh_clear()
    control = bpy.data.objects.get("Control")
    body = bpy.data.objects.get("DEFECTIVE_PRIMITIVE_body")
    editability = {"tested": False}
    if control is not None and body is not None and "width" in control:
        original = float(control["width"])
        old_bounds = object_bounds(body)
        changed = original * 1.1
        try:
            control["width"] = changed
            update_scene()
            changed_bounds = object_bounds(body)
        finally:
            control["width"] = original
            update_scene()
        restored = object_bounds(body)
        editability = {
            "tested": True, "saved_perturbation": False, "property": "Control[width]",
            "original": original, "perturbed": changed,
            "before_dimensions": old_bounds["dimensions"],
            "perturbed_dimensions": changed_bounds["dimensions"],
            "restored_dimensions": restored["dimensions"],
            "width_changed": abs(changed_bounds["dimensions"][0] - old_bounds["dimensions"][0]) > 1e-6,
            "width_restored": abs(restored["dimensions"][0] - old_bounds["dimensions"][0]) < 1e-6,
        }
    driver_count = sum(len(obj.animation_data.drivers) if obj.animation_data else 0 for obj in bpy.context.scene.objects)
    return {
        "blender_version": bpy.app.version_string,
        "blender_build_hash": bpy.app.build_hash.decode("ascii", errors="replace"),
        "background": bool(bpy.app.background),
        "autoexec_enabled": bool(bpy.context.preferences.filepaths.use_scripts_auto_execute),
        "autoexec_fail": bool(bpy.app.autoexec_fail),
        "fixture_label": bpy.context.scene.get("adapter_fixture"),
        "objects": [{"name": obj.name, "type": obj.type} for obj in sorted(bpy.context.scene.objects, key=lambda item: item.name)],
        "geometry": geometry, "driver_count": driver_count,
        "control_properties": {key: control[key] for key in ("width", "depth", "height") if control is not None and key in control},
        "editability": editability,
        "external_dependencies": dependency_inventory(declared, verify=verify_dependencies),
        "units": {"system": bpy.context.scene.unit_settings.system, "scale_length": bpy.context.scene.unit_settings.scale_length},
        "native_file_loaded": bpy.data.filepath,
    }


def point_at(obj, target: tuple) -> None:
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()


def render(request: dict, output: Path) -> dict:
    open_source(request)
    technical = technical_report(request["assets"])
    scene = bpy.context.scene
    for obj in list(scene.objects):
        if obj.type in {"LIGHT", "CAMERA"}:
            bpy.data.objects.remove(obj, do_unlink=True)
    world = bpy.data.worlds.new("Adapter capture neutral world")
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.72, 0.72, 0.72, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.35
    scene.world = world
    for name, location, power, size in (
        ("Capture key", (2, -3, 4), 500, 3),
        ("Capture fill", (-3, -1, 2), 250, 3),
    ):
        data = bpy.data.lights.new(name, type="AREA")
        data.energy = power
        data.shape = "DISK"
        data.size = size
        light = bpy.data.objects.new(name, data)
        scene.collection.objects.link(light)
        light.location = location
        point_at(light, (0, 0, 0.4))
    camera_data = bpy.data.cameras.new("Adapter capture camera")
    camera_data.type = "ORTHO"
    camera = bpy.data.objects.new("Adapter capture camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 8
    scene.cycles.use_denoising = False
    scene.cycles.seed = 0
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    scene.render.resolution_x = request["parameters"]["preview_px"]
    scene.render.resolution_y = request["parameters"]["preview_px"]
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    capture = []
    for view in request["parameters"]["views"]:
        config = VIEW_CONFIG[view]
        camera.location = config["location"]
        camera_data.ortho_scale = config["scale"]
        point_at(camera, config["target"])
        scene.render.filepath = str(output / f"{view}.png")
        bpy.ops.render.render(write_still=True)
        capture.append({"view": view, "camera": config, "path": f"{view}.png"})
    technical["capture"] = {
        "candidate_sha256": request["input"]["sha256"],
        "engine": scene.render.engine, "device": scene.cycles.device,
        "samples": scene.cycles.samples, "seed": scene.cycles.seed,
        "resolution": [scene.render.resolution_x, scene.render.resolution_y],
        "color_mode": "RGB", "film_transparent": False,
        "view_transform": scene.view_settings.view_transform,
        "comparison_settings_version": "fixture-capture-v1",
        "saved_native_changes": False, "views": capture,
    }
    return technical


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True)
    parser.add_argument("--output", required=True)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    args = parser.parse_args(argv)
    output = checked_path(args.output)
    if output == Path("/") or output == Path.home() or output == Path.cwd():
        raise ValueError("private output must be a dedicated directory")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("private output must be initially empty")
    output.mkdir(parents=True, exist_ok=True)
    started = time.time()
    write_json(output / "worker-start.json", {"pid": os.getpid(), "started_at_unix": started, "kind": "actual_native_fixture"})
    request_path = checked_path(args.request, file=True)
    if request_path.is_relative_to(output):
        raise ValueError("request must be outside private output")
    request = validate_request(json.loads(request_path.read_text(encoding="utf-8")), output)
    if not bpy.app.background or bpy.context.preferences.filepaths.use_scripts_auto_execute:
        raise RuntimeError("background mode with automatic execution disabled is required")
    time.sleep(request["parameters"]["hold_seconds"])
    candidate = None
    operation = request["operation"]
    if operation == "build_fixture_v1":
        candidate = build_fixture(request, output)
        technical = technical_report([], verify_dependencies=False)
    elif operation == "edit_width_v1":
        candidate, edit = edit_width(request, output)
        technical = technical_report([], verify_dependencies=False)
        technical["edit"] = edit
    elif operation == "inspect_v1":
        open_source(request)
        technical = technical_report(request["assets"])
    else:
        technical = render(request, output)
    technical["input_preservation"] = assert_preserved(request)
    technical["worker_seconds"] = time.time() - started
    technical["sandbox_claim"] = False
    candidate_record = {"path": str(candidate), "sha256": sha256(candidate)} if candidate else None
    report = {
        "operation": operation, "provenance_kind": "actual_native_fixture",
        "input_sha256": request["input"]["sha256"] if request["input"] else None,
        "output_candidate": candidate_record, "technical": technical,
    }
    write_json(output / "report.json", report)
    artifacts = [{"path": str(path.relative_to(output)), "sha256": sha256(path), "bytes": path.stat().st_size}
                 for path in sorted(output.rglob("*")) if path.is_file()]
    write_json(output / "result.json", {**report, "artifacts": artifacts})
    print(json.dumps({"operation": operation, "result": str(output / "result.json")}), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
