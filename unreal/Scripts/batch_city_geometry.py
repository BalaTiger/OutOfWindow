"""Consolidate repeated, plain City geometry into serialized editor ISMs.

Call batch_city_geometry() after City material/lookdev changes and before saving
the map. Existing ISMs, translucent geometry and all semantic actors stay intact.
UE 5.7 SubobjectDataSubsystem adds registered InstanceComponents to the actor's
serialized component list; constructing an unattached Python component does not.
"""
from collections import Counter, defaultdict
import unreal as u


# Group and copy the effective rendering/collision state, not just the mesh.
COMPONENT_PROPERTIES = (
    'mobility', 'component_tags', 'visible', 'hidden_in_game', 'cast_shadow',
    'cast_dynamic_shadow', 'cast_static_shadow', 'cast_contact_shadow',
    'cast_far_shadow', 'cast_inset_shadow', 'cast_hidden_shadow',
    'cast_shadow_as_two_sided', 'cast_cinematic_shadow',
    'cast_volumetric_translucent_shadow', 'affect_dynamic_indirect_lighting',
    'affect_indirect_lighting_while_hidden', 'affect_distance_field_lighting',
    'visible_in_ray_tracing', 'visible_in_reflection_captures',
    'visible_in_real_time_sky_captures', 'owner_no_see', 'only_owner_see', 'render_in_main_pass',
    'render_in_depth_pass', 'receives_decals', 'use_as_occluder',
    'lighting_channels', 'bounds_scale', 'render_custom_depth',
    'custom_depth_stencil_value', 'custom_depth_stencil_write_mask',
    'translucency_sort_priority', 'reverse_culling', 'disallow_nanite',
    'evaluate_world_position_offset', 'evaluate_world_position_offset_in_ray_tracing',
    'forced_lod_model', 'override_min_lod', 'min_lod', 'never_distance_cull',
    'allow_cull_distance_volume', 'body_instance', 'custom_primitive_data',
)


def _value_key(value):
    if hasattr(value, 'export_text'):
        return value.export_text()
    if isinstance(value, u.Array):
        return tuple(str(item) for item in value)
    return str(value)


def _new_ism(actor, subsystem):
    handles = subsystem.k2_gather_subobject_data_for_instance(actor)
    library = u.SubobjectDataBlueprintFunctionLibrary
    parent = next(handle for handle in handles
                  if library.is_actor(library.get_data(handle)))
    handle, reason = subsystem.add_new_subobject(u.AddNewSubobjectParams(
        parent_handle=parent, new_class=u.InstancedStaticMeshComponent))
    if not library.is_handle_valid(handle):
        raise RuntimeError('Cannot create serialized City ISM: ' + str(reason))
    component = library.get_associated_object(library.get_data(handle))
    if not isinstance(component, u.InstancedStaticMeshComponent):
        raise RuntimeError('Subobject subsystem returned no City ISM')
    return component


