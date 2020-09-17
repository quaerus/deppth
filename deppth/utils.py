import sys
import os
import struct
import io

def requires(moduleName):
    """Marks a function as requiring an optional module dependency."""
    def decorate_function(fn):
        def wrapper(*args, **kwargs):
            if moduleName in sys.modules:
                result = fn(*args, **kwargs)
                return result
            else:
                raise ImportError(f'{fn.__name__}: This action requires the {moduleName} module.')
        return wrapper
    return decorate_function

class IOExtensionMixin():
  """Provides various helper functions to make reading packages from streams easier."""
  def is_eof(self):
    """Returns whether the stream is at EOF."""
    s = self.read(1)
    if (s != b''):
      self.seek(-1, os.SEEK_CUR)
    return s == b''
  
  def read_string(self):
    """Reads an encoded string with max length 255."""
    length = int.from_bytes(self.read(1), byteorder='big')
    stringBytes = self.read(length)
    return stringBytes.decode('ascii')

  def write_string(self, s):
    """Writes an encoded string with max length 255."""
    length = len(s)
    if length > 255:
        raise Exception(f'String exceeds maximum length for packing: {length}')
    stringBytes = s.encode('ascii')
    self.write(bytes([length]))
    self.write(stringBytes)

  def read_big_string(self):
    """Reads an encoded string with max length 2^32 - 1."""
    length = int.from_bytes(self.read(4), byteorder='big', signed=True)
    stringBytes = self.read(length)
    return stringBytes.decode('utf-8')

  def write_big_string(self, s):
    """Writes an encoded string with max length 2^32 - 1."""
    length = len(s)
    stringBytes = s.encode('utf-8')
    self.write(length.to_bytes(4, 'big', signed=True))
    self.write(stringBytes)

  def read_int(self, byteorder='big', signed=True):
    """Reads a four-byte integer."""
    return int.from_bytes(self.read(4), byteorder=byteorder, signed=signed)

  def write_int(self, n, byteorder='big', signed=True):
    """Writes a four-byte integer."""
    intBytes = n.to_bytes(4, byteorder, signed=signed)
    self.write(intBytes)

  def read_single(self):
    """Reads a single-floating-point number."""
    singleBytes = self.read(4)
    return struct.unpack('>f', singleBytes)[0]

  def write_single(self, s):
    """Writes a single-floating-point number."""
    singleBytes = struct.pack('>f', s)
    self.write(singleBytes)

  def read_7bit_encoded_int(self):
    """Reads a 7-bit-encoded number.
    
    7-bit-encoded numbers are encoded with the following algorithm:

    - If the number fits in 7 bits (< 128), write this byte and stop
    - Otherwise, write the least significant 7 bits of the number,
      and set the most significant bit of the byte to 1, then shift
      the number to remove those bits and repeat.

    The advantage of this encoding is it supports numbers of any size.
    """
    result = 0
    index = -1
    while True:
      index += 1
      byte_value = ord(self.read(1))
      result |= (byte_value & 0x7f) << (7 * index)
      if byte_value & 0x80 == 0:
        break
    return result

  def write_7bit_encoded_int(self, n):
    """Writes a 7-bit-encoded number.
    
    See read_7bit_encoded_int for more information on what a 7-bit-encoded numbers.
    """
    value = abs(n)
    while value >= 0x80:
      self.write(bytes([(value | 0x80) & 0xFF]))
      value >>= 7
    self.write(bytes([value & 0xFF]))

  def read_string_7b(self):
    """Reads a string prefixed with length as 7-bit-encoded data.
    
    See read_7bit_encoded_int for more information on what a 7-bit-encoded numbers.
    """
    length = self.read_7bit_encoded_int()
    stringBytes = self.read(length)
    return stringBytes.decode('ascii')

  def write_string_7b(self, s):
    """Writes a string prefixed with length as 7-bit-encoded data.
    
    See read_7bit_encoded_int for more information on what a 7-bit-encoded numbers.
    """
    length = len(s)
    stringBytes = s.encode('ascii')
    self.write_7bit_encoded_int(length)
    self.write(stringBytes)

class BytesIO(io.BytesIO, IOExtensionMixin):
    """An enhanced version of BytesIO that includes additional functions."""
    pass


class FileIO(io.FileIO, IOExtensionMixin):
    """An enhanced version of FileIO that includes additonal functions."""
    pass