// Copyright 2025 $author, All rights reserved.

#pragma once

#include <type_traits>
#include <cstring>

extern "C"
{
    #include <py/obj.h>
    #include <py/runtime.h>
}

namespace Hel::MicroPython
{
    static inline bool FindInMap(mp_map_t *kwargs, const char *name, mp_obj_t& value)
    {
        for (size_t i = 0; i < kwargs->used; ++i)
        {
            mp_map_elem_t *elem = &kwargs->table[i];
            if (mp_obj_is_qstr(elem->key))
            {
                qstr arg_name = mp_obj_str_get_qstr(elem->key);
                const char *arg_name_str = qstr_str(arg_name);
                if (strcmp(arg_name_str, name) == 0)
                {
                    value = elem->value;
                    return true;
                }
            }
        }

        return false;
    }

    template <typename TType>
    using CleanBaseType = std::remove_cv_t<std::remove_pointer_t<std::remove_reference_t<TType>>>;

    template <typename TType>
    struct HIPythonObjectType
    {
        using Type = TType;
        using BaseType = CleanBaseType<TType>;
        TType Value;
    };

    template <typename TType>
    struct HIPythonObjectAllocator
    {
        static TType* Alloc()
        {
            static_assert(always_false<TType>, "No custom allocator for type");
            return nullptr;
        }
    private:
        template <typename T>
        static constexpr bool always_false = false;
    };

    template <typename TType, typename = std::void_t<>>
    struct TIHasPythonObjectAllocatorCondition : std::false_type {};
    template <typename TType>
    struct TIHasPythonObjectAllocatorCondition<TType, std::void_t<typename HIPythonObjectAllocator<TType>::Type>> : std::true_type {};
    template <typename TType>
    struct TIHasPythonObjectAllocatorValue : std::enable_if<TIHasPythonObjectAllocatorCondition<TType>::value> {};
    template <typename TType>
    using TIHasPythonObjectAllocator = typename TIHasPythonObjectAllocatorValue<TType>::type;

    template <typename TType, typename = std::void_t<>>
    struct HIPyTypeMap { using Value = void; };

    template <typename TType, typename = std::void_t<>>
    struct TIHasPythonObjectTypeCondition : std::false_type {};
    template <typename TType>
    struct TIHasPythonObjectTypeCondition<TType, std::void_t<typename std::enable_if<!std::is_same_v<typename HIPyTypeMap<CleanBaseType<TType>>::Value, void>>::type>> : std::true_type {};
    template <typename TType>
    struct TIHasPythonObjectTypeValue : std::enable_if<TIHasPythonObjectTypeCondition<TType>::value> {};
    template <typename TType>
    using TIHasPythonObjectType = typename TIHasPythonObjectTypeValue<TType>::type;

    template <typename TType, typename = std::void_t<>>
    struct TIIsPythonWrapperType : std::false_type {};
    template <typename TType>
    struct TIIsPythonWrapperType<TType, std::void_t<decltype(TType::PyType), std::is_same<decltype(TType::PyType), mp_obj_type_t>>> : std::true_type {};

    template <typename TType, typename Enable = void>
    struct HIPyType
    {
        static bool Is(mp_obj_t value)
        {
            static_assert(always_false<TType>, "No Python conversion defined for this type");
            return false;
        }
        static auto From(mp_obj_t value)
        {
            static_assert(always_false<TType>, "No Python conversion defined for this type");
            return nullptr;
        }
        static mp_obj_t To(TType value)
        {
            static_assert(always_false<TType>, "No Python conversion defined for this type");
            return MP_OBJ_NULL;
        }
    private:
        template <typename T>
        static constexpr bool always_false = false;
    };

    template <typename TType>
    struct HIPyType<TType, std::enable_if_t<TIHasPythonObjectTypeCondition<TType>::value>>
    {
        using BaseType = CleanBaseType<TType>;
        using PyWrapper = typename HIPyTypeMap<BaseType>::Value;
        static bool Is(mp_obj_t value) { return mp_obj_is_type(value, &PyWrapper::PyType); }

        static auto From(mp_obj_t value)
        {
            if constexpr (std::is_pointer_v<TType>)
            {
                if (Is(value))
                {
                    auto* self = static_cast<PyWrapper*>(MP_OBJ_TO_PTR(value));
                    if constexpr (std::is_pointer_v<typename PyWrapper::Type>) return self->Value;
                    else return &self->Value;
                }
                return nullptr;
            }
            else
            {
                if (Is(value))
                {
                    auto* self = static_cast<PyWrapper*>(MP_OBJ_TO_PTR(value));
                    if constexpr (std::is_pointer_v<typename PyWrapper::Type>) return *self->Value;
                    else return self->Value;
                }
                static CleanBaseType<TType> nullValue{};
                return nullValue;
            }
        }

        static mp_obj_t To(TType value)
        {
            PyWrapper* self = mp_obj_malloc(PyWrapper, &PyWrapper::PyType);
            if constexpr (std::is_pointer_v<TType>)
            {
                if constexpr (std::is_pointer_v<typename PyWrapper::Type>) self->Value = value;
                else self->Value = *value;
            }
            else if constexpr (std::is_reference_v<TType>)
            {
                if constexpr (std::is_pointer_v<typename PyWrapper::Type>) self->Value = &value;
                else self->Value = value;
            }
            else if constexpr (std::is_pointer_v<typename PyWrapper::Type> || std::is_reference_v<typename PyWrapper::Type>)
            {
                if constexpr (TIHasPythonObjectAllocatorCondition<TType>::value)
                    if constexpr (std::is_pointer_v<typename PyWrapper::Type>) self->Value = HIPythonObjectAllocator<TType>::Alloc();
                    else self->Value = *HIPythonObjectAllocator<TType>::Alloc();
                else
                {
                    static_assert(always_false<TType>, "Creation of a Python un-owned object wrapper from a temporary value type without allocator is not supported!");
                    return MP_OBJ_NULL;
                }
            }
            else self->Value = value;

            return MP_OBJ_FROM_PTR(self);
        }
    private:
        template <typename T>
        static constexpr bool always_false = false;
    };

