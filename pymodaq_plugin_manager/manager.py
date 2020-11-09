import sys
import subprocess
from PyQt5 import QtWidgets, QtCore
from PyQt5.QtCore import Qt, QVariant, pyqtSlot, pyqtSignal
from pymodaq.daq_utils import gui_utils as gutils
from pymodaq_plugin_manager.validate import validate_json_plugin_list, get_plugins, get_plugin, get_check_repo
import numpy as np
import tempfile

class TableModel(gutils.TableModel):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._selected = [False for ind in range(len(self._data))]

    @property
    def selected(self):
        return self._selected

    def flags(self, index):
        f = super().flags(index)
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable
        return f

    def data(self, index, role=Qt.DisplayRole):
        if index.isValid():
            if role == Qt.DisplayRole or role == Qt.EditRole:
                if index.column() == 0:
                    if self._data[index.row()][0] == 'pymodaq_plugins':
                        dat = 'default'
                    else:
                        dat = self._data[index.row()][0].split('pymodaq_plugins_')[1]
                else:
                    dat = self._data[index.row()][index.column()]
                return dat
            elif role == Qt.CheckStateRole:
                if index.column() == 0:
                    if self._selected[index.row()]:
                        return Qt.Checked
                    else:
                        return Qt.Unchecked
        return QVariant()

    def setData(self, index, value, role):
        if index.isValid():
            if role == Qt.EditRole:
                if self.validate_data(index.row(), index.column(), value):
                    self._data[index.row()][index.column()] = value
                    self.dataChanged.emit(index, index, [role])
                    return True

                else:
                    return False
            if role == Qt.CheckStateRole:
                if index.column() == 0:
                    self._selected[index.row()] = value == Qt.Checked
                    self.dataChanged.emit(index, index, [role])
                    return True
        return False


class FilterProxy(QtCore.QSortFilterProxyModel):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.textRegExp = QtCore.QRegExp()
        self.textRegExp.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.textRegExp.setPatternSyntax(QtCore.QRegExp.Wildcard)

    def filterAcceptsRow(self, sourcerow, parent_index):
        plugin_index = self.sourceModel().index(sourcerow, 0, parent_index)
        try:
            plugin_name = self.sourceModel().data(plugin_index)
            return self.textRegExp.pattern() in plugin_name
        except Exception as e:
            print(e)
            return True

    def setTextFilter(self, regexp):
        self.textRegExp.setPattern(regexp)
        self.invalidateFilter()




