import sys
import os
from PyQt6.QtWidgets import (QApplication, QMainWindow, QGraphicsView, 
                             QGraphicsScene, QGraphicsPixmapItem, QGraphicsItem,
                             QFileDialog, QVBoxLayout, QWidget, QPushButton, QHBoxLayout,
                             QLabel, QSplitter, QGraphicsProxyWidget, QDialog, QToolButton,
                             QLineEdit, QCompleter, QStackedWidget)
from PyQt6.QtGui import (QPainter, QColor, QPixmap, QWheelEvent, QMouseEvent, QPainterPath, QMovie)
from PyQt6.QtCore import Qt, QPoint, QRectF, QPointF, QSize, QThreadPool

# --- وارد کردن از هسته اصلی برنامه ---
# HQPreview اکنون از اینجا وارد می‌شود تا از وابستگی دایره‌ای جلوگیری شود
from image_core import (BaseNode, Edge, Socket, NODE_WIDTH, NODE_REGISTRY, 
                        register_node, load_nodes_from_directory, NodeProcessor, HQPreview)

# --- بارگذاری تمام نودهای خارجی از پوشه 'nodes' ---
# این کار باید قبل از ساخت کلاس‌های اصلی انجام شود تا رجیستری کامل باشد
load_nodes_from_directory("nodes")

# --- نودهای داخلی برنامه ---

@register_node("Image")
class ImageNode(BaseNode):
    """نودی برای بارگذاری یک تصویر از فایل."""
    def __init__(self, title, pixmap, view):
        super().__init__(title, view, has_layer_sockets=True)
        self.original_pixmap = pixmap
        self.image_item = QGraphicsPixmapItem(self.original_pixmap, self)
        scale_factor = (self.width - 20) / self.original_pixmap.width()
        self.image_item.setScale(scale_factor)
        img_height = self.image_item.boundingRect().height() * scale_factor
        self.image_item.setPos(10, self.title_height + 10)
        self.height = self.title_height + img_height + 20
        self.add_socket("Image", is_output=True, socket_type='IMAGE')
        self.output_data = self.original_pixmap
    def boundingRect(self): return QRectF(0, 0, self.width, self.height)
    def paint(self, painter, option, widget=None):
        painter.setBrush(self.bg_color); painter.setPen(self.pen); painter.drawRoundedRect(self.boundingRect(), 5, 5)
        title_path = QPainterPath(); title_path.addRoundedRect(0, 0, self.width, self.title_height, 5, 5); title_path.addRect(0, self.title_height - 5, self.width, 5)
        painter.setBrush(self.title_color); painter.setPen(Qt.PenStyle.NoPen); painter.drawPath(title_path)
    def get_output_data(self, socket): return self.output_data
    def get_cache_key(self): return self.uuid

