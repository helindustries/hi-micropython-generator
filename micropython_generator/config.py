#  Copyright 2025 $author, All rights reserved.
import json
import os
import re
from dataclasses import dataclass
from typing import Union, Optional, Mapping, Any, IO
from python_utilities.placeholders import apply_placeholders, placeholder_re

@dataclass
class TypeTag:
    name: str
    tag: str
@dataclass
class TagConfig:
    module: TypeTag
    types: list[TypeTag]
    properties: TypeTag
    functions: TypeTag
    operators: TypeTag
    parameters: TypeTag
    @staticmethod
    def load(path: str):
        with open(path, "r") as fd:
            data = json.load(fd)
            return TagConfig(
                module=TypeTag(data["module"]["name"], data["module"]["tag"]),
                types=[TypeTag(tag["name"], tag["tag"]) for tag in data["types"]],
                properties=TypeTag(data["properties"]["name"], data["properties"]["tag"]),
                functions=TypeTag(data["functions"]["name"], data["functions"]["tag"]),
                operators=TypeTag(data["operators"]["name"], data["operators"]["tag"]),
                parameters=TypeTag(data["parameters"]["name"], data["parameters"]["tag"])
            )
    @staticmethod
    def default():
        return TagConfig(
            module=TypeTag("MPyModule", "module"),
            types=[TypeTag("MPyClass", "class"), TypeTag("PMyStruct", "struct")],
            properties=TypeTag("MPyProperty", "property"),
            functions=TypeTag("MPyFunction", "function"),
            operators=TypeTag("MPyOperator", "operator"),
            parameters=TypeTag("MPyParam", "parameter")
        )
