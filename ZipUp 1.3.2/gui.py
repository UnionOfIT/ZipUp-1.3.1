import os
import sys
import json
import zipfile
import tarfile
import tempfile
import subprocess
from datetime import datetime
import typing

import wx

from translations import get_translation
from arc_utils import open_zip, compression_for

try:
    _ZIP_ZSTD = zipfile.ZIP_ZSTD
except AttributeError:
    _ZIP_ZSTD = None


class Archiver(wx.Frame):
    def __init__(self, parent, title):
       
        self.config_dir = os.path.join(os.path.expanduser("~"), ".archivator")
        self.config_path = os.path.join(self.config_dir, "config.json")

      
        self.load_config()

        super().__init__(parent, title=self.get_translation(title), size=(900, 700))

        self.current_directory = os.path.dirname(os.path.abspath(__file__))
        self.SetIcon(self.load_icon('archive.png', wx.ART_FILE_OPEN))

        self.archive_name = ""
        self.current_folder = ""
        
        self.zip_password: typing.Optional[bytes] = None

        self.panel = wx.Panel(self)
        self.panel.SetBackgroundColour(wx.Colour(245, 245, 245))

        self.create_menu()
        self.create_toolbar()
        self.create_main_area()
        self.create_status_bar()

        self.Show()

    def prompt_zip_password(self):

        dlg = wx.PasswordEntryDialog(
            self,
            self.get_translation("Введите пароль архива:"),
            self.get_translation("Пароль"),
            ""
        )
        if dlg.ShowModal() == wx.ID_OK:
            pwd = dlg.GetValue()
            dlg.Destroy()
            if pwd:
                self.zip_password = pwd.encode()
                return True
        dlg.Destroy()
        return False

    def check_archive_has_password(self):
        if not self.archive_name or not self._is_zip_based():
            return False
        try:
            with open_zip(self.archive_name, 'r') as (archive, _):
                for info in archive.infolist():
                    if info.flag_bits & 0x1:
                        return True
            return False
        except Exception:
            return False

    def set_archive_password(self, old_password=None, new_password=None):
        if not self.archive_name or not self._is_zip_based():
            return False
        try:
            temp_archive = self.archive_name + '.tmp'
            
            try:
                import pyzipper
                has_pyzipper = True
            except ImportError:
                has_pyzipper = False
            
            with open_zip(self.archive_name, 'r') as (old_archive, _):
                if old_password:
                    old_archive.setpassword(old_password)
                entries = old_archive.infolist()
                data_map = {}
                for entry in entries:
                    if not entry.filename.endswith('/'):
                        data_map[entry.filename] = old_archive.read(entry.filename)
            
            if has_pyzipper and new_password:
                with pyzipper.AESZipFile(temp_archive, 'w', compression=pyzipper.ZIP_DEFLATED) as new_archive:
                    new_archive.setpassword(new_password)
                    new_archive.setencryption(pyzipper.WZ_AES)
                    for entry in entries:
                        if entry.filename.endswith('/'):
                            new_archive.writestr(entry.filename, b'')
                        else:
                            new_archive.writestr(entry.filename, data_map[entry.filename])
            else:
                with open_zip(temp_archive, 'w') as (new_archive, _):
                    if new_password:
                        new_archive.setpassword(new_password)
                    for entry in entries:
                        if entry.filename.endswith('/'):
                            new_archive.writestr(entry.filename, b'')
                        else:
                            new_archive.writestr(entry.filename, data_map[entry.filename])
            
            import shutil
            shutil.move(temp_archive, self.archive_name)
            return True
        except Exception as e:
            if os.path.exists(temp_archive):
                os.remove(temp_archive)
            return False

    def on_set_password(self, event):
        if not self.archive_name:
            self.show_error_dialog(self.get_translation("Сначала откройте архив."))
            return
        
        if not self.archive_name.lower().endswith('.zip'):
            self.show_error_dialog(self.get_translation("Пароль можно установить только на ZIP архивы."))
            return
        has_password = self.check_archive_has_password()
        old_password = None
        
        if has_password:
            dlg = wx.PasswordEntryDialog(
                self,
                self.get_translation("Введите текущий пароль архива:"),
                self.get_translation("Текущий пароль"),
                ""
            )
            if dlg.ShowModal() == wx.ID_OK:
                old_password = dlg.GetValue().encode()
                dlg.Destroy()
                try:
                    with open_zip(self.archive_name, 'r') as (archive, _):
                        archive.setpassword(old_password)
                        archive.testzip()
                except Exception:
                    dlg.Destroy()
                    self.show_error_dialog(self.get_translation("Неверный текущий пароль."))
                    return
            else:
                dlg.Destroy()
                return
        
        new_dlg = wx.PasswordEntryDialog(
            self,
            self.get_translation("Введите новый пароль архива:"),
            self.get_translation("Новый пароль"),
            ""
        )
        if new_dlg.ShowModal() == wx.ID_OK:
            new_password = new_dlg.GetValue().encode()
            new_dlg.Destroy()
            
            if self.set_archive_password(old_password, new_password):
                self.zip_password = new_password
                self.show_info_dialog(self.get_translation("Пароль архива успешно изменён."))
            else:
                self.show_error_dialog(self.get_translation("Ошибка при установке пароля."))
        else:
            new_dlg.Destroy()

    def load_config(self):
        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
        self.language = 'ru'

    def save_config(self):
        config = {'language': self.language}
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.show_error_dialog(f"{self.get_translation('Ошибка сохранения конфига: ')}{str(e)}")

    def get_translation(self, text):
        return get_translation(self.language, text)

    def restart_application(self):
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def load_icon(self, filename, fallback_art):
        icon_path = os.path.join(self.current_directory, filename)
        return wx.Icon(icon_path, wx.BITMAP_TYPE_PNG) if os.path.exists(icon_path) else wx.ArtProvider.GetIcon(fallback_art, wx.ART_OTHER)

    def create_menu(self):
        self.menubar = wx.MenuBar()
        self.update_file_menu()
        self.update_tools_menu()
        self.SetMenuBar(self.menubar)

    def update_file_menu(self):
        self.fileMenu = wx.Menu()
        self.fileMenu.Append(wx.ID_NEW, self.get_translation("Новый архив\tCtrl+N"), self.get_translation("Создать новый архив"))
        self.fileMenu.Append(wx.ID_OPEN, self.get_translation("Открыть архив\tCtrl+O"), self.get_translation("Открыть существующий архив"))
        self.fileMenu.Append(wx.ID_EXIT, self.get_translation("Выход\tCtrl+Q"), self.get_translation("Выход из приложения"))

        self.Bind(wx.EVT_MENU, self.on_create_archive, id=wx.ID_NEW)
        self.Bind(wx.EVT_MENU, self.on_select_archive, id=wx.ID_OPEN)
        self.Bind(wx.EVT_MENU, self.on_exit, id=wx.ID_EXIT)
        self.menubar.Append(self.fileMenu, self.get_translation("Файл"))

    def update_tools_menu(self):
        self.toolsMenu = wx.Menu()
        self.toolsMenu.Append(wx.ID_ADD, self.get_translation("Добавить файл или папку\tCtrl+A"), self.get_translation("Добавить файл или папку в архив"))
        self.toolsMenu.Append(wx.ID_EXECUTE, self.get_translation("Извлечь всё\tCtrl+E"), self.get_translation("Извлечь все файлы из архива"))
        self.toolsMenu.Append(wx.ID_ANY, self.get_translation("Извлечь выбранное\tCtrl+Shift+E"), self.get_translation("Извлечь выбранный файл"))
        self.toolsMenu.Append(wx.ID_ANY, self.get_translation("Создать папку"), self.get_translation("Создать папку в архиве"))
        self.toolsMenu.Append(wx.ID_ANY, self.get_translation("Установить пароль"), self.get_translation("Установить или изменить пароль архива"))
        self.toolsMenu.Append(wx.ID_ANY, self.get_translation("Обратная связь"), self.get_translation("Связь с разработчиком"))

        self.Bind(wx.EVT_MENU, self.on_add_file_or_folder, id=self.toolsMenu.FindItemByPosition(0).GetId())
        self.Bind(wx.EVT_MENU, self.on_extract_all, id=self.toolsMenu.FindItemByPosition(1).GetId())
        self.Bind(wx.EVT_MENU, self.on_extract_selected, id=self.toolsMenu.FindItemByPosition(2).GetId())
        self.Bind(wx.EVT_MENU, self.on_create_folder, id=self.toolsMenu.FindItemByPosition(3).GetId())
        self.Bind(wx.EVT_MENU, self.on_set_password, id=self.toolsMenu.FindItemByPosition(4).GetId())
        self.Bind(wx.EVT_MENU, self.on_feedback, id=self.toolsMenu.FindItemByPosition(5).GetId())

        self.menubar.Append(self.toolsMenu, self.get_translation("Инструменты"))

    def create_toolbar(self):
        toolbar = self.CreateToolBar()
        toolbar.SetBackgroundColour(wx.Colour(240, 240, 240))
        toolbar.AddTool(wx.ID_NEW, self.get_translation("Новый"), wx.ArtProvider.GetBitmap(wx.ART_NEW, wx.ART_TOOLBAR))
        toolbar.AddTool(wx.ID_OPEN, self.get_translation("Открыть"), wx.ArtProvider.GetBitmap(wx.ART_FILE_OPEN, wx.ART_TOOLBAR))
        toolbar.AddTool(wx.ID_ADD, self.get_translation("Добавить"), wx.ArtProvider.GetBitmap(wx.ART_PLUS, wx.ART_TOOLBAR))
        toolbar.AddTool(wx.ID_EXECUTE, self.get_translation("Извлечь"), wx.ArtProvider.GetBitmap(wx.ART_EXECUTABLE_FILE, wx.ART_TOOLBAR))
        search_tool_icon = wx.ArtProvider.GetBitmap(wx.ART_FIND, wx.ART_TOOLBAR)
        search_tool = toolbar.AddTool(wx.ID_ANY, self.get_translation("Поиск"), search_tool_icon, shortHelp=self.get_translation("Поиск файла в архиве"))
        delete_tool_icon = self.load_icon('delete.png', wx.ART_DELETE)
        delete_tool = toolbar.AddTool(wx.ID_ANY, self.get_translation("Удалить"), delete_tool_icon, shortHelp=self.get_translation("Удалить выбранный файл"))
        password_tool_icon = wx.ArtProvider.GetBitmap(wx.ART_TIP, wx.ART_TOOLBAR)
        self.password_tool = toolbar.AddTool(wx.ID_ANY, self.get_translation("Пароль"), password_tool_icon, shortHelp=self.get_translation("Установить или изменить пароль архива"))
        comment_tool_icon = self.load_icon('comment.png', wx.ART_TIP)
        self.comment_tool = toolbar.AddTool(wx.ID_ANY, self.get_translation("Комментарий"), comment_tool_icon, shortHelp=self.get_translation("Комментарий к архиву"))
        toolbar.Realize()

        self.Bind(wx.EVT_TOOL, self.on_create_archive, id=wx.ID_NEW)
        self.Bind(wx.EVT_TOOL, self.on_select_archive, id=wx.ID_OPEN)
        self.Bind(wx.EVT_TOOL, self.on_add_file_or_folder, id=wx.ID_ADD)
        self.Bind(wx.EVT_TOOL, self.on_extract_all, id=wx.ID_EXECUTE)
        self.Bind(wx.EVT_TOOL, self.on_search_file, id=search_tool.GetId())
        self.Bind(wx.EVT_TOOL, self.delete_selected_file, id=delete_tool.GetId())
        self.Bind(wx.EVT_TOOL, self.on_set_password, id=self.password_tool.GetId())
        self.Bind(wx.EVT_TOOL, self.on_comment, id=self.comment_tool.GetId())
        self.update_comment_button_state()
        self.update_password_button_state()

    def create_main_area(self):
        sizer = wx.BoxSizer(wx.HORIZONTAL)
        file_sizer = wx.BoxSizer(wx.VERTICAL)
        self.list_ctrl = wx.ListCtrl(self.panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, self.get_translation("Имя файла/папки"), width=400)
        self.list_ctrl.InsertColumn(1, self.get_translation("Размер"), width=90)
        self.list_ctrl.InsertColumn(2, self.get_translation("Дата изменения"), width=120)
        file_sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 10)
        self.comment_panel = wx.Panel(self.panel)
        self.comment_panel.Hide()
        comment_sizer = wx.BoxSizer(wx.VERTICAL)
        self.comment_label = wx.StaticText(self.comment_panel, label=self.get_translation("Комментарий к архиву:"))
        comment_sizer.Add(self.comment_label, 0, wx.TOP | wx.LEFT, 10)
        self.comment_text = wx.TextCtrl(self.comment_panel, style=wx.TE_MULTILINE|wx.TE_READONLY, size=(250, 100))
        comment_sizer.Add(self.comment_text, 1, wx.EXPAND | wx.ALL, 10)
        self.comment_panel.SetSizer(comment_sizer)
        sizer.Add(file_sizer, 1, wx.EXPAND)
        sizer.Add(self.comment_panel, 0, wx.EXPAND)
        self.panel.SetSizer(sizer)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_double_click)
        self.list_ctrl.Bind(wx.EVT_CONTEXT_MENU, self.on_list_context_menu)
        self.list_ctrl.Bind(wx.EVT_KEY_DOWN, self.on_list_key_down)

        class FileDropTarget(wx.FileDropTarget):
            def __init__(self, owner):
                super().__init__()
                self.owner = owner
            def OnDropFiles(self, x, y, filenames):
                self.owner.handle_drop(filenames)
                return True
        self.list_ctrl.SetDropTarget(FileDropTarget(self))

    def create_status_bar(self):
        self.status_bar = self.CreateStatusBar()
        self.status_bar.SetBackgroundColour(wx.Colour(220, 220, 220))
        self.status_bar.SetStatusText(self.get_translation("Готово"))

    def show_info_dialog(self, message):
        wx.MessageBox(message, self.get_translation("Информация"), wx.OK | wx.ICON_INFORMATION)

    def show_error_dialog(self, message):
        wx.MessageBox(message, self.get_translation("Ошибка"), wx.OK | wx.ICON_ERROR)

    def on_feedback(self, event):
        dlg = wx.Dialog(self, title=self.get_translation("Обратная связь"), size=(350, 160))
        vbox = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(dlg, label=self.get_translation("Связь с разработчиком:"))
        vbox.Add(label, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        discord_label = wx.StaticText(dlg, label="Discord: nonamecgalockoi")
        vbox.Add(discord_label, 0, wx.ALL | wx.ALIGN_CENTER, 5)
        btn_website = wx.Button(dlg, label=self.get_translation("Сайт разработчика"))
        vbox.Add(btn_website, 0, wx.ALL | wx.ALIGN_CENTER, 10)
        def open_website(event_button):
            wx.LaunchDefaultBrowser("https://unionofit.github.io/nonamecgalockoi.github.io/")
        btn_website.Bind(wx.EVT_BUTTON, open_website)
        dlg.SetSizer(vbox)
        dlg.ShowModal()
        dlg.Destroy()

    def on_item_double_click(self, event):
        item = event.GetItem()
        item_name = item.GetText()
        if item_name == '..':
            if self.current_folder:
                parts = self.current_folder.rstrip('/').split('/')[:-1]
                self.current_folder = '/'.join(parts)
                if self.current_folder:
                    self.current_folder += '/'
            self.update_file_list()
            return
        if item_name.endswith('/'):
            self.current_folder = os.path.join(self.current_folder, item_name)
            if not self.current_folder.endswith('/'):
                self.current_folder += '/'
            self.update_file_list()
            return
        file_inside = os.path.join(self.current_folder, item_name)
        try:
            if self._is_zip_based():
                def _read(pwd):
                    with open_zip(self.archive_name, 'r') as (archive, _):
                        if pwd:
                            archive.setpassword(pwd)
                        return archive.read(file_inside)
                try:
                    data = _read(self.zip_password)
                except RuntimeError:
                    if self.prompt_zip_password():
                        data = _read(self.zip_password)
                    else:
                        self.show_error_dialog('Файл защищён паролем.')
                        return
            elif self.archive_name.lower().endswith('.tar'):
                with tarfile.open(self.archive_name, 'r') as archive:
                    member = archive.getmember(file_inside)
                    data = archive.extractfile(member).read() if member is not None else None
            else:
                data = None
            if data is None:
                return

            fd, tmp_path = tempfile.mkstemp(suffix=os.path.splitext(item_name)[1])
            with os.fdopen(fd, 'wb') as f:
                f.write(data)
            if sys.platform.startswith('win'):
                os.startfile(tmp_path)
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', tmp_path])
            else:
                subprocess.Popen(['xdg-open', tmp_path])
        except RuntimeError:
            self.show_error_dialog('Файл защищён паролем.')

    def on_create_folder(self, event):
        if not self.archive_name:
            self.show_error_dialog(self.get_translation("Сначала откройте архив."))
            return
        dialog = wx.TextEntryDialog(self, self.get_translation("Введите имя папки:"), self.get_translation("Создание папки"), "")
        if dialog.ShowModal() == wx.ID_OK:
            folder_name = dialog.GetValue() + '/'
            if folder_name:
                try:
                    if self._is_zip_based():
                        with open_zip(self.archive_name, 'a') as (archive, _):
                            archive.writestr(os.path.join(self.current_folder, folder_name), b'')
                    elif self.archive_name.lower().endswith('.tar'):
                        with tarfile.open(self.archive_name, 'a') as archive:
                            archive.addfile(tarfile.TarInfo(os.path.join(self.current_folder, folder_name)))
                    self.show_info_dialog(f"{self.get_translation('Папка')} '{folder_name}' {self.get_translation('создана.')}" )
                    self.update_file_list()
                except Exception as e:
                    self.show_error_dialog(str(e))

    def on_select_archive(self, event):
        wildcard = "Архивы (*.zip;*.tar;*.arc)|*.zip;*.tar;*.arc"
        with wx.FileDialog(self, self.get_translation("Выберите архив"), wildcard=wildcard, style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            self.archive_name = fileDialog.GetPath()
            self.current_folder = ""
            self.status_bar.SetStatusText(f"{self.get_translation('Открыт архив:')} {self.archive_name}")
            self.update_file_list()

    def on_create_archive(self, event):
        wildcard = "Архивы (*.zip;*.tar;*.arc)|*.zip;*.tar;*.arc"
        with wx.FileDialog(self, self.get_translation("Создать архив"), wildcard=wildcard, style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT) as fileDialog:
            if fileDialog.ShowModal() == wx.ID_CANCEL:
                return
            self.archive_name = fileDialog.GetPath()
            self.current_folder = ""
            self.status_bar.SetStatusText(f"{self.get_translation('Создание архива:')} {self.archive_name}")
            try:
                if self._is_zip_based():
                    with open_zip(self.archive_name, 'w') as (archive, _):
                        pass
                elif self.archive_name.lower().endswith('.tar'):
                    with tarfile.open(self.archive_name, 'w') as archive:
                        pass
                self.show_info_dialog(f"{self.get_translation('Архив')} {self.archive_name} {self.get_translation('создан.')}" )
            except Exception as e:
                self.show_error_dialog(str(e))
            self.update_file_list()

    def on_add_file_or_folder(self, event):
        if not self.archive_name:
            self.show_error_dialog(self.get_translation("Сначала откройте архив."))
            return
        options = wx.MessageBox(
            f"{self.get_translation('Добавить файл (OK) или папку (Cancel)?')}",
            self.get_translation("Выбор"),
            wx.OK | wx.CANCEL | wx.ICON_QUESTION,
        )
        if options == wx.OK:
            with wx.FileDialog(self, self.get_translation("Выберите файл для добавления"), wildcard="*.*", style=wx.FD_OPEN | wx.FD_MULTIPLE) as fileDialog:
                if fileDialog.ShowModal() == wx.ID_OK:
                    paths = fileDialog.GetPaths()
                    try:
                        if self._is_zip_based():
                            with open_zip(self.archive_name, 'a') as (archive, _):
                                for file_path in paths:
                                    arcname = os.path.join(self.current_folder, os.path.basename(file_path))
                                    archive.write(file_path, arcname)
                        elif self.archive_name.lower().endswith('.tar'):
                            with tarfile.open(self.archive_name, 'a') as archive:
                                for file_path in paths:
                                    archive.add(file_path, os.path.join(self.current_folder, os.path.basename(file_path)))
                        self.show_info_dialog(self.get_translation("Файлы добавлены в архив."))
                    except Exception as e:
                        self.show_error_dialog(str(e))
        elif options == wx.CANCEL:
            with wx.DirDialog(self, self.get_translation("Выберите папку для добавления"), style=wx.DD_DEFAULT_STYLE) as dirDialog:
                if dirDialog.ShowModal() == wx.ID_OK:
                    folder_path = dirDialog.GetPath()
                    try:
                        if self._is_zip_based():
                            with open_zip(self.archive_name, 'a') as (archive, _):
                                for root, dirs, files in os.walk(folder_path):
                                    for file in files:
                                        file_path = os.path.join(root, file)
                                        arcname = os.path.relpath(file_path, start=folder_path)
                                        archive.write(file_path, os.path.join(self.current_folder, arcname))
                        elif self.archive_name.lower().endswith('.tar'):
                            with tarfile.open(self.archive_name, 'a') as archive:
                                for root, dirs, files in os.walk(folder_path):
                                    for file in files:
                                        file_path = os.path.join(root, file)
                                        arcname = os.path.relpath(file_path, start=folder_path)
                                        archive.add(file_path, os.path.join(self.current_folder, arcname))
                        self.show_info_dialog(self.get_translation("Папка и файлы добавлены в архив."))
                    except Exception as e:
                        self.show_error_dialog(str(e))
        self.update_file_list()

    def on_extract_all(self, event):
        if not self.archive_name:
            self.show_error_dialog(self.get_translation("Сначала откройте архив."))
            return
        with wx.DirDialog(self, self.get_translation("Выберите папку для извлечения"), style=wx.DD_DEFAULT_STYLE) as dirDialog:
            if dirDialog.ShowModal() == wx.ID_CANCEL:
                return
            extract_path = dirDialog.GetPath()
            def _do_extract(pwd):
                if self._is_zip_based():
                    with open_zip(self.archive_name, 'r') as (archive, _):
                        if pwd:
                            archive.setpassword(pwd)
                        for fi in archive.infolist():
                            if fi.filename == '.archivator_comment.txt':
                                continue
                            archive.extract(fi, extract_path)
                elif self.archive_name.lower().endswith('.tar'):
                    with tarfile.open(self.archive_name, 'r') as archive:
                        for member in archive.getmembers():
                            if member.name == '.archivator_comment.txt':
                                continue
                            archive.extract(member, extract_path)
            try:
                _do_extract(None)
                self.show_info_dialog(f"{self.get_translation('Все файлы извлечены в')} {extract_path}.")
            except RuntimeError:
                if self.prompt_zip_password():
                    try:
                        _do_extract(self.zip_password)
                        self.show_info_dialog(f"{self.get_translation('Все файлы извлечены в')} {extract_path}.")
                    except Exception as e:
                        self.show_error_dialog(str(e))
                else:
                    self.show_error_dialog('Файл защищён паролем.')
            except zipfile.BadZipFile:
                self.show_error_dialog(self.get_translation("Некорректный zip файл."))

    def on_extract_selected(self, event):
        if not self.archive_name:
            self.show_error_dialog(self.get_translation("Сначала откройте архив."))
            return
        selected_items = self.list_ctrl.GetSelectedItemCount()
        if selected_items == 0:
            self.show_error_dialog(self.get_translation("Выберите хотя бы один файл для извлечения."))
            return
        with wx.DirDialog(self, self.get_translation("Выберите папку для извлечения"), style=wx.DD_DEFAULT_STYLE) as dirDialog:
            if dirDialog.ShowModal() == wx.ID_CANCEL:
                return
            extract_path = dirDialog.GetPath()

            def _do_extract_selected(pwd):
                if self._is_zip_based():
                    with open_zip(self.archive_name, 'r') as (archive, _):
                        if pwd:
                            archive.setpassword(pwd)
                        for index in range(self.list_ctrl.GetItemCount()):
                            if self.list_ctrl.IsSelected(index):
                                file_name = os.path.join(self.current_folder, self.list_ctrl.GetItemText(index))
                                archive.extract(file_name, extract_path)
                elif self.archive_name.lower().endswith('.tar'):
                    with tarfile.open(self.archive_name, 'r') as archive:
                        for index in range(self.list_ctrl.GetItemCount()):
                            if self.list_ctrl.IsSelected(index):
                                file_name = os.path.join(self.current_folder, self.list_ctrl.GetItemText(index))
                                archive.extract(file_name, extract_path)
            try:
                _do_extract_selected(None)
                self.show_info_dialog(f"{self.get_translation('Файлы извлечены в')} {extract_path}.")
            except RuntimeError:
                    if self.prompt_zip_password():
                        try:
                            _do_extract_selected(self.zip_password)
                            self.show_info_dialog(f"{self.get_translation('Файлы извлечены в')} {extract_path}.")
                        except Exception as e:
                            self.show_error_dialog(str(e))
                    else:
                        self.show_error_dialog(self.get_translation('Файл защищён паролем.'))
            except zipfile.BadZipFile:
                self.show_error_dialog(self.get_translation("Некорректный zip файл."))

    def delete_selected_file(self, event):
        selected_items = self.list_ctrl.GetSelectedItemCount()
        if selected_items == 0:
            self.show_error_dialog(self.get_translation("Выберите файл для удаления."))
            return
        selected_file_names = [
            os.path.join(self.current_folder, self.list_ctrl.GetItemText(i))
            for i in range(self.list_ctrl.GetItemCount())
            if self.list_ctrl.IsSelected(i)
        ]
        if wx.MessageBox(
            f"{self.get_translation('Вы уверены, что хотите удалить')} {len(selected_file_names)} {self.get_translation('файл(ов)?')}",
            self.get_translation("Удаление"),
            wx.YES_NO | wx.ICON_WARNING,
        ) == wx.NO:
            return
        try:
            if self._is_zip_based():
                with open_zip(self.archive_name, 'r') as (archive, _):
                    entries = [fi for fi in archive.infolist() if fi.filename not in selected_file_names]
                    data = {fi.filename: archive.read(fi.filename) for fi in entries if not fi.filename.endswith('/')}
                with open_zip(self.archive_name, 'w') as (new_arc, _):
                    for fi in entries:
                        if fi.filename.endswith('/'):
                            new_arc.writestr(fi.filename, b'')
                        else:
                            new_arc.writestr(fi.filename, data[fi.filename])
            elif self.archive_name.lower().endswith('.tar'):
                with tarfile.open(self.archive_name, 'r') as archive, \
                     tarfile.open(self.archive_name + '.tmp', 'w') as temp_tar:
                    for member in archive.getmembers():
                        if member.name not in selected_file_names:
                            if member.isfile():
                                fileobj = archive.extractfile(member)
                                temp_tar.addfile(member, fileobj)
                                fileobj.close()
                            else:
                                temp_tar.addfile(member)
                os.replace(self.archive_name + '.tmp', self.archive_name)
            self.show_info_dialog(self.get_translation("Файлы удалены."))
            self.update_file_list()
        except Exception as e:
            self.show_error_dialog(str(e))

    def on_exit(self, event):
        self.Close(True)

    def show_comment(self, comment):
        if comment:
            self.comment_text.SetValue(comment)
            self.comment_panel.Show()
            self.panel.Layout()
        else:
            self.comment_panel.Hide()
            self.panel.Layout()

    def read_archive_comment(self):
        if not self.archive_name:
            return ""
        if self._is_zip_based():
            try:
                with open_zip(self.archive_name, 'r') as (archive, _):
                    comment = archive.comment.decode('utf-8', errors='ignore') if archive.comment else ""
                    return comment
            except Exception:
                return ""
        elif self.archive_name.lower().endswith('.tar'):
            try:
                with tarfile.open(self.archive_name, 'r') as archive:
                    try:
                        member = archive.getmember('.archivator_comment.txt')
                        fileobj = archive.extractfile(member)
                        if fileobj:
                            comment = fileobj.read().decode('utf-8', errors='ignore')
                            fileobj.close()
                            return comment
                    except KeyError:
                        return ""
            except Exception:
                return ""
        return ""

    def update_file_list(self):
        self.list_ctrl.DeleteAllItems()
        def insert_entry(name, size="", dt=None):
            idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), name)
            if size:
                self.list_ctrl.SetItem(idx, 1, size)
            if dt is not None:
                self.list_ctrl.SetItem(idx, 2, dt.strftime("%Y-%m-%d %H:%M:%S"))
        try:
            entries = {}
            if self._is_zip_based():
                with open_zip(self.archive_name, 'r') as (archive, _):
                    for fi in archive.infolist():
                        if not fi.filename.startswith(self.current_folder):
                            continue
                        rel = fi.filename[len(self.current_folder):]
                        if rel == "":
                            continue
                        parts = rel.split('/', 1)
                        top = parts[0]
                        if len(parts) == 1:
                            entries[top] = (str(fi.file_size), datetime(*fi.date_time), False)
                        else:
                            folder_key = top + '/'
                            if folder_key not in entries:
                                entries[folder_key] = ("", None, True)
            elif self.archive_name.lower().endswith('.tar'):
                with tarfile.open(self.archive_name, 'r') as archive:
                    for fi in archive.getmembers():
                        if not fi.name.startswith(self.current_folder):
                            continue
                        rel = fi.name[len(self.current_folder):]
                        if rel == "":
                            continue
                        parts = rel.split('/', 1)
                        top = parts[0]
                        if len(parts) == 1 and not fi.isdir():
                            entries[top] = (str(fi.size), datetime.fromtimestamp(fi.mtime), False)
                        else:
                            folder_key = top + '/'
                            if folder_key not in entries:
                                entries[folder_key] = ("", None, True)
            if self.current_folder:
                insert_entry('..')
            for name, (size, dt, is_dir) in sorted(entries.items(), key=lambda x: (not x[1][2], x[0].lower())):
                insert_entry(name, size, dt)
            self.status_bar.SetStatusText(f"{self.get_translation('Файлы загружены из')} {self.archive_name}.")
        except Exception as e:
            self.show_error_dialog(str(e))
        comment = self.read_archive_comment()
        self.show_comment(comment)
        self.update_comment_button_state()
        self.update_password_button_state()

    def on_search_file(self, event):
        dialog = wx.TextEntryDialog(self, self.get_translation("Введите имя файла для поиска:"), self.get_translation("Поиск файла"), "")
        if dialog.ShowModal() == wx.ID_OK:
            search_text = dialog.GetValue().lower()
            self.search_in_archive(search_text)
        dialog.Destroy()

    def search_in_archive(self, search_text):
        if not self.archive_name:
            self.show_error_dialog(self.get_translation("Сначала откройте архив."))
            return
        self.list_ctrl.DeleteAllItems()
        try:
            found = False
            if self._is_zip_based():
                with open_zip(self.archive_name, 'r') as (archive, _):
                    for file_info in archive.infolist():
                        if search_text in file_info.filename.lower():
                            found = True
                            display_name = file_info.filename[len(self.current_folder):] if self.current_folder else file_info.filename
                            index = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), display_name)
                            self.list_ctrl.SetItem(index, 1, str(file_info.file_size))
                            date_time = datetime(*file_info.date_time)
                            self.list_ctrl.SetItem(index, 2, date_time.strftime("%Y-%m-%d %H:%M:%S"))
            elif self.archive_name.lower().endswith('.tar'):
                with tarfile.open(self.archive_name, 'r') as archive:
                    for file_info in archive.getmembers():
                        if search_text in file_info.name.lower():
                            found = True
                            display_name = file_info.name[len(self.current_folder):] if self.current_folder else file_info.name
                            index = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), display_name)
                            self.list_ctrl.SetItem(index, 1, str(file_info.size))
                            date_time = datetime.fromtimestamp(file_info.mtime)
                            self.list_ctrl.SetItem(index, 2, date_time.strftime("%Y-%m-%d %H:%M:%S"))
            if not found:
                self.show_info_dialog(self.get_translation("Файл не найден."))
        except Exception as e:
            self.show_error_dialog(str(e))

    def _is_zip_based(self):
        return self.archive_name.lower().endswith(('.zip', '.arc'))

    def _zip_compression(self):
        return compression_for(self.archive_name)

    def handle_drop(self, filenames):
        if not self.archive_name:
            self.show_error_dialog(self.get_translation("Сначала откройте архив."))
            return
        try:
            if self._is_zip_based():
                with open_zip(self.archive_name, 'a') as (archive, _):
                    for path in filenames:
                        if os.path.isfile(path):
                            arcname = os.path.join(self.current_folder, os.path.basename(path))
                            archive.write(path, arcname)
                        elif os.path.isdir(path):
                            for root, _, files in os.walk(path):
                                for file in files:
                                    file_path = os.path.join(root, file)
                                    arcname = os.path.relpath(file_path, start=path)
                                    archive.write(file_path, os.path.join(self.current_folder, arcname))
            elif self.archive_name.lower().endswith('.tar'):
                with tarfile.open(self.archive_name, 'a') as archive:
                    for path in filenames:
                        if os.path.isfile(path):
                            archive.add(path, os.path.join(self.current_folder, os.path.basename(path)))
                        elif os.path.isdir(path):
                            archive.add(path, os.path.join(self.current_folder, os.path.basename(path)))
            self.show_info_dialog(self.get_translation("Файлы добавлены в архив."))
            self.update_file_list()
        except Exception as e:
            self.show_error_dialog(str(e))

    def on_list_context_menu(self, event):
        menu = wx.Menu()
        open_item = menu.Append(wx.ID_OPEN, self.get_translation("Открыть"))
        rename_item = menu.Append(wx.ID_ANY, self.get_translation("Переименовать"))
        extract_item = menu.Append(wx.ID_ANY, self.get_translation("Извлечь выбранное"))
        delete_item = menu.Append(wx.ID_DELETE, self.get_translation("Удалить"))
        menu.AppendSeparator()
        password_item = menu.Append(wx.ID_ANY, self.get_translation("Установить пароль"))
        comment_item = menu.Append(wx.ID_ANY, self.get_translation("Комментарий"))
        if not self.archive_name:
            menu.Enable(open_item.GetId(), False)
            menu.Enable(rename_item.GetId(), False)
            menu.Enable(extract_item.GetId(), False)
            menu.Enable(delete_item.GetId(), False)
            menu.Enable(password_item.GetId(), False)
            menu.Enable(comment_item.GetId(), False)
        else:
            if not self._is_zip_based():
                menu.Enable(password_item.GetId(), False)
        self.Bind(wx.EVT_MENU, self.on_item_double_click, open_item)
        self.Bind(wx.EVT_MENU, self.on_rename_file, rename_item)
        self.Bind(wx.EVT_MENU, self.on_extract_selected, extract_item)
        self.Bind(wx.EVT_MENU, self.delete_selected_file, delete_item)
        self.Bind(wx.EVT_MENU, self.on_set_password, password_item)
        self.Bind(wx.EVT_MENU, self.on_comment, comment_item)
        self.PopupMenu(menu)
        menu.Destroy()

    def on_list_key_down(self, event):
        key = event.GetKeyCode()
        ctrl = event.ControlDown()
        shift = event.ShiftDown()
        if key == wx.WXK_RETURN:
            self.on_item_double_click(None)
        elif key == wx.WXK_DELETE:
            self.delete_selected_file(None)
        elif key == wx.WXK_F2:
            self.on_rename_file(None)
        elif ctrl and key == ord('K'):
            self.on_comment(None)
        elif ctrl and shift and key == ord('E'):
            self.on_extract_selected(None)
        else:
            event.Skip()

    def on_comment(self, event):
        if not self.archive_name:
            self.show_error_dialog(self.get_translation("Сначала откройте архив."))
            return
        comment = self.read_archive_comment()
        dlg = wx.Dialog(self, title=self.get_translation("Комментарий"), size=(400, 300))
        vbox = wx.BoxSizer(wx.VERTICAL)
        label = wx.StaticText(dlg, label=self.get_translation("Комментарий к архиву:"))
        vbox.Add(label, 0, wx.ALL, 10)
        text_ctrl = wx.TextCtrl(dlg, value=comment, style=wx.TE_MULTILINE, size=(350, 150))
        vbox.Add(text_ctrl, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        btn_save = wx.Button(dlg, wx.ID_OK, self.get_translation("Сохранить"))
        btn_cancel = wx.Button(dlg, wx.ID_CANCEL, self.get_translation("Отмена"))
        hbox.Add(btn_save, 0, wx.ALL, 10)
        hbox.Add(btn_cancel, 0, wx.ALL, 10)
        vbox.Add(hbox, 0, wx.ALIGN_CENTER)
        dlg.SetSizer(vbox)
        if dlg.ShowModal() == wx.ID_OK:
            new_comment = text_ctrl.GetValue()
            try:
                self.save_archive_comment(new_comment)
                self.show_comment(new_comment)
                self.show_info_dialog(self.get_translation("Комментарий сохранён."))
            except Exception as e:
                self.show_error_dialog(self.get_translation("Ошибка при сохранении комментария: ") + str(e))
        dlg.Destroy()

    def save_archive_comment(self, comment):
        if not self.archive_name:
            return
        if self._is_zip_based():
            try:
                with open_zip(self.archive_name, 'a') as (archive, _):
                    archive.comment = comment.encode('utf-8')
            except Exception:
                pass
        elif self.archive_name.lower().endswith('.tar'):
            import io
            temp_path = self.archive_name + '.tmp'
            with tarfile.open(self.archive_name, 'r') as archive, \
                 tarfile.open(temp_path, 'w') as new_archive:
                for member in archive.getmembers():
                    if member.name == '.archivator_comment.txt':
                        continue
                    fileobj = archive.extractfile(member) if member.isfile() else None
                    if fileobj:
                        new_archive.addfile(member, fileobj)
                        fileobj.close()
                    else:
                        new_archive.addfile(member)
                comment_bytes = comment.encode('utf-8')
                info = tarfile.TarInfo('.archivator_comment.txt')
                info.size = len(comment_bytes)
                new_archive.addfile(info, io.BytesIO(comment_bytes))
            os.replace(temp_path, self.archive_name)

    def update_comment_button_state(self):
        if hasattr(self, 'comment_tool'):
            tb = self.GetToolBar()
            if not self.archive_name:
                tb.EnableTool(self.comment_tool.GetId(), False)
            else:
                tb.EnableTool(self.comment_tool.GetId(), True)

    def update_password_button_state(self):
        if hasattr(self, 'password_tool'):
            tb = self.GetToolBar()
            # Кнопка доступна только для ZIP
            if not self.archive_name or not self._is_zip_based():
                tb.EnableTool(self.password_tool.GetId(), False)
            else:
                tb.EnableTool(self.password_tool.GetId(), True)

    def on_rename_file(self, event):
        
        if not self.archive_name:
            self.show_error_dialog(self.get_translation("Сначала откройте архив."))
            return

        selected_count = self.list_ctrl.GetSelectedItemCount()
        if selected_count == 0:
            self.show_error_dialog(self.get_translation("Выберите файл для переименования."))
            return
        if selected_count > 1:
            self.show_error_dialog(self.get_translation("Переименовать можно только один файл за раз."))
            return

    
        selected_index = self.list_ctrl.GetFirstSelected()
        old_display_name = self.list_ctrl.GetItemText(selected_index)

    
        if old_display_name in ("..", ""):
            return

 
        dlg = wx.TextEntryDialog(self, self.get_translation("Введите новое имя файла:"),
                                 self.get_translation("Переименовать"),
                                 value=old_display_name.rstrip("/"))
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        new_name_input = dlg.GetValue().strip()
        dlg.Destroy()

        
        is_dir = old_display_name.endswith('/')
        if is_dir and not new_name_input.endswith('/'):
            new_name_input += '/'
        if not is_dir and new_name_input.endswith('/'):
            new_name_input = new_name_input.rstrip('/')

        if not new_name_input or new_name_input == old_display_name:
            return

        old_full = os.path.join(self.current_folder, old_display_name)
        new_full = os.path.join(self.current_folder, new_name_input)

        try:
            if self._is_zip_based():
               
                with open_zip(self.archive_name, 'r') as (archive, _):
                    entries = archive.infolist()
                    data_map = {}
                    for fi in entries:
                        if fi.filename.endswith('/'):
                            continue  
                        data_map[fi.filename] = archive.read(fi.filename)

             
                if new_full in [fi.filename for fi in entries]:
                    self.show_error_dialog(self.get_translation("Файл с таким именем уже существует."))
                    return

                with open_zip(self.archive_name, 'w') as (new_arc, _):
                    for fi in entries:
                        original_name = fi.filename
                        if is_dir:
                            if original_name.startswith(old_full):
                                replaced_name = new_full + original_name[len(old_full):]
                            else:
                                replaced_name = original_name
                        else:
                            replaced_name = new_full if original_name == old_full else original_name

                        if original_name.endswith('/'):
                            new_arc.writestr(replaced_name, b'')
                        else:
                            new_arc.writestr(replaced_name, data_map[original_name])

            elif self.archive_name.lower().endswith('.tar'):
                temp_path = self.archive_name + '.tmp'
                with tarfile.open(self.archive_name, 'r') as archive, \
                     tarfile.open(temp_path, 'w') as new_archive:

                    for member in archive.getmembers():
                        original_name = member.name

                        if is_dir:
                            if original_name.startswith(old_full):
                                member.name = new_full + original_name[len(old_full):]
                        else:
                            if original_name == old_full:
                                member.name = new_full

                        fileobj = archive.extractfile(member) if member.isfile() else None
                        if fileobj:
                            new_archive.addfile(member, fileobj)
                            fileobj.close()
                        else:
                            new_archive.addfile(member)

                os.replace(temp_path, self.archive_name)

            else:
                self.show_error_dialog(self.get_translation("Неподдерживаемый формат архива."))
                return

            self.show_info_dialog(self.get_translation("Файл переименован."))
            self.update_file_list()
        except Exception as e:
            self.show_error_dialog(str(e))

    def format_size(self, size):
        if size >= 1024 ** 3:
            return f"{size / (1024 ** 3):.1f} ГБ"
        elif size >= 1024 ** 2:
            return f"{size / (1024 ** 2):.1f} МБ"
        elif size >= 1024:
            return f"{size / 1024:.1f} КБ"
        else:
            return f"{size} байт"


if __name__ == "__main__":
    app = wx.App(False)
    Archiver(None, "Архиватор")
    app.MainLoop()