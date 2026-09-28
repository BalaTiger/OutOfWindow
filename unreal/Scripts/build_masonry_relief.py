"""Single-actor masonry A/B candidate; no source textures or shared graphs change.

CPU: --self-test / --generate-only. UE commandlet: run this script after Alley
import. OOW_MASONRY_RELIEF_RESTORE=1 restores the prior mesh for an A/B capture.
Joint coordinates are authored from the existing normal map, never albedo.
"""
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_window_interiors import read_glb, read_accessor, sub, cross, dot, unit, length, Union

ACTOR = 'OOW_00762_paris_building_09_10'
MATERIAL = 'MASTER_Brick_Large_Beige_BLENDSHADER'
NAME = 'OOW_MasonryRelief_09_10_v1'
DEST = '/Game/Scenes/Alley/Repairs'
RECIPE = 'masonry-joint-relief-v1'
DEPTH = .008  # metres, with an independent hard cap below
VARIATION = .002
FADE = .08
SHOULDER_UV = 4 / 1024
# Measured sign-crossovers in the original 1024px normal map, not evenly spaced
# courses or albedo luminance. Subpixel variations are retained across all rows.
ROW_CENTERS = tuple(v/1024 for v in (.125,104.938,256.135,360.972,512.086,617.004,768.123,872.980,1024.125))
U_PHASE = .125/1024
MAX_TRIANGLES = 60000


def height(uv):
    """Normal-map joint centers: 4 columns, 8 measured alternating courses."""
    u, v = uv
    tile = math.floor(v-ROW_CENTERS[0])
    y = v-tile
    course = min(7,max(i for i,value in enumerate(ROW_CENTERS[:-1]) if y>=value-1e-12))
    row = tile*8+course
    bottom, top = ROW_CENTERS[course:course+2]
    offset = U_PHASE + (0. if course%2==0 else .125)
    column = math.floor((u-offset)*4)
    x = u - offset - column/4
    edge = min(x, .25-x, y-bottom, top-y)
    face = max(0., min(1., edge/SHOULDER_UV))
    seed = ((column * 73856093) ^ (row * 19349663)) & 0xffffffff
    offset_m = VARIATION * (2 * (seed % 65521) / 65520 - 1)
    return max(-.012, min(.012, -DEPTH*(1-face) + offset_m*face))


def distance_to_segment(point, a, b):
    ab = sub(b, a)
    t = max(0., min(1., dot(sub(point, a), ab)/max(1e-20, dot(ab, ab))))
    return length(sub(point, tuple(a[k]+t*ab[k] for k in range(3))))


def bounds(points):
    return [[min(p[k] for p in points), max(p[k] for p in points)] for k in range(3)]


def split(polygon, axis, cut):
    values = [p[axis]-cut for p in polygon]
    if min(values) >= -1e-10 or max(values) <= 1e-10:
        return [polygon]
    left, right = [], []
    for i, p in enumerate(polygon):
        q, a, b = polygon[(i+1) % len(polygon)], values[i], values[(i+1) % len(polygon)]
        if a <= 1e-10: left.append(p)
        if a >= -1e-10: right.append(p)
        if (a < -1e-10 and b > 1e-10) or (a > 1e-10 and b < -1e-10):
            t = a/(a-b)
            point = tuple(p[k]+t*(q[k]-p[k]) for k in range(5))
            left.append(point); right.append(point)
    return [p for p in (left, right) if len(p) >= 3]


def cuts(axis, low, high):
    centers = []
    if axis == 0:
        centers = [i/8+U_PHASE for i in range(math.floor(low*8)-1, math.ceil(high*8)+2)]
    else:
        centers = [i+offset for i in range(math.floor(low)-1, math.ceil(high)+2)
                   for offset in ROW_CENTERS[:-1]]
    return sorted({v+d for v in centers for d in (-SHOULDER_UV, 0., SHOULDER_UV)
                   if low+1e-10 < v+d < high-1e-10})


