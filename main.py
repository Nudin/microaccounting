import csv
import shutil
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import ClassVar, Set

import matplotlib.pyplot as plt
from PyQt6.QtCore import QDate
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import (QApplication, QComboBox, QDateEdit, QDialog,
                             QDialogButtonBox, QDoubleSpinBox, QFormLayout,
                             QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMainWindow, QMessageBox, QPushButton,
                             QTableWidget, QTableWidgetItem, QVBoxLayout,
                             QWidget)


class MicroAccounting(QMainWindow):
    file_path = "Buchhaltung.csv"
    data_changed = False
    in_atomic_change = False

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Buchhaltung")
        self.setGeometry(100, 100, 1100, 600)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        self.layout = QVBoxLayout()
        self.inner_layout = QHBoxLayout()
        self.layout.addLayout(self.inner_layout)
        self.central_widget.setLayout(self.layout)

        self.table_widget = QTableWidget()
        self.inner_layout.addWidget(self.table_widget)

        self.save_button = QPushButton("Speichern")
        self.save_button.setIcon(QIcon(QIcon.fromTheme("document-save")))
        self.save_button.clicked.connect(self.save_csv)
        self.layout.addWidget(self.save_button)

        self.add_entry_button = QPushButton("Eintrag hinzufügen")
        self.add_entry_button.setIcon(QIcon(QIcon.fromTheme("list-add")))
        self.add_entry_button.clicked.connect(self.open_entry_dialog)
        self.layout.addWidget(self.add_entry_button)

        self.pie_chart_label = QLabel(self)
        self.inner_layout.addWidget(self.pie_chart_label)

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
            self.update_pie_chart()

    def load_csv(self, file_path: str):
        if not Path(file_path).is_file():
            self.table_widget.setColumnCount(4)
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
                        row_number, column_number, QTableWidgetItem(data)
                    )

        self.table_widget.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.sort_table_by_date()
        self.update_pie_chart()

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
            description = dialog.description_edit.text()
            amount = dialog.amount_edit.value()
            category = dialog.category_edit.currentText()

            row_number = self.table_widget.rowCount()
            self.in_atomic_change = True
            self.table_widget.insertRow(row_number)
            self.table_widget.setItem(row_number, 0, QTableWidgetItem(date))
            self.table_widget.setItem(row_number, 1, QTableWidgetItem(description))
            self.table_widget.setItem(
                row_number, 2, QTableWidgetItem(f"{amount:.2f}".replace(".", ","))
            )
            self.table_widget.setItem(row_number, 3, QTableWidgetItem(category))
            self.in_atomic_change = False
            self.handle_item_changed()

            self.sort_table_by_date()
            self.data_changed = True

    def sort_table_by_date(self):
        self.table_widget.sortItems(0)

    def get_used_categories(self):
        categories = set()
        for row in range(self.table_widget.rowCount()):
            categories.add(self.table_widget.item(row, 3).text())
        return categories

    def update_pie_chart(self):
        category_sums = defaultdict(float)
        for row in range(self.table_widget.rowCount()):
            category = self.table_widget.item(row, 3).text()
            amount = float(self.table_widget.item(row, 2).text().replace(",", "."))
            category_sums[category] += amount

        categories = list(category_sums.keys())
        sums = list(category_sums.values())

        plt.figure(figsize=(6, 4))
        plt.pie(sums, labels=categories, autopct="%1.1f%%", startangle=140)
        plt.title("Ausgaben pro Kategorie")
        plt.axis("equal")
        plt.savefig("pie_chart.png")  # Save the pie chart as an image
        plt.close()

        pixmap = QPixmap("pie_chart.png")
        self.pie_chart_label.setPixmap(pixmap)


class EntryDialog(QDialog):
    DEFAULT_CATEGORIES: ClassVar[Set[str]] = set(
        ["Lebensmittel", "Gastronomie", "Anschaffungen", "Anderes"]
    )

    def __init__(self, parent=None, categories=None):
        super().__init__(parent)

        self.setWindowTitle("Eintrag hinzufügen")
        self.setGeometry(200, 200, 400, 250)

        self.layout = QFormLayout(self)

        self.date_edit = QDateEdit(self)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        self.layout.addRow("Datum:", self.date_edit)

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
    app = QApplication(sys.argv)
    viewer = MicroAccounting()
    viewer.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
