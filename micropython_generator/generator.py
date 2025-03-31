#  Copyright 2025 $author, All rights reserved.
import argparse
import itertools
import os
import re
import sys
from dataclasses import dataclass
from typing import Union, Iterable, Optional

from python_utilities.cpp import parse_compiler_args
from python_utilities.placeholders import apply_placeholders

from micropython_generator import templates
from micropython_generator.config import Config, ParserConfig, TagConfig
from micropython_generator.parser import Component, Operator, Function, \
    Property, Parameter, Attribute, StringAttribute, SubAttribute, add_parser_parameters, validate_components, \
    get_type_name, ensure_namespaced_type_refs, make_python_name, get_custom_type_register, find_type, \
    get_type_name_without_namespace, analyze_file

# A set of very special exception types, that need to be treated as literal instead of pointers
force_literal_types = ["char*", "const char*"]

def is_pointer_type(type_name: str):
    return type_name.endswith("*") and type_name not in force_literal_types

@dataclass
class GeneratorContext:
    config: Config
    components: list[Component]
    dependencies: dict[str, Iterable[Component]]
    custom_types: dict[str, Component]
    def __init__(self, config: Config, components: Iterable[Component], dependencies: dict[str, Iterable[Component]]):
        self.config = config
        self.components = components
        self.dependencies = dependencies
        self.custom_types = get_custom_type_register(components, dependencies)

@dataclass
class GeneratorParameter:
    name: str
    python_name: str
    arg_type: str
    is_outparam: bool
    default_value: Optional[str]
    def __init__(self, parameter: Parameter):
        self.name = parameter.name
        self.python_name = parameter.python_name
        self.arg_type = parameter.arg_type
        self.default_value = parameter.value
        self.is_outparam = "ParamIsOut" in parameter.export_attributes
        self.is_outparam |= not parameter.is_const and parameter.arg_type.endswith("&")
    def _is_outparam(self, param: Parameter):
        if param.is_const:
            return False
        if "ParamIsOut" in param.export_attributes:
            return True
        # For now always require manual tagging, it gives a better idea of the resulting tuple content
        return False

