"""Extract reusable boulevard props from the already licensed Bistro source.

No UE dependency and no downloads. Run with Python; --self-test verifies the
generated geometry, metre scale, local pivot, texture references and leaf mask.
"""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import struct
import sys

from build_window_interiors import read_accessor, read_glb

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'public/assets/orca/bistro'
DEST = ROOT / 'unreal/Art/City'
RECIPE = 'bistro-city-props-v1'


def prepare(name, selected, height, document, blob, green_canopy=False):
    primitives = [copy.deepcopy(p) for mesh in selected for p in document['meshes'][mesh]['primitives']]
    positions = [p for primitive in primitives
                 for p in read_accessor(document, blob, primitive['attributes']['POSITION'])[1]]
    bottom, top = min(p[1] for p in positions), max(p[1] for p in positions)
    # Center on the foot/trunk, rather than an asymmetric crown or lamp head.
    foot = [p for p in positions if p[1] < bottom + (top-bottom)*.015]
    pivot = [(min(p[k] for p in foot)+max(p[k] for p in foot))*.5 for k in range(3)]
    pivot[1] = bottom
    scale = height/(top-bottom)
    groups = {}
    green = next(i for i, m in enumerate(document['materials'])
                 if m['name'] == 'Foliage_Linde_Tree_Large_Green_Leaves')
    for primitive in primitives:
        material = primitive['material']
        if green_canopy and 'Leaves' in document['materials'][material]['name']:
            material = green
        groups.setdefault(material, []).append(primitive)

    out = {'asset': {'version': '2.0', 'generator': RECIPE,
                     'copyright': 'Amazon Lumberyard Bistro (2017), NVIDIA ORCA, CC BY 4.0; modified by OutOfWindow'},
           'scene': 0, 'scenes': [{'nodes': [0]}],
           'nodes': [{'name': name, 'mesh': 0}],
           'meshes': [{'name': name, 'primitives': []}],
           'materials': [], 'textures': [], 'images': [],
           'samplers': copy.deepcopy(document.get('samplers', [])),
           'accessors': [], 'bufferViews': [], 'buffers': []}
    data = bytearray()
    texture_map = {}
    triangles = 0
    bounds = [[float('inf')]*3, [-float('inf')]*3]

    def texture(index):
        if index in texture_map:
            return texture_map[index]
        tex = copy.deepcopy(document['textures'][index])
        image = document['images'][tex['source']]
        filename = Path(image['uri']).name
        assert image['uri'] == filename, 'Expected a local source texture'
        (DEST / 'textures').mkdir(exist_ok=True)
        shutil.copyfile(SOURCE / filename, DEST / 'textures' / filename)
        tex['source'] = len(out['images'])
        out['images'].append({'name': Path(filename).stem, 'uri': 'textures/' + filename})
        new_index = len(out['textures'])
        out['textures'].append(tex)
        texture_map[index] = new_index
        return new_index

    def put(values, kind, component, target):
        data.extend(b'\0' * (-len(data) % 4))
        fmt = '<' + ('I' if component == 5125 else 'f') * len(values[0])
        raw = b''.join(struct.pack(fmt, *v) for v in values)
        view = len(out['bufferViews'])
        out['bufferViews'].append({'buffer': 0, 'byteOffset': len(data), 'byteLength': len(raw), 'target': target})
        data.extend(raw)
        accessor = {'bufferView': view, 'componentType': component, 'count': len(values), 'type': kind}
        if kind == 'VEC3':
            accessor.update(min=[min(p[k] for p in values) for k in range(3)],
                            max=[max(p[k] for p in values) for k in range(3)])
        out['accessors'].append(accessor)
        return len(out['accessors'])-1

    for material_id, source_primitives in groups.items():
        material = copy.deepcopy(document['materials'][material_id])
        material['name'] = 'City_' + material['name']
        pbr = material['pbrMetallicRoughness']
        for key in ('baseColorTexture', 'metallicRoughnessTexture'):
            if key in pbr:
                pbr[key]['index'] = texture(pbr[key]['index'])
        if 'Leaves' in material['name']:
            material.pop('normalTexture', None)  # Source normal is a 90-byte flat placeholder.
        for key in ('normalTexture', 'occlusionTexture', 'emissiveTexture'):
            if key in material:
                material[key]['index'] = texture(material[key]['index'])
        if 'Leaves' in material['name']:
            material.update(alphaMode='MASK', alphaCutoff=.35, doubleSided=True)
            pbr.update(baseColorFactor=[.70, .92, .57, 1], roughnessFactor=.85)
        out['materials'].append(material)
        attributes = set.intersection(*(set(p['attributes']) for p in source_primitives))
        assert {'POSITION', 'NORMAL', 'TEXCOORD_0'} <= attributes
        values = {semantic: [] for semantic in sorted(attributes)}
        indices = []
        for source in source_primitives:
            offset = len(values['POSITION'])
            for semantic in values:
                current = read_accessor(document, blob, source['attributes'][semantic])[1]
                if semantic == 'POSITION':
                    current = [tuple((v[k]-pivot[k])*scale for k in range(3)) for v in current]
                    for p in current:
                        for k in range(3):
                            bounds[0][k], bounds[1][k] = min(bounds[0][k], p[k]), max(bounds[1][k], p[k])
                values[semantic].extend(current)
            indices.extend((v[0]+offset,) for v in read_accessor(document, blob, source['indices'])[1])
        triangles += len(indices)//3
        primitive = {'attributes': {}, 'material': len(out['materials'])-1, 'mode': 4}
        for semantic, data_values in values.items():
            primitive['attributes'][semantic] = put(data_values, 'VEC' + str(len(data_values[0])), 5126, 34962)
        primitive['indices'] = put(indices, 'SCALAR', 5125, 34963)
        out['meshes'][0]['primitives'].append(primitive)

    data.extend(b'\0' * (-len(data) % 4))
    out['buffers'] = [{'byteLength': len(data)}]
    header = json.dumps(out, separators=(',', ':')).encode()
    header += b' ' * (-len(header) % 4)
    glb = (struct.pack('<III', 0x46546C67, 2, 28+len(header)+len(data))
           + struct.pack('<II', len(header), 0x4E4F534A) + header
           + struct.pack('<II', len(data), 0x004E4942) + data)
    (DEST / (name + '.glb')).write_bytes(glb)
    return {'file': name + '.glb', 'sourceMeshIndices': selected, 'triangles': triangles,
            'sections': len(groups), 'heightMeters': height, 'boundsMeters': bounds,
            'pivot': 'trunk/foot center at ground; Y up; metres', 'sourcePivot': pivot,
            'sourceUniformScale': scale, 'bytes': len(glb), 'sha256': hashlib.sha256(glb).hexdigest(),
            'textures': [image['uri'] for image in out['images']]}


