"""Main entry point for the command-line interface"""

__version__ = "0.0.3.0"

import os
import sys
import argparse
import fnmatch

from .sggpio import PackageWithManifestReader, PackageReader, PackageWriter
from .entries import AtlasEntry, TextureEntry

def main():
  parser = argparse.ArgumentParser(prog='deppth', description='Decompress, Extract, Pack for Pyre, Transistor, and Hades')
  subparsers = parser.add_subparsers(help='The action to perform', dest='action')

  # List parser
  list_parser = subparsers.add_parser('list', help='List the entries of a package', aliases=['ls'])
  list_parser.add_argument('path', metavar='path', type=str, help='The path to the package to act on')
  list_parser.add_argument('patterns', metavar='patterns', nargs='*', help='Patterns to search for')
  list_parser.set_defaults(func=plist)

  # Extract parser
  extract_parser = subparsers.add_parser('extract', help='Extract assets from a package', aliases=['ex'])
  extract_parser.add_argument('source', metavar='source', type=str, help='The path to extract')
  extract_parser.add_argument('-t', '--target', metavar='target', default='', help='Where to extract the package')
  extract_parser.add_argument('-e', '--entries', nargs='*', metavar='entry', help='One or more entry names to extract')
  extract_parser.add_argument('-s', '--subtextures', action='store_true', default=False, help='Export subtextures instead of full atlases')
  extract_parser.set_defaults(func=extract)

  # Pack parser
  pack_parser = subparsers.add_parser('pack', help='Pack assets into a package', aliases=['pk'])
  pack_parser.add_argument('-s', '--source', metavar='source', default='', type=str, help='Path to the folder to pack, default is current folder')
  pack_parser.add_argument('-t', '--target', metavar='target', default='', help='Path of output file')
  pack_parser.set_defaults(func=pack)

  args = parser.parse_args()
  args.func(args)

def plist(args):
  path = args.path
  patterns = args.patterns

  if not os.path.exists(path + '.pkg'):
    print('Error: Specified package does not exist')
    return

  with PackageWithManifestReader(path) as f:
    for entry in f:
      if not entry_match(patterns, entry):
        continue
      
      print(f'{entry.name}')

      atlas = entry.manifest_entry
      if atlas and hasattr(atlas, 'subAtlases'):
        for subatlas in atlas.subAtlases:
          subname = subatlas['name']
          print(f'  {subname}')

def extract(args):
  source = args.source
  target = args.target
  entries = args.entries
  subtextures = args.subtextures
  includes = []

  if len(target) == 0:
    target = source

  os.makedirs(target, exist_ok=True)
  with PackageWithManifestReader(source) as f:
    if f.manifest is None and subtextures:
      print('Exporting subtextures requires a manifest. --subtextures flag ignored')
      subtextures=False

    for entry in f:
      if not entry_match(entries, entry):
        continue

      entry.extract(target, subtextures=subtextures)

    if not f.manifest is None:
      for entry in f.manifest.values():
        if not entry_match(entries, entry):
          continue

        entry.extract(target, subtextures=subtextures, includes=includes)

    if len(includes) > 0:
      include_dir = os.path.join(target, 'manifest')
      os.makedirs(include_dir, exist_ok=True)
      with open(os.path.join(include_dir, 'includes.txt'), 'w') as inc_f:
        for include in includes:
          inc_f.write(include)
          inc_f.write('\n')

def pack(args):
  curdir = os.getcwd()
  source = os.path.join(curdir, args.source)
  target = args.target
  #entries = args.entries

  if len(target) == 0:
    target = f'{os.path.basename(source)}.pkg'

  print(f'Packing {source} to target package {target}')

  manifest_dir = os.path.join(source, 'manifest')
  manifest_entries = []
  print('Scanning Manifest')
  for filename in os.listdir(manifest_dir):
    if filename.endswith('.json'):
      entry = load_manifest_entry(os.path.join(manifest_dir, filename))
      print(entry.name)
      manifest_entries.append(entry)
  
  with PackageWriter(target, compressor='lz4') as pkg_writer, PackageWriter(f'{target}_manifest') as manifest_writer:
    for manifest_entry in manifest_entries:
      entry_name = manifest_entry.name.split('\\')[-1]
      entry_sheet_path = os.path.join(source, 'textures', 'atlases', f'{entry_name}.png')
      if os.path.exists(entry_sheet_path):
        print(f'Packing {entry_sheet_path}')
        manifest_writer.write_entry(manifest_entry)
        texture_entry = TextureEntry()
        texture_entry.name = manifest_entry.referencedTextureName
        texture_entry.import_file(entry_sheet_path)
        pkg_writer.write_entry(texture_entry)
      else:
        print(f'Could not find atlas image for {entry_name}. Entry will be skipped.')

def entry_match(patterns, entry):
  if patterns is None or len(patterns) == 0:
    return True
  else:
    for pattern in patterns:
      if fnmatch.fnmatch(entry.short_name(), pattern):
        return True
  return False

def load_manifest_entry(filename):
  if filename.endswith(".atlas.json"):
    entry = AtlasEntry()
    entry.import_file(filename)
    return entry
  else:
    raise NotImplementedError('Unsupported manifest file type')
 