@dataclass
class GeneratorOverload:
    parameters: list[GeneratorParameter]
    return_type: str
    namespace: str
    context: GeneratorContext
    is_static: bool = False
    def __init__(self, parameters: list[GeneratorParameter], return_type: str, namespace: str, is_static: bool, context: GeneratorContext):
        self.parameters = parameters
        self.return_type = return_type
        self.namespace = namespace
        self.is_static = is_static
        self.context = context
    def __eq__(self, other):
        if not isinstance(other, GeneratorOverload):
            return False
        return all([param == other_param for param, other_param in zip(self.parameters, other.parameters)])
    def __hash__(self):
        # Functions get overloaded by parameters only, there are not going to be overloads with the same parameter list
        return hash(tuple(self.parameters))
    def make_call(self, name: str, self_type: str = None, self_is_ptr: bool = False):
        args = []
        for param in self.parameters:
            type_name, component = find_type(param.arg_type, self.context.components, self.context.dependencies)
            is_transient = component is not None and "TypeNonTransient" not in component.export_attributes and "TypeIsOwned" not in component.export_attributes
            if is_pointer_type(param.arg_type) and not is_transient:
                # in case we have a non-pointer value, we need to take the address
                args.append(f"&{param.name}")
            else:
                args.append(param.name)
        has_outparams = any(param.is_outparam for param in self.parameters)
        if has_outparams:
            out_params = [apply_placeholders(templates.cpp_function_outparam, type=param.arg_type, name=param.name)
                          for param in self.parameters if param.is_outparam]
            if self.return_type == "void":
                return_code = apply_placeholders(templates.cpp_function_return_outparam,
                                                 out_params=", ".join(out_params), out_param_count=len(out_params))
            else:
                return_code = apply_placeholders(templates.cpp_function_return_result_outparam, type=self.return_type,
                                                 out_params=", ".join(out_params), out_param_count=len(out_params))
        else:
            if self.return_type is None:
                return_code = templates.cpp_function_return_void
            else:
                return_code = apply_placeholders(templates.cpp_function_return_result, type=self.return_type)
        if self_type is None:
            if self.return_type == "void":
                call = apply_placeholders(templates.cpp_function_call_noreturn, namespace=self.namespace, name=name, args=", ".join(args), return_code=return_code)
            else:
                call = apply_placeholders(templates.cpp_function_call_return, namespace=self.namespace, name=name, args=", ".join(args), return_code=return_code)
        elif self.is_static:
            if self.return_type == "void":
                call = apply_placeholders(templates.cpp_static_method_call_noreturn, namespace=self.namespace, name=name, args=", ".join(args), return_code=return_code)
            else:
                call = apply_placeholders(templates.cpp_static_method_call_return, namespace=self.namespace, name=name, args=", ".join(args), return_code=return_code)
        else:
            ref_or_ptr = "->" if self_is_ptr else "."
            if self.return_type == "void":
                call = apply_placeholders(templates.cpp_method_call_noreturn, name=name, args=", ".join(args), ref_or_ptr=ref_or_ptr, return_code=return_code)
            else:
                call = apply_placeholders(templates.cpp_method_call_return, name=name, args=", ".join(args), ref_or_ptr=ref_or_ptr, return_code=return_code)

        return call
    def make_kwargs_init_code(self, bound: bool):
        arg_inits = []
        self_offset = 1 if bound else 0
        for index, arg in enumerate(self.parameters):
            if arg.default_value is not None:
                arg_inits.append(apply_placeholders(templates.cpp_function_kwarg_init_with_default, arg_index=index + self_offset, name=arg.name, type=arg.arg_type, default=arg.default_value))
            else:
                arg_inits.append(apply_placeholders(templates.cpp_function_kwargs_init_required, name=arg.name, type=arg.arg_type, arg_index=index + self_offset))
        return "\n".join(arg_inits)
    def make_vararg_init_code(self, bound: bool):
        arg_inits = []
        self_offset = 1 if bound else 0
        for index, arg in enumerate(self.parameters):
            if arg.default_value is not None:
                arg_inits.append(apply_placeholders(templates.cpp_function_varargs_init_withdefault, arg_index=index + self_offset, name=arg.name, type=arg.arg_type, default=arg.default_value))
            else:
                arg_inits.append(apply_placeholders(templates.cpp_function_init_required, arg_index=index + self_offset, name=arg.name, type=arg.arg_type))
        return "\n".join(arg_inits)
    def make_fixed_init_code(self, bound: bool, use_obj_param_index: bool = False):
        arg_offset = 1 if bound else 0
        arg_inits = []
        for index, arg in enumerate(self.parameters):
            if len(self.parameters) > 3 - arg_offset:
                arg_inits.append(apply_placeholders(templates.cpp_function_init_required, arg_index=index + arg_offset, name=arg.name, type=arg.arg_type))
            elif use_obj_param_index:
                arg_inits.append(apply_placeholders(templates.cpp_function_fixed_init_arg, obj_name=f"param{index}", name=arg.name, type=arg.arg_type))
            else:
                arg_inits.append(apply_placeholders(templates.cpp_function_fixed_init_arg, obj_name=f"{arg.name}", name=arg.name, type=arg.arg_type))
        return "\n".join(arg_inits)
    def make_required_param_check(self, bound: bool, allow_kwargs: bool = True, fixed_use_index: Optional[bool] = None):
        # TODO: Fix for 0 args
        arg_offset = 1 if bound else 0
        arg_checks = []
        kwarg_checks = []
        has_optionals = any([param.default_value is not None for param in self.parameters])
        len_required = len(self.parameters)
        for index, arg in enumerate(self.parameters):
            if arg.default_value is not None:
                len_required = index
                break
            if fixed_use_index is None or len(self.parameters) > 3 - arg_offset:
                arg_checks.append(apply_placeholders(templates.cpp_function_kwvarargs_check, arg_index=index + arg_offset, type=arg.arg_type))
                if allow_kwargs:
                    kwarg_checks.append(apply_placeholders(templates.cpp_function_kwarg_check, name=arg.name, type=arg.arg_type))
            else:
                if fixed_use_index:
                    arg_checks.append(apply_placeholders(templates.cpp_function_fixed_args_check, name=f"param{index}", type=arg.arg_type))
                else:
                    arg_checks.append(apply_placeholders(templates.cpp_function_fixed_args_check, name=f"{arg.name}", type=arg.arg_type))

        if len(arg_checks) < 1:
            arg_checks = ["true"]
        if fixed_use_index is None or len(self.parameters) > 3 - arg_offset:
            if allow_kwargs:
                # in this case we need to check all the permutations of args and kwargs
                arg_permutations = []
                for i in range(len_required, -1, -1):
                    arg_comb = arg_checks[:i]
                    arg_comb.extend(kwarg_checks[i:])
                    if has_optionals:
                        arg_permutations.append(apply_placeholders(templates.cpp_function_required_overload_withoptionals_check, required_count=i + arg_offset, arg_checks=" && ".join(arg_comb)))
                    else:
                        arg_permutations.append(apply_placeholders(templates.cpp_function_required_overload_nooptionals_check, required_count=i + arg_offset, arg_checks=" && ".join(arg_comb)))
                return " || ".join([f"({perm})" for perm in arg_permutations])
            else:
                if has_optionals:
                    return apply_placeholders(templates.cpp_function_required_overload_withoptionals_check, required_count=len_required + arg_offset, arg_checks=" && ".join(arg_checks))
                else:
                    return apply_placeholders(templates.cpp_function_required_overload_nooptionals_check, required_count=len_required + arg_offset, arg_checks=" && ".join(arg_checks))
        else:
            return " && ".join(arg_checks)
    def make_optional_param_check(self, param_offset: int):
        # need to generate all combinations of the parameter being passed positional
        optional_params = [param for param in self.parameters if param.default_value is not None]
        checks = []
        for i in range(1, len(self.parameters) - param_offset + 1):
            arg_combs = []
            for combination in itertools.combinations(optional_params, i):
                arg_checks = [apply_placeholders(templates.cpp_function_kwarg_check, name=param.name, type=param.arg_type) for param in combination]
                arg_check_combined = " && ".join(arg_checks)
                arg_combs.append(f"({arg_check_combined})")
            checks_combined = " || ".join(arg_combs)
            checks.append(apply_placeholders(templates.cpp_function_kwarg_optional_check, optional_count=i, arg_checks=f"({checks_combined})"))
        return " || ".join(checks)
    def to_code(self, name: str, self_type: str = None, self_is_ptr: bool = False, allow_kwargs: bool = True, fixed_use_index: Optional[bool] = None):
        call = self.make_call(name, self_type, self_is_ptr)
        required = self.make_required_param_check(self_type is not None, allow_kwargs, fixed_use_index)
        if fixed_use_index is None:
            has_optionals = any([param.default_value is not None for param in self.parameters])
            if allow_kwargs:
                # kwargs
                init_code = self.make_kwargs_init_code(self_type is not None)
                if has_optionals:
                    required_count = len([param for param in self.parameters if param.default_value is None])
                    optional = self.make_optional_param_check(required_count)
                    return apply_placeholders(templates.cpp_function_kwargs_overload_withoptionals, required_check=required, arg_init=init_code,
                                              required_count=required_count, optional_check=optional, call_function=call)
                else:
                    return apply_placeholders(templates.cpp_function_kwargs_overload_nooptionals, overload_check=required, arg_init=init_code, call_function=call)
            else:
                # varargs
                init_code = self.make_vararg_init_code(self_type is not None)
                return apply_placeholders(templates.cpp_function_varargs_overload, overload_check=required, arg_init=init_code, call_function=call)
        else:
            # fixed args
            arg_init = self.make_fixed_init_code(self_type is not None, fixed_use_index)
            return apply_placeholders(templates.cpp_function_fixed_overload, overload_check=required, arg_init=arg_init, call_function=call)

