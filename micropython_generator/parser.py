#  Copyright 2023-2025 $author, All rights reserved.
#
#  For licensing terms, Please find the licensing terms in the closest
#  LICENSE.txt file in this repository going up the directory tree.
#

import argparse
import re
import os
import sys
from dataclasses import dataclass
from typing import List, Optional, Union, Iterable, TextIO

from python_utilities.cpp import filter_code
from .config import TypeTag, TagConfig, ParserConfig, resolve_include_path, Config


@dataclass
class Attribute:
    name: str

@dataclass
class StringAttribute:
    name: str
    value: str

@dataclass
class SubAttribute:
    name: str
    values: dict[str, Union[Attribute, StringAttribute, 'SubAttribute']]

AttributeTypes = Union[Attribute, StringAttribute, SubAttribute]

class Property:
    def __init__(self) -> None:
        self.path: str = None
        self.line: int = None
        self.property_type: Optional[str] = None
        self.name: Optional[str] = None
        self.python_name: Optional[str] = None
        self.export_attributes: dict[str, AttributeTypes] = {}
        self.is_const: bool = False
        self.is_constexpr: bool = False
        self.is_extern: bool = False
        self.is_static: bool = False
        self.attributes: str = ""
        self.module: Optional[str] = None
        self.requires: list[str] = []
        self.value: Optional[str] = None

class Parameter:
    def __init__(self, name, arg_type=None, value=None) -> None:
        self.arg_type: str = arg_type
        self.name: str = name
        self.python_name: Optional[str] = None
        self.value: str = value
        self.is_const: bool = False
        self.export_attributes: dict[str, AttributeTypes] = {}
        self.attributes: list[str] = []

class Function:
    def __init__(self) -> None:
        self.path: str = None
        self.line: int = None
        self.return_type: Optional[str] = None
        self.name: Optional[str] = None
        self.python_name: Optional[str] = None
        self.export_attributes: dict[str, AttributeTypes] = {}
        self.parameters: list[Parameter] = []
        self.is_const: bool = False
        self.is_constexpr: bool = False
        self.is_static: bool = False
        self.is_explicit: bool = False
        self.is_extern: bool = False
        self.is_inline: bool = False
        self.is_virtual: bool = False
        self.attributes: str = ""
        self.module: Optional[str] = None
        self.requires: list[str] = []

class Operator:
    def __init__(self) -> None:
        self.path: str = None
        self.line: int = None
        self.return_type: Optional[str] = None
        self.operator: Optional[str] = None
        self.export_attributes: dict[str, AttributeTypes] = {}
        self.parameters: list[Parameter] = []
        self.is_const: bool = False
        self.is_constexpr: bool = False
        self.is_static: bool = False
        self.is_extern: bool = False
        self.is_inline: bool = False
        self.is_virtual: bool = False
        self.attributes: str = ""
        self.module: Optional[str] = None
        self.requires: list[str] = []

@dataclass
class BaseType:
    name: str = ""
    access: str = ""

class Component:
    def __init__(self) -> None:
        self.path: str = None
        self.line: int = None
        self.component_type: Optional[str] = None
        self.wrapper_type: Optional[str] = None
        self.name: Optional[str] = None
        self.python_name: Optional[str] = None
        self.base_types: list[BaseType] = []
        self.access: Optional[str] = None
        self.component_tag: Optional[TypeTag] = None
        self.export_attributes: dict[str, AttributeTypes] = {}
        self.properties: list[Property] = []
        self.functions: list[Function] = []
        self.operators: list[Operator] = []
        self.attributes: str = ""
        self.constructors: list[Function] = []
        self.destructors: list[Function] = []
        self.module: Optional[str] = None
        self.requires: list[str] = []
        self.path = None

def parse_base_types(base_types: Optional[str], parser_config: ParserConfig) -> Iterable[BaseType]:
    if not base_types:
        return []

    open_templates = 0
    base_type_split = base_types.split(",")
    for i in range(len(base_type_split)):
        entry = base_type_split[i]
        if entry is None:
            continue
        j = i
        while True:
            open_templates += entry.count("<") - entry.count(">")
            if open_templates == 0:
                break
            j += 1
            entry += "," + base_type_split[j]
            base_type_split[j] = None
        if match := parser_config.base_types_re.match(entry):
            if match.group("access") is None:
                yield BaseType(match.group("base_class"))
            else:
                yield BaseType(match.group("base_class"), match.group("access"))