@register_node("Preview")
class PreviewNode(BaseNode):
    """نودی برای نمایش نتیجه نهایی پردازش."""
    def __init__(self, view, main_window):
        super().__init__("Preview", view)
        self.main_window = main_window; self.height = 300
        self.add_socket("In", is_output=False, socket_type='IMAGE')
        self.image_item = QGraphicsPixmapItem(self); self.image_item.setPos(10, self.title_height + 10)
        self.loading_label = QLabel(); self.loading_movie = QMovie(":/qt-project.org/styles/commonstyle/images/standardbutton-open-32.gif")
        self.loading_movie.setScaledSize(QSize(32,32)); self.loading_label.setMovie(self.loading_movie)
        self.loading_proxy = QGraphicsProxyWidget(self); self.loading_proxy.setWidget(self.loading_label)
        self.loading_proxy.setPos(self.width/2 - 16, self.height/2 - 16); self.set_loading(False)
        self.create_hq_button()
    def set_loading(self, is_loading):
        if is_loading: self.loading_proxy.show(); self.loading_movie.start()
        else: self.loading_proxy.hide(); self.loading_movie.stop()
    def create_hq_button(self):
        button = QPushButton("HQ"); button.setFixedSize(30, 20)
        button.setStyleSheet("QPushButton { background-color: #042f2e; color: white; border-radius: 5px; } QPushButton:hover { background-color: #064e3b; }")
        button.clicked.connect(self._toggle_hq_panel)
        proxy = QGraphicsProxyWidget(self); proxy.setWidget(button); proxy.setPos(self.width - button.width() - 5, 2)
    def _toggle_hq_panel(self):
        self.main_window.set_active_preview_node(self); current_image = self.get_input_data(0)
        self.main_window.toggle_side_panel(current_image)
    def boundingRect(self): return QRectF(0, 0, self.width, self.height)
    def paint(self, painter, option, widget=None):
        painter.setBrush(self.bg_color); painter.setPen(self.pen); painter.drawRoundedRect(self.boundingRect(), 5, 5)
        title_path = QPainterPath(); title_path.addRoundedRect(0, 0, self.width, self.title_height, 5, 5); title_path.addRect(0, self.title_height - 5, self.width, 5)
        painter.setBrush(QColor("#042f2e")); painter.setPen(Qt.PenStyle.NoPen); painter.drawPath(title_path)
    def update_preview(self):
        input_pixmap = self.get_input_data(0)
        if isinstance(input_pixmap, QPixmap):
            scaled = input_pixmap.scaled(self.width - 20, int(self.height - self.title_height - 20), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.image_item.setPixmap(scaled)
        else: self.image_item.setPixmap(QPixmap())
        if self.main_window.side_panel.isVisible() and self.main_window.active_preview_node is self:
            self.main_window.side_panel.set_image(input_pixmap)
        self.set_loading(False)

class InfiniteCanvasView(QGraphicsView):
    """ویجت نمایشگر بوم بی‌نهایت با قابلیت زوم و پن."""
    def __init__(self, scene):
        super().__init__(scene)
        self.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.NoDrag); self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._is_panning = False; self._last_mouse_pos = QPoint(); self.temp_edge = None; self.drag_start_socket = None; self.last_mouse_scene_pos = QPointF()
    def wheelEvent(self, event: QWheelEvent): zoom_factor = 1.25 if event.angleDelta().y() > 0 else 1 / 1.25; self.scale(zoom_factor, zoom_factor)
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton: self._is_panning = True; self._last_mouse_pos = event.pos(); self.setCursor(Qt.CursorShape.ClosedHandCursor); event.accept()
        else: super().mousePressEvent(event)
    def mouseMoveEvent(self, event: QMouseEvent):
        self.last_mouse_scene_pos = self.mapToScene(event.pos())
        if self._is_panning: delta = event.pos() - self._last_mouse_pos; self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x()); self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y()); self._last_mouse_pos = event.pos(); event.accept()
        elif self.temp_edge: self.temp_edge.update_path()
        else: super().mouseMoveEvent(event)
    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.temp_edge and event.button() == Qt.MouseButton.LeftButton:
            item_at = self.itemAt(event.pos())
            if isinstance(item_at, Socket): self.end_edge_drag(item_at)
            else: self.cancel_edge_drag()
        elif event.button() == Qt.MouseButton.MiddleButton: self._is_panning = False; self.setCursor(Qt.CursorShape.ArrowCursor); event.accept()
        else: super().mouseReleaseEvent(event)
    def start_edge_drag(self, start_socket):
        if start_socket.edges and not start_socket.is_output: return
        self.drag_start_socket = start_socket; self.temp_edge = Edge(start_socket, None); self.scene().addItem(self.temp_edge)
    def end_edge_drag(self, end_socket):
        if not self.temp_edge: return
        start_socket = self.drag_start_socket
        output_socket, input_socket = (start_socket, end_socket) if start_socket.is_output else (end_socket, start_socket)
        valid = (output_socket and input_socket and output_socket.is_output and not input_socket.is_output and output_socket.node != input_socket.node and output_socket.socket_type == input_socket.socket_type and not input_socket.edges)
        if valid:
            final_edge = Edge(output_socket, input_socket); self.scene().addItem(final_edge); input_socket.node.clear_cache() 
            if output_socket.socket_type == 'LAYER': output_socket.node.update_layers()
            else: self.scene().update_graph()
        self.cancel_edge_drag()
    def cancel_edge_drag(self):
        if self.temp_edge: self.scene().removeItem(self.temp_edge)
        self.temp_edge = None; self.drag_start_socket = None