@dataclass
class GeneratorFunction:
    namespace: str
    name: str
    python_name: str
    context: GeneratorContext
    overloads: list[GeneratorOverload]
    bases: list[Component]
    # Don't allow overloads, still type-checked, not sure why we'd want that but may be a good sanity check
    no_overloads: bool = False
    # Don't allow kwargs, just varargs
    no_kwargs: bool = True
    # Don't allow defaults, warn if present and strip
    no_defaults: bool = False
    # Don't perform type checking, just convert (or fail to) and call
    unchecked: bool = False
    self_type: Optional[str] = None
    self_is_ptr: bool = False
    def __init__(self, function: Function, context: GeneratorContext):
        self.namespace, self.name, self.python_name = get_type_name(function)
        self.context = context
        self.bases = []
        self.overloads = []
        self.add_overload(function)
    def add_overload(self, function: Function):
        self.overloads.append(GeneratorOverload([GeneratorParameter(param) for param in function.parameters], function.return_type, self.namespace, function.is_static, self.context))
        self.no_overloads |= "FuncNoOverloads" in function.export_attributes
        self.unchecked |= "FuncUnchecked" in function.export_attributes
        self.no_defaults |= "FuncNoDefaults" in function.export_attributes
        self.no_kwargs &= "FuncAllowKwargs" not in function.export_attributes
        # This automatically enables FunkHasKwargs due to at least one base function having kwargs
        self.no_kwargs &= not any(self._base_func_has_kwargs(component) for component in self.bases)
    def _make_self_init(self, fixed: bool = False):
        ref_overload = self.overloads[0]
        if self.self_type is not None and not ref_overload.is_static:
            if fixed and len(ref_overload.parameters) < 4:
                return apply_placeholders(templates.cpp_method_fixedargs_self_init, type_name=self.self_type)
            else:
                return apply_placeholders(templates.cpp_method_kwvarargs_self_init, type_name=self.self_type)
        return ""
    def _make_base_overloads(self, component: Component):
        for base_func in component.functions:
            py_name = make_python_name(base_func.python_name, base_func.name)
            if py_name == self.python_name:
                yield base_func
    def _base_func_has_kwargs(self, component: Component):
        for base_func in self._make_base_overloads(component):
            if "FuncAllowKwargs" in base_func.export_attributes:
                return True
        return False
    def _base_func_needs_varargs(self, component: Component):
        overloads = list(self._make_base_overloads(component))
        ref_overload = overloads[0]
        no_overloads = any(["FuncNoDefaults" in overload.export_attributes for overload in overloads[1:]])
        if len(ref_overload.parameters) > 2:
            return True
        for overload in overloads:
            if any([param.value is not None for param in overload.parameters]) and not no_overloads:
                return True
            if len(overload.parameters) != len(ref_overload.parameters):
                return True
        return False
    def _make_fixed_base_calls(self, fixed_use_index: bool):
        if self.self_type is None:
            return []
        ref_overload = self.overloads[0]
        for component in self.bases:
            name = component.name + self.name
            if fixed_use_index:
                args = [f"param{index}_obj" for index in range(len(ref_overload.parameters))]
            else:
                args = [f"{param.name}_obj" for param in ref_overload.parameters]
            yield apply_placeholders(templates.cpp_function_base_call_fixedargs_to_fixedargs,
                                     name=name, args=", ".join(args))
    def _make_vararg_base_calls(self):
        if self.self_type is None:
            return []
        for component in self.bases:
            name = component.name + self.name
            if self._base_func_needs_varargs(component):
                yield apply_placeholders(templates.cpp_function_base_call_varargs_to_varargs, name=name)
            else:
                ref_overload = next(self._make_base_overloads(component))
                args = [f"args[{index + 1}]" for index in range(len(ref_overload.parameters))]
                yield apply_placeholders(templates.cpp_function_base_call_varargs_to_fixedargs,
                                         name=name, arg_count=len(args) + 1, args=", ".join(args))
    def _make_kwarg_base_calls(self):
        if self.self_type is None:
            return []
        for component in self.bases:
            name = component.name + self.name
            if self._base_func_has_kwargs(component):
                yield apply_placeholders(templates.cpp_function_base_call_kwargs_to_kwargs, name=name)
            elif self._base_func_needs_varargs(component):
                yield apply_placeholders(templates.cpp_function_base_call_kwargs_to_varargs, name=name)
            else:
                ref_overload = next(self._make_base_overloads(component))
                args = [f"args[{index + 1}]" for index in range(len(ref_overload.parameters))]
                yield apply_placeholders(templates.cpp_function_base_call_kwargs_to_fixedargs,
                                         name=name, arg_count=len(args) + 1, args=", ".join(args))
    def module_entry(self):
        return apply_placeholders(templates.cpp_module_function_template, name=self.name, py_name=self.python_name)
    def type_entry(self):
        name = self.self_type + self.name if self.self_type is not None else self.name
        return apply_placeholders(templates.cpp_module_function_template, name=name, py_name=self.python_name)
    def to_code(self):
        if self.no_defaults:
            for overload in self.overloads:
                for param in overload.parameters:
                    if param.default_value is not None:
                        print(f"Warning: Function {self.name} has no defaults but parameter {param.name} has a default value", file=sys.stderr)
                        param.default_value = None
        if self.no_overloads and len(self.overloads) > 1:
            raise ValueError(f"Function {self.name} has no overloads but has {len(self.overloads)}")

        name = self.self_type + self.name if self.self_type is not None else self.name
        ref_overload = self.overloads[0]
        self_offset = 1 if self.self_type is not None else 0
        same_args = self.unchecked or all([overload == ref_overload for overload in self.overloads])
        same_length = self.unchecked or all([len(overload.parameters) == len(ref_overload.parameters) for overload in self.overloads])
        if self.unchecked:
            args_init = ref_overload.make_fixed_init_code(self.self_type is not None)
            call = ref_overload.make_call(self.name, self.self_type, self.self_is_ptr)
            if len(ref_overload.parameters) > 3 - self_offset:
                self_init = self._make_self_init(fixed=False)
                return apply_placeholders(templates.cpp_function_fixed_unchecked_long, name=name, self_init=self_init,
                                          args_init=args_init, call_function=call, arg_count=len(ref_overload.parameters) + self_offset)
            else:
                self_init = self._make_self_init(fixed=True)
                args = []
                if self.self_type is not None:
                    args.append(f"mp_obj_t self_in")
                args.extend([f"mp_obj_t {param.name}_obj" for param in ref_overload.parameters])
                return apply_placeholders(templates.cpp_function_fixed_unchecked, name=name, args=", ".join(args), self_init=self_init,
                                          args_init=args_init, call_function=call, arg_count=len(ref_overload.parameters) + self_offset)
        has_defaults = any([param.default_value is not None for param in self.overloads[0].parameters])
        base_has_kwargs = any([self._base_func_has_kwargs(component) for component in self.bases])
        base_has_varargs = any([self._base_func_needs_varargs(component) for component in self.bases])
        fixed_use_index = not same_args if same_length and self.no_kwargs and len(ref_overload.parameters) < 4 - self_offset and not has_defaults and not base_has_kwargs and not base_has_varargs else None
        overloads = [overload.to_code(self.name, self.self_type, self.self_is_ptr, not self.no_kwargs, fixed_use_index) for overload in self.overloads]
        if fixed_use_index is not None:
            base_calls = list(self._make_fixed_base_calls(fixed_use_index))
            self_init = self._make_self_init(fixed=True)
            args = []
            if self.self_type is not None:
                args.append(f"self_in")
            if same_args:
                args.extend([f"{param.name}_obj" for param in ref_overload.parameters])
            else:
                args.extend([f"param{index}_obj" for index in range(len(ref_overload.parameters))])
            args_init = ref_overload.make_fixed_init_code(self.self_type is not None, not same_args)
            return apply_placeholders(templates.cpp_function_fixed_overloads, name=self.name, arg_names=", ".join(args),
                                      args=", ".join(f"mp_obj_t {arg}" for arg in args), self_init=self_init,
                                      args_init=args_init, base_calls="\n".join(base_calls), overloads="\n".join(overloads),
                                      arg_count=len(ref_overload.parameters) + self_offset)

        self_init = self._make_self_init()
        required_arg_count = len([param for param in ref_overload.parameters if param.default_value is None])
        if self.no_kwargs:
            base_calls = list(self._make_vararg_base_calls())
            max_args = max([len(overload.parameters) for overload in self.overloads])
            return apply_placeholders(templates.cpp_function_varargs, name=name, self_init=self_init,
                                      overloads="\n".join(overloads), base_calls="\n".join(base_calls),
                                      min_arg_count=required_arg_count + self_offset, max_arg_count=max_args + self_offset)

        kwargs = set()
        base_calls = list(self._make_kwarg_base_calls())
        for overload in self.overloads:
            kwargs.update([param.name for param in overload.parameters])
        kwarg_init = "\n".join(apply_placeholders(templates.cpp_function_kwarg_init_template, name=kwarg) for kwarg in kwargs)
        return apply_placeholders(templates.cpp_function_kwargs, name=self.name, self_init=self_init, kwarg_init=kwarg_init,
                                  overloads="\n".join(overloads), base_calls="\n".join(base_calls),
                                  min_arg_count=required_arg_count + self_offset)