def parse_export_attributes(attribute_str: str) -> dict[str, AttributeTypes]:
    if not attribute_str:
        return {}
    attributes: list[str] = attribute_str.split(",")
    if attributes[0].strip() == "":
        attributes = []
    if len(attributes) > 0 and attributes[-1].strip() == "":
        attributes = attributes[:-1]

    export_attributes = {}
    for attribute in attributes:
        if "(" in attribute:
            attribute_split = attribute.strip().split("(")
            attribute_name = attribute_split[0].strip()
            export_attributes[attribute_name] = SubAttribute(attribute_name, parse_export_attributes(attribute_split[1][:-1].strip()))
        elif "=" in attribute:
            attribute_split = attribute.split("=")
            attribute_name = attribute_split[0].strip()
            value = attribute_split[1].strip()
            if value.startswith("\"") or value.startswith("'"):
                value = value[1:-1].strip()
            export_attributes[attribute_name] = StringAttribute(attribute_name, value)
        else:
            attribute_name = attribute.strip()
            export_attributes[attribute_name] = Attribute(attribute_name)
    return export_attributes

def parse_parameters(params, path, line):
    if params:
        for param in params.split(","):
            param_split = param.strip().split("=")
            param_kvp = param_split[0].split(" ")
            # Only supports pre-type const for now
            is_const = False
            attribute_str = None
            if param_kvp[0].startswith("TinyParam("):
                attribute_str = param_kvp[0][10:]
                while not attribute_str.endswith(")"):
                    attribute_str += ", " + param_kvp.pop(0)
                attribute_str = attribute_str[:-1]
                param_kvp = param_kvp[1:]

            if param_kvp[0] == "const":
                param_kvp = param_kvp[1:]
                is_const = True

            param_type = param_kvp[0].strip()
            param_name = param_kvp[1].strip()
            while param_name.startswith("&") or param_name.startswith("*"):
                param_type = param_type + param_name[0]
                param_name = param_name[1:]
            if len(param_split) == 1:
                param = Parameter(param_name, param_type)
            else:
                param = Parameter(param_name, param_type, param_split[1].strip())
            if is_const:
                param.is_const = True
            if attribute_str:
                param.export_attributes = parse_export_attributes(attribute_str)

            yield param

def check_type(type_str: str, reference: str, file: str, line: str):
    if type_str.endswith("&&"):
        print(f"{file}:{line}:Error: Rvalue references (&&) not supported for {reference} of type {type_str}.", file=sys.stderr)
        return False
    if type_str.endswith("&*"):
        print(f"{file}:{line}:Error: Pointer to reference not supported for {reference} of type {type_str}.", file=sys.stderr)
        return False
    if type_str.endswith("*&"):
        print(f"{file}:{line}:Error: Reference to pointer not supported for {reference} of type {type_str}.", file=sys.stderr)
        return False
    if type_str.endswith("**"):
        print(f"{file}:{line}:Error: Pointer to pointer not supported for {reference} of type {type_str}.", file=sys.stderr)
        return False
    return True

