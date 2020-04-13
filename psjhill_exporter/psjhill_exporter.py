import lib.inkex

#!/usr/bin/env python
import os
import sys
import tempfile
import re
import json
from pathlib import Path
from shutil import copyfile, rmtree
import subprocess
import glob
import zipfile

from lib.inkex.command import inkscape
from lib.inkex.elements import PathElement, Group, ShapeElement
from lib.inkex import bezier
from lib.inkex import Transform

import util
import clipper
import triangulator
from lib.inkex.command import inkscape


class PsjHillEditor(lib.inkex.EffectExtension):

    def __init__(self):
        super(PsjHillEditor, self).__init__()

    def add_arguments(self, pars):
        pars.add_argument(
            "-b",
            "--build",
            dest="build",
            default=os.path.expanduser("~"),
            help="Build informations",
        )

    def effect(self):
        self.load_build_info()
        self.prepare_paths()
        self.add_textures()
        self.pack_textures()
        self.generate_hill_model()
        self.generate_hill_meta()
        self.generate_manifest()
        self.zipdir(sys.path[0] + '/output/')
        rmtree(sys.path[0] + "/output")

    def recursively_iterate_layer(self, node, layer_num, objects, shape_group):
        if isinstance(node, PathElement) and util.get_psjhill_attrib(node, "type") == "shape":
            id = util.get_psjhill_attrib(node, "id") or None
            generate_type = util.get_psjhill_attrib(
                node, "shape-generate-type") or "DISTANCE"
            generate_distance_between_nodes = util.get_psjhill_attrib(
                node, "shape-generate-distance-between-nodes") or "1.0"
            generate_distance_between_nodes = float(
                generate_distance_between_nodes)
            generate_nodes_count_between = util.get_psjhill_attrib(
                node, "shape-generate-nodes-count-between") or "5"
            generate_nodes_count_between = int(generate_nodes_count_between)
            cut_enabled = util.get_psjhill_attrib(
                node, "shape-cut-enabled") or "true"
            cut_enabled = True if cut_enabled == "true" else False
            cut_grid_size = util.get_psjhill_attrib(
                node, "shape-cut-grid-size") or "10"
            cut_grid_size = int(cut_grid_size)
            if cut_enabled is False:
                cut_grid_size = 100000  # hack

            color_regexp = re.search(
                'fill:(#[0-9a-fA-F]+)', node.attrib['style'])
            color = color_regexp.group(1)

            fill_opacity = 1
            fill_opacity_regexp = re.search(
                'fill-opacity:([0-9.]+)', node.attrib['style'])
            if fill_opacity_regexp is not None and fill_opacity_regexp.group(1) is not None:
                fill_opacity = float(fill_opacity_regexp.group(1))
            fill_opacity = format(int(fill_opacity * 255), '02x')
            color = color + fill_opacity

            if generate_type == "NODES":
                vertices = util.generate_polygon_vertices_nodes_between(
                    node, generate_nodes_count_between, add_last=True)
            else:  # type = DISTANCE or none
                vertices = util.generate_polygon_vertices_dst(
                    node, generate_distance_between_nodes, add_last=True)
            vertices = [node.composed_transform().apply_to_point(point)
                        for point in vertices]
            vertices = [(point[0], point[1], color) for point in vertices]

            if shape_group is not None:
                shape_group.append(vertices)
            else:
                bbox = util.get_absolute_bounding_box(node)

                clipped = clipper.clip_polygon(vertices, bbox, cut_grid_size)
                triangulated = triangulator.triangulate_polygon(clipped)

                for clip in triangulated:
                    new_vertices = [vertex
                                    for object in clip['objects']
                                    for vertex in object['vertices']]
                    new_indicies = [indice
                                    for object in clip['objects']
                                    for indice in object['indicies']]

                    del clip['objects']
                    clip['vertices'] = new_vertices
                    clip['indicies'] = new_indicies

                objects.append({
                    'type': 'shape',
                    'id': id,
                    'subShapes': clipped
                })

        if isinstance(node, Group) or isinstance(node, PathElement):
            type = util.get_psjhill_attrib(node, 'type')
            if type == 'layer':
                if layer_num is not None:
                    raise Exception("Layers can't be nested")
            elif type == 'shape-group':
                id = util.get_psjhill_attrib(node, "id") or None
                cut_enabled = util.get_psjhill_attrib(
                    node, "shape-cut-enabled") or "true"
                cut_enabled = True if cut_enabled == "true" else False
                cut_grid_size = util.get_psjhill_attrib(
                    node, "shape-cut-grid-size") or "10"
                cut_grid_size = int(cut_grid_size)
                if cut_enabled is False:
                    cut_grid_size = 100000  # hack

                shapes = []
                for child in node.getchildren():
                    self.recursively_iterate_layer(
                        child, layer_num, objects, shapes)
                bbox = util.get_absolute_bounding_box(node)

                clipped = clipper.clip_polygons(shapes, bbox, cut_grid_size)
                triangulated = triangulator.triangulate_polygon(clipped)

                for clip in triangulated:
                    new_vertices = [vertex
                                    for object in clip['objects']
                                    for vertex in object['vertices']]

                    new_indicies = []
                    start_indice = 0
                    for object in clip['objects']:
                        for indice in object['indicies']:
                            new_indicies.append([
                                indice[0]+start_indice,
                                indice[1]+start_indice,
                                indice[2]+start_indice])
                        start_indice = start_indice + len(object['vertices'])

                    del clip['objects']
                    clip['vertices'] = new_vertices
                    clip['indicies'] = new_indicies

                objects.append({
                    'type': 'shape',
                    'id': id,
                    'subShapes': clipped
                })
                return

            elif type == 'sprite':
                id = util.get_psjhill_attrib(node, "id") or None
                texture_id = util.get_psjhill_attrib(
                    node, 'texture-id', raise_if_none=True)
                visibility_if = util.get_psjhill_attrib(
                    node, 'visibility-if-modes') or 'ANY'
                if not any(texture['texture-id'] == texture_id for texture in self.textures):
                    raise Exception(
                        'Cannot find texture with id: ' + texture_id)
                bbox = util.get_absolute_bounding_box(node)
                objects.append({
                    "type": "sprite",
                    "id": id,
                    "textureId": texture_id,
                    "x": bbox.x.minimum,
                    "y": bbox.y.minimum,
                    "width": bbox.width,
                    "height": bbox.height,
                    'visibilityIfModes': visibility_if.split('|')
                })
        if isinstance(node, ShapeElement):
            pass
        else:
            if(node.tag_name == "desc"):
                desc = node.text
                parent = node.getparent()

        for child in node.getchildren():
            self.recursively_iterate_layer(
                child, layer_num, objects, shape_group)

    def recursively_iterate(self, node, layers):
        if isinstance(node, Group) and util.get_psjhill_attrib(node, 'type') == "layer":
            layer_num = util.get_psjhill_attrib(
                node, 'layer-num', raise_if_none=True)
            layer_type = util.get_psjhill_attrib(
                node, 'layer-type', raise_if_none=True)
            layer_name = util.get_psjhill_attrib(
                node, 'layer-name', raise_if_none=True)
            if layer_type not in ("BACKGROUND", "HILL_BODY", "HILL_BACKGROUND",
                                  "HILL_FOREGROUND", "FOREGROUND"):
                raise Exception("Unknown layer type: " + layer_type)

            paralax_offset = util.get_psjhill_attrib(
                node, 'paralax-offset') or "0.0"
            paralax_offset = float(paralax_offset)

            objects = []
            for child in node.getchildren():
                self.recursively_iterate_layer(child, layer_num, objects, None)
            layers.append({
                'layer_num': layer_num,
                'layer_type': layer_type,
                'name': layer_name,
                'paralax_offset': paralax_offset,
                'objects': objects
            })
        else:
            for child in node.getchildren():
                self.recursively_iterate(child, layers)

    def zipdir(self, path):
        zipf = zipfile.ZipFile('output.psj', 'w', zipfile.ZIP_DEFLATED)
        length = len(path)
        for root, dirs, files in os.walk(path):
            folder = root[length:]
            for file in files:
                zipf.write(os.path.join(root, file),
                           os.path.join(folder, file))
        zipf.close

    def load_build_info(self):
        with open(self.options.build) as json_file:
            self.build_info = json.load(json_file)

    def prepare_paths(self):
        if Path(sys.path[0] + "/output").exists():
            rmtree(sys.path[0] + "/output")
        Path(sys.path[0] +
             "/output/textures").mkdir(parents=True, exist_ok=True)
        Path(sys.path[0] + "/output/modes").mkdir(parents=True, exist_ok=True)
        Path(sys.path[0] +
             "/output/tmp/textures").mkdir(parents=True, exist_ok=True)

        modes = self.build_info['modes']
        input_file_dir = Path(self.options.input_file).parent
        for key in modes:
            copyfile(str(input_file_dir) + '/' +
                     modes[key], sys.path[0] + '/output/modes/'+modes[key])
        copyfile(str(input_file_dir) + '/' +
                 self.build_info['icon'], sys.path[0] + '/output/'+self.build_info['icon'])

    def add_textures(self):
        input_file_dir = Path(self.options.input_file).parent
        texture_nodes = util.xpath(
            self.document, '//*[@psjhill:type="texture"]')

        self.textures = []
        for texture_node in texture_nodes:
            self.textures.append(self.export_texture(
                texture_node, sys.path[0] + "/output/tmp/textures/"))

        for texture_path in self.build_info['additionalTextures']:
            file = Path(texture_path)
            copyfile(str(input_file_dir) + '/' +
                     texture_path, sys.path[0] + '/output/tmp/textures/'+file.name)
            self.textures.append(
                {
                    "texture-id": file.stem
                })

    def export_texture(self, node, path):
        node_id = node.get_id()
        bbox = util.get_absolute_bounding_box(node)

        id = util.get_psjhill_attrib(node, 'id', raise_if_none=True)
        multiplier = util.get_psjhill_attrib(
            node, 'texture-multiplier', raise_if_none=True)
        multiplier = float(multiplier)
        export_width = int(bbox.width * float(multiplier))
        inkscape(self.options.input_file, **{
            'export-width': export_width,
            'export-id': node_id,
            'export-file': path+id+'.png',
            'export-id-only': ''
        })

        return {
            "texture-id": id,
            "export-aprox-width": export_width,
            "export-aprox-height": int(bbox.height / bbox.width * export_width),
            'export-file': path+id+'.png'
        }

    def pack_textures(self):
        subprocess.run(["java", "-jar", sys.path[0] + "/texture_packer/runnable-texturepacker.jar",
                        sys.path[0] + "/output/tmp/textures", sys.path[0] + "/output/textures", "textures", sys.path[0] + "/files/pack.json"])
        rmtree(sys.path[0] + "/output/tmp")

    def generate_hill_model(self):
        start_gate_info = self.get_startgate_info()
        in_run_path = self.get_special_path_points(
            'in-run-physics', 1, debug=True)
        out_run_path = self.get_special_path_points('out-run-physics', 1)
        out_run_top_path = self.get_special_path_points('out-run-top', 1)
        out_run_bottom_path = self.get_special_path_points('out-run-bottom', 1)
        start_bar_area = self.get_special_path_points('start-gates-area', 10)
        start_bar_area = [start_bar_area[0], start_bar_area[-1]]
        hill_size_cross = self.get_special_path_points('hill-size-cross', 1)
        hill_size_cross = [hill_size_cross[0], hill_size_cross[-1]]

        viewpoint = util.xpath(
            self.document, '//*[@psjhill:type="special" and @psjhill:special-type="viewpoint"]')
        viewpoint_bbox = util.get_absolute_bounding_box(viewpoint[0])
        viewpoint_vertex = [(viewpoint_bbox.x.minimum + viewpoint_bbox.x.maximum)/2,
                            (viewpoint_bbox.y.minimum + viewpoint_bbox.y.maximum)/2]

        first = None
        intersect_point = None
        distance = 0
        for vertex in out_run_path:
            if first is not None:
                intersect_point = util.intersect_segments(
                    first, vertex, hill_size_cross[0], hill_size_cross[1])
                if intersect_point is not None:
                    distance += util.point_point_dst(first, intersect_point)
                    break
                else:
                    distance += util.point_point_dst(first, vertex)
            first = vertex
        if intersect_point is None:
            raise Exception(
                'Hill size cross does not cross with out run physic')

        layers = []
        self.recursively_iterate(self.document.getroot(), layers)
        split_layers = {
            'background': [layer for layer in layers if layer['layer_type'] == 'BACKGROUND'],
            'hillBody': [layer for layer in layers if layer['layer_type'] == 'HILL_BODY'],
            'hillBackground': [layer for layer in layers if layer['layer_type'] == 'HILL_BACKGROUND'],
            'hillForeground': [layer for layer in layers if layer['layer_type'] == 'HILL_FOREGROUND'],
            'foreground': [layer for layer in layers if layer['layer_type'] == 'FOREGROUND']
        }

        for key in split_layers:
            split_layers[key] = sorted(
                split_layers[key], key=lambda x: x['layer_num'], reverse=False)
            for layer in split_layers[key]:
                del layer['layer_num']
                del layer['layer_type']

        K = self.build_info['constructionPoint']
        HS = self.build_info['hillSize']

        texturePaths = []
        if Path(sys.path[0] + "/output/textures/textures.atlas").exists():
            texturePaths = ['textures/textures.atlas']

        hill_model = {
            'texturePaths': texturePaths,
            'viewpointVertex': viewpoint_vertex,
            'inRunVertices': in_run_path,
            'outRunVertices': out_run_path,
            'outRunTopBorderVertices': out_run_top_path,
            'outRunBottomBorderVertices': out_run_bottom_path,
            'startGatesArea': start_bar_area,
            'startGateForegroundTextureId': start_gate_info[0],
            'startGateForegroundTextureSize': start_gate_info[1],
            'startGateForegroundTextureOffset': start_gate_info[2],
            'startGateBackgroundTextureId': start_gate_info[3],
            'startGateBackgroundTextureSize': start_gate_info[4],
            'startGateBackgroundTextureOffset': start_gate_info[5],
            'sizes': {
                'hillSizePathLength': distance,
                'constructionPointPathLength': distance * K/HS,
                'inRunPathLength': util.calc_vertices_path_size(in_run_path),
                'outRunPathLength': util.calc_vertices_path_size(out_run_path),
            },
            'layers': split_layers
        }

        with open(sys.path[0] + "/output/hill_model.json", "w") as text_file:
            text_file.write(json.dumps(json.loads(json.dumps(
                hill_model), parse_float=lambda x: round(float(x), 4))))

    def generate_hill_meta(self):
        hill_meta = {
            "id": self.build_info['id'],
            "name": self.build_info['name'],
            "versionName": self.build_info['versionName'],
            "version": self.build_info['version'],
            "author": self.build_info['author'],
            "description": self.build_info['description'],
            "country": self.build_info['country'],
            "place": self.build_info['place'],
            "icon": self.build_info['icon'],
            "constructionPoint": self.build_info['constructionPoint'],
            "hillSize": self.build_info['hillSize'],
            "noOfStartGates": self.build_info['noOfStartGates'],
            "defaultStartGate": self.build_info['defaultStartGate'],
            "defaultCompetitiveStartGate": self.build_info['defaultCompetitiveStartGate'],
            "defaultMode": self.build_info['defaultMode'],
            "defaultCompetitiveMode": self.build_info['defaultCompetitiveMode'],
            "defaultSnowing": self.build_info['defaultSnowing'],
            "defaultCompetitiveSnowing": self.build_info['defaultCompetitiveSnowing'],
            "physics": self.build_info['physics'],
            "modes":
            {key: {
                "modeData": 'modes/' + self.build_info['modes'][key],
                "hillModelData": "hill_model.json"
            } for key in self.build_info['modes']}
        }
        with open(sys.path[0] + "/output/hill_meta.json", "w") as text_file:
            text_file.write(json.dumps(hill_meta, indent=4))

    def generate_manifest(self):
        manifest = {
            "type": "psjhill",
            "version": 1,
            "data": "hill_meta.json"
        }
        with open(sys.path[0] + "/output/manifest.json", "w") as text_file:
            text_file.write(json.dumps(manifest, indent=4))

    def get_special_path_points(self, specialType, dst, debug=False):
        path = util.xpath(
            self.document, '//*[@psjhill:type="special" and @psjhill:special-type="'+specialType+'"]')
        if len(path) != 1:
            raise Exception(
                "There must be 1 " + specialType + ", found: " + str(len(path)))
        vertices = util.absolute_points(path[0],
                                        util.generate_polygon_vertices_dst(path[0], dst, True, debug=debug))
        vertices = util.ensure_right_pointing_vertices(vertices)
        return vertices

    def get_startgate_info(self):
        start_gate_fg_texture_nodes = util.xpath(
            self.document, '//*[@psjhill:special-type="start-gate-foreground-texture"]')
        start_gate_bg_texture_nodes = util.xpath(
            self.document, '//*[@psjhill:special-type="start-gate-background-texture"]')
        start_gate_texture_position_nodes = util.xpath(
            self.document, '//*[@psjhill:special-type="start-gate-texture-position"]')

        start_gate_fg_texture_id = None
        start_gate_fg_texture_size = None
        start_gate_fg_texture_offset = None
        start_gate_bg_texture_id = None
        start_gate_bg_texture_size = None
        start_gate_bg_texture_offset = None
        if len(start_gate_bg_texture_nodes) == 1 and len(start_gate_fg_texture_nodes) == 1 and len(start_gate_texture_position_nodes) == 1:
            start_gate_bg_texture_id = util.get_psjhill_attrib(
                start_gate_bg_texture_nodes[0], 'id', raise_if_none=True)
            start_gate_fg_texture_id = util.get_psjhill_attrib(
                start_gate_fg_texture_nodes[0], 'id', raise_if_none=True)

            self.textures.append(self.export_texture(
                start_gate_bg_texture_nodes[0], sys.path[0] + "/output/tmp/textures/"))
            self.textures.append(self.export_texture(
                start_gate_fg_texture_nodes[0], sys.path[0] + "/output/tmp/textures/"))

            start_gate_bg_texture_bbox = util.get_absolute_bounding_box(
                start_gate_bg_texture_nodes[0])
            start_gate_bg_texture_size = [
                start_gate_bg_texture_bbox.width, start_gate_bg_texture_bbox.height]
            start_gate_fg_texture_bbox = util.get_absolute_bounding_box(
                start_gate_fg_texture_nodes[0])
            start_gate_fg_texture_size = [
                start_gate_fg_texture_bbox.width, start_gate_fg_texture_bbox.height]

            start_gate_texture_position_bbox = util.get_absolute_bounding_box(
                start_gate_texture_position_nodes[0])
            start_gate_texture_position_vertex = [(start_gate_texture_position_bbox.x.minimum + start_gate_texture_position_bbox.x.maximum)/2,
                                                  (start_gate_texture_position_bbox.y.minimum + start_gate_texture_position_bbox.y.maximum)/2]

            start_gate_bg_texture_vertex = [
                start_gate_bg_texture_bbox.x.minimum, start_gate_bg_texture_bbox.y.maximum]
            start_gate_fg_texture_vertex = [
                start_gate_fg_texture_bbox.x.minimum, start_gate_fg_texture_bbox.y.maximum]

            start_gate_bg_texture_offset = [start_gate_bg_texture_vertex[0] - start_gate_texture_position_vertex[0],
                                            start_gate_bg_texture_vertex[1] - start_gate_texture_position_vertex[1]]
            start_gate_fg_texture_offset = [start_gate_fg_texture_vertex[0] - start_gate_texture_position_vertex[0],
                                            start_gate_fg_texture_vertex[1] - start_gate_texture_position_vertex[1]]
        return (start_gate_fg_texture_id, start_gate_fg_texture_size, start_gate_fg_texture_offset,
                start_gate_bg_texture_id, start_gate_bg_texture_size, start_gate_bg_texture_offset)


if __name__ == "__main__":
    PsjHillEditor().run(output="/dev/null")
