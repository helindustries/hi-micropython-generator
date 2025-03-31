#  Copyright 2025 $author, All rights reserved.
from python_utilities.placeholders import apply_placeholders

# C++ templates:
cpp_header = """// Auto-generated file, do not edit, your changes will be overridden

${header_include:empty_no_line}
${header_dependency_includes:empty_no_line}
#include "Scripting/System/TIScriptingUtilities.h"
#include <memory>

#if defined(_MSC_VER)
#pragma warning(push)
#pragma warning(disable: 4100) // unused parameter
#pragma warning(disable: 4189) // unused local variable
#elif defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wunused-variable"
#elif defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
#pragma clang diagnostic ignored "-Wunused-variable"
#endif

extern "C"
{
    #include "py/obj.h"
    #include "py/runtime.h"

    ${custom_public_type_declarations:keep_indent,empty_no_line}

    ${extern_modules:keep_indent,empty_no_line}
}

namespace Tiny::Scripting::Utilities
{
    ${type_converters:keep_indent,empty_no_line}
}

#if defined(_MSC_VER)
#pragma warning(pop)
#elif defined(__GNUC__)
#pragma GCC diagnostic pop
#elif defined(__clang__)
#pragma clang diagnostic pop
#endif
"""
cpp_source = """// Auto-generated file, do not edit, your changes will be overridden
${primary_header_include:empty_no_line}
${header_include:empty_no_line}

using namespace Tiny::Scripting::Utilities;

#if defined(_MSC_VER)
#pragma warning(push)
#pragma warning(disable: 4100) // unused parameter
#pragma warning(disable: 4189) // unused local variable
#elif defined(__GNUC__)
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wunused-function"
#pragma GCC diagnostic ignored "-Wunused-variable"
#elif defined(__clang__)
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
#pragma clang diagnostic ignored "-Wunused-variable"
#endif

extern "C"
{
    #include "py/obj.h"
    #include "py/runtime.h"

    ${custom_private_type_declarations:keep_indent,empty_no_line}
}

namespace Tiny::Scripting::Utilities
{
    ${type_converters:keep_indent,empty_no_line}
}

extern "C"
{
    ${module_template:keep_indent,empty_no_line}
}

#if defined(_MSC_VER)
#pragma warning(pop)
#elif defined(__GNUC__)
#pragma GCC diagnostic pop
#elif defined(__clang__)
#pragma clang diagnostic pop
#endif
"""
cpp_dependency_include = "#include ${include}"

