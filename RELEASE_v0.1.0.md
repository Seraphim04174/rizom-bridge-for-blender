# Rizom Bridge for Blender v0.1.0

First public release of an unofficial Blender-to-RizomUV bridge focused on practical round-trip work.

## Highlights

- Send the active Blender mesh to RizomUV
- Fetch UVs back onto the original Blender object
- Send multiple selected meshes as a batch
- Fetch batch UVs back into Blender
- Copy UVs from one object to repeated meshes with matching topology
- Uses an external helper through RizomUV's bundled Python for better Blender-version compatibility
- Includes Blender-side and helper-side logs for troubleshooting

## Good fit for

- hard-surface workflows
- robots and mechanical assemblies
- modular kits
- repeated parts like pistons, bolts, and mirrored components

## Notes

- This release focuses on UV round-trip, not full mesh replacement
- Temporary `OBJ` files are currently used for exchange
- Topology changes in RizomUV are not recommended for this version
