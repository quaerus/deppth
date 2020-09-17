from abc import ABC, abstractmethod
import os
import json
from .utils import requires, BytesIO as _BytesIO, FileIO as _FileIO

try: import PIL.Image
except ImportError: pass

_entry_types = {}                   # Stores a mapping of known entry types from their byte codes

def get_entry(b, stream, is_manifest=False):
  return _entry_types[b](stream, isManifest=is_manifest)

def entry(typeName, typeCode):
  """Decorates a subclass of EntryBase to register its name and byte code.
  
  This makes the class discoverable by the entry reading code to find the 
  correct subclass to read the entry's data from the stream.
  """
  def decorate_entry(cls):
    cls._typeName = typeName
    cls._typeCode = typeCode
    if typeCode:
      _entry_types[typeCode] = cls
    return cls
  return decorate_entry

class EntryBase(ABC):
  """Base class for package entries.

  When reading entries from packages, each one should be
  an instance of a subclass of this class.
  """
  _typeName = 'base'
  _typeCode = b'x\00'

  def __init__(self, stream=None, isManifest=False, version=7):
    """Creates an instance of an entry.

    If the stream parameter is provided, this constructor will
    immediately call read_from to initialize its contents from
    data read from that stream.

    If the current package being loaded is a manifest, isManifest
    should be set to True. There is a small amount of logic that
    depends on this.

    The version parameter should be the version number of the
    containing package. Packages for Hades are currently version 7.
    Packages for Transistor and Pyre are version 5.
    """
    self.name = ""  # Generally this should be set by subclasses
    self.manifest_entry = None
    if stream is not None:
      self.read_from(stream, isManifest, version)

  @abstractmethod
  def read_from(self, stream, isManifest=False, version=7):
    """Initializes the entry by unpacking data from a stream.
    
    This method is called whenever a PackageReader is reading an
    entry, just after the entry type byte has been read. The format
    of the data after the entry type byte depends on the entry type.
    Subclasses of EntryBase override this method to correctly read
    the following bytes.
    """
    pass
  
  @abstractmethod
  def write_to(self, stream):
    """Pack the entry, writing it to a stream.
    
    This method is called whenever a PackageWriter is writing an entry,
    just after the entry type byte has been written. The format of the
    data depends on the entry type. Subclasses of EntryBase override
    this method to write the right bytes.
    """
    pass

  def display_name(self):
    """A display name for the entry in e.g. command-line interfaces."""
    dispname = self.name
    return f'{self.entry_type()}: {dispname}'

  def short_name(self):
    return self.name.split('\\')[-1]

  def entry_type(self):
    """Returns the type of entry this is as a human-readable string."""
    return self._typeName

  def export_file(self, path):
    """Exports this entry to a file.

    The extension of the path determines how the entry will be exported.
    All entries support exporting to a .entry file, which will contain the raw
    binary representation of the entry within an uncompressed package.

    Subclasses may override the _export function to allow exporting to other
    formats.
    """
    if not self._export(path):
      raise NotImplementedError(f'Unable to export file to this format: {path}')

  def extract(self, target, **kwargs):
    """Extracts this entry from the package to the target directory.

    This exports the asset as export_file might, but doesn't give the user choice
    as to how that export is performed. This function is expected to create
    one or more files in the directory given by target based on the name and
    type of the entry.

    If not overridden, this function will export a binary representation of the
    entry to a .entry file.
    """
    self._export(self._extraction_path(target) + '.entry')

  def import_file(self, path):
    """Imports this entry from a file.

    The extension of the path determines how the entry will be imported.
    All entries support importing from a .entry file, which should contain the raw
    binary representation of the entry within an uncompressed package.

    Subclasses may override the _import function to allow importing from other
    formats.
    """
    if not self._import(path):
      raise NotImplementedError(f'Unable to import file of this format: {path}')

  def _export(self, path):
    # If the extension isn't .entry, then we're out of ideas on how to export
    if os.path.splitext(path)[1] != '.entry':
      return False

    with _FileIO(path, 'wb') as f:
      f.write(self._typeCode)     # Write the type code byte
      self.write_to(f)            # Then write byte data for the entry
    return True

  def _import(self, path):
    # If the extension isn't .entry, then we're out of ideas on how to import
    if os.path.splitext(path)[1] != '.entry':
      return False

    with _FileIO(path, 'rb') as f:
      f.read(1)                   # Skip the entry code byte (we already knew it)
      self.read_from(f)           # Read the remaining bytes
    return True

  def _extraction_path(self, target):
    return os.path.join(target, self.name.split('\\')[-1])


