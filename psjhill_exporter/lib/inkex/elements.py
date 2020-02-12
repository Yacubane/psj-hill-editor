# -*- coding: utf-8 -*-
#
# Copyright (c) 2018 - Martin Owens <doctormo@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.
#
# pylint: disable=arguments-differ
"""
Provide extra utility to each svg element type specific to its type.

This is useful for having a common interface for each element which can
give path, transform, and property access easily.
"""

import math

from copy import deepcopy
from lxml import etree

from .paths import Path
from .styles import Style, AttrFallbackStyle, StyleSheet, Classes
from .transforms import BoundingBox, Transform, Vector2d
from .utils import PY3, NSS, addNS, removeNS, InitSubClassPy3, FragmentError
from .units import convert_unit

try:
    from typing import Optional  # pylint: disable=unused-import
except ImportError:
    pass

__all__ = ('Group', 'PathElement', 'ShapeElement')

class SvgClassLookup(etree.CustomElementClassLookup):
    """
    We choose what kind of Elements we should return for each element, providing useful
    SVG based API to our extensions system.
    """
    lookup_tags = {}

    def lookup(self, node_type, document, namespace, name):  # pylint: disable=unused-argument
        """Choose what kind of functionality our element will have"""
        if namespace is None:
            namespace = NSS['svg']

        if node_type == 'element':
            return self.lookup_tags.get((namespace, name), BaseElement)
        return None

SVG_PARSER = etree.XMLParser(huge_tree=True, strip_cdata=False)
SVG_PARSER.set_element_class_lookup(SvgClassLookup())

def load_svg(stream):
    """Load SVG file using the SVG_PARSER"""
    if (isinstance(stream, str) and stream.startswith('<'))\
      or (isinstance(stream, bytes) and stream.startswith(b'<')):
        return etree.ElementTree(etree.fromstring(stream, parser=SVG_PARSER))
    return etree.parse(stream, parser=SVG_PARSER)

