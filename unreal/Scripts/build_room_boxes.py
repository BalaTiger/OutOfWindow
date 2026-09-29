"""Fifteen inexpensive furnished interiors for the fixed Alley camera.

CPU: plan(root, analysis=None), generate(root, analysis=None, write=True).
UE: apply(root, analysis=None) while Alley is loaded; caller saves the map.
Geometry is inside the facade, along -outwardNormal. No source actor is changed.
Six canonical layouts are also the source geometry for offline Interior Mapping.
"""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_window_interiors as windows
from build_window_interiors import HERO_ROOM_IDS

RECIPE = 'hero-rooms-v2'
PREFIX = 'OOWHeroRoom_'
GLASS_PREFIX = 'OOWHeroGlass_'
LIGHT_PREFIX = 'OOWHeroLight_'
DEST = '/Game/Scenes/Alley/HeroRooms'
MATERIAL_DEST = '/Game/Materials/OOW/HeroRooms'
LAYOUTS = ('study', 'sitting', 'kitchen', 'bedroom', 'dining', 'reading')
# Authored occupancy is independent of the number of physical rooms. Dark rooms
# still have geometry and a lamp; eight occupied rooms leave four exterior rects.
LIT_ROOM_IDS = frozenset(('67294f945510fc8a', '14286f445050f0e5',
    '13a26cb6982569b0', 'e8143a4235edd362', '2c4f36af47ee8629',
    'fe8ba70448e8d0b4', '4b36e0ec1c9d5fc3', '360ea453eb0f5fb6_R'))
# Linear, deliberately subdued colours; illumination comes from real lights.
MATERIALS = {
    'plaster': ((.38, .32, .24), .91, 0),
    'wood': ((.16, .080, .032), .48, 0),
    'fabric': ((.13, .17, .12), .86, 0),
    'linen': ((.48, .39, .27), .89, 0),
    'rug': ((.15, .065, .040), .95, 0),
    'ceramic': ((.32, .24, .15), .35, 0),
    'metal': ((.12, .085, .040), .35, .7),
    'lamp': ((.58, .43, .23), .7, 0),
}


def world_point(room, point):
    return tuple(room['originMeters'][i] + room['right'][i]*point[0]
                 + room['up'][i]*point[1] + room['inward'][i]*point[2] for i in range(3))


def ue_point(point):
    return [point[0]*100, point[2]*100, point[1]*100]


def plan(root, analysis=None):
    root = Path(root)
    doc, blob, items, islands, rooms, _ = analysis or windows.analyze(root)
    if any('outwardNormal' not in islands[r['islands'][0]] for r in rooms):
        windows.front_panes(doc, blob, items, islands)
    found = {room['id']: room for room in rooms}
    missing = set(HERO_ROOM_IDS) - found.keys()
    if missing:
        raise RuntimeError('Hero apertures absent from source: ' + ', '.join(sorted(missing)))
    result = []
    for index, identity in enumerate(HERO_ROOM_IDS):
        source = found[identity]
        normal = islands[source['islands'][0]]['outwardNormal']
        sources = [source]
        if identity == '2c4f36af47ee8629':
            sources.append(found['2c5bb7bff6cbf8a5'])
        triangles = []
        for backing in sources:
            for island_index in backing['islands']:
                island, item = islands[island_index], items[islands[island_index]['item']]
                for tri in island['triangles']:
                    triangles.append([item['world'][v] for v in item['triangles'][tri]])
        groups = [('', triangles)]
        if identity in windows.HERO_SPLIT_ROOM_IDS:
            middle = (source['box'][0]+source['box'][1])*.5
            groups = [(suffix, [tri for tri in triangles
                               if (sum(windows.dot(p, source['u']) for p in tri)/3 < middle) == left])
                      for suffix, left in (('_L', True), ('_R', False))]
        for suffix, group in groups:
            points = [point for triangle in group for point in triangle]
            lo, hi = min(windows.dot(p, source['u']) for p in points), max(windows.dot(p, source['u']) for p in points)
            bottom, top = min(windows.dot(p, source['v']) for p in points), max(windows.dot(p, source['v']) for p in points)
            width, height = hi-lo, top-bottom
            origin = [source['center'][i]+source['u'][i]*((lo+hi)*.5-windows.dot(source['center'], source['u']))
                      +source['v'][i]*(bottom-windows.dot(source['center'], source['v'])) for i in range(3)]
            scale = max(.85, min(1.35, height/2.75))
            physical_id = identity+suffix
            room = {'id': physical_id, 'sourceRoomId': identity, 'name': PREFIX+physical_id+'_v3',
                    'seed': source['seed'], 'originMeters': origin, 'right': list(source['u']),
                    'up': list(source['v']), 'inward': [-value for value in normal],
                    'apertureWidthMeters': width, 'apertureHeightMeters': height,
                    'apertureSourceBounds': [lo, hi, bottom, top],
                    'widthMeters': max(3.6*scale, width+.60), 'heightMeters': height+.80*scale,
                    'depthMeters': 3.4*scale, 'floorMeters': -.45*scale, 'furnitureScale': scale,
                    'layout': LAYOUTS[(index+(suffix == '_R')) % len(LAYOUTS)],
                    'occupied': physical_id in LIT_ROOM_IDS,
                    'sourceActors': sorted({items[islands[i]['item']]['name'] for s in sources for i in s['islands']})}
            room['lampLocalMeters'] = [-room['widthMeters']*.34, room['floorMeters']+1.38*scale, room['depthMeters']*.58]
            room['light'] = {'name': LIGHT_PREFIX+physical_id, 'room': physical_id,
                            'positionCm': ue_point(world_point(room, room['lampLocalMeters'])),
                            'lumens': 135*scale*scale, 'temperatureKelvin': 2850+(index % 4)*120,
                            'radiusCm': room['depthMeters']*160, 'sourceRadiusCm': 9*scale,
                            'tags': ['OOWNightLight', 'OOWInteriorLight', 'OOWHeroLight', 'OOWRoom_'+physical_id]} if room['occupied'] else None
            result.append(room)
    # Adjacent room shells stop on their own side of the centre partition.
    # Source panes can overlap and extend behind masonry, so their bounds cannot
    # be used as building-interior boundaries. Keep glass/apertures unchanged.
    for room in result:
        width = room['widthMeters']
        neighbours = []
        for other in result:
            if other is room or windows.dot(room['inward'], other['inward']) < .9999:
                continue
            delta = windows.sub(other['originMeters'], room['originMeters'])
            if abs(windows.dot(delta, room['inward'])) > .20 or abs(windows.dot(delta, room['up'])) > .10:
                continue
            separation = abs(windows.dot(delta, room['right']))
            if separation < 1:
                continue
            available = separation-.20  # two 8 cm shells and 4 cm separation
            if available < width:
                width = available
                neighbours.append(other['id'])
        if neighbours:
            room['widthMeters'] = width
            room['neighbourConstraints'] = neighbours
            room['lampLocalMeters'][0] = -width*.34
            if room['light']:
                room['light']['positionCm'] = ue_point(world_point(room, room['lampLocalMeters']))
    return {'recipe': RECIPE, 'appliedToUnreal': False, 'rooms': result,
            'nightEnvelope': 'smoothstep(.58,.86,Night), existing WindowDirector',
            'sourceGeometryChanged': False}


