"""Upgrade existing outdoor awning slots without requiring the GLB export cache.

Run with UnrealEditor-Cmd -run=pythonscript -script=.../repair_awning_hem.py.
Uses the same v17 builder as full imports; hidden indoor curtains are excluded.
"""
import json
from pathlib import Path
import sys
import unreal as u

root = Path(u.Paths.project_dir()).parent
sys.path.insert(0, str(root / 'Scripts'))
import build_surface_materials as builder
from window_lookdev import add_awning_transmission

builder.u = u
builder.mel = u.MaterialEditingLibrary
builder.masters, builder.instances, builder.probes = {}, {}, {}
builder.interior_textures = None
builder.add_awning_transmission = add_awning_transmission
levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
assert levels.load_level('/Game/Maps/Alley')
changed = []
for actor in u.get_editor_subsystem(u.EditorActorSubsystem).get_all_level_actors():
    if not isinstance(actor, u.StaticMeshActor):
        continue
    comp = actor.static_mesh_component
    if not comp.is_visible() or actor.get_actor_label() in builder.LEGACY_CURTAIN_ACTORS:
        continue
    for slot in range(comp.get_num_materials()):
        current = comp.get_material(slot)
        master = current
        while isinstance(master, u.MaterialInstanceConstant):
            master = master.get_editor_property('parent')
        if not master or not master.get_path_name().startswith(builder.DEST + '/Masters/M_fabric_awning_'):
            continue
        original = builder.original_material(current)
        replacement = builder.adapt(original, ('fabric', 'awning', ''), {})
        actor.modify()
        comp.modify()
        comp.set_material(slot, replacement)
        builder.configure_wind_bounds(comp)
        changed.append({'actor': actor.get_actor_label(), 'slot': slot,
                        'material': replacement.get_path_name()})
assert changed, 'No outdoor awning slots found'
assert levels.save_current_level(), 'Cannot save Alley'
report = {'recipe': 'v17', 'frequencyHz': 2., 'movingHeightFraction': .22,
          'maxDisplacementCm': 6., 'rainImpulses': False, 'slots': changed}
(root / 'Migration' / 'awning-hem-repair.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
u.log('OOW_AWNING_HEM_REPAIRED ' + str(len(changed)))