class BaseElement(etree.ElementBase):
    """Provide automatic namespaces to all calls"""
    # TODO: The next two lines are only required for python2, remove when py3 only
    __metaclass__ = InitSubClassPy3
    @classmethod
    def __init_subclass__(cls):
        for name in (cls.tag_name,) if cls.tag_name else cls.tag_names:
            SvgClassLookup.lookup_tags[removeNS(name, url=True)] = cls

    tag_name = ''
    tag_names = ()

    @property
    def TAG(self): # pylint: disable=invalid-name
        """Return the tag_name without NS"""
        assert self.tag_name
        return removeNS(self.tag_name)[-1]

    @classmethod
    def new(cls, *children, **attrs):
        """Create a new element, converting attrs values to strings."""
        obj = cls(*children)
        obj.update(**attrs)
        return obj

    NAMESPACE = property(lambda self: removeNS(self.tag_name, url=True)[0])
    PARSER = SVG_PARSER
    WRAPPED_ATTRS = (
        # (prop_name, [optional: attr_name], cls)
        ('transform', Transform),
        ('style', Style),
        ('classes', 'class', Classes),
    )

    # We do this because python2 and python3 have different ways
    # of combining two dictionaries that are incompatible.
    # This allows us to update these with inheritance.
    @property
    def wrapped_attrs(self):
        """Map attributes to property name and wrapper class"""
        return dict([(row[-2], (row[0], row[-1])) for row in self.WRAPPED_ATTRS])

    @property
    def wrapped_props(self):
        """Map properties to attribute name and wrapper class"""
        return dict([(row[0], (row[-2], row[-1])) for row in self.WRAPPED_ATTRS])

    typename = property(lambda self: type(self).__name__)

    def __getattr__(self, name):
        """Get the attribute, but load it if it is not available yet"""
        if name in self.wrapped_props:
            (attr, cls) = self.wrapped_props[name]
            # The reason we do this here and not in _init is because lxml
            # is inconsistant about when elements are initialised.
            # So we make this a lazy property.
            def _set_attr(new_item):
                if new_item:
                    self.set(attr, str(new_item))
                else:
                    self.attrib.pop(attr, None) # pylint: disable=no-member

            # pylint: disable=no-member
            value = cls(self.attrib.get(attr, None), callback=_set_attr)
            setattr(self, name, value)
            return value
        raise AttributeError("Can't find attribute {}.{}".format(self.typename, name))

    def __setattr__(self, name, value):
        """Set the attribute, update it if needed"""
        if name in self.wrapped_props:
            (attr, cls) = self.wrapped_props[name]
            # Don't call self.set or self.get (infinate loop)
            if value:
                if not isinstance(value, cls):
                    value = cls(value)
                self.attrib[attr] = str(value)
            else:
                self.attrib.pop(attr, None) # pylint: disable=no-member
        else:
            super(BaseElement, self).__setattr__(name, value)

    def get(self, attr, default=None):
        """Get element attribute named, with addNS support."""
        if attr in self.wrapped_attrs:
            (prop, _) = self.wrapped_attrs[attr]
            value = getattr(self, prop, None)
            # We check the boolean nature of the value, because empty
            # transformations and style attributes are equiv to not-existing
            ret = str(value) if value else (default or None)
            return ret
        return super(BaseElement, self).get(addNS(attr), default)

    def set(self, attr, value):
        """Set element attribute named, with addNS support"""
        if attr in self.wrapped_attrs:
            # Always keep the local wrapped class up to date.
            (prop, cls) = self.wrapped_attrs[attr]
            setattr(self, prop, cls(value))
            value = getattr(self, prop)
            if not value:
                return
        if value is None:
            self.attrib.pop(addNS(attr), None) # pylint: disable=no-member
        else:
            value = str(value) if PY3 else unicode(value) # pylint: disable=undefined-variable
            super(BaseElement, self).set(addNS(attr), value)

    def update(self, **kwargs):
        """
        Update element attributes using keyword arguments

        Note: double underscore is used as namespace separator,
        i.e. "namespace__attr" argument name will be treated as "namespace:attr"

        :param kwargs: dict with name=value pairs
        :return: self
        """
        for name, value in kwargs.items():
            self.set(name, value)
        return self

    def pop(self, attr, default=None):
        """Delete/remove the element attribute named, with addNS support."""
        if attr in self.wrapped_attrs:
            # Always keep the local wrapped class up to date.
            (prop, cls) = self.wrapped_attrs[attr]
            value = getattr(self, prop)
            setattr(self, prop, cls(None))
            return value
        return self.attrib.pop(addNS(attr), default) # pylint: disable=no-member

    def add(self, *children):
        """
        Like append, but will do multiple children and will return
        children or only child
        """
        for child in children:
            self.append(child)
        return children if len(children) > 1 else children[0]

    def tostring(self):
        """Return this element as it would appear in an svg document"""
        # This kind of hack is pure maddness, but etree provides very little
        # in the way of fragment printing, prefering to always output valid xml
        from .base import SvgOutputMixin
        svg = SvgOutputMixin.get_template(width=0, height=0).getroot()
        svg.append(self.copy())
        return svg.tostring().split(b'>\n    ', 1)[-1][:-6]

    def description(self, text):
        """Set the desc element with text"""
        desc = self.add(Desc())
        desc.text = text

    def set_random_id(self, prefix=None, size=4, backlinks=False):
        """Sets the id attribute if it is not already set."""
        prefix = str(self) if prefix is None else prefix
        self.set_id(self.root.get_unique_id(prefix, size=size), backlinks=backlinks)

    def set_random_ids(self, prefix=None, levels=-1, backlinks=False):
        """Same as set_random_id, but will apply also to children"""
        self.set_random_id(prefix=prefix, backlinks=backlinks)
        if levels != 0:
            for child in self:
                if hasattr(child, 'set_random_ids'):
                    child.set_random_ids(prefix=prefix, levels=levels-1, backlinks=backlinks)

    def get_id(self):
        """Get the id for the element, will set a new unique id if not set"""
        if 'id' not in self.attrib:
            self.set_random_id(self.TAG)
        return self.get('id')

    def set_id(self, new_id, backlinks=False):
        """Set the id and update backlinks to xlink and style urls if needed"""
        old_id = self.get('id', None)
        self.set('id', new_id)
        if backlinks and old_id:
            for elem in self.root.getElementsByHref(old_id):
                elem.set('xlink:href', '#' + new_id)
            for elem in self.root.getElementsByStyleUrl(old_id):
                elem.style.update_urls(old_id, new_id)

    @property
    def root(self):
        """Get the root document element from any element descendent"""
        if self.getparent() is not None:
            return self.getparent().root
        from inkex.svg import SvgDocumentElement
        if not isinstance(self, SvgDocumentElement):
            raise FragmentError("Element fragment does not have a document root!")
        return self

    def get_or_create(self, xpath, nodeclass, prepend=False):
        """Get or create the given xpath, pre/append new node if not found."""
        node = self.findone(xpath)
        if node is None:
            node = nodeclass()
            if prepend:
                self.insert(0, node)
            else:
                self.append(node)
        return node

    def descendants(self, *types):
        """Walks the element tree and yields all elements, parent first"""
        if not types or isinstance(self, types):
            yield self
        for child in self:
            if hasattr(child, 'descendants'):
                for descendant in child.descendants(*types):
                    yield descendant

    def ancestors(self):
        """Walk the parents and yield all the ancestor elements, parent first"""
        parent = self.getparent()
        if parent is not None:
            yield parent
            for child in parent.ancestors():
                yield child

    def backlinks(self, *types):
        """Get elements which link back to this element, like ancestors but via xlinks"""
        if not types or isinstance(self, types):
            yield self
        my_id = self.get('id')
        if my_id is not None:
            elems = list(self.root.getElementsByHref(my_id)) \
                  + list(self.root.getElementsByStyleUrl(my_id))
            for elem in elems:
                if hasattr(elem, 'backlinks'):
                    for child in elem.backlinks(*types):
                        yield child

    def xpath(self, pattern, namespaces=NSS):  # pylint: disable=dangerous-default-value
        """Wrap xpath call and add svg namespaces"""
        return super(BaseElement, self).xpath(pattern, namespaces=namespaces)

    def findall(self, pattern, namespaces=NSS):  # pylint: disable=dangerous-default-value
        """Wrap findall call and add svg namespaces"""
        return super(BaseElement, self).findall(pattern, namespaces=namespaces)

    def findone(self, xpath):
        """Gets a single element from the given xpath or returns None"""
        el_list = self.xpath(xpath)
        return el_list[0] if el_list else None

    def delete(self):
        """Delete this node from it's parent node"""
        if self.getparent() is not None:
            self.getparent().remove(self)

    def replace_with(self, elem):
        """Replace this element with the given element"""
        self.addnext(elem)
        if not elem.get('id') and self.get('id'):
            elem.set('id', self.get('id'))
        if not elem.label and self.label:
            elem.label = self.label
        self.delete()
        return elem

    def copy(self):
        """Make a copy of the element and return it"""
        elem = deepcopy(self)
        elem.set('id', None)
        return elem

    def __str__(self):
        # We would do more here, but lxml is VERY unpleseant when it comes to
        # namespaces, basically over printing details and providing no
        # supression mechanisms to turn off xml's over engineering.
        return str(self.tag).split('}')[-1]

    @property
    def href(self):
        """Returns the referred-to element if available"""
        ref = self.get('xlink:href')
        if not ref:
            return None
        return self.root.getElementById(ref.strip('#'))

    def fallback_style(self, move=False):
        """Get styles falling back to element attributes"""
        return AttrFallbackStyle(self, move=move)


