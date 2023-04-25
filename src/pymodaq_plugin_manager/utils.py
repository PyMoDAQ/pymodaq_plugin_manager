# -*- coding: utf-8 -*-
"""
Created the 25/04/2023

@author: Sebastien Weber
"""
import copy
from pathlib import Path
import re
from packaging.version import Version, InvalidVersion
import numpy as np


from qtpy import QtCore, QtWidgets
from qtpy.QtCore import QLocale, Qt, QModelIndex
from qtpy import API_NAME


if API_NAME.lower() == 'pyqt5':
    from qtpy.QtCore import QVariant
else:
    def QVariant(*args):
        if len(args) > 1:
            raise TypeError('Argument of QVariant in a singlet')
        elif len(args) == 1:
            return args[0]
        else:
            return None


def decode_data(encoded_data):
    """
    Decode QbyteArrayData generated when drop items in table/tree/list view
    Parameters
    ----------
    encoded_data: QByteArray
                    Encoded data of the mime data to be dropped
    Returns
    -------
    data: list
            list of dict whose key is the QtRole in the Model, and the value a QVariant

    """
    data = []

    ds = QtCore.QDataStream(encoded_data, QtCore.QIODevice.ReadOnly)
    while not ds.atEnd():
        row = ds.readInt32()
        col = ds.readInt32()

        map_items = ds.readInt32()
        item = {}
        for ind in range(map_items):
            key = ds.readInt32()
            #TODO check this is fine
            value = QVariant()
            #value = None
            ds >> value
            item[QtCore.Qt.ItemDataRole(key)] = value.value()
        data.append(item)
    return data


class MyStyle(QtWidgets.QProxyStyle):

    def drawPrimitive(self, element, option, painter, widget=None):
        """
        Draw a line across the entire row rather than just the column
        we're hovering over.  This may not always work depending on global
        style - for instance I think it won't work on OSX.
        """
        if element == self.PE_IndicatorItemViewItemDrop and not option.rect.isNull():
            option_new = QtWidgets.QStyleOption(option)
            option_new.rect.setLeft(0)
            if widget:
                option_new.rect.setRight(widget.width())
            option = option_new
        super().drawPrimitive(element, option, painter, widget)


class SpinBoxDelegate(QtWidgets.QItemEditorFactory):
    def __init__(self, decimals=4, min=-1e6, max=1e6):
        self.decimals = decimals
        self.min = min
        self.max = max
        super().__init__()

    def createEditor(self, userType, parent):
        doubleSpinBox = QtWidgets.QDoubleSpinBox(parent)
        doubleSpinBox.setDecimals(self.decimals)
        doubleSpinBox.setMaximum(self.min)
        doubleSpinBox.setMaximum(self.max)
        return doubleSpinBox


class TableView(QtWidgets.QTableView):
    def __init__(self, *args, **kwargs):
        QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
        super().__init__(*args, **kwargs)
        self.setupview()

    def setupview(self):
        self.setStyle(MyStyle())

        self.verticalHeader().hide()
        self.horizontalHeader().hide()
        self.horizontalHeader().setStretchLastSection(True)

        self.setSelectionBehavior(QtWidgets.QTableView.SelectRows)
        self.setSelectionMode(QtWidgets.QTableView.SingleSelection)

        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDefaultDropAction(QtCore.Qt.MoveAction)
        self.setDragDropMode(QtWidgets.QTableView.InternalMove)
        self.setDragDropOverwriteMode(False)