@dataclass
class ParserConfig:
    def _make_modifiers(self, *modifiers):
        return r"(" + "|".join([f"((?P<{mod}>{mod})" + r"[\s\t]+)" for mod in modifiers]) + r")*"
    def __init__(self, tag_config: TagConfig) -> None:
        self.header_re = re.compile(r"^[\s\t]*#include[\s\t]+(?P<include>[\"<].*[\">])$")
        self.module_re = re.compile(r"^[\s\t]*" + tag_config.module.name + r"\((?P<name>.*?)\)[\s\t]*(?P<attr_inline>.*)$")
        self.namespace_re = re.compile(r"^[\s\t]*namespace[\s\t]+(?P<name>[a-zA-Z0-9_:]+)[\s\t]*({[\s\t]*)?$")
        self.base_types_re = re.compile(r"((?P<access>(public)|(private)|(protected))[\s\t]+)(?P<base_class>[a-zA-Z0-9_:<>,&*\s]+)")
        self.type_res = [(tag, re.compile(r"^[\s\t]*" + tag.name + r"\((?P<export_attrs>.*?)\)[\s\t]*(?P<attr_inline>.*)$")) for tag in tag_config.types]
        self.type_decl_re = re.compile(
            r"^[\s\t]*(?P<type>(class)|(struct))[\s\t]*((?P<attributes>\[\[.*?\]\])[\s\t]*)?(?P<name>[a-zA-Z0-9_]+)[\s\t]*(:[\s\t]*(?P<base_types>[a-zA-Z0-9_:<>,&*\s]+))?([\s\t].*)?$")
        self.property_re = re.compile(r"^[\s\t]*" + tag_config.properties.name + r"\((?P<export_attrs>.*?)\)[\s\t]*(?P<attr_inline>.*)$")
        self.property_decl_re = re.compile(
            r"^[\s\t]*" + self._make_modifiers("virtual", "constexpr", "const", "inline", "static", "extern") + r"(?P<type>[a-zA-Z0-9_<>:*&,]+)[\s\t]*((?P<attributes>\[\[.*?\]\])[\s\t]*)?(?P<name>[a-zA-Z0-9_]+)[{(\s\t;]([\s\t]*=[\s\t]*(?P<value>.*);)?.*$")
        self.function_re = re.compile(r"^[\s\t]*" + tag_config.functions.name + r"\((?P<export_attrs>.*?)\)[\s\t]*(?P<attr_inline>.*)$")
        self.function_decl_re = re.compile(
            r"^[\s\t]*" + self._make_modifiers("virtual", "constexpr", "const", "inline", "static", "extern") + r"(?P<return_type>[a-zA-Z0-9_:<>*&,]+)[\s\t]*((?P<attributes>\[\[.*?\]\])[\s\t]*)?(?P<name>[a-zA-Z0-9_]+)[\s\t]*\((?P<parameters>.*?)\)[\s\t]*(?P<qualifier>[\s\t]*const)?[\s\t]*;.*$")
        self.operator_re = re.compile(r"^[\s\t]*" + tag_config.operators.name + r"\((?P<export_attrs>.*?)\)[\s\t]*(?P<attr_inline>.*)$")
        self.operator_decl_re = re.compile(
            r"^[\s\t]*" + self._make_modifiers("virtual", "constexpr", "const", "inline", "extern") + r"(?P<return_type>[a-zA-Z0-9_:<>*&,]+)[\s\t]*((?P<attributes>\[\[.*?\]\])[\s\t]*)?operator[\s\t]*(?P<operator>[a-zA-Z0-9_+-=*/<>!]+)[\s\t]*\((?P<parameters>.*?)\)[\s\t]*(?P<qualifier>[\s\t]*const)?[\s\t]*;.*$")
        self.argument_decl_re = re.compile(
            r"^[\s\t]*((" + tag_config.parameters.name + r"\((?P<export_attrs>.*?)\)[\s\t]+)?(?P<const>const)[\s\t]+)?(?P<type>[a-zA-Z0-9_:<>]+)[\s\t]*((?P<attributes>\[\[.*?\]\])[\s\t]*)?(?P<name>[a-zA-Z0-9_]+)[\s\t]*(=[\s\t]*(?P<value>.*?))?[\s\t]*$")
    def get_constructor_re(self, component_type):
        return re.compile(r"^[\s\t]*" + self._make_modifiers("constexpr", "virtual", "explicit", "inline") + r"((?P<attributes>\[\[.*?\]\])[\s\t]*)?" + component_type + r"\((?P<parameters>.*?)\)[\s\t]*((?P<qualifier>[\s\t]*const)[\s\t]*)?(?P<attr_inline>.*)$")
    def get_destructor_re(self, component_type):
        return re.compile(r"^[\s\t]*" + self._make_modifiers("virtual", "inline") + r"((?P<attributes>\[\[.*?\]\])[\s\t]*)?~" + component_type + r"\(\)[\s\t]*(?P<attr_inline>.*)$")