def template_room(index):
    """Canonical x-right/y-up/z-inward geometry; no source-scene dependency."""
    index %= len(LAYOUTS)
    return {'id': 'template_%02d' % index, 'name': 'OOWRoomTemplate_%02d' % index,
            'originMeters': [0, 0, 0], 'right': [1, 0, 0], 'up': [0, 1, 0], 'inward': [0, 0, 1],
            'apertureWidthMeters': 2., 'apertureHeightMeters': 2.75,
            'widthMeters': 3.6, 'heightMeters': 3.5, 'depthMeters': 3.4,
            'floorMeters': -.45, 'furnitureScale': 1., 'layout': LAYOUTS[index], 'occupied': True,
            'lampLocalMeters': [-1.224, .93, 1.972],
            'imBoxMin': [-1.8, -.45, 0], 'imBoxMax': [1.8, 3.05, 3.4],
            'imWindowMin': [-1, 0], 'imWindowMax': [1, 2.75]}


class RoomMesh:
    """Small explicit mesh builder; one imported actor per furnished room."""
    def __init__(self, room):
        self.room, self.parts = room, {}

    def quad(self, material, points, normals=None, uv=None):
        part = self.parts.setdefault(material, {'positions': [], 'normals': [], 'uv': [], 'indices': []})
        face = windows.unit(windows.cross(windows.sub(points[1], points[0]), windows.sub(points[2], points[0])))
        normals = normals or [face]*4
        if windows.dot(face, normals[0]) < 0:
            points, normals = [points[i] for i in (0, 3, 2, 1)], [normals[i] for i in (0, 3, 2, 1)]
            if uv: uv = [uv[i] for i in (0, 3, 2, 1)]
        if uv is None:
            a = windows.length(windows.sub(points[1], points[0]))*100
            b = windows.length(windows.sub(points[3], points[0]))*100
            uv = [(0, 0), (a, 0), (a, b), (0, b)]
        offset = len(part['positions'])
        part['positions'].extend(world_point(self.room, point) for point in points)
        for normal in normals:
            part['normals'].append(tuple(self.room['right'][i]*normal[0] + self.room['up'][i]*normal[1]
                                         + self.room['inward'][i]*normal[2] for i in range(3)))
        part['uv'].extend(uv)
        # right/up/inward is left handed for some facade orientations.
        a, b, c = part['positions'][-4:-1]
        winding = windows.dot(windows.cross(windows.sub(b, a), windows.sub(c, a)), part['normals'][-4])
        order = (0, 1, 2, 0, 2, 3) if winding > 0 else (0, 2, 1, 0, 3, 2)
        part['indices'].extend(offset+i for i in order)

    def box(self, material, centre, size, bevel=0):
        half = [value*.5 for value in size]
        bevel = min(bevel, min(half)*.85)
        for axis in range(3):
            a, b = [i for i in range(3) if i != axis]
            us = [-half[a], half[a]] if not bevel else [-half[a], -half[a]+bevel, half[a]-bevel, half[a]]
            vs = [-half[b], half[b]] if not bevel else [-half[b], -half[b]+bevel, half[b]-bevel, half[b]]
            for sign in (-1, 1):
                for ui in range(len(us)-1):
                    for vi in range(len(vs)-1):
                        points, normals, uv = [], [], []
                        for iu, iv in ((ui, vi), (ui+1, vi), (ui+1, vi+1), (ui, vi+1)):
                            p = [0., 0., 0.]
                            p[axis], p[a], p[b] = sign*half[axis], us[iu], vs[iv]
                            n = [0., 0., 0.]
                            n[axis] = sign
                            if bevel:
                                inside = [max(-half[i]+bevel, min(half[i]-bevel, p[i])) for i in range(3)]
                                n = windows.unit(windows.sub(p, inside))
                                p = [inside[i]+n[i]*bevel for i in range(3)]
                            points.append(tuple(p[i]+centre[i] for i in range(3)))
                            normals.append(n)
                            uv.append(((us[iu]+half[a])*100, (vs[iv]+half[b])*100))
                        self.quad(material, points, normals, uv)

    def lathe(self, material, centre, profile, segments=20, caps=True):
        for (ya, ra), (yb, rb) in zip(profile, profile[1:]):
            slope = (ra-rb)/max(1e-6, yb-ya)
            for i in range(segments):
                angles = [2*math.pi*i/segments, 2*math.pi*(i+1)/segments]
                points, normals = [], []
                for angle, y, radius in ((angles[0], ya, ra), (angles[1], ya, ra),
                                         (angles[1], yb, rb), (angles[0], yb, rb)):
                    points.append((centre[0]+math.cos(angle)*radius, centre[1]+y, centre[2]+math.sin(angle)*radius))
                    normals.append(windows.unit((math.cos(angle), slope, math.sin(angle))))
                self.quad(material, points, normals)
        if caps:
            for y, radius, sign in ((profile[0][0], profile[0][1], -1), (profile[-1][0], profile[-1][1], 1)):
                for i in range(segments):
                    a, b = 2*math.pi*i/segments, 2*math.pi*(i+1)/segments
                    c = (centre[0], centre[1]+y, centre[2])
                    self.quad(material, [c, (c[0]+radius*math.cos(a), c[1], c[2]+radius*math.sin(a)),
                                         (c[0]+radius*math.cos(b), c[1], c[2]+radius*math.sin(b)), c], [(0, sign, 0)]*4)