class TableModel(QtCore.QAbstractTableModel):

    def __init__(self, data, header, editable=True, parent=None, show_checkbox=False):
        QLocale.setDefault(QLocale(QLocale.English, QLocale.UnitedStates))
        super().__init__(parent)
        if isinstance(data, np.ndarray):
            data_tot = []
            for dat in data:
                data_tot.append([float(d) for d in dat])
            data = data_tot
        self._data = data  # stored data as a list of list
        self._checked = [False for _ in range(len(self._data))]
        self._show_checkbox = show_checkbox
        self.data_tmp = None
        self.header = header
        if not isinstance(editable, list):
            self.editable = [editable for h in header]
        else:
            self.editable = editable

    def is_checked(self, row: int):
        return self._checked[row]

    @property
    def raw_data(self):
        return copy.deepcopy(self._data)

    def rowCount(self, parent):
        return len(self._data)

    def columnCount(self, parent):
        if self._data != []:
            return len(self._data[0])
        else:
            return 0

    def get_data(self, row, col):
        return self._data[row][col]

    def get_data_all(self):
        return self._data

    def clear(self):
        while self.rowCount(self.index(-1, -1)) > 0:
            self.remove_row(0)

    def set_data_all(self, data):
        self.clear()
        for row in data:
            self.insert_data(self.rowCount(self.index(-1, -1)), [float(d) for d in row])

    def data(self, index, role):
        if index.isValid():
            if role == Qt.DisplayRole or role == Qt.EditRole:
                dat = self._data[index.row()][index.column()]
                return dat
            elif role == Qt.CheckStateRole and index.column() == 0 and self._show_checkbox:
                if self._checked[index.row()]:
                    return Qt.CheckState.Checked
                else:
                    return Qt.CheckState.Unchecked
        return QVariant()

    # def setHeaderData(self, section, orientation, value):
    #     if section == 2 and orientation == Qt.Horizontal:
    #         names = self._data.columns
    #         self._data = self._data.rename(columns={names[section]: value})
    #         self.headerDataChanged.emit(orientation, 0, section)

    def headerData(self, section, orientation, role):
        if role == Qt.DisplayRole:
            if orientation == Qt.Horizontal:
                if section >= len(self.header):
                    return QVariant()
                else:
                    return self.header[section]
            else:
                return section
        else:
            return QVariant()

    def flags(self, index):

        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsDragEnabled
        if index.column() < len(self.editable):
            if self.editable[index.column()]:
                f |= Qt.ItemIsEditable
        if index.column() == 0:
            f |= Qt.ItemIsUserCheckable

        if not index.isValid():
            f |= Qt.ItemIsDropEnabled
        return f

    def supportedDropActions(self):
        return Qt.MoveAction | Qt.CopyAction

    def validate_data(self, row, col, value):
        """
        to be subclassed in order to validate ranges of values for the cell defined by index
        Parameters
        ----------
        index: (QModelIndex)
        value: (str or float or int or ...)


        Returns
        -------
        bool: True if value is valid for the given row and col
        """
        return True

    def setData(self, index, value, role):
        if index.isValid():
            if role == Qt.EditRole:
                if self.validate_data(index.row(), index.column(), value):
                    self._data[index.row()][index.column()] = value
                    self.dataChanged.emit(index, index, [role])
                    return True

                else:
                    return False
            elif role == Qt.CheckStateRole:
                self._checked[index.row()] = True if value == Qt.CheckState.Checked else False
                self.dataChanged.emit(index, index, [role])
                return True
        return False

    def dropMimeData(self, data, action, row, column, parent):
        if row == -1:
            row = self.rowCount(parent)

        self.data_tmp = [dat[2] for dat in decode_data(data.data("application/x-qabstractitemmodeldatalist"))]
        self.insertRows(row, 1, parent)
        return True

    def insert_data(self, row, data):
        self.data_tmp = data
        self.insertRows(row, 1, self.index(-1, -1))

    def insertRows(self, row, count, parent):
        self.beginInsertRows(QtCore.QModelIndex(), row, row + count - 1)
        for ind in range(count):
            self._data.insert(row + ind, self.data_tmp)
            self._checked.insert(row + ind, False)
        self.endInsertRows()
        return True

    def remove_row(self, row):
        self.removeRows(row, 1, self.index(-1, -1))

    def removeRows(self, row, count, parent):
        self.beginRemoveRows(QModelIndex(), row, row + count - 1)
        for ind in range(count):
            self._data.pop(row + ind)
            self._checked.pop(row + ind)
        self.endRemoveRows()
        return True


def get_pymodaq_version():
    """Obtain pymodaq version from the VERSION file

    Follows the layout from the packaging tool hatch, hatchling
    """
    from pymodaq import __version__
    try:
        version = Version(__version__)
    except InvalidVersion as e:
        DEFAULT_PATTERN = r'(?i)^(__version__|VERSION) *= *([\'"])v?(?P<version>.+?)\2'
        match = re.search(DEFAULT_PATTERN, version, flags=re.MULTILINE)
        groups = match.groupdict()
        if 'version' not in groups:
            raise ValueError('no group named `version` was defined in the pattern')
        version = Version(groups['version'])
    return version