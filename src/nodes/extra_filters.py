from PyQt6.QtGui import QColor, QPainterPath, QPixmap
from PyQt6.QtCore import QRectF, Qt
from image_core import BaseNode, register_node, qpixmap_to_pil_image, pil_image_to_qpixmap, SOCKET_RADIUS, SOCKET_MARGIN

@register_node("Sepia Filter")
class SepiaFilterNode(BaseNode):
    """
    A node that applies a sepia effect to an image.
    """
    def __init__(self, view):
        super().__init__("Sepia Filter", view)
        self.add_socket("In", is_output=False, socket_type='IMAGE')
        self.add_socket("Out", is_output=True, socket_type='IMAGE')
        self.height = self.outputs[0].pos().y() + SOCKET_RADIUS + SOCKET_MARGIN

    def boundingRect(self): return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget=None):
        painter.setBrush(QColor("#a16207")) # A brownish color for the node
        painter.setPen(self.pen)
        painter.drawRoundedRect(self.boundingRect(), 5, 5)
        
        title_path = QPainterPath()
        title_path.addRoundedRect(0, 0, self.width, self.title_height, 5, 5)
        title_path.addRect(0, self.title_height - 5, self.width, 5)
        painter.setBrush(QColor("#713f12"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(title_path)

    def compute(self):
        input_pixmap = self.get_input_data(0)
        if isinstance(input_pixmap, QPixmap):
            image = qpixmap_to_pil_image(input_pixmap)
            
            # Apply sepia formula
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            width, height = image.size
            pixels = image.load()
            
            for py in range(height):
                for px in range(width):
                    r, g, b = image.getpixel((px, py))
                    tr = int(0.393 * r + 0.769 * g + 0.189 * b)
                    tg = int(0.349 * r + 0.686 * g + 0.168 * b)
                    tb = int(0.272 * r + 0.534 * g + 0.131 * b)
                    
                    if tr > 255: tr = 255
                    if tg > 255: tg = 255
                    if tb > 255: tb = 255
                    
                    pixels[px, py] = (tr, tg, tb)

            self.output_data = pil_image_to_qpixmap(image)
        else:
            self.output_data = None
        return self.output_data