def verify(records):
    for record in records:
        doc, blob = read_glb(DEST / record['file'])
        total = 0
        for p in doc['meshes'][0]['primitives']:
            positions = read_accessor(doc, blob, p['attributes']['POSITION'])[1]
            indices = [v[0] for v in read_accessor(doc, blob, p['indices'])[1]]
            assert len(indices) % 3 == 0 and 0 <= min(indices) <= max(indices) < len(positions)
            assert min(v[1] for v in positions) >= -.00001
            assert max(v[1] for v in positions) <= record['heightMeters'] + .00001
            total += len(indices)//3
        assert total == record['triangles']
        assert all((DEST / image['uri']).is_file() for image in doc['images'])
        for material in doc['materials']:
            if 'Leaves' in material['name']:
                assert material['alphaMode'] == 'MASK' and material['doubleSided']
                assert 'Green' in material['name']
    print('City props verified:', ', '.join('%s (%s triangles)' % (r['file'], r['triangles']) for r in records))


if __name__ == '__main__':
    manifest = DEST / 'asset-manifest.json'
    if '--self-test' in sys.argv:
        verify(json.loads(manifest.read_text())['assets'])
    else:
        DEST.mkdir(parents=True, exist_ok=True)
        document = json.loads((SOURCE / 'bistro-exterior.gltf').read_text())
        blob = (SOURCE / document['buffers'][0]['uri']).read_bytes()
        records = [prepare('OOW_City_Linden', [972], 11., document, blob, green_canopy=True)]
        manifest.write_text(json.dumps({'recipe': RECIPE, 'license': 'CC BY 4.0',
            'source': 'https://developer.nvidia.com/orca/amazon-lumberyard-bistro',
            'credit': 'Amazon Lumberyard Bistro (2017), Open Research Content Archive (ORCA). Modified by OutOfWindow.',
            'coordinateSystem': 'glTF Y-up metres; UE importer converts to Z-up centimetres once',
            'assets': records}, indent=2) + '\n')
        verify(records)
