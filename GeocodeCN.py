# -*- coding: utf-8 -*-
"""
/***************************************************************************
 GeocodeCN
                                 address --> coordinates
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2022-01-03
        git sha              : $Format:%H$
        copyright            : (C) 2022 by WangShihan
        email                : 3443327820@qq.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import csv
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import QVariant
from qgis.core import QgsVectorLayer, QgsField, QgsFeature, QgsGeometry, QgsPointXY, QgsProject, Qgis
from qgis.PyQt.QtWidgets import QFileDialog, QAction, QMessageBox
import pandas as pd
from .gcs import Baidu, CrsGen
from .utils import CrsTypeEnum
# Initialize Qt resources from file resources.py
from .resources import *
# Import the code for the dialog
from .GeocodeCN_dialog import GeocodeCNDialog
import os
import encodings


class GeocodeCN:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.th = None
        self.iface = iface
        self.dlg = GeocodeCNDialog()
        # initialize plugin directory
        self.plugin_dir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir,
            'i18n',
            'GeocodeCN_{}.qm'.format(locale))

        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.settings = QSettings()
        self.menu = self.tr(u'&GeocodeCN')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.first_start = None
        self.locs = []
        self.fields = []
        self.file_selected = False
        self.crsMap = {"百度坐标系": CrsTypeEnum.bd, "WGS84": CrsTypeEnum.bd2wgs, "国测局坐标系": CrsTypeEnum.bd2gcj}
        self.appKeys = []
        self.curCrs = None
        self.curAk = None
        self.init_config()

    # noinspection PyMethodMayBeStatic
    def tr(self, message):
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('GeocodeCN', message)

    def add_action(
            self,
            icon_path,
            text,
            callback,
            enabled_flag=True,
            add_to_menu=True,
            add_to_toolbar=True,
            status_tip=None,
            whats_this=None,
            parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)

        if status_tip is not None:
            action.setStatusTip(status_tip)

        if whats_this is not None:
            action.setWhatsThis(whats_this)

        if add_to_toolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if add_to_menu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self):
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        icon_path = ':/plugins/GeocodeCN/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u''),
            callback=self.run,
            parent=self.iface.mainWindow())
        # will be set False in run()
        self.first_start = True
        if self.first_start:
            self.first_start = False
            # 绑定信号
            self.dlg.btn_file.clicked.connect(self.select_csv)
            self.dlg.btn_start.clicked.connect(self.run)
            self.dlg.btn_export.clicked.connect(self.export)
            self.dlg.btn_add.clicked.connect(self.add_lyr)
            self.dlg.btn_clear.clicked.connect(self.clear)
            self.dlg.btnSingle.clicked.connect(self.single)
            self.dlg.btn_addAk.clicked.connect(self.add_ak)
            self.dlg.btn_apply.clicked.connect(self.config_apply)
            self.dlg.btn_removeAk.clicked.connect(self.remove_ak)
            self.dlg.showEvent = self.window_show_eventHandler # type: ignore

    def init_config(self):
        self.appKeys = [] if self.settings.value('appKeys') is None else self.settings.value('appKeys')
        self.curCrs = self.settings.value('curCrs')
        self.curAk = self.settings.value('curAk')
        self.address_list = []
        self.dlg.cb_encoding.addItems(sorted(encodings.aliases.aliases.keys()))
        self.dlg.cb_encoding.setCurrentText('utf8')

        if self.curCrs is not None:
            for i in range(self.dlg.cb_crs.count()):
                if self.dlg.cb_crs.itemText(i) == self.curCrs:
                    self.dlg.cb_crs.setCurrentIndex(i)
                    print(self.dlg.cb_crs.itemText(i))
                    break
        if len(self.appKeys) > 0:
            self.dlg.cb_ak_mgr.addItems(self.appKeys)
            self.dlg.cb_ak.addItems(self.appKeys)
            if self.curAk is not None and self.curAk != "":
                self.dlg.cb_ak.setCurrentIndex(self.appKeys.index(self.curAk))

    def unload(self):
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&GeocodeCN'),
                action)
            self.iface.removeToolBarIcon(action)

    def add_ak(self):
        ak = self.dlg.le_addAk.text()
        if ak != "":
            self.appKeys.append(ak)
            self.update_ak(self.appKeys)
        self.dlg.le_addAk.setText("")
        self.setTip(self.tr("成功添加appKey！"), Qgis.Success) # type: ignore

    def remove_ak(self):
        whichAk = self.dlg.cb_ak_mgr.currentText()
        indexAk = self.appKeys.index(whichAk)
        self.appKeys.pop(indexAk)
        self.update_ak(self.appKeys)
        self.setTip(self.tr("成功移除appKey！"), Qgis.Success) # type: ignore

    def update_ak(self, aks):
        self.settings.setValue('appKeys', aks)
        self.dlg.cb_ak.clear()
        self.dlg.cb_ak_mgr.clear()
        self.init_config()

    def config_apply(self):
        self.settings.setValue('curCrs', self.dlg.cb_crs.currentText())
        self.settings.setValue('curAk', self.dlg.cb_ak.currentText())
        self.setTip(self.tr("配置应用成功！"), Qgis.Success) # type: ignore

    def window_show_eventHandler(self, evt):
        pass
        # self.init_config()

    def run(self):
        """Run method that performs all the real work"""
        self.dlg.show()
        result = self.dlg.exec_()
        if result:
            try:
                if self.file_selected and len(self.locs) == 0:
                    col_sel = self.dlg.cb.currentText()
                    crs = self.crsMap[self.dlg.cb_crs.currentText()]
                    self.th = CrsGen(self.address_list, col_sel, Baidu(ak=self.curAk, transform=crs))
                    self.th.signal.connect(self.collect_and_print)
                    self.th.finished.connect(lambda: self.dlg.pb.setValue(0))
                    self.th.start()
                else:
                    raise FileNotFoundError("请选择匹配文件或清除当前数据！")
            except Exception as e:
                QMessageBox.critical(self.dlg, '状态', str(e), QMessageBox.Ok)

    def select_csv(self):
        """
        选择文件
        """
        self.clear()
        try:
            file_name, _filter = QFileDialog.getOpenFileName(self.dlg, "选择文件", r"E:\Desktop\GisFile\sheet_text_asset",
                                                             "*.csv")
            # 是否选择文件
            if file_name:
                self.file_selected = True
                self.dlg.le_file.setText(file_name)
                reader = csv.DictReader(open(self.dlg.le_file.text(), 'r', encoding=self.dlg.cb_encoding.currentText()))
                self.fields.clear()
                self.fields += reader.fieldnames # type: ignore
                self.address_list.clear()
                self.address_list = list(reader)
                self.dlg.cb.addItems(self.fields)
                self.dlg.pb.setMaximum(len(self.address_list))
            else:
                pass
        except Exception as e:
            QMessageBox.information(self.dlg, "状态", str(e), QMessageBox.Yes)

    def single(self):
        """
        单一匹配地址
        """
        try:
            self.clear()
            crs = self.crsMap[self.dlg.cb_crs.currentText()]
            baidu = Baidu(ak=self.curAk, transform=crs)
            address = self.dlg.leAddress.text()
            self.fields: list= ['地址']
            res = baidu.get_one(address)
            if len(res) > 0:
                if res[0] == 1:
                    loc = res[1]
                    self.locs.clear()
                    self.locs.append([address] + loc)
                    self.dlg.tb_loc.append("地址：{:<50}\n经度：{:<20}\t纬度：{:<20} \n{:-<58}".format(address, loc[0], loc[1], ""))

            else:
                raise Exception("无地址数据！")
        except Exception as e:
            QMessageBox.information(self.dlg, '状态', str(e), QMessageBox.Ok)

    def collect_and_print(self, location):
        """
        自定义信号槽，接收子线程坐标信号
        """
        self.iface.messageBar().pushMessage(self.tr("已完成"), Qgis.Success)
        value = self.dlg.pb.value()
        self.dlg.pb.setValue(value + 1)
        if len(location) != 0:
            loc = location[-1]
            address = location[0]
            attr = location[1]
            self.locs.append(attr + loc)
            self.dlg.tb_loc.append("地址：{:<50}\n经度：{:<20}\t纬度：{:<20} \n{:-<58}".format(address, loc[0], loc[1], ""))

    def export(self):
        """
        导出为csv文件
        """
        try:
            # 是否存在已编码数据
            if len(self.locs) != 0:
                output_file, _filter = QFileDialog.getSaveFileName(self.dlg, "另存为csv", "", "*.csv")
                if output_file:
                    writer = csv.writer(open(output_file, 'a', encoding="gbk", newline=""))
                    writer.writerow(self.fields + ['lon', 'lat'])
                    for r in self.locs:
                        writer.writerow(r)
                    # 提醒并修改窗口标题
                    self.setTip(self.tr("成功导出为csv！"), Qgis.Success) # type: ignore
                    # QMessageBox.information(self.dlg, '状态', '保存成功！', QMessageBox.Yes)
                    self.dlg.setWindowTitle("GeocodeCN-已保存")
                else:
                    raise Exception("保持出错！")
            else:
                raise FileNotFoundError("无坐标数据！")
        except Exception as e:
            QMessageBox.critical(self.dlg, '状态', str(e), QMessageBox.Yes)

    def add_lyr(self):
        """
        添加临时图层至地图窗口
        """
        try:
            # 是否含有编码数据
            if len(self.locs) != 0:
                # 创建临时图层
                lyr = QgsVectorLayer("Point", "geocode_temp_lyr", "memory")
                # 添加属性字段
                pr = lyr.dataProvider()
                attr = [QgsField(i, QVariant.String) for i in self.fields + ['lon', 'lat']]

                pr.addAttributes(attr)
                lyr.updateFields()
                for r in self.locs:
                    y = r[-1]
                    x = r[-2]
                    # 创建要素
                    f = QgsFeature()
                    # 设置要素几何
                    f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
                    # 添加字段数据
                    f.setAttributes(r)
                    pr.addFeature(f)
                lyr.updateExtents()
                # 添加至地图
                QgsProject.instance().addMapLayer(lyr)
                self.setTip(self.tr("成功添加图层！"), Qgis.Success) # type: ignore
            else:
                raise ValueError("无坐标数据！")
        except Exception as e:
            QMessageBox.critical(self.dlg, '状态', str(e), QMessageBox.Yes)

    def setTip(self, tip: str, isSuccess: bool):
        if isSuccess:
            responseType = Qgis.Success
        else:
            responseType = Qgis.Warning
        self.iface.messageBar().pushMessage(self.tr(tip), responseType)

    def clear(self):
        """
        清除窗口信息
        """
        self.dlg.le_file.setText("")
        self.dlg.tb_loc.setText("")
        self.file_selected = False
        self.dlg.setWindowTitle("GeocodeCN")
        self.locs.clear()
        self.fields.clear()
        self.dlg.cb.clear()
