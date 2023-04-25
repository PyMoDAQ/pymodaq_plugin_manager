import logging
from packaging import version as version_mod
import sys
import subprocess


import numpy as np
from qtpy import QtWidgets, QtCore
from qtpy.QtCore import Qt, Slot, Signal
from qtpy.QtGui import QTextCursor
from readme_renderer.rst import render

from pymodaq_plugin_manager.validate import validate_json_plugin_list, get_plugins, get_plugin, get_check_repo,\
    find_dict_in_list_from_key_val
from pymodaq_plugin_manager.validate import get_pypi_pymodaq
from pymodaq_plugin_manager import __version__ as version
from pymodaq_plugin_manager.utils import QVariant, TableModel, TableView, SpinBoxDelegate, get_pymodaq_version

logger = logging.getLogger(__name__)
# logger.addHandler(logging.NullHandler())


class TableModel(TableModel):

    def __init__(self, *args, plugins=[], **kwargs):
        super().__init__(*args, **kwargs)
        self._selected = [False for ind in range(len(self._data))]
        self.plugins = plugins

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
                    dat = self._data[index.row()][0]
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
            plugin = self.sourceModel().plugins[plugin_index.row()]
            match = False
            if not not plugin:
                match = match or self.textRegExp.pattern().lower() in plugin['plugin-name'].lower()
                match = match or self.textRegExp.pattern().lower() in plugin['display-name'].lower()
                match = match or self.textRegExp.pattern().lower() in plugin['description'].lower()
                for plug in plugin['instruments']:
                    match = match | any(self.textRegExp.pattern().lower() in p.lower() for p in plugin['instruments'][plug])
            return match
        except Exception as e:
            print(e)
            return True

    def setTextFilter(self, regexp):
        self.textRegExp.setPattern(regexp)
        self.invalidateFilter()


