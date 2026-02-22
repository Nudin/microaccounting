#!/usr/bin/env python
import os
import re
import shutil
import signal
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Set

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import (QAbstractTableModel, QByteArray, QCoreApplication,
                          QDate, QLibraryInfo, QLocale, QSettings,
                          QSharedMemory, Qt, QTimer, QTranslator, pyqtSignal)
from PyQt6.QtGui import QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDateEdit,
                             QDialog, QDialogButtonBox, QDockWidget,
                             QDoubleSpinBox, QFormLayout, QHBoxLayout,
                             QHeaderView, QInputDialog, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPushButton,
                             QStyledItemDelegate, QToolBar, QVBoxLayout,
                             QWidget)

from main_window import Ui_MainWindow

matplotlib.use("QtAgg")

window = None

APPNAME = "microaccounting"


def tr(text: str, context="") -> str:
    return QCoreApplication.translate(context, text)


class ColumnsMeta(type):
    def __getitem__(cls, x):
        return cls.displayOrder[x]

    def __len__(cls):
        return len(cls.displayOrder)


class Columns(metaclass=ColumnsMeta):
    # Internal keys (stable, not translated)
    Date = "date"
    Shop = "shop"
    Category = "category"
    Value = "value"
    Description = "description"

    # CSV storage columns (keep stable keys)
    displayOrder = [Date, Category, Shop, Description, Value]

    # Source texts for translation
    _displayTexts = {
        Date: tr("Date"),
        Shop: tr("Shop"),
        Category: tr("Category"),
        Value: tr("Amount"),
        Description: tr("Description"),
    }

    @classmethod
    def displayText(cls, column):
        return tr(cls._displayTexts[column])

    @classmethod
    def index(cls, column):
        return cls.displayOrder.index(column)


def find_i18n_dir(appname: str) -> Path:
    """
    Resolve i18n directory using a fallback chain (first existing wins):
      1) alongside this file: <module_dir>/i18n
      2) XDG user data dir:    $XDG_DATA_HOME/<appname>/i18n  (or ~/.local/share)
      3) system-wide:          /usr/local/share/<appname>/i18n
      4) system-wide:          /usr/share/<appname>/i18n

    If none exist, returns the first option (alongside this file) as a default.
    """
    module_i18n = Path(__file__).resolve().parent / "i18n"

    xdg_data_home = Path(
        os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
    )
    user_i18n = xdg_data_home / appname / "i18n"

    local_i18n = Path("/usr/local/share") / appname / "i18n"
    system_i18n = Path("/usr/share") / appname / "i18n"

    for candidate in (module_i18n, user_i18n, local_i18n, system_i18n):
        if candidate.is_dir():
            return candidate

    # Fallback default when nothing exists yet
    return module_i18n


def install_translators(app: QApplication, ui_locale: QLocale | None = None) -> None:
    """
    Install Qt base translations + app translations.

    App translations are expected as:
      i18n/microaccounting_<locale>.qm
    """
    if ui_locale is None:
        ui_locale = QLocale.system()

    # 1) Qt (widgets, dialogs etc.)
    qt_translator = QTranslator(app)
    qt_translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if qt_translator.load(ui_locale, "qtbase", "_", qt_translations_path):
        app.installTranslator(qt_translator)

    # 2) App
    app_translator = QTranslator(app)
    i18n_dir = find_i18n_dir(APPNAME)
    if app_translator.load(ui_locale, APPNAME, "_", str(i18n_dir)):
        app.installTranslator(app_translator)


def sigint_handler(*args):
    """Handler for the SIGINT signal."""
    sys.stderr.write("\r")
    if window:
        window.close()


class ComboBoxDelegate(QStyledItemDelegate):
    def __init__(self, model, candidate_generator):
        super().__init__()
        self.model = model
        self.candidate_generator = candidate_generator

    def createEditor(self, parent, option, index):
        comboBox = QComboBox(parent)
        comboBox.addItems(self.candidate_generator())
        comboBox.setEditable(True)
        return comboBox

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        editor.setCurrentText(str(value))

    def setModelData(self, editor, model, index):
        model.setData(index, editor.currentText(), Qt.ItemDataRole.EditRole)


class DateDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        editor = QDateEdit(parent)
        editor.setCalendarPopup(True)
        # Prefer locale format
        editor.setDisplayFormat(QLocale().dateFormat(QLocale.FormatType.ShortFormat))
        return editor

    def setEditorData(self, editor, index):
        date = index.model().data(index, Qt.ItemDataRole.EditRole)
        editor.setDate(QDate.fromString(date, "yyyy-MM-dd"))

    def setModelData(self, editor, model, index):
        model.setData(
            index, editor.date().toString("yyyy-MM-dd"), Qt.ItemDataRole.EditRole
        )

    def displayText(self, value, locale):
        date = QDate.fromString(value, "yyyy-MM-dd")
        return locale.toString(date, QLocale.FormatType.ShortFormat)


class CurrencyDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, currency="€"):
        super().__init__(parent)
        self.currency = currency

    def createEditor(self, parent, option, index):
        editor = QDoubleSpinBox(parent)
        editor.setSuffix("\u2009" + self.currency)
        editor.setDecimals(2)
        editor.setMinimum(0.00)
        editor.setMaximum(1000000.00)
        editor.setAlignment(Qt.AlignmentFlag.AlignRight)
        return editor

    def setEditorData(self, editor, index):
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        editor.setValue(float(value))

    def setModelData(self, editor, model, index):
        value = editor.value()
        model.setData(index, value, Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(self, editor, option, index):
        editor.setGeometry(option.rect)


class MyTableModel(QAbstractTableModel):
    data_changed: bool

    def __init__(self, file_path, currency="€"):
        super(MyTableModel, self).__init__()
        self.file_path = file_path
        self.currency = currency
        self.locale = QLocale()
        self.load_csv()

    def load_csv(self, file_path=None):
        if file_path is None:
            file_path = self.file_path
        if Path(file_path).is_file():
            self._data = pd.read_csv(file_path, keep_default_na=False).sort_values(
                by=Columns.Date, ignore_index=True
            )
        else:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            self._data = pd.DataFrame(columns=Columns.displayOrder)
        self.data_changed = False

    def save_csv(self, file_path=None):
        if file_path is None:
            file_path = self.file_path
        self.create_backup(file_path)
        self._data.to_csv(file_path, index=False)
        self.data_changed = False

    def create_backup(self, file_path: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file_path = f"{file_path}_{timestamp}.bak"
        if Path(file_path).is_file():
            shutil.copyfile(file_path, backup_file_path)

    def rowCount(self, index=None):
        return len(self._data)

    def columnCount(self, index=None):
        return len(self._data.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        data = self._data.iloc[index.row()][Columns[index.column()]]
        if role == Qt.ItemDataRole.DisplayRole:
            if not isinstance(data, str):
                data = self.locale.toString(data, "f", 2) + "\u2009" + self.currency
            return data
        elif role == Qt.ItemDataRole.TextAlignmentRole:
            if index.column() == Columns.index(Columns.Value):
                return Qt.AlignmentFlag.AlignRight
        if role == Qt.ItemDataRole.EditRole:
            if not isinstance(data, str):
                data = float(data)
            return data

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role == Qt.ItemDataRole.EditRole:
            old_val = self._data.loc[index.row(), Columns[index.column()]]
            if old_val == value:
                return True
            self._data.loc[index.row(), Columns[index.column()]] = value
            self.dataChanged.emit(
                index, index, (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole)
            )
            self.data_changed = True
            return True
        return False

    def insertRow(self, date, description, shop, category, value):
        new = pd.DataFrame(
            [
                {
                    Columns.Date: date,
                    Columns.Shop: shop,
                    Columns.Description: description,
                    Columns.Value: value,
                    Columns.Category: category,
                }
            ]
        )
        self._data = pd.concat(
            [self._data, new], ignore_index=True, copy=False
        ).sort_values(by=Columns.Date, ignore_index=True)
        self.layoutChanged.emit()
        self.data_changed = True

    def flags(self, index):
        return (
            Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsEditable
        )

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                try:
                    return Columns.displayText(Columns[section])
                except KeyError:
                    return ""
            if orientation == Qt.Orientation.Vertical:
                return str(section + 1)

    def get_row(self, row):
        return self._data.iloc[row]

    def get_used_categories(self):
        return set(self._data[Columns.Category])

    def get_used_shops(self):
        return set(self._data[Columns.Shop])

    def search(self, pattern: str, regex: bool = False) -> list[tuple[int, int]]:
        matches = []
        for row_idx in range(self._data.shape[0]):
            for col_idx in range(self._data.shape[1]):
                # Skip the first and last columns (Date and Value)
                if col_idx in [0, 4]:
                    continue
                cell = str(self._data.iat[row_idx, col_idx])
                if regex:
                    if re.search(pattern, cell):
                        matches.append((row_idx, col_idx))
                else:
                    if pattern in cell:
                        matches.append((row_idx, col_idx))
        return matches

    def replace(self, pattern: str, replacement: str, regex: bool = False) -> int:
        matches = self.search(pattern, regex)
        for row, col in matches:
            cell = str(self._data.iat[row, col])
            new_value = (
                re.sub(pattern, replacement, cell)
                if regex
                else cell.replace(pattern, replacement)
            )
            self._data.iat[row, col] = new_value
        if matches:
            top_left = self.index(
                min(r for r, _ in matches), min(c for _, c in matches)
            )
            bottom_right = self.index(
                max(r for r, _ in matches), max(c for _, c in matches)
            )
            self.dataChanged.emit(top_left, bottom_right, [Qt.ItemDataRole.DisplayRole])
            self.data_changed = True
        return len(matches)


class BarCanvas(FigureCanvasQTAgg):

    def __init__(
        self, parent=None, width=6, height=4, dpi=130, title=None, currency="€"
    ):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super().__init__(fig)
        self.figure.set_layout_engine("tight")
        fig.set_layout_engine("tight")
        if title:
            fig.suptitle(title)
        self.data = []
        self.labels = []
        self.currency = currency

    def set_data(self, labels, values):
        self.labels = labels
        self.data = values
        self.update_responsive()

    def draw_bars(self, labels, values):
        self.axes.cla()
        bars = self.axes.bar(labels, values)
        self.axes.bar_label(bars, fmt=f"{{:,.2f}}\u2009{self.currency}")
        self.draw()

    def update_responsive(self):
        if not self.data:
            return
        width = self.width()
        max_bars = max(3, width // 50)
        self.draw_bars(self.labels[-max_bars:], self.data[-max_bars:])

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_responsive()


class PieCanvas(FigureCanvasQTAgg):

    def __init__(self, parent=None, width=6, height=4, dpi=130, title=None):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super().__init__(fig)
        self.figure.set_layout_engine("tight")
        fig.set_layout_engine("tight")
        if title:
            fig.suptitle(title)

    def pie(self, data, *kargs, labels=None, **kwargs):
        def fix_labels(mylabels, tooclose=0.1, sepfactor=2):
            vecs = np.zeros((len(mylabels), len(mylabels), 2))
            dists = np.zeros((len(mylabels), len(mylabels)))
            for i in range(0, len(mylabels) - 1):
                for j in range(i + 1, len(mylabels)):
                    a = np.array(mylabels[i].get_position())
                    b = np.array(mylabels[j].get_position())
                    dists[i, j] = np.linalg.norm(a - b)
                    vecs[i, j, :] = a - b
                    if dists[i, j] < tooclose:
                        mylabels[i].set_x(a[0] + sepfactor * vecs[i, j, 0])
                        mylabels[i].set_y(a[1] + sepfactor * vecs[i, j, 1])
                        mylabels[j].set_x(b[0] - sepfactor * vecs[i, j, 0])
                        mylabels[j].set_y(b[1] - sepfactor * vecs[i, j, 1])

        if len(data) > 6:
            # Sort categories and sums together by sums in ascending order
            sorted_zip = sorted(zip(data, labels))

            # Separate the sums and categories again after sorting
            sorted_data, sorted_labels = zip(*sorted_zip)

            # Combine the smallest categories into "other"
            other_sum = sum(sorted_data[:-4])
            other_label = self.tr("Other")

            # Keep the largest 4 categories plus the "other" category
            data = list(sorted_data[-4:]) + [other_sum]
            labels = list(sorted_labels[-4:]) + [other_label]
        # replace labels of segments smaller than 3% by empty string
        for i, d in enumerate(data):
            if d < 0.03 * sum(data):
                labels[i] = ""
        self.axes.cla()

        def labelfilter(pct):
            """Filter labels for small segments"""
            if pct < 4:
                return ""
            return f"{pct:.0f}%"

        wedges, labels, autopct = self.axes.pie(
            data,
            *kargs,
            labels=labels,
            labeldistance=1.1,
            autopct=labelfilter,
            **kwargs,
        )
        fix_labels(labels, sepfactor=2)

        self.draw()


class ResizeAbleFontWindow:
    def __init__(self, font_size=14):
        self.font_size = font_size  # Default font size
        self.update_font()

    def register_shortcuts(self):
        # Shortcuts for increasing and decreasing font size
        increase_font_shortcut = QShortcut(
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Plus), self
        )
        decrease_font_shortcut = QShortcut(
            QKeySequence(Qt.Modifier.CTRL | Qt.Key.Key_Minus), self
        )

        # Connect shortcuts to methods
        increase_font_shortcut.activated.connect(self.increase_font_size)
        decrease_font_shortcut.activated.connect(self.decrease_font_size)

    def increase_font_size(self):
        self.font_size += 1
        self.update_font()

    def decrease_font_size(self):
        self.font_size -= 1
        self.update_font()

    def update_font(self):
        font = QFont()
        font.setPointSize(self.font_size)
        if isinstance(self, QMainWindow):
            centralWidget = self.centralWidget()
        elif isinstance(self, QDialog):
            centralWidget = self
        else:
            return
        self.setFontForAllWidgets(centralWidget, font)
        self.setFontForAllWidgets(self.findChild(QToolBar), font)
        self.setFontForAllWidgets(self.findChild(QDockWidget), font)

    def setFontForAllWidgets(self, widget, font):
        if widget is None:
            return
        widget.setFont(font)
        for child in widget.findChildren(QWidget):
            child.setFont(font)


class MicroAccounting(QMainWindow, Ui_MainWindow, ResizeAbleFontWindow):
    data_dir = (
        Path(os.getenv("XDG_DATA_HOME", Path.home() / ".local" / "share")) / APPNAME
    )
    file_path = data_dir / "accounting.csv"
    settings = QSettings(APPNAME)

    def __init__(self):
        Ui_MainWindow.__init__(self)
        QMainWindow.__init__(self)
        ResizeAbleFontWindow.__init__(self)
        self.setupUi(self)
        self.actionSave.triggered.connect(self.save_csv)
        self.actionAdd_Entry.triggered.connect(self.open_entry_dialog)
        self.actionSaveImages.triggered.connect(self.save_figures)

        owner = self.settings.value("owner")
        if owner is None:
            owner, ok = QInputDialog.getText(
                self,
                self.tr("Owner name"),
                self.tr("Please enter your name:"),
            )
            if ok:
                self.settings.setValue("owner", owner)
        if owner:
            self.setWindowTitle(self.tr("Bookkeeping of {owner}").format(owner=owner))
        else:
            self.setWindowTitle(self.tr("Bookkeeping"))

        self.currency = self.settings.value("currency")
        if self.currency is None:
            self.currency, ok = QInputDialog.getText(
                self,
                self.tr("Currency"),
                self.tr("Please enter the currency symbol:"),
            )
            if ok:
                self.settings.setValue("currency", self.currency)

        self.model = MyTableModel(self.file_path, currency=self.currency)
        self.table_widget.setModel(self.model)

        self.cat_delegate = ComboBoxDelegate(self.model, self.model.get_used_categories)
        self.shop_delegate = ComboBoxDelegate(self.model, self.model.get_used_shops)
        self.date_delegate = DateDelegate()
        self.value_delegate = CurrencyDelegate(currency=self.currency)
        self.table_widget.setItemDelegateForColumn(
            Columns.index(Columns.Category), self.cat_delegate
        )
        self.table_widget.setItemDelegateForColumn(
            Columns.index(Columns.Shop), self.shop_delegate
        )
        self.table_widget.setItemDelegateForColumn(
            Columns.index(Columns.Date), self.date_delegate
        )
        self.table_widget.setItemDelegateForColumn(
            Columns.index(Columns.Value), self.value_delegate
        )
        self.resize_columns()

        self.cat_chart = PieCanvas(self, title=self.tr("Expenses by category"))
        self.month_chart = BarCanvas(
            self, title=self.tr("Expenses per month"), currency=self.currency
        )
        self.shop_chart = PieCanvas(self, title=self.tr("Expenses by shop"))

        self.category_chart_layout.addWidget(self.cat_chart)
        self.monthly_chart_layout.addWidget(self.month_chart)
        self.shop_chart_layout.addWidget(self.shop_chart)

        self.toolBar.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.update_charts()
        self.model.dataChanged.connect(self.handle_item_changed)
        self.resizeDocks(
            [self.dockWidget],
            [self.frameGeometry().width() // 3],
            Qt.Orientation.Horizontal,
        )
        self.register_shortcuts()
        self.restore_geometry()

        # Set up debug shortcut
        QShortcut("Ctrl+Alt+Shift+K", self).activated.connect(self.debug)
        QShortcut("Ctrl+Shift+E", self).activated.connect(
            self.open_search_replace_dialog
        )

    def open_search_replace_dialog(self) -> None:
        self.search_replace_dialog = SearchAndReplaceDialog(
            self, font_size=self.font_size
        )
        self.search_replace_dialog.replaceRequested.connect(self.handle_replace)
        self.search_replace_dialog.show()

    def handle_replace(self, pattern: str, replacement: str, regex: bool) -> None:
        count = self.model.replace(pattern, replacement, regex)
        self.search_replace_dialog.result_label.setText(
            self.tr("Replaced {count} occurrence(s).").format(count=count)
        )

    def save_geometry(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("font_size", self.font_size)

    def restore_geometry(self):
        geometry = self.settings.value("geometry")
        font_size = self.settings.value("font_size")
        if geometry:
            self.restoreGeometry(QByteArray(geometry))
        if font_size:
            self.font_size = int(font_size)
            self.update_font()

    def resize_columns(self):
        self.table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        content_sizes = {}
        for col in range(len(Columns)):
            content_sizes[col] = self.table_widget.columnWidth(col)

        self.table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Interactive
        )
        self.table_widget.horizontalHeader().setSectionResizeMode(
            Columns.index(Columns.Description), QHeaderView.ResizeMode.Stretch
        )
        # Make sure all Columns have enough white space
        for col in range(len(Columns)):
            current_size = self.table_widget.columnWidth(col)
            new = max(current_size, content_sizes[col] + 30)
            self.table_widget.setColumnWidth(col, new)

    def debug(self):
        import IPython

        IPython.embed()

    def update_font(self):
        super().update_font()
        try:
            self.table_widget.verticalHeader().setDefaultSectionSize(self.font_size + 4)
            self.resize_columns()
        except AttributeError:
            pass

    def closeEvent(self, event):
        if self.model.data_changed:
            reply = QMessageBox.question(
                self,
                self.tr("Unsaved changes"),
                self.tr(
                    "There are unsaved changes. Do you want to save before closing?"
                ),
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_csv()
                self.save_geometry()
                event.accept()
            elif reply == QMessageBox.StandardButton.No:
                self.save_geometry()
                event.accept()
            else:
                event.ignore()
        else:
            self.save_geometry()
            event.accept()

    def handle_item_changed(self, _item=None):
        self.update_charts()

    def load_csv(self, file_path: str):
        self.model.load_csv(file_path)
        self.model.layoutChanged.emit()
        self.update_charts()

    def save_csv(self):
        self.model.save_csv()

    def open_entry_dialog(self):
        def filter_text(text: str):
            text = text.strip().strip(".")
            return text

        dialog = EntryDialog(
            self,
            categories=self.model.get_used_categories(),
            shops=self.model.get_used_shops(),
            font_size=self.font_size,
            currency=self.currency,
        )
        if dialog.exec():
            date = dialog.date_edit.date()
            # If date is before 2000, assume typo, move 100 years
            if date.year() < 2000:
                date.replace(year=date.year + 100)
            date_str = date.toString("yyyy-MM-dd")
            amount = dialog.amount_edit.value()
            shop = filter_text(dialog.shop_edit.currentText())
            description = filter_text(dialog.description_edit.text())
            category = filter_text(dialog.category_edit.currentText())

            row_number = self.model.rowCount()
            self.model.insertRow(
                date=date_str,
                description=description,
                shop=shop,
                category=category,
                value=amount,
            )
            self.handle_item_changed()

    def update_charts(self):
        category_sums = defaultdict(float)
        by_month = defaultdict(float)
        by_shop = defaultdict(float)
        for row in range(self.model.rowCount()):
            try:
                _date, category, shop, _, _amount = self.model.get_row(row)
                amount = float(_amount)
                month = datetime.strptime(_date, "%Y-%m-%d").strftime("%b\n%y")
                category_sums[category] += amount
                by_month[month] += amount
                if shop != "":
                    by_shop[shop] += amount
            except ValueError as e:
                print("Error", e)
        try:
            categories = list(category_sums.keys())
            sums = list(category_sums.values())
            shops = list(by_shop.keys())
            shop_sums = list(by_shop.values())
            self.cat_chart.pie(sums, labels=categories, startangle=140)
            self.shop_chart.pie(shop_sums, labels=shops, startangle=140)
            self.month_chart.set_data(list(by_month.keys()), list(by_month.values()))
        except Exception as e:
            print("Error", e)

    def save_figures(self):
        """Saves the figures to home directory."""
        home = Path.home()
        self.cat_chart.figure.savefig(home / "categories.png")
        self.shop_chart.figure.savefig(home / "shops.png")
        self.month_chart.figure.savefig(home / "monthly.png")
        print(self.tr("Figures saved to {home}").format(home=home))


class SearchAndReplaceDialog(QDialog, ResizeAbleFontWindow):
    replaceRequested = pyqtSignal(str, str, bool)

    def __init__(self, parent=None, font_size=None) -> None:
        super().__init__(parent)
        ResizeAbleFontWindow.__init__(self, font_size)
        self.setWindowTitle(self.tr("Search and replace"))

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(self.tr("Search for..."))

        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText(self.tr("Replace with..."))

        self.regex_checkbox = QCheckBox(self.tr("Regular expression"))

        self.result_label = QLabel()

        self.replace_button = QPushButton(self.tr("Replace"))
        self.close_button = QPushButton(self.tr("Close"))

        self.replace_button.clicked.connect(self.on_replace)
        self.close_button.clicked.connect(self.close)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(self.tr("Search:")))
        layout.addWidget(self.search_input)
        layout.addWidget(QLabel(self.tr("Replace:")))
        layout.addWidget(self.replace_input)
        layout.addWidget(self.regex_checkbox)
        layout.addWidget(self.replace_button)
        layout.addWidget(self.close_button)
        layout.addWidget(self.result_label)

        self.setLayout(layout)
        self.register_shortcuts()

    def on_replace(self) -> None:
        pattern = self.search_input.text()
        replacement = self.replace_input.text()
        regex = self.regex_checkbox.isChecked()
        self.replaceRequested.emit(pattern, replacement, regex)


class EntryDialog(QDialog, ResizeAbleFontWindow):

    def __init__(
        self, parent=None, categories=None, shops=None, font_size=None, currency="€"
    ):
        QDialog.__init__(self, parent)
        ResizeAbleFontWindow.__init__(self, font_size)
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.DEFAULT_CATEGORIES: ClassVar[Set[str]] = set(
            [
                tr("Groceries"),
                tr("Restaurants"),
                tr("Purchases"),
                tr("Gift"),
                tr("Other"),
            ]
        )

        self.setWindowTitle(self.tr("Add entry"))
        self.resize(500, 250)

        self.layout = QFormLayout(self)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.layout.addRow(f"{Columns.displayText(Columns.Date)}:", self.date_edit)

        self.category_edit = QComboBox(self)
        self.category_edit.setEditable(True)
        if categories:
            all_categories = self.DEFAULT_CATEGORIES | categories
        else:
            all_categories = self.DEFAULT_CATEGORIES
        self.category_edit.addItems(sorted(all_categories))
        self.category_edit.lineEdit().setMaxLength(30)
        self.category_edit.lineEdit().textEdited.connect(
            self.validate_input(self.tr("Category"))
        )
        self.layout.addRow(
            f"{Columns.displayText(Columns.Category)}:", self.category_edit
        )

        self.shop_edit = QComboBox(self)
        self.shop_edit.setEditable(True)
        self.shop_edit.addItems(sorted(shops))
        self.shop_edit.lineEdit().setMaxLength(30)
        self.shop_edit.lineEdit().textEdited.connect(
            self.validate_input(self.tr("Shop"))
        )
        self.layout.addRow(f"{Columns.displayText(Columns.Shop)}:", self.shop_edit)

        self.description_edit = QLineEdit(self)
        self.layout.addRow(
            f"{Columns.displayText(Columns.Description)}:", self.description_edit
        )

        self.amount_edit = QDoubleSpinBox(self)
        self.amount_edit.setSuffix("\u2009" + currency)
        self.amount_edit.setMaximum(9999999.99)
        self.layout.addRow(f"{Columns.displayText(Columns.Value)}:", self.amount_edit)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.accepted.connect(self.accept_if_valid)
        self.button_box.rejected.connect(self.reject)
        self.layout.addRow(self.button_box)
        self.register_shortcuts()

    def validate_input(self, title: str):
        def handler(text: str):
            if len(text) >= 30:
                QMessageBox.warning(
                    self,
                    self.tr("Too long"),
                    self.tr(
                        "Value for {title} is too long. Please shorten.", "EntryDialog"
                    ).format(title=title),
                )

        return handler

    def accept_if_valid(self):
        amount = self.amount_edit.value()
        description = self.description_edit.text()
        shop = self.shop_edit.currentText()
        if amount == 0 and description == "" and shop == "":
            self.reject()
        elif amount != 0 and description:
            self.accept()
        elif amount == 0:
            QMessageBox.warning(
                self,
                self.tr("Invalid entry"),
                self.tr("Amount must not be zero."),
            )
        elif description == "":
            QMessageBox.warning(
                self,
                self.tr("Invalid entry"),
                self.tr("Description must not be empty."),
            )


def main():
    signal.signal(signal.SIGINT, sigint_handler)
    app = QApplication(sys.argv)
    shm = QSharedMemory(APPNAME)
    if not shm.create(1):
        print(tr("App is already running."))
        sys.exit(0)
    app.setWindowIcon(QIcon("Bookkeeping_icon.jpeg"))
    install_translators(app)
    global window
    window = MicroAccounting()
    window.show()
    timer = QTimer()
    timer.start(500)  # Let the interpreter run each 500 ms.
    timer.timeout.connect(lambda: None)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