@dataclass
class GeneratorOperator:
    operator: str
    overloads: list[GeneratorOverload]
    self_type: str
    context: GeneratorContext
    def __init__(self, operator: Operator, namespace: str, context: GeneratorContext):
        self.operator = operator.operator
        self.context = context
        self.overloads = []
        self.add_overload(operator, namespace)
    def add_overload(self, operator: Operator, namespace: str):
        self.overloads.append(GeneratorOverload([GeneratorParameter(param) for param in operator.parameters], operator.return_type, namespace,False, self.context))
    def to_code(self):
        ref_overload = self.overloads[0]
        if self.operator == "[]":
            op_calls = [apply_placeholders(templates.cpp_custom_type_subscript_template, self_type=self.self_type, index_type=overload.parameters[0].arg_type, return_type=overload.return_type) for overload in self.overloads]
            return "\n".join(op_calls)
        elif len(ref_overload.parameters) < 1:
            if (op := templates.cpp_custom_type_unary_op_template_map.get(self.operator, None)) is not None:
                return apply_placeholders(templates.cpp_custom_type_unary_op_template, name=op, return_type=ref_overload.return_type, unary_op=self.operator)
        else:
            if (op_name := templates.cpp_custom_type_binary_op_name_map.get(self.operator, None)) is not None:
                if (op_template := templates.cpp_custom_type_binary_op_template_map.get(self.operator, None)) is not None:
                    op_calls = [apply_placeholders(op_template, False, return_type=overload.return_type, type_name=overload.parameters[0].arg_type, op=self.operator) for overload in self.overloads]
                    overloads = [apply_placeholders(templates.cpp_custom_type_binary_op_overload, type=overload.parameters[0].arg_type, binary_op="\n".join(op_calls)) for overload in self.overloads]
                    return apply_placeholders(templates.cpp_custom_type_binary_op_template, name=op_name, overloads="\n".join(overloads))
        raise ValueError(f"Operator {self.operator} not supported")

