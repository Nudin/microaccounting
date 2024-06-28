#!/usr/bin/env python
import csv
import shutil
import signal
import sys
from collections import defaultdict
from datetime import datetime
from enum import IntEnum
from pathlib import Path
from typing import ClassVar, Set

import matplotlib
import numpy as np
import pandas as pd
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import (QAbstractTableModel, QDate, QLibraryInfo, QLocale,
                          Qt, QTimer, QTranslator)
from PyQt6.QtGui import QFont, QKeySequence, QShortcut, QStandardItemModel
from PyQt6.QtWidgets import (QApplication, QComboBox, QDateEdit, QDialog,
                             QDialogButtonBox, QDockWidget, QDoubleSpinBox,
                             QFormLayout, QHeaderView, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPushButton,
                             QStyledItemDelegate, QTableView, QTableWidgetItem,
                             QTextEdit, QToolBar, QVBoxLayout, QWidget)

from main_window import Ui_MainWindow

matplotlib.use("QtAgg")

window = None


def install_translator(app: QApplication) -> None:
    translator = QTranslator(app)
    qt_translations_path = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
    if translator.load(QLocale.system(), "qtbase", "_", qt_translations_path):
        app.installTranslator(translator)
    else:
        print("Übersetzung konnte nicht geladen werden.")


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
        editor.setDisplayFormat("dd.MM.yyyy")
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
        return date.toString("dd.MM.yyyy")


class MyTableModel(QAbstractTableModel):
    data_changed: bool
    FIELDS = ["Datum", "Geschäft", "Ausgabe", "Wert", "Kategorie"]

    def __init__(self, file_path):
        super(MyTableModel, self).__init__()
        self.file_path = file_path
        self.locale = QLocale()
        self.load_csv()

    def load_csv(self, file_path=None):
        if file_path is None:
            file_path = self.file_path
        if Path(file_path).is_file():
            self._data = pd.read_csv(file_path, keep_default_na=False)
        else:
            self._data = pd.DataFrame(columns=self.FIELDS)
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
        shutil.copyfile(file_path, backup_file_path)

    def rowCount(self, index=None):
        return len(self._data)

    def columnCount(self, index=None):
        return len(self._data.columns)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            data = self._data.iloc[index.row(), index.column()]
            if not isinstance(data, str):
                data = self.locale.toString(data, "f", 2)
            return data
        if role == Qt.ItemDataRole.EditRole:
            data = self._data.iloc[index.row(), index.column()]
            if not isinstance(data, str):
                data = float(data)
            return data

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if role == Qt.ItemDataRole.EditRole:
            self._data.iloc[index.row(), index.column()] = value
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
                    "Datum": date,
                    "Geschäft": shop,
                    "Ausgabe": description,
                    "Wert": value,
                    "Kategorie": category,
                }
            ]
        )
        self._data = pd.concat(
            [self._data, new], ignore_index=True, copy=False
        ).sort_values(by="Datum")
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
                    return self.FIELDS[section]
                except KeyError:
                    return ""
            if orientation == Qt.Orientation.Vertical:
                return str(section + 1)

    def get_row(self, row):
        return self._data.iloc[row]

    def get_used_categories(self):
        return set(self._data["Kategorie"])

    def get_used_shops(self):
        return set(self._data["Geschäft"])


class MplCanvas(FigureCanvasQTAgg):

    def __init__(self, parent=None, width=6, height=4, dpi=150, title=None):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super().__init__(fig)
        if title:
            fig.suptitle(title)

    def bar(self, *kargs, **kwargs):
        self.axes.cla()
        bar = self.axes.bar(*kargs, **kwargs)
        self.axes.bar_label(bar, fmt="{:,.2f}\u2009€")
        self.draw()

    def pie(self, *kargs, **kwargs):
        self.axes.cla()
        self.axes.pie(*kargs, **kwargs)
        self.draw()


