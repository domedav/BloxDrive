import struct
import math
import numpy as np
from PIL import Image

class ImageCoder:
    """
    Encodes and decodes raw binary data into PNG images using 2-bit LSB steganography.
    Generates an organic-looking randomized gradient cover image to bypass moderation AI.
    1 Byte of data is spread across 4 color channels (2 bits each).
    """

    @staticmethod
    def _generate_cover(width, height):
        x = np.linspace(0, 255, width, dtype=np.float32)
        y = np.linspace(0, 255, height, dtype=np.float32)
        xv, yv = np.meshgrid(x, y)
        
        import random
        r_base = random.randint(0, 255)
        g_base = random.randint(0, 255)
        b_base = random.randint(0, 255)
        
        r = (xv + r_base) % 255
        g = (yv + g_base) % 255
        b = ((xv + yv) / 2 + b_base) % 255
        
        cover = np.stack([r, g, b], axis=2).astype(np.uint8)
        # Clear the lowest 2 bits (mask with 0xFC = 11111100)
        cover &= 0xFC
        return cover

    @staticmethod
    def encode(data: bytes, output_path: str):
        data_len = len(data)
        # Prefix the data with its length (4 bytes, unsigned int, big-endian)
        full_data = struct.pack('>I', data_len) + data
        
        arr = np.frombuffer(full_data, dtype=np.uint8)
        
        # Split each byte into 4 pieces of 2 bits
        p1 = (arr >> 6) & 0x03
        p2 = (arr >> 4) & 0x03
        p3 = (arr >> 2) & 0x03
        p4 = arr & 0x03
        
        pieces = np.column_stack((p1, p2, p3, p4)).flatten()
        
        total_channels = len(pieces)
        total_pixels = math.ceil(total_channels / 3)
        
        width = math.ceil(math.sqrt(total_pixels))
        height = math.ceil(total_pixels / width)
        
        cover = ImageCoder._generate_cover(width, height)
        cover_flat = cover.flatten()
        
        # Embed the data into the lowest 2 bits
        cover_flat[:len(pieces)] |= pieces
        
        img_arr = cover_flat.reshape((height, width, 3))
        img = Image.fromarray(img_arr, 'RGB')
        img.save(output_path, format='PNG')
        return output_path

    @staticmethod
    def decode(image_path_or_bytes) -> bytes:
        import io
        if isinstance(image_path_or_bytes, bytes):
            img = Image.open(io.BytesIO(image_path_or_bytes))
        else:
            img = Image.open(image_path_or_bytes)
            
        if img.mode != 'RGB':
            img = img.convert('RGB')
            
        flat_arr = np.array(img, dtype=np.uint8).flatten()
        
        # Extract the lowest 2 bits
        pieces = flat_arr & 0x03
        
        valid_len = (len(pieces) // 4) * 4
        pieces = pieces[:valid_len]
        
        p1 = pieces[0::4]
        p2 = pieces[1::4]
        p3 = pieces[2::4]
        p4 = pieces[3::4]
        
        # Reconstruct bytes
        reconstructed = (p1 << 6) | (p2 << 4) | (p3 << 2) | p4
        reconstructed_bytes = reconstructed.tobytes()
        
        data_len = struct.unpack('>I', reconstructed_bytes[:4])[0]
        
        return reconstructed_bytes[4:4+data_len]

