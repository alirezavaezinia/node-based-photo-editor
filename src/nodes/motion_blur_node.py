from PyQt6.QtGui import QColor, QPainterPath, QPixmap, QIcon
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSlider, QSpinBox, QLabel,
    QGraphicsProxyWidget, QPushButton, QDialog, QGridLayout
)
import math
import numpy as np
import cv2
from PIL import Image

from image_core import (
    BaseNode,
    register_node,
    qpixmap_to_pil_image,
    pil_image_to_qpixmap,
    SOCKET_RADIUS,
    SOCKET_MARGIN,
)

# Presets مثال
PRESETS = [
    {"name": "Soft Horizontal", "distance": 15, "angle": 0, "steps": 1, "strength": 50},
    {"name": "Strong Vertical", "distance": 40, "angle": 90, "steps": 2, "strength": 80},
    {"name": "Diagonal Light", "distance": 25, "angle": 45, "steps": 1, "strength": 60},
    {"name": "Soft Diagonal", "distance": 20, "angle": 135, "steps": 1, "strength": 50},
]

class PresetDialog(QDialog):
    def __init__(self, parent, preview_img, apply_callback):
        super().__init__(parent)
        self.setWindowTitle("Motion Blur Templates")
        self.resize(600, 400)
        self.apply_callback = apply_callback

        layout = QGridLayout(self)

        for i, preset in enumerate(PRESETS):
            btn = QPushButton(preset["name"])
            btn.setFixedSize(120, 120)
            # اضافه کردن پیش‌نمایش کوچک با تبدیل به QIcon
            if preview_img:
                small = preview_img.resize((120, 120))
                qpix = pil_image_to_qpixmap(small)
                icon = QIcon(qpix)  # ← تبدیل QPixmap به QIcon
                btn.setIcon(icon)
                btn.setIconSize(btn.size())
            btn.clicked.connect(lambda checked, p=preset: self.select_preset(p))
            layout.addWidget(btn, i // 4, i % 4)

    def select_preset(self, preset):
        self.apply_callback(preset)
        self.accept()


@register_node("Motion Blur")
class MotionBlurNode(BaseNode):
    def __init__(self, view):
        super().__init__("Motion Blur", view)

        # ابعاد بزرگ‌تر برای کنترل‌ها
        self.width = 300

        # مقادیر پیش‌فرض
        self.distance = 15
        self.angle = 0
        self.steps = 1
        self.strength = 100

        # سوکت‌ها
        self.add_socket("In", is_output=False, socket_type="IMAGE")
        self.add_socket("Out", is_output=True, socket_type="IMAGE")

        # ساخت کنترل‌ها و template button
        self.create_controls()

        # محاسبه ارتفاع دینامیک با استفاده از widget اصلی
        self.height = self.widget.sizeHint().height() + self.outputs[0].pos().y() + SOCKET_RADIUS + SOCKET_MARGIN

    def create_controls(self):
        self.widget = QWidget()
        layout = QVBoxLayout(self.widget)
        layout.setContentsMargins(10, 10, 10, 10)

        # Distance
        dist_layout = QHBoxLayout()
        dist_layout.addWidget(QLabel("Distance"))
        self.distance_slider = QSlider(Qt.Orientation.Horizontal)
        self.distance_slider.setRange(1, 100)
        self.distance_slider.setValue(self.distance)
        self.distance_slider.sliderReleased.connect(self.on_value_changed)
        dist_layout.addWidget(self.distance_slider)
        self.distance_spin = QSpinBox()
        self.distance_spin.setRange(1, 100)
        self.distance_spin.setValue(self.distance)
        self.distance_spin.editingFinished.connect(self.on_value_changed)
        dist_layout.addWidget(self.distance_spin)
        layout.addLayout(dist_layout)

        # Angle
        angle_layout = QHBoxLayout()
        angle_layout.addWidget(QLabel("Angle"))
        self.angle_slider = QSlider(Qt.Orientation.Horizontal)
        self.angle_slider.setRange(0, 360)
        self.angle_slider.setValue(self.angle)
        self.angle_slider.sliderReleased.connect(self.on_value_changed)
        angle_layout.addWidget(self.angle_slider)
        self.angle_spin = QSpinBox()
        self.angle_spin.setRange(0, 360)
        self.angle_spin.setValue(self.angle)
        self.angle_spin.editingFinished.connect(self.on_value_changed)
        angle_layout.addWidget(self.angle_spin)
        layout.addLayout(angle_layout)

        # Steps
        steps_layout = QHBoxLayout()
        steps_layout.addWidget(QLabel("Steps"))
        self.steps_slider = QSlider(Qt.Orientation.Horizontal)
        self.steps_slider.setRange(1, 20)
        self.steps_slider.setValue(self.steps)
        self.steps_slider.sliderReleased.connect(self.on_value_changed)
        steps_layout.addWidget(self.steps_slider)
        self.steps_spin = QSpinBox()
        self.steps_spin.setRange(1, 20)
        self.steps_spin.setValue(self.steps)
        self.steps_spin.editingFinished.connect(self.on_value_changed)
        steps_layout.addWidget(self.steps_spin)
        layout.addLayout(steps_layout)

        # Strength
        strength_layout = QHBoxLayout()
        strength_layout.addWidget(QLabel("Strength"))
        self.strength_slider = QSlider(Qt.Orientation.Horizontal)
        self.strength_slider.setRange(0, 100)
        self.strength_slider.setValue(self.strength)
        self.strength_slider.sliderReleased.connect(self.on_value_changed)
        strength_layout.addWidget(self.strength_slider)
        self.strength_spin = QSpinBox()
        self.strength_spin.setRange(0, 100)
        self.strength_spin.setValue(self.strength)
        self.strength_spin.editingFinished.connect(self.on_value_changed)
        strength_layout.addWidget(self.strength_spin)
        layout.addLayout(strength_layout)

        # Template Button
        self.template_button = QPushButton("Templates")
        self.template_button.clicked.connect(self.open_template_dialog)
        layout.addWidget(self.template_button)

        # Embed widget into node
        self.proxy_widget = QGraphicsProxyWidget(self)
        self.proxy_widget.setWidget(self.widget)

    def open_template_dialog(self):
        input_pixmap = self.get_input_data(0)
        if isinstance(input_pixmap, QPixmap):
            preview_img = qpixmap_to_pil_image(input_pixmap).resize((120, 120))
        else:
            preview_img = None
        dlg = PresetDialog(None, preview_img, self.apply_preset)
        dlg.exec()

    def apply_preset(self, preset):
        self.distance = preset["distance"]
        self.angle = preset["angle"]
        self.steps = preset["steps"]
        self.strength = preset["strength"]
        self.sync_controls()
        self.view.scene().update_graph()

    def sync_controls(self):
        self.distance_slider.setValue(self.distance)
        self.distance_spin.setValue(self.distance)
        self.angle_slider.setValue(self.angle)
        self.angle_spin.setValue(self.angle)
        self.steps_slider.setValue(self.steps)
        self.steps_spin.setValue(self.steps)
        self.strength_slider.setValue(self.strength)
        self.strength_spin.setValue(self.strength)

    def on_value_changed(self):
        self.distance = self.distance_slider.value()
        self.angle = self.angle_slider.value()
        self.steps = self.steps_slider.value()
        self.strength = self.strength_slider.value()
        self.sync_controls()
        self.view.scene().update_graph()

    def compute(self):
        input_pixmap = self.get_input_data(0)
        if isinstance(input_pixmap, QPixmap):
            pil_img = qpixmap_to_pil_image(input_pixmap).convert("RGBA")
            img = np.array(pil_img)

            kernel_size = max(1, self.distance)
            kernel = np.zeros((kernel_size, kernel_size), dtype=np.float32)

            angle_rad = math.radians(self.angle)
            x = np.linspace(-kernel_size // 2, kernel_size // 2, kernel_size)
            y = np.linspace(-kernel_size // 2, kernel_size // 2, kernel_size)
            xv, yv = np.meshgrid(x, y)
            line = np.cos(angle_rad) * xv + np.sin(angle_rad) * yv
            kernel[np.abs(line) < self.steps] = 1.0
            kernel /= np.sum(kernel)

            blurred = cv2.filter2D(img, -1, kernel)
            alpha = self.strength / 100.0
            final = cv2.addWeighted(img, 1 - alpha, blurred, alpha, 0)

            final_img = Image.fromarray(final)
            self.output_data = pil_image_to_qpixmap(final_img)
        else:
            self.output_data = None
        return self.output_data

    def get_parameters(self):
        return {
            "distance": self.distance,
            "angle": self.angle,
            "steps": self.steps,
            "strength": self.strength,
        }

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def paint(self, painter, option, widget=None):
        painter.setBrush(QColor("#2563eb"))
        painter.setPen(self.pen)
        painter.drawRoundedRect(self.boundingRect(), 10, 10)

        title_path = QPainterPath()
        title_path.addRoundedRect(0, 0, self.width, self.title_height, 10, 10)
        title_path.addRect(0, self.title_height - 5, self.width, 5)
        painter.setBrush(QColor("#1e3a8a"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawPath(title_path)