class ShapeElement(BaseElement):
    """Elements which have a visible representation on the canvas"""
    @property
    def path(self):
        """Gets the outline or path of the element, this may be a simple bounding box"""
        return Path(self.get_path())

    @path.setter
    def path(self, path):
        self.set_path(path)

    def get_path(self):
        """Generate a path for this object which can inform the bounding box"""
        raise NotImplementedError("Path should be provided by svg elem {}.".format(self.typename))

    def set_path(self, path):
        """Set the path for this object (if possible)"""
        raise AttributeError(
            "Path can not be set on this element: {} <- {}.".format(self.typename, path))

    def to_path_element(self):
        """Replace this element with a path element"""
        elem = PathElement()
        elem.path = self.path
        elem.style = self.effective_style()
        elem.transform = self.transform
        return elem

    def composed_transform(self):
        """Calculate every transform down to the root document node"""
        parent = self.getparent()
        if parent is not None and isinstance(parent, ShapeElement):
            return self.transform * parent.composed_transform()
        return self.transform

    def composed_style(self):
        """Calculate the final styles applied to this element"""
        parent = self.getparent()
        if parent is not None and isinstance(parent, ShapeElement):
            return parent.composed_style() + self.style
        return self.style

    def cascaded_style(self):
        """Add all cascaded styles, do not write to this Style object"""
        ret = Style()
        for style in self.root.stylesheets.lookup(self.get('id')):
            ret += style
        return ret + self.style

    def effective_style(self):
        """Without parent styles, what is the effective style is"""
        return self.style

    def bounding_box(self, transform=None):  # type: () -> BoundingBox
        """BoundingBox calculation based on the ShapeElement rendered to a path."""
        path = self.path.to_absolute()
        if transform is True:
            path = path.transform(self.composed_transform())
        else:
            path = path.transform(self.transform)
            if transform:  # apply extra transformation
                path = path.transform(transform)
        return path.bounding_box()

    @property
    def label(self):
        """Returns the inkscape label"""
        return self.get('inkscape:label', None)
    label = label.setter(lambda self, value: self.set('inkscape:label', str(value)))