@dataclass
class GeneratorType:
    namespace: str
    name: str
    python_name: str
    type_name: str
    base_types: list[Component]
    self_is_ptr: bool
    init_code: str
    variable_getters: list[str]
    variable_setters: list[str]
    constants: list[str]
    constructor: GeneratorFunction
    destructor: GeneratorFunction
    functions: dict[str, GeneratorFunction]
    operators: dict[str, GeneratorOperator]
    export_attributes: dict[str, Union[Attribute, StringAttribute, SubAttribute]]
    def __init__(self, type: Component, context):
        self.namespace, self.name, self.python_name = get_type_name(type)
        self.context = context
        self.type_name = make_custom_type_type(self.namespace + self.name, type)
        is_owned = "TypeOwned" in type.export_attributes
        is_transient = "TypeNonTransient" not in type.export_attributes and not is_owned
        self.self_is_ptr = not is_owned and is_transient
        self.export_attributes = type.export_attributes
        self.init_code = self.export_attributes["TypeInitCode"] if "TypeInitCode" in self.export_attributes else ""
        self.variable_getters = []
        self.variable_setters = []
        self.constants = []
        self.functions = {}
        self.operators = {}

        self.base_types = []
        for base in type.base_types:
            if base.access != "public":
                continue
            for component in context.components:
                if component.name == base.name:
                    self.base_types.append(component)
            for dep in context.dependencies.values():
                self.base_types.extend([component.name for component in dep if component.name == base.name])

        if len(type.constructors) > 0:
            self.constructor = GeneratorFunction(type.constructors[0], self.context)
            for constructor in type.constructors[1:]:
                self.constructor.add_overload(constructor)
        else:
            self.constructor = GeneratorFunction(Function(), self.context)
        if len(type.destructors) > 0:
            self.destructor = GeneratorFunction(type.destructors[0], self.context)
            for destructor in type.destructors[1:]:
                self.destructor.add_overload(destructor)
        else:
            self.destructor = GeneratorFunction(Function(), self.context)
        for function in type.functions:
            self.add_function(function)
        for operator in type.operators:
            self.add_operator(operator)
        for property in type.properties:
            self.add_property(property)
    def add_operator(self, operator: Operator):
        if (gen_op := self.operators.get(operator.operator, None)) is None:
            gen_op = GeneratorOperator(operator, self.namespace, self.context)
            gen_op.self_type = self.name
            self.operators[operator.operator] = gen_op
        else:
            gen_op.add_overload(operator, self.namespace)
    def add_function(self, function: Function):
        py_name = make_python_name(function.python_name, function.name)
        if (gen_func := self.functions.get(py_name, None)) is None:
            gen_func = GeneratorFunction(function, self.context)
            gen_func.self_type = self.name
            gen_func.self_is_ptr = self.self_is_ptr
            for component in self.base_types:
                for base_func in component.functions:
                    if py_name == make_python_name(base_func.python_name, base_func.name):
                        gen_func.bases.append(component)
            self.functions[py_name] = gen_func
        else:
            gen_func.add_overload(function)
    def add_property(self, property: Property):
        if (property.is_constexpr and property.is_static) or "PropConstant" in property.export_attributes:
            py_name = make_python_name(property.python_name, property.name)
            py_type = templates.cpp_pytype_to_rom_ptr_map.get(templates.cpp_type_to_pytype_map.get(property.property_type, "object"), "PTR")
            self.constants.append(apply_placeholders(templates.cpp_module_constant_template, py_name=py_name, type=py_type, value=property.value))
        else:
            py_name = make_python_name(property.python_name, property.name)
            if "PropWriteOnly" not in property.export_attributes:
                self.variable_getters.append(apply_placeholders(templates.cpp_custom_type_getter_template, py_name=py_name,
                                                                type=property.property_type, value=property.name,
                                                                ref_or_ptr="->" if self.self_is_ptr else "."))
            if "PropReadOnly" not in property.export_attributes and not property.is_const:
                self.variable_setters.append(apply_placeholders(templates.cpp_custom_type_setter_template, py_name=py_name,
                                                                type=property.property_type, value=property.name,
                                                                ref_or_ptr="->" if self.self_is_ptr else "."))
    def module_entry(self):
        return apply_placeholders(templates.cpp_module_type_template, name=self.name, py_name=self.python_name)
    def to_code(self):
        subscript = []
        unary_ops = []
        if "TypeIsHashable" in self.export_attributes:
            unary_ops.append(templates.cpp_custom_type_unary_op_template_map["hash"])
        binary_ops = []
        for operator in self.operators.values():
            if operator.operator == "[]":
                subscript.append(operator.to_code())
            elif len(operator.overloads[0].parameters) < 1:
                unary_ops.append(operator.to_code())
            else:
                binary_ops.append(operator.to_code())
        if "TypeOwned" in self.export_attributes:
            constructors = []
            for constructor in self.constructor.overloads:
                required = constructor.make_required_param_check(False, False, None)
                init_code = constructor.make_vararg_init_code(False)
                call = apply_placeholders(templates.cpp_custom_type_owned_constructor, namespace=self.namespace, type_name=self.name,
                                          args=", ".join([param.name for param in constructor.parameters]))
                constructors.append(apply_placeholders(templates.cpp_function_varargs_overload, overload_check=required,
                                          arg_init=init_code, call_function=call))

            make_new = apply_placeholders(templates.cpp_custom_type_owned_init, type_name=self.name, init_code=self.init_code,
                                          constructors="\nelse ".join(constructors))

            if len(self.destructor.overloads) > 0:
                # There is only going to be one that is relevant
                destroy = apply_placeholders(templates.cpp_custom_type_owned_destroy, namespace=self.namespace, type_name=self.name)
                destroy_entry = apply_placeholders(templates.cpp_custom_type_owned_destroy_entry, type_name=self.name)
            else:
                destroy = ""
                destroy_entry = ""
        else:
            factory = self.export_attributes["TypeFactory"].value if "TypeFactory" in self.export_attributes else ""
            make_new = apply_placeholders(templates.cpp_custom_type_unowned_init, type_name=self.name, factory=factory)
            destroy = ""
            destroy_entry = ""
        base_type_names = [get_type_name_without_namespace(base.name) for base in self.base_types]
        base_attrs = [apply_placeholders(templates.cpp_custom_type_base_attr, parent_type=base) for base in base_type_names]
        base_unary_ops = [apply_placeholders(templates.cpp_custom_type_base_unary_op, parent_type=base) for base in base_type_names]
        base_binary_ops = [apply_placeholders(templates.cpp_custom_type_base_binary_op, parent_type=base) for base in base_type_names]
        base_subscripts = [apply_placeholders(templates.cpp_custom_type_base_subscript, parent_type=base) for base in base_type_names]
        bases_list = [apply_placeholders(templates.cpp_custom_type_base, parent_type=base) for base in base_type_names]
        if len(self.base_types) > 1:
            bases_tuple_def = apply_placeholders(templates.cpp_custom_type_bases, type_name=self.name, base_list=", ".join(bases_list), base_count=len(base_type_names))
            bases_tuple_entry = apply_placeholders(templates.cpp_custom_type_bases_entry, type_name=self.name)
            bases_slot_index = templates.cpp_custom_type_bases_slot_index
        elif len(self.base_types) > 0:
            bases_tuple_def = ""
            bases_tuple_entry = apply_placeholders(templates.cpp_custom_type_bases_single, type_name=bases_list[0])
            bases_slot_index = templates.cpp_custom_type_bases_slot_index
        else:
            bases_tuple_def = ""
            bases_tuple_entry = ""
            bases_slot_index = ""
        return apply_placeholders(templates.cpp_custom_type_source_template, namespace=self.namespace, name=self.name, type_name=self.type_name,
                                  py_type_name=self.python_name, make_new=make_new, attr_getters="\n".join(self.variable_getters),
                                  attr_setters="\n".join(self.variable_setters), type_constants="\n".join(self.constants),
                                  type_functions="\n".join([function.type_entry() for function in self.functions.values()]),
                                  subscripts="\n".join(subscript), unary_ops="\n".join(unary_ops), binary_ops="\n".join(binary_ops),
                                  functions="\n".join([function.to_code() for function in self.functions.values()]),
                                  destroy=destroy, base_attrs="\n".join(base_attrs), base_unary_ops="\n".join(base_unary_ops),
                                  base_binary_ops="\n".join(base_binary_ops), base_subscripts="\n".join(base_subscripts),
                                  bases_tuple_def=bases_tuple_def, bases_tuple_entry=bases_tuple_entry,
                                  bases_slot_index=bases_slot_index, destroy_entry=destroy_entry)

