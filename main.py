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
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QDate, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QComboBox, QDateEdit, QDialog,
                             QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                             QHeaderView, QLineEdit, QMainWindow, QMessageBox,
                             QTableWidgetItem)

from main_window import Ui_MainWindow

matplotlib.use("QtAgg")

window = None


def sigint_handler(*args):
    """Handler for the SIGINT signal."""
    sys.stderr.write("\r")
    if window:
        window.close()


class MplCanvas(FigureCanvasQTAgg):

    def __init__(self, parent=None, width=6, height=4, dpi=150, title=None):
        fig = Figure(figsize=(width, height), dpi=dpi)
        self.axes = fig.add_subplot(111)
        super().__init__(fig)
        if title:
            fig.suptitle(title)

    def bar(self, *kargs, **kwargs):
        self.axes.cla()
        self.axes.bar(*kargs, **kwargs)
        self.draw()

    def pie(self, *kargs, **kwargs):
        self.axes.cla()
        self.axes.pie(*kargs, **kwargs)
        self.draw()


class DataColumns(IntEnum):
    DATE = 0
    SHOP = 1
    DESC = 2
    AMOUNT = 3
    CATEGORY = 4


class MicroAccounting(QMainWindow, Ui_MainWindow):
    file_path = "Buchhaltung.csv"
    data_changed = False
    in_atomic_change = False

    def __init__(self):
        Ui_MainWindow.__init__(self)
        QMainWindow.__init__(self)
        self.setupUi(self)
        self.actionSave.triggered.connect(self.save_csv)
        self.actionAdd_Entry.triggered.connect(self.open_entry_dialog)

        self.cat_chart = MplCanvas(self, title="Ausgaben pro Kategorie")
        self.month_chart = MplCanvas(self, title="Ausgaben pro Monat")
        self.shop_chart = MplCanvas(self, title="Ausgaben pro Geschäft")
        self.category_chart_layout.addWidget(self.cat_chart)
        self.monthly_chart_layout.addWidget(self.month_chart)
        self.shop_chart_layout.addWidget(self.shop_chart)

        self.load_csv(MicroAccounting.file_path)
        self.table_widget.itemChanged.connect(self.handle_item_changed)

    def closeEvent(self, event):
        if self.data_changed:
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
        if not self.in_atomic_change:
            self.data_changed = True
            self.sort_table_by_date()
            self.update_charts()

    def load_csv(self, file_path: str):
        if not Path(file_path).is_file():
            self.table_widget.setColumnCount(len(DataColumns))
            self.table_widget.setHorizontalHeaderLabels(
                ["Datum", "Ausgabe", "Wert", "Kategorie"]
            )
            return

        with open(file_path, newline="", encoding="utf-8") as file:
            reader = csv.reader(file)
            headers = next(reader)

            self.table_widget.setColumnCount(len(headers))
            self.table_widget.setHorizontalHeaderLabels(headers)

            self.table_widget.setRowCount(0)
            for row_data in reader:
                row_number = self.table_widget.rowCount()
                self.table_widget.insertRow(row_number)
                for column_number, data in enumerate(row_data):
                    self.table_widget.setItem(
                        row_number,
                        column_number,
                        QTableWidgetItem(data),
                    )

        self.table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.sort_table_by_date()
        self.update_charts()

    def save_csv(self):
        self.create_backup(MicroAccounting.file_path)
        with open(MicroAccounting.file_path, "w", newline="", encoding="utf-8") as file:
            writer = csv.writer(file)
            headers = [
                self.table_widget.horizontalHeaderItem(i).text()
                for i in range(self.table_widget.columnCount())
            ]
            writer.writerow(headers)

            for row in range(self.table_widget.rowCount()):
                row_data = [
                    (
                        self.table_widget.item(row, column).text()
                        if self.table_widget.item(row, column)
                        else ""
                    )
                    for column in range(self.table_widget.columnCount())
                ]
                writer.writerow(row_data)
        self.data_changed = False

    def create_backup(self, file_path: str):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file_path = f"{file_path}_{timestamp}.bak"
        shutil.copyfile(file_path, backup_file_path)

    def open_entry_dialog(self):
        dialog = EntryDialog(self, categories=self.get_used_categories())
        if dialog.exec():
            date = dialog.date_edit.date().toString("yyyy-MM-dd")
            shop = dialog.shop_edit.text()
            description = dialog.description_edit.text()
            amount = dialog.amount_edit.value()
            category = dialog.category_edit.currentText()

            row_number = self.table_widget.rowCount()
            self.in_atomic_change = True
            self.table_widget.insertRow(row_number)
            self.table_widget.setItem(
                row_number, DataColumns.DATE, QTableWidgetItem(date)
            )
            self.table_widget.setItem(
                row_number, DataColumns.SHOP, QTableWidgetItem(shop)
            )
            self.table_widget.setItem(
                row_number, DataColumns.DESC, QTableWidgetItem(description)
            )
            self.table_widget.setItem(
                row_number,
                DataColumns.AMOUNT,
                QTableWidgetItem(f"{amount:.2f}".replace(".", ",")),
            )
            self.table_widget.setItem(
                row_number, DataColumns.CATEGORY, QTableWidgetItem(category)
            )
            self.in_atomic_change = False
            self.handle_item_changed()

            self.sort_table_by_date()
            self.data_changed = True

    def sort_table_by_date(self):
        self.table_widget.sortItems(DataColumns.DATE)

    def get_used_categories(self):
        categories = set()
        for row in range(self.table_widget.rowCount()):
            categories.add(self.table_widget.item(row, DataColumns.CATEGORY).text())
        return categories

    def update_charts(self):
        category_sums = defaultdict(float)
        by_month = defaultdict(float)
        by_shop = defaultdict(float)
        for row in range(self.table_widget.rowCount()):
            try:
                _date = self.table_widget.item(row, DataColumns.DATE).text()
                month = datetime.strptime(_date, "%Y-%m-%d").strftime("%b %Y")
                category = self.table_widget.item(row, DataColumns.CATEGORY).text()
                shop = self.table_widget.item(row, DataColumns.SHOP).text()
                amount = float(
                    self.table_widget.item(row, DataColumns.AMOUNT)
                    .text()
                    .replace(",", ".")
                )
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

    def __init__(self, parent=None, categories=None):
        super().__init__()

        self.setWindowTitle("Eintrag hinzufügen")
        self.setGeometry(200, 200, 400, 250)

        self.layout = QFormLayout(self)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.layout.addRow("Datum:", self.date_edit)

        self.shop_edit = QLineEdit(self)
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
        self.category_edit.addItems(all_categories)
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
        if amount != 0 and description:
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
    global window
    window = MicroAccounting()
    window.show()
    timer = QTimer()
    timer.start(500)  # You may change this if you wish.
    timer.timeout.connect(lambda: None)  # Let the interpreter run each 500 ms.
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
