"""Top-level API exposure of package actions"""

__version__ = "0.1.0.0"

import os
import sys
import fnmatch

from .sggpio import PackageWithManifestReader, PackageWithManifestWriter, PackageReader, PackageWriter
from .entries import AtlasEntry, TextureEntry
 
def list_contents(name, *patterns, logger=lambda s: None):
  with PackageWithManifestReader(name) as f:
    for entry in f:
      if not _entry_match(patterns, entry):
        continue
      
      logger(f'{entry.name}')

      atlas = entry.manifest_entry
      if atlas and hasattr(atlas, 'subAtlases'):
        for subatlas in atlas.subAtlases:
          subname = subatlas['name']
          logger(f'  {subname}')

def extract(package, target_dir, *entries, subtextures=False, logger=lambda s: None):
  includes = []

  if len(target_dir) == 0:
    target_dir = os.path.splitext(package)[0]

  os.makedirs(target_dir, exist_ok=True)
  with PackageWithManifestReader(package) as f:
    if f.manifest is None and subtextures:
      logger('Exporting subtextures requires a manifest. --subtextures flag ignored')
      subtextures=False

    for entry in f:
      if not _entry_match(entries, entry):
        continue

      logger(f'Extracting entry {entry.name}')
      entry.extract(target_dir, subtextures=subtextures)

    if not f.manifest is None:
      for entry in f.manifest.values():
        if not _entry_match(entries, entry):
          continue
        
        logger(f'Extracting manifest entry {entry.name}')
        entry.extract(target_dir, subtextures=subtextures, includes=includes)

    if len(includes) > 0:
      include_dir = os.path.join(target_dir, 'manifest')
      os.makedirs(include_dir, exist_ok=True)
      with open(os.path.join(include_dir, 'includes.txt'), 'w') as inc_f:
        logger(f'Writing includes to {inc_f.name}')
        for include in includes:
          inc_f.write(include)
          inc_f.write('\n')

def pack(source_dir, package, *entries, logger=lambda s: None):
  curdir = os.getcwd()
  source = os.path.join(curdir, source_dir)
  target = package

  if len(target) == 0:
    target = f'{os.path.basename(source)}.pkg'

  logger(f'Packing {source} to target package {target}')

  manifest_dir = os.path.join(source, 'manifest')
  manifest_entries = []
  logger('Scanning Manifest')
  for filename in os.listdir(manifest_dir):
    if filename.endswith('.json'):
      entry = _load_manifest_entry(os.path.join(manifest_dir, filename))
      if not _entry_match(entries, entry):
        continue
      logger(entry.name)
      manifest_entries.append(entry)
  
  with PackageWriter(target, compressor='lz4') as pkg_writer, PackageWriter(f'{target}_manifest') as manifest_writer:
    for manifest_entry in manifest_entries:
      entry_name = manifest_entry.name.split('\\')[-1]
      entry_sheet_path = os.path.join(source, 'textures', 'atlases', f'{entry_name}.png')
      if os.path.exists(entry_sheet_path):
        logger(f'Packing {entry_sheet_path}')
        manifest_writer.write_entry(manifest_entry)
        texture_entry = TextureEntry()
        texture_entry.name = manifest_entry.referencedTextureName
        texture_entry.import_file(entry_sheet_path)
        pkg_writer.write_entry(texture_entry)
      else:
        logger(f'Could not find atlas image for {entry_name}. Entry will be skipped.')

def patch(name, *patches, logger=lambda s : None):
  # Rename existing package/manifest so we can edit in place
  package_old_path = f'{name}.old'
  os.replace(name, package_old_path)
  manifest_path = f'{name}_manifest'
  manifest_old_path = f'{package_old_path}_manifest'
  os.replace(manifest_path, manifest_old_path)

  # Get the entries to replace in the package from the patches
  patch_entries = {}
  for patch in patches:
    for entry in PackageWithManifestReader(patch):
      patch_entries[entry.name] = entry

  # Open the old package for reading and a new package for writing
  with PackageWithManifestReader(package_old_path) as source, PackageWithManifestWriter(name, compressor=source.compressor, version=source.version) as target:
    # Scan source package, replacing entries with the patched versions if present
    for entry in source:
      if entry.name in patch_entries:
        # Write the entry from the patches
        logger(f'Applying patch to entry {entry.name}')
        target.write_entry_with_manifest(patch_entries.pop(entry.name))
      else:
        # No matching entry in patches, so just write the original entry
        logger(f'No patch for entry {entry.name}, using original entry')
        target.write_entry_with_manifest(entry)

    # Append any entries in patches that weren't in the source
    for entry in patch_entries.values():
      logger(f'Appending entry {entry.name}')
      target.write_entry_with_manifest(entry)
        
  # Delete the old files
  os.remove(package_old_path)
  os.remove(manifest_old_path)

def _load_manifest_entry(filename):
  if filename.endswith(".atlas.json"):
    entry = AtlasEntry()
    entry.import_file(filename)
    return entry
  else:
    raise NotImplementedError('Unsupported manifest file type')

def _entry_match(patterns, entry):
  if patterns is None or len(patterns) == 0:
    return True
  else:
    for pattern in patterns:
      if fnmatch.fnmatch(entry.short_name(), pattern):
        return True
  return False