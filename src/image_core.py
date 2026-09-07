import sys
import os
import uuid
import hashlib
import json
import importlib.util
from PyQt6.QtWidgets import (QGraphicsItem, QGraphicsTextItem, QGraphicsProxyWidget, 
                             QWidget, QSlider, QVBoxLayout, QLabel, QSpinBox,
                             QGraphicsView, QGraphicsScene, QGraphicsPixmapItem)
from PyQt6.QtGui import (QPainter, QColor, QPixmap, QBrush, QPen, QPainterPath, QImage, QWheelEvent)
from PyQt6.QtCore import Qt, QRectF, QPointF, QObject, pyqtSignal, QRunnable
from PIL import Image, ImageEnhance, ImageQt
import numpy as np

# --- CONFIGURATION & REGISTRY ---
NODE_WIDTH = 220
TITLE_HEIGHT = 25
SOCKET_RADIUS = 8
SOCKET_MARGIN = 10
CACHE_DIR = ".cache"
NODE_REGISTRY = {}

if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

def register_node(name):
    """A decorator to automatically register node classes."""
    def decorator(cls):
        NODE_REGISTRY[name] = cls
        return cls
    return decorator

def load_nodes_from_directory(path):
    """Scans all python files in a directory for new nodes."""
    if not os.path.exists(path):
        print(f"Warning: Nodes directory not found at '{path}'")
        return
    for filename in os.listdir(path):
        if filename.endswith(".py") and filename != "__init__.py":
            module_path = os.path.join(path, filename)
            module_name = filename[:-3]
            try:
                spec = importlib.util.spec_from_file_location(module_name, module_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                print(f"Loaded external nodes from: {filename}")
            except Exception as e:
                print(f"Error loading node from {filename}: {e}")

# --- UTILITY FUNCTIONS ---
def qpixmap_to_pil_image(pixmap):
    image = pixmap.toImage().convertToFormat(QImage.Format.Format_RGBA8888)
    width, height = image.width(), image.height()
    ptr = image.bits()
    ptr.setsize(height * width * 4)
    arr = np.array(ptr).reshape((height, width, 4))
    return Image.fromarray(arr)

def pil_image_to_qpixmap(pil_image):
    if pil_image.mode != "RGBA": pil_image = pil_image.convert("RGBA")
    return QPixmap.fromImage(ImageQt.ImageQt(pil_image))

# --- UI WIDGETS ---
class HQPreview(QGraphicsView):
    """A reusable high-quality image preview widget with zoom/pan."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self._pixmap_item = QGraphicsPixmapItem()
        self.scene().addItem(self._pixmap_item)

    def set_pixmap(self, pixmap):
        self._pixmap_item.setPixmap(pixmap if pixmap and not pixmap.isNull() else QPixmap())
        self.fitInView(self.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent):
        zoom_factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(zoom_factor, zoom_factor)

# --- THREADING & WORKER CLASSES ---
class WorkerSignals(QObject):
    """Defines signals available from a running worker thread."""
    finished = pyqtSignal(str, object)

class NodeProcessor(QRunnable):
    """A worker thread for processing a single node."""
    def __init__(self, node):
        super().__init__()
        self.node = node
        self.signals = WorkerSignals()

    def run(self):
        """Executes the node's process method and emits a finished signal."""
        result = self.node.process()
        self.signals.finished.emit(self.node.uuid, result)

# --- GRAPH CLASSES ---
class Edge(QGraphicsItem):
    def __init__(self, start_socket, end_socket):
        super().__init__()
        self.start_socket = start_socket
        self.end_socket = end_socket
        self.start_socket.add_edge(self)
        if self.end_socket: self.end_socket.add_edge(self)
        self.setZValue(-1)
        self.pen = QPen(QColor("#fde047"), 2)
        self.pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.path = QPainterPath()
        self.update_path()

    def boundingRect(self):
        return self.path.boundingRect()

    def paint(self, painter, option, widget=None):
        painter.setPen(self.pen)
        painter.drawPath(self.path)

    def update_path(self):
        self.prepareGeometryChange()
        self.path = QPainterPath()
        start_pos = self.start_socket.scenePos()
        end_pos = self.end_socket.scenePos() if self.end_socket else self.mapFromScene(self.start_socket.view.last_mouse_scene_pos)
        self.path.moveTo(start_pos)
        dx = abs(start_pos.x() - end_pos.x())
        ctrl1 = QPointF(start_pos.x() + dx * 0.5, start_pos.y())
        ctrl2 = QPointF(end_pos.x() - dx * 0.5, end_pos.y())
        self.path.cubicTo(ctrl1, ctrl2, end_pos)
        self.update()

    def disconnect(self):
        if self.start_socket: self.start_socket.remove_edge(self)
        if self.end_socket: self.end_socket.remove_edge(self)
        if self.scene(): self.scene().removeItem(self)

class Socket(QGraphicsItem):
    def __init__(self, parent, text, is_output=False, socket_type='IMAGE'):
        super().__init__(parent)
        self.node = parent
        self.view = self.node.view
        self.is_output = is_output
        self.socket_type = socket_type
        self.edges = []
        self.setAcceptHoverEvents(True)
        self.radius = SOCKET_RADIUS
        self.brush = QBrush(QColor("#1e293b"))
        self.pen = QPen(QColor("#475569"), 2)
        self.hover_pen = QPen(QColor("#fde047"), 2)
        self._is_hovered = False
        self.text_item = QGraphicsTextItem(text, self)
        self.text_item.setDefaultTextColor(QColor("#cbd5e1"))
        y_pos = -self.text_item.boundingRect().height() / 2
        x_pos = -self.radius - self.text_item.boundingRect().width() - 5 if is_output else self.radius + 5
        self.text_item.setPos(x_pos, y_pos)

    def boundingRect(self):
        return QRectF(-self.radius, -self.radius, 2 * self.radius, 2 * self.radius)

    def paint(self, painter, option, widget=None):
        painter.setBrush(self.brush)
        painter.setPen(self.hover_pen if self._is_hovered else self.pen)
        painter.drawEllipse(self.boundingRect())

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.is_output or not self.edges: 
                self.view.start_edge_drag(self)
            else: # Disconnecting an input socket
                edge = self.edges[0]
                original_start_socket = edge.start_socket
                self.node.clear_cache()
                edge.disconnect()
                self.view.start_edge_drag(original_start_socket)
                self.view.scene().update_graph()

    def mouseReleaseEvent(self, event):
        self.view.end_edge_drag(self)

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self.update()

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        self.update()

    def add_edge(self, edge):
        self.edges.append(edge)

    def remove_edge(self, edge):
        if edge in self.edges:
            self.edges.remove(edge)

class BaseNode(QGraphicsItem):
    def __init__(self, title, view, has_layer_sockets=False):
        super().__init__()
        self.view = view
        self.title = title
        self.uuid = str(uuid.uuid4())
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setCacheMode(QGraphicsItem.CacheMode.DeviceCoordinateCache)
        
        self.width = NODE_WIDTH
        self.title_height = TITLE_HEIGHT
        self.title_color = QColor("#475569")
        self.bg_color = QColor("#1e293b")
        self.pen = QPen(QColor("#0f172a"), 2)
        
        self.title_text = QGraphicsTextItem(self.title, self)
        self.title_text.setDefaultTextColor(QColor("#f8fafc"))
        self.title_text.setPos(5, 2)
        
        self.inputs = []
        self.outputs = []
        self.output_data = None
        self._cache_key = None
        self._in_memory_cache = None
        self.is_processing = False
        
        if has_layer_sockets:
            self.add_socket("Layer In", is_output=False, socket_type='LAYER')
            self.add_socket("Layer Out", is_output=True, socket_type='LAYER')

    def add_socket(self, text, is_output=False, socket_type='IMAGE'):
        socket = Socket(self, text, is_output, socket_type)
        container = self.get_ui_container()
        base_y = container.y() + container.height() if container else self.title_height
        
        relevant_sockets = [s for s in (self.inputs if not is_output else self.outputs) if s.socket_type == socket_type]
        y_pos = base_y + SOCKET_MARGIN + len(relevant_sockets) * (2 * SOCKET_RADIUS + SOCKET_MARGIN)
        if "Layer" in text:
            y_pos = self.title_height / 2
        
        x_pos = 0 if not is_output else self.width
        socket.setPos(x_pos, y_pos)
        
        if is_output:
            self.outputs.append(socket)
        else:
            self.inputs.append(socket)
        return socket
        
    def get_ui_container(self):
        return QRectF(0, 0, 0, 0)

    def get_input_data(self, index):
        if index < len(self.inputs) and self.inputs[index].edges:
            connected_socket = self.inputs[index].edges[0].start_socket
            return connected_socket.node.output_data
        return None
        
    def get_output_data(self, socket):
        return self.output_data

    def get_parameters(self):
        return {}

    def get_cache_key(self):
        input_socket = next((s for s in self.inputs if s.socket_type == 'IMAGE'), None)
        input_key = ""
        if input_socket and input_socket.edges:
            input_node = input_socket.edges[0].start_socket.node
            input_key = input_node._cache_key if input_node._cache_key else input_node.get_cache_key()
        
        params = json.dumps(self.get_parameters(), sort_keys=True)
        key_string = f"{self.__class__.__name__}{input_key}{params}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    def process(self):
        new_key = self.get_cache_key()
        if self._cache_key == new_key and self._in_memory_cache is not None:
            self.output_data = self._in_memory_cache
            return self.output_data
            
        self._cache_key = new_key
        cache_path = os.path.join(CACHE_DIR, f"{self._cache_key}.png")
        if os.path.exists(cache_path):
            self.output_data = QPixmap(cache_path)
            self._in_memory_cache = self.output_data
            return self.output_data
            
        self.compute()
        self._in_memory_cache = self.output_data
        
        if isinstance(self.output_data, QPixmap) and not self.output_data.isNull():
            self.output_data.save(cache_path, "PNG")
        return self.output_data
        
    def compute(self):
        pass
    
    def clear_cache(self):
        """Clears the internal cache and output data for this node and all downstream nodes."""
        self.output_data = None
        self._in_memory_cache = None
        self._cache_key = None
        for socket in self.outputs:
            for edge in socket.edges:
                if edge.end_socket:
                    if edge.end_socket.node.output_data is not None:
                         edge.end_socket.node.clear_cache()

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            for socket in self.inputs + self.outputs:
                for edge in socket.edges:
                    edge.update_path()
        return super().itemChange(change, value)
        
    def update_layers(self):
        all_image_nodes = [item for item in self.scene().items() if "ImageNode" in type(item).__name__]
        sorted_nodes = []
        visited = set()
        def visit(node):
            if node in visited: return
            visited.add(node)
            layer_input_socket = next((s for s in node.inputs if s.socket_type == 'LAYER'), None)
            if layer_input_socket and layer_input_socket.edges:
                prev_node = layer_input_socket.edges[0].start_socket.node
                if "ImageNode" in type(prev_node).__name__:
                    visit(prev_node)
            sorted_nodes.append(node)
        
        for node in all_image_nodes:
            if node not in visited:
                visit(node)
        
        for i, node in enumerate(sorted_nodes):
            node.setZValue(i)

    def open_studio(self):
        """Default behavior for double-click. Nodes zoom into view."""
        item_rect = self.sceneBoundingRect()
        margin_factor = 0.8
        new_width = item_rect.width() / margin_factor
        new_height = item_rect.height() / margin_factor
        center_point = item_rect.center()
        margin_rect = QRectF(center_point.x() - new_width / 2, center_point.y() - new_height / 2, new_width, new_height)
        self.view.fitInView(margin_rect, Qt.AspectRatioMode.KeepAspectRatio)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        if self.view is not None:
            self.open_studio()
        event.accept()

# --- BUILT-IN NODES ---
@register_node("Grayscale")
class GrayscaleFilterNode(BaseNode):
    def __init__(self, view):
        super().__init__("Grayscale", view)
        self.add_socket("In", is_output=False)
        self.add_socket("Out", is_output=True)
        self.height = self.outputs[0].pos().y() + SOCKET_RADIUS + SOCKET_MARGIN

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget=None):
        painter.setBrush(QColor("#4f46e5"))
        painter.setPen(self.pen)
        painter.drawRoundedRect(self.boundingRect(), 5, 5)
        
        title_path = QPainterPath()
        title_path.addRoundedRect(0, 0, self.width, self.title_height, 5, 5)
        title_path.addRect(0, self.title_height - 5, self.width, 5)
        painter.setBrush(QColor("#312e81"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(title_path)

    def compute(self):
        input_pixmap = self.get_input_data(0)
        if isinstance(input_pixmap, QPixmap):
            image = qpixmap_to_pil_image(input_pixmap).convert("L").convert("RGBA")
            self.output_data = pil_image_to_qpixmap(image)
        else:
            self.output_data = None

@register_node("Lumetri Color")
class LumetriColorNode(BaseNode):
    def __init__(self, view):
        super().__init__("Lumetri Color", view)
        self.proxy_widget = self.create_controls()
        self.add_socket("In", is_output=False)
        self.add_socket("Out", is_output=True)
        self.height = self.outputs[0].pos().y() + SOCKET_RADIUS + SOCKET_MARGIN

    def get_ui_container(self):
        return self.proxy_widget.geometry().adjusted(0, self.title_height + 10, 0, self.title_height + 10)

    def create_controls(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)
        self.brightness_slider = self.create_slider(layout, "Brightness", 0, 200, 100)
        self.contrast_slider = self.create_slider(layout, "Contrast", 0, 200, 100)
        self.saturation_slider = self.create_slider(layout, "Saturation", 0, 200, 100)
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(widget)
        proxy.setPos(0, self.title_height)
        return proxy

    def create_slider(self, layout, name, min_val, max_val, default_val):
        layout.addWidget(QLabel(name, styleSheet="color: #cbd5e1;"))
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(default_val)
        slider.sliderReleased.connect(self.on_value_changed)
        layout.addWidget(slider)
        return slider

    def on_value_changed(self):
        self.clear_cache()
        self.view.scene().update_graph()

    def get_parameters(self):
        return {"b": self.brightness_slider.value(), "c": self.contrast_slider.value(), "s": self.saturation_slider.value()}

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget=None):
        painter.setBrush(QColor("#4f46e5"))
        painter.setPen(self.pen)
        painter.drawRoundedRect(self.boundingRect(), 5, 5)
        
        title_path = QPainterPath()
        title_path.addRoundedRect(0, 0, self.width, self.title_height, 5, 5)
        title_path.addRect(0, self.title_height - 5, self.width, 5)
        painter.setBrush(QColor("#312e81"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(title_path)

    def compute(self):
        input_pixmap = self.get_input_data(0)
        if isinstance(input_pixmap, QPixmap):
            image = qpixmap_to_pil_image(input_pixmap)
            enhancer = ImageEnhance.Brightness(image)
            image = enhancer.enhance(self.brightness_slider.value() / 100.0)
            enhancer = ImageEnhance.Contrast(image)
            image = enhancer.enhance(self.contrast_slider.value() / 100.0)
            enhancer = ImageEnhance.Color(image)
            image = enhancer.enhance(self.saturation_slider.value() / 100.0)
            self.output_data = pil_image_to_qpixmap(image)
        else:
            self.output_data = None

@register_node("Crop")
class CropNode(BaseNode):
    def __init__(self, view):
        super().__init__("Crop", view)
        self.proxy_widget = self.create_controls()
        self.add_socket("In", is_output=False)
        self.add_socket("Out", is_output=True)
        self.height = self.outputs[0].pos().y() + SOCKET_RADIUS + SOCKET_MARGIN
        self._initial_input_set = False

    def get_ui_container(self):
        return self.proxy_widget.geometry().adjusted(0, self.title_height + 10, 0, self.title_height + 10)

    def create_controls(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 5, 10, 5)
        layout.setSpacing(5)
        self.left_spin = self.create_spinbox(layout, "Left")
        self.top_spin = self.create_spinbox(layout, "Top")
        self.right_spin = self.create_spinbox(layout, "Right")
        self.bottom_spin = self.create_spinbox(layout, "Bottom")
        proxy = QGraphicsProxyWidget(self)
        proxy.setWidget(widget)
        proxy.setPos(0, self.title_height)
        return proxy

    def create_spinbox(self, layout, name):
        layout.addWidget(QLabel(name, styleSheet="color: #cbd5e1;"))
        spinbox = QSpinBox()
        spinbox.setRange(0, 9999)
        spinbox.setValue(0)
        spinbox.editingFinished.connect(self.on_value_changed)
        layout.addWidget(spinbox)
        return spinbox

    def update_spinbox_state(self, pixmap):
        if isinstance(pixmap, QPixmap) and not self._initial_input_set:
            self._initial_input_set = True
            w, h = pixmap.width(), pixmap.height()
            self.right_spin.blockSignals(True)
            self.bottom_spin.blockSignals(True)
            self.left_spin.setRange(0, w)
            self.right_spin.setRange(0, w)
            self.top_spin.setRange(0, h)
            self.bottom_spin.setRange(0, h)
            self.right_spin.setValue(w)
            self.bottom_spin.setValue(h)
            self.right_spin.blockSignals(False)
            self.bottom_spin.blockSignals(False)

    def on_value_changed(self):
        self.clear_cache()
        self.view.scene().update_graph()

    def get_parameters(self):
        return {"l": self.left_spin.value(), "t": self.top_spin.value(), "r": self.right_spin.value(), "b": self.bottom_spin.value()}

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget=None):
        painter.setBrush(QColor("#4f46e5"))
        painter.setPen(self.pen)
        painter.drawRoundedRect(self.boundingRect(), 5, 5)
        
        title_path = QPainterPath()
        title_path.addRoundedRect(0, 0, self.width, self.title_height, 5, 5)
        title_path.addRect(0, self.title_height - 5, self.width, 5)
        painter.setBrush(QColor("#312e81"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(title_path)

    def compute(self):
        input_pixmap = self.get_input_data(0)
        if not isinstance(input_pixmap, QPixmap):
            self.output_data = None
            return
            
        self.update_spinbox_state(input_pixmap)
        image = qpixmap_to_pil_image(input_pixmap)
        box = (self.left_spin.value(), self.top_spin.value(), self.right_spin.value(), self.bottom_spin.value())
        if box[2] > box[0] and box[3] > box[1]:
            try:
                cropped_image = image.crop(box)
                self.output_data = pil_image_to_qpixmap(cropped_image)
            except Exception:
                self.output_data = input_pixmap
        else:
            self.output_data = input_pixmap