class FlowRegion(ShapeElement):
    """SVG Flow Region (SVG 2.0)"""
    tag_name = 'flowRegion'

    def get_path(self):
        # This ignores flowRegionExcludes
        return sum([child.path for child in self], Path())

class FlowRoot(ShapeElement):
    """SVG Flow Root (SVG 2.0)"""
    tag_name = 'flowRoot'

    @property
    def region(self):
        """Return the first flowRegion in this flowRoot"""
        return self.findone('svg:flowRegion')

    def get_path(self):
        region = self.region
        return region.get_path() if region is not None else Path()

class FlowPara(ShapeElement):
    """SVG Flow Paragraph (SVG 2.0)"""
    tag_name = 'flowPara'

    def get_path(self):
        # XXX: These empty paths mean the bbox for text elements will be nothing.
        return Path()

class FlowDiv(ShapeElement):
    """SVG Flow Div (SVG 2.0)"""
    tag_name = 'flowDiv'

    def get_path(self):
        # XXX: These empty paths mean the bbox for text elements will be nothing.
        return Path()

class FlowSpan(ShapeElement):
    """SVG Flow Span (SVG 2.0)"""
    tag_name = 'flowSpan'

    def get_path(self):
        # XXX: These empty paths mean the bbox for text elements will be nothing.
        return Path()

class FilterPrimitive(BaseElement):
    """A bunch of different filter primitives"""
    tag_names = [
        'feBlend', 'feColorMatrix', 'feComponentTransfer', 'feComposite',
        'feConvolveMatrix', 'feDiffuseLighting', 'feDisplacementMap', 'feFlood',
        'feGaussianBlur', 'feImage', 'feMerge', 'feMorphology', 'feOffset',
        'feSpecularLighting', 'feTile', 'feTurbulence'
    ]

class Filter(BaseElement):
    """A filter (usually in defs)"""
    tag_name = 'filter'

    def add_primitive(self, fe_type, **args):
        """Create a filter primitive with the given arguments"""
        elem = etree.SubElement(self, addNS(fe_type, 'svg'))
        elem.update(**args)
        return elem

class Group(ShapeElement):
    """Any group element (layer or regular group)"""
    tag_name = 'g'
    is_layer = lambda self: self.groupmode == 'layer'

    @classmethod
    def new(cls, label, is_layer=False, *children, **attrs):
        attrs['inkscape:label'] = label
        if is_layer is True:
            attrs['inkscape:groupmode'] = 'layer'
        return super(Group, cls).new(*children, **attrs)

    def get_path(self):
        ret = Path()
        for child in self:
            ret += child.path.transform(child.transform)
        return ret

    def bounding_box(self, transform=None):  # type: (Transform) -> Optional[BoundingBox]
        bbox = None

        transform = Transform(transform) * self.transform
        if not transform:
            transform = None

        for child in self:
            if isinstance(child, ShapeElement):
                bbox += child.bounding_box(transform=transform)
        return bbox

    def effective_style(self):
        """A blend of each child's style mixed together (last child wins)"""
        style = self.style
        for child in self:
            style.update(child.effective_style())
        return style

    @property
    def groupmode(self):
        """Return the type of group this is"""
        return self.get('inkscape:groupmode', 'group')

class Anchor(Group):
    """An anchor or link tag"""
    tag_name = 'a'

    @classmethod
    def new(cls, href, *children, **attrs):
        attrs['xlink:href'] = href
        return super(Group, cls).new(*children, **attrs)

