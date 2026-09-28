"""Deterministic slate-course relief for the two matching Bistro hip roofs.

All clipping planes are shared in world space. Displacement is confined to one
tile width around the hip; independent UV charts and authored normal seams stay
independent. This is an offline mesh operation, not a runtime material effect.
"""
import bisect
import math
import struct

from build_window_interiors import sub, cross, dot, unit, length

RECIPE = 'roof-source-geometry-v2-slate-relief'
SEAM_ROWS = (21, 107, 192, 277, 363, 448, 533, 619, 703, 791, 875, 959)
WIDTH = .46
LIP = .009
INSET = .027


def _mix(a, b, t):
    return tuple(x+(y-x)*t for x, y in zip(a, b))


def _smooth(x):
    x = min(1., max(0., x))
    return x*x*(3.-2.*x)


def _edge_counts(points, triangles):
    keys = [tuple(round(x, 5) for x in point) for point in points]
    edges = {}
    for start in range(0, len(triangles), 3):
        ids = triangles[start:start+3]
        for a, b in zip(ids, ids[1:]+ids[:1]):
            edge = tuple(sorted((keys[a], keys[b])))
            if edge[0] != edge[1]: edges[edge] = edges.get(edge, 0)+1
    return edges


def _unexpected_boundaries(original_edges, new_edges):
    originals = [edge for edge, count in original_edges.items() if count == 1]
    def on_old_boundary(point):
        for a, b in originals:
            edge = sub(b, a); t = dot(sub(point, a), edge)/dot(edge, edge)
            if -.00001 <= t <= 1.00001 and length(sub(point, _mix(a, b, min(1., max(0., t))))) < .00005:
                return True
        return False
    return [edge for edge, count in new_edges.items() if count == 1 and not all(on_old_boundary(p) for p in edge)]


def audit_float32(local_points, indices, matrix, source_points, source_indices):
    """Check encoded float32 data again after UE's float32 m-to-cm conversion."""
    def f32(value): return struct.unpack('<f', struct.pack('<f', value))[0]
    ue_cm = [tuple(f32(value*100.) for value in point) for point in local_points]
    world = [tuple(point[k]/100.*matrix[k*5]+matrix[12+k] for k in range(3)) for point in ue_cm]
    minimum_edge, minimum_area, degenerates = math.inf, math.inf, 0
    for start in range(0, len(indices), 3):
        a, b, c = [ue_cm[i] for i in indices[start:start+3]]
        pairs = ((a, b), (b, c), (c, a))
        minimum_edge = min(minimum_edge, *(length(sub(x, y)) for x, y in pairs))
        area = length(cross(sub(b, a), sub(c, a)))*.5
        minimum_area = min(minimum_area, area)
        if area == 0. or any(all(abs(x[k]-y[k]) <= .00002 for k in range(3)) for x, y in pairs):
            degenerates += 1
    old_edges, new_edges = _edge_counts(source_points, source_indices), _edge_counts(world, indices)
    unexpected = _unexpected_boundaries(old_edges, new_edges)
    report = {'input': 'Encoded GLB float32 positions after UE float32 centimeter conversion',
              'triangles': len(indices)//3, 'minimumEdgeUnrealLocalCm': minimum_edge,
              'minimumTriangleAreaUnrealLocalCm2': minimum_area, 'unrealPointEqualityThresholdCm': .00002,
              'degenerateTriangles': degenerates, 'unexpectedBoundaryEdges': len(unexpected),
              'nonManifoldEdges': sum(count > 2 for count in new_edges.values())}
    assert degenerates == 0, 'Encoded GLB has UE-degenerate triangles: %s' % report
    assert not unexpected, 'Encoded GLB has unmatched shared edges: %s' % report
    assert report['nonManifoldEdges'] == 0
    return report