cpp_function_return_void = "return mp_const_none;"
cpp_function_return_result = "return TIPyType<${type}>::To(result);"
cpp_function_outparam = "TIPyType<${type}>::To(${name})"
cpp_function_return_outparam = """
mp_obj_t outParams[] = {${out_params}};
return mp_obj_new_tuple(${out_param_count}, outParams);
"""
cpp_function_return_result_outparam = """
mp_obj_t outParams[] = {TIPyType<${type}>::To(result), ${out_params}};
return mp_obj_new_tuple(${out_param_count} + 1, outParams);
"""
cpp_function_call_return = """
auto result = ${namespace}${name}(${args});
${return_code}
"""
cpp_function_call_noreturn = """
${namespace}${name}(${args});
${return_code}
"""
# Types:
#  - Owned types: Any non-pointer, non-reference type
#  - Unowned types:
#     - Pointer types: Any object that can be created or destroyed from the C++ side, needs to be a weak pointer
#        - This should default to a default implementation of the bool operator
#     - Reference types: Any object that is not created or destroyed from the C++ side after init
#        - NonTransient
#  - We accept, that a type can only ever be used in one way by the Python implementation, if we need to use them in
#    multiple ways, we need to create a new type for each use, like Type, TypeRef and TypePtr.
#  - It would also be nice to have a way of using weak_ptr, shared_ptr and the like. We should likely make FromPyType
#    return a bool and a reference parameter for the actual reference or pointer value depending on whether the type
#    is marked nullable
#  - On the other hand, we are on embedded and we are going to use pointers primarily as array elements
# Parameters:
#  - only custom types in the dependencies can be used
#  - as long as we pass the correct TType and indicate owned and transient as template parameters, we should be
#    able to handle creation of the auto-locals inside the templates
#  - type:
#     - for simple types, int, float and the like, we can use the unmodified local, no modification needed to call
#        - this needs to work for custom types as well, like half and fixed
#     - TI*Span needs to be treated as a list of the underlying type, even as a value type
#     - std::string and std::string_view need to be treated as strings, even as a value type
#     - TIDateTime and TITimeSpan need to be treated as their respective datetime and timespan counterparts
#     - for complex types, we have the following options:
#        - Owned types: we need to create a value type local from the type conversion, can std::move the args to a
#          function call for better performance, they aren't needed later
#        - Unowned types:
#           - NonTransient types we can just assign the value, will result in a copy
#           - Transient will need to deref the weak pointer
#  - type&:
#     - for simple types, we create a value type local and pass the reference, const or no const
#     - for special types, the same rules apply as for the value types
#     - for complex types, we can expect to have a custom type implementation
#        - Owned types: we need to get the value reference from FromPyType, then we can pass the reference to the function
#        - Unowned types: for NonTransient, we can pass the reference directly, for Transient, we need to deref the weak pointer
#        - in either case, we can keep a potential const qualifier
#     - This may be used for a value-type out-parameter
#  - type*:
#     - for simple types, we can create a local and pass the pointer
#     - for special types, the same rules apply as for the value types
#     - for complex types, we can expect to have a custom type implementation
#        - Owned types: we need to get the value reference from FromPyType, then we can pass the pointer
#        - Unowned types: for NonTransient, we can pass the pointer directly, for Transient, we need to deref the weak pointer
#        - in either case, we can keep a potential const qualifier
#     - This may be used for a value-type out-parameter
#     - This may be used as an array (even though we don't really want it to be, span would be better), by being tagged
#       either as TinyParam(NullTerminatedArray) for null-termination, in which case we need to find the length,
#       or TinyParam(Array(n)) for fixed-size arrays. We need to pass these back as value types of the given type
#  - type&&:
#     - we are going to reject on parsing, this is not a valid type to use for an API binding level using our code generator
# Return values:
# Variables:
#  - type&:
#  - const type&:
cpp_method_call_return = """
auto result = self->Value${ref_or_ptr}${name}(${args});
${return_code}
"""
cpp_method_call_noreturn = """
self->Value${ref_or_ptr}${name}(${args});
${return_code}
"""
cpp_static_method_call_noreturn = """
${namespace}${type}::${name}(${args});
${return_code}
"""
cpp_static_method_call_return = """
auto result = ${namespace}${type}::${name}(${args});
${return_code}
"""
cpp_method_kwvarargs_self_init = """
auto* self = static_cast<Py${type_name}*>(MP_OBJ_TO_PTR(args[0]));
"""
cpp_method_fixedargs_self_init = """
auto* self = static_cast<Py${type_name}*>(MP_OBJ_TO_PTR(self_in));
"""
cpp_function_base_return = "return ${base_call};"
cpp_function_raise_args_return = """
mp_raise_TypeError("Invalid arguments");
return mp_const_none;
"""

cpp_function_base_call_kwargs_to_kwargs = """
if (auto result = ${name}Impl(n_args, args, kwargs); result != MP_OBJ_NULL) return result;
"""
cpp_function_base_call_kwargs_to_varargs = """
if (auto result = ${name}Impl(n_args, args); result != MP_OBJ_NULL) return result;
"""
cpp_function_base_call_kvarwargs_to_fixedarg = "args[{index}]"
cpp_function_base_call_kwargs_to_fixedargs = """
if (n_args >= {arg_count})
    if (auto result = ${name}Impl(${args}); result != MP_OBJ_NULL) return result;
"""
cpp_function_base_call_varargs_to_varargs = """
if (auto result = ${name}Impl(n_args, args); result != MP_OBJ_NULL) return result;
"""
cpp_function_base_call_varargs_to_fixedargs = """
if (n_args == {arg_count}) if (auto result = ${name}Impl(${args}); result != MP_OBJ_NULL) return result;
"""
cpp_function_base_call_fixedargs_to_fixedargs = """
if (auto result = ${name}Impl(${args}); result != MP_OBJ_NULL) return result;
"""

