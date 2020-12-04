from abc import ABC, abstractmethod
from .utils import requires
import os

try: import lz4.block
except ImportError: pass
try: import lzf
except ImportError: pass

_chunk_processors = {}              # Stores a mapping of possible chunk processors by byte code
_chunk_processors_by_name = {}      # Stores a mapping of possible chunk processors by name

def chunkprocessor(typeName, typeCode):
  """Decorates a subclass of ChunkProcessorBase to register its name and byte code.

  This makes the class discoverable by the chunk reading code to find the 
  correct subclass to read and (possibly) decompress chunks of data from
  the stream.
  """
  def decorate_entry(cls):
    def class_wrapper(*args):
      return cls(*args)
    if typeCode:
      _chunk_processors[typeCode] = class_wrapper
      _chunk_processors_by_name[typeName] = class_wrapper
      class_wrapper._typeCode = typeCode
      cls._typeCode = typeCode
    return class_wrapper
  return decorate_entry

def validate_compressor_name(name):
  return name in _chunk_processors_by_name

def get_chunkprocessor_by_name(name):
  return _chunk_processors_by_name[name]()

def get_chunkprocessor(b):
  return _chunk_processors[b]()

#region Chunk Processing
class _ChunkProcessorBase(ABC):
  """Base class for a chunk processor.
    
  What is a chunk processor? Well, in this case, it is an object which is responsible for
  reading chunks of data from and writing chunks of data to packages. SuperGiant's packages
  consist of a four-byte header followed by a series of chunks containing asset data.
  The various subclasses of this class handle the variety of formats the chunks themselves
  can be stored as.
  """
  @abstractmethod
  def read_chunk(self, stream, chunk_size):
    """Reads the next chunk of data from the stream.

    This function is responsible for reading the next chunk of data, performing any needed
    processing on the data (such as decompression), and ensuring the output is of the
    indicated size.
    """
    pass

  @abstractmethod
  def write_chunk(self, stream, chunk):
    """Writes a chunk of data to the stream.

    This function is responsible for performing any needed processing on the chunk
    (such as compression), and writing the processed data to the stream.
    """
    pass

  @abstractmethod
  def skip_chunk(self, stream, chunk_size):
    """Skips past the next chunk of data from the stream.

    This function should act similar to read_chunk in determining how much data
    is in the next chunk, but should skip past it in the stream instead of
    reading it. This function is used to faciliate random access IO functions
    like seek().
    """
    pass


@chunkprocessor('uncompressed', b'\x00')
class _UncompressedChunkProcessor(_ChunkProcessorBase):
  """Chunk processor for uncompressed packages."""
  def read_chunk(self, stream, chunk_size):
    """Reads the next chunk of data from the stream.

    In this case, the data is assumed uncompressed, so this just reads unmodified data
    from the stream.
    """
    return stream.read(chunk_size)

  def write_chunk(self, stream, chunk):
    """Writes a chunk of data to the stream.

    In this case, the data is assumed uncompressed, so this just writes unmodified data
    to the stream.
    """
    stream.write(chunk)

  def skip_chunk(self, stream, chunk_size):
    """Skips past the next chunk of data in the stream.

    In this case, the data is assumed to be uncompressed, so this just skips bytes
    equal to the size of the chunk.
    """
    stream.seek(chunk_size, os.SEEK_CUR)


class _CompressedChunkProcessor(_ChunkProcessorBase):
  """Chunk processor for compressed packages.
  
  Packages generally consist of compressed chunks. The purpose of this class is to
  facilitate reading and writing package data one chunk at a time.
  """
  def read_chunk(self, stream, chunk_size):
    """Reads the next chunk of data from the stream.

    In this case, the data is likely compressed, so this will read the compressed data
    from the stream, then call decompress to decompress it if it is indeed compressed. 
    The decompress function should return a chunk of the correct size by padding it with 0-bytes.
    """
    if stream.read(1) != 0:
      # The chunk is compressed. Read it, then decompress it.
      compSize = stream.read_int()
      compressedData = stream.read(compSize)
      return self.decompress(compressedData, chunk_size)
    else:
      # The chunk is not compressed. Just read it.
      return stream.read(chunk_size)

  def write_chunk(self, stream, chunk):
    """Writes a chunk of data to the stream.

    In this case, the data is assumed compressed, so this will compress the given chunk
    of data, then write the compressed data to the stream.
    """
    compressedData = self.compress(chunk)
    stream.write(bytes([1]))                # The "1" indicates it's compressed
    stream.write_int(len(compressedData))   # Then write the length of the compressed data
    stream.write(compressedData)            # Then write the compressed data itself

  def skip_chunk(self, stream, chunk_size):
    """Skips past the next chunk of data in the stream.

    Compressed chunks encode the size of the compressed data as part of the chunk.
    Therefore, this function will read in that size, but then just seek past the
    actual chunk data.
    """
    if stream.read(1) != 0:
      # The chunk is compressed. Read the size, then seek past it.
      compSize = stream.read_int()
      stream.seek(compSize, os.SEEK_CUR)
    else:
      # The chunk is not compressed. Just seek past it.
      stream.seek(chunk_size, os.SEEK_CUR)

  @abstractmethod
  def compress(self, chunk):
    """Compresses the given chunk."""
    pass

  @abstractmethod
  def decompress(self, chunk, chunk_size):
    """Decompresses the given chunk, zero-filling to chunk_size."""
    pass

@requires('lz4')
@chunkprocessor('lz4', b'\x20')
class _Lz4ChunkProcessor(_CompressedChunkProcessor):
  """Chunk processor for LZ4-compressed packages.

  Packages in Hades are compressed using LZ4. The 'lz4' module
  is required to use this chunk processor.
  """
  def compress(self, chunk):
    """Compresses a block of data using LZ4 compression."""
    return lz4.block.compress(chunk, mode='high_compression', store_size=False)

  def decompress(self, chunk, chunk_size):
    """Decompresses an LZ4-compressed block of data, zero-filling to chunk_size."""
    return lz4.block.decompress(chunk, uncompressed_size=chunk_size).ljust(chunk_size, b'\x00')

@requires('lzf')
@chunkprocessor('lzf', b'\x40')
class _LzfChunkProcessor(_CompressedChunkProcessor):
  """Chunk processor for LZF-compressed packages.

  Packages in Transistor are compressed using LZF. The 'lzf' module
  is required to use this chunk processor.
  """
  def compress(self, chunk):
    """Compresses a block of data using LZF compression."""
    return lzf.compress(chunk)

  def decompress(self, chunk, chunk_size):
    """Decompresses an LZF-compressed block of data, zero-filling to chunk_size."""
    return lzf.decompress(chunk, chunk_size).ljust(chunk_size, b'\x00')
#endregion


@chunkprocessor('lzx', b'\x60')
class _LzxChunkProcessor(_CompressedChunkProcessor):
  """Chunk processor for LZX-compressed data.

  LZX is not actually used to compress packages, but can be used to compress
  XNB data. This class is provided as a consistent interface for that compression.

  This mode of compression is not yet implemented.
  """
  def compress(self, chunk):
    """Compresses a block of data using LZX compression."""
    raise NotImplementedError('LZX compression is not yet implemented')

  def decompress(self, chunk, chunk_size):
    """Decompresses an LZX-compressed block of data."""
    raise NotImplementedError('LZX decompression is not yet implemented')