class PluginManager(QtCore.QObject):

    quit_signal = Signal()
    restart_signal = Signal()

    def __init__(self, parent, standalone=False):
        super().__init__()
        self.parent = parent
        self.parent.setLayout(QtWidgets.QVBoxLayout())
        self.standalone = standalone

        self.plugins_available, self.plugins_installed,\
            self.plugins_update = get_plugins(False, pymodaq_version=get_pymodaq_version())

        self.setup_UI()

    def check_version(self, show=True):
        try:
            current_version = version_mod.parse(version)
            available_version = [version_mod.parse(ver) for ver in
                                 get_pypi_pymodaq('pymodaq-plugin-manager')['versions']]
            msgBox = QtWidgets.QMessageBox()
            if max(available_version) > current_version:
                msgBox.setText(f"A new version of PyMoDAQ Plugin Manager is available, {str(max(available_version))}!")
                msgBox.setInformativeText("Do you want to install it?")
                msgBox.setStandardButtons(msgBox.Ok | msgBox.Cancel)
                msgBox.setDefaultButton(msgBox.Ok)

                ret = msgBox.exec()

                if ret == msgBox.Ok:
                    command = [sys.executable, '-m', 'pip', 'install', f'pymodaq-plugin-manager=={str(max(available_version))}']
                    subprocess.Popen(command)

                    self.restart()
            else:
                if show:
                    msgBox.setText(f"Your version of PyMoDAQ Plugin Manager, {str(current_version)}, is up to date!")
                    ret = msgBox.exec()
        except Exception as e:
            logger.exception("Error while checking the available PyMoDAQ version")

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

        self.check_updates_pb = QtWidgets.QPushButton('Check Updates')
        self.check_updates_pb.clicked.connect(lambda: self.check_version(True))

        self.search_edit = QtWidgets.QLineEdit()
        self.search_edit.setPlaceholderText("Plugin name")

        settings_widget.layout().addWidget(self.plugin_choice)
        settings_widget.layout().addStretch()
        settings_widget.layout().addWidget(self.check_updates_pb)
        settings_widget.layout().addStretch()
        settings_widget.layout().addWidget(QtWidgets.QLabel('Search:'))
        settings_widget.layout().addWidget(self.search_edit)
        settings_widget.layout().addStretch()

        pymodaq_version = QtWidgets.QLabel(f'PyMoDAQ Version: {get_pymodaq_version()}')
        settings_widget.layout().addWidget(pymodaq_version)

        settings_widget.layout().addStretch()
        self.action_button = QtWidgets.QPushButton('Install')
        self.action_button.setEnabled(False)
        self.action_button.clicked.connect(self.do_action)
        settings_widget.layout().addWidget(self.action_button)


        self.parent.layout().addWidget(settings_widget)

        splitter = QtWidgets.QSplitter(Qt.Vertical)

        self.table_view = TableView()

        styledItemDelegate = QtWidgets.QStyledItemDelegate()
        styledItemDelegate.setItemEditorFactory(SpinBoxDelegate())
        self.table_view.setItemDelegate(styledItemDelegate)
        self.table_view.horizontalHeader().show()
        self.table_view.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)

        self.model_available = TableModel([[plugin['display-name'],
                                            plugin['version']] for plugin in self.plugins_available],
                                          header=['Plugin', 'Version'],
                                          editable=[False, False],
                                          plugins=self.plugins_available)
        self.model_update = TableModel([[plugin['display-name'],
                                         plugin['version']] for plugin in self.plugins_update],
                                       header=['Plugin', 'Version'],
                                       editable=[False, False],
                                       plugins=self.plugins_update)
        self.model_installed = TableModel([[plugin['display-name'],
                                            plugin['version']] for plugin in self.plugins_installed],
                                          header=['Plugin', 'Version'],
                                          editable=[False, False],
                                          plugins=self.plugins_installed)

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
        indexes_plugin = []
        plugins = []
        if self.plugin_choice.currentText() == 'Available':
            action = 'install'
            for ind, plug in enumerate(self.model_available.get_data_all()):
                if self.model_available.selected[ind]:
                    plugins.append(plug[0])
                    indexes_plugin.append(ind)
        elif self.plugin_choice.currentText() == 'Update':
            action = 'update'
            for ind, plug in enumerate(self.model_update.get_data_all()):
                if self.model_update.selected[ind]:
                    plugins.append(plug[0])
                    indexes_plugin.append(ind)
        elif self.plugin_choice.currentText() == 'Installed':
            action = 'remove'
            for ind, plug in enumerate(self.model_installed.get_data_all()):
                if self.model_installed.selected[ind]:
                    plugins.append(plug[0])
                    indexes_plugin.append(ind)

        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(f"You will {action} this list of plugins: {plugins}")
        msgBox.setInformativeText("Do you want to proceed?")
        msgBox.setStandardButtons(msgBox.Ok | msgBox.Cancel)
        msgBox.setDefaultButton(msgBox.Ok)

        ret = msgBox.exec()
        self.info_widget.clear()
        if ret == msgBox.Ok:
            for index in indexes_plugin:
                # plugin_dict = get_plugin(plug)
                if self.plugin_choice.currentText() == 'Available' or self.plugin_choice.currentText() == 'Update':
                    if self.plugin_choice.currentText() == 'Available':
                        plugin_dict = self.plugins_available[index]
                    else:
                        plugin_dict = self.plugins_update[index]
                    if plugin_dict is not None:
                        command = [sys.executable, '-m', 'pip', 'install',
                                   f'{plugin_dict["plugin-name"]}=={plugin_dict["version"]}']
                        self.do_subprocess(command)
                    else:
                        self.info_widget.insertPlainText(f'Plugin {plugin_dict["plugin-name"]} not found!')

                elif self.plugin_choice.currentText() == 'Installed':
                    plugin_dict = self.plugins_installed[index]
                    command = [sys.executable, '-m', 'pip', 'uninstall', '--yes', plugin_dict['plugin-name']]
                    self.do_subprocess(command)

        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(f"All actions were performed!")
        msgBox.setInformativeText(f"Do you want to quit and restart the application to take into account the modifications?")
        msgBox.setStandardButtons(msgBox.Close | msgBox.Cancel)
        restart_button = msgBox.addButton('Restart', msgBox.ApplyRole)
        msgBox.setDefaultButton(msgBox.Close)
        ret = msgBox.exec()
        if ret == msgBox.Close:
            self.quit()
        elif msgBox.clickedButton() is restart_button:
            self.restart()

    def do_subprocess(self, command):
        try:
            self.info_widget.moveCursor(QTextCursor.End)
            self.info_widget.insertPlainText(' '.join(command))
            self.info_widget.moveCursor(QTextCursor.End)

            with subprocess.Popen(command, stdout=subprocess.PIPE, universal_newlines=True, shell=True) as sp:
                while True:
                    self.info_widget.moveCursor(QTextCursor.End)
                    self.info_widget.insertPlainText(sp.stdout.readline())
                    self.info_widget.moveCursor(QTextCursor.End)
                    QtWidgets.QApplication.processEvents()
                    return_code = sp.poll()
                    if return_code is not None:
                        self.info_widget.insertPlainText(str(return_code))
                        for output in sp.stdout.readlines():
                            print(output.strip())
                        break
        except Exception as e:
            logger.info(str(e))
            subprocess.Popen(command)

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
            self.action_button.setEnabled(bool(np.any(index.model().sourceModel().selected)))



    def display_info(self, index):
        self.info_widget.clear()
        if index.isValid():
            if self.plugin_choice.currentText() == 'Available':
                plugin = self.plugins_available[index.model().mapToSource(index).row()]
            elif self.plugin_choice.currentText() == 'Update':
                plugin = self.plugins_update[index.model().mapToSource(index).row()]
            elif self.plugin_choice.currentText() == 'Installed':
                plugin = self.plugins_installed[index.model().mapToSource(index).row()]
            # doc, tag, text = Doc().tagtext()
            #
            # with tag('p'):
            #     text(plugin['description'])
            #
            # if not not plugin['authors']:
            #     text('Authors:')
            #     with tag('ul'):
            #         for inst in plugin['authors']:
            #             with tag('li'):
            #                 text(inst)
            #
            # if not not plugin['instruments']:
            #     with tag('p'):
            #         text('This package include plugins for the instruments listed below:')
            #     for inst in plugin['instruments']:
            #         with tag('p'):
            #             text(f'{inst}:')
            #         with tag('ul'):
            #             for instt in plugin['instruments'][inst]:
            #                 with tag('li'):
            #                     text(instt)
            # self.info_widget.insertHtml(doc.getvalue())
            self.info_widget.insertHtml(render(plugin['description']))


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = QtWidgets.QMainWindow()
    win.setWindowTitle('PyMoDAQ Plugin Manager')
    widget = QtWidgets.QWidget()
    win.setCentralWidget(widget)
    prog = PluginManager(widget, standalone=True)
    win.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