cpp_function_kwargs = """
inline mp_obj_t Py${name}Impl(size_t n_args, const mp_obj_t *args, mp_map_t *kwargs)
{
    ${self_init:keep_indent,empty_no_line}
    ${kwarg_init:keep_indent,empty_no_line}
    ${overloads:keep_indent,empty_no_line}
    return MP_OBJ_NULL;
}

STATIC mp_obj_t Py${name}(size_t n_args, const mp_obj_t *args)
{
    if (auto result = Py${name}Impl(n_args, args, nullptr); result != MP_OBJ_NULL) return result;
    ${base_calls:keep_indent,empty_no_line}
    mp_raise_TypeError("Invalid arguments");
    return mp_const_none;
}
//STATIC MP_DEFINE_CONST_FUN_OBJ_KW(Py${name}Obj, ${min_arg_count}, Py${name});
const mp_obj_fun_builtin_var_t Py${name}Obj = {{&mp_type_fun_builtin_var}, MP_OBJ_FUN_MAKE_SIG(${min_arg_count}, MP_OBJ_FUN_ARGS_MAX, true), .fun = {.kw = Py${name}}}
"""
cpp_function_kwargs_overload_nooptionals = """
if (${overload_check})
{
    ${arg_init:keep_indent,empty_no_line}
    ${call_function:keep_indent}
}
"""
cpp_function_kwvarargs_check = "TIPyType<${type}>::Is(args[${arg_index}])"
cpp_function_required_overload_nooptionals_check = "n_args == ${required_count} && ${arg_checks}"
cpp_function_required_overload_withoptionals_check = "n_args >= ${required_count} && ${arg_checks}"
cpp_function_kwargs_overload_withoptionals = """
if (${required_check})
{
    const auto kwargs_used = kwargs->used - ${required_count} + (n_args > ${required_count} ? ${required_count} : n_args);
    if (kwargs_used == 0 || ${optional_check})
    {
        ${arg_init:keep_indent,empty_no_line}
        ${call_function:keep_indent}
    }
}
"""
cpp_function_kwarg_check = "${name}_obj_present && TIPyType<${type}>::Is(${name}_obj)"
cpp_function_kwarg_optional_check = "(kwargs_used == ${optional_count} && ${arg_checks})"
cpp_function_kwarg_init_template = """
mp_obj_t ${name}_obj = mp_const_none;
auto ${name}_obj_present = FindInMap(kwargs, \"${name}\", &${name}_obj);
"""
cpp_function_kwarg_init_with_default = """
if (n_args > ${arg_index}) { ${name}_obj = args[${arg_index}]; ${name}_obj_present = true; }
${type} ${name} = ${default};
if (${name}_obj_present) ${name} = TIPyType<${type}>::From(${name}_obj);
"""
cpp_function_kwargs_init_required = """
if (n_args > ${arg_index}) ${name}_obj = args[${arg_index}];
auto ${name} = TIPyType<${type}>::From(${name}_obj);
"""

cpp_function_varargs = """
inline mp_obj_t Py${name}Impl(size_t n_args, const mp_obj_t *args)
{
    ${self_init:keep_indent,empty_no_line}
    ${overloads:keep_indent,empty_no_line}
    return MP_OBJ_NULL;
}

STATIC mp_obj_t Py${name}(size_t n_args, const mp_obj_t *args)
{
    if (auto result = Py${name}Impl(n_args, args); result != MP_OBJ_NULL) return result;
    ${base_calls:keep_indent,empty_no_line}
    mp_raise_TypeError("Invalid arguments");
    return mp_const_none;
}
//MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(Py${name}Obj, ${min_arg_count}, ${max_arg_count}, Py${name});
const mp_obj_fun_builtin_var_t Py${name}Obj = {{&mp_type_fun_builtin_var}, MP_OBJ_FUN_MAKE_SIG(${min_arg_count}, ${max_arg_count}, false), .fun = {.var = Py${name}}};
"""
cpp_function_varargs_init_withdefault = """
${type} ${name} = ${default};
if (n_args > ${arg_index}) ${name} = TIPyType<${type}>::From(args[${arg_index}]);
"""
cpp_function_init_required = """auto ${name} = TIPyType<${type}>::From(args[${arg_index}]);"""
cpp_function_varargs_overload = """
if (${overload_check})
{
    ${arg_init:keep_indent,empty_no_line}
    ${call_function:keep_indent}
}
"""

