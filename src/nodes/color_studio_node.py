import sys
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSlider, 
                             QPushButton, QFrame, QScrollArea, QGraphicsProxyWidget)
from PyQt6.QtGui import QColor, QPainterPath, QPixmap
from PyQt6.QtCore import Qt, QRectF, pyqtSignal

# --- وارد کردن کلاس‌های ضروری از هسته اصلی برنامه ---
# HQPreview اکنون از image_core وارد می‌شود تا وابستگی دایره‌ای شکسته شود
from image_core import (BaseNode, register_node, qpixmap_to_pil_image, pil_image_to_qpixmap, 
                        SOCKET_RADIUS, SOCKET_MARGIN, HQPreview)
from PIL import Image, ImageEnhance
import numpy as np

# --- ویجت کنترلی قابل استفاده مجدد ---
class LabeledSlider(QWidget):
    """ویجتی شامل یک لیبل، یک اسلایدر و یک نمایشگر مقدار."""
    value_changed = pyqtSignal(int)
    def __init__(self, text, min_val, max_val, default_val):
        super().__init__()
        layout = QHBoxLayout(self); layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel(text); self.label.setFixedWidth(80); layout.addWidget(self.label)
        self.slider = QSlider(Qt.Orientation.Horizontal); self.slider.setRange(min_val, max_val); self.slider.setValue(default_val)
        self.slider.sliderMoved.connect(self._on_slider_move); layout.addWidget(self.slider)
        self.value_label = QLabel(str(default_val)); self.value_label.setFixedWidth(35); layout.addWidget(self.value_label)
    def _on_slider_move(self, value): self.value_label.setText(str(value)); self.value_changed.emit(value)
    def value(self): return self.slider.value()
    def setValue(self, value): self.slider.setValue(value); self.value_label.setText(str(value))

