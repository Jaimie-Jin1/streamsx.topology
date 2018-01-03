# coding=utf-8
# Licensed Materials - Property of IBM
# Copyright IBM Corp. 2016,2017
"""
Schemas for streams.

********
Overview
********

On a structured stream a tuple is a sequence of attributes,
and an attribute is a named value of a specific type.

The supported types are defined by IBM Streams Streams Processing Language (SPL).

"""
from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
from builtins import *

import collections
import enum
import io
import itertools
import token
import tokenize


def is_common(schema):
    """
    Is `schema` an common schema
    Args:
        schema: Scheme to test.

    Returns:
        bool: ``True`` if schema is a common schema, otherwise ``False``.

    """
    if isinstance(schema, StreamSchema):
        return schema.schema() in _SCHEMA_COMMON
    if isinstance(schema, CommonSchema):
        return True
    if isinstance(schema, str):
        return is_common(StreamSchema(schema))
    return False

_SCHEMA_PENDING = '<pending>'
def _is_pending(schema):
    return isinstance(schema, StreamSchema) and schema.schema() == _SCHEMA_PENDING

# Parses a schema of the form 'tuple<...>'
# _parse returns a list of the schema attributes,
# each attribute is a python tuple of:
# (type, name)
# with type being
#    primitive type (str), e.g. 'int32'
#    collection type (tuple), e.g. ('list', 'int32')
#    nested tuple type (tuple), e.g. ('tuple', [('int32', 'a'), ('float64', 'b')])
# This is an internal api.
#
class _SchemaParser(object):
    """Class for parsing schemas."""
    _SPL_PRIMITIVE_TYPES = { 'boolean',
                         'uint8', 'uint16', 'uint32', 'uint64',
                         'int8', 'int16', 'int32', 'int64',
                         'float32', 'float64',
                         'complex32', 'complex64',
                         'decimal32', 'decimal64', 'decimal128',
                         'rstring', 'ustring',
                         'timestamp', 'blob', 'xml'}

    _SPL_COLLECTION_TYPES = { 'list', 'set'}

    def __init__(self, schema):
        self.schema = schema
        self._type = []

    def _parse_error(self, token):
        raise SyntaxError("Invalid schema:" + self.schema + " token " + str(token))

    def _req_op(self, which):
        token = next(self.tokens)
        if token[0] != tokenize.OP or which != token[1]:
            self._parse_error(token)

    def _parse(self):
        schema = self.schema.replace(">>", ' > > ')
        schema = schema.replace('<<', ' < < ')

        ios = io.StringIO(schema).readline
        self.tokens = tokenize.generate_tokens(ios)
        self._parse_tuple(self._type, next(self.tokens))
        endtoken = next(self.tokens)
        if not endtoken[0] == token.ENDMARKER:
            self._parse_error(endtoken)
        return self._type

    def _parse_tuple(self, _type, token):
        if token[0] != tokenize.NAME or 'tuple' != token[1]:
            self._parse_error(token)
        self._req_op('<')
    
        token = None
        while True:
            token = next(self.tokens)
            if token[0] == tokenize.OP:
                if token[1] == ',':
                    continue
                if token[1] == '>':
                    break
                self._parse_error(token)

            if token[0] == tokenize.NAME:
                self._parse_attribute_type(_type, token)
                continue

            self._parse_error(token)

    def _parse_type(self, attr_type):
        if attr_type[0] != tokenize.NAME:
            self._parse_error(attr_type)

        if 'tuple' == attr_type[1]:
            nested_tuple = []
            self._parse_tuple(nested_tuple, attr_type)
            return ('tuple', nested_tuple)

        if 'map' == attr_type[1]:
            self._req_op('<')
            key_type = self._parse_type(next(self.tokens))
            self._req_op(',')
            value_type = self._parse_type(next(self.tokens))
            self._req_op('>')
            bound = self._parse_optional_bounded()
            return ('map', (key_type, value_type), bound)
            
        if attr_type[1] in _SchemaParser._SPL_PRIMITIVE_TYPES:
            if attr_type[1] == 'rstring':
                bound = self._parse_optional_bounded()
                if bound is not None:
                    return 'rstring' + bound
            return attr_type[1]

        if attr_type[1] in _SchemaParser._SPL_COLLECTION_TYPES:
            self._req_op('<')
            element_type = self._parse_type(next(self.tokens))
            self._req_op('>')
            bound = self._parse_optional_bounded()
            return (attr_type[1], element_type, bound)

        self._parse_error(attr_type)

    def _parse_attribute_type(self, _type, attr_type):
        if attr_type[0] != tokenize.NAME:
            self._parse_error(attr_type)

        attr_type = self._parse_type(attr_type)

        attr = (attr_type, self._parse_attribute_name())
        _type.append(attr)

    def _parse_attribute_name(self):
        attr_name = next(self.tokens)
        if attr_name[0] != tokenize.NAME:
            self._parse_error(attr_name)
        return attr_name[1]

    def _parse_optional_bounded(self):
        token = next(self.tokens)
        if token[0] == tokenize.OP and '[' == token[1]:
            bound_info = next(self.tokens)
            if bound_info[0] != tokenize.NUMBER:
                self._parse_error(bound_info)
            bound = str(int(bound_info[0]))
            self._req_op(']')
            return bound
        else:
            # push back the token
            self.tokens = itertools.chain([token], self.tokens)
            return None