class XNBAssetEntryBase(EntryBase):
  """Represents a wrapped XNB asset in a package.
  
  Both Texture2D and Texture3D entries are encoded into packages in the
  same way, so this class exists to provide logic common to both.

  Entries inheriting from this class support importing from and exporting
  to .xnb files, which can be generated by other tools, such as MonoGame
  Pipeline.
  """
  def read_from(self, stream, isManifest=False, version=7):
    self.name = stream.read_string()
    self.size = stream.read_int()
    self.data = stream.read(self.size)

  def write_to(self, stream):
    stream.write_string(self.name)
    stream.write_int(self.size)
    stream.write(self.data)

  def display_name(self):
    dispname = self.name.split('\\')[-1]
    return f'{self.entry_type()}: {dispname}'

  def extract(self, target, **kwargs):
    self._export(self._extraction_path(target) + '.xnb')

  def _export(self, path):
    if os.path.splitext(path)[1] != '.xnb':
      return super()._export(path)

    with open(path, 'wb') as f:
      f.write(self.data)

    return True

  def _import(self, path):
    if os.path.splitext(path)[1] != '.xnb':
      return super()._import(path)

    with open(path, 'rb') as f:
      self.data = f.read()

    return True

  def _extraction_path(self, target):
    return os.path.join(target, 'textures', self.name.split('\\')[-1])


@entry('texture', b'\xAD')
class TextureEntry(XNBAssetEntryBase):
  """Represents a 2D Texture asset.

  Texture entries comprise a majority of packages' contents. These entries
  are compiled spritesheets which are paired with an Atlas file in the
  package's manifest to identify the various sprites contained within.

  These entries can be exported to and imported from various image formats,
  but doing so requires the pillow/PIL module.
  """
  def extract(self, target, **kwargs):
    if 'subtextures' in kwargs and kwargs['subtextures']:
      self._export_subtextures(os.path.join(target, 'textures'))
    else:
      os.makedirs(os.path.join(target, 'textures', 'atlases'), exist_ok=True)
      self._export(self._extraction_path(target) + '.png')

  @requires('PIL.Image')
  def _export(self, path):
    # If the user didn't ask for a supported image format, then don't export
    if os.path.splitext(path)[1] not in ['.png', '.jpg', '.bmp']:
      return super()._export(path)

    self._get_image().save(path)
    return True

  @requires('PIL.Image')
  def _get_image(self):
    dataio = _BytesIO(self.data)

    # The first four bytes should be b'XNBw'
    dataio.seek(4)
    
    # The next byte is the XNB Version number, which should be 5 or 6
    xnbversion = ord(dataio.read(1))
    if not xnbversion in [5, 6]:
      raise ValueError(f'Invalid XNB Version: {xnbversion}')
    
    # The next byte represents some flags, which we ignore, possibly at our peril. 
    # If the flags aren't 0, bail. The data could be compressed
    flags = dataio.read(1)
    if flags != b'\x00':
      raise NotImplementedError(f'Cannot export compressed XNB data. Flags: {flags}')
    
    # The next four bytes are the file length, but we don't actually use this right now
    dataio.read(4)

    # For version 5 XNB's, there's some extra nonsense we can just skip past
    if (xnbversion == 5):
      num = dataio.read_7bit_encoded_int()
      for _ in range(0, num):
        dataio.read_string()
        dataio.read_int('little')
      dataio.read_7bit_encoded_int()
      dataio.read_7bit_encoded_int()

    imgformat = dataio.read_int('little')
    size = (dataio.read_int('little'), dataio.read_int('little'))
    dataio.read_int('little')  # mip level, it should always be 1
    numbytes = dataio.read_int('little')
    imgbytes = dataio.read(numbytes)
    if imgformat == 0:
      image = PIL.Image.frombytes('RGBA', size, imgbytes, 'raw', 'BGRA')
    elif imgformat == 6:
      image = PIL.Image.frombytes('RGBA', size, imgbytes, 'bcn', (3,))
    elif imgformat == 28:
      image = PIL.Image.frombytes('RGBA', size, imgbytes, 'bcn', (7,))
    else:
      raise Exception(f'Unsupported image format {imgformat}')
    return image
  
  def import_file(self, path):
    # If the user didn't give a supported image format, don't import here
    if os.path.splitext(path)[1] not in ['.png', '.jpg', '.bmp']:
      return super()._import(path)

    raise NotImplementedError("Not implemented yet")

  def _unpack(self, path):
    # Make a directory to hold the contents
    subpath = self.name.replace('\\', '/')
    fullpath = os.path.join(path, subpath)
    os.makedirs(fullpath, exist_ok=True)

    # First, get the image out of the entry data
    image = self._get_image()
    atlas = self.manifest_entry
    for subatlas in atlas.subAtlases:
      rect = subatlas['rect']
      box = (rect['x'], 
      rect['y'], 
      rect['x']+rect['width'], 
      rect['y']+rect['height'])
      subimage = image.crop(box)
      subatlasdir, subatlasfile = os.path.split(subatlas['name'])
      os.makedirs(os.path.join(fullpath, subatlasdir), exist_ok=True)
      subimage.save(os.path.join(fullpath, subatlasdir, f'{subatlasfile}.png'))

  @requires('PIL.Image')
  def _export_subtextures(self, target):
    # First, get the image out of the entry data
    image = self._get_image()
    atlas = self.manifest_entry
    for subatlas in atlas.subAtlases:
      rect = subatlas['rect']
      box = (rect['x'], 
      rect['y'], 
      rect['x']+rect['width'], 
      rect['y']+rect['height'])
      subimage = image.crop(box)
      subatlasdir, subatlasfile = os.path.split(subatlas['name'])
      os.makedirs(os.path.join(target, subatlasdir), exist_ok=True)
      subimage.save(os.path.join(target, subatlasdir, f'{subatlasfile}.png'))

  def _extraction_path(self, target):
    return os.path.join(target, 'textures', 'atlases', self.name.split('\\')[-1])


