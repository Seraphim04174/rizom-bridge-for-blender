# Rizom Bridge for Blender

Unofficial Blender bridge for RizomUV round-trip workflows.

Send meshes from Blender to RizomUV, work there, and bring the UVs back into Blender without manually exporting and reimporting files every time.

This addon is built for practical round-trip work, especially for hard-surface scenes with many separate parts such as robots, weapons, mechanical kits, and repeated pieces like pistons or bolts.

## Why This Project Exists

Blender and RizomUV are a powerful combination, but the handoff between them can be slow and repetitive.

This project focuses on making that handoff simple:

- send the active object to RizomUV
- send multiple selected objects as a batch
- fetch UVs back into Blender
- reuse UVs across repeated meshes with matching topology

## Key Idea

The addon does **not** import `RizomUVLink` directly inside Blender.

Instead, Blender launches an external helper script through RizomUV's bundled `python.exe`. That helper talks to `RizomUVLink`, which makes this project much more compatible with different Blender versions whose embedded Python versions may not match RizomUV's binary Python modules.

## Features

- `Send to RizomUV`
  Export the active mesh to a temporary `OBJ` and load it into RizomUV.

- `Get UVs from RizomUV`
  Save the current RizomUV result and copy the UVs back onto the original Blender object.

- `Send Selected Batch`
  Export multiple selected mesh objects into one shared `OBJ` and open them together in RizomUV.

- `Fetch Batch UVs`
  Save the current batch session and copy UVs back to all linked Blender objects.

- `Copy UV to Similar`
  Copy UVs from the active object to other selected mesh objects with matching topology.
  This is especially useful for repeated mechanical parts.

- External helper architecture
  Keeps Blender-side compatibility much better than a direct binary bridge inside Blender.

- Debug logs
  Writes Blender-side and helper-side logs for easier troubleshooting.

## Current Workflow

### Single object

1. Select a mesh object in `Object Mode`.
2. Open `View3D > Sidebar > RizomUV`.
3. Set the RizomUV install path if it was not detected automatically.
4. Click `Send to RizomUV`.
5. Edit the UVs in RizomUV.
6. Return to Blender and click `Get UVs from RizomUV`.

### Multiple objects

1. Select several mesh objects.
2. Click `Send Selected Batch`.
3. Edit the batch in RizomUV.
4. Return to Blender and click `Fetch Batch UVs`.

### Repeated parts

1. Unwrap one source mesh.
2. Select that source mesh and other repeated meshes with the same topology.
3. Make the source mesh the active object.
4. Click `Copy UV to Similar`.

## Compatibility

This project was designed specifically to avoid Python-version conflicts between Blender and RizomUV.

- Blender side: intended to be adaptable across multiple Blender versions
- RizomUV side: uses the Python runtime bundled with RizomUV
- Current target path: `C:\Program Files\Rizom Lab\RizomUV 2024.1`

That architecture is the main reason this addon can stay practical even when Blender updates its embedded Python.

## Installation

### One-click install for users

The easiest way to install the addon is through the project's GitHub `Releases` page:

1. Open the latest release.
2. Download the packaged addon zip, for example `rizom_bridge_for_blender-0.1.0.zip`.
3. In Blender open `Edit > Preferences > Add-ons > Install...`
4. Select the downloaded zip.
5. Enable `Rizom Bridge`.

This packaged zip is built specifically for Blender addon installation.

### Standard install

1. Download or clone this repository.
2. Zip the addon folder, or keep it as a folder named `rizomuv_bridge_addon`.
3. In Blender open `Edit > Preferences > Add-ons > Install...`
4. Choose the zip or addon folder.
5. Enable `RizomUV Bridge`.

### Development install

For live iteration during development, link the project folder into Blender's user addons directory and use `Reload Scripts` inside Blender after edits.

### Building the install zip manually

If you want to build the release archive yourself:

```powershell
python tools/package_addon.py
```

The generated installable addon zip will appear in the `dist/` folder.

## What Gets Transferred

This addon currently transfers **UV results back onto existing Blender objects**.

It does **not** replace the whole Blender object, so it is much safer for production scenes:

- object transforms stay intact
- materials stay intact
- modifiers stay intact
- object references stay intact

## Known Limitations

- The current bridge uses temporary `OBJ` files for transfer.
- For the cleanest round-trip, avoid changing topology in RizomUV.
- Batch fetch currently relies on object matching after `OBJ` round-trip. Matching has fallbacks, but extreme renaming cases may still need improvement.
- This version is focused on UV transfer, not full mesh replacement.

## Logs

The addon writes logs to help diagnose issues:

- Blender-side log: `rizomuv_bridge.log`
- Helper-side log: `rizomuv_helper.log`

If something goes wrong, these two files are the first place to check.

## Project Direction

This project is a strong base for a more complete public bridge.

Possible future improvements:

- stronger batch matching strategies
- one-click session recovery
- better UX around active batch state
- direct support for broader Blender version coverage
- more robust handling for repeated and instanced parts

## Contributing

Issues, testing feedback, edge cases, and workflow suggestions are all welcome.

If you use Blender and RizomUV together in production, especially for hard-surface or modular asset work, your feedback can help shape the next version of the bridge.
