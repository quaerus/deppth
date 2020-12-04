import io
import os
import fnmatch

from .compression import get_chunkprocessor, get_chunkprocessor_by_name, validate_compressor_name
from .utils import IOExtensionMixin as _IOExtensionMixin, FileIO as _FileIO, BytesIO as _BytesIO
from .entries import get_entry, import_entry

#region Constants
CHUNK_SIZE = 0x2000000              # The size of uncompressed chunks in packages

PACKAGE_VERSION_HADES = 7
PACKAGE_VERSION_TRANSISTOR = 5
PACKAGE_VERSION_PYRE = 5
PACKAGE_VERSIONS = [PACKAGE_VERSION_HADES, PACKAGE_VERSION_PYRE, PACKAGE_VERSION_TRANSISTOR]

ENTRY_CODE_END_OF_CHUNK = b'\xBE'
ENTRY_CODE_END_OF_FILE = b'\xFF'
#endregion

class PackageIO(io.IOBase, _IOExtensionMixin):
  """Base class for reading to and writing from SuperGiant Games asset packages.
  
  You almost never should instantiate this directly nor any subclass, but
  instead should use the open_package function, which will return the correct
  subclass.

  This class implements the IOBase interface, so typical IO patterns should
  readily be familiar. As such, documentation will be omitted for members
  that behave like any standard IO object.
  """

  #region Basic Functionality
  def __init__(self, name, mode='r', closefd=True, opener=None, compressor='uncompressed', version=PACKAGE_VERSION_HADES, is_manifest=False):
    """Creates an instance of PackageIO, opening a stream to read the package.
    
    The name, mode, closefd, and opener properties match those from io.open.

    The compressor property indicates the type of compression used in the package.
    Because this class cannot read or write data, the user must specify. The possible
    values are 'uncompressed', 'lz4' and 'lzf'. LZ4 and LZF compression require the
    lz4 and lzf modules, respectively.

    The version property indicates the version number of the package. The PACKAGE_VERSION_*
    constants provide the correct values for this property
    """
    if not mode in ['r', 'w', 'x']:
      raise ValueError(f'invalid mode: {mode}. Only modes r, w, and x are supported')
    self.mode = mode + 'b'
    self.raw = _FileIO(name, mode, closefd, opener)
    self.virtual_pos = [0, 0]   # Chunk num and position within chunk
    self.chunklocs = [4]
    self.compressor = compressor
    self.chunkprocessor = None
    self.version = version
    self.is_manifest = is_manifest

  def close(self):
    if self.raw is not None and not self.closed:
      try:
        self.flush()
      finally:
        self.raw.close()

  @property
  def closed(self):
    return self.raw.closed

  def fileno(self):
    return self.raw.fileno()

  def flush(self):
    if self.closed:
      raise ValueError("flush on closed file")
    self.raw.flush()

  def _get_chunkprocessor(self):
    if not self.chunkprocessor:
      if len(self.compressor) == 1:
        self.chunkprocessor = get_chunkprocessor(self.compressor)
      else:
        self.chunkprocessor = get_chunkprocessor_by_name(self.compressor)
    return self.chunkprocessor
            
  def isatty(self):
    return self.raw.fileno()

  def is_eof(self):
    """Returns whether the underlying file stream is at EOF.

    This is not necessarily whether the reader or writer itself is at EOF."""
    return self.raw.is_eof()
  #endregion

  #region Read Access
  def read(self, size):
    """Reads the next specified bytes of data from the package.
    
    This will just return raw bytes from the underlying file stream without
    decompression.
    """
    return self.raw.read(size)

  def readable(self):
    return self.raw.readable()

  def read_entry(self):
    """Reads the next entry from the package.

    This function is meant to be called many times in succession to
    read the entire contents of the package, until the end is reached,
    at which point None is returned.

    This function assumes the stream is positioned to read the next
    entry. Adjusting the position of the stream manually will likely
    make this function unusable. You have been warned.

    The object returned will either be None or an instance of a subclass
    of EntryBase.
    """
    raise NotImplementedError("Cannot read entries from PackageIOBase")
  #endregion

  #region Write Access
  def write(self, b):
    """Writes the specified bytes to the package file.
    
    This function is provided in fulfillment of the IOBase interface,
    and is implemented for convenience within this module. Consumers
    of this module should almost certainly not call this function.
    """
    raise NotImplementedError()

  def writable(self):
    return self.raw.writable()
  #endregion

  #region Random Access
  def seek(self, pos, whence=0):
    """Change stream position.

    Functions similar to IOBase.seek, but currently only os.SEEK_SET is
    supported for whence.

    Returns the stream position, which is a virtual position in a hypothetical
    uncompressed version of the stream.
    """
    if not self.seekable():
      return OSError("stream not seekable")

    if whence != os.SEEK_SET:
      raise NotImplementedError("Only os.SEEK_SET is supported for now")
    
    old_virtual_pos = self.virtual_pos.copy()

    # Figure out which chunk to go to.
    new_virtual_pos = [pos // CHUNK_SIZE, pos % CHUNK_SIZE]

    # If we need to move to a new chunk, do that.
    if new_virtual_pos[0] != self.virtual_pos[0]:
      self._seek_chunk(new_virtual_pos[0])

    # Set the virtual position within this chunk to the new one.
    # The reason why it's virtual is we aren't actually reading the
    # compressed data to navigate within a decompressed chunk.
    self.virtual_pos[1] = new_virtual_pos[1]

    # Execute "after seek" code to handle potentially stale buffers.
    self._after_seek(old_virtual_pos, new_virtual_pos)

    # Return the new stream position.
    return self.tell()

  def tell(self):
    """Returns the stream position.
    
    For this stream, tell functions a bit differently due to the way the
    data is being read and decompressed on the fly. The stream position
    is more of a "virtual" concept. This function will return what the
    stream position *would* be if the contents were fully decompressed.

    The underlying FileIO object's tell function can be used to return
    the position of the stream accessing the compressed data.
    """
    return self.virtual_pos[0]*CHUNK_SIZE + self.virtual_pos[1]

  def truncate(self, pos=None):
    """This action is not supported at this time, since it's not clear how it should work."""
    raise NotImplementedError("truncate for PackageIO streams is not supported")
      
  def _skip_chunk(self):
    """Skips the next chunk in the stream. Returns whether there actually was a chunk."""
    # If there's no data left in the file, there's no more chunks to load.
    if self.raw.is_eof():
        return False

    # The first chunk actually includes the header, so remove it if we're at the start of the file.
    pos = self.raw.tell()   # This should be 4 exactly for the first chunk
    chunksize = CHUNK_SIZE - pos if pos <= 4 else CHUNK_SIZE

    # Skip the next chunk from the file using the correct chunk processor
    self._get_chunkprocessor().skip_chunk(self.raw, chunksize)
    self.virtual_pos[0] += 1
    
    # If we haven't already, add a chunk marker indicating where the next chunk begins
    if self.virtual_pos[0] >= len(self.chunklocs):
      self.chunklocs.append(self.raw.tell())

    return True

  def _seek_chunk(self, n):
    """Seeks to the start of the chunk n (0-indexed) in the package."""
    if n < len(self.chunklocs):
        # We already know where this is! Just seek to that spot.
        self.raw.seek(self.chunklocs[n], os.SEEK_SET)
        self.virtual_pos[0] = n
    else:
        # We don't know where this is! Go to the start of the last chunk we know
        # about and skip chunks until we get there!
        self.raw.seek(self.chunklocs[-1], os.SEEK_SET)
        self.virtual_pos[0] = len(self.chunklocs) - 1
        while self.virtual_pos[0] < n:
            self._skip_chunk()

  def _after_seek(self, old_pos, new_pos):
    """Executed immediately after seek is called. Use this to, e.g., handle stale buffers."""
    pass

  #endregion


class PackageReader(PackageIO):
  #region Constructor
  def __init__(self, name, closefd=True, opener=None, is_manifest=False):
    super().__init__(name, 'r', closefd, opener, is_manifest=is_manifest)

    # Initialize the read buffer
    self._reset_read_buf()

    # Read the header, which should set the compressor and version correctly
    self._read_header()
  #endregion

  #region Basic Functionality Overrides
  def is_eof(self):
    # if the file is eof and there's nothing left in the read buffer, we're EOF
    return self.raw.is_eof() and self._read_pos >= len(self._read_buf)
  #endregion

  #region Read Access
  def read(self, size):
    """Reads the next specified bytes of data from the package.
    
    This function differs from standard IO implementations in that
    the size parameter is (currently) mandatory, and None is not
    a legal value.

    Because packages are usually stored compressed, and this class
    will invoke decompression on chunks of data as needed, it's
    worth clarifying that this function will return the specified
    number of bytes of uncompressed data. The actual amount of data
    read could differ for a number of different reasons, not the least
    of which being the fact that this stream utilizes a buffer.
    """

    # How many bytes are left in the current chunk?
    num_bytes_to_read = len(self._read_buf) - self._read_pos

    # If we can satisfy the read just with the current chunk, great!
    if size <= num_bytes_to_read:
      return self._read_from_buffer(size)

    # Otherwise, we'll need to load at least one more chunk 
    # to load the requested amount of bytes
    data = [self._read_buf[self._read_pos:]]
    num_bytes_read = num_bytes_to_read

    # Load chunks of additional data until we have enough bytes to satisfy the request
    while True:
      if self._read_chunk() is not None:
        if len(self._read_buf) < size - num_bytes_read:
          # Read in this entire chunk, and keep going
          num_bytes_read += len(self._read_buf)
          data.append(self._read_buf)
        else:
          # Read in enough data to satisfy the request, and stop
          data.append(self._read_from_buffer(size - num_bytes_read))
          break
      else:
        break   # Out of data to load, so this is it!

    return b"".join(data)

  def read_entry(self):
    """Reads the next entry from the package.

    This function is meant to be called many times in succession to
    read the entire contents of the package, until the end is reached,
    at which point None is returned.

    This function assumes the stream is positioned to read the next
    entry. Adjusting the position of the stream manually will likely
    make this function unusable. You have been warned.

    The object returned will either be None or an instance of a subclass
    of EntryBase.
    """
    if self.is_eof():
      return None

    # The first byte tells us what type of entry this is, or signals a special case
    entry_type = self.read(1)

    if entry_type == ENTRY_CODE_END_OF_CHUNK:
      # Handle end of chunk and try reading again
      self._end_of_chunk()
      return self.read_entry()    
    elif entry_type == ENTRY_CODE_END_OF_FILE:
      # Nothing further to do, return None
      return None
    else:
      # Instantiate correct entry type and use this stream to read its data
      return get_entry(entry_type, self, self.is_manifest)

  def __next__(self):
    """Reads the next entry from the package.

    Normally, iterating through a file reads a line at a time.
    This override is provided to make for loops intuitive.
    """
    entry = self.read_entry()
    if not entry:
        raise StopIteration
    return entry
  
  def _end_of_chunk(self):
    """Code executed at end of chunk."""
    # Clear the read buffer, we're done with it
    self._reset_read_buf()    

    # Adjust virtual_pos to start of next chunk
    self.virtual_pos[0] += 1    
    self.virtual_pos[1] = 0

    # If we haven't already, add a chunk marker indicating where the next chunk begins
    if self.virtual_pos[0] >= len(self.chunklocs):
        self.chunklocs.append(self.raw.tell())

  def _read_header(self):
    # If we're not at the start of the file, why are we reading a header?
    if (self.raw.tell() != 0):
        raise ValueError("attempted to read header while not at start of file")

    # The first byte of the header indicates the compression method of the package, if any
    self.compressor = self.raw.read(1)
    self._get_chunkprocessor()

    # The next two bytes are zeroes and don't matter
    self.raw.read(2)

    # The fourth (last) byte of the header indicates the package version, which should be
    # 5 for Transistor/Pyte and 7 for Hades
    self.version = ord(self.raw.read(1))

    # Update the virtual position to indicate we're at position 4
    self.virtual_pos[1] = 4

  def _reset_read_buf(self):
    # Resets the state of the read buffer, clearing it and moving the position to 0
    self._read_buf = b""
    self._read_pos = 0

  def _read_chunk(self):
    # If there's no data left in the file, we can't load another chunk, obviously
    if self.raw.is_eof():
      return None

    # The first chunk actually includes the header, so remove it if we're at the start of the file
    pos = self.raw.tell()   # This should be 4 exactly for the first chunk
    chunksize = CHUNK_SIZE - pos if pos <= 4 else CHUNK_SIZE

    # Read the next chunk from the file using the correct chunk processor
    self._read_buf = self._get_chunkprocessor().read_chunk(self.raw, chunksize)
    self._read_pos = 0
    self.virtual_pos[1] = 0

    return self._read_buf
  
  def _read_from_buffer(self, amt):
    # Advance position by amt and read that many bytes
    data = self._read_buf[self._read_pos:self._read_pos+amt]
    self._read_pos += amt
    self.virtual_pos[1] += amt
    return data
  #endregion

  #region Random Access
  def _after_seek(self, old_pos, new_pos):
    """Executed after seek is called. We use this to wipe the buffer if it's stale."""
    if old_pos[0] != new_pos[0]:
      # Buffer is now stale. Wipe it.
      self._reset_read_buf()

      chunknum = new_pos[0]
      chunkpos = new_pos[1]
      
      # If this is the first chunk, we need to account for the header.
      if chunknum == 0:
        if chunkpos <= 4:
          # If we're moving to the header, we don't need to read a chunk, or do
          # anything else.
          return
        else:
          # We need to move the position within the buffer back by 4 because the
          # header is not going to be loaded into the buffer.
          chunkpos -= 4

      # If we're seeking to a non-zero position within this chunk,
      # we need to load that chunk to have something to actually seek.
      if chunkpos > 0:
        self._read_chunk()
        self._read_pos = chunkpos
    else:
      # Buffer is still okay. Just update the position within it.
      self._read_pos = new_pos[1]
  #endregion

  #region Complete Loading
  def load(self):
    # Move to the start of the file (past the header)
    self.seek(4, os.SEEK_SET)
    entries = {}

    for entry in self:
      entries[entry.name] = entry

    return entries

  @staticmethod
  def load_package(name, is_manifest=False):
    with PackageReader(name, is_manifest=is_manifest) as p:
      return p.load()
  #endregion


class PackageWriter(PackageIO):
  #region Constructor
  def __init__(self, name, closefd=True, opener=None, compressor='uncompressed', version=PACKAGE_VERSION_HADES, is_manifest=False):
    super().__init__(name, 'w', closefd, opener, compressor, version, is_manifest)

    # Initialize the write buffer
    self._reset_write_buf()

    # Write the header (based on compressor and version)
    self._write_header()
  #endregion

  #region Basic Functionality Overrides
  def close(self):
    self._write_chunk(closing=True)
    super().close()
  #endregion

  #region Write Access
  def write(self, b):
    # If the bytes given won't fit in a chunk, we can't write it at all
    if len(b) > CHUNK_SIZE:
      raise OSError(f'cannot write more than {CHUNK_SIZE} bytes at once')

    # Check space in this chunk
    availspace = len(self._write_buf.getvalue()) - self._write_buf.tell() - 1     # Why -1? Need room for end chunk byte
    if len(b) > availspace:
      # No more room in the chunk, write the buffer out, which will allocate a new one
      self._write_chunk()

    # Write the bytes to the current chunk (may or may not have just been made)
    self._write_buf.write(b) 
    self.virtual_pos[1] += len(b)

  def _write_header(self):
    # If we're not at the start of the file, why are we writing a header?
    if (self.raw.tell() != 0):
      raise ValueError("attempted to write header while not at start of file")

    # The first byte of the header indicates the compression method of the package, if any
    self.raw.write(self._get_chunkprocessor()._typeCode)

    # The next two bytes are zeroes and don't matter
    self.raw.write(bytes([0, 0]))

    # The fourth (last) byte of the header indicates the package version
    self.raw.write(bytes([self.version]))

    # Update the virtual position to indicate we're at position 4
    self.virtual_pos[1] = 4

  def write_entry(self, entry):
    # Write the entry's bytes to a temporary stream to figure out what the bytes are
    entrystream = _BytesIO()
    entrystream.write(entry.typeCode)
    entry.write_to(entrystream)

    # Write the entry's bytes to the "actual" stream
    self.write(entrystream.getvalue())

  def _write_chunk(self, closing=False):
    # Write end-of-chunk or end-of-file
    endbyte = ENTRY_CODE_END_OF_FILE if closing else ENTRY_CODE_END_OF_CHUNK
    self._write_buf.write(endbyte)

    # If we're writing compressed, we need to write the whole chunk. But if not, we can strip off the extra null bytes.
    chunk = ""
    if self.compressor != 'uncompressed':
      chunk = self._write_buf.getvalue()
    else:
      chunk = self._write_buf.getvalue()[:self._write_buf.tell()]

    # Write the current chunk to the file
    self._get_chunkprocessor().write_chunk(self.raw, chunk)

    # Reset the write buffer to a blank state
    self._reset_write_buf()

    # Set the virtual position (chunk, pos_in_chunk) of the stream
    self.virtual_pos[0] += 1
    self.virtual_pos[1] = 0

  def _reset_write_buf(self):
    chunksize = CHUNK_SIZE - 4 if self.virtual_pos[0] == 0 else CHUNK_SIZE
    self._write_buf = _BytesIO(bytes(chunksize))
  #endregion

  #region Random Access (disabled)
  def seekable(self):
    return False
  #endregion


class PackageWithManifestReader(PackageReader):
  def __init__(self, name, closefd=True, opener=None):
    super().__init__(f'{name}', closefd, opener)
    if os.path.exists(f'{name}_manifest'):
      self.manifest = PackageReader.load_package(f'{name}_manifest', True)
    else:
      self.manifest = None

  def read_entry(self):
    entry = super().read_entry()
    if entry is None:
      return None

    # Can we find a matching manifest entry?
    if self.manifest is not None and entry.name in self.manifest:
      entry.manifest_entry = self.manifest[entry.name]

    return entry

class PackageWithManifestWriter(PackageWriter):
  def __init__(self, name, closefd=True, opener=None, compressor='uncompressed', version=PACKAGE_VERSION_HADES):
    super().__init__(name, closefd, opener, compressor, version)
    manifest_name = f'{name}_manifest'
    self.manifest = PackageWriter(manifest_name, closefd, opener, version=version, is_manifest=True)

  def write_entry_with_manifest(self, entry):
    self.write_entry(entry)
    if self.manifest is not None and hasattr(entry, 'manifest_entry'):
      self.manifest.write_entry(entry.manifest_entry)

  def close(self):
    super().close()
    self.manifest.close()

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

def load_package(name):
  """Loads the entire contents of the package given by name and returns an array of entries."""
  is_manifest = name.endswith('_manifest')
  return PackageReader.load_package(name, is_manifest)

def open_package(name, mode, closefd=True, opener=None, compressor='lz4', version=PACKAGE_VERSION_HADES):
  """Opens the package with base filename given by name. 
  
  mode - Valid modes are 'r', 'w', 'rm', and 'wm'. R for Read, W for Write, M for include Manifest.
  closefd, opener - Similar to the same parameters on os.open

  These parameters are only used for writing; if reading the values are inferred from the package data:
  compressor - Compression to use on the package. Valid values are 'uncompressed', 'lz4', and 'lzf'
  version - Should be a PACKAGE_VERSION_* constant depending on the game (7 if Hades, 5 otherwise)
  """
  if not validate_compressor_name(compressor):
    raise ValueError(f'Invalid compressor: {compressor}')

  if not version in PACKAGE_VERSIONS:
    raise ValueError(f'Invalid version: {version}')

  if mode == 'r':
    return PackageReader(name, closefd=closefd, opener=opener)
  elif mode == 'w':
    return PackageWriter(name, closefd=closefd, opener=opener, compressor=compressor, version=version)
  elif mode == 'rm':
    return PackageWithManifestReader(name, closefd=closefd, opener=opener)
  elif mode == 'wm':
    return PackageWithManifestWriter(name, closefd=closefd, opener=opener, compressor=compressor, version=version)
  else:
    raise ValueError(f'Invalid mode: {mode}')