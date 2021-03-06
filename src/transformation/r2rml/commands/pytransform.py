#!/usr/bin/python
# -*- coding: utf-8 -*-

from typing import Dict, Tuple, List, Set, Union, Optional

from transformation.models.table_schema import Schema


class PyTransformNewColumnCmd:
    def __init__(self, input_attr_paths: List[str], new_attr_name: str, code: str, default_error_value) -> None:
        self.input_attr_paths = input_attr_paths
        self.new_attr_name = new_attr_name
        self.code = code
        self.default_error_value = default_error_value

    def to_dict(self):
        return {
            "_type_": "PyTransformNewColumn",
            "input_attr_paths": self.input_attr_paths,
            "new_attr_name": self.new_attr_name,
            "code": self.code,
            "default_error_value": self.default_error_value
        }

    @staticmethod
    def from_dict(obj: dict):
        return PyTransformNewColumnCmd(obj['input_attr_paths'], obj['new_attr_name'], obj['code'],
                                       obj['default_error_value'])


# noinspection PyUnresolvedReferences
def get_value(attr_path: str):
    return globals['__input_paths_val__'][attr_path]


globals = {"getValue": get_value, "__row__": None, "__input_paths_val__": None}


def pytransform_(original_row: dict, prefix_sep_path: str, row: dict, schema: Schema, prefix_attr_path: List[str],
                 input_attrs: List[str], new_attr: str, code: str) -> None:
    if len(prefix_attr_path) == 0:
        if len(input_attrs) > 1:
            # TODO: need to figure out how to support this
            assert all(not isinstance(row[attr], list) for attr in input_attrs), "Not support transform data from 2 list"

        if isinstance(row[input_attrs[0]], list):
            # only one input
            key = prefix_sep_path + input_attrs[0]
            results = []
            globals['__row__'] = original_row
            globals['__input_paths_val__'] = {key: None}
            for val in row[input_attrs[0]]:
                locals = {}
                globals['__input_paths_val__'][key] = str(val or "")
                exec(code, globals, locals)
                results.append(locals['__return__'])
            row[new_attr] = results
        else:
            locals = {}
            globals['__row__'] = original_row
            # so by the default, a NULL column is an empty string, everything is string!
            globals['__input_paths_val__'] = {prefix_sep_path + attr: str(row[attr] or "") for attr in input_attrs}
            exec(code, globals, locals)
            row[new_attr] = locals['__return__']
    else:
        attr = prefix_attr_path[0]
        schema = schema.attributes[attr]
        if schema.is_list_of_objects:
            for r in row[attr]:
                pytransform_(original_row, prefix_sep_path, r, schema, prefix_attr_path[1:], input_attrs, new_attr,
                             code)
        else:
            pytransform_(original_row, prefix_sep_path, row[attr], schema, prefix_attr_path[1:], input_attrs, new_attr,
                         code)
