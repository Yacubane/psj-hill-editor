import lib.tripy as tripy

def triangulate_polygon(polygon):
    for clip in polygon:
            new_object = []
            for vertices in clip['vertices']:
                points = [(verticle[0], verticle[1])
                            for verticle in vertices]
                triangulated_points = tripy.earclip(points)
                indicies = [(points.index(triangle[0]), points.index(
                    triangle[1]), points.index(triangle[2])) for triangle in triangulated_points]
                new_object.append({
                    'vertices': vertices,
                    'indicies': indicies
                })
            del clip['vertices']
            clip['objects'] = new_object
    return polygon