@dataclass
class GeneratorModule:
    module_name: str
    py_module_name: str
    modules: list["GeneratorModule"]
    is_extern: bool
    context: GeneratorContext
    variable_getters: list[str]
    variable_setters: list[str]
    constants: list[str]
    functions: dict[str, GeneratorFunction]
    unused_operators: list[Operator]
    types: list[GeneratorType]
    includes: set[str]
    def __init__(self, module_name, py_module_name, context: GeneratorContext):
        self.module_name = module_name
        self.py_module_name = py_module_name
        self.context = context
        self.variable_getters = []
        self.variable_setters = []
        self.constants = []
        self.modules = []
        self.functions = {}
        self.unused_operators = []
        self.types = []
        self.is_extern = False
        self.includes = []
        for dep in self.context.dependencies.values():
            for component in dep:
                if get_type_name(component)[2] == py_module_name:
                    # The module is defined externally, it can't be re-defined here
                    self.is_extern = True
                    break
                for function in component.functions:
                    if make_python_name(function.python_name, function.name) == py_module_name:
                        self.is_extern = True
                for property in component.properties:
                    if make_python_name(property.python_name, property.name) == py_module_name:
                        self.is_extern = True
                # Don't check operators, they must live in the same module as their type
    def __eq__(self, other):
        return self.module_name == other.module_name
    def __hash__(self):
        return hash(self.module_name)
    def add_submodule(self, module: "GeneratorModule"):
        self.modules.append(module)
    def add_type(self, type: Component):
        self.types.append(GeneratorType(type, self.context))
        for operator in self.unused_operators:
            if self._try_add_operator(operator):
                self.unused_operators.remove(operator)
    def add_function(self, function: Function):
        py_name = make_python_name(function.python_name, function.name)
        if (gen_func := self.functions.get(py_name, None)) is None:
            gen_func = GeneratorFunction(function, self.context)
            self.functions[py_name] = gen_func
        else:
            gen_func.add_overload(function)
    def _try_add_operator(self, operator: Operator):
        if len(types := list(filter(lambda type: type.name == operator.parameters[0].arg_type, self.types))) > 0:
            # Convert to instance-bound by removing the first parameter and attaching to type
            del (operator.parameters[0])
            types[0].add_operator(operator)
            return True
        return False
    def add_operator(self, operator: Operator):
        if not self._try_add_operator(operator):
            # If we fail, keep the operator around, we may be adding the type later
            self.unused_operators.append(operator)
    def add_property(self, property: Property):
        if property.is_constexpr or "PropConstant" in property.export_attributes:
            py_name = make_python_name(property.python_name, property.name)
            py_type = templates.cpp_pytype_to_rom_ptr_map.get(templates.cpp_type_to_pytype_map.get(property.property_type, "object"), "PTR")
            self.constants.append(apply_placeholders(templates.cpp_module_constant_template, py_name=py_name, type=py_type, value=property.value))
        else:
            py_name = make_python_name(property.python_name, property.name)
            if "PropWriteOnly" not in property.export_attributes:
                self.variable_getters.append(apply_placeholders(templates.cpp_module_variable_getter_template, py_name=py_name, type=property.property_type, value=property.name))
            if "PropReadOnly" not in property.export_attributes and not property.is_const:
                self.variable_setters.append(apply_placeholders(templates.cpp_module_variable_setter_template, py_name=py_name, type=property.property_type, value=property.name))
    def to_code(self):
        if self.is_extern:
            return apply_placeholders(templates.cpp_module_extern_template, module_name=self.module_name, py_module_name=self.py_module_name)
        else:
            submodules = [apply_placeholders(templates.cpp_module_submodule_template, py_name=module.py_module_name, name=module.module_name) for module in self.modules]
            getters = [getter for getter in self.variable_getters]
            setters = [setter for setter in self.variable_setters]
            constants = [constant for constant in self.constants]
            module_functions = [function.module_entry() for function in self.functions.values()]
            functions = [function.to_code() for function in self.functions.values()]
            module_types = [type.module_entry() for type in self.types]
            types = [type for type in self.types]
            return apply_placeholders(templates.cpp_module_template, check=True, module_name=self.module_name, py_module_name=self.py_module_name,
                                      module_submodules="\n".join(submodules) if len(submodules) > 0 else "",
                                      module_variable_getters="\n".join(getters) if len(setters) > 0 else "",
                                      module_variable_setters="\n".join(setters) if len(setters) > 0 else "",
                                      module_constants="\n".join(constants) if len(constants) > 0 else "",
                                      module_types="\n".join(module_types) if len(module_types) > 0 else "",
                                      types="\n".join([type.to_code() for type in types]) if len(types) > 0 else "",
                                      module_functions="\n".join(module_functions) if len(module_functions) > 0 else "",
                                      functions="\n".join(functions) if len(functions) > 0 else "")