class PluginManager(QtCore.QObject):

    quit_signal = pyqtSignal()
    restart_signal = pyqtSignal()

    def __init__(self, parent, standalone=False):
        super().__init__()
        self.parent = parent
        self.parent.setLayout(QtWidgets.QVBoxLayout())
        self.standalone = standalone


        self.plugins_available, self.plugins_installed, self.plugins_update = get_plugins()

        self.setup_UI()

    def quit(self):
        self.parent.parent().close()
        self.quit_signal.emit()

    def restart(self):
        self.parent.parent().close()
        if self.standalone:
            subprocess.call([sys.executable, __file__])
        else:
            self.restart_signal.emit()

    def setup_UI(self):

        settings_widget = QtWidgets.QWidget()
        settings_widget.setLayout(QtWidgets.QHBoxLayout())
        self.plugin_choice = QtWidgets.QComboBox()
        self.plugin_choice.addItems(['Available', 'Update', 'Installed'])
        self.plugin_choice.currentTextChanged.connect(self.update_model)
        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Plugin name")
        settings_widget.layout().addWidget(self.plugin_choice)
        settings_widget.layout().addStretch()
        settings_widget.layout().addWidget(QtWidgets.QLabel('Search:'))
        settings_widget.layout().addWidget(self.search_edit)
        settings_widget.layout().addStretch()
        self.action_button = QtWidgets.QPushButton('Install')
        self.action_button.setEnabled(False)
        self.action_button.clicked.connect(self.do_action)
        settings_widget.layout().addWidget(self.action_button)


        self.parent.layout().addWidget(settings_widget)

        splitter = QtWidgets.QSplitter(Qt.Vertical)

        self.table_view = gutils.TableView()
        styledItemDelegate = QtWidgets.QStyledItemDelegate()
        styledItemDelegate.setItemEditorFactory(gutils.SpinBoxDelegate())
        self.table_view.setItemDelegate(styledItemDelegate)
        self.table_view.horizontalHeader().show()

        self.model_available = TableModel([[plugin['plugin-name'],
                                            plugin['version']] for plugin in self.plugins_available],
                                          header=['Plugin', 'Version'],
                                          editable=[False, False])
        self.model_update = TableModel([[plugin['plugin-name'],
                                         plugin['version']] for plugin in self.plugins_update],
                                       header=['Plugin', 'Version'],
                                       editable=[False, False])
        self.model_installed = TableModel([[plugin['plugin-name'],
                                            plugin['version']] for plugin in self.plugins_installed],
                                          header=['Plugin', 'Version'],
                                          editable=[False, False])

        model_available_proxy = FilterProxy()
        model_available_proxy.setSourceModel(self.model_available)
        self.search_edit.textChanged.connect(model_available_proxy.setTextFilter)
        self.table_view.setModel(model_available_proxy)
        self.table_view.setSortingEnabled(True)
        self.table_view.clicked.connect(self.item_clicked)

        self.info_widget = QtWidgets.QTextEdit()
        self.info_widget.setReadOnly(True)

        splitter.addWidget(self.table_view)
        splitter.addWidget(self.info_widget)

        self.parent.layout().addWidget(splitter)

    def do_action(self):
        if self.plugin_choice.currentText() == 'Available':
            action = 'install'
            plugins = [plug[0] for ind, plug in enumerate(self.model_available.get_data_all())
                       if self.model_available.selected[ind]]
        elif self.plugin_choice.currentText() == 'Update':
            action = 'update'
            plugins = [plug[0] for ind, plug in enumerate(self.model_update.get_data_all())
                       if self.model_update.selected[ind]]
        elif self.plugin_choice.currentText() == 'Installed':
            action = 'remove'
            plugins = [plug[0] for ind, plug in enumerate(self.model_installed.get_data_all())
                       if self.model_installed.selected[ind]]

        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(f"You will {action} this list of plugins: {plugins}")
        msgBox.setInformativeText("Do you want to proceed?")
        msgBox.setStandardButtons(msgBox.Ok | msgBox.Cancel)
        msgBox.setDefaultButton(msgBox.Ok)

        ret = msgBox.exec()
        self.info_widget.clear()
        if ret == msgBox.Ok:
            for plug in plugins:
                plugin_dict = get_plugin(plug)
                if self.plugin_choice.currentText() == 'Available' or self.plugin_choice.currentText() == 'Update':
                    rep = get_check_repo(plugin_dict)
                    if rep is None:
                        command = [sys.executable, '-m', 'pip', 'install', plugin_dict['repository']]
                        self.do_subprocess(command)
                    else:
                        self.info_widget.insertPlainText(rep)


                elif self.plugin_choice.currentText() == 'Installed':
                    command = [sys.executable, '-m', 'pip', 'uninstall', '--yes', plug]
                    self.do_subprocess(command)

        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(f"All actions were performed!")
        msgBox.setInformativeText(f"Do you want to quit and restart the application to take into account the modifications?")
        msgBox.setStandardButtons(msgBox.Close | msgBox.Reset | msgBox.Cancel)
        msgBox.setDefaultButton(msgBox.Close)
        ret = msgBox.exec()
        if ret == msgBox.Close:
            self.close()
        elif ret == msgBox.Reset:
            self.restart()

    def do_subprocess(self, command):
        with subprocess.Popen(command, stdout=subprocess.PIPE, stdin=sys.stdout,
                              bufsize=1) as sp:
            for line in sp.stdout:
                self.info_widget.insertPlainText(line.decode())
                QtWidgets.QApplication.processEvents()


    def update_model(self, plugin_choice):
        self.search_edit.textChanged.disconnect()
        model_proxy = FilterProxy()
        if plugin_choice == 'Available':
            model_proxy.setSourceModel(self.model_available)
            self.action_button.setText('Install')
        elif plugin_choice == 'Update':
            model_proxy.setSourceModel(self.model_update)
            self.action_button.setText('Update')
        elif plugin_choice == 'Installed':
            model_proxy.setSourceModel(self.model_installed)
            self.action_button.setText('Remove')
        self.search_edit.textChanged.connect(model_proxy.setTextFilter)
        self.table_view.setModel(model_proxy)
        self.item_clicked(model_proxy.index(0, 0))


    def item_clicked(self, index):
        if index.isValid():
            self.display_info(index)
            self.action_button.setEnabled(np.any(index.model().sourceModel().selected))



    def display_info(self, index):
        self.info_widget.clear()
        if index.isValid():
            if self.plugin_choice.currentText() == 'Available':
                plugin = self.plugins_available[index.model().mapToSource(index).row()]
            elif self.plugin_choice.currentText() == 'Update':
                plugin = self.plugins_update[index.model().mapToSource(index).row()]
            elif self.plugin_choice.currentText() == 'Installed':
                plugin = self.plugins_installed[index.model().mapToSource(index).row()]
            self.info_widget.insertPlainText(plugin['description'])


if __name__ == '__main__':
    app = QtWidgets.QApplication(sys.argv)
    win = QtWidgets.QMainWindow()
    win.setWindowTitle('PyMoDAQ Plugin Manager')
    widget = QtWidgets.QWidget()
    win.setCentralWidget(widget)
    prog = PluginManager(widget, standalone=True)
    win.show()
    sys.exit(app.exec_())