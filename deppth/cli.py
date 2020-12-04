"""Command-line interface for deppth functionality"""
import os
import argparse

from .deppth import list_contents, pack, patch, extract

def main():
  parser = argparse.ArgumentParser(prog='deppth', description='Decompress, Extract, Pack for Pyre, Transistor, and Hades')
  subparsers = parser.add_subparsers(help='The action to perform', dest='action')

  # List parser
  list_parser = subparsers.add_parser('list', help='List the entries of a package', aliases=['ls'])
  list_parser.add_argument('path', metavar='path', type=str, help='The path to the package to act on')
  list_parser.add_argument('patterns', metavar='pattern', nargs='*', help='Patterns to search for')
  list_parser.set_defaults(func=cli_list)

  # Extract parser
  extract_parser = subparsers.add_parser('extract', help='Extract assets from a package', aliases=['ex'])
  extract_parser.add_argument('source', metavar='source', type=str, help='The path to extract')
  extract_parser.add_argument('-t', '--target', metavar='target', default='', help='Where to extract the package')
  extract_parser.add_argument('-e', '--entries', nargs='*', metavar='entry', help='One or more entry names to extract')
  extract_parser.add_argument('-s', '--subtextures', action='store_true', default=False, help='Export subtextures instead of full atlases')
  extract_parser.set_defaults(func=cli_extract)

  # Pack parser
  pack_parser = subparsers.add_parser('pack', help='Pack assets into a package', aliases=['pk'])
  pack_parser.add_argument('-s', '--source', metavar='source', default='', type=str, help='Path to the folder to pack, default is current folder')
  pack_parser.add_argument('-t', '--target', metavar='target', default='', help='Path of output file')
  pack_parser.add_argument('-e', '--entries', nargs='*', metavar='entry', help='Only pack entries matching these patterns')
  pack_parser.set_defaults(func=cli_pack)

  # Patch parser
  patch_parser = subparsers.add_parser('patch', help='Patch a package, replacing or adding entries from patches', aliases=['pt'])
  patch_parser.add_argument('package', metavar='package', type=str, help='The package to patch')
  patch_parser.add_argument('patches', metavar='patches', nargs='*', help='The patches to apply')
  patch_parser.set_defaults(func=cli_patch)

  args = parser.parse_args()
  args.func(args)

def cli_list(args):
  path = args.path
  patterns = args.patterns

  list_contents(path, *patterns, logger=lambda s: print(s))

def cli_extract(args):
  source = args.source
  target = args.target
  entries = args.entries or []
  subtextures = args.subtextures

  extract(source, target, *entries, subtextures=subtextures)

def cli_pack(args):
  curdir = os.getcwd()
  source = os.path.join(curdir, args.source)
  target = args.target
  entries = args.entries or []

  pack(source, target, *entries, logger=lambda s: print(s))

def cli_patch(args):
  package = args.package
  patches = args.patches
  patch(package, *patches, logger=lambda s : print(s))