    template <typename TType>
    struct HIPyType<TType*, std::enable_if_t<std::is_integral_v<TType>>>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_int(value); }
        static TType From(mp_obj_t value) { return mp_obj_get_int(value); }
        static mp_obj_t To(TType* value) { return mp_obj_new_int(*value); }
    };
    template <typename TType>
    struct HIPyType<TType&, std::enable_if_t<std::is_integral_v<TType>>>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_int(value); }
        static TType From(mp_obj_t value) { return mp_obj_get_int(value); }
        static mp_obj_t To(TType& value) { return mp_obj_new_int(value); }
    };
    template <typename TType>
    struct HIPyType<TType, std::enable_if_t<std::is_integral_v<TType>>>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_int(value); }
        static TType From(mp_obj_t value) { return mp_obj_get_int(value); }
        static mp_obj_t To(TType value) { return mp_obj_new_int(value); }
    };

    template <typename TType>
    struct HIPyType<TType*, std::enable_if_t<std::is_floating_point_v<TType>>>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_float(value); }
        static TType From(mp_obj_t value) { return mp_obj_get_float(value); }
        static mp_obj_t To(TType* value) { return mp_obj_new_float(*value); }
    };
    template <typename TType>
    struct HIPyType<TType&, std::enable_if_t<std::is_floating_point_v<TType>>>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_float(value); }
        static TType From(mp_obj_t value) { return mp_obj_get_float(value); }
        static mp_obj_t To(TType& value) { return mp_obj_new_float(value); }
    };
    template <typename TType>
    struct HIPyType<TType, std::enable_if_t<std::is_floating_point_v<TType>>>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_float(value); }
        static TType From(mp_obj_t value) { return mp_obj_get_float(value); }
        static mp_obj_t To(TType value) { return mp_obj_new_float(value); }
    };

    template <>
    struct HIPyType<bool*>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_bool(value); }
        static bool From(mp_obj_t value) { return mp_obj_is_true(value); }
        static mp_obj_t To(bool* value) { return mp_obj_new_bool(*value); }
    };
    template <>
    struct HIPyType<bool&>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_bool(value); }
        static bool From(mp_obj_t value) { return mp_obj_is_true(value); }
        static mp_obj_t To(bool& value) { return mp_obj_new_bool(value); }
    };
    template <>
    struct HIPyType<bool>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_bool(value); }
        static bool From(mp_obj_t value) { return mp_obj_is_true(value); }
        static mp_obj_t To(bool value) { return mp_obj_new_bool(value); }
    };

    template <>
    struct HIPyType<char*>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_str(value); }
        static const char* From(mp_obj_t value) { return mp_obj_str_get_str(value); }
        static mp_obj_t To(const char* value) { return mp_obj_new_str(value, strlen(value)); }
    };

    template <>
    struct HIPyType<const char*>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_str(value); }
        static const char* From(mp_obj_t value) { return mp_obj_str_get_str(value); }
        static mp_obj_t To(const char* value) { return mp_obj_new_str(value, strlen(value)); }
    };

#if TINY_SCRIPTING_ENABLE_STRING
    template <>
    struct HIPyType<std::string>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_str(value); }
        static std::string From(mp_obj_t value) { return std::string(mp_obj_str_get_str(value)); }
        static mp_obj_t To(const std::string& value) { return mp_obj_new_str(value.c_str(), value.size()); }
    };
    template <>
    struct HIPyType<std::string*>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_str(value); }
        static std::string* From(mp_obj_t value) { return new std::string(mp_obj_str_get_str(value)); }
        static mp_obj_t To(std::string* value) { return mp_obj_new_str(value->c_str(), value->size()); }
    };
    template <>
    struct HIPyType<std::string&>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_str(value); }
        static std::string& From(mp_obj_t value) { return *new std::string(mp_obj_str_get_str(value)); }
        static mp_obj_t To(std::string& value) { return mp_obj_new_str(value.c_str(), value.size()); }
    };

    template <>
    struct HIPyType<std::string_view>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_str(value); }
        static std::string_view From(mp_obj_t value) { return std::string_view(mp_obj_str_get_str(value)); }
        static mp_obj_t To(const std::string_view& value) { return mp_obj_new_str(value.data(), value.size()); }
    };
    template <>
    struct HIPyType<std::string_view*>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_str(value); }
        static std::string_view* From(mp_obj_t value) { return new std::string_view(mp_obj_str_get_str(value)); }
        static mp_obj_t To(std::string_view* value) { return mp_obj_new_str(value->data(), value->size()); }
    };
    template <>
    struct HIPyType<std::string_view&>
    {
        static bool Is(mp_obj_t value) { return mp_obj_is_str(value); }
        static std::string_view& From(mp_obj_t value) { return *new std::string_view(mp_obj_str_get_str(value)); }
        static mp_obj_t To(std::string_view& value) { return mp_obj_new_str(value.data(), value.size()); }
    };
#endif

    template <typename TPyType, typename TSubscript, typename TData>
    mp_obj_t Subscript(TPyType* self, mp_obj_t subscript_obj, TData value)
    {
        auto subscript = HIPyType<TSubscript>::To(subscript_obj);
        if (value == MP_OBJ_SENTINEL) { return HIPyType<TData>::To(self->Value[subscript]); }
        else { self->Value[subscript] = HIPyType<TData>::From(value); return mp_const_none; }
    }
}
