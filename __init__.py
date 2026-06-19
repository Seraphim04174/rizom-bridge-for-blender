bl_info = {
    "name": "RizomUV Bridge",
    "author": "OpenAI",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > RizomUV",
    "description": "Send a mesh to RizomUV and pull edited UVs back into Blender",
    "category": "UV",
}

import json
import subprocess
import tempfile
import traceback
import uuid
from datetime import datetime
from pathlib import Path

import bpy
from bpy.props import PointerProperty, StringProperty
from bpy.types import Operator, Panel, PropertyGroup


class _BridgeRuntime:
    pass


_LOG_PATH = Path(__file__).resolve().parent / "rizomuv_bridge.log"
_HELPER_LOG_PATH = Path(__file__).resolve().parent / "rizomuv_helper.log"
_STATE_PATH = Path(__file__).resolve().parent / "rizomuv_bridge_state.json"
_HELPER_PATH = Path(__file__).resolve().parent / "rizomuv_bridge_helper.py"


def _log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    print(f"[RizomUV Bridge] {message}")
    try:
        with _LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _log_exception(context, exc, *, where):
    active_name = None
    mode = None
    if context is not None:
        active_obj = getattr(context, "active_object", None)
        active_name = getattr(active_obj, "name", None)
        mode = getattr(context, "mode", None)

    _log(
        f"{where} failed: {_error_message(exc)} | "
        f"active_object={active_name!r} | mode={mode!r}"
    )
    _log(traceback.format_exc().rstrip())


def _find_rizom_install_path():
    default_path = Path(r"C:\Program Files\Rizom Lab\RizomUV 2024.1")
    if (default_path / "rizomuv.exe").exists():
        return str(default_path)

    try:
        import winreg
    except ImportError:
        return ""

    for major in range(9, 1, -1):
        for minor in range(10, -1, -1):
            if major == 2 and minor < 2:
                continue
            key_path = f"SOFTWARE\\Rizom Lab\\RizomUV VS RS 202{major}.{minor}"
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
                exe_path = winreg.QueryValue(key, "rizomuv.exe")
            except OSError:
                continue
            return str(Path(exe_path).parent)

    return ""


def _find_rizom_python(install_path):
    python_path = Path(install_path) / "python.exe"
    if python_path.exists():
        return str(python_path)
    raise RuntimeError(f"RizomUV python.exe not found at: {python_path}")


def _get_settings(context):
    return context.scene.rizomuv_bridge


def _resolve_install_path(settings):
    configured = bpy.path.abspath(settings.install_path).strip()
    _log(f"Resolving RizomUV install path. configured={configured!r}")
    if configured:
        exe_path = Path(configured) / "rizomuv.exe"
        if exe_path.exists():
            _log(f"Using configured RizomUV path: {exe_path.parent}")
            return str(exe_path.parent)
        raise RuntimeError(f"RizomUV not found at: {configured}")

    detected = _find_rizom_install_path()
    if detected:
        _log(f"Using detected RizomUV path: {detected}")
        return detected

    raise RuntimeError(
        "RizomUV installation not found. Set the RizomUV path in the addon panel."
    )


def _error_message(exc):
    message = str(exc).strip()
    return message or exc.__class__.__name__


def _run_helper(context, command, *, exchange_path="", object_name=""):
    settings = _get_settings(context)
    install_path = _resolve_install_path(settings)
    python_path = _find_rizom_python(install_path)

    payload = {
        "command": command,
        "install_path": install_path,
        "exchange_path": exchange_path,
        "object_name": object_name,
        "state_path": str(_STATE_PATH),
        "log_path": str(_HELPER_LOG_PATH),
    }
    payload_json = json.dumps(payload)

    cmd = [python_path, str(_HELPER_PATH), payload_json]
    _log(f"Running helper command={command!r} python={python_path!r}")
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        check=False,
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if stdout:
        _log(f"Helper stdout: {stdout}")
    if stderr:
        _log(f"Helper stderr: {stderr}")

    try:
        response = json.loads(stdout or "{}")
    except json.JSONDecodeError as exc:
        if completed.returncode != 0:
            raise RuntimeError(
                f"Helper command '{command}' failed with exit code {completed.returncode}."
            ) from exc
        raise RuntimeError("Helper returned invalid JSON.") from exc

    if completed.returncode != 0:
        raise RuntimeError(
            response.get("error")
            or f"Helper command '{command}' failed with exit code {completed.returncode}."
        )

    if not response.get("ok"):
        raise RuntimeError(response.get("error") or "Helper command failed.")

    _log(f"Helper command {command!r} completed successfully")
    return response