def analyze_file(path: str, parser_config: ParserConfig) -> Iterable[Component]:
    with (open(path, "r") as fd):
        global_component = None
        current_namespace: Optional[str] = None
        current_component: Optional[Component] = None
        current_component_constructor_re = None
        current_component_destructor_re = None
        component_brace_count = 0
        current_property: Optional[Property] = None
        current_function: Optional[Function] = None
        current_operator: Optional[Operator] = None
        current_tag: Optional[TypeTag] = None
        current_module: Optional[str] = None
        requires = []
        for line_index, line in enumerate(filter_code(fd.readlines())):
            if match := parser_config.header_re.match(line):
                requires.append(match.group("include"))
                continue

            if match := parser_config.module_re.match(line):
                if current_component:
                    raise Exception("Modules cannot be defined inside components")
                if current_property:
                    raise Exception("Modules cannot be defined inside properties")
                if current_function:
                    raise Exception("Modules cannot be defined inside functions")
                if global_component:
                    global_component.module = current_module
                    yield global_component
                    global_component = Component()
                    global_component.path = path
                current_module = match.group("name")
                continue

            if match := parser_config.namespace_re.match(line):
                current_namespace = match.group("name")
                continue

            if current_component:
                component_brace_count += line.count("{") - line.count("}")
                if component_brace_count < 1:
                    yield current_component
                    current_component = None

            for tag, type_re in parser_config.type_res:
                if match := type_re.match(line):
                    current_tag = tag
                    break
            if match:
                if current_component:
                    yield current_component
                current_component = Component()
                current_component.export_attributes = parse_export_attributes(match.group("export_attrs"))
                current_component.component_tag = current_tag
                current_component.module = current_module
                current_component.requires = requires
                line = match.group("attr_inline")
                component_brace_count = line.count("{") - line.count("}") + 1

            if match := parser_config.type_decl_re.match(line):
                if current_component is not None:
                    current_component.component_type = match.group("type")
                    current_component.name = match.group("name")
                    current_component_constructor_re = parser_config.get_constructor_re(current_component.name)
                    current_component_destructor_re = parser_config.get_destructor_re(current_component.name)
                    if current_namespace:
                        current_component.name = current_namespace + "::" + current_component.name
                    current_component.base_types = list(parse_base_types(match.group("base_types"), parser_config))
                    current_component.attributes = match.group("attributes")
                    current_component.path = path
                    current_component.line = line_index
                    component_brace_count -= 1
                    continue

            if current_component_constructor_re is not None:
                if match := current_component_constructor_re.match(line):
                    if current_component is None:
                        raise Exception(f"Constructor found outside of component in line: {line_index}")
                    constructor = Function()
                    constructor.parameters = list(parse_parameters(match.group("parameters"), path, line))
                    for param in constructor.parameters:
                        if param.arg_type.endswith("&&") or param.arg_type.endswith("&*") or param.arg_type.endswith("*&") or param.arg_type.endswith("**"):
                            break
                    else:
                        constructor.is_constexpr = match.group("constexpr") is not None
                        constructor.is_inline = match.group("inline") is not None
                        constructor.is_explicit = match.group("explicit") is not None
                        constructor.is_virtual = match.group("virtual") is not None
                        constructor.is_const = match.group("qualifier") is not None
                        constructor.attributes = match.group("attributes")
                        constructor.path = path
                        constructor.line = line_index
                        current_component.constructors.append(constructor)
                        line = match.group("attr_inline")

            if current_component_destructor_re is not None:
                if match := current_component_destructor_re.match(line):
                    if current_component is None:
                        raise Exception(f"Destructor found outside of component in line: {line_index}")
                    destructor = Function()
                    destructor.is_inline = match.group("inline") is not None
                    destructor.is_virtual = match.group("virtual") is not None
                    destructor.attributes = match.group("attributes")
                    destructor.path = path
                    destructor.line = line_index
                    current_component.destructors.append(destructor)
                    line = match.group("attr_inline")

            if match := parser_config.property_re.match(line):
                current_property = Property()
                current_property.export_attributes = parse_export_attributes(match.group("export_attrs"))
                current_property.module = current_module
                current_property.requires = requires
                line = match.group("attr_inline")

            if match := parser_config.property_decl_re.match(line):
                if current_property is not None:
                    current_property.property_type = match.group("type")
                    check_type(current_property.property_type, "property", path, line)
                    current_property.name = match.group("name")
                    current_property.is_const = match.group("const") is not None
                    current_property.is_constexpr = match.group("constexpr") is not None
                    current_property.is_static = match.group("static") is not None
                    current_property.is_extern = match.group("extern") is not None
                    current_property.attributes = match.group("attributes")
                    current_property.value = match.group("value")
                    current_property.path = path
                    current_property.line = line_index
                    if current_component is None:
                        if global_component is None:
                            global_component = Component()
                            global_component.path = path
                        if current_namespace is not None:
                            current_property.name = current_namespace + "::" + current_property.name
                        global_component.properties.append(current_property)
                    else:
                        current_component.properties.append(current_property)
                    current_property = None
                    continue

            if match := parser_config.function_re.match(line):
                current_function = Function()
                current_function.export_attributes = parse_export_attributes(match.group("export_attrs"))
                current_function.module = current_module
                current_function.requires = requires
                line = match.group("attr_inline")

            if match := parser_config.function_decl_re.match(line):
                if current_function is not None:
                    current_function.return_type = match.group("return_type")
                    check_type(current_function.return_type, "return", path, line)
                    current_function.name = match.group("name")
                    if match.group("const") is not None:
                        current_function.return_type = f"const {current_function.return_type}"
                    current_function.is_const = match.group("qualifier") is not None
                    current_function.is_constexpr = match.group("constexpr") is not None
                    current_function.is_static = match.group("static") is not None
                    current_function.is_extern = match.group("extern") is not None
                    current_function.is_inline = match.group("inline") is not None
                    current_function.is_virtual = match.group("virtual") is not None
                    current_function.parameters = list(parse_parameters(match.group("parameters"), path, line))
                    current_function.attributes = match.group("attributes")
                    current_function.path = path
                    current_function.line = line_index
                    if current_component is None:
                        if global_component is None:
                            global_component = Component()
                            global_component.path = path
                        if current_namespace is not None:
                            current_function.name = current_namespace + "::" + current_function.name
                        global_component.functions.append(current_function)
                    else:
                        current_component.functions.append(current_function)
                    current_function = None
                    continue

            if match := parser_config.operator_re.match(line):
                current_operator = Operator()
                current_operator.export_attributes = parse_export_attributes(match.group("export_attrs"))
                current_operator.module = current_module
                current_operator.requires = requires
                line = match.group("attr_inline")

            if match := parser_config.operator_decl_re.match(line):
                if current_operator is not None:
                    current_operator.return_type = match.group("return_type")
                    check_type(current_operator.return_type, "return", path, line)
                    current_operator.operator = match.group("operator")
                    if match.group("const") is not None:
                        current_operator.return_type = f"const {current_function.return_type}"
                    current_operator.is_const = match.group("qualifier") is not None
                    current_operator.is_constexpr = match.group("constexpr") is not None
                    current_operator.is_extern = match.group("extern") is not None
                    current_operator.is_inline = match.group("inline") is not None
                    current_operator.is_virtual = match.group("virtual") is not None
                    current_operator.parameters = list(parse_parameters(match.group("parameters"), path, line))
                    current_operator.attributes = match.group("attributes")
                    current_operator.path = path
                    current_operator.line = line_index
                    if current_component is None:
                        if global_component is None:
                            global_component = Component()
                            global_component.path = path
                        global_component.operators.append(current_operator)
                    else:
                        current_component.operators.append(current_operator)
                    current_operator = None
                    continue

        if current_component:
            yield current_component
        if global_component:
            global_component.module = current_module
            yield global_component

