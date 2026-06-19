import struct
import math
from PIL import Image

class ImageCoder:
    """
    Encodes and decodes raw binary data into PNG images.
    Roblox accepts up to 20MB files, max 8000x8000.
    1 Pixel = 3 Bytes (RGB) or 4 Bytes (RGBA).
    We use RGB (3 Bytes per pixel).
    """

    @staticmethod
    def encode(data: bytes, output_path: str):
        """
        Converts binary data into a PNG image.
        First 4 bytes of data are used to store the exact length of the original data.
        """
        data_len = len(data)
        # Prefix the data with its length (4 bytes, unsigned int, big-endian)
        length_prefix = struct.pack('>I', data_len)
        full_data = length_prefix + data

        # Calculate required pixels (3 bytes per pixel for RGB)
        total_bytes = len(full_data)
        total_pixels = math.ceil(total_bytes / 3)

        # Calculate image dimensions (make it roughly square)
        width = math.ceil(math.sqrt(total_pixels))
        height = math.ceil(total_pixels / width)

        # Pad data so it perfectly fits the RGB array
        padding_needed = (width * height * 3) - total_bytes
        padded_data = full_data + b'\x00' * padding_needed

        # Create image
        img = Image.frombytes('RGB', (width, height), padded_data)
        
        # Save as PNG
        img.save(output_path, format='PNG')
        return output_path

    @staticmethod
    def decode(image_path_or_bytes) -> bytes:
        """
        Extracts binary data from a PNG image created by encode().
        Accepts a file path or a bytes-like object of the image file.
        """
        import io
        if isinstance(image_path_or_bytes, bytes):
            img = Image.open(io.BytesIO(image_path_or_bytes))
        else:
            img = Image.open(image_path_or_bytes)

        # Ensure RGB mode
        if img.mode != 'RGB':
            img = img.convert('RGB')

        padded_data = img.tobytes()

        # Read the first 4 bytes to get the original data length
        data_len = struct.unpack('>I', padded_data[:4])[0]

        # Extract the original data
        original_data = padded_data[4:4+data_len]
        return original_data