def generate(root, write=True):
    doc, blob = read_glb(root/'Migration/Exported/alley.glb')
    node = next(n for n in doc['nodes'] if n.get('name') == ACTOR)
    mesh = doc['meshes'][node['mesh']]
    assert len(mesh['primitives']) == 1
    primitive = mesh['primitives'][0]
    assert doc['materials'][primitive['material']]['name'] == MATERIAL
    assert set(primitive['attributes']) == {'POSITION', 'NORMAL', 'TEXCOORD_0'}
    source = {name: read_accessor(doc, blob, index)[1] for name,index in primitive['attributes'].items()}
    positions, normals, uvs = [source[k] for k in ('POSITION','NORMAL','TEXCOORD_0')]
    indices = [v[0] for v in read_accessor(doc, blob, primitive['indices'])[1]] if 'indices' in primitive else list(range(len(positions)))
    matrix = node['matrix']
    scale = matrix[0]
    assert scale > 0 and all(abs(matrix[i]) < 1e-10 for i in (1,2,4,6,8,9))
    assert max(abs(scale-matrix[i]) for i in (5,10)) < 1e-10
    world = [tuple(p[k]*scale+matrix[12+k] for k in range(3)) for p in positions]
    triangles = [indices[t:t+3] for t in range(0,len(indices),3)]
    keys = [tuple(round(v,5) for v in point) for point in world]
    edges = collections.defaultdict(list)
    for tri, ids in enumerate(triangles):
        p = [world[i] for i in ids]
        face = unit(cross(sub(p[1],p[0]),sub(p[2],p[0])))
        for j in range(3):
            a,b = ids[j], ids[(j+1)%3]
            edges[tuple(sorted((keys[a],keys[b])))].append((tri,a,b,face))
    barriers, continuous, patches = [], [], Union(len(triangles))
    for incidence in edges.values():
        regular = len(incidence) == 2 and dot(incidence[0][3],incidence[1][3]) > .9999
        if regular:
            _,a,b,_ = incidence[0]
            _,c,d,_ = incidence[1]
            c,d = (c,d) if keys[a] == keys[c] else (d,c)
            regular = all(length(sub(uvs[x],uvs[y])) < 1e-5 and dot(unit(normals[x]),unit(normals[y])) > .9999
                          for x,y in ((a,c),(b,d)))
        tri,a,b,_ = incidence[0]
        (continuous if regular else barriers).append((world[a],world[b]))
        if regular: patches.join(incidence[0][0],incidence[1][0])
    camera=json.loads((root/'Migration/Exported/alley.json').read_text())['camera']
    eye=camera['position']
    facing=set()
    for ti,ids in enumerate(triangles):
        pp=[world[i] for i in ids]
        n=unit(cross(sub(pp[1],pp[0]),sub(pp[2],pp[0])))
        center=tuple(sum(p[k] for p in pp)/3 for k in range(3))
        if abs(n[1])<.25 and dot(n,unit(sub(eye,center)))>.15:
            facing.add(patches.root(ti))
    active={i for i in range(len(triangles)) if patches.root(i) in facing}

    def fade(point, segments):
        distance = min((distance_to_segment(point,a,b) for a,b in segments), default=FADE)
        t = max(0., min(1., distance/FADE))
        return t*t*(3-2*t)

    output = {name: [] for name in source}
    out_indices, vertex_cache = [], {}
    displacement_min, displacement_max, max_uv_error = 0.,0.,0.
    source_area, covered_area, max_seam_error, boundary_vertices = 0.,0.,0.,0
    source_edge_samples = collections.defaultdict(list)
    for tri_index, ids in enumerate(triangles):
        pp = [world[i] for i in ids]
        source_area += length(cross(sub(pp[1],pp[0]),sub(pp[2],pp[0])))*.5
        box = bounds(pp)
        nearby = [(a,b) for a,b in barriers if all(max(a[k],b[k]) >= box[k][0]-FADE and
                                                    min(a[k],b[k]) <= box[k][1]+FADE for k in range(3))]
        polygons = [[tuple(uvs[index]) + tuple(float(j==k) for k in range(3)) for j,index in enumerate(ids)]]
        for axis in ((0,1) if tri_index in active else ()):
            low,high = min(uvs[i][axis] for i in ids),max(uvs[i][axis] for i in ids)
            for cut in cuts(axis,low,high):
                polygons = [piece for poly in polygons for piece in split(poly,axis,cut)]
        for poly in polygons:
            base = [tuple(sum(p[2+j]*world[ids[j]][k] for j in range(3)) for k in range(3)) for p in poly]
            new_ids=[]
            for sample, point in zip(poly,base):
                weights = sample[2:]
                uv = tuple(sum(weights[j]*uvs[ids[j]][k] for j in range(3)) for k in range(2))
                max_uv_error=max(max_uv_error,length(sub(uv,sample[:2])))
                normal = unit(tuple(sum(weights[j]*normals[ids[j]][k] for j in range(3)) for k in range(3)))
                amount = height(uv) * fade(point,nearby) if tri_index in active else 0.
                displacement_min,displacement_max=min(displacement_min,amount),max(displacement_max,amount)
                moved = tuple(point[k]+normal[k]*amount for k in range(3))
                local = tuple((moved[k]-matrix[12+k])/scale for k in range(3))
                cache_key = tuple(round(v,6) for v in local+normal+uv)
                if cache_key not in vertex_cache:
                    vertex_cache[cache_key]=len(output['POSITION'])
                    output['POSITION'].append(local); output['NORMAL'].append(normal); output['TEXCOORD_0'].append(uv)
                new_ids.append(vertex_cache[cache_key])
                if nearby and min(distance_to_segment(point,a,b) for a,b in nearby) < 1e-6:
                    boundary_vertices+=1
                    assert abs(amount)<1e-8, 'Outer/hard/UV seam must not move'
                for j,w in enumerate(weights):
                    if abs(w)<1e-8:
                        a,b=ids[(j+1)%3],ids[(j+2)%3]
                        edge_key=tuple(sorted((keys[a],keys[b])))
                        source_edge_samples[(edge_key,tuple(round(v,6) for v in point))].append((tri_index,moved))
            for j in range(1,len(poly)-1):
                area=length(cross(sub(base[j],base[0]),sub(base[j+1],base[0])))*.5
                if area>1e-12:
                    covered_area+=area
                    out_indices.extend((new_ids[0],new_ids[j],new_ids[j+1]))
    for samples in source_edge_samples.values():
        if len({s[0] for s in samples})>1:
            max_seam_error=max(max_seam_error,max(length(sub(p,samples[0][1])) for _,p in samples))
    assert max_seam_error<1e-5, 'Shared source edges opened'
    assert abs(covered_area-source_area)/source_area<1e-7
    assert max_uv_error<1e-7 and min(displacement_min,0)>=-.012 and displacement_max<=.002001
    assert len(out_indices)//3<=MAX_TRIANGLES, 'Candidate exceeds bounded triangle budget: %d' % (len(out_indices)//3)
    assert continuous and boundary_vertices>0

    packed, views, accessors = bytearray(),[],[]
    def add(values, size, fmt, component, target):
        packed.extend(b'\0'*((-len(packed))%4))
        raw=b''.join(struct.pack('<'+fmt*size,*v) for v in values)
        view=len(views); views.append({'buffer':0,'byteOffset':len(packed),'byteLength':len(raw),'target':target})
        packed.extend(raw)
        index=len(accessors); accessors.append({'bufferView':view,'componentType':component,'count':len(values),
                                              'type':{1:'SCALAR',2:'VEC2',3:'VEC3'}[size]})
        if size==3:
            bb=bounds(values);accessors[-1].update(min=[v[0] for v in bb],max=[v[1] for v in bb])
        return index
    attrs={name:add(values,2 if name=='TEXCOORD_0' else 3,'f',5126,34962) for name,values in output.items()}
    index=add([(v,) for v in out_indices],1,'I',5125,34963)
    result={'asset':{'version':'2.0','generator':RECIPE},'scene':0,'scenes':[{'nodes':[0]}],
            'nodes':[{'name':NAME,'mesh':0}], 'meshes':[{'name':NAME,'primitives':[{'attributes':attrs,'indices':index,'material':0}]}],
            'materials':[{'name':MATERIAL,'pbrMetallicRoughness':{'metallicFactor':0,'roughnessFactor':.9}}],
            'accessors':accessors,'bufferViews':views,'buffers':[{'byteLength':len(packed)}]}
    encoded=json.dumps(result,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
    packed.extend(b'\0'*((-len(packed))%4))
    glb=struct.pack('<III',0x46546C67,2,28+len(encoded)+len(packed))+struct.pack('<II',len(encoded),0x4E4F534A)+encoded+struct.pack('<II',len(packed),0x004E4942)+packed
    digest=hashlib.sha256(glb).hexdigest()
    report={'recipe':RECIPE,'actor':ACTOR,'assetName':NAME,'actorCount':1,'sourceMeshIndex':node['mesh'],
            'material':MATERIAL,'appliedToUnreal':False,'beforeTriangles':len(triangles),'triangles':len(out_indices)//3,
            'vertices':len(output['POSITION']),'generatedSha256':digest,'reliefMeters':[displacement_min,displacement_max],
            'mortarDepthMeters':DEPTH,'hardCapMeters':.012,'blockVariationMeters':VARIATION,'boundaryFadeMeters':FADE,
            'activeSourceTriangles':len(active),'untouchedBackAndHorizontalTriangles':len(triangles)-len(active),
            'scope':'Only camera-facing continuous vertical patches on this one actor',
            'jointRowsPixels1024':[v*1024 for v in ROW_CENTERS],'jointShoulderPixels1024':SHOULDER_UV*1024,
            'boundaryOrHardOrUVSeamEdges':len(barriers),'continuousInternalEdgesNotFaded':len(continuous),
            'boundarySamplesUnmoved':boundary_vertices,'maxSharedEdgeGapMeters':max_seam_error,
            'sourceAreaSquareMeters':source_area,'coverageRelativeError':abs(covered_area-source_area)/source_area,
            'maxUVInterpolationError':max_uv_error,'sourceNormals':'Preserved/interpolated, never recomputed',
            'heightSource':'Authored joint coordinates from normal map; no BaseColor sampling',
            'exportLocalBounds':bounds(output['POSITION']), 'originalLocalBounds':bounds(positions),
            'sourceActorMatrix':matrix,'materialPolicy':'Reuse current single-actor UE weather material and Nanite settings'}
    path=root/'Migration/Generated'/f'{NAME}.glb'
    if write:
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(glb)
        (root/'Migration/masonry-relief.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return path,report


def main():
    import unreal as u
    root=Path(u.Paths.project_dir()).parent
    levels=u.get_editor_subsystem(u.LevelEditorSubsystem)
    actors=u.get_editor_subsystem(u.EditorActorSubsystem)
    editor=u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    assert levels.load_level('/Game/Maps/Alley')
    static=[a for a in actors.get_all_level_actors() if isinstance(a,u.StaticMeshActor) and a.static_mesh_component.static_mesh]
    def state(a):
        p,r,s=a.get_actor_location(),a.get_actor_rotation(),a.get_actor_scale3d()
        return [p.x,p.y,p.z,r.pitch,r.yaw,r.roll,s.x,s.y,s.z],a.static_mesh_component.static_mesh.get_path_name()
    before={a.get_actor_label():state(a) for a in static}
    target=next(a for a in static if a.get_actor_label()==ACTOR)
    comp=target.static_mesh_component;old=comp.static_mesh
    assert comp.get_num_materials()==1
    material=comp.get_material(0)
    original=str(u.EditorAssetLibrary.get_metadata_tag(old,'OOWMasonryOriginalMesh')) or old.get_path_name()
    if os.environ.get('OOW_MASONRY_RELIEF_RESTORE')=='1':
        restored=u.load_asset(original);assert isinstance(restored,u.StaticMesh)
        comp.set_static_mesh(restored);comp.set_material(0,material)
        report={'recipe':RECIPE,'actor':ACTOR,'restored':True,'restoredMesh':original}
    else:
        source,report=generate(root)
        reused=str(u.EditorAssetLibrary.get_metadata_tag(old,'OOWMasonryReliefHash'))==report['generatedSha256']
        repaired=old
        nanite=old.get_editor_property('nanite_settings').copy()
        if not reused:
            manager=u.InterchangeManager.get_interchange_manager_scripted()
            options=u.ImportAssetParameters();options.is_automated=True;options.replace_existing=True
            imported=manager.import_asset(DEST,manager.create_source_data(str(source)),options)
            meshes=[a for a in imported or [] if isinstance(a,u.StaticMesh)]
            assert len(meshes)==1 and meshes[0].get_name()==NAME
            repaired=meshes[0]
            build=editor.get_lod_build_settings(old,0).copy()
            build.set_editor_property('recompute_normals',False);build.set_editor_property('recompute_tangents',True)
            build.set_editor_property('use_mikk_t_space',True);build.set_editor_property('use_full_precision_u_vs',True)
            build.set_editor_property('generate_lightmap_u_vs',False)
            editor.set_lod_build_settings(repaired,0,build)
            repaired.set_material(0,material)
            u.EditorAssetLibrary.set_metadata_tag(repaired,'OOWMasonryOriginalMesh',original)
            u.EditorAssetLibrary.set_metadata_tag(repaired,'OOWMasonryReliefHash',report['generatedSha256'])
        report['importedBeforeFallbackPolicy']={
            'naniteEnabled':bool(repaired.get_editor_property('nanite_settings').enabled),
            'trianglesLOD0':repaired.get_num_triangles(0)}
        u.log('OOW_MASONRY_IMPORTED_BEFORE_FALLBACK '+json.dumps(report['importedBeforeFallbackPolicy']))
        policy={'fallback_target':u.NaniteFallbackTarget.PERCENT_TRIANGLES,'fallback_percent_triangles':1.,
                'fallback_relative_error':0.,'keep_percent_triangles':1.,'trim_relative_error':0.,
                'generate_fallback':u.NaniteGenerateFallback.ENABLED}
        changed=any(nanite.get_editor_property(k)!=v for k,v in policy.items())
        for k,v in policy.items(): nanite.set_editor_property(k,v)
        if not reused or changed:
            editor.set_nanite_settings(repaired,nanite,True)
        actual=repaired.get_editor_property('nanite_settings')
        assert all(actual.get_editor_property(k)==v for k,v in policy.items())
        assert repaired.get_num_triangles(0)==report['triangles'], 'HW ray tracing fallback must keep all candidate triangles'
        box=repaired.get_bounding_box()
        for axis,source_axis in (('x',0),('y',2),('z',1)):
            assert abs(getattr(box.min,axis)-report['exportLocalBounds'][source_axis][0]*100)<.05
            assert abs(getattr(box.max,axis)-report['exportLocalBounds'][source_axis][1]*100)<.05
        assert not editor.get_lod_build_settings(repaired,0).get_editor_property('recompute_normals')
        assert repaired.get_editor_property('nanite_settings').enabled==nanite.enabled
        assert u.EditorAssetLibrary.save_loaded_asset(repaired)
        comp.set_static_mesh(repaired);comp.set_material(0,material)
        report.update(appliedToUnreal=True,reused=reused,originalMesh=original,repairedMesh=repaired.get_path_name(),
                      material=material.get_path_name(),naniteEnabled=bool(actual.enabled),
                      fallbackTriangles=repaired.get_num_triangles(0),
                      naniteFallbackPolicy={k:str(actual.get_editor_property(k)) if 'target' in k or k=='generate_fallback'
                                           else actual.get_editor_property(k) for k in policy},
                      rayTracingProxyEnabled=bool(repaired.get_editor_property('ray_tracing_proxy_settings').enabled))
    assert comp.get_material(0)==material
    for actor in static:
        placement,mesh=state(actor);prior=before[actor.get_actor_label()]
        assert placement==prior[0]
        if actor!=target: assert mesh==prior[1]
    assert levels.save_current_level()
    report.update(actorTransformsUnchanged=len(before),otherActorsUnchanged=len(before)-1)
    (root/'Migration/masonry-relief.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    u.log('OOW_MASONRY_RELIEF '+json.dumps(report))


def self_test(write=False):
    root=Path(__file__).resolve().parent.parent
    for tile in range(-2,3):
        for row in ROW_CENTERS[:-1]:
            assert abs(height((.07,tile+row))+DEPTH)<1e-10
    assert abs(height((U_PHASE,.05))+DEPTH)<1e-10
    assert abs(height((.125+U_PHASE,.18))+DEPTH)<1e-10
    assert -VARIATION<=height((.10,.05))<=VARIATION
    _,report=generate(root,write)
    _,repeat=generate(root,False)
    assert report==repeat and report['beforeTriangles']==474
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    if '--self-test' in sys.argv or '--generate-only' in sys.argv:
        self_test('--generate-only' in sys.argv)
    else:
        main()
