"""Give Alley window glazing continuous per-room UVs without interior geometry.

UV0 and original vertex attributes are preserved (zero UV0 if absent).
UV1: whole-window projection, U left-to-right, V=0 bottom / V=1 top.
UV2: (stable 24-bit room seed, 1); non-room faces (0,-1).
True panes also receive a separate front-glass sheet, 1 cm outward, with native LODs.
Run after scene import, before surface materials. City is deliberately untouched.
--self-test validates CPU grouping; --generate-only also writes the local GLB.
Only an explicit UE execution imports meshes and changes the Alley map.
"""
import collections
import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

DEST = '/Game/Scenes/Alley/WindowInteriors'
RECIPE = 'window-uv-v2'
PREFIX = 'OOWInterior_'
FRONT_PREFIX = 'OOWGlassFront_'
GLASS = ('MASTER_Glass_', 'MASTER_Focus_Glass', 'MASTER_Frosted_Glass')


def sub(a, b): return tuple(x - y for x, y in zip(a, b))
def dot(a, b): return sum(x * y for x, y in zip(a, b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def length(a): return math.sqrt(dot(a, a))
def unit(a):
    size = length(a)
    return tuple(x / size for x in a) if size > 1e-12 else (0., 0., 0.)


class Union:
    def __init__(self, count): self.parent = list(range(count))
    def root(self, index):
        while self.parent[index] != index:
            self.parent[index] = self.parent[self.parent[index]]
            index = self.parent[index]
        return index
    def join(self, a, b): self.parent[self.root(b)] = self.root(a)


def read_glb(path):
    with path.open('rb') as f:
        magic, version, _ = struct.unpack('<III', f.read(12))
        assert magic == 0x46546C67 and version == 2
        count, kind = struct.unpack('<II', f.read(8))
        assert kind == 0x4E4F534A
        doc = json.loads(f.read(count))
        count, kind = struct.unpack('<II', f.read(8))
        assert kind == 0x004E4942
        return doc, f.read(count)


def read_accessor(doc, blob, index):
    accessor = doc['accessors'][index]
    assert 'sparse' not in accessor, 'Sparse source needs explicit expansion'
    view = doc['bufferViews'][accessor['bufferView']]
    component = accessor['componentType']
    fmt = {5120: 'b', 5121: 'B', 5122: 'h', 5123: 'H', 5125: 'I', 5126: 'f'}[component]
    count = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[accessor['type']]
    fmt = '<' + fmt * count
    size = struct.calcsize(fmt)
    stride = view.get('byteStride', size)
    offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
    raw = [blob[offset + i*stride:offset + i*stride + size] for i in range(accessor['count'])]
    values = [struct.unpack(fmt, value) for value in raw]
    if accessor.get('normalized'):
        divisor = {5120: 127, 5121: 255, 5122: 32767, 5123: 65535}[component]
        values = [tuple(max(-1., x / divisor) for x in value) for value in values]
    return raw, values


def canonical(normal):
    # One frame for coplanar triangles even if source triangles are reversed.
    axis = max(range(3), key=lambda i: abs(normal[i]))
    return tuple(-v for v in normal) if normal[axis] < 0 else normal


def frame(normal):
    vertical = unit(sub((0., 1., 0.), tuple(normal[1] * v for v in normal)))
    return unit(cross(vertical, normal)), vertical


def bounds(points, u, v):
    pu, pv = [dot(p, u) for p in points], [dot(p, v) for p in points]
    return min(pu), max(pu), min(pv), max(pv)


def is_window_rim(island, item):
    """A thin border with an empty central aperture is not an interior pane."""
    box = island['box']
    width, height = box[1]-box[0], box[3]-box[2]
    coverage = island['area'] / (width * height)
    island['rectangleCoverage'] = coverage
    if coverage >= .45:
        return False
    triangles = [[(dot(item['world'][v], island['u']), dot(item['world'][v], island['v']))
                  for v in item['triangles'][t]] for t in island['triangles']]
    def covers(point, triangle):
        signs = [(triangle[(i+1)%3][0]-triangle[i][0])*(point[1]-triangle[i][1])
                 - (triangle[(i+1)%3][1]-triangle[i][1])*(point[0]-triangle[i][0]) for i in range(3)]
        return min(signs) >= -1e-7 or max(signs) <= 1e-7
    # An arch/irregular filled pane can have a small bounding-box coverage, but
    # still covers its central opening. Require the entire central grid empty.
    return not any(covers((box[0]+x*width, box[2]+y*height), triangle)
                   for x in (.35, .5, .65) for y in (.35, .5, .65) for triangle in triangles)


def plane_islands(item):
    """Split connected bent glazing at corners before assigning planar UVs."""
    world, triangles = item['world'], item['triangles']
    welded = {}
    vertex_keys = []
    for point in world:
        key = tuple(round(v, 5) for v in point)
        vertex_keys.append(welded.setdefault(key, len(welded)))
    by_vertex = collections.defaultdict(list)
    normals, centers, areas = [], [], []
    for index, triangle in enumerate(triangles):
        a, b, c = [world[i] for i in triangle]
        n = cross(sub(b, a), sub(c, a))
        areas.append(length(n) * .5)
        normals.append(canonical(unit(n)))
        centers.append(tuple((a[i] + b[i] + c[i]) / 3 for i in range(3)))
        for vertex in triangle:
            by_vertex[vertex_keys[vertex]].append(index)
    connected, planar = Union(len(triangles)), Union(len(triangles))
    for incident in by_vertex.values():
        for a in incident:
            for b in incident:
                if b <= a: continue
                connected.join(a, b)
                if dot(normals[a], normals[b]) >= math.cos(math.radians(1.)) and abs(dot(normals[a], sub(centers[b], centers[a]))) <= .01:
                    planar.join(a, b)
    grouped = collections.defaultdict(list)
    for tri in range(len(triangles)):
        grouped[planar.root(tri)].append(tri)
    islands = []
    for ids in grouped.values():
        total = sum(areas[i] for i in ids)
        if total <= 1e-9: continue
        normal = canonical(unit(tuple(sum(normals[t][i] * areas[t] for t in ids) for i in range(3))))
        vertices = sorted({vertex for tri in ids for vertex in triangles[tri]})
        points = [world[i] for i in vertices]
        center = tuple(sum(p[i] for p in points) / len(points) for i in range(3))
        u, v = frame(normal)
        box = bounds(points, u, v)
        island = {'item': item['index'], 'triangles': ids, 'points': points,
                  'normal': normal, 'center': center, 'u': u, 'v': v, 'box': box,
                  'area': total, 'connected': connected.root(ids[0])}
        island['eligible'] = abs(normal[1]) < .25 and box[1]-box[0] >= .12 and box[3]-box[2] >= .25
        islands.append(island)
    # Bay/shopfront boxes have side and underside glass. Map their principal
    # face; keep side-face glass appearance instead of stretching a flat room.
    principal = {}
    for island in islands:
        if island['eligible']:
            key = island['connected']
            if key not in principal or principal[key]['area'] < island['area']:
                principal[key] = island
    for island in islands:
        main = principal.get(island['connected'])
        if main and dot(main['normal'], island['normal']) < math.cos(math.radians(1.)):
            island['eligible'] = False
    rim_components = {key: main['rectangleCoverage'] for key, main in principal.items()
                      if is_window_rim(main, item)}
    for island in islands:
        island['nonEmissiveRim'] = island['connected'] in rim_components
        if island['nonEmissiveRim']:
            island['eligible'] = False
            island['rimRectangleCoverage'] = rim_components[island['connected']]
    return islands, len({connected.root(t) for t in range(len(triangles))})


def adjacent(a, b):
    """Conservative side-by-side sash pairing, in world metres."""
    if dot(a['normal'], b['normal']) < math.cos(math.radians(1.)): return None
    relative = sub(b['center'], a['center'])
    if max(abs(dot(a['normal'], relative)), abs(dot(b['normal'], relative))) > .01: return None
    aa, bb = a['box'], bounds(b['points'], a['u'], a['v'])
    width_a, width_b = aa[1]-aa[0], bb[1]-bb[0]
    height_a, height_b = aa[3]-aa[2], bb[3]-bb[2]
    overlap_u = min(aa[1], bb[1]) - max(aa[0], bb[0])
    overlap_v = min(aa[3], bb[3]) - max(aa[2], bb[2])
    if overlap_u > .005 or overlap_u < -.25: return None
    if overlap_v < .95 * min(height_a, height_b): return None
    if abs((aa[2]+aa[3]-bb[2]-bb[3])*.5) > .03: return None
    if min(width_a, width_b) < .65 * max(width_a, width_b): return None
    return max(0., -overlap_u)


def group_rooms(islands):
    eligible = [i for i, island in enumerate(islands) if island['eligible']]
    merged = Union(len(islands))
    candidates = []
    for offset, a in enumerate(eligible):
        for b in eligible[offset+1:]:
            if length(sub(islands[a]['center'], islands[b]['center'])) > 6.: continue
            gap = adjacent(islands[a], islands[b])
            if gap is not None: candidates.append((gap, a, b))
    members = {i: [i] for i in eligible}
    for _, a, b in sorted(candidates):
        ra, rb = merged.root(a), merged.root(b)
        if ra == rb: continue
        ids = members[ra] + members[rb]
        reference = islands[ids[0]]
        box = bounds([p for i in ids for p in islands[i]['points']], reference['u'], reference['v'])
        # Never chain a row of independently framed windows into one panorama.
        if len(ids) > 4 or box[1]-box[0] > 5.5 or box[3]-box[2] > 4.5: continue
        merged.join(ra, rb)
        members[merged.root(ra)] = ids
    groups = collections.defaultdict(list)
    for index in eligible:
        groups[merged.root(index)].append(index)
    rooms = []
    for ids in sorted(groups.values(), key=lambda group: min(group)):
        reference = islands[ids[0]]
        u, v = reference['u'], reference['v']
        points = [p for i in ids for p in islands[i]['points']]
        box = bounds(points, u, v)
        center = tuple(sum(p[i] for p in points) / len(points) for i in range(3))
        identity = 'alley|' + ','.join(str(round(x, 2)) for x in center + reference['normal'])
        digest = hashlib.sha256(identity.encode()).digest()
        seed = int.from_bytes(digest[:3], 'big') / 16777216.
        rooms.append({'islands': ids, 'u': u, 'v': v, 'box': box, 'seed': seed,
                      'id': digest.hex()[:16], 'center': center})
    return rooms


def shader_choice(seed):
    """Mirror v4's image and occupancy hashes; GPU FMA may round differently."""
    f32 = lambda x: struct.unpack('<f', struct.pack('<f', x))[0]
    image_hash = f32(f32(seed * f32(17.171)) + f32(.37))
    occupancy_hash = f32(f32(seed * f32(73.137)) + f32(.11))
    image = min(5, int((image_hash - math.floor(image_hash)) * 6))
    occupied = occupancy_hash - math.floor(occupancy_hash) >= f32(.62)
    return image, occupied


def shader_distribution(rooms):
    choices = [shader_choice(room['seed']) for room in rooms]
    return {'imageDistribution': [sum(image == i for image, _ in choices) for i in range(6)],
            'litImageDistributionEstimate': [sum(image == i and lit for image, lit in choices) for i in range(6)],
            'litRoomCountEstimate': sum(lit for _, lit in choices),
            'shaderChoiceFormula': {'image': 'floor(frac(seed*17.171+.37)*6)',
                                    'occupied': 'step(.62,frac(seed*73.137+.11))',
                                    'precision': 'CPU float32 estimate; GPU FMA may differ at boundaries'}}


def analyze(root):
    doc, blob = read_glb(root / 'Migration' / 'Exported' / 'alley.glb')
    items, islands, original_islands = [], [], 0
    for node in doc['nodes']:
        if 'mesh' not in node: continue
        primitives = doc['meshes'][node['mesh']]['primitives']
        if not any(doc['materials'][p.get('material', 0)].get('name', '').startswith(GLASS) for p in primitives): continue
        assert len(primitives) == 1, 'Mixed-slot glazing needs explicit per-slot mapping'
        primitive = primitives[0]
        assert primitive.get('mode', 4) == 4
        attrs = primitive['attributes']
        assert 'TEXCOORD_1' not in attrs and 'TEXCOORD_2' not in attrs, 'Reserved UV channels already exist'
        _, positions = read_accessor(doc, blob, attrs['POSITION'])
        _, indices = read_accessor(doc, blob, primitive['indices'])
        indices = [value[0] for value in indices]
        matrix = node['matrix']
        world = [tuple(sum(matrix[c*4+r]*point[c] for c in range(3)) + matrix[12+r] for r in range(3)) for point in positions]
        item = {'index': len(items), 'name': node['name'], 'primitive': primitive,
                'material': doc['materials'][primitive['material']]['name'], 'positions': positions,
                'matrix': matrix, 'world': world, 'triangles': list(zip(indices[::3], indices[1::3], indices[2::3]))}
        parts, count = plane_islands(item)
        item['rawIslands'], item['planeIslands'] = count, len(parts)
        original_islands += count
        items.append(item)
        islands.extend(parts)
    return doc, blob, items, islands, group_rooms(islands), original_islands


def front_panes(doc, blob, items, islands):
    """Keep true panes; orient from source normals and remove near-identical sheets."""
    normals = {}
    eligible = [i for i, island in enumerate(islands) if island['eligible']]
    for index in eligible:
        island = islands[index]
        item = items[island['item']]
        matrix = item['matrix']
        # The runtime export bakes orientation into vertices, leaving only a
        # positive uniform quantization scale and translation on each node.
        assert all(abs(matrix[j]) < 1e-8 for j in (1, 2, 4, 6, 8, 9))
        assert matrix[0] > 0 and abs(matrix[0]-matrix[5])+abs(matrix[5]-matrix[10]) < 1e-6
        if item['index'] not in normals:
            normals[item['index']] = read_accessor(doc, blob, item['primitive']['attributes']['NORMAL'])[1]
        ids = {vertex for tri in island['triangles'] for vertex in item['triangles'][tri]}
        authored = unit(tuple(sum(normals[item['index']][v][axis] for v in ids) for axis in range(3)))
        alignment = dot(authored, island['normal'])
        assert abs(alignment) > .99, 'Ambiguous authored outward normal: ' + item['name']
        island['outwardNormal'] = tuple(value * (1 if alignment > 0 else -1) for value in island['normal'])
    duplicates = Union(len(islands))
    for offset, a_index in enumerate(eligible):
        a = islands[a_index]
        aa = a['box']
        area_a = (aa[1]-aa[0])*(aa[3]-aa[2])
        if a['area']/area_a < .95: continue
        for b_index in eligible[offset+1:]:
            b = islands[b_index]
            relative = sub(b['center'], a['center'])
            if length(relative) > .06 or dot(a['outwardNormal'], b['outwardNormal']) < math.cos(math.radians(1.)): continue
            if max(abs(dot(a['normal'], relative)), abs(dot(b['normal'], relative))) > .02: continue
            bb = bounds(b['points'], a['u'], a['v'])
            area_b = (bb[1]-bb[0])*(bb[3]-bb[2])
            overlap = max(0., min(aa[1], bb[1])-max(aa[0], bb[0])) * max(0., min(aa[3], bb[3])-max(aa[2], bb[2]))
            if b['area']/area_b >= .95 and overlap/(area_a+area_b-overlap) > .97:
                duplicates.join(a_index, b_index)
    groups = collections.defaultdict(list)
    for index in eligible:
        groups[duplicates.root(index)].append(index)
    keep, skipped = set(), []
    for indices in groups.values():
        normal = islands[indices[0]]['outwardNormal']
        chosen = max(indices, key=lambda index: (dot(islands[index]['center'], normal), -index))
        keep.add(chosen)
        for index in indices:
            if index != chosen:
                skipped.append({'actor': items[islands[index]['item']]['name'], 'triangles': islands[index]['triangles'],
                                'keptActor': items[islands[chosen]['item']]['name'], 'keptTriangles': islands[chosen]['triangles']})
    return keep, skipped


def generate(root, write=True):
    doc, blob, items, islands, rooms, original_islands = analyze(root)
    front_islands, skipped_front_panes = front_panes(doc, blob, items, islands)
    assignment = {}
    for island in islands:
        if island['nonEmissiveRim']:
            for tri in island['triangles']:
                assignment[island['item'], tri] = -2
    for room_index, room in enumerate(rooms):
        for island_index in room['islands']:
            island = islands[island_index]
            for tri in island['triangles']:
                assignment[island['item'], tri] = room_index
    out = {'asset': {'version': '2.0', 'generator': 'OutOfWindow ' + RECIPE},
           'scene': 0, 'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [],
           'materials': [{'name': 'OOW_Window_ImportPlaceholder', 'pbrMetallicRoughness': {'metallicFactor': 0, 'roughnessFactor': .2}}],
           'accessors': [], 'bufferViews': [], 'buffers': [],
           'extensionsUsed': ['KHR_mesh_quantization'], 'extensionsRequired': ['KHR_mesh_quantization']}
    data = bytearray()
    stats, front_stats = [], []

    def put(raw, accessor, target=34962):
        data.extend(b'\0' * ((-len(data)) % 4))
        view = len(out['bufferViews'])
        out['bufferViews'].append({'buffer': 0, 'byteOffset': len(data), 'byteLength': len(raw), 'target': target})
        data.extend(raw)
        accessor = copy.deepcopy(accessor)
        accessor['bufferView'], accessor['byteOffset'] = view, 0
        accessor.pop('sparse', None)
        out['accessors'].append(accessor)
        return len(out['accessors']) - 1

    for item in items:
        used_rooms = {assignment[item['index'], tri] for tri in range(len(item['triangles']))
                      if assignment.get((item['index'], tri), -1) >= 0}
        rejected = [tri for tri in range(len(item['triangles'])) if assignment.get((item['index'], tri)) == -2]
        if not used_rooms and not rejected: continue
        # A shared vertex at a bent corner needs separate UVs, without moving
        # it or changing any source triangle/material/normal/UV0 value.
        remap, vertices, uv1, uv2, indices = {}, [], [], [], []
        for tri_index, triangle in enumerate(item['triangles']):
            room_index = assignment.get((item['index'], tri_index), -1)
            for original in triangle:
                key = original, room_index
                if key not in remap:
                    remap[key] = len(vertices)
                    vertices.append(original)
                    if room_index >= 0:
                        room = rooms[room_index]
                        box, point = room['box'], item['world'][original]
                        uv = ((dot(point, room['u']) - box[0])/(box[1]-box[0]),
                              (dot(point, room['v']) - box[2])/(box[3]-box[2]))
                        assert all(-.000001 <= value <= 1.000001 for value in uv)
                        uv1.append(tuple(max(0., min(1., value)) for value in uv))
                        uv2.append((room['seed'], 1.))
                    else:
                        uv1.append((0., 0.))
                        # Every non-room face on an adapted mesh is dark.
                        # Legacy v3 fallback belongs only to untagged meshes.
                        uv2.append((0., -1.))
                indices.append(remap[key])
        source_primitive = item['primitive']
        primitive = {'attributes': {}, 'material': 0}
        for semantic, index in source_primitive['attributes'].items():
            raw, _ = read_accessor(doc, blob, index)
            copied = b''.join(raw[i] for i in vertices)
            accessor = copy.deepcopy(doc['accessors'][index])
            accessor['count'] = len(vertices)
            primitive['attributes'][semantic] = put(copied, accessor)
            assert all(copied[i*len(raw[0]):(i+1)*len(raw[0])] == raw[original] for i, original in enumerate(vertices))
        # Channels must be contiguous or importers may renumber UV1/UV2.
        for channel, values in [(0, [(0., 0.)]*len(vertices)), (1, uv1), (2, uv2)]:
            semantic = 'TEXCOORD_' + str(channel)
            if semantic in primitive['attributes']: continue
            raw = b''.join(struct.pack('<ff', *value) for value in values)
            primitive['attributes'][semantic] = put(raw, {'componentType': 5126, 'count': len(vertices), 'type': 'VEC2'})
        index_data = b''.join(struct.pack('<I', value) for value in indices)
        primitive['indices'] = put(index_data, {'componentType': 5125, 'count': len(indices), 'type': 'SCALAR'}, 34963)
        mesh_index = len(out['meshes'])
        asset_name = PREFIX + item['name']
        out['meshes'].append({'name': asset_name, 'primitives': [primitive]})
        out['nodes'].append({'name': asset_name, 'mesh': mesh_index})
        out['scenes'][0]['nodes'].append(mesh_index)
        # Exact per-triangle correspondence, including source UV0 at seams.
        assert [vertices[i] for i in indices] == [i for triangle in item['triangles'] for i in triangle]
        stats.append({'actor': item['name'], 'assetName': asset_name, 'sourceMaterial': item['material'],
                      'sourceVertices': len(item['positions']), 'outputVertices': len(vertices),
                      'triangles': len(item['triangles']), 'connectedIslands': item['rawIslands'],
                      'planeIslands': item['planeIslands'], 'roomGroups': len(used_rooms),
                      'enabledTriangles': sum(assignment.get((item['index'], tri), -1) >= 0 for tri in range(len(item['triangles']))),
                      'nonEmissiveRimTriangles': len(rejected),
                      'nonEmissiveRimComponents': len({i['connected'] for i in islands if i['item'] == item['index'] and i['nonEmissiveRim']}),
                      'nonEmissiveOtherTriangles': sum(assignment.get((item['index'], tri), -1) == -1 for tri in range(len(item['triangles']))),
                      'addedZeroUV0': 'TEXCOORD_0' not in source_primitive['attributes']})
        selected = sorted(index for index in front_islands if islands[index]['item'] == item['index'])
        if not selected: continue
        front_vertices, front_positions, front_indices, front_uv1, front_uv2, front_remap = [], [], [], [], [], {}
        for island_index in selected:
            island = islands[island_index]
            assert island['eligible'] and not island['nonEmissiveRim']
            offset = tuple(value * .01 / item['matrix'][0] for value in island['outwardNormal'])
            for tri in island['triangles']:
                room_index = assignment[item['index'], tri]
                assert room_index >= 0
                for original in item['triangles'][tri]:
                    key = (island_index, original)
                    if key not in front_remap:
                        front_remap[key] = len(front_vertices)
                        front_vertices.append(original)
                        shifted = tuple(value+delta for value, delta in zip(item['positions'][original], offset))
                        shifted = struct.unpack('<fff', struct.pack('<fff', *shifted))
                        assert abs(length(sub(shifted, item['positions'][original])) * item['matrix'][0] - .01) < .00001
                        front_positions.append(shifted)
                        back_index = remap[original, room_index]
                        front_uv1.append(uv1[back_index])
                        front_uv2.append(uv2[back_index])
                    front_indices.append(front_remap[key])
        front_primitive = {'attributes': {}, 'material': 0}
        for semantic, index in source_primitive['attributes'].items():
            accessor = copy.deepcopy(doc['accessors'][index])
            accessor['count'] = len(front_vertices)
            if semantic == 'POSITION':
                raw = b''.join(struct.pack('<fff', *value) for value in front_positions)
                accessor.update(componentType=5126, min=[min(p[k] for p in front_positions) for k in range(3)],
                                max=[max(p[k] for p in front_positions) for k in range(3)])
                accessor.pop('normalized', None)
            else:
                original_raw, _ = read_accessor(doc, blob, index)
                raw = b''.join(original_raw[v] for v in front_vertices)
            front_primitive['attributes'][semantic] = put(raw, accessor)
        for channel, values in [(0, [(0., 0.)]*len(front_vertices)), (1, front_uv1), (2, front_uv2)]:
            semantic = 'TEXCOORD_' + str(channel)
            if semantic not in front_primitive['attributes']:
                front_primitive['attributes'][semantic] = put(b''.join(struct.pack('<ff', *value) for value in values),
                    {'componentType': 5126, 'count': len(front_vertices), 'type': 'VEC2'})
        front_primitive['indices'] = put(b''.join(struct.pack('<I', value) for value in front_indices),
            {'componentType': 5125, 'count': len(front_indices), 'type': 'SCALAR'}, 34963)
        front_name, mesh_index = FRONT_PREFIX + item['name'], len(out['meshes'])
        out['meshes'].append({'name': front_name, 'primitives': [front_primitive]})
        out['nodes'].append({'name': front_name, 'mesh': mesh_index})
        out['scenes'][0]['nodes'].append(mesh_index)
        front_stats.append({'actor': front_name, 'backingActor': item['name'], 'assetName': front_name,
                            'triangles': len(front_indices)//3, 'paneIslands': len(selected), 'offsetMeters': .01,
                            'nonEmissiveRimTriangles': 0, 'uvChannels': 3})
    data.extend(b'\0' * ((-len(data)) % 4))
    out['buffers'] = [{'byteLength': len(data)}]
    encoded = json.dumps(out, separators=(',', ':')).encode()
    encoded += b' ' * ((-len(encoded)) % 4)
    glb = struct.pack('<III', 0x46546C67, 2, 28+len(encoded)+len(data)) + struct.pack('<II', len(encoded), 0x4E4F534A) + encoded + struct.pack('<II', len(data), 0x004E4942) + data
    output = root / 'Migration' / 'Generated' / 'alley-window-interiors.glb'
    rejected_components = collections.defaultdict(list)
    for island in islands:
        if island['nonEmissiveRim']:
            rejected_components[island['item'], island['connected']].append(island)
    report = {'recipe': RECIPE, 'uvChannels': {'0': 'source or zero', '1': 'whole window, V0=bottom', '2': 'seed, flag: -1 non-emissive; 0 reserved legacy fallback; 1 room'},
              'sourceGlassActors': len(items), 'changedActors': len(stats), 'connectedIslands': original_islands,
              'planeIslands': len(islands), 'eligiblePlaneIslands': sum(i['eligible'] for i in islands),
              'roomGroups': len(rooms), 'joinedGroups': sum(len(r['islands']) > 1 for r in rooms),
              'crossActorGroups': sum(len({islands[i]['item'] for i in r['islands']}) > 1 for r in rooms),
              'nonEmissiveRimComponents': len(rejected_components),
              'nonEmissiveRimTriangles': sum(a['nonEmissiveRimTriangles'] for a in stats),
              'nonEmissiveOtherTriangles': sum(a['nonEmissiveOtherTriangles'] for a in stats),
              'frontGlassActors': len(front_stats), 'frontGlassTriangles': sum(a['triangles'] for a in front_stats),
              'frontGlassPaneIslands': sum(a['paneIslands'] for a in front_stats),
              'frontGlassOffsetMeters': .01, 'frontGlassSkippedDuplicates': skipped_front_panes, 'frontActors': front_stats,
              'rejectedRims': [{'actor': items[item_index]['name'], 'component': component,
                               'rectangleCoverage': parts[0]['rimRectangleCoverage'],
                               'triangles': sorted(t for part in parts for t in part['triangles'])}
                              for (item_index, component), parts in rejected_components.items()],
              **shader_distribution(rooms),
              'generatedSha256': hashlib.sha256(glb).hexdigest(), 'actors': stats,
              'rooms': [{'id': r['id'], 'seed': r['seed'], 'centerMeters': list(r['center']),
                         'sashes': len(r['islands']), 'widthMeters': r['box'][1]-r['box'][0],
                         'heightMeters': r['box'][3]-r['box'][2],
                         'normalThreeXYZ': list(islands[r['islands'][0]]['outwardNormal']),
                         'actors': sorted({items[islands[i]['item']]['name'] for i in r['islands']})} for r in rooms]}
    if write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(glb)
        (root / 'Migration' / 'window-interiors-geometry.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return output, report


def main():
    import unreal as u
    root = Path(u.Paths.project_dir()).parent
    source, report = generate(root)
    levels = u.get_editor_subsystem(u.LevelEditorSubsystem)
    actor_editor = u.get_editor_subsystem(u.EditorActorSubsystem)
    mesh_editor = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    if not levels.load_level('/Game/Maps/Alley'): raise RuntimeError('Cannot load Alley')
    actors = {a.get_actor_label(): a for a in actor_editor.get_all_level_actors() if isinstance(a, u.StaticMeshActor)}
    expected = report['generatedSha256']
    targets, original_settings = [], {}
    for entry in report['actors']:
        actor = actors[entry['actor']]
        comp = actor.static_mesh_component
        assert comp.get_num_materials() == 1, 'Unexpected material-slot count: ' + entry['actor']
        targets.append((entry, actor, comp.static_mesh, comp.get_material(0)))
        mesh = comp.static_mesh
        bound = mesh.get_bounds()
        original_settings[entry['actor']] = {
            'build': mesh_editor.get_lod_build_settings(mesh, 0), 'nanite': mesh.get_editor_property('nanite_settings'),
            'original': str(u.EditorAssetLibrary.get_metadata_tag(mesh, 'OOWWindowOriginalMesh')) or mesh.get_path_name(),
            'bounds': tuple(getattr(getattr(bound, field), axis) for field in ('origin', 'box_extent') for axis in ('x', 'y', 'z'))}
    fronts = {entry['actor']: actors.get(entry['actor']) for entry in report['frontActors']}
    front_materials = {label: actor.static_mesh_component.get_material(0) if actor else None for label, actor in fronts.items()}
    needs_import = any(str(u.EditorAssetLibrary.get_metadata_tag(mesh, 'OOWWindowGeometry')) != expected for _, _, mesh, _ in targets)
    needs_import |= any(not actor or str(u.EditorAssetLibrary.get_metadata_tag(actor.static_mesh_component.static_mesh,
                         'OOWWindowGeometry')) != expected for actor in fronts.values())
    imported_by_name = {}
    if needs_import:
        manager = u.InterchangeManager.get_interchange_manager_scripted()
        params = u.ImportAssetParameters()
        params.is_automated, params.replace_existing = True, True
        imported = manager.import_asset(DEST, manager.create_source_data(str(source)), params)
        imported_by_name = {asset.get_name(): asset for asset in (imported or []) if isinstance(asset, u.StaticMesh)}
        assert len(imported_by_name) == len(targets) + len(fronts), 'Interchange must keep the generated meshes separate'
        # Validate every replacement before changing any actor.
        for entry, actor, old, _ in targets:
            new = imported_by_name[entry['assetName']]
            bound = new.get_bounds()
            values = tuple(getattr(getattr(bound, field), axis) for field in ('origin', 'box_extent') for axis in ('x', 'y', 'z'))
            assert max(abs(a-b) for a, b in zip(original_settings[entry['actor']]['bounds'], values)) < .05, 'Local geometry bounds changed: ' + entry['actor']
    backing_labels = {entry['backingActor'] for entry in report['frontActors']}
    for entry, actor, old, material in targets:
        mesh = imported_by_name.get(entry['assetName'], old)
        if needs_import:
            build = original_settings[entry['actor']]['build']
            build.set_editor_property('generate_lightmap_u_vs', False)
            build.set_editor_property('use_full_precision_u_vs', True)
            mesh_editor.set_lod_build_settings(mesh, 0, build)
            mesh_editor.set_nanite_settings(mesh, original_settings[entry['actor']]['nanite'], True)
            assert mesh_editor.get_num_uv_channels(mesh, 0) >= 3, 'Required UV channels missing'
            mesh.set_material(0, material)
            original = original_settings[entry['actor']]['original']
            u.EditorAssetLibrary.set_metadata_tag(mesh, 'OOWWindowGeometry', expected)
            u.EditorAssetLibrary.set_metadata_tag(mesh, 'OOWWindowOriginalMesh', original)
            u.EditorAssetLibrary.set_metadata_tag(mesh, 'OOWWindowSourceNode', entry['actor'])
            u.EditorAssetLibrary.save_loaded_asset(mesh)
            actor.static_mesh_component.set_static_mesh(mesh)
            actor.static_mesh_component.set_material(0, material)
        tags = {str(tag) for tag in actor.tags} | {'OOWWindowInterior'}
        tags.discard('OOWWindowGlassBacking')
        if entry['actor'] in backing_labels:
            tags.add('OOWWindowGlassBacking')
        actor.tags = sorted(tags)
        entry['unrealMesh'] = mesh.get_path_name()
        entry['unrealMaterial'] = material.get_path_name()
    for entry in report['frontActors']:
        label = entry['actor']
        backing = actors[entry['backingActor']]
        front = fronts[label]
        if not front:
            front = actor_editor.spawn_actor_from_class(u.StaticMeshActor, backing.get_actor_location(), backing.get_actor_rotation())
            assert front, 'Cannot create front glass actor: ' + label
            front.set_actor_label(label)
        front.set_actor_transform(backing.get_actor_transform(), False, True)
        comp = front.static_mesh_component
        mesh = imported_by_name[entry['assetName']] if needs_import else comp.static_mesh
        if needs_import:
            build = original_settings[entry['backingActor']]['build']
            build.set_editor_property('generate_lightmap_u_vs', False)
            build.set_editor_property('use_full_precision_u_vs', True)
            mesh_editor.set_lod_build_settings(mesh, 0, build)
            nanite = mesh.get_editor_property('nanite_settings')
            nanite.enabled = False
            mesh_editor.set_nanite_settings(mesh, nanite, True)
            lods = u.StaticMeshReductionOptions()
            lods.auto_compute_lod_screen_size = False
            lods.reduction_settings = [u.StaticMeshReductionSettings(percent_triangles=1., screen_size=1.),
                                      u.StaticMeshReductionSettings(percent_triangles=.7, screen_size=.25),
                                      u.StaticMeshReductionSettings(percent_triangles=.4, screen_size=.08)]
            mesh_editor.set_lods(mesh, lods)
            assert mesh_editor.get_num_uv_channels(mesh, 0) >= 3, 'Front glass UV channels missing'
            material = front_materials[label] or u.load_asset('/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial')
            mesh.set_material(0, material)
            u.EditorAssetLibrary.set_metadata_tag(mesh, 'OOWWindowGeometry', expected)
            u.EditorAssetLibrary.set_metadata_tag(mesh, 'OOWWindowSourceNode', entry['backingActor'])
            u.EditorAssetLibrary.save_loaded_asset(mesh)
            comp.set_static_mesh(mesh)
            comp.set_material(0, material)
        comp.set_editor_property('mobility', u.ComponentMobility.STATIC)
        comp.set_editor_property('cast_shadow', False)
        comp.set_editor_property('visible_in_ray_tracing', True)
        front.tags = sorted({str(tag) for tag in front.tags} | {'OOWGeometry', 'OOWWindowGlassFront'})
        assert not mesh.get_editor_property('nanite_settings').enabled
        entry['unrealMesh'] = mesh.get_path_name()
    # Re-runs remove only obsolete generated front actors, never source geometry.
    for label, actor in actors.items():
        if label.startswith(FRONT_PREFIX) and 'OOWWindowGlassFront' in {str(tag) for tag in actor.tags} and label not in fronts:
            actor_editor.destroy_actor(actor)
    levels.save_current_level()
    report['appliedToUnreal'] = True
    (root / 'Migration' / 'window-interiors-geometry.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_WINDOW_GEOMETRY_COMPLETE ' + json.dumps({k: v for k, v in report.items() if k not in ('actors', 'rooms', 'rejectedRims', 'frontActors', 'frontGlassSkippedDuplicates')}))


def self_test(write=False):
    root = Path(__file__).resolve().parent.parent
    _, report = generate(root, write)
    _, repeated = generate(root, False)
    assert report == repeated, 'Grouping/seed generation must be deterministic'
    assert report['roomGroups'] > 50 and report['joinedGroups'] > 10
    assert all(report['imageDistribution']), 'All six room variations must be reachable'
    right = next(a for a in report['actors'] if a['actor'] == 'OOW_00760_paris_building_09_8')
    left = next(a for a in report['actors'] if a['actor'] == 'OOW_00719_Paris_Building_08_paris_building_08_1')
    assert right['roomGroups'] < right['connectedIslands']
    assert right['nonEmissiveRimComponents'] == 12 and right['nonEmissiveRimTriangles'] == 144
    assert report['nonEmissiveRimComponents'] == 26 and report['nonEmissiveRimTriangles'] == 259
    assert right['triangles'] == 274, 'Reject emission without removing any geometry'
    assert report['frontGlassActors'] == 66 and report['frontGlassTriangles'] == 1199
    assert all(entry['nonEmissiveRimTriangles'] == 0 for entry in report['frontActors'])
    assert report['frontGlassPaneIslands'] == report['eligiblePlaneIslands'] - len(report['frontGlassSkippedDuplicates'])
    assert left['roomGroups'] <= 11, 'The three top-floor double sashes should merge'
    print(json.dumps({k: v for k, v in report.items() if k not in ('actors', 'rooms', 'rejectedRims', 'frontActors', 'frontGlassSkippedDuplicates')}, indent=2))
    print(json.dumps({'right': right, 'left': left}, indent=2))


if __name__ == '__main__':
    if '--self-test' in sys.argv or '--generate-only' in sys.argv:
        self_test('--generate-only' in sys.argv)
    else:
        main()