def _ensure_object_mode(context):
    obj = context.active_object
    if obj is None or obj.type != "MESH":
        raise RuntimeError("Select an active mesh object.")
    if context.mode != "OBJECT":
        _log(f"Switching Blender mode from {context.mode} to OBJECT")
        bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def _selected_mesh_objects(context):
    mesh_objects = [obj for obj in context.selected_objects if obj.type == "MESH"]
    if not mesh_objects:
        raise RuntimeError("Select at least one mesh object.")
    return mesh_objects


def _create_exchange_path(label):
    safe_label = label.replace(" ", "_")
    exchange_name = f"rizomuv_bridge_{safe_label}_{uuid.uuid4().hex}.obj"
    return str(Path(tempfile.gettempdir()) / exchange_name)


def _export_objects(context, objects, filepath):
    object_names = [obj.name for obj in objects]
    _log(f"Exporting OBJ for objects {object_names!r} to {filepath}")
    view_layer = context.view_layer
    previous_active = view_layer.objects.active
    previous_selected = list(context.selected_objects)

    try:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in objects:
            obj.select_set(True)
        view_layer.objects.active = objects[0]

        if hasattr(bpy.ops.wm, "obj_export"):
            result = bpy.ops.wm.obj_export(
                filepath=filepath,
                export_selected_objects=True,
                export_uv=True,
                export_materials=False,
                export_triangulated_mesh=False,
            )
        else:
            result = bpy.ops.export_scene.obj(
                filepath=filepath,
                use_selection=True,
                use_uvs=True,
                use_materials=False,
                keep_vertex_order=True,
            )
    finally:
        try:
            bpy.ops.object.select_all(action="DESELECT")
        except Exception:
            pass
        for selected_obj in previous_selected:
            if selected_obj.name in bpy.data.objects:
                selected_obj.select_set(True)
        if previous_active and previous_active.name in bpy.data.objects:
            view_layer.objects.active = previous_active

    if "FINISHED" not in result:
        raise RuntimeError("OBJ export failed.")
    _log("OBJ export finished")


def _import_obj_objects(filepath):
    _log(f"Importing OBJ from {filepath}")
    existing_names = {obj.name for obj in bpy.data.objects}

    if hasattr(bpy.ops.wm, "obj_import"):
        result = bpy.ops.wm.obj_import(filepath=filepath)
    else:
        result = bpy.ops.import_scene.obj(filepath=filepath)

    if "FINISHED" not in result:
        raise RuntimeError("OBJ import failed.")

    new_objects = [obj for obj in bpy.data.objects if obj.name not in existing_names]
    mesh_objects = [obj for obj in new_objects if obj.type == "MESH"]
    if not mesh_objects:
        raise RuntimeError("Imported OBJ did not create a mesh object.")

    _log(f"OBJ import created {len(mesh_objects)} mesh object(s)")
    return mesh_objects, new_objects