class PathElement(ShapeElement):
    """Provide a useful extension for path elements"""
    tag_name = 'path'
    get_path = lambda self: self.get('d')

    @classmethod
    def new(cls, path, **attrs):
        return super(PathElement, cls).new(d=Path(path), **attrs)

    def set_path(self, path):
        """Set the given data as a path as the 'd' attribute"""
        self.set('d', str(Path(path)))

    def apply_transform(self):
        """Apply the internal transformation to this node and delete"""
        if 'transform' in self.attrib:
            self.path.transform(self.transform)
            self.set('d', str(self.path))
            self.set('transform', Transform())

    @property
    def original_path(self):
        """Returns the original path if this is an LPE, or the path if not"""
        return Path(self.get('inkscape:original-d', self.path))

    @original_path.setter
    def original_path(self, path):
        if addNS('inkscape:original-d') in self.attrib:
            self.set('inkscape:original-d', str(Path(path)))
        else:
            self.path = path

    @classmethod
    def arc(cls, center, rx, ry=None, **kw):
        """Generate a sodipodi arc (special type)"""
        others = [(name, kw.pop(name, None)) for name in ('start', 'end', 'open')]
        elem = cls(**kw)
        elem.set('sodipodi:cx', center[0])
        elem.set('sodipodi:cy', center[1])
        elem.set('sodipodi:rx', rx)
        elem.set('sodipodi:ry', ry or rx)
        elem.set('sodipodi:type', 'arc')
        for name, value in others:
            if value is not None:
                elem.set('sodipodi:'+name, str(value).lower())
        return elem


class Polyline(ShapeElement):
    """Like a path, but made up of straight lines only"""
    tag_name = 'polyline'

    def get_path(self):
        return Path('M' + self.get('points'))

    def set_path(self, path):
        points = ['{:g},{:g}'.format(x, y) for x, y in Path(path).end_points]
        self.set('points', ' '.join(points))

class Pattern(BaseElement):
    """Pattern element which is used in the def to control repeating fills"""
    tag_name = 'pattern'
    WRAPPED_ATTRS = BaseElement.WRAPPED_ATTRS + (('patternTransform', Transform),)

class Gradient(BaseElement):
    """A gradient instruction usually in the defs"""
    tag_names = ('linearGradient', 'radialGradient')
    WRAPPED_ATTRS = BaseElement.WRAPPED_ATTRS + (('gradientTransform', Transform),)

class Polygon(ShapeElement):
    """A closed polyline"""
    tag_name = 'polygon'
    get_path = lambda self: 'M' + self.get('points') + ' Z'


class Line(ShapeElement):
    """A line connecting two points"""
    tag_name = 'line'
    get_path = lambda self: 'M{0[x1]},{0[y1]} L{0[x2]},{0[y2]}'.format(self.attrib)

    @classmethod
    def new(cls, start, end, **attrs):
        start = Vector2d(start)
        end = Vector2d(end)
        return super(Line, cls).new(x1=start.x, y1=start.y,
                                    x2=end.x, y2=end.y, **attrs)


class Rectangle(ShapeElement):
    """Provide a useful extension for rectangle elements"""
    tag_name = 'rect'
    left = property(lambda self: float(self.get('x', '0')))
    top = property(lambda self: float(self.get('y', '0')))
    right = property(lambda self: self.left + self.width)
    bottom = property(lambda self: self.top + self.height)
    width = property(lambda self: float(self.get('width', '0')))
    height = property(lambda self: float(self.get('height', '0')))
    rx = property(lambda self: float(self.get('rx', self.get('ry', 0.0))))
    ry = property(lambda self: float(self.get('ry', self.get('rx', 0.0)))) # pylint: disable=invalid-name

    @classmethod
    def new(cls, left, top, width, height, **attrs):
        return super(Rectangle, cls).new(x=left, y=top, width=width, height=height, **attrs)

    def get_path(self):
        """Calculate the path as the box around the rect"""
        if self.rx:
            rx, ry = self.rx, self.ry # pylint: disable=invalid-name
            return 'M {1},{0.top}'\
                   'L {2},{0.top}    A {0.rx},{0.ry} 0 0 1 {0.right},{3}'\
                   'L {0.right},{4}  A {0.rx},{0.ry} 0 0 1 {2},{0.bottom}'\
                   'L {1},{0.bottom} A {0.rx},{0.ry} 0 0 1 {0.left},{4}'\
                   'L {0.left},{3}   A {0.rx},{0.ry} 0 0 1 {1},{0.top} z'\
                .format(self, self.left + rx, self.right - rx, self.top + ry, self.bottom - ry)

        return 'M {0.left},{0.top} h{0.width}v{0.height}h{1} z'.format(self, -self.width)


