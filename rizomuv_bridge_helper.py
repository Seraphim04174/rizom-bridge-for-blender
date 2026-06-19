import json
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def _log(log_path, message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}"
    try:
        with Path(log_path).open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _emit(payload):
    sys.stdout.write(json.dumps(payload))


def _load_request():
    if len(sys.argv) < 2:
        raise RuntimeError("Missing helper request payload.")
    return json.loads(sys.argv[1])


def _load_state(state_path):
    path = Path(state_path)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(state_path, state):
    Path(state_path).write_text(json.dumps(state, indent=2), encoding="utf-8")


def _clear_state(state_path):
    path = Path(state_path)
    if path.exists():
        path.unlink()


def _import_link(install_path):
    if os.name == "nt":
        os.add_dll_directory(install_path)
        os.add_dll_directory(str(Path(install_path) / "RizomUVLink" / "win"))

    link_path = Path(install_path) / "RizomUVLink"
    sys.path.append(str(link_path))
    from RizomUVLink import CRizomUVLink  # type: ignore

    return CRizomUVLink


def _connect_or_run(request, state, log_path, require_existing):
    CRizomUVLink = _import_link(request["install_path"])
    link = CRizomUVLink()
    port = state.get("port")

    if port is not None:
        try:
            _log(log_path, f"Trying to connect to existing RizomUV session on port {port}")
            link.Connect(port)
            link.RizomUVVersion()
            _log(log_path, "Connected to existing RizomUV session")
            return link, port
        except Exception:
            _log(log_path, "Existing RizomUV session not reachable")

    if require_existing:
        raise RuntimeError("No active RizomUV session. Use 'Send to RizomUV' first.")

    exe_path = str(Path(request["install_path"]) / "rizomuv.exe")
    _log(log_path, f"Launching RizomUV from {exe_path}")
    port = link.RunRizomUV(exePath=exe_path)
    _log(log_path, f"RizomUV launched on port {port}")
    return link, port


def _command_send(request, state, log_path):
    link, port = _connect_or_run(request, state, log_path, require_existing=False)
    exchange_path = request["exchange_path"]
    _log(log_path, f"Loading mesh into RizomUV from {exchange_path}")
    link.Load(
        {
            "File.Path": exchange_path,
            "File.XYZUVW": True,
            "File.UVWProps": True,
            "__Focus": True,
        }
    )
    state["port"] = port
    state["object_name"] = request.get("object_name", "")
    state["exchange_path"] = exchange_path
    _log(log_path, "Send command completed")
    return {"port": port}


def _command_fetch(request, state, log_path):
    link, port = _connect_or_run(request, state, log_path, require_existing=True)
    exchange_path = request["exchange_path"]
    _log(log_path, f"Saving RizomUV mesh to {exchange_path}")
    link.Save({"File.Path": exchange_path})
    state["port"] = port
    _log(log_path, "Fetch command completed")
    return {"port": port}


def _command_close(request, state, log_path):
    link, port = _connect_or_run(request, state, log_path, require_existing=True)
    _log(log_path, f"Closing RizomUV session on port {port}")
    link.Quit({})
    _clear_state(request["state_path"])
    _log(log_path, "Close command completed")
    return {"port": port}


def main():
    request = _load_request()
    log_path = request["log_path"]
    _log(log_path, f"Helper started with command={request.get('command')!r}")

    try:
        state = _load_state(request["state_path"])
        command = request["command"]

        if command == "send":
            result = _command_send(request, state, log_path)
            _save_state(request["state_path"], state)
        elif command == "fetch":
            result = _command_fetch(request, state, log_path)
            _save_state(request["state_path"], state)
        elif command == "close":
            result = _command_close(request, state, log_path)
        else:
            raise RuntimeError(f"Unknown helper command: {command}")

        _emit({"ok": True, "result": result})
    except Exception as exc:
        _log(log_path, f"Helper failed: {exc}")
        _log(log_path, traceback.format_exc().rstrip())
        _emit({"ok": False, "error": str(exc)})
        raise


if __name__ == "__main__":
    main()