def furnish(room):
    mesh = RoomMesh(room)
    w, h, d, floor, s = (room[key] for key in ('widthMeters', 'heightMeters', 'depthMeters', 'floorMeters', 'furnitureScale'))
    # Inner shell surfaces exactly match the parallax-corrected IM box bounds.
    mesh.box('plaster', (0, floor+h*.5, d+.04), (w+.16, h, .08))
    for sign in (-1, 1):
        mesh.box('plaster', (sign*(w*.5+.04), floor+h*.5, d*.5), (.08, h, d))
        mesh.box('wood', (sign*(w*.5-.015), floor+.08*s, d*.5), (.03, .16*s, d))
    mesh.box('wood', (0, floor-.04, d*.5), (w+.16, .08, d))
    mesh.box('plaster', (0, floor+h+.04, d*.5), (w+.16, .08, d))
    mesh.box('wood', (0, floor+.08*s, d-.015), (w, .16*s, .03))
    mesh.box('rug', (0, floor+.006, d*.49), (2.0*s, .012, 1.65*s))
    aw, ah = room['apertureWidthMeters'], room['apertureHeightMeters']
    mesh.box('wood', (0, -.035, .13), (min(aw+.08, w-.10), .07, .25))
    curtain_span = min(aw, w-.28)
    for sign in (-1, 1):
        # Eight pleats suffice at this camera distance; depth still occludes.
        for i in range(8):
            x0, x1 = sign*(curtain_span*.5-.06)-.115+i*.03, sign*(curtain_span*.5-.06)-.115+(i+1)*.03
            z0, z1 = .15+.04*math.cos(i*math.pi), .15+.04*math.cos((i+1)*math.pi)
            mesh.quad('linen', [(x0, -.15, z0), (x1, -.15, z1), (x1, ah+.06, z1), (x0, ah+.06, z0)])
    def box(mat, p, size):
        mesh.box(mat, (p[0]*s, floor+p[1]*s, p[2]*s), tuple(v*s for v in size))
    def legs(x, z, width, depth, height):
        for dx in (-1, 1):
            for dz in (-1, 1):
                box('wood', (x+dx*(width*.5-.04), height*.5, z+dz*(depth*.5-.04)), (.055, height, .055))
    def table(x, z, width=1.1, depth=.6, height=.76):
        box('wood', (x, height, z), (width, .06, depth))
        legs(x, z, width-.10, depth-.10, height-.03)
    def chair(x, z):
        box('fabric', (x, .47, z), (.45, .06, .44))
        legs(x, z, .43, .41, .44)
        for dx in (-.19, .19):
            box('wood', (x+dx, .70, z+.19), (.045, .48, .045))
        box('fabric', (x, .87, z+.19), (.43, .16, .055))
    def shelf(x, z, rows=3):
        box('wood', (x, .82, z+.12), (.65, 1.64, .035))
        for dx in (-.33, .33):
            box('wood', (x+dx, .82, z), (.045, 1.64, .28))
        for row in range(rows+1):
            y = .06+row*1.53/rows
            box('wood', (x, y, z), (.66, .035, .28))
            if row < rows:
                for j in range(3):
                    box(('linen', 'rug', 'fabric')[j], (x-.21+j*.16, y+.16, z-.015), (.10, .28+(j%2)*.035, .20))
    layout = room['layout']
    if layout == 'study':
        table(.16, 2.10, 1.4, .67)
        chair(.20, 1.49)
        for i in range(3):
            box(('linen', 'fabric', 'rug')[i], (-.18+i*.015, .81+i*.027, 2.1), (.30, .022, .22))
        shelf(1.18, 3.06, 2)
    elif layout == 'sitting':
        box('wood', (.10, .20, 2.71), (1.78, .24, .72))
        box('fabric', (.10, .75, 3.0), (1.78, .73, .19))
        for x in (-.78, .98):
            box('fabric', (x, .55, 2.70), (.18, .58, .78))
        for x in (-.32, .52):
            box('fabric', (x, .45, 2.65), (.78, .20, .64))
            box('linen', (x, .72, 2.86), (.38, .36, .13))
        legs(.10, 2.71, 1.7, .68, .13)
        table(.10, 1.64, 1.04, .56, .43)
        box('linen', (.13, .49, 1.66), (.23, .035, .18))
    elif layout == 'kitchen':
        box('wood', (.36, .46, 3.04), (2.15, .88, .57))
        box('ceramic', (.36, .92, 3.00), (2.20, .065, .66))
        for x in (-.33, .36, 1.05):
            box('linen', (x, .47, 2.74), (.65, .81, .027))
            box('metal', (x+.22, .72, 2.72), (.10, .025, .02))
            box('wood', (x, 1.89, 3.15), (.64, .70, .34))
        box('metal', (.67, .962, 3.02), (.45, .025, .34))
        table(.20, 1.50, .86, .61)
        chair(.75, 1.22)
    elif layout == 'bedroom':
        box('wood', (.26, .20, 2.14), (1.58, .26, 2.02))
        box('linen', (.26, .42, 2.10), (1.54, .20, 1.96))
        box('fabric', (.26, .55, 1.80), (1.55, .07, 1.35))
        box('wood', (.26, .69, 3.17), (1.64, 1.16, .08))
        for x in (-.14, .63):
            box('linen', (x, .56, 2.76), (.65, .16, .37))
        box('wood', (1.37, .64, 2.83), (.49, 1.25, .70))
        for y in (.27, .65, 1.03):
            box('linen', (1.37, y, 2.47), (.43, .33, .025))
            box('metal', (1.37, y+.06, 2.45), (.14, .025, .025))
    elif layout == 'dining':
        table(.22, 2.13, 1.24, .86)
        chair(-.40, 1.60)
        chair(.75, 2.65)
        box('wood', (1.31, .53, 3.0), (.66, 1.04, .56))
        box('linen', (.20, .802, 2.10), (.49, .024, .37))
        mesh.lathe('ceramic', (.16*s, floor+.82*s, 2.12*s), [(0, .07*s), (.20*s, .045*s)], 8)
    else:
        chair(.38, 2.05)
        table(.90, 1.65, .53, .49, .53)
        shelf(.90, 3.07, 3)
        shelf(-.18, 3.07, 3)
    # A framed print gives a readable scale cue without a photo on the window.
    box('wood', (.0, 2.12, 3.33), (.77, .61, .045))
    box('linen', (.0, 2.12, 3.30), (.66, .50, .018))
    box('fabric', (-.10, 2.13, 3.287), (.19, .28, .008))
    lx, ly, lz = room['lampLocalMeters']
    mesh.box('wood', (lx, floor+.72*s, lz), (.47*s, .055*s, .43*s))
    # Two side panels support the end table, leaving a visible dark recess.
    for sign in (-1, 1):
        mesh.box('wood', (lx+sign*.18*s, floor+.35*s, lz), (.035*s, .70*s, .38*s))
    mesh.lathe('ceramic', (lx, floor+.75*s, lz), [(0, .10*s), (.17*s, .09*s), (.28*s, .035*s)], 8)
    mesh.lathe('metal', (lx, floor+1.02*s, lz), [(0, .014*s), (.31*s, .014*s)], 8)
    # Open shade: never enclose the point light in opaque bulb geometry.
    mesh.lathe('lamp', (lx, ly-.11*s, lz), [(0, .22*s), (.29*s, .12*s)], 12, False)
    return mesh