def batch_city_geometry():
    """Batch current City map; validate every world transform before removal.

    The caller owns map saving. On a creation/validation failure, new actors are
    removed and originals remain. Reload the map if a removal itself fails.
    """
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    mesh_editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    subobjects = u.get_engine_subsystem(u.SubobjectDataSubsystem)
    world = u.get_editor_subsystem(u.UnrealEditorSubsystem).get_editor_world()
    if world.get_name() != 'City':
        raise RuntimeError('City batching requires the City map')
    groups, skipped = defaultdict(list), Counter()
    all_actors = list(actors.get_all_level_actors())
    for actor in all_actors:
        # Keep custom actors, animation semantics, existing ISMs and their data.
        if actor.get_class() != u.StaticMeshActor.static_class():
            continue
        tags = tuple(sorted(str(tag) for tag in actor.tags))
        component = actor.static_mesh_component
        if tags != ('OOWGeometry',) or actor.get_attached_actors() or actor.get_owner():
            skipped['semantic_or_parent'] += 1
            continue
        if (isinstance(component, u.InstancedStaticMeshComponent)
                or component.get_editor_property('mobility') != u.ComponentMobility.STATIC
                or actor.get_editor_property('hidden')):
            skipped['instanced_moving_or_hidden'] += 1
            continue
        mesh = component.static_mesh
        if not mesh or mesh_editor.has_instance_vertex_colors(component):
            skipped['missing_mesh_or_vertex_paint'] += 1
            continue
        materials = [component.get_material(index)
                     for index in range(component.get_num_materials())]
        # Translucent windows need their existing per-component sorting.
        if any(material and material.get_blend_mode() not in
               (u.BlendMode.BLEND_OPAQUE, u.BlendMode.BLEND_MASKED)
               for material in materials):
            skipped['translucent'] += 1
            continue
        transform = component.get_world_transform()
        scale = transform.scale3d
        if (scale.x * scale.y * scale.z <= 0
                or component.get_editor_property('min_draw_distance') != 0
                or component.get_editor_property('ld_max_draw_distance') != 0):
            skipped['mirrored_or_distance_culled'] += 1
            continue
        state = {name: component.get_editor_property(name)
                 for name in COMPONENT_PROPERTIES}
        key = (mesh.get_path_name(),
               tuple(material.get_path_name() if material else None for material in materials),
               tags, actor.get_actor_enable_collision(),
               tuple(_value_key(state[name]) for name in COMPONENT_PROPERTIES))
        groups[key].append((actor, component, transform, materials, state))

    batches = [group for group in groups.values() if len(group) > 1]
    created, masters = [], set()
    try:
        for index, group in enumerate(batches):
            source_actor, source, _, materials, state = group[0]
            actor = actors.spawn_actor_from_class(u.Actor, u.Vector())
            if not actor:
                raise RuntimeError('Could not spawn City batch actor')
            created.append(actor)
            actor.set_actor_label('OOWCityStaticBatch_' + str(index))
            actor.tags = list(source_actor.tags) + ['OOWCityStaticBatch']
            actor.set_actor_enable_collision(source_actor.get_actor_enable_collision())
            component = _new_ism(actor, subobjects)
            component.set_static_mesh(source.static_mesh)
            for name, value in state.items():
                component.set_editor_property(name, value)
            for slot, material in enumerate(materials):
                component.set_material(slot, material)
                if material:
                    masters.add(material.get_base_material())
            transforms = [item[2] for item in group]
            component.add_instances(transforms, False, True, False)
            if component.get_instance_count() != len(group):
                raise RuntimeError('City instance count changed during batching')
            for instance, transform in enumerate(transforms):
                actual = component.get_instance_transform(instance, True)
                if not actual or not transform.is_near_equal(actual, .01, .0001, .0001):
                    raise RuntimeError('City instance world transform was not preserved')

        # Explicit usage avoids a packaged-game fallback to the default material.
        for material in masters:
            if not material.get_editor_property('used_with_instanced_static_meshes'):
                material.set_editor_property('used_with_instanced_static_meshes', True)
                u.MaterialEditingLibrary.recompile_material(material)
                if not u.EditorAssetLibrary.save_loaded_asset(material):
                    raise RuntimeError('Could not save ISM material usage: ' + material.get_path_name())
    except Exception:
        for actor in created:
            actors.destroy_actor(actor)
        raise

    removed = 0
    for group in batches:
        for actor, _, _, _, _ in group:
            if not actors.destroy_actor(actor):
                raise RuntimeError('City source removal failed; reload the unsaved map')
            removed += 1
    report = {
        'actorsBefore': len(all_actors), 'actorsAfter': len(actors.get_all_level_actors()),
        'sourceActorsBatched': removed, 'instanceComponentsCreated': len(created),
        'instancesCreated': removed, 'actorsRemovedNet': removed - len(created),
        'allWorldTransformsVerified': True, 'skipped': dict(skipped),
    }
    u.log('OOW_CITY_BATCH ' + str(report))
    return report


if __name__ == '__main__':
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    if not levels.load_level('/Game/Maps/City'):
        raise RuntimeError('Missing City map')
    batch_city_geometry()
    if not levels.save_current_level():
        raise RuntimeError('Could not save batched City map')