@entry('texture3d', b'\xAA')
class Texture3DEntry(XNBAssetEntryBase):
  """Represents a 3D Texture asset.

  These entires represent encoded three-dimensional images. The data within
  is essentially a stack of 2-d images -- you could imagine the data as voxels.
  3-d modeling/rendering software generally assumes an image format consisting
  of defined surfaces and shapes instead. It is therefore difficult to export
  this type of asset to something useful, unlike it's 2D cousin.

  For now, exporting and importing to anything other than .xnb or .entry is
  unsupported.
  """
  def _extraction_path(self, target):
    return os.path.join(target, 'textures', '3d', self.name.split('\\')[-1])


@entry('bink', b'\xBB')
class BinkEntry(EntryBase):
  """Represents a Bink asset.

  Bink is a video file format developed by RAD Game Tools, generally for
  full-motion video sequences. These entries don't contain all of that
  data, however, but instead merely contain references to those files.

  These entries are substantially more complicated in Hades' format, but 
  Hades doesn't seem to actually have these in its packages anymore. The
  correct parsing code is provided regardless.

  Because this entry doesn't really contain any data in and of itself,
  it cannot be exported to or imported from any format (other than the
  standard .entry)
  """
  def read_from(self, stream, isManifest=False, version=7):
    firstByte = stream.read(1)
    self.isAlpha = (firstByte == b'\x01')
    self.scaling = 1.0
    if firstByte == b'\xFF':
      num = stream.read_int()
      stream.read(1)
      if num > 0:
        self.scaling = stream.read_single()
    self.name = stream.read_string()

  def write_to(self, stream):
    pass

  def display_name(self):
    dispname = self.name.split('\\')[-1]
    return f'{self.entry_type()}: {dispname}'
  
  def extract(self, target, **kwargs):
    path = os.path.join(target, 'bink_refs')
    os.makedirs(path, exist_ok=True)
    super().extract(target, **kwargs)

  def _extraction_path(self, target):
    return os.path.join(target, 'bink_refs', self.name.split('\\')[-1])