cpp_function_fixed_init_arg = """auto ${name} = TIPyType<${type}>::From(${obj_name}_obj);"""
cpp_function_fixed_args_check = "TIPyType<${type}>::Is(${name}_obj)"
cpp_function_fixed_overload = """
if (${overload_check})
{
    ${arg_init:keep_indent,empty_no_line}
    ${call_function:keep_indent}
}
"""
cpp_function_fixed_overloads = """
inline mp_obj_t Py${name}Impl(${args})
{
    ${self_init:keep_indent,empty_no_line}

    ${overloads:keep_indent,empty_no_line}

    return MP_OBJ_NULL;
}

STATIC mp_obj_t Py${name}(${args})
{
    if (auto result = Py${name}Impl(${arg_names}); result != MP_OBJ_NULL) return result;
    ${base_calls:keep_indent,empty_no_line}
    mp_raise_TypeError("Invalid arguments");
    return mp_const_none;
}
//MP_DEFINE_CONST_FUN_OBJ_${arg_count}(Py${name}Obj, Py${name});
STATIC const mp_obj_fun_builtin_fixed_t Py${name}Obj = {{&mp_type_fun_builtin_${arg_count}}, .fun = {._${arg_count} = Py${name}}};
"""
cpp_function_fixed_unchecked = """
STATIC mp_obj_t Py${name}(${args})
{
    ${self_init:keep_indent,empty_no_line}
    ${args_init:keep_indent,empty_no_line}
    ${call_function:keep_indent}
}
//MP_DEFINE_CONST_FUN_OBJ_${arg_count}(Py${name}Obj, Py${name});
STATIC const mp_obj_fun_builtin_fixed_t Py${name}Obj = {{&mp_type_fun_builtin_${arg_count}}, .fun = {._${arg_count} = Py${name}}};
"""
cpp_function_fixed_unchecked_long = """
STATIC mp_obj_t Py${name}(size_t n_args, const mp_obj_t *args)
{
    ${self_init:keep_indent,empty_no_line}
    ${args_init:keep_indent,empty_no_line}
    ${call_function:keep_indent}
}
//MP_DEFINE_CONST_FUN_OBJ_VAR_BETWEEN(Py${name}Obj, ${arg_count}, ${arg_count}, Py${name});
const mp_obj_fun_builtin_var_t Py${name}Obj = {{&mp_type_fun_builtin_var}, MP_OBJ_FUN_MAKE_SIG(${arg_count}, ${arg_count}, false), .fun = {.var = Py${name}}};
"""

