# MicroPython API Generator

This tool generates C++ MicroPython module bindings from annotated C++ code. It creates the necessary wrapper code to
expose C++ classes, functions, properties, and operators to Python scripts.

## Overview

The ScriptingApiGenerator analyzes C++ source files with special annotations and generates MicroPython compatible C++ 
code that provides Python bindings for the annotated elements.

## Usage

### Annotated C++ Example

```cpp
// Example class annotation
MPyClass(TypeOwned)
class MyClass
{
    // Property annotation
    MPyProperty(ReadOnly)
    int Value;
    
    // Function annotation
    MPyFunction(name="calculate")
    int Calculate(int a, int b);
};

// Module annotation
MPyModule(Math)
```

### Building

The generator can be run directly using:

```bash
python3 Tools/ScriptingApiGenerator/ScriptingApiGenerator.py path/to/module.json [options]
```

It can also be integrated into a Makefile build:

```bash
make -f Tools/ScriptingApiGenerator/MicroPythonModule.mk MICROPYTHON_MODULE_TARGET=path/to/module.json
```

## Configuration

The generator uses a JSON configuration file to control code generation:

```json
{
  "target_path": "output/path",
  "base_directory": "./",
  "include_paths": ["include/dir1", "include/dir2"],
  "variables": {
    "MODULE_NAME": "MyModule"
  }
}
```

## Type Conversion

The generator handles type conversion between C++ and Python types using the `MPGPyType` template system. Standard types 
like integers, floats, booleans, and strings are automatically supported. For this reason, it is required, that the
include directory is in your header search path.

## Parser Configuration

The parser can be configured to recognize custom tags and annotations. A custom parser configuration can be specified 
with the `--parser-config` argument.