class InfiniteCanvasScene(QGraphicsScene):
    """صحنه گراف که منطق پردازش چندریسمانی را مدیریت می‌کند."""
    def __init__(self, parent_window):
        super().__init__(); self.parent_window = parent_window; self.setSceneRect(-5000, -5000, 10000, 10000)
        self.grid_spacing = 50; self.bg_color = QColor(30, 30, 30); self.dot_color = QColor(70, 70, 70)
        self.thread_pool = QThreadPool()
    def drawBackground(self, painter: QPainter, rect: QRectF):
        painter.fillRect(rect, self.bg_color); painter.setPen(self.dot_color)
        left = int(rect.left() / self.grid_spacing) * self.grid_spacing; top = int(rect.top() / self.grid_spacing) * self.grid_spacing
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom(): painter.drawPoint(int(x), int(y)); y += self.grid_spacing
            x += self.grid_spacing
    def on_node_finished(self, node_uuid, result):
        node = next((item for item in self.items() if isinstance(item, BaseNode) and item.uuid == node_uuid), None)
        if not node: return
        node.is_processing = False; node.output_data = result
        nodes_to_check = set()
        for out_socket in node.outputs:
            for edge in out_socket.edges:
                if edge.end_socket: nodes_to_check.add(edge.end_socket.node)
        for n in nodes_to_check: self.submit_node_if_ready(n)
    def submit_node_if_ready(self, node):
        if node.is_processing or node.output_data is not None: return
        is_ready = all(not (in_socket.edges and in_socket.socket_type == 'IMAGE') or in_socket.edges[0].start_socket.node.output_data is not None for in_socket in node.inputs)
        if is_ready:
            node.is_processing = True
            if isinstance(node, PreviewNode): node.update_preview(); node.is_processing = False; return
            worker = NodeProcessor(node); worker.signals.finished.connect(self.on_node_finished); self.thread_pool.start(worker)
    def update_graph(self):
        all_nodes = [item for item in self.items() if isinstance(item, BaseNode)]
        for p_node in all_nodes:
            if isinstance(p_node, PreviewNode):
                if p_node.inputs and p_node.inputs[0].edges and p_node.inputs[0].edges[0].start_socket.node.output_data is None: p_node.set_loading(True)
        QApplication.processEvents()
        for node in all_nodes: self.submit_node_if_ready(node)

class FullScreenViewer(QDialog):
    """پنجره نمایش تمام‌صفحه برای پیش‌نمایش با کیفیت بالا."""
    def __init__(self, pixmap, parent=None):
        super().__init__(parent); self.setWindowTitle("Full Screen Preview"); self.setLayout(QVBoxLayout()); self.layout().setContentsMargins(0,0,0,0)
        self.viewer = HQPreview(self); self.viewer.set_pixmap(pixmap); self.layout().addWidget(self.viewer); self.showFullScreen()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.close()
    def mouseDoubleClickEvent(self, a0): self.close()

class SidePanel(QWidget):
    """پنل کناری برای نمایش پیش‌نمایش با کیفیت بالا."""
    def __init__(self, parent=None):
        super().__init__(parent); self.setMinimumWidth(300); self.setStyleSheet("background-color: #1e293b; color: white;")
        layout = QVBoxLayout(self); layout.setContentsMargins(5, 5, 5, 5); toolbar = QHBoxLayout(); layout.addLayout(toolbar)
        self.title_label = QLabel("High Quality Preview"); self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        self.fullscreen_btn = QToolButton(); self.fullscreen_btn.setText("⛶"); self.fullscreen_btn.setStyleSheet("font-size: 20px; border: none;"); self.fullscreen_btn.clicked.connect(self.go_fullscreen)
        toolbar.addWidget(self.title_label, 1); toolbar.addWidget(self.fullscreen_btn)
        self.preview_widget = HQPreview(self); layout.addWidget(self.preview_widget); self._current_pixmap = None
    def set_image(self, pixmap): self._current_pixmap = pixmap; self.preview_widget.set_pixmap(pixmap)
    def go_fullscreen(self):
        if self._current_pixmap and not self._current_pixmap.isNull(): self.fs_viewer = FullScreenViewer(self._current_pixmap, self); self.fs_viewer.show()

class SearchBar(QLineEdit):
    """ویجت جستجو برای پیدا کردن و ساختن نودها."""
    def __init__(self, parent=None):
        super().__init__(parent); self.setPlaceholderText("Search for a node...")
        self.setStyleSheet("QLineEdit { background-color: #1e293b; color: white; border: 1px solid #475569; border-radius: 5px; padding: 8px; font-size: 16px; }")
        self.setFixedSize(400, 40)
        completer = QCompleter(list(NODE_REGISTRY.keys())); completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setFilterMode(Qt.MatchFlag.MatchContains); self.setCompleter(completer)
        self.returnPressed.connect(self.on_enter)
    def on_enter(self): self.parent().create_node_from_search(self.text()); self.hide()
    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape: self.hide()
        else: super().keyPressEvent(event)