def make_python_name(py_name: str, cpp_name: str) -> str:
    if py_name is None:
        namespace_name = cpp_name.rsplit("::", 1)
        return re.sub(r'([A-Z]+)', lambda match: '_' + match.group(1).lower(), namespace_name[-1]).removeprefix("_")
    return py_name
def get_type_name(entry: Union[Component, Function]) -> tuple[str, str, str]:
    if entry.name is None:
        return "", "", ""
    namespace_name = entry.name.rsplit("::", 1)
    namespace = namespace_name[0] + "::" if len(namespace_name) > 1 else ""
    name = namespace_name[-1]
    py_name = make_python_name(entry.python_name, entry.name)
    return namespace, name, py_name
def get_type_without_namespace(name: str) -> str:
    return name.split("::")[-1] if name else None
def get_type_name_without_namespace(name: str) -> str:
    return get_type_without_namespace(name).rstrip("*&") if name else None
def get_non_template_name_without_namespace(name: str) -> str:
    return get_type_name_without_namespace(name).split("<")[0] if name else None

def find_type(name: Optional[str], components: Iterable[Component], dependencies: dict[str, Iterable[Component]]) -> tuple[Optional[str], Optional[Component]]:
    # We can't really have multiple types with the same name in different namespaces anyway,
    # so might as well just assume we'll find the same type again if we strip the namespace.
    if name is None:
        return None, None
    original_name = get_type_without_namespace(name)
    clean_name = get_type_name_without_namespace(name)
    for component in components:
        namespace, type_name, _ = get_type_name(component)
        if type_name == clean_name:
            return namespace + original_name, component
    for dep in dependencies.values():
        for component in dep:
            namespace, type_name, _ = get_type_name(component)
            if type_name == clean_name:
                return namespace + original_name, component
    return name, None