class Image(Rectangle):
    """Provide a useful extension for image elements"""
    tag_name = 'image'

class Circle(ShapeElement):
    """Provide a useful extension for circle elements"""
    tag_name = 'circle'
    radius = property(lambda self: self.get('r', '0'))
    radius_x = property(lambda self: float(self.get('rx', self.radius)))
    radius_y = property(lambda self: float(self.get('ry', self.radius)))
    center_x = property(lambda self: float(self.get('cx', '0')))
    center_y = property(lambda self: float(self.get('cy', '0')))
    top = property(lambda self: self.center_y - self.radius_y)
    bottom = property(lambda self: self.center_y + self.radius_y)
    left = property(lambda self: self.center_x - self.radius_x)
    right = property(lambda self: self.center_x + self.radius_x)

    @classmethod
    def new(cls, center_x, center_y, radius, **attrs):
        return super(Circle, cls).new(cx=center_x, cy=center_y, r=radius, **attrs)

    def get_path(self):
        """Calculate the arc path of this circle"""
        return ('M {0.center_x},{0.top} '
                'a {0.radius_x},{0.radius_y} 0 1 0 {0.radius_x}, {0.radius_y} '
                'a {0.radius_x},{0.radius_y} 0 0 0 -{0.radius_x}, -{0.radius_y} z'
               ).format(self)


class Ellipse(Circle):
    """Provide a similar extension to the Circle interface"""
    tag_name = 'ellipse'

    @classmethod
    def new(cls, center_x, center_y, radius_x, radius_y, **attrs):
        return super(Circle, cls).new(cx=center_x, cy=center_y, rx=radius_x, ry=radius_y, **attrs)


class Use(ShapeElement):
    """A 'use' element that links to another in the document"""
    tag_name = 'use'

    def get_path(self):
        """Returns the path of the cloned href plus any transformation"""
        path = self.href.path
        path.transform(self.href.transform)
        return path

    def effective_style(self):
        """Href's style plus this object's own styles"""
        style = self.href.effective_style()
        style.update(self.style)
        return style

    def unlink(self):
        """Unlink this clone, replacing it with a copy of the original"""
        copy = self.href.copy()
        if isinstance(copy, Symbol):
            group = Group(**copy.attrib)
            group.extend(copy)
            copy = group
        copy.transform *= self.transform
        copy.style = self.style + copy.style
        self.replace_with(copy)
        copy.set_random_ids()
        return copy


class ClipPath(Group):
    """A path used to clip objects"""
    tag_name = 'clipPath'


class Defs(BaseElement):
    """An header defs element, one per document"""
    tag_name = 'defs'

class StyleElement(BaseElement):
    """A CSS style element containing multiple style definitions"""
    tag_name = 'style'

    def set_text(self, content):
        """Sets the style content text as a CDATA section"""
        self.text = etree.CDATA(str(content))

    def stylesheet(self):
        """Return the StyleSheet() object for the style tag"""
        return StyleSheet(self.text, callback=self.set_text)

class Script(BaseElement):
    """A javascript tag in SVG"""
    tag_name = 'script'

    def set_text(self, content):
        """Sets the style content text as a CDATA section"""
        self.text = etree.CDATA(str(content))

class Desc(BaseElement):
    """Description element"""
    tag_name = 'desc'

class Title(BaseElement):
    """Title element"""
    tag_name = 'title'

class NamedView(BaseElement):
    """The NamedView element is Inkscape specific metadata about the file"""
    tag_name = 'sodipodi:namedview'

    current_layer = property(lambda self: self.get('inkscape:current-layer'))

    @property
    def center(self):
        """Returns view_center in terms of document units"""
        return Vector2d(self.root.unittouu(self.get('inkscape:cx') or 0),
                        self.root.unittouu(self.get('inkscape:cy') or 0))

    def get_guides(self):
        """Returns a list of guides"""
        return self.findall('sodipodi:guide')

    def new_guide(self, position, orient=True, name=None):
        """Creates a new guide in this namedview"""
        if orient is True:
            elem = Guide().move_to(0, position, (0, 1))
        elif orient is False:
            elem = Guide().move_to(position, 0, (1, 0))
        if name:
            elem.set('inkscape:label', str(name))
        return self.add(elem)