@dataclass
class Config:
    """Configuration for a single python wrapper file pair, loaded from a JSON config file"""
    configs: dict[str, 'Config']

    _source_path: Optional[str]
    _target_path: Optional[str]
    _base_directory: str
    _include_paths: list[str]
    _dependencies: list[str]
    _variables: dict[str, str]

    def __init__(self, source_path: str, variables: Optional[dict[str, str]] = None):
        self._target_path = None
        self._dependencies = []
        self._variables = {} if variables is None else variables
        self._requires_expand = False

        self._source_path = source_path
        if placeholder_re.search(source_path):
            raise ValueError("Source path cannot contain placeholders")

        if not hasattr(self.__class__, "configs") or self.__class__.configs is None:
            self.__class__.configs = {}
        self.__class__.configs[os.path.abspath(self._source_path)] = self

        with open(self._source_path, "r") as fd:
            config: Mapping[str, str] = json.load(fd)
            if "variables" in config:
                if isinstance(config["variables"], dict):
                    for key, value in config["variables"].items():
                        self._variables[key] = value
                        self._requires_expand = True
                else:
                    raise ValueError("Variables must be a dictionary")

            if "target_path" in config:
                if isinstance(config["target_path"], str):
                    path = config["target_path"]
                    self._target_path = path if os.path.isabs(path) else os.path.join(os.path.dirname(source_path), path)
                else:
                    raise ValueError("Target path must be a string")

            # Working dir needs to be relative to the source file and may contain placeholders
            self._base_directory = os.path.dirname(source_path)
            if "base_directory" in config:
                base_dir = config["base_directory"]
                if not os.path.isabs(base_dir):
                    base_dir = os.path.join(self._base_directory, base_dir)
                self._base_directory = base_dir

            self._include_paths = [os.getcwd(), self._base_directory]
            if "include_paths" in config:
                if isinstance(config["include_paths"], list):
                    self._include_paths.extend(path if os.path.isabs(path) else os.path.join(self._base_directory, path)
                                           for path in config["include_paths"])
                else:
                    raise ValueError("Dependencies must be a list of paths")

            if "dependencies" in config:
                if isinstance(config["dependencies"], list):
                    for path in config["dependencies"]:
                        if not os.path.isabs(path):
                            path = os.path.join(self._base_directory, path)
                        self.add_dependency(path)
                else:
                    raise ValueError("Dependencies must be a list of paths")

    def __getitem__(self, item) -> Optional[str]:
        self._expand_variables()
        return self._variables.get(item, None)
    def __setitem__(self, name, value):
        self._variables[name] = value
        self._requires_expand = True

    def set(self, *definitions: str):
        for definition in definitions:
            definition = definition.split("=", 1)
            if len(definition) > 1:
                key, value = definition
            else:
                key, value = definition[0], ""
            self._variables[key.strip()] = value.strip()
            self._requires_expand = True
    def expand(self, template: str, check: bool = True) -> str:
        self._expand_variables()
        return apply_placeholders(template, check, **self._variables)
    def _expand_variables(self):
        if self._requires_expand:
            for key, value in self._variables.items():
                self._variables[key] = apply_placeholders(value, False, **self._variables)

            self._target_path = apply_placeholders(self._target_path, False, **self._variables)
            self._base_directory = apply_placeholders(self._base_directory, False, **self._variables)
            self._include_paths = [apply_placeholders(path, False, **self._variables) for path in self._include_paths]
            self._dependencies = [apply_placeholders(path, False, **self._variables) for path in self._dependencies]
            self._requires_expand = False

    @property
    def source_path(self) -> Optional[str]:
        """The source config file path, it is the project path base to search for source files, exposing properties
        to python"""
        return self._source_path

    @property
    def target_path(self) -> Optional[str]:
        """The target path for the generated file, containing all required code for the module, it does
        not contain the file extension, as .cpp and .h file extensions will be added during generation."""
        if self._target_path is None:
            if self._source_path is not None:
                return os.path.splitext(self._source_path)[0]
            return None
        elif self._target_path == "-":
            return "-"
        if self._requires_expand:
            self._expand_variables()
            if match := placeholder_re.search(self._target_path):
                raise ValueError(f"Target path cannot contain remaining placeholders upon setting, {match.group(0)} not found.")
        return self._target_path
    @target_path.setter
    def target_path(self, value: str) -> None:
        self._target_path = value
        self._expand_variables()
    @property
    def target_is_stdout(self) -> bool:
        """Whether the target path points to stdout"""
        return self._target_path == "-"

    @property
    def target_source_path(self) -> Optional[str]:
        """The name of the generated source cpp file"""
        return None if self.target_is_stdout or self.target_path is None else self.target_path + ".cpp"
    @property
    def target_header_path(self) -> Optional[str]:
        """The name of the generated header file"""
        return None if self.target_is_stdout or self.target_path is None else self.target_path + ".h"

    @property
    def target_source(self) -> Optional[IO[Any]]:
        """The file object for the generated source cpp file"""
        if self.target_is_stdout:
            import sys
            return sys.stdout
        if self.target_source_path is None:
            return None
        return open(self.target_source_path, "w")
    @property
    def target_header(self) -> Optional[IO[Any]]:
        """The file object for the generated header file"""
        if self.target_is_stdout:
            import sys
            return sys.stdout
        if self.target_header_path is None:
            return None
        return open(self.target_header_path, "w")

    @property
    def base_directory(self) -> str:
        """The working directory for generating the module, so we can use relative paths"""
        if self._requires_expand:
            self._expand_variables()
            if match := placeholder_re.search(self._base_directory):
                raise ValueError(f"Working directory cannot contain remaining placeholders upon accessing, {match.group(0)} not found")
        return self._base_directory

    @property
    def include_paths(self) -> list[str]:
        """The paths to search for include files in. This is required to be set up the same way as the compiler, so
        the generation script can make sure we link against proper headers."""
        if self._requires_expand:
            self._expand_variables()
            for path in self._include_paths:
                if match := placeholder_re.search(path):
                    raise ValueError(f"Include path cannot contain remaining placeholders upon accessing, {match.group(0)} not found")
        return self._include_paths
    @include_paths.setter
    def include_paths(self, *value: str) -> None:
        self._include_paths = list(value)
    def add_include_paths_from_flags(self, flags: Union[str, list[str]]) -> None:
        if isinstance(flags, str):
            flags = flags.split()
        for flag in flags:
            if flag.startswith("-I"):
                self._include_paths.append(flag[2:])
    def add_include_path(self, path: str) -> None:
        self._include_paths.append(path)

    @property
    def dependencies(self) -> dict[str, 'Config']:
        """The dependencies for this module, which are other modules that need to be generated before this one.
        We only store the paths here, the configs are cached globally and referenced when returning the values."""
        dependencies: dict[str, 'Config'] = {}
        for path in self._dependencies:
            if (config := self.__class__.configs.get(path, None)) is None:
                raise ValueError("Dependencies not loaded")
            dependencies[path] = config
        return dependencies
    def add_dependency(self, path: str) -> None:
        self._dependencies.append(path)
    def load_dependencies(self) -> None:
        self._expand_variables()
        for path in self._dependencies:
            if match := placeholder_re.search(path):
                raise ValueError(f"Dependency path cannot contain remaining placeholders upon loading, {match.group(0)} not found")
            path = os.path.abspath(path)

            if path in self.__class__.configs:
                if not os.path.isfile(path):
                    raise FileNotFoundError(f"Dependency file {path} not found")
                # We pass the root variables to the dependency, but expect the dependency to override them if necessary
                config = Config(path, variables = self._variables)
                config.load_dependencies()
                self.__class__.configs[path] = config