def _copy_uvs(source_obj, target_obj):
    _log(f"Copying UVs from {source_obj.name!r} to {target_obj.name!r}")
    source_mesh = source_obj.data
    target_mesh = target_obj.data

    if len(source_mesh.polygons) != len(target_mesh.polygons):
        raise RuntimeError("Polygon count mismatch. Cannot transfer UVs safely.")
    if len(source_mesh.loops) != len(target_mesh.loops):
        raise RuntimeError("Loop count mismatch. Cannot transfer UVs safely.")

    if not source_mesh.uv_layers:
        raise RuntimeError("The mesh returned from RizomUV has no UV layer.")

    source_uv = source_mesh.uv_layers.active or source_mesh.uv_layers[0]
    target_uv = target_mesh.uv_layers.active
    if target_uv is None:
        target_uv = target_mesh.uv_layers.new(name=source_uv.name or "UVMap")

    for src_loop, dst_loop in zip(source_uv.data, target_uv.data):
        dst_loop.uv = src_loop.uv.copy()

    target_mesh.update()
    _log("UV copy finished")


def _mesh_signature(mesh):
    poly_sizes = tuple(len(poly.vertices) for poly in mesh.polygons)
    return (
        len(mesh.vertices),
        len(mesh.edges),
        len(mesh.polygons),
        len(mesh.loops),
        poly_sizes,
    )


def _name_candidates(name):
    separators = (".", ":", "_")
    seen = set()
    queue = [name]
    candidates = []

    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        candidates.append(current)

        for separator in separators:
            for replacement in separators:
                if separator == replacement:
                    continue
                swapped = current.replace(separator, replacement)
                if swapped not in seen:
                    queue.append(swapped)

        for separator in separators:
            base, sep, suffix = current.rpartition(separator)
            if sep and suffix.isdigit() and base and base not in seen:
                queue.append(base)

    return candidates


def _match_imported_to_target(imported_name, target_names):
    target_set = set(target_names)
    for candidate in _name_candidates(imported_name):
        if candidate in target_set:
            return candidate
    return None


def _copy_uvs_batch(imported_meshes, target_objects):
    _log(f"Batch imported object names: {[obj.name for obj in imported_meshes]!r}")
    _log(f"Batch target object names: {[obj.name for obj in target_objects]!r}")
    target_by_name = {obj.name: obj for obj in target_objects}
    imported_by_target = {}

    for imported in imported_meshes:
        target_name = _match_imported_to_target(imported.name, target_by_name.keys())
        if target_name and target_name not in imported_by_target:
            imported_by_target[target_name] = imported

    missing = [name for name in target_by_name if name not in imported_by_target]
    if missing:
        _log(f"Name-based batch matching missed: {missing!r}")

        unmatched_imported = [
            imported
            for imported in imported_meshes
            if imported not in imported_by_target.values()
        ]
        unmatched_targets = [target_by_name[name] for name in missing]

        imported_by_signature = {}
        for imported in unmatched_imported:
            imported_by_signature.setdefault(_mesh_signature(imported.data), []).append(imported)

        recovered = []
        still_missing = []
        for target in unmatched_targets:
            signature = _mesh_signature(target.data)
            matches = imported_by_signature.get(signature, [])
            if len(matches) == 1:
                imported_by_target[target.name] = matches.pop(0)
                recovered.append(target.name)
            else:
                still_missing.append(target.name)

        if recovered:
            _log(f"Recovered batch matches by topology signature: {recovered!r}")

        if still_missing and len(still_missing) == len(unmatched_imported):
            _log("Falling back to import order for remaining batch objects")
            for target, imported in zip(
                [target_by_name[name] for name in still_missing],
                unmatched_imported,
            ):
                imported_by_target[target.name] = imported
            still_missing = [
                name for name in still_missing if name not in imported_by_target
            ]

        if still_missing:
            raise RuntimeError(
                "Could not match imported objects back to: "
                + ", ".join(sorted(still_missing))
            )

    for target_name, target_obj in target_by_name.items():
        _copy_uvs(imported_by_target[target_name], target_obj)