cpp_custom_type_header_declaration_template = """
struct Py${name} : public Tiny::Scripting::Utilities::TIPythonObjectType<${type_name}>
{ static const mp_obj_type_t PyType; };
STATIC mp_obj_t PyMake${name}(${type_name} value);
STATIC mp_obj_t Py${name}Init(const mp_obj_type_t* type, size_t n_args, size_t, size_t n_kwargs, const mp_obj_t* args);
STATIC void Py${name}Attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest);
STATIC mp_obj_t Py${name}UnaryOp(mp_unary_op_t op, mp_obj_t value);
STATIC mp_obj_t Py${name}BinaryOp(mp_binary_op_t op, mp_obj_t lhs, mp_obj_t rhs);
STATIC mp_obj_t Py${name}Index(mp_obj_t self_in, mp_obj_t index, mp_obj_t value);
"""
cpp_custom_type_source_declaration_template = """
struct Py${name} : public Tiny::Scripting::Utilities::TIPythonObjectType<${type_name}> 
{ static const mp_obj_type_t PyType; };
STATIC mp_obj_t PyMake${name}(${type_name} value);
STATIC mp_obj_t Py${name}Init(const mp_obj_type_t* type, size_t n_args, size_t n_kwargs, size_t, const mp_obj_t* args);
STATIC void Py${name}Attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest);
STATIC mp_obj_t Py${name}UnaryOp(mp_unary_op_t op, mp_obj_t value);
STATIC mp_obj_t Py${name}BinaryOp(mp_binary_op_t op, mp_obj_t lhs, mp_obj_t rhs);
STATIC mp_obj_t Py${name}Index(mp_obj_t self_in, mp_obj_t index, mp_obj_t value);
"""
cpp_custom_type_converter = "template <> struct TIPyTypeMap<Tiny::CleanBaseType<${type_name}>> { using Value = Py${name}; };"
cpp_custom_type_subscript_template = "if (TIPyType<${type_name}>::Is(${index_type})) return Subscript<${self_type}, ${index_type}, ${return_type}>(self, index, value);"
cpp_custom_type_unary_op_template = "case MP_UNARY_OP_${name}: return TIPyType<${return_type}>::To(${unary_op}self->Value);"
cpp_custom_type_unary_op_template_map = {
    "+": apply_placeholders(cpp_custom_type_unary_op_template, False, name="POSITIVE", unary_op="+"),
    "-": apply_placeholders(cpp_custom_type_unary_op_template, False, name="NEGATIVE", unary_op="-"),
    "~": apply_placeholders(cpp_custom_type_unary_op_template, False, name="INVERT", unary_op="~"),
    "bool": "case MP_UNARY_OP_BOOL: return Tiny:IsValid(self->Value) ? mp_const_true : mp_const_false;",
    "hash": "case MP_UNARY_OP_HASH: return MP_OBJ_NEW_SMALL_INT(Tiny::HashCode(self->Value));"
}
cpp_custom_type_binary_op_name_map = {"+" : "ADD", "-" : "SUBTRACT", "*" : "MULTIPLY", "/" : "TRUE_DIVIDE", "//" : "FLOOR_DIVIDE", "%" : "MODULO",
                                      "**" : "POWER", "<<" : "LSHIFT", ">>" : "RSHIFT", "&" : "AND", "|" : "OR", "^" : "XOR", "+=" : "INPLACE_ADD",
                                      "-=" : "INPLACE_SUBTRACT", "*=" : "INPLACE_MULTIPLY", "/=" : "INPLACE_TRUE_DIVIDE", "//=" : "INPLACE_FLOOR_DIVIDE",
                                      "%=" : "INPLACE_MODULO", "**=" : "INPLACE_POWER", "<<=" : "INPLACE_LSHIFT", ">>=" : "INPLACE_RSHIFT",
                                      "&=" : "INPLACE_AND", "|=" : "INPLACE_OR", "^=" : "INPLACE_XOR"}