def add_relief(points, normals, uvs, indices):
    # The source pair has identical vertex topology. 5--7 and 44--43 bound
    # the existing 15.5cm hip bevel; the other slope repeats 44/43 as 50/0.
    assert length(sub(points[44], points[50])) < 1e-8
    assert length(sub(points[43], points[0])) < 1e-8
    top, bottom = _mix(points[5], points[44], .5), _mix(points[7], points[43], .5)
    edge = sub(bottom, top)
    edge_length, along = length(edge), unit(edge)
    face_normal = unit(cross(sub(points[5], points[4]), sub(points[6], points[4])))
    across = unit(cross(along, face_normal))
    if dot(across, sub(points[6], points[7])) < 0:
        across = tuple(-x for x in across)
    # UV-v as an affine world-space field from source triangle 3. It continues
    # across the bevel/other slope without depending on their separate charts.
    origin = points[5]
    a, b = sub(points[7], origin), sub(points[6], origin)
    aa, ab, bb = dot(a, a), dot(a, b), dot(b, b)
    va, vb = uvs[7][1]-uvs[5][1], uvs[6][1]-uvs[5][1]
    av, bv = (va*bb-vb*ab)/(aa*bb-ab*ab), (vb*aa-va*ab)/(aa*bb-ab*ab)
    gradient = tuple(av*x+bv*y for x, y in zip(a, b))
    def course_v(point): return uvs[5][1]+dot(sub(point, origin), gradient)
    def cross_distance(point): return dot(sub(point, top), across)
    low, high = sorted((uvs[5][1], uvs[7][1]))
    seams = sorted(repeat+y/1024 for repeat in range(math.floor(low)-1, math.ceil(high)+1) for y in SEAM_ROWS)
    # Low-frequency course variation, with deterministic bounded amplitude.
    def inset(row):
        value = (row*1664525+1013904223) & 0xffffffff
        value = ((value ^ (value >> 16))*2246822519) & 0xffffffff
        return INSET * (2.*(value & 0xffff)/65535.-1.)
    guard = WIDTH/edge_length+.02

    def displacement(point):
        relative = sub(point, top)
        t = dot(relative, along)/edge_length
        perpendicular = tuple(relative[k]-along[k]*t*edge_length for k in range(3))
        radius = length(perpendicular)
        if radius >= WIDTH or t <= guard or t >= 1.-guard: return (0., 0., 0.)
        weight = (1.-_smooth(radius/WIDTH))*_smooth((t-guard)/.04)*_smooth((1.-guard-t)/.04)
        v = course_v(point)
        row = max(0, min(len(seams)-2, bisect.bisect_right(seams, v)-1))
        phase = (v-seams[row])/(seams[row+1]-seams[row])
        transition = min(1., max(0., (phase-.92)/.08))
        lateral = inset(row)*(1.-transition)+inset(row+1)*transition
        # A thin slate overlap ramps up then drops at the measured dark seam.
        height = LIP * (phase/.92 if phase <= .92 else (1.-phase)/.08)
        return tuple(weight*(across[k]*lateral+face_normal[k]*height) for k in range(3))

    def displaced(point):
        delta = displacement(point)
        return tuple(point[k]+delta[k] for k in range(3))

    # Split every intersected source triangle with the same planes. This also
    # keeps zero-displacement neighbours conforming, without T-shaped seams.
    cuts = []
    for i in range(len(seams)-1):
        for phase in (0., .46, .92):
            value = seams[i]+(seams[i+1]-seams[i])*phase
            if low < value < high: cuts.append((course_v, value))
    cuts += [(cross_distance, value) for value in (-WIDTH, -.3, -.155, 0., .155, .3, WIDTH)]

    def split(poly, field, value):
        distances = [field(vertex[0])-value for vertex in poly]
        if min(distances) >= -1e-10 or max(distances) <= 1e-10: return [poly]
        left, right = [], []
        for i, vertex in enumerate(poly):
            next_vertex, a, b = poly[(i+1) % len(poly)], distances[i], distances[(i+1) % len(poly)]
            if a <= 1e-10: left.append(vertex)
            if a >= -1e-10: right.append(vertex)
            if a*b < 0. and abs(a) > 1e-10 and abs(b) > 1e-10:
                t = a/(a-b)
                intersection = tuple(_mix(x, y, t) for x, y in zip(vertex, next_vertex))
                left.append(intersection); right.append(intersection)
        return [poly for poly in (left, right) if len(poly) >= 3]

    out_points, out_normals, out_uvs, out_indices, source_points, normal_groups = [], [], [], [], [], []
    lookup, displaced_cache, affected_faces = {}, {}, set()
    def vertex_id(vertex):
        point, normal, uv = vertex
        # Coincident source positions share exactly the same final world point,
        # while normals/UVs still remain split at the original hard seams.
        position_key = tuple(round(x, 9) for x in point)
        point = position_key
        key = (position_key, tuple(round(x, 7) for x in normal), tuple(round(x, 8) for x in uv))
        if key not in lookup:
            if position_key not in displaced_cache: displaced_cache[position_key] = displaced(point)
            lookup[key] = len(out_points)
            out_points.append(displaced_cache[position_key]); source_points.append(point)
            out_normals.append(unit(normal)); out_uvs.append(uv)
            normal_groups.append((position_key, tuple(round(x, 6) for x in unit(normal))))
        return lookup[key]

    for start in range(0, len(indices), 3):
        ids = indices[start:start+3]
        polygons = [[(points[i], normals[i], uvs[i]) for i in ids]]
        for field, value in cuts:
            polygons = [piece for poly in polygons for piece in split(poly, field, value)]
        for poly in polygons:
            vertices = [vertex_id(vertex) for vertex in poly]
            if any(length(sub(out_points[i], source_points[i])) > 1e-7 for i in vertices):
                affected_faces.add(start//3)
            for i in range(1, len(vertices)-1):
                tri = (vertices[0], vertices[i], vertices[i+1])
                a, b, c = [out_points[j] for j in tri]
                if length(cross(sub(b, a), sub(c, a))) > 1e-9:
                    out_indices.extend(tri)

    # Recalculate displaced vertices from the actual final triangles. Original
    # normal groups keep the hip hard; UV seams alone do not create a new crease.
    offsets = [length(sub(a, b)) for a, b in zip(out_points, source_points)]
    normal_sums, reversed_triangles = {}, 0
    for start in range(0, len(out_indices), 3):
        ids = out_indices[start:start+3]
        a, b, c = [out_points[i] for i in ids]
        sa, sb, sc = [source_points[i] for i in ids]
        face = cross(sub(b, a), sub(c, a))
        if dot(face, cross(sub(sb, sa), sub(sc, sa))) <= 0.: reversed_triangles += 1
        for i in ids:
            key = normal_groups[i]
            old = normal_sums.get(key, (0., 0., 0.))
            normal_sums[key] = tuple(x+y for x, y in zip(old, face))
    for i in range(len(out_normals)):
        if offsets[i] > 1e-7 and normal_groups[i] in normal_sums:
            out_normals[i] = unit(normal_sums[normal_groups[i]])
    original_edges, new_edges = _edge_counts(points, indices), _edge_counts(out_points, out_indices)
    old_boundary = sum(count == 1 for count in original_edges.values())
    new_boundary = sum(count == 1 for count in new_edges.values())
    old_nonmanifold = sum(count > 2 for count in original_edges.values())
    new_nonmanifold = sum(count > 2 for count in new_edges.values())
    # An open source edge may legitimately split into more boundary segments.
    # Every new boundary must still lie on one unchanged original open edge.
    unexpected = _unexpected_boundaries(original_edges, new_edges)
    report = {'recipe': RECIPE, 'courseSeamRowsPixels': list(SEAM_ROWS),
              'sourceTriangles': len(indices)//3, 'generatedTriangles': len(out_indices)//3,
              'generatedVertices': len(out_points), 'displacedVertices': sum(value > 1e-7 for value in offsets),
              'displacedSourceTriangles': sorted(affected_faces),
              'maxDisplacementMeters': max(offsets), 'maxCourseInsetOutsetMeters': INSET,
              'slateLipMeters': LIP, 'bandWidthMeters': WIDTH,
              'sourceBoundaryEdges': old_boundary, 'generatedBoundaryEdges': new_boundary,
              'sourceNonManifoldEdges': old_nonmanifold, 'generatedNonManifoldEdges': new_nonmanifold,
              'unexpectedBoundaryEdges': len(unexpected),
              'reversedTriangles': reversed_triangles,
              'sharedWorldEdgePositions': True, 'normalPolicy': 'Area-weighted final geometry normals on displaced vertices, grouped by original split normals; original normals elsewhere',
              'uvPolicy': 'Barycentric interpolation within each original UV chart; no re-unwrap'}
    assert report['maxDisplacementMeters'] < .05
    assert affected_faces <= {3, 30, 31, 50, 51, 59}
    assert not unexpected, 'Slate relief introduced %d unmatched edges' % len(unexpected)
    assert new_nonmanifold <= old_nonmanifold
    assert reversed_triangles == 0
    return out_points, out_normals, out_uvs, out_indices, report