def write_geometry(rooms, output_path=None, include_glass=False):
    """Export canonical or world-space rooms; two opaque material sections each."""
    rooms = [dict(room) for room in rooms]
    doc = {'asset': {'version': '2.0', 'generator': RECIPE}, 'scene': 0,
           'scenes': [{'nodes': []}], 'nodes': [], 'meshes': [], 'accessors': [], 'bufferViews': [],
           'materials': [{'name': 'OOWRoom_'+name, 'doubleSided': True,
                          'pbrMetallicRoughness': {'baseColorFactor': [1, 1, 1, 1], 'roughnessFactor': .8}}
                         for name in ('surface', 'lamp')]}
    if include_glass:
        doc['materials'].append({'name': 'OOWRoom_glass', 'doubleSided': True, 'alphaMode': 'BLEND',
                                'pbrMetallicRoughness': {'baseColorFactor': [.98, .99, 1, .05], 'roughnessFactor': .16}})
    blob = bytearray()
    def put(values, width, indices=False):
        blob.extend(b'\0'*((-len(blob)) % 4))
        start = len(blob)
        for value in values:
            blob.extend(struct.pack('<'+('I' if indices else 'f')*width, *(value if width > 1 else (value,))))
        view = len(doc['bufferViews'])
        doc['bufferViews'].append({'buffer': 0, 'byteOffset': start, 'byteLength': len(blob)-start,
                                  'target': 34963 if indices else 34962})
        accessor = {'bufferView': view, 'componentType': 5125 if indices else 5126,
                    'count': len(values), 'type': {1: 'SCALAR', 2: 'VEC2', 3: 'VEC3', 4: 'VEC4'}[width]}
        if width == 3:
            accessor.update(min=[min(v[i] for v in values) for i in range(3)], max=[max(v[i] for v in values) for i in range(3)])
        doc['accessors'].append(accessor)
        return len(doc['accessors'])-1
    def add_mesh(name, primitives):
        index = len(doc['meshes'])
        doc['meshes'].append({'name': name, 'primitives': primitives})
        doc['nodes'].append({'name': name, 'mesh': index})
        doc['scenes'][0]['nodes'].append(index)
    for room in rooms:
        mesh, primitives = furnish(room), []
        for slot in ('surface', 'lamp'):
            combined = {key: [] for key in ('positions', 'normals', 'uv', 'uv1', 'colour', 'indices')}
            for name, part in mesh.parts.items():
                if (name == 'lamp') != (slot == 'lamp'):
                    continue
                offset, count = len(combined['positions']), len(part['positions'])
                for key in ('positions', 'normals', 'uv'):
                    combined[key].extend(part[key])
                colour, roughness, _ = MATERIALS[name]
                kind = 1 if name == 'wood' else 2 if name in ('fabric', 'linen', 'rug', 'lamp') else 3 if name == 'metal' else 0
                combined['colour'].extend([(*colour, 1)]*count)
                combined['uv1'].extend([(roughness, kind)]*count)
                combined['indices'].extend(i+offset for i in part['indices'])
            primitives.append({'attributes': {'POSITION': put(combined['positions'], 3), 'NORMAL': put(combined['normals'], 3),
                                'TEXCOORD_0': put(combined['uv'], 2), 'TEXCOORD_1': put(combined['uv1'], 2),
                                'COLOR_0': put(combined['colour'], 4)},
                               'indices': put(combined['indices'], 1, True), 'material': 0 if slot == 'surface' else 1})
        add_mesh(room['name'], primitives)
        room['materialSlots'] = ['surface', 'lamp']
        room['triangles'] = sum(len(part['indices'])//3 for part in mesh.parts.values())
        # UE removes zero-area triangles, including the repeated corner in caps.
        # Count them from coordinates without changing the exported source mesh.
        room['renderTriangles'] = 0
        for part in mesh.parts.values():
            for offset in range(0, len(part['indices']), 3):
                a, b, c = (part['positions'][index] for index in part['indices'][offset:offset+3])
                area = windows.cross(windows.sub(b, a), windows.sub(c, a))
                room['renderTriangles'] += int(any(value != 0 for value in area))
        if include_glass:
            glass_builder = RoomMesh(room)
            aw, ah = room['apertureWidthMeters'], room['apertureHeightMeters']
            glass_builder.quad('glass', [(-aw*.5, 0, -.01), (-aw*.5, ah, -.01), (aw*.5, ah, -.01), (aw*.5, 0, -.01)], [(0, 0, -1)]*4)
            part = glass_builder.parts['glass']
            room['glass'] = {'name': GLASS_PREFIX+room['id']+'_v3', 'triangles': 2, 'offsetMeters': .01}
            add_mesh(room['glass']['name'], [{'attributes': {'POSITION': put(part['positions'], 3), 'NORMAL': put(part['normals'], 3),
                      'TEXCOORD_0': put(part['uv'], 2)}, 'indices': put(part['indices'], 1, True), 'material': 2}])
    blob.extend(b'\0'*((-len(blob)) % 4))
    doc['buffers'] = [{'byteLength': len(blob)}]
    encoded = json.dumps(doc, separators=(',', ':')).encode()
    encoded += b' '*((-len(encoded)) % 4)
    glb = struct.pack('<III', 0x46546C67, 2, 28+len(encoded)+len(blob))
    glb += struct.pack('<II', len(encoded), 0x4E4F534A)+encoded+struct.pack('<II', len(blob), 0x004E4942)+blob
    report = {'recipe': RECIPE, 'rooms': rooms, 'generatedSha256': hashlib.sha256(glb).hexdigest(),
              'totalTriangles': sum(room['triangles'] for room in rooms),
              'totalRenderTriangles': sum(room['renderTriangles'] for room in rooms),
              'glassTriangles': sum(room.get('glass', {}).get('triangles', 0) for room in rooms)}
    if output_path is not None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(glb)
    return report


def generate(root, analysis=None, write=True):
    root = Path(root)
    report = plan(root, analysis)
    output = root/'Migration/Generated/alley-hero-rooms-v3.glb'
    report.update(write_geometry(report['rooms'], output if write else None, True))
    if write:
        (root/'Migration/hero-rooms.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    return output, report


def build_materials(u):
    # Bump RECIPE whenever material construction changes; geometry-only rebuilds
    # can reuse the compiled masters exactly like the surface material builder.
    cached = {name: u.load_asset(MATERIAL_DEST+'/M_HeroRoom_'+name)
              for name in ('surface', 'lamp', 'glass')}
    if all(isinstance(material, u.Material)
           and str(u.EditorAssetLibrary.get_metadata_tag(material, 'OOWRecipe')) == RECIPE
           for material in cached.values()):
        return cached
    from build_desktop_frame import WOOD
    import build_surface_materials as surface
    surface.u, surface.mel = u, u.MaterialEditingLibrary
    mel, output = u.MaterialEditingLibrary, {}
    def clear(material):
        # UE 5.7's delete-all mutates the expression array while traversing it.
        count = mel.get_num_material_expressions(material)
        while count:
            mel.delete_all_material_expressions(material)
            remaining = mel.get_num_material_expressions(material)
            if remaining >= count:
                raise RuntimeError('Material expression cleanup stalled: ' + material.get_path_name())
            count = remaining
    for name in ('surface', 'lamp'):
        asset_name = 'M_HeroRoom_' + name
        material = u.load_asset(MATERIAL_DEST+'/'+asset_name)
        if material is None:
            material = u.AssetToolsHelpers.get_asset_tools().create_asset(asset_name, MATERIAL_DEST, u.Material, u.MaterialFactoryNew())
        if not isinstance(material, u.Material):
            raise RuntimeError('Cannot build hero room material: '+asset_name)
        clear(material)
        material.set_editor_property('blend_mode', u.BlendMode.BLEND_OPAQUE)
        material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_DEFAULT_LIT)
        material.set_editor_property('two_sided', True)
        g, prop = surface.Graph(material), u.MaterialProperty
        uv = g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=0)
        attributes = g.node(u.MaterialExpressionTextureCoordinate, coordinate_index=1)
        colour = g.node(u.MaterialExpressionVertexColor)
        grain = g.custom(WOOD, {'UV': uv}, True, 'Filtered centimetre wood grain')
        albedo = g.custom('float wood=1.-step(.4,abs(A.y-1.)); float cloth=1.-step(.4,abs(A.y-2.)); '
                          'float2 f=1.-smoothstep(.25,.8,fwidth(UV)*2.); '
                          'float weave=(sin(UV.x*6.283)*f.x+sin(UV.y*6.283)*f.y)*.025; '
                          'return C.rgb*(1.+wood*D.x*.35+cloth*weave);',
                          {'C': colour, 'A': attributes, 'D': grain, 'UV': uv}, True)
        normal = g.custom('float wood=1.-step(.4,abs(A.y-1.)); '
                          'return normalize(float3(-D.y*.08*wood,-D.z*.08*wood,1));',
                          {'A': attributes, 'D': grain}, True)
        g.output(albedo, prop.MP_BASE_COLOR)
        g.output(normal, prop.MP_NORMAL)
        g.output(g.custom('return saturate(A.x);', {'A': attributes}), prop.MP_ROUGHNESS)
        g.output(g.custom('return .7*(1.-step(.4,abs(A.y-3.)));', {'A': attributes}), prop.MP_METALLIC)
        if name == 'lamp':
            emission = g.custom('return float3(1.,.67,.34)*1.6*smoothstep(.58,.86,Night)*Occupied;',
                                {'Night': g.scalar('Night', 0), 'Occupied': g.scalar('Occupied', 1)}, True,
                                'Occupied lamp fabric only; surfaces use actual lighting')
            g.output(emission, prop.MP_EMISSIVE_COLOR)
        mel.layout_material_expressions(material)
        mel.recompile_material(material)
        u.EditorAssetLibrary.set_metadata_tag(material, 'OOWRecipe', RECIPE)
        u.EditorAssetLibrary.save_loaded_asset(material)
        output[name] = material
    name = 'M_HeroRoom_glass'
    material = u.load_asset(MATERIAL_DEST+'/'+name)
    if material is None:
        material = u.AssetToolsHelpers.get_asset_tools().create_asset(name, MATERIAL_DEST, u.Material, u.MaterialFactoryNew())
    if not isinstance(material, u.Material):
        raise RuntimeError('Cannot build hero glass material')
    clear(material)
    material.set_editor_property('blend_mode', u.BlendMode.BLEND_TRANSLUCENT)
    material.set_editor_property('shading_model', u.MaterialShadingModel.MSM_THIN_TRANSLUCENT)
    material.set_editor_property('translucency_lighting_mode', u.TranslucencyLightingMode.TLM_SURFACE_PER_PIXEL_LIGHTING)
    material.set_editor_property('two_sided', True)
    material.set_editor_property('use_material_attributes', False)
    g, prop = surface.Graph(material), u.MaterialProperty
    g.output(g.vector((0, 0, 0)), prop.MP_BASE_COLOR)
    g.output(g.constant(0), prop.MP_METALLIC)
    g.output(g.constant(.5), prop.MP_SPECULAR)
    g.output(g.constant(.16), prop.MP_ROUGHNESS)
    g.output(g.constant(0), prop.MP_OPACITY)
    thin = g.node(u.MaterialExpressionThinTranslucentMaterialOutput)
    g.connect(g.vector((.96, .975, .985)), thin, 'TransmittanceColor')
    g.connect(g.constant(1), thin, 'SurfaceCoverage')
    mel.layout_material_expressions(material)
    mel.recompile_material(material)
    u.EditorAssetLibrary.set_metadata_tag(material, 'OOWRecipe', RECIPE)
    u.EditorAssetLibrary.save_loaded_asset(material)
    output['glass'] = material
    return output