def _stream_schema(schema):
    if isinstance(schema, StreamSchema):
        return schema
    if isinstance(schema, CommonSchema):
        return schema
    return StreamSchema(str(schema))

def _attribute_names(types):
    names = []
    for attr in types:
        names.append(attr[1])
    return names

_SCHEMA_PYTHON_OBJECT = 'tuple<blob __spl_po>'
_SCHEMA_STRING = 'tuple<rstring string>'
_SCHEMA_JSON = 'tuple<rstring jsonString>'
_SCHEMA_BINARY = 'tuple<blob binary>' # not yet supported
_SCHEMA_XML = 'tuple<xml document>' # not yet supported

_SCHEMA_COMMON = frozenset([_SCHEMA_PYTHON_OBJECT, _SCHEMA_JSON, _SCHEMA_STRING, _SCHEMA_BINARY, _SCHEMA_XML])

_SCHEMA_COMMON_STYLES = {_SCHEMA_PYTHON_OBJECT:object, _SCHEMA_STRING: str, _SCHEMA_JSON: dict, _SCHEMA_BINARY:None, _SCHEMA_XML: None }

class StreamSchema(object) :
    """Defines a schema for a structured stream.

    On a structured stream a tuple is a sequence of attributes,
    and an attribute is a named value of a specific type.

    The supported types are defined by IBM Streams Streams Processing
    Language and include such types as `int8`, `int16`, `rstring`
    and `list<float32>`.

    A schema is defined with the syntax ``tuple<type name [,...]>``,
    for example::

        tuple<rstring id, timestamp ts, float64 value>

    represents a schema with three attributes suitable for a sensor reading.

    The complete list of supported types are:

    ============================  ======================================  =====================
    Type                          Description                             Python representation

    ============================  ======================================  =====================
    ``boolean``                   True or False                           ``bool``
    ``int8``                      8-bit signed integer                    ``int``
    ``int16``                     16-bit signed integer                   ``int``
    ``int32``                     32-bit signed integer                   ``int``
    ``int64``                     64-bit signed integer                   ``int``
    ``uint8``                     8-bit unsigned integer                  ``int``
    ``uint16``                    16-bit unsigned integer                 ``int``
    ``uint32``                    32-bit unsigned integer                 ``int``
    ``uint64``                    64-bit unsigned integer                 ``int``
    ``float32``                   32-bit binary floating point            ``float``
    ``float64``                   64-bit binary floating point            ``float``
    ``decimal32``                 32-bit decimal floating point           ``decimal.Decimal``
    ``decimal64``                 64-bit decimal floating point           ``decimal.Decimal``
    ``decimal128``                128-bit decimal floating point          ``decimal.Decimal``
    ``complex32``                 complex using `float32` values          ``complex``
    ``complex64``                 complex using `float64` values          ``complex``
    ``timestamp``                 Timestamp with nanosecond resolution    :py:class:`~streamsx.spl.types.Timestamp`
    ``rstring``                   Character string (UTF-8 encoded)        ``str`` (``unicode`` 2.7)
    ``rstring[N]``                Bounded string (UTF-8 encoded)          ``str`` (``unicode`` 2.7)
    ``ustring``                   Character string (UTF-16 encoded)       ``str`` (``unicode`` 2.7)
    ``blob``                      Sequence of bytes                       ``memoryview``
    ``list<T>``                   List with elements of type `T`          ``list``
    ``list<T>[N]``                Bounded list, limted to N elements      ``list``
    ``set<T>``                    Set with elements of type `T`           ``set``
    ``set<T>[N]``                 Bounded set, limted to N elements       ``set``
    ``map<K,V>``                  Map with typed keys and values          ``dict``
    ``map<K,V>[N]``               Bounded map, limted to N pairs          ``dict``
 
    ``enum{id [,...]}``           Enumeration                             Not supported
    ``xml``                       XML value                               Not supported
    ``tuple<type name [, ...]>``  Nested tuple                            Not supported
    ============================  ======================================  =====================

    When a type is not supported in Python it can only be used in a schema used for streams produced and consumed by invocation of SPL operators.

    A `StreamSchema` can be created by passing a string of the
    form ``tuple<...>`` or by passing the name of an SPL type from
    an SPL toolkit, for example ``com.ibm.streamsx.transportation.vehicle::VehicleLocation``.

    Attribute names must start with an ASCII letter or underscore, followed by ASCII letters, digits, or underscores.

    When a tuple on a structured scheme is passed into Python it
    is converted to a `dict` containing all attributes of the tuple.
    Each key is the attribute name as a `str` and
    the value is the attribute's value.

    When a Python object is submitted to a structured stream,
    for example as the return from the function invoked in a 
    :py:meth:`~streamsx.topology.topology.Stream.map` with the
    `schema` parameter set, it must be:
         * A Python `dict`. Attributes are set by name using value in the dict for the name. If a value does not exist (the name does not exist as a key) or is set to `None` then the attribute has its default value, zero, false, empty list or string etc.
         * A Python `tuple`. Attributes are set by position, with the first attribute being the value at index 0 in the Python `tuple`. If a value does not exist (the tuple has less values than the structured schema) or is set to `None` then the attribute has its default value, zero, false, empty list or string etc.

    Args:
        schema(str): Schema definition. Either a schema definition or the name of an SPL type.
    """
    def __init__(self, schema):
        schema = schema.strip()
        self.__spl_type = not schema.startswith("tuple<")
        self.__schema=schema
        if not self.__spl_type:
            parser = _SchemaParser(schema)
            self._types = parser._parse()

        self._style = self._default_style()
            
    def _set(self, schema):
        """Set a schema from another schema"""
        if isinstance(schema, CommonSchema):
            self.__spl_type = False
            self.__schema = schema.schema()
            self._style = self._default_style()
        else:
            self.__spl_type = schema.__spl_type
            self.__schema = schema.__schema
            self._style = schema._style

    @property
    def style(self):
        """Style stream tuples will be passed into a callable.

        For the common schemas the style is fixed as:
            * ``CommonSchema.Python`` - ``object`` - Stream tuples are arbitrary objects.
            * ``CommonSchema.String`` - ``str`` - Stream tuples are strings.
            * ``CommonSchema.Json`` - ``dict`` - Stream tuples are a ``dict`` that represents the JSON object.

        For a structured schema the supported styles are:
            * ``dict`` - Stream tuples are passed as a ``dict`` with the key being the attribute name and
                and the value the attribute value. This is the default.
                * E.g. with a schema of ``tuple<rsting id, float32 value>`` a value is passed as
                    ``{'id':'TempSensor', 'value':20.3}``.
            * ``tuple`` - Stream tuples are passed as a ``tuple`` with the value being the attributes
                value in order. A schema is set to pass stream tuples as tuples using :py:meth:`as_tuple`.
                * E.g. with a schema of ``tuple<rsting id, float32 value>`` a value is passed as
                    ``('TempSensor', 20.3)``.


        Structured schemas may be changed to pass the stream tuple as a ``tuple`` using

        Returns:
            type: Class of tuples that will be passed into callables.

        .. versionadded:: 1.8
        """
        return self._style

    def _default_style(self):
        if self.__spl_type:
            return dict
        return _SCHEMA_COMMON_STYLES[self.schema()] if is_common(self) else dict

    def _copy(self, style=None):
        if style is None:
            return self
        if self._style == style:
            return self
        # Cannot change style of common schemas
        if is_common(self):
            return self
        c = StreamSchema(self.schema())
        c._style = style
        return c

    def as_tuple(self):
        """
        Create a structured schema that will pass stream tuples into callables as ``tuple`` instances.

        If this instance represents a common schema then it will be returned
        without modification. Stream tuples with common schemas are always passed according
        to their definition.

        Returns:
            StreamSchema: Schema passing stream tuples as ``tuple`` if allowed.

        .. versionadded:: 1.8
        """
        return self._copy(tuple)

    def as_dict(self):
        """
        Create a structured schema that will pass stream tuples into callables as ``dict`` instances.
        This allows a return to the default calling style for a structured schema.

        If this instance represents a common schema then it will be returned
        without modification. Stream tuples with common schemas are always passed according
        to their definition.

        Returns:
            StreamSchema: Schema passing stream tuples as ``dict`` if allowed.

        .. versionadded:: 1.8
        """
        return self._copy(dict)

    def schema(self):
        """Private method. May be removed at any time."""
        return self.__schema

    def __str__(self):
        """Private method. May be removed at any time."""
        return self.__schema

    def spl_json(self):
        """Private method. May be removed at any time."""
        _splj = {}
        _splj["type"] = 'spltype'
        _splj["value"] = self.schema()
        return _splj

    def extend(self, schema):
        """
        Extend a structured schema by another.

        For example extending ``tuple<rstring id, timestamp ts, float64 value>``
        with ``tuple<float32 score>`` results in ``tuple<rstring id, timestamp ts, float64 value, float32 score>``.

        Args:
            schema(StreamSchema): Schema to extend this schema by.

        Returns:
            StreamSchema: New schema that is an extension of this schema.
        """
        if self.__spl_type:
           raise TypeError("Not supported for declared SPL types")
        base = self.schema()
        extends = schema.schema()
        new_schema = base[:-1] + ',' + extends[6:]
        return StreamSchema(new_schema)

    def __hash__(self):
        return hash(self.schema())

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.schema() == other.schema()
        return False

    def __ne__(self, other):
        return not self.__eq__(other)

    @staticmethod
    def _fnop_style(schema, op, name):
        """Set an operator's parameter representing the style of this schema."""
        if is_common(schema):
            if name in op.params:
                del op.params[name]
            return
        if _is_pending(schema):
            ntp = 'pending'
        elif schema.style == tuple:
            ntp = 'tuple'
        elif schema.style == dict:
            ntp = 'dict'
        else:
            return
        op.params[name] = ntp