def _cleanup_imported(imported_objects):
    _log(f"Cleaning up {len(imported_objects)} imported temporary object(s)")
    imported_meshes = {obj.data for obj in imported_objects if obj.type == "MESH"}
    for obj in imported_objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    for mesh in imported_meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def _copy_uvs_to_similar_objects(source_obj, target_objects):
    source_signature = _mesh_signature(source_obj.data)
    copied_names = []

    for target_obj in target_objects:
        if target_obj.name == source_obj.name or target_obj.type != "MESH":
            continue
        if _mesh_signature(target_obj.data) != source_signature:
            continue
        _copy_uvs(source_obj, target_obj)
        copied_names.append(target_obj.name)

    return copied_names


class RIZOMUVBRIDGE_PG_settings(PropertyGroup):
    install_path: StringProperty(
        name="RizomUV Path",
        description="Path to the RizomUV installation folder",
        subtype="DIR_PATH",
        default=_find_rizom_install_path(),
    )
    exchange_path: StringProperty(
        name="Exchange File",
        description="Temporary OBJ used by the bridge",
        default="",
        subtype="FILE_PATH",
    )
    object_name: StringProperty(
        name="Object Name",
        description="Object currently linked to RizomUV",
        default="",
    )
    batch_objects_json: StringProperty(
        name="Batch Objects",
        description="JSON list of objects linked in the current batch session",
        default="[]",
    )
    log_path: StringProperty(
        name="Log File",
        description="Path to the addon log file",
        default=str(_LOG_PATH),
        subtype="FILE_PATH",
    )
    helper_log_path: StringProperty(
        name="Helper Log File",
        description="Path to the helper log file",
        default=str(_HELPER_LOG_PATH),
        subtype="FILE_PATH",
    )


class RIZOMUVBRIDGE_OT_send(Operator):
    bl_idname = "rizomuv_bridge.send"
    bl_label = "Send to RizomUV"
    bl_description = "Export the active mesh and load it into RizomUV"

    def execute(self, context):
        settings = _get_settings(context)

        try:
            _log("Send to RizomUV started")
            obj = _ensure_object_mode(context)
            exchange_path = _create_exchange_path(obj.name)

            _export_objects(context, [obj], exchange_path)
            _run_helper(
                context,
                "send",
                exchange_path=exchange_path,
                object_name=obj.name,
            )

            settings.exchange_path = exchange_path
            settings.object_name = obj.name
            settings.batch_objects_json = json.dumps([obj.name])
            _log(
                f"Send to RizomUV completed. object={obj.name!r} exchange_path={exchange_path}"
            )
            self.report({"INFO"}, f"Sent '{obj.name}' to RizomUV.")
            return {"FINISHED"}
        except Exception as exc:
            _log_exception(context, exc, where="Send to RizomUV")
            self.report({"ERROR"}, _error_message(exc))
            return {"CANCELLED"}


class RIZOMUVBRIDGE_OT_fetch(Operator):
    bl_idname = "rizomuv_bridge.fetch"
    bl_label = "Get UVs from RizomUV"
    bl_description = "Save the current RizomUV mesh and copy its UVs back to the source object"

    def execute(self, context):
        settings = _get_settings(context)

        try:
            _log(
                f"Get UVs from RizomUV started. object={settings.object_name!r} "
                f"exchange_path={settings.exchange_path!r}"
            )
            batch_names = json.loads(settings.batch_objects_json or "[]")
            if len(batch_names) > 1:
                raise RuntimeError(
                    "Current session contains multiple objects. Use 'Fetch Batch UVs'."
                )
            if not settings.exchange_path:
                raise RuntimeError("Nothing to fetch yet. Send a mesh to RizomUV first.")
            if not Path(settings.exchange_path).exists():
                raise RuntimeError("Temporary exchange file is missing. Send the mesh again.")
            if settings.object_name not in bpy.data.objects:
                raise RuntimeError("Original Blender object no longer exists.")

            target_obj = bpy.data.objects[settings.object_name]
            if target_obj.type != "MESH":
                raise RuntimeError("Original linked object is not a mesh anymore.")

            _run_helper(
                context,
                "fetch",
                exchange_path=settings.exchange_path,
                object_name=settings.object_name,
            )

            imported_meshes, imported_objects = _import_obj_objects(settings.exchange_path)
            try:
                _copy_uvs(imported_meshes[0], target_obj)
            finally:
                _cleanup_imported(imported_objects)

            _log(f"Get UVs from RizomUV completed for {target_obj.name!r}")
            self.report({"INFO"}, f"UVs updated on '{target_obj.name}'.")
            return {"FINISHED"}
        except Exception as exc:
            _log_exception(context, exc, where="Get UVs from RizomUV")
            self.report({"ERROR"}, _error_message(exc))
            return {"CANCELLED"}