def make_custom_type_type(name: str, component: Component):
    is_owned = "TypeOwned" in component.export_attributes
    is_transient = "TypeNonTransient" not in component.export_attributes and not is_owned
    if is_transient:
        type_name = f"{name}*"
    elif not is_owned:
        type_name = f"{name}&"
    else:
        type_name = f"{name}"
    return type_name

def generate_header_args(context: GeneratorContext) -> dict:
    headers = set()
    types = []
    type_converters = []
    modules = set()
    for component in context.components:
        modules.add(component.module)
        # We only need to export types for now, functions and operations can just as well be performed on the underlying
        # type and would require fully parsing the whole API here to build the correct function template
        if "ExportPublic" in component.export_attributes:
            # Types don't have template arguments, we can skip those
            namespace, name, _ = get_type_name(component)
            type_name = make_custom_type_type(namespace + name, component)

            types.append(apply_placeholders(templates.cpp_custom_type_header_declaration_template, name=name, type_name=type_name, template_opts=""))
            type_converters.append(apply_placeholders(templates.cpp_custom_type_converter, type_name=type_name, name=get_type_name_without_namespace(name)))
            headers.update(component.requires)

    header_file_args = {}
    header_file_args["header_include"] = "\n".join(apply_placeholders(templates.cpp_dependency_include, include=include) for include in headers)
    header_file_args["header_dependency_includes"] = "\n".join(
        apply_placeholders(templates.cpp_dependency_include, include=dep.target_header_path) for dep in context.config.dependencies.values())
    header_file_args["custom_public_type_declarations"] = "\n".join(types)
    header_file_args["type_converters"] = "\n".join(type_converters)
    header_file_args["extern_modules"] = "\n".join(apply_placeholders(templates.cpp_module_extern_template, module_name=make_module_declaration_name(module)) for module in modules)
    return header_file_args

def make_module_declaration_name(name: str) -> str:
    mod_parts = name.split(".")
    return "".join([part.capitalize() for part in mod_parts])

def generate_source_args(context: GeneratorContext) -> dict:
    headers = set()
    modules = {}
    private_types = []
    type_converters = []
    def get_or_make_module(module_name, extern=True):
        mod = modules.get(module_name, None)
        if mod is None:
            py_name = module_name
            mod_parts = py_name.split(".")
            mod_name = make_module_declaration_name(module_name)
            print(f"Creating module {module_name} as {mod_name} with parts {mod_parts[-1]}")
            mod = GeneratorModule(mod_name, mod_parts[-1], context)
            mod.is_extern = extern
            modules[py_name] = mod

            if len(mod_parts) > 1:
                parent = get_or_make_module(".".join(mod_parts[:-1]))
                parent.add_submodule(mod)
        if mod.is_extern and not extern:
            mod.is_extern = False
        return mod

    # Process headers and types first, so adding free operators is easier later
    for component in context.components:
        headers.update(component.requires)
        mod = get_or_make_module(component.module, False)
        if component.name is not None:
            mod.add_type(component)
            if "ExportPublic" not in component.export_attributes:
                # Types don't have template arguments, we can skip those
                namespace, name, _ = get_type_name(component)
                type_name = make_custom_type_type(namespace + name, component)
                private_types.append(apply_placeholders(templates.cpp_custom_type_source_declaration_template, type_name=type_name, name=name, template_opts=""))
                type_converters.append(apply_placeholders(templates.cpp_custom_type_converter, type_name=type_name, name=get_type_name_without_namespace(name)))

    for component in context.components:
        if "ExportPublic" in component.export_attributes:
            for header in component.requires:
                if header in headers:
                    headers.remove(header)
        mod = get_or_make_module(component.module, False)
        if component.name is None:
            # Globals component, these definitions values go into the module
            for property in component.properties:
                mod.add_property(property)
            for function in component.functions:
                mod.add_function(function)
            for operator in component.operators:
                mod.add_operator(operator)

    touched_modules = set()
    ordered_modules = []
    modules_queue = list(modules.values())
    while len(modules_queue) > 0:
        peek = modules_queue[-1]
        if all([dep in ordered_modules for dep in peek.modules]):
            ordered_modules.append(modules_queue.pop())
        else:
            if peek in touched_modules:
                raise ValueError(f"Module {peek.module_name} has a circular dependency, {touched_modules}, {ordered_modules}, {peek.modules}")
            touched_modules.add(peek)
            for mod in peek.modules:
                if mod not in ordered_modules:
                    modules_queue.remove(mod)
                    modules_queue.append(mod)

    source_file_args = {}
    primary_header = os.path.basename(context.config.target_header_path).removeprefix("./") if context.config.target_header_path is not None else ""
    source_file_args["primary_header_include"] = apply_placeholders(templates.cpp_dependency_include, include=f"\"{primary_header}\"")
    source_file_args["custom_private_type_declarations"] = "\n".join(private_types)
    source_file_args["header_include"] = "\n".join([apply_placeholders(templates.cpp_dependency_include, include=include) for include in headers])
    source_file_args["module_template"] = "\n".join(module.to_code() for module in ordered_modules)
    source_file_args["type_converters"] = "\n".join(type_converters)
    return source_file_args