# --- ویجت اصلی استودیو ---
class ColorStudioWidget(QWidget):
    """ویجت تمام‌صفحه برای تنظیمات رنگ و نور."""
    accepted = pyqtSignal(dict); rejected = pyqtSignal()
    def __init__(self, input_pixmap, initial_params):
        super().__init__()
        self.setStyleSheet("background-color: #18181b; color: #e4e4e7;")
        self._original_pixmap = input_pixmap; self._initial_params = initial_params.copy(); self._current_params = initial_params.copy()
        self.main_layout = QHBoxLayout(self)
        self.main_layout.addWidget(self._create_left_panel(), 1)
        self.preview = HQPreview(); self.preview.set_pixmap(self._original_pixmap); self.main_layout.addWidget(self.preview, 4)
        self.update_preview()

    def _create_left_panel(self):
        panel = QFrame(); panel_layout = QVBoxLayout(panel)
        scroll_area = QScrollArea(); scroll_area.setWidgetResizable(True); scroll_area.setStyleSheet("QScrollArea { border: none; }")
        controls_widget = QWidget(); controls_layout = QVBoxLayout(controls_widget)
        
        wb_group = self._create_group_box("White Balance")
        self.temp_slider = LabeledSlider("Temperature", -100, 100, self._current_params.get("temp", 0))
        self.tint_slider = LabeledSlider("Tint", -100, 100, self._current_params.get("tint", 0))
        wb_group.layout().addWidget(self.temp_slider); wb_group.layout().addWidget(self.tint_slider); controls_layout.addWidget(wb_group)

        tone_group = self._create_group_box("Tone")
        self.exposure_slider = LabeledSlider("Exposure", -100, 100, self._current_params.get("exposure", 0))
        self.contrast_slider = LabeledSlider("Contrast", -100, 100, self._current_params.get("contrast", 0))
        self.highlights_slider = LabeledSlider("Highlights", -100, 100, self._current_params.get("highlights", 0))
        self.shadows_slider = LabeledSlider("Shadows", -100, 100, self._current_params.get("shadows", 0))
        tone_group.layout().addWidget(self.exposure_slider); tone_group.layout().addWidget(self.contrast_slider); tone_group.layout().addWidget(self.highlights_slider); tone_group.layout().addWidget(self.shadows_slider); controls_layout.addWidget(tone_group)
        
        presence_group = self._create_group_box("Presence")
        self.vibrance_slider = LabeledSlider("Vibrance", -100, 100, self._current_params.get("vibrance", 0))
        self.saturation_slider = LabeledSlider("Saturation", -100, 100, self._current_params.get("saturation", 0))
        presence_group.layout().addWidget(self.vibrance_slider); presence_group.layout().addWidget(self.saturation_slider); controls_layout.addWidget(presence_group)

        controls_layout.addStretch(); scroll_area.setWidget(controls_widget); panel_layout.addWidget(scroll_area)
        button_layout = QHBoxLayout(); self.apply_btn = QPushButton("Apply Changes"); self.apply_btn.clicked.connect(self._on_accept)
        self.cancel_btn = QPushButton("Cancel"); self.cancel_btn.clicked.connect(self.rejected.emit)
        self.reset_btn = QPushButton("Reset"); self.reset_btn.clicked.connect(self._reset_params)
        button_layout.addWidget(self.reset_btn); button_layout.addStretch(); button_layout.addWidget(self.cancel_btn); button_layout.addWidget(self.apply_btn); panel_layout.addLayout(button_layout)
        
        self.temp_slider.value_changed.connect(lambda v: self._update_param("temp", v)); self.tint_slider.value_changed.connect(lambda v: self._update_param("tint", v))
        self.exposure_slider.value_changed.connect(lambda v: self._update_param("exposure", v)); self.contrast_slider.value_changed.connect(lambda v: self._update_param("contrast", v))
        self.highlights_slider.value_changed.connect(lambda v: self._update_param("highlights", v)); self.shadows_slider.value_changed.connect(lambda v: self._update_param("shadows", v))
        self.vibrance_slider.value_changed.connect(lambda v: self._update_param("vibrance", v)); self.saturation_slider.value_changed.connect(lambda v: self._update_param("saturation", v))
        return panel

    def _create_group_box(self, title):
        from PyQt6.QtWidgets import QGroupBox
        box = QGroupBox(title); box.setLayout(QVBoxLayout()); box.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; border: 1px solid #404040; border-radius: 5px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }")
        return box
    def _update_param(self, name, value): self._current_params[name] = value; self.update_preview()
    def _on_accept(self): self.accepted.emit(self._current_params)
    def _reset_params(self):
        self._current_params = self._initial_params.copy()
        self.temp_slider.setValue(self._current_params.get("temp", 0)); self.tint_slider.setValue(self._current_params.get("tint", 0))
        self.exposure_slider.setValue(self._current_params.get("exposure", 0)); self.contrast_slider.setValue(self._current_params.get("contrast", 0))
        self.highlights_slider.setValue(self._current_params.get("highlights", 0)); self.shadows_slider.setValue(self._current_params.get("shadows", 0))
        self.vibrance_slider.setValue(self._current_params.get("vibrance", 0)); self.saturation_slider.setValue(self._current_params.get("saturation", 0))
        self.update_preview()
    def update_preview(self):
        if self._original_pixmap is None: return
        preview_pixmap = self._original_pixmap.scaled(1280, 1280, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
        pil_image = qpixmap_to_pil_image(preview_pixmap)
        processed_image = self._apply_effects(pil_image, self._current_params)
        final_pixmap = pil_image_to_qpixmap(processed_image); self.preview.set_pixmap(final_pixmap); QApplication.processEvents()
    @staticmethod
    def _apply_effects(pil_image, params):
        img = pil_image.convert("RGB")
        if (val := params.get("exposure", 0)) != 0: img = ImageEnhance.Brightness(img).enhance(1 + val / 100.0)
        if (val := params.get("contrast", 0)) != 0: img = ImageEnhance.Contrast(img).enhance(1 + val / 100.0)
        if (temp := params.get("temp", 0)) != 0 or (tint := params.get("tint", 0)) != 0:
            r, g, b = img.split(); r = r.point(lambda i: i * (1 + temp / 200.0)); b = b.point(lambda i: i * (1 - temp / 200.0)); g = g.point(lambda i: i * (1 - tint / 200.0)); img = Image.merge("RGB", (r, g, b))
        if (val := params.get("saturation", 0)) != 0: img = ImageEnhance.Color(img).enhance(1 + val / 100.0)
        if (highlights := params.get("highlights", 0)) != 0 or (shadows := params.get("shadows", 0)) != 0:
            img_arr = np.array(img, dtype=np.float32) / 255.0; luminance = 0.299 * img_arr[..., 0] + 0.587 * img_arr[..., 1] + 0.114 * img_arr[..., 2]
            if highlights != 0: img_arr += (np.clip((luminance - 0.5) * 2, 0, 1) ** 2)[..., np.newaxis] * (highlights / 100.0)
            if shadows != 0: img_arr += (np.clip((0.5 - luminance) * 2, 0, 1) ** 2)[..., np.newaxis] * (shadows / 100.0)
            img = Image.fromarray(np.clip(img_arr * 255.0, 0, 255).astype(np.uint8))
        return img

# --- نود اصلی استودیو ---
@register_node("Color Studio")
class ColorStudioNode(BaseNode):
    def __init__(self, view):
        super().__init__("Color Studio", view)
        self.width = 250; self.add_socket("In", is_output=False, socket_type='IMAGE'); self.add_socket("Out", is_output=True, socket_type='IMAGE')
        self.params = { "temp": 0, "tint": 0, "exposure": 0, "contrast": 0, "highlights": 0, "shadows": 0, "vibrance": 0, "saturation": 0 }
        self.create_controls(); self.height = self.title_height + 70

    def create_controls(self):
        self.button = QPushButton("Open Studio"); self.button.setStyleSheet("QPushButton { background-color: #059669; color: white; border: none; padding: 8px; border-radius: 5px; } QPushButton:hover { background-color: #047857; }")
        self.button.clicked.connect(self.open_studio); proxy = QGraphicsProxyWidget(self); proxy.setWidget(self.button)
        proxy.setPos((self.width - self.button.sizeHint().width()) / 2, self.title_height + 15)
        
    def open_studio(self):
        """رفتار دو بار کلیک را بازنویسی می‌کند تا استودیو باز شود."""
        input_pixmap = self.get_input_data(0)
        if not isinstance(input_pixmap, QPixmap) or input_pixmap.isNull(): print("Color Studio needs an input image."); return
        studio_widget = ColorStudioWidget(input_pixmap, self.params)
        # از پنجره اصلی می‌خواهد که این ویجت را نمایش دهد
        self.view.scene().parent_window.show_fullscreen_widget(studio_widget, self)

    def on_studio_accepted(self, new_params):
        """زمانی که کاربر تغییرات را در استودیو تایید می‌کند، فراخوانی می‌شود."""
        self.params = new_params; self.clear_cache(); self.view.scene().update_graph()

    def get_parameters(self): return self.params
    def boundingRect(self): return QRectF(0, 0, self.width, self.height)
    def paint(self, painter, option, widget=None):
        painter.setBrush(QColor("#065f46")); painter.setPen(self.pen); painter.drawRoundedRect(self.boundingRect(), 5, 5)
        title_path = QPainterPath(); title_path.addRoundedRect(0, 0, self.width, self.title_height, 5, 5); title_path.addRect(0, self.title_height - 5, self.width, 5)
        painter.setBrush(QColor("#064e3b")); painter.setPen(Qt.PenStyle.NoPen); painter.drawPath(title_path)
    def compute(self):
        input_pixmap = self.get_input_data(0)
        if isinstance(input_pixmap, QPixmap):
            image = qpixmap_to_pil_image(input_pixmap); processed_image = ColorStudioWidget._apply_effects(image, self.params)
            self.output_data = pil_image_to_qpixmap(processed_image)
        else:
            self.output_data = None