class Guide(BaseElement):
    """An inkscape guide"""
    tag_name = 'sodipodi:guide'

    is_horizontal = property(lambda self: self.get('orientation').startswith('0,') and not
                                          self.get('orientation') == '0,0')
    is_vertical = property(lambda self: self.get('orientation').endswith(',0'))
    point = property(lambda self: Vector2d(self.get('position')))

    @classmethod
    def new(cls, pos_x, pos_y, angle, **attrs):
        guide = super(Guide, cls).new(**attrs)
        guide.move_to(pos_x, pos_y, angle=angle)
        return guide

    def move_to(self, pos_x, pos_y, angle=None):
        """
        Move this guide to the given x,y position,

        Angle may either be a float or integer, which will change the orientation.
        Or a pair of numbers (tuple) which will be set as the orientation directly.
        """
        self.set('position', "{:g},{:g}".format(float(pos_x), float(pos_y)))
        if isinstance(angle, str):
            if ',' not in angle:
                angle = float(angle)

        if isinstance(angle, (float, int)):
            # Generate orientation from angle
            angle = (math.sin(math.radians(angle)), -math.cos(math.radians(angle)))

        if isinstance(angle, (tuple, list)) and len(angle) == 2:
            angle = "{:g},{:g}".format(*angle)

        self.set('orientation', angle)
        return self

class Metadata(BaseElement):
    """Inkscape Metadata element"""
    tag_name = 'metadata'

class ForeignObject(BaseElement):
    """SVG foreignObject element"""
    tag_name = 'foreignObject'

class TextElement(ShapeElement):
    """A Text element"""
    tag_name = 'text'
    x = property(lambda self: float(self.get('x', 0)))
    y = property(lambda self: float(self.get('y', 0)))

    def get_path(self):
        return Path()

    def tspans(self):
        """Returns all children that are tspan elements"""
        return self.findall('svg:tspan')

    def get_text(self, sep="\n"):
        """Return the text content including tspans"""
        nodes = [self] + list(self.tspans())
        return sep.join([elem.text for elem in nodes if elem.text is not None])

    def bounding_box(self, transform=None):
        """
        Returns a horrible bounding box that just contains the coord points
        of the text without width or height (which is impossible to calculate)
        """
        transform = self.transform * transform
        x, y = transform.apply_to_point((self.x, self.y))
        bbox = BoundingBox(x, y)
        for tspan in self.tspans():
            bbox += tspan.bounding_box(transform)
        return bbox

class TextPath(ShapeElement):
    """A textPath element"""
    tag_name = 'textPath'

    def get_path(self):
        return Path()

class Tspan(ShapeElement):
    """A tspan text element"""
    tag_name = 'tspan'
    x = property(lambda self: float(self.get('x', 0)))
    y = property(lambda self: float(self.get('y', 0)))

    @classmethod
    def superscript(cls, text):
        """Adds a superscript tspan element"""
        return cls(text, style="font-size:65%;baseline-shift:super")

    def get_path(self):
        return Path()

    def bounding_box(self, transform=None):
        """
        Returns a horrible bounding box that just contains the coord points
        of the text without width or height (which is impossible to calculate)
        """
        transform = self.transform * transform
        x1, y1 = transform.apply_to_point((self.x, self.y))
        fontsize = convert_unit(self.style.get('font-size', '1em'), 'px')
        y2 = y1 + float(fontsize)
        x2 = x1 + 0 # XXX This is impossible to calculate!
        return BoundingBox((x1, x2), (y1, y2))

class Marker(Group):
    """The <marker> element defines the graphic that is to be used for drawing arrowheads
     or polymarkers on a given <path>, <line>, <polyline> or <polygon> element."""
    tag_name = 'marker'

class Switch(BaseElement):
    """A switch element"""
    tag_name = 'switch'

class Grid(BaseElement):
    """A namedview grid child"""
    tag_name = 'inkscape:grid'


class SVGfont(BaseElement):
    """An svg font element"""
    tag_name = 'font'


class FontFace(BaseElement):
    """An svg font font-face element"""
    tag_name = 'font-face'


class Glyph(PathElement):
    """An svg font glyph element"""
    tag_name = 'glyph'


class MissingGlyph(BaseElement):
    """An svg font missing-glyph element"""
    tag_name = 'missing-glyph'


class Symbol(BaseElement):
    """SVG symbol element"""
    tag_name = 'symbol'


class PathEffect(BaseElement):
    """Inkscape LPE element"""
    tag_name = 'inkscape:path-effect'