def ensure_namespaced_type_refs(components: Iterable[Component], dependencies: dict[str, Iterable[Component]]) -> None:
    for component in components:
        for prop in component.properties:
            name, _ = find_type(prop.property_type, components, dependencies)
            prop.property_type = name
        for func in component.functions:
            for param in func.parameters:
                name, _ = find_type(param.arg_type, components, dependencies)
                param.arg_type = name
            name, _ = find_type(func.return_type, components, dependencies)
            func.return_type = name
        for op in component.operators:
            for param in op.parameters:
                name, _ = find_type(param.arg_type, components, dependencies)
                param.arg_type = name
            name, _ = find_type(op.return_type, components, dependencies)
            op.return_type = name
        for func in component.constructors:
            for param in func.parameters:
                name, _ = find_type(param.arg_type, components, dependencies)
                param.arg_type = name
            name, _ = find_type(func.return_type, components, dependencies)
            func.return_type = name
def fix_header_references(components: Iterable[Component], config: Config, file = sys.stdout) -> bool:
    success = True
    for component in components:
        component_include = os.path.relpath(os.path.abspath(component.path), os.path.abspath(os.path.dirname(config.target_path.removeprefix("./"))))
        updated_includes = [f"\"{component_include}\""]
        for header in component.requires:
            local_first = not (header.startswith("<") and header.endswith(">"))
            try:
                new_path = resolve_include_path(component.path, header[1:-1], config, local_first)
                updated_includes.append(new_path)
            except Exception as e:
                if header.startswith("<") and header.endswith(">"):
                    #print(f"{component.path}:Warning: {component.name}: {e}", file=file)
                    updated_includes.append(header)
                else:
                    print(f"{component.path}:Error: {component.name}: {e}", file=file)
                    success = False
        component.requires = updated_includes
    return success

def get_custom_type_register(components: Iterable[Component], dependencies: dict[str, Iterable[Component]]) -> dict[str, Component]:
    type_register = {}
    for component in components:
        type_register[get_type_without_namespace(component.name)] = component
    for dep in dependencies.values():
        for component in dep:
            type_register[get_type_without_namespace(component.name)] = component
    return type_register

