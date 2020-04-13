import pyclipper


def clip_polygon(vertices, bounding_box, grid_size, optimize=True):
    SCALING_FACTOR = 2 ** 31
    output = []

    points = [(verticle[0], verticle[1]) for verticle in vertices]

    bounding_box_x = bounding_box.left
    while bounding_box_x < bounding_box.left + bounding_box.width:
        bounding_box_x2 = min(
            bounding_box_x+grid_size, bounding_box.left + bounding_box.width)
        bounding_box_y = bounding_box.top
        while bounding_box_y < bounding_box.top + bounding_box.height:
            bounding_box_y2 = min(
                bounding_box_y+grid_size, bounding_box.top + bounding_box.height)

            clip = ((bounding_box_x, bounding_box_y),
                    (bounding_box_x2, bounding_box_y),
                    (bounding_box_x2, bounding_box_y2),
                    (bounding_box_x, bounding_box_y2))

            pc = pyclipper.Pyclipper()
            pc.AddPath(pyclipper.scale_to_clipper(
                clip, SCALING_FACTOR), pyclipper.PT_CLIP)
            pc.AddPath(pyclipper.scale_to_clipper(points, SCALING_FACTOR),
                       pyclipper.PT_SUBJECT)

            solution = pyclipper.scale_from_clipper(pc.Execute(
                pyclipper.CT_INTERSECTION, pyclipper.PFT_EVENODD, pyclipper.PFT_EVENODD), SCALING_FACTOR)

            for object in solution:
                for point in object:
                    point.append(vertices[0][2])  # add color

            if len(solution) > 0 or not optimize:
                output.append({
                    "boundingBoxX": bounding_box_x,
                    "boundingBoxY": bounding_box_y,
                    "boundingBoxWidth": bounding_box_x2-bounding_box_x,
                    "boundingBoxHeight": bounding_box_y2-bounding_box_y,
                    "vertices": solution
                })
            bounding_box_y = bounding_box_y+grid_size
        bounding_box_x = bounding_box_x+grid_size
    return output


def clip_polygons(polygons, bounding_box, grid_size):
    first = True
    output1 = clip_polygon(
        polygons[0], bounding_box, grid_size, optimize=False)
    for vertices in polygons:
        if first:
            first = False
        else:
            output = clip_polygon(vertices, bounding_box,
                                  grid_size, optimize=False)
            for idx, val in enumerate(output):
                for solution in val['vertices']:
                    output1[idx]['vertices'].append(solution)
    output1 = [val for val in output1 if len(val['vertices']) > 0]
    return output1