class RIZOMUVBRIDGE_OT_send_selected(Operator):
    bl_idname = "rizomuv_bridge.send_selected"
    bl_label = "Send Selected Batch"
    bl_description = "Export selected mesh objects together and load them into RizomUV"

    def execute(self, context):
        settings = _get_settings(context)

        try:
            _log("Send Selected Batch started")
            _ensure_object_mode(context)
            objects = _selected_mesh_objects(context)
            exchange_path = _create_exchange_path("batch")

            _export_objects(context, objects, exchange_path)
            _run_helper(
                context,
                "send",
                exchange_path=exchange_path,
                object_name=objects[0].name,
            )

            object_names = [obj.name for obj in objects]
            settings.exchange_path = exchange_path
            settings.object_name = objects[0].name
            settings.batch_objects_json = json.dumps(object_names)
            _log(
                "Send Selected Batch completed. "
                f"objects={object_names!r} exchange_path={exchange_path}"
            )
            self.report({"INFO"}, f"Sent {len(object_names)} objects to RizomUV.")
            return {"FINISHED"}
        except Exception as exc:
            _log_exception(context, exc, where="Send Selected Batch")
            self.report({"ERROR"}, _error_message(exc))
            return {"CANCELLED"}


class RIZOMUVBRIDGE_OT_fetch_batch(Operator):
    bl_idname = "rizomuv_bridge.fetch_batch"
    bl_label = "Fetch Batch UVs"
    bl_description = "Save the current RizomUV batch and copy UVs back to all linked objects"

    def execute(self, context):
        settings = _get_settings(context)

        try:
            _log(
                f"Fetch Batch UVs started. exchange_path={settings.exchange_path!r} "
                f"batch={settings.batch_objects_json}"
            )
            if not settings.exchange_path:
                raise RuntimeError("Nothing to fetch yet. Send selected meshes first.")
            if not Path(settings.exchange_path).exists():
                raise RuntimeError("Temporary exchange file is missing. Send the batch again.")

            object_names = json.loads(settings.batch_objects_json or "[]")
            if not object_names:
                raise RuntimeError("No batch session stored. Use 'Send Selected Batch' first.")

            target_objects = []
            missing_names = []
            for name in object_names:
                obj = bpy.data.objects.get(name)
                if obj is None or obj.type != "MESH":
                    missing_names.append(name)
                else:
                    target_objects.append(obj)

            if missing_names:
                raise RuntimeError(
                    "Original Blender objects no longer exist: " + ", ".join(missing_names)
                )

            _run_helper(
                context,
                "fetch",
                exchange_path=settings.exchange_path,
                object_name=settings.object_name,
            )

            imported_meshes, imported_objects = _import_obj_objects(settings.exchange_path)
            try:
                _copy_uvs_batch(imported_meshes, target_objects)
            finally:
                _cleanup_imported(imported_objects)

            _log(f"Fetch Batch UVs completed for {len(target_objects)} object(s)")
            self.report({"INFO"}, f"Updated UVs on {len(target_objects)} objects.")
            return {"FINISHED"}
        except Exception as exc:
            _log_exception(context, exc, where="Fetch Batch UVs")
            self.report({"ERROR"}, _error_message(exc))
            return {"CANCELLED"}