cpp_custom_type_binary_op_template = """
case MP_BINARY_OP_${name}:
    ${overloads:keep_indent,empty_no_line}
    break;
"""
cpp_custom_type_binary_op_overload = """
if (TIPyType<${type}>::Is(rhsObj))
{
    auto rhs = TIPyType<${type}>::From(rhsObj);
    ${binary_op:keep_indent,empty_no_line}
}"""
cpp_custom_type_binary_op_bool_template = "return lhs->Value ${op} rhs ? mp_const_true : mp_const_false;"
cpp_custom_type_binary_op_value_template = "return TIPyType<${return_type}>::To(lhs->Value ${op} rhs);"
cpp_custom_type_binary_op_input_value_template = "lhs->Value ${op}= rhs; return lhsObj;"
cpp_custom_type_binary_op_template_map = {
    "==": apply_placeholders(cpp_custom_type_binary_op_bool_template, False, op="=="), "!=": apply_placeholders(cpp_custom_type_binary_op_bool_template, False, op="!="),
    "<": apply_placeholders(cpp_custom_type_binary_op_bool_template, False, op="<"), "<=": apply_placeholders(cpp_custom_type_binary_op_bool_template, False, op="<="),
    ">": apply_placeholders(cpp_custom_type_binary_op_bool_template, False, op=">"), ">=": apply_placeholders(cpp_custom_type_binary_op_bool_template, False, op=">="),
    "+": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="+"), "-": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="-"),
    "*": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="*"), "/": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="/"),
    "//": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="//"), "%": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="%"),
    "**": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="**"), "<<": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="<<"),
    ">>": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op=">>"), "&": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="&"),
    "|": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="|"), "^": apply_placeholders(cpp_custom_type_binary_op_value_template, False, op="^"),
    "+=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="+"), "-=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="-"),
    "*=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="*"), "/=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="/"),
    "//=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="//"), "%=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="%"),
    "**=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="**"), "<<=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="<<"),
    ">>=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op=">>"), "&=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="&"),
    "|=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="|"), "^=": apply_placeholders(cpp_custom_type_binary_op_input_value_template, False, op="^")
}
cpp_custom_type_base = "&Py${parent_type}::PyType"
cpp_custom_type_bases = """
STATIC const mp_obj_type_t* Py${type_name}Bases[] =
{
    ${base_list:keep_indent,empty_no_line}
};

STATIC mp_obj_tuple_t Py${type_name}BasesTuple =
{
    .base = {&mp_type_tuple},
    .len = ${base_count},
    .items = {(mp_obj_t *)&Py${type_name}Bases}
};
"""
#cpp_custom_type_bases_entry = ", parent, &Py${type_name}BasesTuple"
cpp_custom_type_bases_entry = ", &Py${type_name}BasesTuple"
#cpp_custom_type_bases_single = ", parent, ${type_name}"
cpp_custom_type_bases_single = ", ${type_name}"
cpp_custom_type_bases_slot_index = ", .slot_index_parent = 7"
cpp_custom_type_base_attr = "Py${parent_type}Attr(self_in, attr, dest);"
cpp_custom_type_base_unary_op = "if (auto result = Py${parent_type}UnaryOp(op, value); result != MP_OBJ_NULL) return result;"
cpp_custom_type_base_binary_op = "if (auto result = Py${parent_type}BinaryOp(op, lhsObj, rhsObj); result != MP_OBJ_NULL) return result;"
cpp_custom_type_base_subscript = "if (auto result = Py${parent_type}Index(self_in, index, value); result != MP_OBJ_NULL) return result;"
cpp_custom_type_getter_template = "if (attr == MP_QSTR_${py_name}) dest[0] = TIPyType<${type}>::To(self->Value${ref_or_ptr}${value});"
cpp_custom_type_setter_template = "if (attr == MP_QSTR_${py_name}) { self->Value${ref_or_ptr}${value} = TIPyType<${type}>::From(dest[1]); return; }"
#cpp_custom_type_attr_getter_template = "if (attr == MP_QSTR_${name}) { ${attr_getter_code}; dest[0] = value; }"
#cpp_custom_type_attr_setter_template = "if (attr == MP_QSTR_${name}) { ${attr_setter_code}; ${value} = value; dest[0] = MP_OBJ_NULL; }"
cpp_custom_type_owned_constructor = """
new (&self->Value) ${namespace}${type_name}(${args});
"""
cpp_custom_type_owned_init = """
STATIC mp_obj_t Py${type_name}Init(const mp_obj_type_t* type, size_t n_args, size_t n_kwargs, size_t, const mp_obj_t* args)
{
    auto* self = mp_obj_malloc(Py${type_name}, type);
    ${constructors:keep_indent,empty_no_line}
    ${init_code:keep_indent,empty_no_line}
    return MP_OBJ_FROM_PTR(self);
}
"""
cpp_custom_type_unowned_init = """
STATIC mp_obj_t Py${type_name}Init(const mp_obj_type_t* type, size_t n_args, size_t n_kwargs, size_t, const mp_obj_t* args)
{
    mp_raise_TypeError("Constructing ${type_name} not allowed${factory}!");
}
"""
cpp_custom_type_owned_destroy_entry = "{MP_ROM_QSTR(MP_QSTR___del__), MP_ROM_PTR(&Py${type_name}DestroyObj)},"
cpp_custom_type_owned_destroy = """
STATIC mp_obj_t Py${type_name}Destroy(mp_obj_t self_in)
{
    auto* self = static_cast<Py${type_name}*>(MP_OBJ_TO_PTR(self_in));
    self->Value.~${type_name}();
    return mp_const_none;
}
//STATIC MP_DEFINE_CONST_FUN_OBJ_1(Py${type_name}DestroyObj, Py${type_name}Destroy);
STATIC const mp_obj_fun_builtin_fixed_t Py${type_name}DestroyObj = {{&mp_type_fun_builtin_1}, .fun = {._1 = Py${type_name}Destroy}};
"""
cpp_custom_type_source_template = """
${make_new:empty_no_line,keep_indent}
${destroy:empty_no_line,keep_indent}

STATIC mp_obj_t PyMake${name}(${type_name} value)
{
    return TIPyType<${type_name}>::To(value);
}

STATIC void Py${name}Attr(mp_obj_t self_in, qstr attr, mp_obj_t* dest)
{
    auto* self = static_cast<Py${name}*>(MP_OBJ_TO_PTR(self_in));
    if (dest[0] == MP_OBJ_NULL)
    {
        ${base_attrs}
        ${attr_getters:keep_indent,empty_no_line}
        dest[1] = MP_OBJ_SENTINEL;
    }
    else if (dest[0] == MP_OBJ_SENTINEL)
    {
        if (dest[1] == MP_OBJ_NULL) { dest[0] = MP_OBJ_NULL; return; }
        ${base_attrs}
        ${attr_setters:keep_indent,empty_no_line}
    }
}

STATIC mp_obj_t Py${name}UnaryOp(mp_unary_op_t op, mp_obj_t value)
{
    auto* self = static_cast<Py${name}*>(MP_OBJ_TO_PTR(value));
    switch (op)
    {
        ${unary_ops:keep_indent,empty_no_line}
        default: break;
    }

    ${base_unary_ops}
    return MP_OBJ_NULL;
}

STATIC mp_obj_t Py${name}BinaryOp(mp_binary_op_t op, mp_obj_t lhsObj, mp_obj_t rhsObj)
{
    auto* lhs = static_cast<Py${name}*>(MP_OBJ_TO_PTR(lhsObj));
    switch (op)
    {
        ${binary_ops:keep_indent,empty_no_line}
        default: break;
    }
    ${base_binary_ops}
    return MP_OBJ_NULL;
}

STATIC mp_obj_t Py${name}Index(mp_obj_t self_in, mp_obj_t index, mp_obj_t value)
{
    auto* self = static_cast<Py${name}*>(MP_OBJ_TO_PTR(self_in));
    ${subscripts:keep_indent,empty_no_line}
    ${base_subscripts:keep_indent,empty_no_line};
    return MP_OBJ_NULL;
}

${functions:empty_no_line}

STATIC const mp_rom_map_elem_t Py${name}DictTable[] =
{
    ${destroy_entry:keep_indent,empty_no_line}
    ${type_constants:keep_indent,empty_no_line}
    ${type_functions:keep_indent,empty_no_line}
};
${bases_tuple_def:empty_no_line}
STATIC MP_DEFINE_CONST_DICT(Py${name}Dict, Py${name}DictTable);
//MP_DEFINE_CONST_OBJ_TYPE(Py${name}Type, MP_QSTR_${py_type_name}, MP_TYPE_FLAG_NONE, make_new, Py${name}Init,
//                         unary_op, Py${name}UnaryOp, binary_op, Py${name}BinaryOp, attr, Py${name}Attr,
//                         subscr, Py${name}Index, locals_dict, &Py${name}Dict${bases_tuple_entry});
const mp_obj_type_t Py${name}Type = {.base = { &mp_type_type }, .flags = MP_TYPE_FLAG_NONE, .name = MP_QSTR_${py_type_name},
                                     .slot_index_make_new = 1, .slot_index_unary_op = 2, .slot_index_binary_op = 3, 
                                     .slot_index_attr = 4, .slot_index_subscr = 5${bases_slot_index}, .slot_index_locals_dict = 6,
                                     .slots = {(const void*)Py${name}Init, (const void*)Py${name}UnaryOp, (const void*)Py${name}BinaryOp,
                                               (const void*)Py${name}Attr, (const void*)Py${name}Index, &Py${name}Dict${bases_tuple_entry}}};
extern "C++" { const mp_obj_type_t Py${name}::PyType = Py${name}Type; }
"""

