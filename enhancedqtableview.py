from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QApplication, QTableView


class EnhancedQTableView(QTableView):
    def __init__(self, parent=None):
        super().__init__(parent)

    def keyPressEvent(self, event):
        super().keyPressEvent(event)
        if event.key() == Qt.Key.Key_C and (
            event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            selected_indexes = sorted(self.selectedIndexes())

            copy_text = ""
            previous_row = selected_indexes[0].row()
            first = True
            for index in selected_indexes:
                if index.row() != previous_row:
                    copy_text += "\n"
                elif first:
                    first = False
                else:
                    copy_text += "\t"
                copy_text += str(self.model().data(index))
                previous_row = index.row()

            QApplication.clipboard().setText(copy_text)