def resolve_include_path(file_path: str, include: str, config: Config, local_first: bool = True) -> str:
    if os.path.splitext(include)[1] == "":
        # No extension, assume C++ style module include, we need to check for any of the common extensions
        for ext in [".h", ".hpp", ".cpp", ".c"]:
            try:
                return resolve_include_path(file_path, include + ext, config, False)
            except FileNotFoundError:
                pass
        raise FileNotFoundError(f"Could not find include directory for {include}")

    if local_first:
        if os.path.isabs(include):
            if os.path.isfile(include) or os.path.islink(include):
                return f"\"{os.path.dirname(include)}\""
            else:
                raise FileNotFoundError(f"Could not find absolute include directory for {include}")

        if config.target_path is None:
            raise ValueError("Target path not set")
        local_dir: str = os.path.dirname(file_path)
        local_path: str = os.path.join(local_dir, include)
        if os.path.isfile(local_path) or os.path.islink(local_path):
            # Resolve the path relative to the target_path file
            target_dir = os.path.dirname(config.target_path)
            local_dir = os.path.relpath(local_dir, target_dir)
            include_path = os.path.join(local_dir, include).removeprefix("./")
            return f"\"{include_path}\""

    # These are simple, because we use the same paths as the compiler, they can be returned directly
    for include_path in config.include_paths:
        path = os.path.join(include_path, include)
        if os.path.isfile(path) or os.path.islink(path):
            return f"<{include}>"

    raise FileNotFoundError(f"Could not find include directory for {include}")
