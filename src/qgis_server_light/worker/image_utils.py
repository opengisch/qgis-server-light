from typing import Tuple

from fpng_py import CompressionFlags, fpng_encode_image_to_memory
from PyQt5.QtCore import QBuffer, QByteArray, QIODevice
from PyQt5.QtGui import QImage


def _encode_image(image: QImage, fmt: str) -> Tuple:
    """Encodes an image in a specific mime type
    Args:
        image (QImage): The image to encode
        fmt (str): The mime type of the format
    Returns:
        A tuple with mime type and bytes-like object of an encoded image in the desired format
    """
    if fmt.lower() == "image/png":
        image.convertTo(QImage.Format_RGBA8888)
        image_data = fpng_encode_image_to_memory(
            image.constBits().asstring(image.sizeInBytes()),
            image.width(),
            image.height(),
            0,
            CompressionFlags.NONE,
        )
        return "image/png", image_data
    else:
        image_data = QByteArray()
        buf = QBuffer(image_data)
        buf.open(QIODevice.WriteOnly)
        image.save(buf, "JPG")
        return "image/jpeg", image_data