@entry('atlas', b'\xDE')
class AtlasEntry(EntryBase):
  """Represents an Atlas map.

  Often found in manifests, atlas entries are meant to be paired with 2D
  textures to map out the different sprites contained within a sprite sheet.
  The data in the entry essentially amounts to encoding of the positions and
  sizes of various rectangles representing different sprites.

  Atlas entries can be exported to and imported from .json files.
  """
  def read_from(self, stream, isManifest=False, version=7):
    stream.read(4)  # This is the size, but we don't care about this and it gets ignored
    self.version = 0
    numSubAtlases = int.from_bytes(stream.read(4), byteorder='big')
    if (numSubAtlases == 2142336875):   # No, I can't explain this           
      self.version = stream.read_int()
      numSubAtlases = stream.read_int()
    self.subAtlases = []
    for _ in range(0, numSubAtlases):
      name = stream.read_string()
      rect = {
        'x': stream.read_int(),
        'y': stream.read_int(),
        'width': stream.read_int(),
        'height': stream.read_int()
      }
      topLeft = {
        'x': stream.read_int(),
        'y': stream.read_int()
      }
      originalSize = {
        'x': stream.read_int(),
        'y': stream.read_int()
      }
      scaleRatio = {
        'x': stream.read_single(),
        'y': stream.read_single()
      }
      isMulti = False
      isMip = False
      isAlpha8 = False
      if (self.version > 0):
        flags = ord(stream.read(1))
        if (self.version > 1):
          isMulti = (flags & 1) != 0
          isMip = (flags & 2) != 0
          if (self.version > 3):
              isAlpha8 = (flags & 4) != 0
      hullPoints = []
      if (self.version > 2):
        hullCount = stream.read_int()
        for _ in range(0, hullCount):
          hullPoints.append({
            'x': stream.read_int(),
            'y': stream.read_int()
          })
      self.subAtlases.append({
        'name': name,
        'rect': rect,
        'topLeft': topLeft,
        'originalSize': originalSize,
        'scaleRatio': scaleRatio,
        'isMulti': isMulti,
        'isMip': isMip,
        'isAlpha8': isAlpha8,
        'hull': hullPoints
      })
    
    if (int.from_bytes(stream.read(1), byteorder='big') == 221) or isManifest:
      self.isReference = True
      self.referencedTextureName = stream.read_string()
      self.name = self.referencedTextureName
    else:
      self.isReference = False
      self.includedTexture = TextureEntry(stream, False, version)
      self.name = self.includedTexture.name

  def write_to(self, stream):
    contentsBytes = _BytesIO()
    contentsBytes.write_int(2142336875)
    contentsBytes.write_int(self.version)
    contentsBytes.write_int(len(self.subAtlases))
    for subAtlas in self.subAtlases:
      contentsBytes.write_string(subAtlas['name'])
      contentsBytes.write_int(subAtlas['rect']['x'])
      contentsBytes.write_int(subAtlas['rect']['y'])
      contentsBytes.write_int(subAtlas['rect']['width'])
      contentsBytes.write_int(subAtlas['rect']['height'])
      contentsBytes.write_int(subAtlas['topLeft']['x'])
      contentsBytes.write_int(subAtlas['topLeft']['y'])
      contentsBytes.write_int(subAtlas['originalSize']['x'])
      contentsBytes.write_int(subAtlas['originalSize']['y'])
      contentsBytes.write_single(subAtlas['scaleRatio']['x'])
      contentsBytes.write_single(subAtlas['scaleRatio']['y'])

      if (self.version > 0):
        flags = 1 if subAtlas['isMulti'] else 0
        flags = flags + (2 if subAtlas['isMip'] else 0)
        flags = flags + (4 if subAtlas['isAlpha8'] else 0)
        contentsBytes.write(bytes([flags]))

      if (self.version > 2):
        contentsBytes.write_int(len(subAtlas['hull']))
        for point in subAtlas['hull']:
          contentsBytes.write_int(point['x'])
          contentsBytes.write_int(point['y'])
      
    contentsBytes.write(bytes([221 if self.isReference else 0]))

    if self.isReference:
      contentsBytes.write_string(self.referencedTextureName)
    else:
      self.includedTexture.write_to(contentsBytes)

    buf = contentsBytes.getbuffer()
    stream.write_int(len(buf) - 35)     # Apparently the size is wrong. No one cares.
    stream.write(bytes(buf))

  def _export(self, path):
    # If the user didn't ask for a supported format, then don't export
    if os.path.splitext(path)[1] not in ['.json']:
      return super()._export(path)

    data = {
      'version': self.version, 
      'subAtlases': self.subAtlases,
      'isReference': self.isReference,
      'referencedTextureName': self.referencedTextureName
    }

    with open(path, "w") as json_file:
      json_file.write(json.dumps(data))

    return True

  def extract(self, target, **kwargs):
    path = os.path.join(target, 'manifest')
    os.makedirs(path, exist_ok=True)
    self._export(self._extraction_path(target) + '.atlas.json')

  def _import(self, path):
    # If the user didn't ask for a supported image format, then don't export
    if os.path.splitext(path)[1] not in ['.json']:
      return super()._export(path)

    with open(path, "r") as json_file:
      data = json.load(json_file)
      self.version = data['version']
      self.isReference = data['isReference']
      self.referencedTextureName = data['referencedTextureName']
      self.subAtlases = data['subAtlases']
    return True
  
  def _extraction_path(self, target):
    return os.path.join(target, 'manifest', self.name.split('\\')[-1])