class MainWindow(QMainWindow):
    """پنجره اصلی برنامه که ویجت‌های مختلف را مدیریت می‌کند."""
    def __init__(self):
        super().__init__(); self.setWindowTitle("Node-Based Photo Editor"); self.setStyleSheet("background-color: #2A2A2A;")
        self.stack = QStackedWidget(); self.setCentralWidget(self.stack)
        
        # --- نمای اصلی گراف ---
        self.scene = InfiniteCanvasScene(self); self.view = InfiniteCanvasView(self.scene)
        self.side_panel = SidePanel(); self.side_panel.hide(); self.active_preview_node = None
        self.graph_view_widget = QWidget(); graph_layout = QHBoxLayout(self.graph_view_widget); graph_layout.setContentsMargins(0,0,0,0)
        splitter = QSplitter(Qt.Orientation.Horizontal); splitter.addWidget(self.view); splitter.addWidget(self.side_panel)
        splitter.setSizes([1200, 400]); graph_layout.addWidget(splitter)
        self.stack.addWidget(self.graph_view_widget)
        
        self.active_fullscreen_node = None
        self.search_bar = SearchBar(self); self.search_bar.hide(); self.resize(1600, 900)

    def show_fullscreen_widget(self, widget, node):
        """یک ویجت (مانند استودیو) را به صورت تمام‌صفحه نمایش می‌دهد."""
        self.active_fullscreen_node = node
        widget.accepted.connect(self._on_fullscreen_accept)
        widget.rejected.connect(self._on_fullscreen_reject)
        self.stack.addWidget(widget); self.stack.setCurrentWidget(widget)

    def _close_fullscreen_widget(self):
        widget = self.stack.currentWidget()
        if widget is not self.graph_view_widget:
            self.stack.removeWidget(widget); widget.deleteLater()
        self.stack.setCurrentWidget(self.graph_view_widget); self.active_fullscreen_node = None

    def _on_fullscreen_accept(self, params):
        if hasattr(self.active_fullscreen_node, 'on_studio_accepted'):
             self.active_fullscreen_node.on_studio_accepted(params)
        self._close_fullscreen_widget()

    def _on_fullscreen_reject(self): self._close_fullscreen_widget()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.stack.currentIndex() != 0: self._close_fullscreen_widget()
        elif event.key() == Qt.Key.Key_Alt and self.stack.currentIndex() == 0:
            self.search_bar.show(); self.search_bar.setFocus(); self.search_bar.selectAll()
            x_pos = int(self.view.viewport().width() / 2 - self.search_bar.width() / 2)
            self.search_bar.move(x_pos, 50); event.accept()
        else: super().keyPressEvent(event)

    def set_active_preview_node(self, node): self.active_preview_node = node
    def toggle_side_panel(self, pixmap):
        if self.side_panel.isVisible(): self.side_panel.hide()
        else: self.side_panel.set_image(pixmap); self.side_panel.show()

    def create_node_from_search(self, node_name):
        completer = self.search_bar.completer()
        if completer.completionCount() > 0: node_name = completer.currentCompletion()
        if node_name not in NODE_REGISTRY: return
        node_class = NODE_REGISTRY[node_name]; pos = self.view.mapToScene(self.view.viewport().rect().center())
        node_instance = None
        
        # بررسی بر اساس نام رجیستر شده برای نودهای خاص
        if node_name == "Image":
            file_path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Images (*.png *.jpg *.jpeg)")
            if file_path:
                pixmap = QPixmap(file_path)
                if not pixmap.isNull(): node_instance = node_class(title=os.path.basename(file_path), pixmap=pixmap, view=self.view)
        elif node_name == "Preview":
            node_instance = node_class(view=self.view, main_window=self)
        else: 
            node_instance = node_class(view=self.view)
            
        if node_instance:
            node_instance.setPos(pos); self.scene.addItem(node_instance); self.scene.update_graph()

def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        QSplitter::handle { background-color: #4A4A4A; }
        QLabel { color: #cbd5e1; }
        QPushButton { background-color: #3f3f46; color: white; border: 1px solid #52525b; padding: 5px; border-radius: 4px; }
        QPushButton:hover { background-color: #52525b; }
        QSlider::groove:horizontal { border: 1px solid #bbb; background: #5A5A5A; height: 8px; border-radius: 4px; }
        QSlider::handle:horizontal { background: #4f46e5; border: 1px solid #312e81; width: 16px; margin: -4px 0; border-radius: 8px; }
        QSpinBox { background-color: #3A3A3A; color: white; border: 1px solid #555; padding: 2px; }
    """)
    window = MainWindow(); window.show()
    sys.exit(app.exec())

if __name__ == '__main__':
    main()