def write_header(fd, context: GeneratorContext):
    fd.write(apply_placeholders(templates.cpp_header, **generate_header_args(context)))
def write_source(fd, context: GeneratorContext):
    fd.write(apply_placeholders(templates.cpp_source, **generate_source_args(context)))

source_exts = [".h", ".hpp", ".cpp", ".cxx", ".cc", ".c"]
def analyze_directory(directory: str, parser_config: ParserConfig, log: bool) -> Iterable[Component]:
    for root, dirs, files in os.walk(directory):
        for file in files:
            if os.path.splitext(file)[1] in source_exts:
                if log:
                    print(f"Analyzing {file}")
                yield from analyze_file(os.path.join(root, file), parser_config)

def get_components(config, parser_config: ParserConfig, log: bool = True) -> tuple[Iterable[Component], dict[str, Iterable[Component]]]:
    if log:
        print(f"Analyzing {config.base_directory}")
    components: Iterable[Component] = analyze_directory(config.base_directory, parser_config, log)
    dependencies: dict[str, Iterable[Component]] = {}
    for dep_path, dep_config in config.dependencies.items():
        dependencies[dep_path] = analyze_directory(dep_config.base_directory, parser_config, log)
    return list(components), dict(dependencies)

def generate_code(context: GeneratorContext) -> None:
    if context.config.target_is_stdout:
        write_header(sys.stdout, context)
    else:
        target = context.config.target_header
        if target is not None:
            with target as fd:
                write_header(fd, context)

    if context.config.target_is_stdout:
        write_source(sys.stdout, context)
    else:
        target = context.config.target_source
        if target is not None:
            with target as fd:
                write_source(fd, context)

def build_config(args: Union[argparse.Namespace, dict[str, str]], compiler_args: list[str]) -> 'Config':
    if isinstance(args, argparse.Namespace):
        args = vars(args)
    config: Config = Config(args["source"])
    parsed_compiler_args = parse_compiler_args(compiler_args)
    if "variables" in args and args["variables"] is not None:
        config.set(*args["variables"])
    for key, value in parsed_compiler_args.defines.items():
        config[key] = value
    if "output" in args and args["output"] is not None:
        # Allow overriding the target path, but generally expect to keep the same name as the source file
        config.target_path = args["output"]

    # Set the rest of the parameters, placeholders may be used
    if "include" in args and args["include"] is not None:
        config.include_paths = list(args["include"])
    if "CFLAGS" in args and args["CFLAGS"] is not None:
        config.add_include_paths_from_flags(str(args["CFLAGS"]))
    if "CXXFLAGS" in args and args["CXXFLAGS"] is not None:
        config.add_include_paths_from_flags(str(args["CXXFLAGS"]))
    if "CPPFLAGS" in args and args["CPPFLAGS"] is not None:
        config.add_include_paths_from_flags(str(args["CPPFLAGS"]))
    config.add_include_path(config.base_directory)
    for include_path in parsed_compiler_args.header_paths:
        config.add_include_path(include_path)
    config.load_dependencies()
    return config

def add_generator_parameters(argparser: argparse.ArgumentParser):
    argparser.add_argument("--source", "-s", type=str, help="Path to the source json file")
    argparser.add_argument("--output", "-o", type=str, help="Path to the target directory, relative to the working directory or absolute, if specified")
    argparser.add_argument("--include", "-I", action="append", type=str, help="Path of the include directory, relative to the working directory or absolute if specified")
    argparser.add_argument("--dependency", "-i", action="append", type=str, help="Path of an additional dependency json file, relative to the working directory, in search path or absolute if specified.")
    argparser.add_argument('variables', nargs='*', help='Makefile-style variables (e.g., VAR=value)')

if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="Generate Python integration code for C++ types, components and systems")
    add_generator_parameters(parser)
    add_parser_parameters(parser)
    parser.add_argument("file", type=str, help="Path to the source file for a parsing test")
    compiler_args_index = index if (index := sys.argv.index("--")) != -1 else len(sys.argv)
    args = parser.parse_args(sys.argv[:compiler_args_index])
    config = build_config(args, sys.argv[compiler_args_index + 1:])
    if "parser_config" in config:
        parser_config = ParserConfig(TagConfig.load(config["parser_config"]))
    else:
        parser_config = ParserConfig(TagConfig.default())

    from .parser import analyze_file
    if config.source_path is None:
        raise ValueError("No source file specified")

    components, dependencies = get_components(config, parser_config)
    ensure_namespaced_type_refs(components, dependencies)
    if not validate_components(components, dependencies):
        print("Validation failed", file=sys.stderr)
        sys.exit(1)
    context = GeneratorContext(config, components, dependencies)
    generate_code(context)
