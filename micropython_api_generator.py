#  Copyright 2023 Hel Industries, all rights reserved.
#
#  For licensing terms, Please find the licensing terms in the closest
#  LICENSE.txt in this repository file going up the directory tree.
#

import argparse
import sys

from micropython_generator.config import ParserConfig, TagConfig
from micropython_generator.generator import add_generator_parameters, build_config, generate_code, get_components, GeneratorContext
from micropython_generator.parser import add_parser_parameters, ensure_namespaced_type_refs, validate_components, \
    print_components, fix_header_references

if __name__ == "__main__":
    parser: argparse.ArgumentParser = argparse.ArgumentParser(description="Generate Python integration code for C++ types, components and systems")
    add_generator_parameters(parser)
    add_parser_parameters(parser)
    parser.add_argument("--targetpath", action="store_true", help="Print the target path")
    parser.add_argument("--basepath", action="store_true", help="Print the target path")
    parser.add_argument("--sources", action="store_true", help="Print the source files")
    parser.add_argument("--log", action="store_true", help="Print parsed components")
    #parser.add_argument("file", type=str, help="Path to the source file for a parsing test")
    compiler_args_index = index if (index := sys.argv.index("--")) != -1 else len(sys.argv)
    args = parser.parse_args(sys.argv[:compiler_args_index])
    config = build_config(args, sys.argv[compiler_args_index + 1:])
    if "parser_config" in args and args.parser_config is not None:
        parser_config = ParserConfig(TagConfig.load(args.parser_config))
    else:
        parser_config = ParserConfig(TagConfig.default())

    if config.source_path is None:
        raise ValueError("No source file specified")

    if "targetpath" in args and args.targetpath:
        print(config.target_path)
        sys.exit(0)
    if "basepath" in args and args.basepath:
        print(config.base_directory)
        sys.exit(0)

    if args.log:
        print(config)
    components, dependencies = get_components(config, parser_config, args.log)
    if "sources" in args and args.sources:
        sources = set([component.path for component in components])
        print("\n".join(sources))
        sys.exit(0)

    if args.log:
        print_components(components)
    ensure_namespaced_type_refs(components, dependencies)
    if not validate_components(components, dependencies):
        print("Validation failed", file=sys.stderr)
        sys.exit(1)
    if not fix_header_references(components, config, sys.stderr):
        print("Header resolution failed", file=sys.stderr)
        sys.exit(2)
    context = GeneratorContext(config, components, dependencies)
    generate_code(context)