@enum.unique
class CommonSchema(enum.Enum):
    """
    Common stream schemas for interoperability within Streams applications.

    Streams application can publish streams that are subscribed to by other applications.
    Use of common schemas allow streams connections regardless of the application implementation language.

    Python applications publish streams using :py:meth:`~streamsx.topology.topology.Stream.publish`
    and subscribe using :py:meth:`~streamsx.topology.topology.Topology.subscribe`.
    
     * :py:const:`Python` - Stream constains Python objects.
     * :py:const:`Json` - Stream contains JSON objects.
     * :py:const:`String` - Stream contains strings.
     * :py:const:`Binary` - Stream contains binary tuples.
     * :py:const:`XML` - Stream contains XML documents.
    """
    Python = StreamSchema(_SCHEMA_PYTHON_OBJECT)
    """
    Stream where each tuple is a Python object. Each object
    must be picklable to allow execution in a distributed
    environment where streams can connect processes
    running on the same or different resources.

    Python streams can only be used by Python applications.
    """
    Json = StreamSchema(_SCHEMA_JSON)
    """
    Stream where each tuple is logically a JSON object.

    `Json` can be used as a natural interchange format between Streams applications
    implemented in different programming languages. All languages supported by
    Streams support publishing and subscribing to JSON streams.

    A Python callable receives each tuple as a `dict` as though it was
    created from ``json.loads(json_formatted_str)`` where `json_formatted_str`
    is the JSON formatted representation of tuple.

    Python objects that are to be converted to JSON objects
    must be supported by `JSONEncoder`. If the object is not a `dict`
    then it will be converted to a JSON object with a single key `payload`
    containing the value.
    """
    String = StreamSchema(_SCHEMA_STRING)
    """
    Stream where each tuple is a string.

    `String` can be used as a natural interchange format between Streams applications
    implemented in different programming languages. All languages supported by
    Streams support publishing and subscribing to string streams.

    A Python callable receives each tuple as a `str` object.

    Python objects are converted to strings using ``str(obj)``.
    """
    Binary = StreamSchema(_SCHEMA_BINARY)
    """
    Stream where each tuple is a binary object (sequence of bytes).

    .. warning:: `Binary` is not yet supported for Python applications.
    """
    XML = StreamSchema(_SCHEMA_XML)
    """
    Stream where each tuple is an XML document.

    .. warning:: `XML` is not yet supported for Python applications.
    """

    def schema(self):
        """Private method. May be removed at any time."""
        return self.value.schema()

    def spl_json(self):
        """Private method. May be removed at any time."""
        return self.value.spl_json()

    def extend(self, schema):
        """Extend a structured schema by another.

        Args:
            schema(StreamSchema): Schema to extend this schema by.

        Returns:
            StreamSchema: New schema that is an extension of this schema.
        """
        return self.value.extend(schema)

    def __str__(self):
        return str(self.schema())