# Function and method templates, methods use the owning object as the first argument
cpp_type_to_pytype_map = {"int64_t": "int", "int32_t": "int", "int16_t": "int", "int8_t": "int", "int": "int",
                          "uint64_t": "int", "uint32_t": "int", "uint16_t": "int", "uint8_t": "int",
                          "float": "float", "double": "float", "bool": "bool",
                          "std::string": "str", "std::string_view": "str", "char*": "str"}
cpp_pytype_to_rom_ptr_map = {"int": "INT", "float": "FLOAT", "str": "QSTR", "bool": "BOOL", "object": "PTR"}
cpp_module_constant_template = "{MP_ROM_QSTR(MP_QSTR_${py_name}), MP_ROM_${type}(${value})},"
cpp_module_function_template = "{MP_ROM_QSTR(MP_QSTR_${py_name}), MP_ROM_PTR(&Py${name}Obj)},"
cpp_module_type_template = "{MP_ROM_QSTR(MP_QSTR_${py_name}), MP_ROM_PTR(&Py${name}::PyType)},"
cpp_module_submodule_template = "{MP_ROM_QSTR(MP_QSTR_${py_name}), MP_ROM_PTR(&Py${name}UserModule)},"
cpp_module_variable_getter_template = "if (attr == MP_QSTR_${py_name}) return TIPyType<${type}>::To(${value});"
cpp_module_variable_setter_template = "if (attr == MP_QSTR_${py_name}) { ${value} = TIPyType<${type}>::From(value); return mp_const_none; }"
cpp_module_template = """
${functions:keep_indent,empty_no_line}

${types:keep_indent,empty_no_line}
STATIC mp_obj_t Py${module_name}GetAttr(mp_obj_t self_in, mp_obj_t attr_obj)
{
    auto attr = mp_obj_str_get_qstr(attr_obj);
    ${module_variable_getters:keep_indent,empty_no_line}
    return mp_load_attr(self_in, attr);
}
//STATIC MP_DEFINE_CONST_FUN_OBJ_2(Py${module_name}GetAttrObj, Py${module_name}GetAttr);
STATIC const mp_obj_fun_builtin_fixed_t Py${module_name}GetAttrObj = {{&mp_type_fun_builtin_2}, .fun = {._2 = Py${module_name}GetAttr}};

STATIC mp_obj_t Py${module_name}SetAttr(mp_obj_t self_in, mp_obj_t attr_obj, mp_obj_t value)
{
    auto attr = mp_obj_str_get_qstr(attr_obj);
    ${module_variable_setters:keep_indent,empty_no_line}
    mp_store_attr(self_in, attr, value);
    return mp_const_none;
}
//STATIC MP_DEFINE_CONST_FUN_OBJ_3(Py${module_name}SetAttrObj, Py${module_name}SetAttr);
STATIC const mp_obj_fun_builtin_fixed_t Py${module_name}SetAttrObj = {{&mp_type_fun_builtin_3}, .fun = {._3 = Py${module_name}SetAttr}};

STATIC const mp_rom_map_elem_t Py${module_name}ModuleGlobalsTable[] =
{
    {MP_ROM_QSTR(MP_QSTR___name__), MP_ROM_QSTR(MP_QSTR_${py_module_name})},
    {MP_ROM_QSTR(MP_QSTR___getattr__), MP_ROM_PTR(&Py${module_name}GetAttrObj)},
    {MP_ROM_QSTR(MP_QSTR___setattr__), MP_ROM_PTR(&Py${module_name}SetAttrObj)},
    ${module_constants:keep_indent,empty_no_line}
    ${module_submodules:keep_indent,empty_no_line}
    ${module_functions:keep_indent,empty_no_line}
    ${module_types:keep_indent,empty_no_line}
};

STATIC MP_DEFINE_CONST_DICT(Py${module_name}ModuleGlobals, Py${module_name}ModuleGlobalsTable);
const mp_obj_module_t Py${module_name}UserModule =
{
    .base = {&mp_type_module},
    .globals = (mp_obj_dict_t *)&Py${module_name}ModuleGlobals,
};
MP_REGISTER_MODULE(MP_QSTR_${py_module_name}, Py${module_name}UserModule);
"""
cpp_module_extern_template = """extern const mp_obj_module_t Py${module_name}UserModule;"""