@entry('binkAtlas', b'\xEE')
class BinkAtlasEntry(EntryBase):
  """Represents a Bink atlas.

  Found in manifests of packages with Bink entries, Bink atlases serve
  a somewhat similar purpose as Atlas entries do for Textures. That
  said, bink files don't contain a bunch of imagery packed together
  like a spritesheet would, so the data in a Bink atlas is much simpler --
  it defines a bounding rectangle for the content, and allows for storage
  of a scaling factor to be used, presumably, by the game engine to enlarge
  or shrink the display of the asset.

  Currently does not support import or export (other than .entry)
  """
  def read_from(self, stream, isManifest=False, version=7):
    self.size = stream.read_int()
    self.version = stream.read_int()
    if (self.version < 1):
      raise Exception('Invalid Bink Atlas version')
    self.name = stream.read_string()
    self.width = stream.read_int()
    self.height = stream.read_int()
    if (self.version > 1):
      self.originalSize = {
        'x': stream.read_int(),
        'y': stream.read_int()
      }
      if (self.version > 2):
        self.scaling = stream.read_single()

  def write_to(self, stream):
    stream.write_int(self.size)
    stream.write_int(self.version)
    stream.write_string(self.name)
    stream.write_int(self.width)
    stream.write_int(self.height)
    if (self.version > 1):
      stream.write_int(self.originalSize['x'])
      stream.write_int(self.originalSize['y'])
      if (self.version > 2):
        stream.write_single(self.scaling)

  def extract(self, target, **kwargs):
    path = os.path.join(target, 'manifest')
    os.makedirs(path, exist_ok=True)
    super().extract(target, **kwargs)

  def _extraction_path(self, target):
    return os.path.join(target, 'manifest', self.name.split('\\')[-1])


@entry('include', b'\xCC')
class IncludePackageEntry(EntryBase):
  """Represents a package include reference.

  These entries are simply references to other packages. When
  read by the game engine, the named packages are also loaded.

  Currently does not support import or export (other than .entry).
  """
  def read_from(self, stream, isManifest=False, version=7):
    self.name = stream.read_string()
  
  def write_to(self, stream):
    stream.write_string(self.name)

  def extract(self, target, **kwargs):
    if 'includes' in kwargs:
      kwargs['includes'].append(self.name)

@entry('spine', b'\xF0')
class SpineEntry(EntryBase):
  """Represents a spine asset.

  Spine is a 2D skeletal animation framework for video games.
  The data in a spine entry consist of an identifier, the spine
  data itself, and a texture atlas (using the libgdx format, not
  the format used by other atlases).

  Currently does not support import or export (other than .entry).
  """
  def read_from(self, stream, isManifest=False, version=7):
    self.version = ord(stream.read(1))
    self.name = stream.read_string()
    self.spineAtlas = stream.read_big_string()
    self.spineData = stream.read_big_string()

  def write_to(self, stream):
    stream.write(bytes([self.version]))
    stream.write_string(self.name)
    stream.write_big_string(self.spineAtlas)
    stream.write_big_string(self.spineData)

  def extract(self, target, **kwargs):
    path = os.path.join(target, 'spines')
    os.makedirs(path, exist_ok=True)
    super().extract(target, **kwargs)

  def _extraction_path(self, target):
    return os.path.join(target, 'spines', self.name.split('\\')[-1])


