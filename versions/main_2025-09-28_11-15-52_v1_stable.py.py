#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import curses
import shutil
import subprocess
import locale
from pathlib import Path

# Файл для сохранения последнего посещенного каталога
CD_FILE = os.path.expanduser("~/.tui_fm_last_dir")

# Включаем поддержку локали для корректного отображения Unicode (в том числе кириллицы)
locale.setlocale(locale.LC_ALL, '')

class FileManager:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.current_dir = os.getcwd()
        self.last_dir = self.current_dir # Добавлено: Запоминаем начальную директорию
        self.cursor_pos = 0
        self.offset = 0
        self.files = []
        self.selected_files = set()
        self.show_hidden = False
        self.height, self.width = stdscr.getmaxyx()
        self.max_items = self.height - 4  # Оставляем место для заголовка и строки статуса
        curses.curs_set(0)  # Скрываем курсор
        curses.start_color()
        curses.use_default_colors()
        curses.init_pair(1, curses.COLOR_BLACK, curses.COLOR_RED)   # курсор
        curses.init_pair(2, curses.COLOR_RED, -1)                   # директории
        curses.init_pair(3, curses.COLOR_GREEN, -1)                 # исполняемые
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)  # символические ссылки
        curses.init_pair(5, curses.COLOR_YELLOW, -1)  # выделенные файлы
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

    def draw(self):
        self.stdscr.clear()
        self.height, self.width = self.stdscr.getmaxyx()
        self.max_items = self.height - 4

        # Заголовок
        header = f" GFD - {self.current_dir} "
        self.stdscr.addstr(0, 0, header[:self.width-1], curses.A_REVERSE)

        # Список файлов
        line = 2
        for i in range(self.offset, min(len(self.files), self.offset + self.max_items)):
            file_name = self.files[i]
            full_path = os.path.join(self.current_dir, file_name)

            # Определяем цвет
            if i == self.cursor_pos:
                attr = curses.color_pair(1)
            elif file_name in self.selected_files:
                attr = curses.color_pair(5)
            else:
                attr = curses.A_NORMAL

            if os.path.isdir(full_path) or file_name == "..":
                file_attr = curses.color_pair(2)
            elif os.path.islink(full_path):
                file_attr = curses.color_pair(4)
            elif os.access(full_path, os.X_OK):
                file_attr = curses.color_pair(3)
            else:
                file_attr = curses.A_NORMAL

            # Отрисовка строки
            if i == self.cursor_pos or file_name in self.selected_files:
                self.stdscr.addstr(line, 0, file_name[:self.width-1], attr)
            else:
                self.stdscr.addstr(line, 0, file_name[:self.width-1], file_attr)

            line += 1

        # Строка подсказок
        help_text = " ←: Back | →: Open/Run | q: Quit | c: Copy | m: Move | d: Delete | r: Rename | .: Show hidden | Space: Select "
        self.stdscr.addstr(self.height-1, 0, help_text[:self.width-1], curses.A_REVERSE)

        self.stdscr.refresh()

    def show_message(self, message):
        y, x = self.height // 2, max(0, self.width // 2 - len(message) // 2)
        self.stdscr.addstr(y, x, message[:self.width-1], curses.A_BOLD)
        self.stdscr.refresh()
        self.stdscr.get_wch()

    def get_input(self, prompt):
        curses.echo()
        curses.curs_set(1)
        self.stdscr.addstr(self.height-2, 0, prompt)
        self.stdscr.clrtoeol()
        input_str = ""
        while True:
            ch = self.stdscr.get_wch()
            if ch in ("\n", "\r"):  # Enter
                break
            elif ch == "\x1b":  # Escape
                input_str = ""
                break
            elif ch in ("\b", "\x7f"):  # Backspace
                input_str = input_str[:-1]
                self.stdscr.addstr(self.height-2, len(prompt), input_str.ljust(self.width - len(prompt) - 1))
            elif isinstance(ch, str):
                input_str += ch
                self.std_scr.addstr(self.height-2, len(prompt), input_str.ljust(self.width - len(prompt) - 1))
        curses.noecho()
        curses.curs_set(0)
        return input_str

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
            # Сохраняем текущую директорию для cd on exit, только если она изменилась
            if self.current_dir != self.last_dir:
                with open(CD_FILE, 'w') as f:
                    f.write(self.current_dir)
            return False

        elif key == " ":
            if self.cursor_pos < len(self.files):
                fname = self.files[self.cursor_pos]
                if fname in self.selected_files:
                    self.selected_files.remove(fname)
                else:
                    self.selected_files.add(fname)

        elif key == ".":
            self.show_hidden = not self.show_hidden
            self.get_files()

        elif key == "r":
            self.rename_item()

        elif key == "c":
            self.copy_items()

        elif key == "m":
            self.move_items()

        elif key == "d":
            self.delete_items()

        elif key == "n":
            self.create_new_item()

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
        if self.current_dir != os.path.expanduser("~"):
            self.current_dir = os.path.dirname(self.current_dir)
            self.cursor_pos = 0
            self.offset = 0
            self.get_files()

    def change_directory(self, path):
        self.current_dir = os.path.abspath(path)
        self.cursor_pos = 0
        self.offset = 0
        self.get_files()

    def open_file(self, full_path):
        try:
            curses.endwin()
            if sys.platform.startswith("linux"):
                subprocess.Popen(["xdg-open", full_path])
            elif sys.platform == "darwin":  # macOS
                subprocess.Popen(["open", full_path])
            elif sys.platform.startswith("win"):
                os.startfile(full_path)
            else:
                self.show_message("Неизвестная платформа: не знаю, как открыть файл")
            curses.doupdate()
        except Exception as e:
            self.show_message(f"Ошибка при открытии файла: {e}")

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

    def copy_items(self):
        targets = self.selected_files if self.selected_files else [self.files[self.cursor_pos]]
        dest_name = self.get_input("Копировать в (каталог): ")
        if dest_name:
            for fname in targets:
                if fname == "..":
                    continue
                src = os.path.join(self.current_dir, fname)
                try:
                    if os.path.isdir(src):
                        shutil.copytree(src, os.path.join(dest_name, fname))
                    else:
                        shutil.copy2(src, os.path.join(dest_name, fname))
                    self.get_files()
                except Exception as e:
                    self.show_message(f"Ошибка копирования {fname}: {e}")
            self.selected_files.clear()

    def move_items(self):
        targets = self.selected_files if self.selected_files else [self.files[self.cursor_pos]]
        dest_name = self.get_input("Переместить в (каталог): ")
        if dest_name:
            for fname in targets:
                if fname == "..":
                    continue
                src = os.path.join(self.current_dir, fname)
                try:
                    shutil.move(src, os.path.join(dest_name, fname))
                    self.get_files()
                except Exception as e:
                    self.show_message(f"Ошибка перемещения {fname}: {e}")
            self.selected_files.clear()

    def delete_items(self):
        targets = self.selected_files if self.selected_files else [self.files[self.cursor_pos]]
        confirm = self.get_input(f"Удалить {', '.join(targets)}? (y/n): ")
        if confirm.lower() == 'y':
            for fname in targets:
                if fname == "..":
                    continue
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
