import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import Qt, QDate, QPointF, QLineF, QUrl, QSize
from PyQt6.QtGui import QDesktopServices, QFont, QPainter, QPainterPath, QPen, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QFileDialog,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from database import DatabaseManager

LBS_PER_STONE = 14


def nearest_saturday() -> date:
    today = date.today()
    distance = (5 - today.weekday()) % 7
    return today + timedelta(days=distance)


def lbs_to_stone_lbs(lbs: float) -> tuple[int, float]:
    stone = int(lbs // LBS_PER_STONE)
    remainder = round(lbs - stone * LBS_PER_STONE, 1)
    if remainder >= LBS_PER_STONE:
        stone += 1
        remainder -= LBS_PER_STONE
    return stone, remainder


def format_lbs_as_stone(lbs: float) -> str:
    stone, remainder = lbs_to_stone_lbs(lbs)
    return f"{stone} st {remainder:.1f} lb"


class WeightEditDialog(QDialog):
    def __init__(self, existing_lbs: float | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edit Weight')
        self.stone_input = QSpinBox()
        self.stone_input.setRange(4, 60)
        self.stone_input.setSuffix(' st')
        self.lbs_input = QDoubleSpinBox()
        self.lbs_input.setRange(0.0, 13.9)
        self.lbs_input.setDecimals(1)
        self.lbs_input.setSuffix(' lb')
        if existing_lbs is not None:
            s, r = lbs_to_stone_lbs(existing_lbs)
            self.stone_input.setValue(s)
            self.lbs_input.setValue(r)
        layout = QFormLayout(self)
        layout.addRow('Stone:', self.stone_input)
        layout.addRow('Pounds:', self.lbs_input)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_lbs(self) -> float:
        return float(self.stone_input.value() * LBS_PER_STONE + self.lbs_input.value())


class ThresholdEditDialog(QDialog):
    def __init__(self, threshold: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edit Threshold')
        self.threshold = threshold
        self.label_input = QLineEdit(threshold['label'])
        self.weight_input = QDoubleSpinBox()
        self.weight_input.setRange(30.0, 400.0)
        self.weight_input.setDecimals(1)
        self.weight_input.setValue(float(threshold['target_weight']))
        self.weight_input.setSuffix(' lb')
        self.reward_input = QDoubleSpinBox()
        self.reward_input.setRange(0.0, 1000.0)
        self.reward_input.setDecimals(1)
        self.reward_input.setValue(float(threshold['reward_amount']))
        layout = QFormLayout(self)
        layout.addRow('Label:', self.label_input)
        layout.addRow('Target weight:', self.weight_input)
        layout.addRow('Reward amount (£):', self.reward_input)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_values(self) -> tuple[str, float, float]:
        return (
            self.label_input.text().strip(),
            float(self.weight_input.value()),
            float(self.reward_input.value()),
        )


class RewardItemEditDialog(QDialog):
    def __init__(self, item: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Edit Reward Item')
        self.item = item
        self.name_input = QLineEdit(item['name'])
        self.price_input = QDoubleSpinBox()
        self.price_input.setRange(0.0, 500.0)
        self.price_input.setDecimals(2)
        self.price_input.setValue(float(item['price']))
        self.link_input = QLineEdit(item.get('link', ''))
        self.image_input = QLineEdit(item.get('image', ''))
        browse_button = QPushButton('Browse...')
        browse_button.clicked.connect(self.on_browse_image)
        img_layout = QHBoxLayout()
        img_layout.setContentsMargins(0, 0, 0, 0)
        img_layout.addWidget(self.image_input)
        img_layout.addWidget(browse_button)
        layout = QFormLayout(self)
        layout.addRow('Name:', self.name_input)
        layout.addRow('Price (£):', self.price_input)
        layout.addRow('Link:', self.link_input)
        layout.addRow('Image:', img_layout)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def on_browse_image(self) -> None:
        fname, _ = QFileDialog.getOpenFileName(self, 'Select image', '', 'Images (*.png *.jpg *.jpeg *.bmp)')
        if fname:
            self.image_input.setText(fname)

    def get_values(self) -> tuple[str, float, str, str]:
        return (
            self.name_input.text().strip(),
            float(self.price_input.value()),
            self.link_input.text().strip(),
            self.image_input.text().strip(),
        )


class WeightGraphWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.weights = []
        self.setMinimumHeight(220)

    def set_weights(self, weights):
        self.weights = weights
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), Qt.GlobalColor.white)

        if len(self.weights) < 2:
            painter.setPen(Qt.GlobalColor.black)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, 'Add at least two Saturday entries to see a trend graph')
            return

        left_margin = 40
        right_margin = 20
        top_margin = 20
        bottom_margin = 40
        width = self.width() - left_margin - right_margin
        height = self.height() - top_margin - bottom_margin

        values = [entry['weight'] for entry in self.weights]
        min_weight = min(values) - 1.0
        max_weight = max(values) + 1.0
        value_range = max_weight - min_weight
        if value_range <= 0:
            value_range = 1.0

        points = []
        for index, entry in enumerate(self.weights):
            x = left_margin + (width * index / (len(self.weights) - 1))
            y = top_margin + height * (1.0 - (entry['weight'] - min_weight) / value_range)
            points.append(QPointF(x, y))

        painter.setPen(QPen(Qt.GlobalColor.lightGray, 1, Qt.PenStyle.DashLine))
        for step in range(5):
            y = top_margin + height * step / 4
            painter.drawLine(QLineF(left_margin, y, left_margin + width, y))

        painter.setPen(QPen(Qt.GlobalColor.blue, 2))
        path = QPainterPath()
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        painter.drawPath(path)

        painter.setPen(QPen(Qt.GlobalColor.darkBlue, 8))
        for point in points:
            painter.drawPoint(point)

        painter.setPen(Qt.GlobalColor.black)
        painter.setFont(QFont('Arial', 9))
        for index, entry in enumerate(self.weights):
            x = left_margin + (width * index / (len(self.weights) - 1))
            painter.drawText(int(x - 20), int(top_margin + height + 20), entry['date'].strftime('%d %b'))

        painter.drawText(6, int(top_margin + 12), f'{max_weight:.1f} lb')
        painter.drawText(6, int(top_margin + height + 4), f'{min_weight:.1f} lb')


class RewardSelectionDialog(QDialog):
    def __init__(self, threshold, items, preselected_item_ids=None, parent=None):
        super().__init__(parent)
        self.threshold = threshold
        self.items = items
        self.checkboxes = []
        self.total = 0.0
        self.action = 'save'
        self.preselected_item_ids = preselected_item_ids or []
        self.setWindowTitle('Select Reward Items')
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        instruction = QLabel(
            f"Choose reward items for the {self.threshold['label']} tier."
        )
        instruction.setWordWrap(True)
        layout.addWidget(instruction)

        self.total_label = QLabel('Selected total: £0.00')
        layout.addWidget(self.total_label)

        for item in self.items:
            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            if item.get('image'):
                try:
                    pix = QPixmap(item['image'])
                    if not pix.isNull():
                        pic = QLabel()
                        pic.setPixmap(pix.scaled(QSize(64, 64), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                        row_layout.addWidget(pic)
                except Exception:
                    pass
            label_text = f"{item['name']} — £{item['price']:.2f}"
            if item.get('link'):
                label_text += f" — {item['link']}"
            checkbox = QCheckBox(label_text)
            checkbox.item_id = item['id']
            checkbox.item_price = item['price']
            checkbox.stateChanged.connect(self.update_total)
            if item['id'] in self.preselected_item_ids:
                checkbox.setChecked(True)
            row_layout.addWidget(checkbox)
            layout.addWidget(row_widget)
            self.checkboxes.append(checkbox)

        button_layout = QHBoxLayout()
        save_button = QPushButton('Save Selection')
        claim_button = QPushButton('Claim Now')
        cancel_button = QPushButton('Cancel')
        save_button.clicked.connect(self.accept_save)
        claim_button.clicked.connect(self.accept_claim)
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(save_button)
        button_layout.addWidget(claim_button)
        button_layout.addWidget(cancel_button)
        layout.addLayout(button_layout)

        self.update_total()

    def update_total(self):
        self.total = sum(cb.item_price for cb in self.checkboxes if cb.isChecked())
        self.total_label.setText(
            f"Selected total: £{self.total:.2f} / £{self.threshold['reward_amount']:.2f}"
        )
        self.total_label.setStyleSheet(
            'color: red;' if self.total > self.threshold['reward_amount'] else 'color: black;'
        )

    def accept_save(self):
        if self._validate_selection(allow_empty=False):
            self.action = 'save'
            self.accept()

    def accept_claim(self):
        if self._validate_selection(allow_empty=False):
            self.action = 'claim'
            self.accept()

    def _validate_selection(self, allow_empty: bool = True) -> bool:
        if self.total > self.threshold['reward_amount']:
            QMessageBox.warning(
                self,
                'Total too high',
                f'Selected items total £{self.total:.2f}, which exceeds the available £{self.threshold['reward_amount']:.2f}.',
            )
            return False
        if self.total <= 0 and not allow_empty:
            QMessageBox.warning(self, 'Select items', 'Please select at least one reward item.')
            return False
        return True

    def selected_item_ids(self):
        return [cb.item_id for cb in self.checkboxes if cb.isChecked()]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Weight Rewards Tracker')
        self.resize(980, 700)
        self.db = DatabaseManager()
        self.init_ui()
        self.refresh_all()

    def init_ui(self):
        tabs = QTabWidget()
        tabs.addTab(self.create_track_tab(), 'Track')
        tabs.addTab(self.create_rewards_tab(), 'Rewards')
        tabs.addTab(self.create_admin_tab(), 'Admin')

        self.setCentralWidget(tabs)

    def create_track_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        header = QLabel('Enter or edit weights for the current Saturday and up to 11 past Saturdays')
        header.setWordWrap(True)

        self.sat_table = QTableWidget(0, 3)
        self.sat_table.setHorizontalHeaderLabels(['Date', 'Weight', 'Actions'])
        self.sat_table.horizontalHeader().setSectionResizeMode(0, self.sat_table.horizontalHeader().ResizeMode.ResizeToContents)
        self.sat_table.horizontalHeader().setSectionResizeMode(1, self.sat_table.horizontalHeader().ResizeMode.Stretch)
        self.sat_table.horizontalHeader().setSectionResizeMode(2, self.sat_table.horizontalHeader().ResizeMode.ResizeToContents)
        self.sat_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.weight_graph = WeightGraphWidget()
        self.summary_label = QLabel('Enter two Saturdays to start tracking reward eligibility.')
        self.summary_label.setWordWrap(True)
        self.estimate_label = QLabel('Weekly progress estimate will appear here.')
        self.estimate_label.setWordWrap(True)

        layout.addWidget(header)
        layout.addWidget(self.sat_table)
        layout.addWidget(self.weight_graph)
        layout.addWidget(self.summary_label)
        layout.addWidget(self.estimate_label)
        self.populate_saturdays_table()
        return widget

    def get_saturdays_list(self, weeks: int = 12):
        start = nearest_saturday()
        return [start - timedelta(weeks=i) for i in range(weeks)]

    def populate_saturdays_table(self):
        dates = self.get_saturdays_list(12)
        self.sat_table.setRowCount(len(dates))
        for row, d in enumerate(dates):
            date_item = QTableWidgetItem(d.strftime('%Y-%m-%d'))
            date_item.setData(Qt.ItemDataRole.UserRole, d.isoformat())
            date_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sat_table.setItem(row, 0, date_item)

            weight = self.db.get_weight_for_date(d)
            weight_text = format_lbs_as_stone(weight) if weight is not None else '—'
            weight_item = QTableWidgetItem(weight_text)
            weight_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.sat_table.setItem(row, 1, weight_item)

            action_widget = QWidget()
            h_layout = QHBoxLayout(action_widget)
            h_layout.setContentsMargins(0, 0, 0, 0)
            edit_btn = QPushButton('Edit' if weight is not None else 'Add')
            del_btn = QPushButton('Delete')
            edit_btn.clicked.connect(lambda _, dd=d: self.edit_weight_for_date(dd))
            del_btn.clicked.connect(lambda _, dd=d: self.delete_weight_for_date(dd))
            h_layout.addWidget(edit_btn)
            h_layout.addWidget(del_btn)
            self.sat_table.setCellWidget(row, 2, action_widget)

            is_future = d > date.today()
            if is_future:
                edit_btn.setEnabled(False)
                del_btn.setEnabled(False)
                edit_btn.setToolTip('Future Saturday entry is not available until that date arrives.')
                del_btn.setToolTip('You can only delete entries for Saturdays that have already occurred.')
            else:
                edit_btn.setEnabled(True)
                del_btn.setEnabled(weight is not None)

            # highlight current week only after it has arrived
            if d == nearest_saturday() and d <= date.today():
                for c in range(3):
                    item = self.sat_table.item(row, c)
                    if item:
                        item.setBackground(Qt.GlobalColor.lightGray)

    def create_rewards_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        self.threshold_table = QTableWidget(0, 4)
        self.threshold_table.setHorizontalHeaderLabels(['Threshold', 'Target', 'Reward', 'Status'])
        self.threshold_table.horizontalHeader().setSectionResizeMode(0, self.threshold_table.horizontalHeader().ResizeMode.Stretch)
        self.threshold_table.horizontalHeader().setSectionResizeMode(1, self.threshold_table.horizontalHeader().ResizeMode.ResizeToContents)
        self.threshold_table.horizontalHeader().setSectionResizeMode(2, self.threshold_table.horizontalHeader().ResizeMode.ResizeToContents)
        self.threshold_table.horizontalHeader().setSectionResizeMode(3, self.threshold_table.horizontalHeader().ResizeMode.ResizeToContents)
        self.threshold_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.threshold_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.threshold_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)

        self.pending_label = QLabel('No pending reward selections.')
        self.pending_label.setWordWrap(True)
        self.claim_table = QTableWidget(0, 4)
        self.claim_table.setHorizontalHeaderLabels(['Date', 'Threshold', 'Items', 'Status'])
        self.claim_table.horizontalHeader().setSectionResizeMode(0, self.claim_table.horizontalHeader().ResizeMode.ResizeToContents)
        self.claim_table.horizontalHeader().setSectionResizeMode(1, self.claim_table.horizontalHeader().ResizeMode.Stretch)
        self.claim_table.horizontalHeader().setSectionResizeMode(2, self.claim_table.horizontalHeader().ResizeMode.Stretch)
        self.claim_table.horizontalHeader().setSectionResizeMode(3, self.claim_table.horizontalHeader().ResizeMode.ResizeToContents)
        self.claim_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.open_reward_selection_button = QPushButton('Open reward selection')
        self.open_reward_selection_button.clicked.connect(self.on_open_reward_selection)
        self.continue_pending_button = QPushButton('Continue saved selection')
        self.continue_pending_button.clicked.connect(self.on_continue_pending_selection)
        self.delete_pending_button = QPushButton('Delete saved selection')
        self.delete_pending_button.clicked.connect(self.on_delete_pending_selection)
        button_row = QWidget()
        button_layout = QHBoxLayout(button_row)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addWidget(self.open_reward_selection_button)
        button_layout.addWidget(self.continue_pending_button)
        button_layout.addWidget(self.delete_pending_button)

        layout.addWidget(QLabel('Reward thresholds and status'))
        layout.addWidget(self.threshold_table)
        layout.addWidget(button_row)
        layout.addWidget(self.pending_label)
        layout.addWidget(QLabel('Claim history'))
        layout.addWidget(self.claim_table)
        return widget

    def create_admin_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)

        threshold_group = QGroupBox('Add Reward Threshold')
        threshold_layout = QFormLayout()
        self.threshold_name_input = QLineEdit()
        self.threshold_weight_input = QDoubleSpinBox()
        self.threshold_weight_input.setRange(30.0, 400.0)
        self.threshold_weight_input.setDecimals(1)
        # live conversion label to show stones and lbs
        self.threshold_weight_stone_label = QLabel(format_lbs_as_stone(float(self.threshold_weight_input.value())))
        def _on_threshold_weight_changed(val: float) -> None:
            self.threshold_weight_stone_label.setText(format_lbs_as_stone(float(val)))
        self.threshold_weight_input.valueChanged.connect(_on_threshold_weight_changed)
        self.threshold_reward_input = QDoubleSpinBox()
        self.threshold_reward_input.setRange(0.0, 1000.0)
        self.threshold_reward_input.setDecimals(1)
        self.add_threshold_button = QPushButton('Add Threshold')
        self.add_threshold_button.clicked.connect(self.on_add_threshold)
        threshold_layout.addRow('Label:', self.threshold_name_input)
        weight_row = QWidget()
        weight_row_layout = QHBoxLayout(weight_row)
        weight_row_layout.setContentsMargins(0, 0, 0, 0)
        weight_row_layout.addWidget(self.threshold_weight_input)
        weight_row_layout.addWidget(self.threshold_weight_stone_label)
        threshold_layout.addRow('Target weight (lbs):', weight_row)
        threshold_layout.addRow('Reward amount (£):', self.threshold_reward_input)
        threshold_layout.addRow('', self.add_threshold_button)
        threshold_group.setLayout(threshold_layout)

        item_group = QGroupBox('Add Reward Item')
        item_layout = QFormLayout()
        self.item_name_input = QLineEdit()
        self.item_price_input = QDoubleSpinBox()
        self.item_price_input.setRange(0.0, 500.0)
        self.item_price_input.setDecimals(2)
        self.item_link_input = QLineEdit()
        self.add_item_button = QPushButton('Add Item')
        self.add_item_button.clicked.connect(self.on_add_item)
        item_layout.addRow('Item name:', self.item_name_input)
        item_layout.addRow('Price (£):', self.item_price_input)
        self.item_image_input = QLineEdit()
        browse_image = QPushButton('Browse...')
        browse_image.clicked.connect(self.on_browse_item_image)
        img_layout = QHBoxLayout()
        img_layout.addWidget(self.item_image_input)
        img_layout.addWidget(browse_image)
        item_layout.addRow('Link:', self.item_link_input)
        item_layout.addRow('Image:', img_layout)
        item_layout.addRow('', self.add_item_button)
        item_group.setLayout(item_layout)

        self.admin_items_list = QListWidget()
        self.admin_items_list.itemDoubleClicked.connect(self.on_open_reward_link)
        self.thresholds_admin_list = QListWidget()
        edit_threshold_btn = QPushButton('Edit Selected Threshold')
        edit_threshold_btn.clicked.connect(self.on_edit_selected_threshold)
        delete_threshold_btn = QPushButton('Delete Selected Threshold')
        delete_threshold_btn.clicked.connect(self.on_delete_selected_threshold)
        edit_item_btn = QPushButton('Edit Selected Item')
        edit_item_btn.clicked.connect(self.on_edit_selected_item)
        delete_item_btn = QPushButton('Delete Selected Item')
        delete_item_btn.clicked.connect(self.on_delete_selected_item)

        self.threshold_buttons_widget = QWidget()
        threshold_buttons_layout = QHBoxLayout(self.threshold_buttons_widget)
        threshold_buttons_layout.setContentsMargins(0, 0, 0, 0)
        threshold_buttons_layout.addWidget(edit_threshold_btn)
        threshold_buttons_layout.addWidget(delete_threshold_btn)

        self.item_buttons_widget = QWidget()
        item_buttons_layout = QHBoxLayout(self.item_buttons_widget)
        item_buttons_layout.setContentsMargins(0, 0, 0, 0)
        item_buttons_layout.addWidget(edit_item_btn)
        item_buttons_layout.addWidget(delete_item_btn)

        layout.addWidget(threshold_group)
        layout.addWidget(QLabel('Reward thresholds (admin only)'))
        layout.addWidget(self.thresholds_admin_list)
        layout.addWidget(self.threshold_buttons_widget)
        layout.addWidget(item_group)
        layout.addWidget(QLabel('Reward items available (double-click to open link)'))
        layout.addWidget(self.admin_items_list)
        layout.addWidget(self.item_buttons_widget)
        return widget

    def refresh_all(self) -> None:
        self.refresh_recent_weights()
        self.refresh_thresholds()
        self.refresh_claims()
        self.refresh_admin_items()
        self.refresh_admin_thresholds()
        self.refresh_reward_buttons()
        # refresh the Saturdays table and summary after other updates
        try:
            self.populate_saturdays_table()
        except Exception:
            pass
        self.update_summary()

    def refresh_recent_weights(self) -> None:
        recent = self.db.get_recent_weights(limit=16)
        # update graph only (recent table removed in favor of Saturdays list)
        self.weight_graph.set_weights(list(reversed(recent)))

    def refresh_thresholds(self) -> None:
        thresholds = self.db.get_thresholds()
        self.threshold_table.setRowCount(len(thresholds))
        for row_index, threshold in enumerate(thresholds):
            self.threshold_table.setItem(row_index, 0, QTableWidgetItem(threshold['label']))
            self.threshold_table.setItem(row_index, 1, QTableWidgetItem(format_lbs_as_stone(threshold['target_weight'])))
            self.threshold_table.setItem(row_index, 2, QTableWidgetItem(f"£{threshold['reward_amount']:.2f}"))
            status_text = 'Reached' if threshold['reached'] else 'Open'
            status_item = QTableWidgetItem(status_text)
            if threshold['reached']:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            self.threshold_table.setItem(row_index, 3, status_item)

    def refresh_claims(self) -> None:
        claims = self.db.get_claims()
        self.claim_table.setRowCount(len(claims))
        for row_index, claim in enumerate(claims):
            self.claim_table.setItem(row_index, 0, QTableWidgetItem(claim['claimed_at']))
            self.claim_table.setItem(row_index, 1, QTableWidgetItem(claim['threshold_label']))
            item_names = ', '.join(
                f"{item['name']} (£{item['price']:.2f})" + (f" [{item['link']} ]" if item.get('link') else '')
                for item in claim['items']
            )
            self.claim_table.setItem(row_index, 2, QTableWidgetItem(item_names))
            status_item = QTableWidgetItem(claim.get('status', 'claimed').capitalize())
            if claim.get('status') == 'draft':
                status_item.setForeground(Qt.GlobalColor.darkYellow)
            elif claim.get('status') == 'claimed':
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            self.claim_table.setItem(row_index, 3, status_item)

    def refresh_reward_buttons(self) -> None:
        eligible = self.db.get_eligible_threshold()
        pending = self.db.get_pending_claims()
        self.open_reward_selection_button.setEnabled(eligible is not None)
        self.continue_pending_button.setEnabled(bool(pending))
        self.delete_pending_button.setEnabled(bool(pending))

    def refresh_admin_items(self) -> None:
        self.admin_items_list.clear()
        for item in self.db.get_reward_items(active_only=False):
            status = 'Active' if item['active'] else 'Inactive'
            item_text = f"{item['name']} — £{item['price']:.2f} — {status}"
            if item.get('link'):
                item_text += f" — {item['link']}"
            if item.get('image'):
                item_text += f" — [image]"
            list_item = QListWidgetItem(item_text)
            # store the full item dict for later actions
            list_item.setData(Qt.ItemDataRole.UserRole, item)
            self.admin_items_list.addItem(list_item)

    def refresh_admin_thresholds(self) -> None:
        self.thresholds_admin_list.clear()
        for threshold in self.db.get_thresholds():
            status = 'Reached' if threshold['reached'] else 'Open'
            item_text = f"{threshold['label']} — {format_lbs_as_stone(threshold['target_weight'])} — £{threshold['reward_amount']:.2f} — {status}"
            list_item = QListWidgetItem(item_text)
            list_item.setData(Qt.ItemDataRole.UserRole, threshold)
            self.thresholds_admin_list.addItem(list_item)

    def on_edit_selected_threshold(self) -> None:
        cur = self.thresholds_admin_list.currentItem()
        if not cur:
            QMessageBox.warning(self, 'No threshold selected', 'Please select a threshold to edit.')
            return
        threshold = cur.data(Qt.ItemDataRole.UserRole)
        if not isinstance(threshold, dict):
            return
        dialog = ThresholdEditDialog(threshold, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            label, target_weight, reward_amount = dialog.get_values()
            if not label:
                QMessageBox.warning(self, 'Missing label', 'Please enter a threshold name.')
                return
            try:
                self.db.update_threshold(threshold['id'], label, target_weight, reward_amount)
            except Exception as exc:
                QMessageBox.warning(self, 'Unable to update threshold', str(exc))
            self.refresh_all()

    def on_edit_selected_item(self) -> None:
        cur = self.admin_items_list.currentItem()
        if not cur:
            QMessageBox.warning(self, 'No item selected', 'Please select a reward item to edit.')
            return
        item = cur.data(Qt.ItemDataRole.UserRole)
        if not isinstance(item, dict):
            return
        dialog = RewardItemEditDialog(item, parent=self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            name, price, link, image = dialog.get_values()
            if not name:
                QMessageBox.warning(self, 'Missing name', 'Please enter an item name.')
                return
            try:
                self.db.update_reward_item(item['id'], name, price, link, image)
            except Exception as exc:
                QMessageBox.warning(self, 'Unable to update item', str(exc))
            self.refresh_all()

    def on_open_reward_selection(self) -> None:
        eligible = self.db.get_eligible_threshold()
        if eligible is None:
            QMessageBox.information(self, 'No available reward', 'No reward tier is currently eligible. Enter two qualifying Saturdays first.')
            return
        draft = self.db.get_draft_claim(eligible['id'])
        preselected = draft['item_ids'] if draft else []
        self._run_reward_dialog(eligible, preselected)

    def on_continue_pending_selection(self) -> None:
        pending = self.db.get_pending_claims()
        if not pending:
            QMessageBox.information(self, 'No pending selection', 'There is no saved reward selection to continue.')
            return
        pending_claim = pending[0]
        threshold_id = pending_claim.get('threshold_id')
        if threshold_id is None:
            QMessageBox.warning(self, 'Missing threshold', 'The saved reward threshold could not be found.')
            return
        threshold = next((t for t in self.db.get_thresholds() if t['id'] == threshold_id), None)
        if threshold is None:
            QMessageBox.warning(self, 'Missing threshold', 'The saved reward threshold could not be found.')
            return
        draft = self.db.get_draft_claim(threshold_id)
        preselected = draft['item_ids'] if draft else []
        self._run_reward_dialog(threshold, preselected)

    def on_delete_pending_selection(self) -> None:
        pending = self.db.get_pending_claims()
        if not pending:
            QMessageBox.information(self, 'No pending selection', 'There is no saved reward selection to delete.')
            return
        pending_claim = pending[0]
        claim_id = pending_claim.get('claim_id')
        if claim_id is None:
            QMessageBox.warning(self, 'Unable to delete', 'Unable to identify the pending reward selection.')
            return
        if QMessageBox.question(
            self,
            'Delete saved selection',
            'Delete the saved reward selection? This cannot be undone.',
        ) != QMessageBox.StandardButton.Yes:
            return
        self.db.delete_draft_claim(claim_id)
        self.refresh_all()

    def _run_reward_dialog(self, threshold: dict, preselected_item_ids: list[int]) -> None:
        dialog = RewardSelectionDialog(
            threshold,
            self.db.get_reward_items(),
            preselected_item_ids=preselected_item_ids,
            parent=self,
        )
        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected_item_ids = dialog.selected_item_ids()
            if dialog.action == 'save':
                self.db.save_reward_selection(threshold['id'], selected_item_ids)
                QMessageBox.information(
                    self,
                    'Selection saved',
                    f"Your reward selection for '{threshold['label']}' has been saved. You can claim it later from the Rewards tab.",
                )
            else:
                self.db.finalize_reward_claim(threshold['id'], selected_item_ids)
                QMessageBox.information(
                    self,
                    'Reward claimed',
                    f"Your reward tier '{threshold['label']}' has been claimed and locked. Selected items are now inactive.",
                )
            self.refresh_all()

    def update_summary(self) -> None:
        eligible = self.db.get_eligible_threshold()
        pending = self.db.get_pending_claims()
        if pending:
            self.pending_label.setText(
                f"There is a saved reward selection for '{pending[0]['threshold_label']}'. Open the Rewards tab to complete or adjust it."
            )
        else:
            self.pending_label.setText('No pending reward selections.')

        if eligible is not None:
            draft = self.db.get_draft_claim(eligible['id'])
            message = (
                f"Congratulations — you qualified for the '{eligible['label']}' reward tier!\n"
                f"You can claim up to £{eligible['reward_amount']:.2f} in reward items."
            )
            if draft:
                message += "\nYou have a saved selection ready to claim in the Rewards tab."
            else:
                message += "\nYou have an unclaimed reward available — open the Rewards tab to select items."
            self.summary_label.setText(message)
        else:
            next_threshold = self.db.get_next_unreached_threshold()
            if next_threshold is None:
                self.summary_label.setText('All reward tiers have been claimed. Great progress!')
            else:
                self.summary_label.setText(
                    f"No current reward claim available. Next target is '{next_threshold['label']}' at {format_lbs_as_stone(next_threshold['target_weight'])}."
                )

        trend = self.db.calculate_weight_trend()
        if trend is None:
            self.estimate_label.setText('Enter at least two Saturday entries to see your progress trend.')
        elif trend < 0:
            next_threshold = self.db.get_next_unreached_threshold()
            if next_threshold is None:
                self.estimate_label.setText('No unreached thresholds remain.')
            else:
                current_weights = self.db.get_saturday_weights()
                current_weight = current_weights[-1]['weight']
                remaining = current_weight - next_threshold['target_weight']
                if remaining <= 0:
                    self.estimate_label.setText(
                        'You are below the next threshold and may qualify after another Saturday entry.'
                    )
                else:
                    weeks = max(1, int((remaining / -trend) + 0.999))
                    self.estimate_label.setText(
                        f"Trend shows about {weeks} week(s) to reach {next_threshold['label']} if the current pace continues."
                    )
        else:
            self.estimate_label.setText(
                'Your recent Saturday trend is flat or rising. Enter additional weight entries and keep moving toward the next reward target.'
            )

    def on_save_weight(self) -> None:
        selected_date = self.date_edit.date().toPyDate()
        if selected_date.weekday() != 5:
            QMessageBox.warning(self, 'Invalid date', 'Please select a Saturday for the entry.')
            return

        weight = float(self.stone_input.value() * LBS_PER_STONE + self.lbs_input.value())
        self.db.add_weight_entry(selected_date, weight)
        self.refresh_all()

        eligible = self.db.get_eligible_threshold()
        if eligible is not None:
            draft = self.db.get_draft_claim(eligible['id'])
            preselected = draft['item_ids'] if draft else []
            dialog = RewardSelectionDialog(
                eligible,
                self.db.get_reward_items(),
                preselected_item_ids=preselected,
                parent=self,
            )
            if dialog.exec() == QDialog.DialogCode.Accepted:
                selected_item_ids = dialog.selected_item_ids()
                if dialog.action == 'save':
                    self.db.save_reward_selection(eligible['id'], selected_item_ids)
                    QMessageBox.information(
                        self,
                        'Selection saved',
                        f"Your reward selection for '{eligible['label']}' has been saved. You can claim it later from the Rewards tab.",
                    )
                else:
                    self.db.finalize_reward_claim(eligible['id'], selected_item_ids)
                    QMessageBox.information(
                        self,
                        'Reward claimed',
                        f"Your reward tier '{eligible['label']}' has been claimed and locked. Selected items are now inactive.",
                    )
                self.refresh_all()

    def on_add_threshold(self) -> None:
        label = self.threshold_name_input.text().strip()
        target_weight = float(self.threshold_weight_input.value())
        reward_amount = float(self.threshold_reward_input.value())
        if not label:
            QMessageBox.warning(self, 'Missing label', 'Please enter a name for the threshold.')
            return
        self.db.add_threshold(label, target_weight, reward_amount)
        self.threshold_name_input.clear()
        self.threshold_weight_input.setValue(30.0)
        self.threshold_reward_input.setValue(0.0)
        self.refresh_all()

    def on_add_item(self) -> None:
        name = self.item_name_input.text().strip()
        price = float(self.item_price_input.value())
        link = self.item_link_input.text().strip()
        image = self.item_image_input.text().strip()
        if not name:
            QMessageBox.warning(self, 'Missing item', 'Please enter a reward item name.')
            return
        self.db.add_reward_item(name, price, link, image)
        self.item_name_input.clear()
        self.item_price_input.setValue(0.0)
        self.item_link_input.clear()
        self.item_image_input.clear()
        self.refresh_all()

    def on_open_reward_link(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(data, dict):
            link = data.get('link')
        else:
            link = data
        if link:
            QDesktopServices.openUrl(QUrl(link))

    def on_browse_item_image(self) -> None:
        fname, _ = QFileDialog.getOpenFileName(self, 'Select image', '', 'Images (*.png *.jpg *.jpeg *.bmp)')
        if fname:
            self.item_image_input.setText(fname)

    def on_delete_selected_item(self) -> None:
        cur = self.admin_items_list.currentItem()
        if not cur:
            return
        item = cur.data(Qt.ItemDataRole.UserRole)
        if not item:
            return
        if QMessageBox.question(self, 'Delete item', f"Delete '{item['name']}'? This cannot be undone.") != QMessageBox.StandardButton.Yes:
            return
        self.db.remove_reward_item(item['id'])
        self.refresh_all()

    def on_delete_selected_threshold(self) -> None:
        cur = self.thresholds_admin_list.currentItem()
        if not cur:
            QMessageBox.warning(self, 'No threshold selected', 'Please select a threshold from the admin list first.')
            return
        threshold = cur.data(Qt.ItemDataRole.UserRole)
        if not isinstance(threshold, dict):
            return
        thr_label = threshold['label']
        if QMessageBox.question(self, 'Delete threshold', f"Delete threshold '{thr_label}' and associated claims? This cannot be undone.") != QMessageBox.StandardButton.Yes:
            return
        self.db.remove_threshold(threshold['id'])
        self.refresh_all()
        self.refresh_all()

    def edit_weight_for_date(self, entry_date: date) -> None:
        if entry_date > date.today():
            QMessageBox.warning(self, 'Future Saturday', 'You can only enter a weight on or after the Saturday date has arrived.')
            return
        existing = self.db.get_weight_for_date(entry_date)
        dlg = WeightEditDialog(existing, parent=self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            lbs = dlg.get_lbs()
            self.db.add_weight_entry(entry_date, lbs)
            self.refresh_all()

    def delete_weight_for_date(self, entry_date: date) -> None:
        if entry_date > date.today():
            QMessageBox.warning(self, 'Future Saturday', 'There is no weight entry to remove for a future Saturday.')
            return
        if QMessageBox.question(self, 'Delete weight', f"Remove weight entry for {entry_date.isoformat()}?") != QMessageBox.StandardButton.Yes:
            return
        self.db.remove_weight_entry(entry_date)
        self.refresh_all()


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
