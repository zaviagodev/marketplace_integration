from PIL import Image
from io import BytesIO


def compress_image(image_path, target_size):
    image = Image.open(image_path)
    return _compress_image(image, target_size)


def _compress_image(image, target_size):

    current_quality = 95
    target_size = target_size * 1024 * 1024

    while True:
        
        resized_image = BytesIO()
        image.save(resized_image, format="jpeg", optimize=True, quality=current_quality)
        
        current_size = resized_image.tell()

        if current_size <= target_size:
            resized_image.seek(0)
            return resized_image

        current_quality -= 5

        
        if current_quality < 10:
            raise Exception("Could not resize your image.")