class RIZOMUVBRIDGE_OT_copy_uv_to_similar(Operator):
    bl_idname = "rizomuv_bridge.copy_uv_to_similar"
    bl_label = "Copy UV to Similar"
    bl_description = "Copy UVs from the active object to selected mesh objects with matching topology"

    def execute(self, context):
        try:
            _log("Copy UV to Similar started")
            source_obj = _ensure_object_mode(context)
            target_objects = _selected_mesh_objects(context)
            copied_names = _copy_uvs_to_similar_objects(source_obj, target_objects)

            if not copied_names:
                raise RuntimeError(
                    "No compatible selected mesh objects found. Matching topology is required."
                )

            _log(f"Copy UV to Similar completed. copied={copied_names!r}")
            self.report({"INFO"}, f"Copied UVs to {len(copied_names)} similar objects.")
            return {"FINISHED"}
        except Exception as exc:
            _log_exception(context, exc, where="Copy UV to Similar")
            self.report({"ERROR"}, _error_message(exc))
            return {"CANCELLED"}


class RIZOMUVBRIDGE_OT_close(Operator):
    bl_idname = "rizomuv_bridge.close"
    bl_label = "Close RizomUV Session"
    bl_description = "Close the active RizomUV session managed by this addon"

    def execute(self, context):
        try:
            _log("Close RizomUV Session started")
            _run_helper(context, "close")
            _log("RizomUV session closed")
            self.report({"INFO"}, "RizomUV session closed.")
            return {"FINISHED"}
        except Exception as exc:
            _log_exception(context, exc, where="Close RizomUV Session")
            self.report({"ERROR"}, _error_message(exc))
            return {"CANCELLED"}


class RIZOMUVBRIDGE_PT_panel(Panel):
    bl_label = "RizomUV Bridge"
    bl_idname = "RIZOMUVBRIDGE_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "RizomUV"

    def draw(self, context):
        layout = self.layout
        settings = _get_settings(context)

        layout.prop(settings, "install_path")
        layout.label(text=f"Log: {Path(settings.log_path).name}")
        layout.label(text=f"Helper Log: {Path(settings.helper_log_path).name}")

        layout.label(text="Single Object")
        col = layout.column(align=True)
        col.operator("rizomuv_bridge.send", icon="EXPORT")
        col.operator("rizomuv_bridge.fetch", icon="IMPORT")

        layout.label(text="Batch / Reuse")
        col = layout.column(align=True)
        col.operator("rizomuv_bridge.send_selected", icon="MOD_ARRAY")
        col.operator("rizomuv_bridge.fetch_batch", icon="UV_SYNC_SELECT")
        col.operator("rizomuv_bridge.copy_uv_to_similar", icon="DUPLICATE")

        layout.label(text="Session")
        col = layout.column(align=True)
        col.operator("rizomuv_bridge.close", icon="PANEL_CLOSE")

        if settings.object_name:
            layout.label(text=f"Linked object: {settings.object_name}")
        if settings.exchange_path:
            layout.label(text=Path(settings.exchange_path).name)
        try:
            batch_count = len(json.loads(settings.batch_objects_json or "[]"))
        except Exception:
            batch_count = 0
        if batch_count:
            layout.label(text=f"Batch objects: {batch_count}")


classes = (
    RIZOMUVBRIDGE_PG_settings,
    RIZOMUVBRIDGE_OT_send,
    RIZOMUVBRIDGE_OT_fetch,
    RIZOMUVBRIDGE_OT_send_selected,
    RIZOMUVBRIDGE_OT_fetch_batch,
    RIZOMUVBRIDGE_OT_copy_uv_to_similar,
    RIZOMUVBRIDGE_OT_close,
    RIZOMUVBRIDGE_PT_panel,
)


def register():
    _log("Registering addon")
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.rizomuv_bridge = PointerProperty(type=RIZOMUVBRIDGE_PG_settings)


def unregister():
    _log("Unregistering addon")
    if hasattr(bpy.types.Scene, "rizomuv_bridge"):
        del bpy.types.Scene.rizomuv_bridge
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