class MicroAccounting(QMainWindow, Ui_MainWindow):
    file_path = "Buchhaltung.csv"

    def __init__(self):
        Ui_MainWindow.__init__(self)
        QMainWindow.__init__(self)
        self.setupUi(self)
        self.actionSave.triggered.connect(self.save_csv)
        self.actionAdd_Entry.triggered.connect(self.open_entry_dialog)

        self.model = MyTableModel(self.file_path)
        self.table_widget.setModel(self.model)

        self.cat_delegate = ComboBoxDelegate(self.model, self.model.get_used_categories)
        self.shop_delegate = ComboBoxDelegate(self.model, self.model.get_used_shops)
        self.date_delegate = DateDelegate()
        self.table_widget.setItemDelegateForColumn(4, self.cat_delegate)
        self.table_widget.setItemDelegateForColumn(1, self.shop_delegate)
        self.table_widget.setItemDelegateForColumn(0, self.date_delegate)
        self.table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )

        self.cat_chart = MplCanvas(self, title="Ausgaben pro Kategorie")
        self.month_chart = MplCanvas(self, title="Ausgaben pro Monat")
        self.shop_chart = MplCanvas(self, title="Ausgaben pro Geschäft")
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
        self.font_size = 14  # Default font size
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

        self.update_font()

    def increase_font_size(self):
        self.font_size += 1
        # self.table_widget.setRowHeight(self.table_widget.rowHeight() * 1.1)
        self.update_font()

    def decrease_font_size(self):
        self.font_size -= 1
        self.update_font()

    def update_font(self):
        font = QFont()
        font.setPointSize(self.font_size)
        self.setFontForAllWidgets(self.centralWidget(), font)
        self.setFontForAllWidgets(self.findChild(QToolBar), font)
        self.setFontForAllWidgets(self.findChild(QDockWidget), font)
        self.table_widget.verticalHeader().setDefaultSectionSize(self.font_size + 4)

    def setFontForAllWidgets(self, widget, font):
        widget.setFont(font)
        for child in widget.findChildren(QWidget):
            child.setFont(font)

    def closeEvent(self, event):
        if self.model.data_changed:
            reply = QMessageBox.question(
                self,
                "Ungespeicherte Änderungen",
                "Es gibt ungespeicherte Änderungen. Möchten Sie speichern, bevor Sie schließen?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.save_csv()
                event.accept()
            elif reply == QMessageBox.StandardButton.No:
                event.accept()
            else:
                event.ignore()
        else:
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
        dialog = EntryDialog(
            self,
            categories=self.model.get_used_categories(),
            shops=self.model.get_used_shops(),
        )
        if dialog.exec():
            date = dialog.date_edit.date().toString("yyyy-MM-dd")
            shop = dialog.shop_edit.currentText()
            description = dialog.description_edit.text()
            amount = dialog.amount_edit.value()
            category = dialog.category_edit.currentText()

            row_number = self.model.rowCount()
            self.model.insertRow(
                date=date,
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
                _date, shop, _, _amount, category = self.model.get_row(row)
                amount = float(_amount)
                month = datetime.strptime(_date, "%Y-%m-%d").strftime("%b %Y")
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
            self.cat_chart.pie(sums, labels=categories, autopct="%i%%", startangle=140)
            self.shop_chart.pie(shop_sums, labels=shops, autopct="%i%%", startangle=140)
            self.month_chart.bar(by_month.keys(), by_month.values())
        except Exception as e:
            print("Error", e)


class EntryDialog(QDialog):
    DEFAULT_CATEGORIES: ClassVar[Set[str]] = set(
        ["Lebensmittel", "Gastronomie", "Anschaffungen", "Geschenk", "Anderes"]
    )

    def __init__(self, parent=None, categories=None, shops=None):
        super().__init__()
        self.setWindowModality(Qt.WindowModality.WindowModal)

        self.setWindowTitle("Eintrag hinzufügen")
        self.setGeometry(200, 200, 500, 250)

        self.layout = QFormLayout(self)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.layout.addRow("Datum:", self.date_edit)

        self.shop_edit = QComboBox(self)
        self.shop_edit.setEditable(True)
        self.shop_edit.addItems(sorted(shops))
        self.layout.addRow("Geschäft:", self.shop_edit)

        self.description_edit = QLineEdit(self)
        self.layout.addRow("Beschreibung:", self.description_edit)

        self.amount_edit = QDoubleSpinBox(self)
        self.amount_edit.setSuffix(" €")
        self.amount_edit.setMaximum(9999999.99)
        self.layout.addRow("Betrag:", self.amount_edit)

        self.category_edit = QComboBox(self)
        self.category_edit.setEditable(True)
        if categories:
            all_categories = self.DEFAULT_CATEGORIES | categories
        else:
            all_categories = self.DEFAULT_CATEGORIES
        self.category_edit.addItems(sorted(all_categories))
        self.layout.addRow("Kategorie:", self.category_edit)

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.accepted.connect(self.accept_if_valid)
        self.button_box.rejected.connect(self.reject)
        self.layout.addRow(self.button_box)

    def accept_if_valid(self):
        amount = self.amount_edit.value()
        description = self.description_edit.text()
        shop = self.shop_edit.currentText()
        if amount == 0 and description == "" and shop == "":
            self.reject()
        elif amount != 0 and description:
            self.accept()
        else:
            QMessageBox.warning(
                self,
                "Ungültiger Eintrag",
                "Der Betrag darf nicht Null sein und die Beschreibung darf nicht leer sein.",
            )


def main():
    signal.signal(signal.SIGINT, sigint_handler)
    app = QApplication(sys.argv)
    install_translator(app)
    global window
    window = MicroAccounting()
    # Installiere den Translator
    window.show()
    timer = QTimer()
    timer.start(500)  # You may change this if you wish.
    timer.timeout.connect(lambda: None)  # Let the interpreter run each 500 ms.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
