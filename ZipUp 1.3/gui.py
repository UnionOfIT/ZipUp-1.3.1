import os
import sys
import json
import zipfile
import tarfile
from datetime import datetime

import wx

from translations import get_translation
from arc_utils import open_zip, compression_for

try:
    _ZIP_ZSTD = zipfile.ZIP_ZSTD
except AttributeError:
    _ZIP_ZSTD = None


class Archiver(wx.Frame):

    def __init__(self, parent, title):

        self.config_dir = os.path.join(os.getenv('LOCALAPPDATA'), 'Archiver')
        self.config_path = os.path.join(self.config_dir, 'config.json')
        self.load_config()

        super().__init__(parent, title=self.get_translation(title), size=(900, 700))

        self.current_directory = os.path.dirname(os.path.abspath(__file__))
        self.SetIcon(self.load_icon('archive.png', wx.ART_FILE_OPEN))

        self.archive_name: str = ""
        self.current_folder: str = ""

        self.panel = wx.Panel(self)
        self.panel.SetBackgroundColour(wx.Colour(245, 245, 245))

        self.create_menu()
        self.create_toolbar()
        self.create_main_area()
        self.create_status_bar()

        self.Show()

    def load_config(self):

        if not os.path.exists(self.config_dir):
            os.makedirs(self.config_dir)
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    self.language = config.get('language', 'ru')
            except Exception:
                self.language = 'ru'
        else:
            self.language = 'ru'
            self.save_config()

    def save_config(self):

        config = {'language': self.language}
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.show_error_dialog(f"{self.get_translation('Ошибка сохранения конфига: ')}{str(e)}")

    def get_translation(self, text: str) -> str:
        return get_translation(self.language, text)

    def restart_application(self):
        python = sys.executable
        os.execl(python, python, *sys.argv)

    def load_icon(self, filename: str, fallback_art):
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
        self.toolsMenu.Append(wx.ID_ANY, self.get_translation("Обратная связь"), self.get_translation("Связь с разработчиком"))
        self.toolsMenu.Append(wx.ID_ANY, self.get_translation("Настройки"), self.get_translation("Настройки приложения"))

        self.Bind(wx.EVT_MENU, self.on_open_settings, id=self.toolsMenu.FindItemByPosition(5).GetId())
        self.Bind(wx.EVT_MENU, self.on_add_file_or_folder, id=self.toolsMenu.FindItemByPosition(0).GetId())
        self.Bind(wx.EVT_MENU, self.on_extract_all, id=self.toolsMenu.FindItemByPosition(1).GetId())
        self.Bind(wx.EVT_MENU, self.on_extract_selected, id=self.toolsMenu.FindItemByPosition(2).GetId())
        self.Bind(wx.EVT_MENU, self.on_create_folder, id=self.toolsMenu.FindItemByPosition(3).GetId())
        self.Bind(wx.EVT_MENU, self.on_feedback, id=self.toolsMenu.FindItemByPosition(4).GetId())

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
        toolbar.Realize()

        self.Bind(wx.EVT_TOOL, self.on_create_archive, id=wx.ID_NEW)
        self.Bind(wx.EVT_TOOL, self.on_select_archive, id=wx.ID_OPEN)
        self.Bind(wx.EVT_TOOL, self.on_add_file_or_folder, id=wx.ID_ADD)
        self.Bind(wx.EVT_TOOL, self.on_extract_all, id=wx.ID_EXECUTE)
        self.Bind(wx.EVT_TOOL, self.on_search_file, id=search_tool.GetId())
        self.Bind(wx.EVT_TOOL, self.delete_selected_file, id=delete_tool.GetId())

    def create_main_area(self):
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.list_ctrl = wx.ListCtrl(self.panel, style=wx.LC_REPORT | wx.BORDER_SUNKEN)
        self.list_ctrl.InsertColumn(0, self.get_translation("Имя файла/папки"), width=400)
        self.list_ctrl.InsertColumn(1, self.get_translation("Размер"), width=90)
        self.list_ctrl.InsertColumn(2, self.get_translation("Дата изменения"), width=120)
        sizer.Add(self.list_ctrl, 1, wx.EXPAND | wx.ALL, 10)
        self.panel.SetSizer(sizer)
        self.list_ctrl.Bind(wx.EVT_LIST_ITEM_ACTIVATED, self.on_item_double_click)

        # Drag-and-drop support
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

    def on_open_settings(self, event):
        dialog = wx.SingleChoiceDialog(
            self,
            self.get_translation("Выберите язык:"),
            self.get_translation("Настройки языка"),
            ["Русский", "English"]
        )
        current_selection = 0 if self.language == 'ru' else 1
        dialog.SetSelection(current_selection)
        if dialog.ShowModal() == wx.ID_OK:
            selection = dialog.GetStringSelection()
            old_language = self.language
            self.language = 'ru' if selection == "Русский" else 'en'
            if old_language != self.language:
                self.save_config()
                dialog.Destroy()
                wx.MessageBox(
                    self.get_translation("Язык изменен. Программа будет перезапущена."),
                    self.get_translation("Информация"),
                    wx.OK | wx.ICON_INFORMATION,
                )
                self.Close()
                self.restart_application()
            else:
                dialog.Destroy()
        else:
            dialog.Destroy()

    def on_feedback(self, event):
        wx.MessageBox(
            "Для обратной связи свяжитесь со мной в Discord: nonamecgalockoi",
            self.get_translation("Обратная связь"),
            wx.OK | wx.ICON_INFORMATION,
        )

    def on_item_double_click(self, event):
        item = event.GetItem()
        item_name = item.GetText()
        if item_name == '..':
            # Вверх
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
                with open_zip(self.archive_name, 'r') as (archive, _):
                    data = archive.read(file_inside)
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
            def _do_extract(pwd: bytes | None):
                if self._is_zip_based():
                    with open_zip(self.archive_name, 'r') as (archive, _):
                        archive.extractall(extract_path)
                elif self.archive_name.lower().endswith('.tar'):
                    with tarfile.open(self.archive_name, 'r') as archive:
                        archive.extractall(extract_path)
            try:
                _do_extract(None) # Removed password handling
                self.show_info_dialog(f"{self.get_translation('Все файлы извлечены в')} {extract_path}.")
            except RuntimeError:
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
            def _do_extract_selected(pwd: bytes | None):
                if self._is_zip_based():
                    with open_zip(self.archive_name, 'r') as (archive, _):
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
                _do_extract_selected(None) # Removed password handling
                self.show_info_dialog(f"{self.get_translation('Файлы извлечены в')} {extract_path}.")
            except RuntimeError:
                self.show_error_dialog('Файл защищён паролем.')
            except zipfile.BadZipFile:
                self.show_error_dialog(self.get_translation("Некорректный zip файл."))

    def delete_selected_file(self, event):
        """Удаляет выбранные элементы из архива (поддерживает .zip/.arc/.tar)."""
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
                # читаем исходный архив
                with open_zip(self.archive_name, 'r') as (archive, _):
                    entries = [fi for fi in archive.infolist() if fi.filename not in selected_file_names]
                    data = {fi.filename: archive.read(fi.filename) for fi in entries if not fi.filename.endswith('/')}

                # перезаписываем
                with open_zip(self.archive_name, 'w') as (new_arc, _):
                    for fi in entries:
                        if fi.filename.endswith('/'):
                            new_arc.writestr(fi.filename, b'')
                        else:
                            new_arc.writestr(fi.filename, data[fi.filename])

            elif self.archive_name.lower().endswith('.tar'):
                temp_members = []
                with tarfile.open(self.archive_name, 'r') as archive:
                    for member in archive.getmembers():
                        if member.name not in selected_file_names:
                            temp_members.append((member, archive.extractfile(member)))
                with tarfile.open(self.archive_name + '.tmp', 'w') as temp_tar:
                    for member, fileobj in temp_members:
                        temp_tar.addfile(member, fileobj)
                os.replace(self.archive_name + '.tmp', self.archive_name)

            self.show_info_dialog(self.get_translation("Файлы удалены."))
            self.update_file_list()
        except Exception as e:
            self.show_error_dialog(str(e))

    def on_exit(self, event):
        self.Close(True)

    def update_file_list(self):
        self.list_ctrl.DeleteAllItems()

        def insert_entry(name: str, size: str = "", dt: datetime | None = None):
            idx = self.list_ctrl.InsertItem(self.list_ctrl.GetItemCount(), name)
            if size:
                self.list_ctrl.SetItem(idx, 1, size)
            if dt is not None:
                self.list_ctrl.SetItem(idx, 2, dt.strftime("%Y-%m-%d %H:%M:%S"))

        try:
            entries: dict[str, tuple[str, datetime | None, bool]] = {}

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

            # сортировка: папки первыми, затем файлы, по имени
            for name, (size, dt, is_dir) in sorted(entries.items(), key=lambda x: (not x[1][2], x[0].lower())):
                insert_entry(name, size, dt)

            self.status_bar.SetStatusText(f"{self.get_translation('Файлы загружены из')} {self.archive_name}.")
        except Exception as e:
            self.show_error_dialog(str(e))

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

    def _is_zip_based(self) -> bool:

        return self.archive_name.lower().endswith(('.zip', '.arc'))

    def _zip_compression(self):

        return compression_for(self.archive_name)

    def handle_drop(self, filenames: list[str]):
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

if __name__ == "__main__":
    app = wx.App(False)
    Archiver(None, "Архиватор")
    app.MainLoop() 