def validate_components(components: Iterable[Component], dependencies: dict[str, Iterable[Component]]):
    encountered_error: bool = False
    type_list: list[str] = []
    for component in components:
        if component.name is not None:
            name = get_non_template_name_without_namespace(component.name)
            if name in type_list:
                print(f"{component.path}:{component.line}:Error: Value {component.name} already defined.", file=sys.stderr)
                encountered_error = True
            else:
                type_list.append(name)
    for dep in dependencies.values():
        for component in dep:
            if component.name is not None:
                name = get_non_template_name_without_namespace(component.name)
                if name in type_list:
                    print(f"{component.path}:{component.line}:Error: Value {component.name} already defined.", file=sys.stderr)
                    encountered_error = True
                else:
                    type_list.append(name)

    type_list.extend(["void", "int", "float", "double", "bool", "char", "unsigned char", "short", "unsigned short",
                      "long", "unsigned long", "long long", "unsigned long long", "int8_t", "uint8_t", "int16_t",
                      "uint16_t", "int32_t", "uint32_t", "int64_t", "uint64_t", "size_t", "ssize_t", "std::size_t",
                      "std::ssize_t", "std::string", "std::string_view", "std::vector",
                      # Add spans here, span of pair is going to be treated as an immutable dict, span of anything
                      # else as a tuple for performance reasons and clarity. We explicitly don't support lists due
                      # to those requiring write-back if passed to a function.
                      "TISpan", "TIFixedSpan", "TIConstantSpan", "std::span", "span"])

    def is_known_type(type_str: str, reference, path, line):
        nonlocal encountered_error, type_list
        main_type = get_non_template_name_without_namespace(type_str)
        if main_type not in type_list:
            encountered_error = True
            return False
        encountered_error |= not check_type(type_str, reference, path, line)
        return True

    for component in components:
        for constructor in component.constructors:
            for param in constructor.parameters:
                if not is_known_type(param.arg_type, param.name, constructor.path, constructor.line):
                    print(f"{constructor.path}:{constructor.line}:Error: Parameter type {param.arg_type} not found for constructor of {component.name}", file=sys.stderr)
        for function in component.functions:
            for param in function.parameters:
                if not is_known_type(param.arg_type, function.name, function.path, function.line):
                    print(f"{function.path}:{function.line}:Error: Parameter type {param.arg_type} not found for function {function.name} of {component.name}", file=sys.stderr)
            if not is_known_type(function.return_type.removeprefix("const "), function.name, function.path, function.line):
                print(f"{function.path}:{function.line}:Error: Return type {function.return_type} not found for function {function.name} of {component.name}", file=sys.stderr)
        for operator in component.operators:
            for param in operator.parameters:
                if not is_known_type(param.arg_type, operator.operator, operator.path, operator.line):
                    print(f"{operator.path}:{operator.line}:Error: Parameter type {param.arg_type} not found for operator {operator.operator} of {component.name}", file=sys.stderr)
            if not is_known_type(operator.return_type.removeprefix("const "), operator.operator, operator.path, operator.line):
                print(f"{operator.path}:{operator.line}:Error: Return type {operator.return_type} not found for operator {operator.operator} of {component.name}", file=sys.stderr)
        for prop in component.properties:
            if not is_known_type(prop.property_type, prop.name, prop.path, prop.line):
                print(f"{prop.path}:{prop.line}:Error: Property type {prop.property_type} not found for {component.name}", file=sys.stderr)
    return not encountered_error

