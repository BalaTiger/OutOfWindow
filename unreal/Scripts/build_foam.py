"""Repair exported shore foam/ocean extent and preserve native pine needle area.

Run AFTER build_surface_materials.py, with no concurrent editor/asset writer.
Only Coast's verified foam/ocean actors and Forest/Village twig mesh settings
are changed. Original land, source assets and engine/plugin assets stay intact.
Plain Python --self-test checks the pinned shoreline expansion calculation.
"""
import importlib.util
import itertools
import json
from pathlib import Path
import struct
import sys

FOAM_NODE = 'OOW_00002_Mesh'
OCEAN_NODE = 'OOW_00001_Water'
FOAM_PATH = '/Game/Materials/OOW/M_ShoreFoam_v1'


def expanded_bounds(origin, extent, pivot, minimum=200000.):
    """Keep the near edge and source centre X; extend under land to hide side edges."""
    if min(extent[0], extent[1]) <= 0:
        raise ValueError('Ocean must have a nonzero horizontal footprint')
    factor = max(1., minimum / (2. * min(extent[0], extent[1])))
    target = (3200.,
              origin[1] + extent[1] - extent[1] * factor, origin[2])
    new_pivot = tuple(target[i] - (origin[i] - pivot[i]) * factor for i in range(3))
    return factor, new_pivot


def make_foam(u, surface):
    existing = u.load_asset(FOAM_PATH)
    if existing:
        return existing
    material = u.AssetToolsHelpers.get_asset_tools().create_asset(
        FOAM_PATH.rsplit('/', 1)[1], FOAM_PATH.rsplit('/', 1)[0], u.Material, u.MaterialFactoryNew())
    if not material:
        raise RuntimeError('Cannot create ' + FOAM_PATH)
    material.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property('two_sided', True)
    material.set_editor_property('translucency_lighting_mode', u.TranslucencyLightingMode.TLM_SURFACE)
    g, prop = surface.Graph(material), u.MaterialProperty
    uv, time = g.node(u.MaterialExpressionTextureCoordinate), g.node(u.MaterialExpressionTime)
    # Original makeShoreFoam GLSL expressed in native lit translucency, with
    # endpoint fading so this finite ribbon has no visible rectangular border.
    alpha = g.custom(
        'float2 a=UV*11., b=UV*19.; '
        'float n1=sin(a.x*17.+sin(a.y*9.))*sin(a.y*31.-a.x*5.); '
        'float n2=sin(b.x*17.+sin(b.y*9.))*sin(b.y*31.-b.x*5.); '
        'float edge=1.-smoothstep(.1,.52,abs(UV.x-.5)); '
        'float tide=.5+.5*sin(UV.y*22.-T*.9+n1*2.5); '
        'float broken=smoothstep(.68,.96,tide+n2*.22); '
        'return edge*broken*.20*smoothstep(0.,.018,UV.y)*smoothstep(0.,.018,1.-UV.y);',
        {'UV': uv, 'T': time}, description='OOW original shore foam alpha animation')
    depth = g.node(u.MaterialExpressionDepthFade, fade_distance_default=20.)
    g.connect(alpha, depth, '')
    g.output(depth, prop.MP_OPACITY)
    g.output(g.vector((.64, .82, .80)), prop.MP_BASE_COLOR)
    g.output(g.constant(.78), prop.MP_ROUGHNESS)
    g.output(g.constant(0), prop.MP_METALLIC)
    surface.ensure_mesh_usage(material)
    surface.mel.recompile_material(material)
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWSourceRecipe', 'src/main.js:makeShoreFoam')
    u.EditorAssetLibrary.save_loaded_asset(material)
    return material


def assert_export_identity(root):
    with (root / 'Migration' / 'Exported' / 'coast.glb').open('rb') as f:
        f.seek(12)
        size, chunk = struct.unpack('<II', f.read(8))
        assert chunk == 0x4E4F534A
        document = json.loads(f.read(size))
    nodes = {n.get('name'): n for n in document['nodes']}
    foam = nodes[FOAM_NODE]
    primitive = document['meshes'][foam['mesh']]['primitives'][0]
    bounds = document['accessors'][primitive['attributes']['POSITION']]
    assert bounds['min'] == [-6.5, -80, 0] and bounds['max'] == [6.5, 80, 0]
    assert document['materials'][primitive['material']]['name'] == 'Material_2'
    assert all(abs(a - b) < .0001 for a, b in zip(foam['matrix'][12:15], [-13, -.94, -48]))
    ocean = nodes[OCEAN_NODE]
    primitive = document['meshes'][ocean['mesh']]['primitives'][0]
    assert document['materials'][primitive['material']]['name'] == 'MirrorShader'


