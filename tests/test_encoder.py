import pytest
import os
import tempfile
from encoder import ImageCoder

def test_encode_decode_valid():
    data = b"Testing encoding and decoding!"
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_name = tmp.name
    
    try:
        ImageCoder.encode(data, tmp_name)
        decoded_data = ImageCoder.decode(tmp_name)
        assert decoded_data == data
    finally:
        os.remove(tmp_name)

@pytest.mark.parametrize("size", [1, 2, 3, 4, 7, 8, 15, 1024, 65536])
def test_encode_decode_different_sizes(size):
    data = os.urandom(size)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_name = tmp.name
        
    try:
        ImageCoder.encode(data, tmp_name)
        decoded_data = ImageCoder.decode(tmp_name)
        assert decoded_data == data
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)

def test_decode_from_bytes():
    data = b"Bytes testing!"
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_name = tmp.name
        
    try:
        ImageCoder.encode(data, tmp_name)
        with open(tmp_name, "rb") as f:
            img_bytes = f.read()
        
        decoded_data = ImageCoder.decode(img_bytes)
        assert decoded_data == data
    finally:
        os.remove(tmp_name)

def test_generate_cover():
    width, height = 100, 100
    cover = ImageCoder._generate_cover(width, height)
    
    # Check shape
    assert cover.shape == (height, width, 3)
    
    # Check that lowest 2 bits are clear
    assert (cover & 0x03).sum() == 0

def test_decode_non_rgb():
    from PIL import Image
    data = b"Testing non-RGB decoding"
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_name = tmp.name
        
    try:
        ImageCoder.encode(data, tmp_name)
        # Convert the saved image to RGBA
        img = Image.open(tmp_name)
        img = img.convert("RGBA")
        img.save(tmp_name)
        
        # Now decode should hit the 'if img.mode != "RGB":' branch
        decoded_data = ImageCoder.decode(tmp_name)
        assert decoded_data == data
    finally:
        if os.path.exists(tmp_name):
            os.remove(tmp_name)