def print_component(component: Component, file=None):
    if file is None:
        import sys
        file = sys.stdout
    if component.component_tag == "system":
        t = "System"
    elif component.component_tag == "component":
        t = "Component"
    else:
        t = "Value"
    args = ", ".join(str(arg) for arg in component.export_attributes)
    print(f"{t}: {component.name} ({component.component_type}), Base: {component.base_types}, Attributes: {component.attributes}, Module: {component.module}, Python Name: {component.python_name}, Export: {args}", file=file)
    if len(component.requires) > 0:
        requires = ", ".join(str(req) for req in component.requires)
        print(f"    Requires: {requires}", file=file)
    if component.attributes:
        attrs = ", ".join(str(attr) for attr in component.attributes)
        print(f"    Attributes: {attrs}", file=file)

    for constructor in component.constructors:
        mods = []
        if constructor.is_const:
            mods.append("const")
        if constructor.is_constexpr:
            mods.append("constexpr")
        if constructor.is_inline:
            mods.append("inline")
        if constructor.is_virtual:
            mods.append("virtual")
        if constructor.is_virtual:
            mods.append("explicit")
        args = ", ".join(str(arg) for arg in constructor.export_attributes.values())
        print(f"  Constructor: {constructor.name} ({constructor.return_type}), Modifiers: {mods}, Module: {constructor.module}, Python Name: {component.python_name}, Export: {args}", file=file)
        if constructor.attributes:
            attrs = ", ".join(str(attr) for attr in constructor.attributes)
            print(f"    Attributes: {attrs}", file=file)
        for param in constructor.parameters:
            attrs = ", ".join(str(attr) for attr in param.attributes)
            print(f"    Parameter: {param.name} ({param.arg_type}), Default: {param.value}, Args: [{attrs}]", file=file)
    for destructor in component.destructors:
        mods = []
        if destructor.is_inline:
            mods.append("inline")
        if destructor.is_virtual:
            mods.append("virtual")
        args = ", ".join(str(arg) for arg in destructor.export_attributes.values())
        print(f"  Destructor: {destructor.name} ({destructor.return_type}), Modifiers: {mods}, Module: {destructor.module}, Python Name: {component.python_name}, Export: {args}", file=file)
        if destructor.attributes:
            attrs = ", ".join(str(attr) for attr in destructor.attributes)
            print(f"    Attributes: {attrs}", file=file)

    for prop in component.properties:
        mods = []
        if prop.is_const:
            mods.append("const")
        if prop.is_constexpr:
            mods.append("constexpr")
        if prop.is_static:
            mods.append("static")
        if prop.is_extern:
            mods.append("extern")
        mods = ", ".join(mods)
        args = ", ".join(str(arg) for arg in prop.export_attributes.values())
        print(f"  Property: {prop.name} ({prop.property_type}), Modifiers: {mods}, Module: {prop.module}, Python Name: {component.python_name}, Export: {args}", file=file)
        if prop.attributes:
            attrs = ", ".join(str(attr) for attr in prop.attributes)
            print(f"    Attributes: {attrs}", file=file)

    for func in component.functions:
        mods = []
        if func.is_const:
            mods.append("const")
        if func.is_constexpr:
            mods.append("constexpr")
        if func.is_static:
            mods.append("static")
        if func.is_inline:
            mods.append("inline")
        if func.is_virtual:
            mods.append("virtual")
        args = ", ".join(str(arg) for arg in func.export_attributes.values())
        print(f"  Function: {func.name} ({func.return_type}), Modifiers: {mods}, Module: {func.module}, Python Name: {component.python_name}, Export: {args}", file=file)
        if func.attributes:
            attrs = ", ".join(str(attr) for attr in func.attributes)
            print(f"    Attributes: {attrs}", file=file)
        for param in func.parameters:
            attrs = ", ".join(str(attr) for attr in param.attributes)
            print(f"    Parameter: {param.name} ({param.arg_type}), Default: {param.value}, Args: [{attrs}]", file=file)

    for op in component.operators:
        mods = []
        if prop.is_const:
            mods.append("const")
        if prop.is_constexpr:
            mods.append("constexpr")
        if prop.is_static:
            mods.append("static")
        args = ", ".join(str(arg) for arg in op.export_attributes.values())
        print(f"  Operator: {op.operator} ({op.return_type}), Modifiers: {mods}, Module: {op.module}, Python Name: {component.python_name}, Export: {args}", file=file)
        if op.attributes:
            attrs = ", ".join(str(attr) for attr in op.attributes)
            print(f"    Attributes: {attrs}", file=file)
        for param in op.parameters:
            attrs = ", ".join(str(attr) for attr in param.attributes)
            print(f"    Parameter: {param.name} ({param.arg_type}), Default: {param.value}, Args: [{attrs}]", file=file)

def print_components(components: Iterable[Component], file=None):
    if file is None:
        import sys
        file = sys.stdout
    for component in components:
        print_component(component, file)

def match_filename(path):
    for ext in (".cpp", ".hpp", ".cxx", ".hxx", ".cc", ".hh", ".c", ".h"):
        if path.endswith(ext):
            return True
    return False

def gather_components(base_path):
    if (os.path.isdir(base_path)):
        for root, dirs, files in os.walk(base_path):
            for file in files:
                if match_filename(file):
                    path = os.path.join(root, file)
                    print(f"Analyzing {path}")
                    for component in analyze_file(path):
                        component.path = path
                        yield component
    else:
        for component in analyze_file(base_path):
            component.path = base_path
            yield component

def add_parser_parameters(parser: argparse.ArgumentParser):
    parser.add_argument("--parser-config", help="The config file for the parser")
    pass

if __name__ == "__main__":
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("base_dir", help="The base directory of the modpack")
    args = parser.parse_args()

    def capture_exception(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                    import sys
                    print(sys.stderr, f"Error: {e}")
                    exit(1)
        return wrapper

    #@capture_exception
    def print_components(base_dir):
        for component in gather_components(base_dir):
            print_component(component)

    print_components(args.base_dir)