def main():
    import unreal as u
    root = Path(u.Paths.project_dir()).parent
    spec = importlib.util.spec_from_file_location('oow_surface_helpers', root / 'Scripts' / 'build_surface_materials.py')
    surface = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(surface)
    surface.u, surface.mel = u, u.MaterialEditingLibrary
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    meshes = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    assert_export_identity(root)
    if not levels.load_level('/Game/Maps/Coast'):
        raise RuntimeError('Cannot load Coast')
    scene_actors = {actor.get_actor_label(): actor for actor in actors.get_all_level_actors()}
    foam, ocean = scene_actors[FOAM_NODE], scene_actors[OCEAN_NODE]
    foam_comp = foam.static_mesh_component
    foam_mat = make_foam(u, surface)
    for index in range(foam_comp.get_num_materials()):
        foam_comp.set_material(index, foam_mat)
    foam_comp.set_editor_property('cast_shadow', False)
    foam_comp.set_editor_property('translucency_sort_priority', 3)
    foam.tags = sorted({str(tag) for tag in foam.tags} | {'OOWFoam'})
    foam_mesh = foam_comp.static_mesh
    settings = foam_mesh.get_editor_property('nanite_settings')
    if settings.enabled:
        settings.enabled = False  # translucent foam cannot use Nanite
        meshes.set_nanite_settings(foam_mesh, settings, True)
        u.EditorAssetLibrary.save_loaded_asset(foam_mesh)

    # Use actual transformed mesh bounds, not component bounds_scale (1.1 for
    # waves), and compensate for a mesh pivot not located at its bounds center.
    comp = ocean.static_mesh_component
    lo, hi = comp.get_local_bounds()
    transform = comp.get_world_transform()
    corners = [u.MathLibrary.transform_location(transform, u.Vector(x, y, z))
               for x, y, z in itertools.product((lo.x, hi.x), (lo.y, hi.y), (lo.z, hi.z))]
    mins = tuple(min(getattr(v, axis) for v in corners) for axis in ('x', 'y', 'z'))
    maxs = tuple(max(getattr(v, axis) for v in corners) for axis in ('x', 'y', 'z'))
    origin = tuple((mins[i] + maxs[i]) * .5 for i in range(3))
    extent = tuple((maxs[i] - mins[i]) * .5 for i in range(3))
    location = ocean.get_actor_location()
    factor, position = expanded_bounds(origin, extent, (location.x, location.y, location.z))
    if factor > 1.000001:
        scale = ocean.get_actor_scale3d()
        ocean.set_actor_scale3d(u.Vector(scale.x * factor, scale.y * factor, scale.z * factor))
    ocean.set_actor_location(u.Vector(*position), False, True)
    levels.save_current_level()
    report = {'foamActor': FOAM_NODE, 'foamMaterial': FOAM_PATH, 'oceanActor': OCEAN_NODE,
              'oceanScaleFactor': factor, 'oceanWidthCm': 2 * extent[0] * factor,
              'oceanDepthCm': 2 * extent[1] * factor, 'centerXCm': 3200.,
              'pinnedNearCm': maxs[1], 'needleMeshes': []}

    # UE 5.7 replaced the legacy PreserveArea boolean with ShapePreservation.
    # Only actual twig geometry receives it; trunk/rock/terrain settings stay put.
    for scene_id in ('forest', 'village'):
        if not levels.load_level('/Game/Maps/' + scene_id.capitalize()):
            raise RuntimeError('Cannot load ' + scene_id)
        metadata = json.loads((root / 'Migration' / 'Exported' / (scene_id + '.json')).read_text(encoding='utf-8'))
        twig_labels = {node['name'] for node in metadata['nodes'] if 'pine_sapling_small_twig' in node.get('materials', [])}
        unique = set()
        for actor in actors.get_all_level_actors():
            if isinstance(actor, u.StaticMeshActor) and actor.get_actor_label() in twig_labels:
                unique.add(actor.static_mesh_component.static_mesh)
        for mesh in unique:
            settings = mesh.get_editor_property('nanite_settings')
            target = u.NaniteShapePreservation.PRESERVE_AREA
            if settings.enabled and settings.get_editor_property('shape_preservation') != target:
                settings.set_editor_property('shape_preservation', target)
                meshes.set_nanite_settings(mesh, settings, True)
                u.EditorAssetLibrary.save_loaded_asset(mesh)
            report['needleMeshes'].append(mesh.get_path_name())
    (root / 'Migration' / 'foam-repair.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_FOAM_REPAIR_COMPLETE ' + json.dumps(report))


def self_test():
    origin, extent = (3200., -4800., -105.), (8500., 9000., 0.)
    factor, pivot = expanded_bounds(origin, extent, origin)
    assert min(2 * extent[0] * factor, 2 * extent[1] * factor) >= 199999.99
    assert abs(pivot[0] - 3200.) < .0001
    assert abs(pivot[1] + extent[1] * factor - (origin[1] + extent[1])) < .0001
    assert pivot[2] == -105.
    assert expanded_bounds(pivot, tuple(v * factor for v in extent), pivot)[0] == 1.
    # Offset pivots must not shift the shoreline when scaling imported geometry.
    _, offset = expanded_bounds(origin, extent, (0., 0., -105.))
    assert abs(offset[0] + origin[0] * factor - pivot[0]) < .0001
    assert_export_identity(Path(__file__).resolve().parent.parent)
    print('Foam export identity, pinned 2km ocean expansion and rerun idempotency passed')


if __name__ == '__main__':
    self_test() if '--self-test' in sys.argv else main()
