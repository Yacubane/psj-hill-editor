from lib.inkex import bezier
import math


def get_psjhill_attrib(node, attrib, raise_if_none=False):
    key = "{http://www.cyfrogen.com/psj/develop/namespaces/psjhill}" + attrib
    if key in node.attrib:
        return node.attrib[key]
    if raise_if_none:
        raise Exception('Missing key: ', key)
    return None


def xpath(document, xpath):
    return document.xpath(xpath, namespaces={
        'psjhill': 'http://www.cyfrogen.com/psj/develop/namespaces/psjhill',
    })


def getbez(sp1, sp2):
    bez = (sp1[1][:], sp1[2][:], sp2[0][:], sp2[1][:])
    return bez


def csp_sub_length(csp_sub):
    length = 0
    i = 1
    while i <= len(csp_sub) - 1:
        length += bezier.cspseglength(csp_sub[i-1], csp_sub[i])
        i += 1

    return length


def csp_sub_points_dst(csp_sub, point_dst, add_last=False, debug=False):
    """ Gets sub curves (one path, maybe with multiple cubic bezier fragments)
    and creates point every point_dst distance. It also creates points in
    bezier curve nodes.
    """
    # csp_sub = [(a,bezier,b)...]
    points = []
    i = 1
    while i <= len(csp_sub) - 1:
        point_length = 0
        # length = bezier.cspseglength(csp_sub[i-1], csp_sub[i])
        dst_to_next_point = point_dst
        bez = getbez(csp_sub[i-1], csp_sub[i])
        length = bezier.bezierlength(bez)
        length_left = length

        start_point = bezier.bezierpointatt(bez, 0)
        end_point = bezier.bezierpointatt(bez, 1)
        point_to_point_dst = point_point_dst(start_point, end_point)

        difference = abs(point_to_point_dst - length)
        points.append(bezier.bezierpointatt(bez, 0))

        if difference > 0.01:
            while dst_to_next_point < length_left:
                length_left -= dst_to_next_point
                point_length += dst_to_next_point

                time = bezier.beziertatlength(bez, point_length/length)
                dst_to_next_point = point_dst
                if time > 0.0001 and time < 0.9999:
                    point = bezier.bezierpointatt(bez, time)
                    points.append(point)

            dst_to_next_point -= length_left
        i = i+1

        if add_last and i == len(csp_sub):
            points.append(bezier.bezierpointatt(bez, 1))

    return points


def csp_sub_points_nodes_between(csp_sub, nodes_between, add_last=False):
    """ Gets sub curves (one path, maybe with multiple cubic bezier fragments)
    and creates point every point_dst distance. It also creates points in
    bezier curve nodes.
    """
    # csp_sub = [(a,bezier,b)...]
    points = []
    i = 1
    while i <= len(csp_sub) - 1:
        bez = getbez(csp_sub[i-1], csp_sub[i])

        points.append(bezier.bezierpointatt(bez, 0))
        for node in range(nodes_between):
            percentage = (node+1) / (nodes_between+1)
            time = bezier.beziertatlength(bez, percentage)
            point = bezier.bezierpointatt(bez, time)
            points.append(point)

        i = i+1

        if add_last and i == len(csp_sub):
            points.append(bezier.bezierpointatt(bez, 1))

    return points


def generate_polygon_vertices_dst(node, point_dst, add_last=False, debug=False):
    """ Gets Inkscape PathElement node and creates points every point_dst distance
    """
    points = []
    for sub in node.path.to_superpath():
        points = csp_sub_points_dst(sub, point_dst, add_last, debug=debug)
        return points


def generate_polygon_vertices_nodes_between(node, nodes_between, add_last=False):
    """ Gets Inkscape PathElement node and creates nodes_between points between every curve
    """
    points = []
    for sub in node.path.to_superpath():
        points = csp_sub_points_nodes_between(sub, nodes_between, add_last)
        return points


def absolute_points(node, vertices):
    vertices = [node.composed_transform().apply_to_point(point)
                 for point in vertices]
    return [[point[0], point[1]] for point in vertices]


def get_absolute_bounding_box(node):
    tran = node.getparent().composed_transform()
    return node.bounding_box(tran)


def ensure_right_pointing_vertices(vertices):
    if(vertices[1][0] > vertices[0][0]):
        return vertices
    else:
        return vertices[::-1]


def point_point_dst(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1])**2)


def calc_vertices_path_size(vertices):
    first = None
    distance = 0
    for vertex in vertices:
        if first is not None:
            distance += math.sqrt((first[0] - vertex[0])
                                  ** 2 + (first[1] - vertex[1])**2)
        first = vertex
    return distance


def intersect_segments(p1, p2, p3, p4):
    x1 = p1[0]
    y1 = p1[1]
    x2 = p2[0]
    y2 = p2[1]
    x3 = p3[0]
    y3 = p3[1]
    x4 = p4[0]
    y4 = p4[1]

    d = (y4 - y3) * (x2 - x1) - (x4 - x3) * (y2 - y1)

    if (d == 0):
        return None

    yd = y1 - y3
    xd = x1 - x3
    ua = ((x4 - x3) * yd - (y4 - y3) * xd) / d
    if ua < 0 or ua > 1:
        return None

    ub = ((x2 - x1) * yd - (y2 - y1) * xd) / d
    if ub < 0 or ub > 1:
        return None

    return [x1 + (x2 - x1) * ua, y1 + (y2 - y1) * ua]


def nearest_segment_point(start, end, point):
    length2 = (start[0] - end[0]) ** 2 + (start[1] - end[1])**2
    if (length2 == 0):
        return start
    t = ((point[0] - start[0]) * (end[0] - start[0]) +
         (point[1] - start[1]) * (end[1] - start[1])) / length2
    if (t < 0):
        return start
    if (t > 1):
        return end
    return [start.x + t * (end.x - start.x), start.y + t * (end.y - start.y)]
