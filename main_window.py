# Form implementation generated from reading ui file 'redesigned.ui'
#
# Created by: PyQt6 UI code generator 6.7.0
#
# WARNING: Any manual changes made to this file will be lost when pyuic6 is
# run again.  Do not edit this file unless you know what you are doing.


from PyQt6 import QtCore, QtGui, QtWidgets


class Ui_MainWindow(object):
    def setupUi(self, MainWindow):
        MainWindow.setObjectName("MainWindow")
        MainWindow.resize(1200, 600)
        self.centralwidget = QtWidgets.QWidget(parent=MainWindow)
        self.centralwidget.setObjectName("centralwidget")
        self.horizontalLayout_2 = QtWidgets.QHBoxLayout(self.centralwidget)
        self.horizontalLayout_2.setObjectName("horizontalLayout_2")
        self.table_widget = QtWidgets.QTableWidget(parent=self.centralwidget)
        self.table_widget.setRowCount(3)
        self.table_widget.setColumnCount(4)
        self.table_widget.setObjectName("table_widget")
        self.horizontalLayout_2.addWidget(self.table_widget)
        MainWindow.setCentralWidget(self.centralwidget)
        self.toolBar = QtWidgets.QToolBar(parent=MainWindow)
        self.toolBar.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toolBar.setObjectName("toolBar")
        MainWindow.addToolBar(QtCore.Qt.ToolBarArea.TopToolBarArea, self.toolBar)
        self.dockWidget = QtWidgets.QDockWidget(parent=MainWindow)
        self.dockWidget.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        self.dockWidget.setObjectName("dockWidget")
        self.dockWidgetContents = QtWidgets.QWidget()
        self.dockWidgetContents.setObjectName("dockWidgetContents")
        self.horizontalLayout_3 = QtWidgets.QHBoxLayout(self.dockWidgetContents)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.tabWidget = QtWidgets.QTabWidget(parent=self.dockWidgetContents)
        self.tabWidget.setObjectName("tabWidget")
        self.tab = QtWidgets.QWidget()
        self.tab.setObjectName("tab")
        self.horizontalLayout_4 = QtWidgets.QHBoxLayout(self.tab)
        self.horizontalLayout_4.setObjectName("horizontalLayout_4")
        self.pie_chart_label = QtWidgets.QLabel(parent=self.tab)
        self.pie_chart_label.setText("")
        self.pie_chart_label.setObjectName("pie_chart_label")
        self.horizontalLayout_4.addWidget(self.pie_chart_label)
        self.tabWidget.addTab(self.tab, "")
        self.tab_2 = QtWidgets.QWidget()
        self.tab_2.setObjectName("tab_2")
        self.tabWidget.addTab(self.tab_2, "")
        self.horizontalLayout_3.addWidget(self.tabWidget)
        self.dockWidget.setWidget(self.dockWidgetContents)
        MainWindow.addDockWidget(QtCore.Qt.DockWidgetArea(2), self.dockWidget)
        self.actionSave = QtGui.QAction(parent=MainWindow)
        self.actionSave.setEnabled(True)
        icon = QtGui.QIcon.fromTheme("document-save")
        self.actionSave.setIcon(icon)
        self.actionSave.setMenuRole(QtGui.QAction.MenuRole.NoRole)
        self.actionSave.setObjectName("actionSave")
        self.actionAdd_Entry = QtGui.QAction(parent=MainWindow)
        icon = QtGui.QIcon.fromTheme("list-add")
        self.actionAdd_Entry.setIcon(icon)
        self.actionAdd_Entry.setMenuRole(QtGui.QAction.MenuRole.TextHeuristicRole)
        self.actionAdd_Entry.setObjectName("actionAdd_Entry")
        self.toolBar.addAction(self.actionSave)
        self.toolBar.addSeparator()
        self.toolBar.addAction(self.actionAdd_Entry)

        self.retranslateUi(MainWindow)
        self.tabWidget.setCurrentIndex(0)
        QtCore.QMetaObject.connectSlotsByName(MainWindow)

    def retranslateUi(self, MainWindow):
        _translate = QtCore.QCoreApplication.translate
        MainWindow.setWindowTitle(_translate("MainWindow", "MainWindow"))
        self.toolBar.setWindowTitle(_translate("MainWindow", "toolBar"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab), _translate("MainWindow", "Tab 1"))
        self.tabWidget.setTabText(self.tabWidget.indexOf(self.tab_2), _translate("MainWindow", "Tab 2"))
        self.actionSave.setText(_translate("MainWindow", "Save"))
        self.actionAdd_Entry.setText(_translate("MainWindow", "Add Entry"))
        self.actionAdd_Entry.setToolTip(_translate("MainWindow", "Neuen Eintrag hinzufügen"))