def apply(root, analysis=None):
    """Idempotent generated actors only. The caller loads and saves Alley."""
    import unreal as u
    root = Path(root)
    source, report = generate(root, analysis)
    actors = u.get_editor_subsystem(u.EditorActorSubsystem)
    meshes = u.get_editor_subsystem(u.StaticMeshEditorSubsystem) or u.StaticMeshEditorSubsystem()
    existing = {actor.get_actor_label(): actor for actor in actors.get_all_level_actors()}
    materials = build_materials(u)
    lamp_instances = {}
    for occupied in (False, True):
        name = 'MI_HeroRoom_lamp_' + ('on' if occupied else 'off')
        instance = u.load_asset(MATERIAL_DEST+'/'+name)
        if instance is None:
            instance = u.AssetToolsHelpers.get_asset_tools().create_asset(name, MATERIAL_DEST,
                u.MaterialInstanceConstant, u.MaterialInstanceConstantFactoryNew())
        u.MaterialEditingLibrary.set_material_instance_parent(instance, materials['lamp'])
        u.MaterialEditingLibrary.set_material_instance_scalar_parameter_value(instance, 'Occupied', float(occupied))
        u.MaterialEditingLibrary.update_material_instance(instance)
        u.EditorAssetLibrary.set_metadata_tag(instance, 'OOWRecipe', RECIPE)
        u.EditorAssetLibrary.save_loaded_asset(instance)
        lamp_instances[occupied] = instance
    manager = u.InterchangeManager.get_interchange_manager_scripted()
    params = u.ImportAssetParameters()
    params.is_automated, params.replace_existing = True, True
    assets = manager.import_asset(DEST, manager.create_source_data(str(source)), params)
    imported = {asset.get_name(): asset for asset in (assets or []) if isinstance(asset, u.StaticMesh)}
    expected = {entry['name'] for room in report['rooms'] for entry in (room, room['glass'])}
    if set(imported) != expected:
        raise RuntimeError('Expected fifteen room and fifteen glass meshes: ' + str(sorted(imported)))
    for room in report['rooms']:
        for part, expected_triangles in ((room, room['renderTriangles']), (room['glass'], 2)):
            actual_triangles = imported[part['name']].get_num_triangles(0)
            if actual_triangles != expected_triangles:
                raise RuntimeError('Imported hero triangle count differs: %s (%d != %d)' %
                                   (part['name'], actual_triangles, expected_triangles))
    wanted = expected | {room['light']['name'] for room in report['rooms'] if room['light']}
    for name, actor in existing.items():
        if name.startswith((PREFIX, GLASS_PREFIX, LIGHT_PREFIX)) and name not in wanted:
            actors.destroy_actor(actor)
    for room in report['rooms']:
        mesh = imported[room['name']]
        slots = mesh.get_editor_property('static_materials')
        if len(slots) != len(room['materialSlots']):
            raise RuntimeError('Hero room material slot count changed: ' + room['name'])
        for index, name in enumerate(room['materialSlots']):
            mesh.set_material(index, materials[name])
        nanite = mesh.get_editor_property('nanite_settings')
        nanite.enabled = False
        meshes.set_nanite_settings(mesh, nanite, True)
        build = meshes.get_lod_build_settings(mesh, 0)
        build.set_editor_property('generate_lightmap_u_vs', False)
        build.set_editor_property('use_full_precision_u_vs', True)
        meshes.set_lod_build_settings(mesh, 0, build)
        u.EditorAssetLibrary.set_metadata_tag(mesh, 'OOWRecipe', RECIPE)
        u.EditorAssetLibrary.set_metadata_tag(mesh, 'OOWRoomGeometry', report['generatedSha256'])
        u.EditorAssetLibrary.save_loaded_asset(mesh)
        actor = existing.get(room['name']) or actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector())
        if not isinstance(actor, u.StaticMeshActor):
            raise RuntimeError('Reserved hero actor name has wrong class: ' + room['name'])
        actor.set_actor_label(room['name'])
        actor.set_actor_transform(u.Transform(), False, True)
        actor.tags = ['OOWGeometry', 'OOWHeroRoom', 'OOWRoom_'+room['id']]
        comp = actor.static_mesh_component
        comp.set_static_mesh(mesh)
        for index, name in enumerate(room['materialSlots']):
            comp.set_material(index, lamp_instances[room['occupied']] if name == 'lamp' else materials[name])
        comp.set_mobility(u.ComponentMobility.STATIC)
        comp.set_editor_property('cast_shadow', True)
        comp.set_editor_property('visible_in_ray_tracing', True)
        comp.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        light = room['light']
        if light:
            lamp = existing.get(light['name']) or actors.spawn_actor_from_class(u.PointLight, u.Vector(*light['positionCm']))
            if not isinstance(lamp, u.PointLight):
                raise RuntimeError('Reserved hero lamp name has wrong class: ' + light['name'])
            lamp.set_actor_label(light['name'])
            lamp.set_actor_location(u.Vector(*light['positionCm']), False, False)
            lamp.tags = light['tags']
            component = lamp.get_component_by_class(u.PointLightComponent)
            component.set_mobility(u.ComponentMobility.MOVABLE)
            component.set_editor_property('intensity_units', u.LightUnits.LUMENS)
            component.set_intensity(light['lumens'])
            component.set_attenuation_radius(light['radiusCm'])
            component.set_editor_property('source_radius', light['sourceRadiusCm'])
            component.set_editor_property('use_temperature', True)
            component.set_temperature(light['temperatureKelvin'])
            component.set_cast_shadows(True)
            component.set_volumetric_scattering_intensity(0)
        room['unrealMesh'] = mesh.get_path_name()
        glass = room['glass']
        glass_mesh = imported[glass['name']]
        glass_mesh.set_material(0, materials['glass'])
        nanite = glass_mesh.get_editor_property('nanite_settings')
        nanite.enabled = False
        meshes.set_nanite_settings(glass_mesh, nanite, True)
        u.EditorAssetLibrary.set_metadata_tag(glass_mesh, 'OOWRecipe', RECIPE)
        u.EditorAssetLibrary.set_metadata_tag(glass_mesh, 'OOWRoomGeometry', report['generatedSha256'])
        u.EditorAssetLibrary.save_loaded_asset(glass_mesh)
        front = existing.get(glass['name']) or actors.spawn_actor_from_class(u.StaticMeshActor, u.Vector())
        if not isinstance(front, u.StaticMeshActor):
            raise RuntimeError('Reserved hero glass actor name has wrong class: ' + glass['name'])
        front.set_actor_label(glass['name'])
        front.set_actor_transform(u.Transform(), False, True)
        front.tags = ['OOWGeometry', 'OOWHeroRoom', 'OOWHeroGlass', 'OOWRoom_'+room['id']]
        comp = front.static_mesh_component
        comp.set_static_mesh(glass_mesh)
        comp.set_material(0, materials['glass'])
        comp.set_mobility(u.ComponentMobility.STATIC)
        comp.set_editor_property('cast_shadow', False)
        comp.set_editor_property('visible_in_ray_tracing', True)
        comp.set_collision_enabled(u.CollisionEnabled.NO_COLLISION)
        glass['unrealMesh'] = glass_mesh.get_path_name()
    report['appliedToUnreal'] = True
    (root/'Migration/hero-rooms.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    u.log('OOW_HERO_ROOMS_COMPLETE '+json.dumps({'rooms': len(report['rooms']), 'triangles': report['totalTriangles']}))
    return report


def self_test():
    root = Path(__file__).resolve().parent.parent
    analysis = windows.analyze(root)
    _, report = generate(root, analysis, False)
    _, again = generate(root, analysis, False)
    assert report == again
    assert len(report['rooms']) == 15 and report['totalTriangles'] < 18000
    assert report['glassTriangles'] == 30
    assert {r['sourceRoomId'] for r in report['rooms']} == set(HERO_ROOM_IDS)
    assert {r['id'] for r in report['rooms'] if r['light']} == LIT_ROOM_IDS
    assert sum(bool(r['light']) for r in report['rooms']) == 8
    for room in report['rooms']:
        mesh = furnish(room)
        if room['light']:
            assert room['light']['tags'][:2] == ['OOWNightLight', 'OOWInteriorLight']
        assert bool(room['light']) == room['occupied']
        assert .1 < room['lampLocalMeters'][2] < room['depthMeters']
        assert room['materialSlots'] == ['surface', 'lamp']
        assert 500 <= room['triangles'] <= 1200
        for part in mesh.parts.values():
            assert len(part['positions']) == len(part['normals']) == len(part['uv'])
            assert all(math.isfinite(v) for point in part['positions'] for v in point)
            assert all(abs(windows.length(n)-1) < 1e-5 for n in part['normals'])
            assert min(windows.dot(windows.sub(point, room['originMeters']), room['inward'])
                       for point in part['positions']) >= -.001, 'Geometry protrudes outside the original pane'
            assert max(abs(windows.dot(windows.sub(point, room['originMeters']), room['right']))
                       for point in part['positions']) <= room['widthMeters']*.5+.081, 'Furniture or curtain crosses room side shell'
        for identity in room.get('neighbourConstraints', []):
            neighbour = next(r for r in report['rooms'] if r['id'] == identity)
            separation = abs(windows.dot(windows.sub(neighbour['originMeters'], room['originMeters']), room['right']))
            assert (room['widthMeters']+neighbour['widthMeters'])*.5+.16 < separation-.03, 'Adjacent room shells overlap'
    for identity in windows.HERO_SPLIT_ROOM_IDS:
        left, right = [r for r in report['rooms'] if r['sourceRoomId'] == identity]
        assert abs(left['apertureSourceBounds'][1]-right['apertureSourceBounds'][0]) < 1e-5
        assert abs(left['apertureWidthMeters']-4.4404819931) < 1e-4
    templates = [template_room(i) for i in range(6)]
    template_report = write_geometry(templates)
    assert len({r['triangles'] for r in template_report['rooms']}) == 6
    for room in templates:
        assert room['imBoxMin'] == [-1.8, -.45, 0] and room['imBoxMax'] == [1.8, 3.05, 3.4]
        assert room['floorMeters']+room['heightMeters'] == 3.05
    print(json.dumps({'recipe': RECIPE, 'rooms': len(report['rooms']), 'triangles': report['totalTriangles'],
                      'renderTriangles': report['totalRenderTriangles'],
                      'sha256': report['generatedSha256'], 'selfTest': 'passed'}))


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        self_test()
    elif '--generate-only' in sys.argv:
        print(json.dumps(generate(Path(__file__).resolve().parent.parent)[1], indent=2))
    else:
        import unreal as u
        if not u.get_editor_subsystem(u.LevelEditorSubsystem).load_level('/Game/Maps/Alley'):
            raise RuntimeError('Cannot load Alley')
        apply(Path(u.Paths.project_dir()).parent)
        u.get_editor_subsystem(u.LevelEditorSubsystem).save_current_level()
