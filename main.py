#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import curses
import shutil
import subprocess
import locale
import json
from pathlib import Path

# Файл для сохранения последнего посещенного каталога
CD_FILE = os.path.expanduser("~/.tui_fm_last_dir")
# Файл для сохранения позиций курсора по директориям
CURSOR_POSITIONS_FILE = os.path.expanduser("~/.tui_fm_cursor_positions")

# Включаем поддержку локали для корректного отображения Unicode (в том числе кириллицы)
locale.setlocale(locale.LC_ALL, '')

class FileManager:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_dir = os.getcwd()
        self.last_dir = self.current_dir # Запоминаем начальную директорию
        self.cursor_pos = 0
        self.offset = 0
        self.files = []
        self.selected_files = set()
        self.show_hidden = False
        # Словарь для хранения позиций курсора по директориям
        self.cursor_positions = {}
        self.height, self.width = stdscr.getmaxyx()
        self.max_items = self.height - 3  # Оставляем место для заголовка и строки статуса
        curses.curs_set(0)  # Скрываем курсор
        curses.start_color()
        curses.use_default_colors()

    # Кастомные цвета
        curses.init_color(10, 400, 400, 600)  # пастельно-синий
        curses.init_color(11, 500, 500, 500)  # серый
        curses.init_color(12, 550, 500, 300)  # фисташковый
        curses.init_color(13, 1000, 800, 200)  # жёлто-оранжевый
        curses.init_color(14, 300, 300, 300)   # мягкий серый
        curses.init_color(15, 950, 900, 700)    # курсор
        curses.init_color(16, 320, 320, 320) # <--- НОВЫЙ ЦВЕТ: для обычных файлов
    
    # Пары цветов
        curses.init_pair(1, 15, -1)    # курсор
        curses.init_pair(2, 11, -1)  # директории
        curses.init_pair(3, 12, -1)  # фисташковый (для исполняемых)
        curses.init_pair(4, 10, -1)  # ссылки — пастельный синий
        curses.init_pair(5, curses.COLOR_YELLOW, -1) # выделенные
        curses.init_pair(6, curses.COLOR_GREEN, -1)  # copy
        curses.init_pair(7, 13, -1)   # move — жёлто-оранжевый
        curses.init_pair(8, curses.COLOR_RED, -1)    # delete
        curses.init_pair(9, 14, -1)   # сообщения — мягкий серый
        curses.init_pair(10, 16, -1)  # <--- НОВАЯ ПАРА: для обычных файлов (использует цвет 16)
            

        # Буфер (clipboard) для copy/move
        # хранит список полных путей и действие: 'copy' или 'move'
        self.clipboard = []  # список полных путей
        self.clipboard_action = None

        self.load_cursor_positions()
        self.get_files()

    def get_files(self):
        self.files = []
        try:
            if self.show_hidden:
                self.files.extend(sorted(os.listdir(self.current_dir)))
            else:
                self.files.extend(sorted([f for f in os.listdir(self.current_dir) if not f.startswith('.')]))
        except PermissionError:
            self.show_message("Ошибка доступа к директории")
            self.current_dir = os.path.dirname(self.current_dir)
            self.get_files()

    def load_cursor_positions(self):
        """Загружает сохраненные позиции курсора из файла."""
        try:
            if os.path.exists(CURSOR_POSITIONS_FILE):
                with open(CURSOR_POSITIONS_FILE, 'r', encoding='utf-8') as f:
                    self.cursor_positions = json.load(f)
        except Exception:
            self.cursor_positions = {}

    def save_cursor_positions(self):
        """Сохраняет текущие позиции курсора в файл."""
        try:
            with open(CURSOR_POSITIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.cursor_positions, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def save_current_cursor_position(self):
        """Сохраняет текущую позицию курсора для текущей директории."""
        self.cursor_positions[self.current_dir] = {
            'cursor_pos': self.cursor_pos,
            'offset': self.offset
        }

    def restore_cursor_position(self):
        """Восстанавливает позицию курсора для текущей директории."""
        if self.current_dir in self.cursor_positions:
            saved_pos = self.cursor_positions[self.current_dir]
            self.cursor_pos = min(saved_pos['cursor_pos'], len(self.files) - 1)
            self.offset = saved_pos['offset']
            # Корректируем offset если курсор не виден
            if self.cursor_pos < self.offset:
                self.offset = self.cursor_pos
            elif self.cursor_pos >= self.offset + self.max_items:
                self.offset = max(0, self.cursor_pos - self.max_items + 1)

    def draw(self):
        self.stdscr.clear()
        self.height, self.width = self.stdscr.getmaxyx()
        self.max_items = self.height - 3

        # Заголовок + информация о буфере
        clipboard_info = ""
        if self.clipboard:
            clipboard_info = f" | Clipboard: {len(self.clipboard)} item(s) [{self.clipboard_action}]"
        header = f" GFD - {self.current_dir} {clipboard_info} "
        try:
            self.stdscr.addstr(0, 0, header[:self.width-1], curses.A_NORMAL)
        except curses.error:
            pass

        # Список файлов
        line = 2
        for i in range(self.offset, min(len(self.files), self.offset + self.max_items)):
            file_name = self.files[i]
            full_path = os.path.join(self.current_dir, file_name)

            # Определяем цвет строки (для курсора и выделенных)
            if i == self.cursor_pos:
                attr = curses.color_pair(1) # Курсор
            elif file_name in self.selected_files:
                attr = curses.color_pair(5) # Выделенные
            else:
                attr = curses.A_NORMAL # По умолчанию для строки, если не курсор и не выделено

            # Определяем цвет текста файла
            if os.path.isdir(full_path) or file_name == "..":
                file_attr = curses.color_pair(2)  # Директории
            elif os.path.islink(full_path):
                file_attr = curses.color_pair(4)  # Ссылки
            elif os.access(full_path, os.X_OK):
                file_attr = curses.color_pair(3)  # Исполняемые
            else:
                file_attr = curses.color_pair(10) # <--- ЗДЕСЬ назначаем цвет для обычных файлов
            # Отрисовка строки
            try:
                if i == self.cursor_pos or file_name in self.selected_files:
                    self.stdscr.addstr(line, 0, file_name[:self.width-1], attr)
                else:
                    self.stdscr.addstr(line, 0, file_name[:self.width-1], file_attr)
            except curses.error:
                pass

            line += 1

        self.stdscr.refresh()

    def show_message(self, message, wait=True, timeout=None):
                y = self.height // 2
                # центрируем по первой строке (если многострочное, рисуем с последующей строкой)
                lines = message.splitlines() or [""]
                x = max(0, self.width // 2 - max(len(l) for l in lines) // 2)
                try:
                    for i, line in enumerate(lines):
                        self.stdscr.addstr(y + i, x, line[:self.width-1], curses.A_BOLD)
                    self.stdscr.refresh()
                    if timeout is not None:
                        curses.napms(int(timeout * 1000))  # ждём timeout секунд
                    elif wait:
                        self.stdscr.get_wch()  # старое поведение — ждать клавишу
                except curses.error:
                    pass

    def get_input(self, prompt):
            """
            Безопасный ввод строки внизу экрана.
            Рисуем только видимую часть (хвост) строки, очищаем остаток строки и явно перемещаем курсор.
            """
            curses.curs_set(1)
            # Отключаем автоматическое эхо (мы сами рисуем ввод)
            curses.noecho()
            y = self.height - 3
            buffer = []
            try:
                while True:
                    # рассчитываем доступное место для ввода (плюс оставляем 1 колонку в запас)
                    max_input = max(0, self.width - len(prompt) - 1)
                    full = "".join(buffer)
                    # показываем правую (видимую) часть строки
                    visible = full[-max_input:] if max_input > 0 else ""
        
                    try:
                        self.stdscr.move(y, 0)
                        self.stdscr.clrtoeol()
                        # рисуем prompt + видимую часть (ограничиваем длину)
                        self.stdscr.addnstr(y, 0, prompt + visible, self.width - 1)
                        # ставим курсор после видимой части
                        cursor_x = min(len(prompt) + len(visible), max(0, self.width - 1))
                        self.stdscr.move(y, cursor_x)
                        self.stdscr.refresh()
                    except curses.error:
                        pass
        
                    ch = self.stdscr.get_wch()
        
                    # Enter
                    if ch in ("\n", "\r"):
                        break
                    # Escape — отмена ввода
                    if ch == "\x1b":
                        buffer = []
                        break
                    # Backspace (символьные и символьный код)
                    if ch in ("\b", "\x7f") or ch == curses.KEY_BACKSPACE:
                        if buffer:
                            buffer.pop()
                        continue
                    # Обычный вводимый символ (строка)
                    if isinstance(ch, str):
                        buffer.append(ch)
                        continue
                    # Игнорируем прочие управляющие/спец-клавиши
                    # (можно добавить обработку стрелок/вставки, если нужно)
        
            finally:
                # всегда скрываем курсор после ввода
                try:
                    curses.curs_set(0)
                except curses.error:
                    pass
        
            return "".join(buffer)

    def show_help_popup(self):
        """Отображает popup окно с помощью в центре экрана."""
        # Определяем размеры popup окна
        help_lines = [
            "=== GFD - Файловый менеджер ===",
            "",
            "НАВИГАЦИЯ:",
            "  ↑/↓     - Перемещение курсора",
            "  ←       - Назад в родительскую директорию", 
            "  →/Enter - Открыть файл/директорию",
            "",
            "ВЫДЕЛЕНИЕ:",
            "  Space   - Выделить/снять выделение файла",
            "",
            "ОПЕРАЦИИ С ФАЙЛАМИ:",
            "  c       - Копировать в буфер обмена",
            "  m       - Вырезать в буфер обмена",
            "  p       - Вставить из буфера обмена",
            "  x       - Очистить буфер обмена",
            "  d       - Удалить файл/директорию",
            "  r       - Переименовать файл/директорию",
            "  n       - Создать новый файл/директорию",
            "",
            "НАСТРОЙКИ:",
            "  .       - Показать/скрыть скрытые файлы",
            "",
            "СИСТЕМА:",
            "  h       - Показать эту справку",
            "  q       - Выход из программы",
            "",
            "Нажмите любую клавишу для закрытия..."
        ]
        
        # Вычисляем размеры окна
        max_width = max(len(line) for line in help_lines) + 4
        height = len(help_lines) + 2
        
        # Центрируем окно
        start_y = max(0, (self.height - height) // 2)
        start_x = max(0, (self.width - max_width) // 2)
        
        # Создаем окно помощи
        help_win = curses.newwin(height, max_width, start_y, start_x)
        help_win.border()
        help_win.bkgd(' ', curses.color_pair(9))  # Используем цвет для сообщений
        
        # Заполняем окно текстом
        for i, line in enumerate(help_lines):
            try:
                # Выравниваем по левому краю с отступом
                x_pos = 2  # Отступ от левого края
                help_win.addstr(i + 1, x_pos, line[:max_width-4])
            except curses.error:
                pass
        
        # Отображаем окно
        help_win.refresh()
        
        # Ждем нажатия любой клавиши
        self.stdscr.get_wch()
        
        # Очищаем окно
        help_win.clear()
        help_win.refresh()
        del help_win

    def handle_input(self):
        key = self.stdscr.get_wch()

        if key == curses.KEY_UP:
            self.cursor_pos = max(0, self.cursor_pos - 1)
            if self.cursor_pos < self.offset:
                self.offset = max(0, self.offset - 1)

        elif key == curses.KEY_DOWN:
            self.cursor_pos = min(len(self.files) - 1, self.cursor_pos + 1)
            if self.cursor_pos >= self.offset + self.max_items:
                self.offset += 1

        elif key == curses.KEY_LEFT:
            self.navigate_back()

        elif key == curses.KEY_RIGHT:
            self.open_selected_item()

        elif key == "q":
            # Сохраняем текущую позицию курсора
            self.save_current_cursor_position()
            # Сохраняем все позиции в файл
            self.save_cursor_positions()
            
            # Сохраняем текущую директорию для cd on exit, только если она изменилась
            if self.current_dir != self.last_dir:
                try:
                    with open(CD_FILE, 'w') as f:
                        f.write(self.current_dir)
                except Exception:
                    pass
            return False # Выходим из цикла

        elif key == " ":
            if self.cursor_pos < len(self.files):
                fname = self.files[self.cursor_pos]
                if fname in self.selected_files:
                    self.selected_files.remove(fname)
                else:
                    self.selected_files.add(fname)

        elif key == ".":
            # Сохраняем текущую позицию курсора перед переключением
            self.save_current_cursor_position()
            
            self.show_hidden = not self.show_hidden
            self.get_files()
            
            # Восстанавливаем позицию курсора после обновления списка
            self.restore_cursor_position()

        elif key == "r":
            self.rename_item()

        elif key == "c":
            self.copy_to_clipboard()

        elif key == "m":
            self.cut_to_clipboard()

        elif key == "p":
            self.paste_from_clipboard()

        elif key == "x":
            self.clear_clipboard()

        elif key == "d":
            self.delete_items()

        elif key == "n":
            self.create_new_item()

        elif key == "?":
            self.show_help_popup()

        return True


    def open_selected_item(self):
        if self.cursor_pos < len(self.files):
            selected_file = self.files[self.cursor_pos]
            full_path = os.path.join(self.current_dir, selected_file)

            if os.path.isdir(full_path):
                self.change_directory(full_path)
            else:
                self.open_file(full_path)


    def navigate_back(self):
        # Сохраняем текущую позицию курсора перед возвратом
        self.save_current_cursor_position()
        
        parent_dir = os.path.dirname(self.current_dir)
        if parent_dir != self.current_dir:  # Проверяем, что мы не в корневой директории
            self.current_dir = parent_dir
            self.get_files()
            
            # Восстанавливаем позицию курсора для родительской директории
            self.restore_cursor_position()

    def change_directory(self, path):
        # Сохраняем текущую позицию курсора перед сменой директории
        self.save_current_cursor_position()
        
        self.current_dir = os.path.abspath(path)
        self.get_files()
        
        # Восстанавливаем позицию курсора для новой директории
        self.restore_cursor_position()

    def open_file(self, full_path):
                try:
                    # Закрываем окно curses, чтобы терминальный редактор правильно работал
                    curses.endwin()
            
                    # Предпочитаем редактор из переменной окружения GFD_EDITOR,
                    # затем EDITOR, затем пытаемся использовать 'micro' если он в PATH
                    editor = os.environ.get('GFD_EDITOR') or os.environ.get('EDITOR') or None
                    if editor and shutil.which(editor.split()[0]):
                        # Если в EDITOR стоит команда с аргументами — примитивно разбиваем по пробелу
                        cmd = editor.split() + [full_path]
                        subprocess.call(cmd)
                    elif shutil.which('micro'):
                        subprocess.call(['micro', full_path])
                    else:
                        # fallback на поведение по умолчанию (xdg-open / open / os.startfile)
                        if sys.platform.startswith("linux"):
                            subprocess.Popen(["xdg-open", full_path])
                        elif sys.platform == "darwin":
                            subprocess.Popen(["open", full_path])
                        elif sys.platform.startswith("win"):
                            os.startfile(full_path)
                        else:
                            # если платформа неизвестна, показываем сообщение (после восстановления curses)
                            pass
            
                    # Попытка вернуть curses в нормальное состояние
                    try:
                        # иногда достаточно doupdate/refresh
                        curses.doupdate()
                    except Exception:
                        pass
            
                except Exception as e:
                    # Если ещё не вышли из curses, покажем сообщение внутри интерфейса
                    try:
                        self.show_message(f"Ошибка при открытии файла: {e}")
                    except Exception:
                        # как запасной вариант — напечатаем в stderr
                        print(f"Ошибка при открытии файла: {e}", file=sys.stderr)

    def rename_item(self):
        if self.cursor_pos < len(self.files) and self.files[self.cursor_pos] != "..":
            old_name = self.files[self.cursor_pos]
            new_name = self.get_input(f"Переименовать {old_name} в: ")
            if new_name:
                try:
                    os.rename(os.path.join(self.current_dir, old_name),
                              os.path.join(self.current_dir, new_name))
                    self.get_files()
                except Exception as e:
                    self.show_message(f"Ошибка переименования: {e}")

    # --- Clipboard operations ---

    def _get_targets_fullpaths(self):
        """Возвращает список полных путей для текущей селекции или файла под курсором."""
        targets = []
        if self.selected_files:
            for fname in self.selected_files:
                if fname == "..":
                    continue
                targets.append(os.path.join(self.current_dir, fname))
        else:
            if self.cursor_pos < len(self.files):
                fname = self.files[self.cursor_pos]
                if fname != "..":
                    targets.append(os.path.join(self.current_dir, fname))
        return targets

    def copy_to_clipboard(self):
        targets = self._get_targets_fullpaths()
        if not targets:
            self.show_message("Нечего копировать")
            return
        self.clipboard = targets.copy()
        self.clipboard_action = 'copy'
        # можно очистить выделение, чтобы избежать повторного добавления
        self.selected_files.clear()

    def cut_to_clipboard(self):
        targets = self._get_targets_fullpaths()
        if not targets:
            self.show_message("Нечего вырезать")
            return
        self.clipboard = targets.copy()
        self.clipboard_action = 'move'
        self.selected_files.clear()

    def clear_clipboard(self):
        self.clipboard = []
        self.clipboard_action = None

    def _unique_dest(self, dest_path):
        """Если dest_path существует, возвращает уникальный путь с суффиксом _copy, _copy1, ..."""
        if not os.path.exists(dest_path):
            return dest_path
        base, ext = os.path.splitext(dest_path)
        # для директорий ext == ''
        count = 1
        new_path = f"{base}_copy{ext}"
        while os.path.exists(new_path):
            new_path = f"{base}_copy{count}{ext}"
            count += 1
        return new_path

    def paste_from_clipboard(self):
        if not self.clipboard:
            self.show_message("Буфер пуст")
            return

        # Пытаемся вставить все элементы в self.current_dir
        errors = []
        for src in self.clipboard:
            try:
                if not os.path.exists(src):
                    errors.append(f"Исходник не найден: {src}")
                    continue
                name = os.path.basename(src.rstrip(os.sep))
                dest = os.path.join(self.current_dir, name)

                # Защита: если пытаемся переместить директорию в саму себя (или в его потомка)
                if self.clipboard_action == 'move':
                    # Если dest начинается с src + os.sep, то запрещаем
                    src_real = os.path.realpath(src)
                    dest_real = os.path.realpath(dest)
                    if dest_real.startswith(src_real + os.sep) or dest_real == src_real:
                        errors.append(f"Нельзя переместить {name} внутрь него самого")
                        continue

                # Получаем уникальное имя, если нужно
                if os.path.exists(dest):
                    dest = self._unique_dest(dest)

                if os.path.isdir(src):
                    # Копирование/перемещение директорий
                    if self.clipboard_action == 'copy':
                        shutil.copytree(src, dest)
                    else:
                        shutil.move(src, dest)
                else:
                    # Файлы: используем copy2 (копирует метаданные) или move
                    if self.clipboard_action == 'copy':
                        shutil.copy2(src, dest)
                    else:
                        shutil.move(src, dest)

            except Exception as e:
                errors.append(f"{os.path.basename(src)}: {e}")

        # После операции обновляем список
        self.get_files()

        # Если операция была перемещение — очищаем буфер
        if self.clipboard_action == 'move':
            self.clear_clipboard()

        if errors:
            self.show_message("Ошибки:\n" + "\n".join(errors))
        else:
            self.show_message("Операция выполнена", timeout=0.4)

    # --- Конец clipboard operations ---

    def copy_items(self):
        # Старый метод заменён на clipboard-поведение. Оставляем для совместимости:
        self.copy_to_clipboard()

    def move_items(self):
        # Старый метод заменён на clipboard-поведение. Оставляем для совместимости:
        self.cut_to_clipboard()

    def delete_items(self):
        targets = self.selected_files if self.selected_files else {self.files[self.cursor_pos]}
        # Преобразуем в корректный список имён (исключая "..")
        targets = [t for t in targets if t != ".."]
        if not targets:
            self.show_message("Нечего удалять")
            return
        confirm = self.get_input(f"Удалить {', '.join(targets)}? (y/n): ")
        if confirm.lower() == 'y':
            for fname in targets:
                file_to_delete = os.path.join(self.current_dir, fname)
                try:
                    if os.path.isdir(file_to_delete):
                        shutil.rmtree(file_to_delete)
                    else:
                        os.remove(file_to_delete)
                    self.get_files()
                except Exception as e:
                    self.show_message(f"Ошибка удаления {fname}: {e}")
            self.selected_files.clear()

    def create_new_item(self):
        name = self.get_input("Имя нового файла/директории: ")
        if name:
            create_type = self.get_input("Файл (f) или директория (d)? ")
            if create_type.lower() == 'f':
                try:
                    open(os.path.join(self.current_dir, name), 'a').close()
                    self.get_files()
                except Exception as e:
                    self.show_message(f"Ошибка создания файла: {e}")
            elif create_type.lower() == 'd':
                try:
                    os.mkdir(os.path.join(self.current_dir, name))
                    self.get_files()
                except Exception as e:
                    self.show_message(f"Ошибка создания директории: {e}")

    def run(self):
        while True:
            self.draw()
            if not self.handle_input():
                break

def main(stdscr):
    fm = FileManager(stdscr)
    fm.run()

if __name__ == "__main__":
    curses.wrapper(main)



