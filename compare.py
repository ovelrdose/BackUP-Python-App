import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext, simpledialog
import datetime
import threading
import sys
import shutil
import json
import fnmatch
import ctypes
from pathlib import Path

CONFIG_FILE = "archive_helper_config.json"

class ArchiveMoverApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Архиватор файлов с расширенными исключениями")
        self.root.geometry("900x720")
        self.root.minsize(850, 620)
        
        # Загрузка сохраненных настроек
        self.load_config()
        
        # Переменные интерфейса
        self.source_folder = tk.StringVar(value=self.config.get("source_folder", ""))
        self.archive_folder = tk.StringVar(value=self.config.get("archive_folder", ""))
        self.start_date_var = tk.StringVar()
        self.end_date_var = tk.StringVar()
        self.time_type_var = tk.StringVar(value=self.config.get("time_type", "modified"))
        self.skip_hidden_var = tk.BooleanVar(value=self.config.get("skip_hidden", True))
        self.exclude_files_var = tk.StringVar(value=self.config.get("exclude_files", "*.tmp, *.log, Thumbs.db, desktop.ini, ~*.*"))
        self.exclude_dirs_var = tk.StringVar(value=self.config.get("exclude_dirs", "node_modules, .git, .svn, __pycache__, bin, obj, build, dist"))
        self.exclude_paths_var = tk.StringVar(value=self.config.get("exclude_paths", ""))
        self.exclude_small_var = tk.BooleanVar(value=self.config.get("exclude_small", False))
        self.min_size_var = tk.StringVar(value=str(self.config.get("min_size_kb", 10)))
        self.save_txt_report_var = tk.BooleanVar(value=self.config.get("save_txt_report", True))  # НОВОЕ: опция сохранения в формате .txt
        self.is_running = False
        self.cancel_flag = False
        self.found_files = []
        self.source_root = ""
        
        # Установка периода "последний год" по умолчанию
        today = datetime.datetime.today()
        year_ago = today - datetime.timedelta(days=365)
        self.start_date_var.set(year_ago.strftime("%Y-%m-%d"))
        self.end_date_var.set(today.strftime("%Y-%m-%d"))
        
        self.create_widgets()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
    
    def load_config(self):
        """Загрузка сохраненных настроек из JSON"""
        try:
            if os.path.exists(CONFIG_FILE):
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
            else:
                self.config = {
                    "time_type": "modified",
                    "skip_hidden": True,
                    "exclude_files": "*.tmp, *.log, Thumbs.db, desktop.ini, ~*.*",
                    "exclude_dirs": "node_modules, .git, .svn, __pycache__, bin, obj, build, dist",
                    "exclude_paths": "",
                    "exclude_small": False,
                    "min_size_kb": 10,
                    "save_txt_report": True  # НОВОЕ: по умолчанию включено
                }
        except Exception:
            self.config = {}
    
    def save_config(self):
        """Сохранение текущих настроек в JSON"""
        try:
            config = {
                "source_folder": self.source_folder.get(),
                "archive_folder": self.archive_folder.get(),
                "time_type": self.time_type_var.get(),
                "skip_hidden": self.skip_hidden_var.get(),
                "exclude_files": self.exclude_files_var.get(),
                "exclude_dirs": self.exclude_dirs_var.get(),
                "exclude_paths": self.exclude_paths_var.get(),
                "exclude_small": self.exclude_small_var.get(),
                "min_size_kb": int(self.min_size_var.get()) if self.min_size_var.get().isdigit() else 10,
                "save_txt_report": self.save_txt_report_var.get()  # НОВОЕ: сохранение опции
            }
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.log(f"Не удалось сохранить настройки: {str(e)}", error=True)
    
    def on_closing(self):
        """Сохранение настроек при закрытии окна"""
        self.save_config()
        self.root.destroy()
    
    def normalize_long_path(self, path):
        """Добавляет префикс \\?\ для путей >260 символов"""
        if os.name == 'nt' and len(path) > 259 and not path.startswith('\\\\?\\'):
            return '\\\\?\\' + os.path.abspath(path)
        return path
    
    def _is_hidden_windows(self, path):
        """Проверка скрытого атрибута файла/папки (только Windows)"""
        if os.name != 'nt':
            return False
        try:
            attrs = ctypes.windll.kernel32.GetFileAttributesW(path)
            return attrs != -1 and (attrs & 2) != 0
        except:
            return False
    
    def create_widgets(self):
        # Верхний фрейм с вкладками
        notebook = ttk.Notebook(self.root)
        notebook.grid(row=0, column=0, sticky="nsew", padx=10, pady=5)
        
        # Вкладка 1: Основные настройки
        main_frame = ttk.Frame(notebook)
        notebook.add(main_frame, text="Основные настройки")
        
        # Выбор папок
        source_frame = ttk.LabelFrame(main_frame, text="Исходная папка (анализ и удаление)", padding="10")
        source_frame.grid(row=0, column=0, padx=10, pady=5, sticky="ew")
        ttk.Entry(source_frame, textvariable=self.source_folder, width=75, state="readonly").grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(source_frame, text="Обзор...", command=self.browse_source).grid(row=0, column=1, padx=5)
        
        archive_frame = ttk.LabelFrame(main_frame, text="Папка архива (копирование)", padding="10")
        archive_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        ttk.Entry(archive_frame, textvariable=self.archive_folder, width=75, state="readonly").grid(row=0, column=0, padx=5, pady=5)
        ttk.Button(archive_frame, text="Обзор...", command=self.browse_archive).grid(row=0, column=1, padx=5)
        
        # Параметры поиска
        search_frame = ttk.LabelFrame(main_frame, text="Параметры поиска", padding="10")
        search_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        
        # Тип временной метки
        ttk.Label(search_frame, text="Использовать дату:").grid(row=0, column=0, sticky="w", pady=5)
        time_type_combo = ttk.Combobox(
            search_frame, 
            textvariable=self.time_type_var,
            values=[
                "modified|Время изменения (Last Modified) - РЕКОМЕНДУЕТСЯ",
                "accessed|Время последнего доступа (Last Accessed)",
                "created|Время создания (Created)"
            ],
            state="readonly",
            width=65
        )
        time_type_combo.grid(row=0, column=1, columnspan=3, padx=5, pady=5, sticky="w")
        time_type_combo.set(self.time_type_var.get())
        time_type_combo.bind("<<ComboboxSelected>>", lambda e: self.update_time_type_tip())
        
        # Подсказка по типу даты
        self.time_type_tip = ttk.Label(
            search_frame, 
            text="",
            foreground="blue",
            wraplength=780,
            justify="left"
        )
        self.time_type_tip.grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 10))
        self.update_time_type_tip()
        
        # Период
        ttk.Label(search_frame, text="Период (включая границы):").grid(row=2, column=0, columnspan=4, sticky="w", pady=(5,0))
        
        ttk.Label(search_frame, text="Дата от (ГГГГ-ММ-ДД):").grid(row=3, column=0, sticky="w", pady=5)
        start_entry = ttk.Entry(search_frame, textvariable=self.start_date_var, width=15)
        start_entry.grid(row=3, column=1, sticky="w", padx=5)
        
        ttk.Label(search_frame, text="Дата до (ГГГГ-ММ-ДД):").grid(row=3, column=2, sticky="e", pady=5, padx=(20,0))
        end_entry = ttk.Entry(search_frame, textvariable=self.end_date_var, width=15)
        end_entry.grid(row=3, column=3, sticky="w", padx=5)
        
        # Кнопки быстрого выбора периода
        period_btn_frame = ttk.Frame(search_frame)
        period_btn_frame.grid(row=4, column=0, columnspan=4, pady=5, sticky="w")
        periods = [
            ("Посл. 7 дней", 7), ("Посл. 30 дней", 30), ("Посл. 90 дней", 90), 
            ("Посл. год", 365), ("Текущий год", 0), ("Сбросить на сегодня", -1)
        ]
        for i, (text, days) in enumerate(periods):
            if days == 0:
                cmd = self.set_current_year
            elif days == -1:
                cmd = self.set_today
            else:
                cmd = lambda d=days: self.set_period_days(d)
            ttk.Button(period_btn_frame, text=text, command=cmd, width=15).grid(row=0, column=i, padx=2)
        
        # Вкладка 2: Исключения
        exclude_frame = ttk.Frame(notebook)
        notebook.add(exclude_frame, text="Исключения")
        
        exclude_inner = ttk.LabelFrame(exclude_frame, text="Правила исключения файлов и папок", padding="15")
        exclude_inner.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Скрытые файлы
        hidden_frame = ttk.Frame(exclude_inner)
        hidden_frame.grid(row=0, column=0, columnspan=2, sticky="w", pady=5)
        ttk.Checkbutton(
            hidden_frame, 
            text="Пропускать скрытые файлы и папки (рекомендуется)", 
            variable=self.skip_hidden_var,
            command=self.save_config
        ).pack(side=tk.LEFT)
        ttk.Button(hidden_frame, text="?", width=3, command=self.show_hidden_help).pack(side=tk.LEFT, padx=(5,0))
        
        # Маски файлов
        ttk.Label(exclude_inner, text="Исключить файлы по маске (через запятую):").grid(row=1, column=0, sticky="nw", pady=8)
        file_mask_frame = ttk.Frame(exclude_inner)
        file_mask_frame.grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Entry(file_mask_frame, textvariable=self.exclude_files_var, width=60).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(file_mask_frame, text="Редактор", command=self.open_file_mask_editor).pack(side=tk.LEFT)
        ttk.Button(file_mask_frame, text="Сброс", command=lambda: self.exclude_files_var.set("*.tmp, *.log, Thumbs.db, desktop.ini, ~*.*")).pack(side=tk.LEFT, padx=(5,0))
        
        # Маски папок (по имени)
        ttk.Label(exclude_inner, text="Исключить папки по имени/маске (через запятую):").grid(row=2, column=0, sticky="nw", pady=8)
        dir_mask_frame = ttk.Frame(exclude_inner)
        dir_mask_frame.grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Entry(dir_mask_frame, textvariable=self.exclude_dirs_var, width=60).pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(dir_mask_frame, text="Редактор", command=self.open_dir_mask_editor).pack(side=tk.LEFT)
        ttk.Button(dir_mask_frame, text="Сброс", command=lambda: self.exclude_dirs_var.set("node_modules, .git, .svn, __pycache__, bin, obj, build, dist")).pack(side=tk.LEFT, padx=(5,0))
        
        # ИСКЛЮЧЕНИЕ ПО ПОЛНОМУ ПУТИ (НОВОЕ)
        ttk.Label(exclude_inner, text="Исключить ПОЛНЫЕ ПУТИ к папкам (с содержимым):", foreground="darkred", font=("TkDefaultFont", 10, "bold")).grid(row=3, column=0, sticky="nw", pady=(15,5))
        path_frame = ttk.Frame(exclude_inner)
        path_frame.grid(row=3, column=1, sticky="ew", pady=5)
        path_entry = ttk.Entry(path_frame, textvariable=self.exclude_paths_var, width=60)
        path_entry.pack(side=tk.LEFT, padx=(0,5))
        ttk.Button(path_frame, text="➕ Добавить папку", command=self.add_exclude_path).pack(side=tk.LEFT)
        ttk.Button(path_frame, text="🗑 Очистить", command=lambda: self.exclude_paths_var.set("")).pack(side=tk.LEFT, padx=(5,0))
        ttk.Button(path_frame, text="?", width=3, command=self.show_path_help).pack(side=tk.LEFT, padx=(10,0))
        
        # Размер файла
        size_frame = ttk.Frame(exclude_inner)
        size_frame.grid(row=4, column=0, columnspan=2, sticky="w", pady=8)
        ttk.Checkbutton(
            size_frame, 
            text="Исключить файлы меньше", 
            variable=self.exclude_small_var,
            command=self.save_config
        ).pack(side=tk.LEFT)
        ttk.Entry(size_frame, textvariable=self.min_size_var, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(size_frame, text="КБ").pack(side=tk.LEFT)
        ttk.Button(size_frame, text="?", width=3, command=self.show_size_help).pack(side=tk.LEFT, padx=(10,0))
        
        # Вкладка 3: Дополнительные настройки
        settings_frame = ttk.Frame(notebook)
        notebook.add(settings_frame, text="Дополнительно")
        
        settings_inner = ttk.LabelFrame(settings_frame, text="Дополнительные параметры", padding="15")
        settings_inner.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Опция сохранения отчетов в формате TXT (НОВОЕ)
        report_frame = ttk.Frame(settings_inner)
        report_frame.grid(row=0, column=0, columnspan=2, sticky="w", pady=10)
        ttk.Checkbutton(
            report_frame,
            text="Сохранять отчеты в формате .txt (необязательно)",
            variable=self.save_txt_report_var,
            command=self.save_config
        ).pack(side=tk.LEFT)
        ttk.Button(
            report_frame,
            text="?",
            width=3,
            command=self.show_txt_report_help
        ).pack(side=tk.LEFT, padx=(5,0))
        ttk.Label(
            settings_inner,
            text="ℹ️ Отчеты в формате JSON всегда сохраняются. Отчеты в формате .txt можно отключить для экономии места.",
            foreground="blue",
            wraplength=780,
            justify="left"
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        
        # Предупреждение
        warning_frame = ttk.LabelFrame(self.root, text="КРИТИЧЕСКИ ВАЖНО", padding="10")
        warning_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        warning_text = (
            "⚠️ 1. Для архивации НЕИСПОЛЬЗУЕМЫХ файлов выбирайте период ДО текущей даты (например, 'Дата до' = вчера).\n"
            "⚠️ 2. 'Время доступа' (Last Accessed) в Windows часто ОТКЛЮЧЕНО. Используйте 'Время изменения' для надёжности.\n"
            "⚠️ 3. Файлы будут УДАЛЕНЫ из исходной папки после копирования! Убедитесь в целостности архива.\n"
            "⚠️ 4. Все настройки исключений автоматически сохраняются между запусками программы."
        )
        ttk.Label(warning_frame, text=warning_text, foreground="red", justify="left", wraplength=850).pack(anchor="w")
        
        # Кнопки управления
        btn_frame = ttk.Frame(self.root, padding="10")
        btn_frame.grid(row=2, column=0, sticky="ew")
        self.search_btn = ttk.Button(btn_frame, text="🔍 Найти файлы в периоде", command=self.start_search, width=25)
        self.search_btn.pack(side=tk.LEFT, padx=5)
        self.move_btn = ttk.Button(btn_frame, text="➡️ Переместить выбранные файлы в архив", command=self.start_move, width=35, state="disabled")
        self.move_btn.pack(side=tk.LEFT, padx=5)
        self.cancel_btn = ttk.Button(btn_frame, text="⏹ Отмена", command=self.cancel_operation, state="disabled", width=12)
        self.cancel_btn.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="❓ Справка", command=self.show_help, width=12).pack(side=tk.RIGHT, padx=5)
        
        # Статус и лог
        status_frame = ttk.Frame(self.root, padding="5")
        status_frame.grid(row=3, column=0, sticky="ew")
        self.status_label = ttk.Label(status_frame, text="Готово к работе", foreground="green")
        self.status_label.pack(anchor="w")
        
        log_frame = ttk.LabelFrame(self.root, text="Журнал операций", padding="10")
        log_frame.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")
        self.log_text = scrolledtext.ScrolledText(log_frame, height=12, wrap=tk.WORD, state="disabled", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        
        # Настройка растягивания
        self.root.grid_rowconfigure(4, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        exclude_inner.grid_columnconfigure(1, weight=1)
        
        # Горячие клавиши
        self.root.bind('<Control-s>', lambda e: self.browse_source())
        self.root.bind('<Control-a>', lambda e: self.browse_archive())
        self.root.bind('<F5>', lambda e: self.start_search())
        
        self.validate_inputs()
    
    def show_txt_report_help(self):
        """Справка по опции сохранения отчетов в формате TXT"""
        messagebox.showinfo("Отчеты в формате .txt",
            "Эта опция позволяет включить или отключить сохранение отчетов в формате .txt.\n\n"
            "✅ ВКЛЮЧЕНО (по умолчанию):\n"
            "• Сохраняются отчеты в формате .txt (человекочитаемые)\n"
            "• Сохраняются отчеты в формате .json (машинночитаемые)\n"
            "• Итого: 2 файла отчета на операцию\n\n"
            "❌ ОТКЛЮЧЕНО:\n"
            "• Сохраняются только отчеты в формате .json (машинночитаемые)\n"
            "• Отчеты в формате .txt НЕ создаются\n"
            "• Итого: 1 файл отчета на операцию\n\n"
            "💡 Рекомендация:\n"
            "• Включите для удобства чтения отчетов человеком\n"
            "• Отключите для экономии места на диске\n\n"
            "⚠️ Важно: Отчеты в формате JSON всегда сохраняются, так как они содержат полные метаданные и используются для автоматической обработки.")
    
    # Вспомогательные методы интерфейса (идентичны предыдущей версии)
    def update_time_type_tip(self):
        tip_text = {
            "modified": "ℹ️ Время изменения (Last Modified) — обновляется при сохранении файла. НАИБОЛЕЕ НАДЁЖНЫЙ вариант для архивации.",
            "accessed": "⚠️ Время доступа (Last Accessed) — в современных Windows ЧАСТО ОТКЛЮЧЕНО. Проверьте: fsutil behavior query disablelastaccess",
            "created": "ℹ️ Время создания (Created) — фиксирует момент появления файла в текущей файловой системе."
        }
        selected = self.time_type_var.get().split('|')[0] if '|' in self.time_type_var.get() else self.time_type_var.get()
        self.time_type_tip.config(
            text=tip_text.get(selected, tip_text["modified"]),
            foreground="red" if selected == "accessed" else "blue"
        )
        self.save_config()
    
    def show_hidden_help(self):
        messagebox.showinfo("Скрытые файлы", 
            "Включите эту опцию, чтобы пропустить:\n"
            "• Скрытые файлы (например, .gitignore, .env)\n"
            "• Скрытые папки (например, .git, .svn)\n\n"
            "Рекомендуется оставить включённым, чтобы избежать ошибок доступа к системным папкам.")
    
    def show_size_help(self):
        messagebox.showinfo("Исключение по размеру",
            "Полезно для пропуска:\n"
            "• Временных файлов (маленькие .tmp)\n"
            "• Кэш-файлов\n"
            "• Пустых или почти пустых документов\n\n"
            "Пример: значение 10 исключит файлы меньше 10 КБ.")
    
    def show_path_help(self):
        messagebox.showinfo("Исключение по полному пути",
            "Здесь вы можете указать ПОЛНЫЕ или ОТНОСИТЕЛЬНЫЕ пути к папкам, которые нужно ПОЛНОСТЬЮ исключить из поиска (включая всё содержимое).\n\n"
            "Примеры:\n"
            "• C:\\Data\\Temp\n"
            "• Projects\\Legacy\n"
            "• Backup\\2023\n\n"
            "Как добавить:\n"
            "1. Нажмите '➕ Добавить папку'\n"
            "2. Выберите папку в проводнике\n"
            "3. Путь автоматически добавится в список\n"
            "4. Можно добавить несколько папок через запятую\n\n"
            "💡 Совет: Относительные пути указываются от корня исходной папки (выбранной в 'Исходная папка')")
    
    def add_exclude_path(self):
        """Добавление пути к папке через диалог выбора"""
        folder = filedialog.askdirectory(title="Выберите папку для полного исключения")
        if folder:
            current = self.exclude_paths_var.get().strip()
            if current:
                new_value = current + ", " + folder
            else:
                new_value = folder
            self.exclude_paths_var.set(new_value)
            self.save_config()
            self.log(f"Добавлена папка для исключения: {folder}", success=True)
    
    def open_file_mask_editor(self):
        self.open_mask_editor("Файлы", self.exclude_files_var, [
            "*.tmp", "*.log", "Thumbs.db", "desktop.ini", "~*.*", 
            "*.bak", "*.temp", "cache_*", "temp_*"
        ])
    
    def open_dir_mask_editor(self):
        self.open_mask_editor("Папки", self.exclude_dirs_var, [
            "node_modules", ".git", ".svn", ".hg", "__pycache__", 
            "bin", "obj", "build", "dist", ".idea", ".vscode", "venv"
        ])
    
    def open_mask_editor(self, title, var, suggestions):
        """Модальное окно для удобного редактирования масок"""
        editor = tk.Toplevel(self.root)
        editor.title(f"Редактор исключений: {title}")
        editor.geometry("500x400")
        editor.transient(self.root)
        editor.grab_set()
        
        ttk.Label(editor, text=f"Выберите или добавьте маски для исключения {title.lower()}:", 
                 wraplength=480, justify="center").pack(pady=10)
        
        current_masks = [m.strip() for m in var.get().split(',') if m.strip()]
        listbox_frame = ttk.Frame(editor)
        listbox_frame.pack(fill="both", expand=True, padx=10, pady=5)
        
        listbox = tk.Listbox(listbox_frame, selectmode=tk.MULTIPLE, height=10, exportselection=False)
        listbox.pack(side=tk.LEFT, fill="both", expand=True)
        
        scrollbar = ttk.Scrollbar(listbox_frame, orient="vertical", command=listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill="y")
        listbox.config(yscrollcommand=scrollbar.set)
        
        all_masks = sorted(set(suggestions + current_masks))
        for mask in all_masks:
            listbox.insert(tk.END, mask)
            if mask in current_masks:
                listbox.selection_set(all_masks.index(mask))
        
        btn_frame = ttk.Frame(editor)
        btn_frame.pack(pady=10)
        
        def update_and_close():
            selected = [listbox.get(i) for i in listbox.curselection()]
            if selected:
                var.set(", ".join(selected))
                self.save_config()
            editor.destroy()
        
        ttk.Button(btn_frame, text="Применить выделенные", command=update_and_close, width=25).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Отмена", command=editor.destroy, width=15).pack(side=tk.LEFT, padx=5)
        
        editor.wait_window()
    
    # Методы для дат, логирования, поиска, перемещения
    def set_period_days(self, days):
        end = datetime.datetime.today()
        start = end - datetime.timedelta(days=days)
        self.start_date_var.set(start.strftime("%Y-%m-%d"))
        self.end_date_var.set(end.strftime("%Y-%m-%d"))
        self.log(f"Установлен период: последние {days} дней", success=True)
        self.validate_inputs()
        self.save_config()
    
    def set_current_year(self):
        today = datetime.datetime.today()
        start = datetime.datetime(today.year, 1, 1)
        self.start_date_var.set(start.strftime("%Y-%m-%d"))
        self.end_date_var.set(today.strftime("%Y-%m-%d"))
        self.log("Установлен период: текущий год", success=True)
        self.validate_inputs()
        self.save_config()
    
    def set_today(self):
        today = datetime.datetime.today().strftime("%Y-%m-%d")
        self.start_date_var.set(today)
        self.end_date_var.set(today)
        self.log("Установлен период: сегодня", success=True)
        self.validate_inputs()
        self.save_config()
    
    def log(self, message, error=False, success=False):
        self.log_text.config(state="normal")
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        prefix = "[ОШИБКА] " if error else ("[УСПЕХ] " if success else "")
        color_tag = "error" if error else ("success" if success else "normal")
        self.log_text.insert(tk.END, f"[{timestamp}] {prefix}{message}\n", color_tag)
        self.log_text.tag_config("error", foreground="red")
        self.log_text.tag_config("success", foreground="green")
        self.log_text.see(tk.END)
        self.log_text.config(state="disabled")
        self.root.update_idletasks()
    
    def update_status(self, text, error=False):
        self.status_label.config(text=text, foreground="red" if error else "green")
    
    def browse_source(self):
        folder = filedialog.askdirectory(title="Выберите исходную папку для анализа")
        if folder:
            self.source_folder.set(folder)
            self.log(f"Исходная папка: {folder}")
            self.validate_inputs()
            self.save_config()
    
    def browse_archive(self):
        folder = filedialog.askdirectory(title="Выберите папку для архива")
        if folder:
            self.archive_folder.set(folder)
            self.log(f"Папка архива: {folder}")
            self.validate_inputs()
            self.save_config()
    
    def validate_date(self, date_str):
        try:
            return datetime.datetime.strptime(date_str.strip(), "%Y-%m-%d")
        except ValueError:
            return None
    
    def validate_inputs(self):
        start_dt = self.validate_date(self.start_date_var.get())
        end_dt = self.validate_date(self.end_date_var.get())
        dates_valid = start_dt is not None and end_dt is not None and start_dt <= end_dt
        source_ok = bool(self.source_folder.get() and os.path.isdir(self.source_folder.get()))
        
        self.search_btn.config(state="normal" if (source_ok and dates_valid) else "disabled")
        archive_ok = bool(self.archive_folder.get() and os.path.isdir(self.archive_folder.get()))
        self.move_btn.config(state="normal" if (self.found_files and archive_ok) else "disabled")
        
        if not dates_valid:
            self.update_status("Ошибка: проверьте формат дат (ГГГГ-ММ-ДД) и чтобы 'Дата от' <= 'Дата до'", error=True)
        elif not source_ok:
            self.update_status("Выберите исходную папку", error=False)
        else:
            self.update_status("Готово к поиску", error=False)
    
    def start_search(self):
        if self.is_running:
            return
        
        start_dt = self.validate_date(self.start_date_var.get())
        end_dt = self.validate_date(self.end_date_var.get())
        if not start_dt or not end_dt or start_dt > end_dt:
            messagebox.showerror("Ошибка", "Некорректный период!\nФормат: ГГГГ-ММ-ДД\nДата 'от' должна быть <= даты 'до'")
            return
        
        source = self.source_folder.get()
        if not source or not os.path.isdir(source):
            messagebox.showerror("Ошибка", "Выберите корректную исходную папку!")
            return
        
        time_type_raw = self.time_type_var.get()
        time_type = time_type_raw.split('|')[0] if '|' in time_type_raw else time_type_raw
        
        start_search = datetime.datetime.combine(start_dt.date(), datetime.time.min)
        end_search = datetime.datetime.combine(end_dt.date(), datetime.time.max)
        
        time_label = {
            "modified": "изменения",
            "accessed": "последнего доступа",
            "created": "создания"
        }.get(time_type, "изменения")
        
        confirm = messagebox.askyesno(
            "Подтверждение поиска",
            f"Найти файлы, у которых дата {time_label} находится в периоде:\n"
            f"  с {start_search.strftime('%d.%m.%Y %H:%M')}\n"
            f"  по {end_search.strftime('%d.%m.%Y %H:%M')}\n\n"
            f"Исходная папка: {source}\n"
            f"Внимание: для архивации НЕИСПОЛЬЗУЕМЫХ файлов период должен заканчиваться ДО текущей даты!\n\n"
            f"Продолжить поиск?"
        )
        if not confirm:
            return
        
        self.source_root = source
        self.found_files = []
        self.move_btn.config(state="disabled")
        self.cancel_flag = False
        self.is_running = True
        self.search_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.update_status("Выполняется поиск файлов...")
        self.log(f"Поиск файлов по дате '{time_label}' в периоде: {start_search} — {end_search}")
        self.log(f"Применяются правила исключений: скрытые={self.skip_hidden_var.get()}, "
                f"маски файлов={self.exclude_files_var.get()[:50]}..., "
                f"маски папок={self.exclude_dirs_var.get()[:50]}..., "
                f"пути={self.exclude_paths_var.get()[:50]}...", success=True)
        
        thread = threading.Thread(
            target=self.search_files, 
            args=(source, start_search, end_search, time_type), 
            daemon=True
        )
        thread.start()
    
    def search_files(self, folder, start_dt, end_dt, time_type):
        results = []
        error_count = 0
        skipped_hidden = 0
        skipped_pattern = 0
        skipped_size = 0
        skipped_by_path = 0
        processed = 0
        start_time = datetime.datetime.now()
        
        # Подготовка правил исключений
        skip_hidden = self.skip_hidden_var.get()
        exclude_file_patterns = [p.strip() for p in self.exclude_files_var.get().split(',') if p.strip()]
        exclude_dir_patterns = [p.strip() for p in self.exclude_dirs_var.get().split(',') if p.strip()]
        base_system_dirs = ['$RECYCLE.BIN', 'System Volume Information', 'Recovery']
        all_exclude_dir_patterns = base_system_dirs + exclude_dir_patterns
        
        # Подготовка исключенных путей
        exclude_path_list = [p.strip() for p in self.exclude_paths_var.get().split(',') if p.strip()]
        exclude_paths_normalized = []
        for path_str in exclude_path_list:
            try:
                if not os.path.isabs(path_str):
                    abs_path = os.path.abspath(os.path.join(self.source_root, path_str))
                else:
                    abs_path = os.path.abspath(path_str)
                norm_path = self.normalize_long_path(abs_path).lower()
                if not norm_path.endswith(('\\', '/')):
                    norm_path += '\\'
                exclude_paths_normalized.append(norm_path)
            except Exception as e:
                self.log(f"Ошибка обработки пути исключения '{path_str}': {str(e)}", error=True)
        
        exclude_by_size = self.exclude_small_var.get()
        min_size_kb = int(self.min_size_var.get()) if self.min_size_var.get().isdigit() else 10
        min_size_bytes = min_size_kb * 1024 if exclude_by_size and min_size_kb > 0 else 0
        
        time_func = {
            "modified": os.path.getmtime,
            "accessed": os.path.getatime,
            "created": os.path.getctime
        }.get(time_type, os.path.getmtime)
        
        try:
            for root_dir, dirs, files in os.walk(folder, topdown=True):
                if self.cancel_flag:
                    break
                
                # Проверка по полному пути - ПОЛНОСТЬЮ пропускаем ветку
                norm_root = self.normalize_long_path(root_dir).lower()
                if not norm_root.endswith(('\\', '/')):
                    norm_root_check = norm_root + '\\'
                else:
                    norm_root_check = norm_root
                
                skip_entire_branch = False
                for excl_path in exclude_paths_normalized:
                    if norm_root_check.startswith(excl_path):
                        skip_entire_branch = True
                        break
                
                if skip_entire_branch:
                    dirs[:] = []
                    skipped_by_path += 1
                    continue
                
                # Фильтрация папок по шаблонам имен
                dirs[:] = [d for d in dirs if not any(fnmatch.fnmatch(d, pattern) for pattern in all_exclude_dir_patterns)]
                
                # Фильтрация скрытых папок
                if skip_hidden:
                    non_hidden_dirs = []
                    for d in dirs:
                        full_dir_path = self.normalize_long_path(os.path.join(root_dir, d))
                        if not self._is_hidden_windows(full_dir_path):
                            non_hidden_dirs.append(d)
                        else:
                            skipped_hidden += 1
                    dirs[:] = non_hidden_dirs
                
                for file in files:
                    if self.cancel_flag:
                        break
                    
                    file_path = self.normalize_long_path(os.path.join(root_dir, file))
                    
                    # Пропуск по маске файла
                    if any(fnmatch.fnmatch(file, pattern) for pattern in exclude_file_patterns):
                        skipped_pattern += 1
                        continue
                    
                    # Пропуск скрытых файлов
                    if skip_hidden and self._is_hidden_windows(file_path):
                        skipped_hidden += 1
                        continue
                    
                    # Пропуск по размеру
                    if exclude_by_size:
                        try:
                            size = os.path.getsize(file_path)
                            if size < min_size_bytes:
                                skipped_size += 1
                                continue
                        except:
                            pass
                    
                    try:
                        timestamp = time_func(file_path)
                        file_time = datetime.datetime.fromtimestamp(timestamp)
                        
                        if start_dt <= file_time <= end_dt:
                            clean_path = file_path.replace('\\\\?\\', '') if file_path.startswith('\\\\?\\') else file_path
                            results.append((clean_path, file_time))
                        
                        processed += 1
                        if processed % 200 == 0:
                            self.root.after(0, lambda p=processed: self.log(f"Обработано файлов: {p}..."))
                            
                    except (PermissionError, FileNotFoundError, OSError) as e:
                        error_count += 1
                        if error_count <= 5:
                            clean_path = (file_path.replace('\\\\?\\', '')[:80] + "...") if len(file_path) > 80 else file_path
                            self.root.after(0, lambda ep=clean_path, ee=str(e): 
                                self.log(f"Ошибка обработки {ep}: {ee[:60]}", error=True))
                        continue
            
            if self.cancel_flag:
                self.root.after(0, lambda: self.log("Поиск отменен пользователем"))
                return
            
            duration = (datetime.datetime.now() - start_time).total_seconds()
            self.found_files = results
            self.root.after(0, lambda: self.on_search_complete(
                results, duration, error_count, skipped_hidden, skipped_pattern, skipped_size, skipped_by_path,
                time_type, start_dt, end_dt
            ))
            
        except Exception as e:
            self.root.after(0, lambda err=str(e): [
                self.log(f"Критическая ошибка поиска: {err}", error=True),
                self.update_status("Ошибка поиска", error=True)
            ])
        finally:
            self.root.after(0, self.finalize_operation)
    
    def on_search_complete(self, results, duration, errors, skipped_hidden, skipped_pattern, skipped_size, skipped_by_path, time_type, start_dt, end_dt):
        time_label = {
            "modified": "изменения",
            "accessed": "последнего доступа",
            "created": "создания"
        }.get(time_type, "изменения")
        
        self.update_status(f"Поиск завершен: найдено {len(results)} файлов")
        summary = (f"Поиск по дате '{time_label}' за {duration:.1f} сек. "
                  f"Найдено: {len(results)}, Ошибок: {errors}, "
                  f"Пропущено: скрытые={skipped_hidden}, маски={skipped_pattern}, "
                  f"размер={skipped_size}, ПОЛНЫЕ ПУТИ={skipped_by_path}")
        self.log(summary, success=True)
        
        if results:
            sample = min(5, len(results))
            self.log(f"Примеры найденных файлов (первые {sample}):")
            for i in range(sample):
                path, dt = results[i]
                self.log(f"  • {os.path.basename(path)} | {dt.strftime('%d.%m.%Y %H:%M:%S')}")
            if len(results) > sample:
                self.log(f"  ... и ещё {len(results) - sample} файлов")
            
            # Сохранение отчета о поиске (с учетом опции)
            if messagebox.askyesno("Результаты поиска", 
                f"Найдено файлов: {len(results)}\n"
                f"Пропущено по правилам: {skipped_hidden + skipped_pattern + skipped_size + skipped_by_path}\n"
                f"В том числе по полным путям: {skipped_by_path} папок\n\n"
                f"Сохранить отчет о найденных файлах (без перемещения)?"):
                self.save_search_report(results, time_type, start_dt, end_dt, skipped_by_path)
            
            if self.archive_folder.get():
                self.move_btn.config(state="normal")
                self.log("Выберите папку архива (если ещё не выбрана) и нажмите 'Переместить в архив'", success=True)
            else:
                self.log("Укажите папку архива для активации кнопки перемещения", success=True)
        else:
            messagebox.showinfo("Результат", 
                "Файлы не найдены.\n"
                "Проверьте:\n"
                "• Период указан корректно (для архивации старых файлов — период ДО текущей даты)\n"
                "• Выбран правильный тип даты (рекомендуется 'Время изменения')\n"
                "• Правила исключений не блокируют все файлы\n"
                "• Файлы существуют в указанной папке")
    
    # Методы перемещения и отчетов (обновлены для учета опции сохранения в формате .txt)
    def start_move(self):
        if not self.found_files:
            messagebox.showwarning("Внимание", "Сначала выполните поиск файлов!")
            return
        
        archive = self.archive_folder.get()
        if not archive or not os.path.isdir(archive):
            messagebox.showerror("Ошибка", "Выберите корректную папку архива!")
            return
        
        warning = (
            "⚠️ ВНИМАНИЕ! Эта операция:\n"
            "1. Скопирует найденные файлы в папку архива с сохранением структуры папок\n"
            "2. УДАЛИТ файлы из исходной папки после успешного копирования\n"
            "3. Операция НЕОБРАТИМА!\n\n"
            f"Переместить {len(self.found_files)} файлов в:\n{archive}\n\n"
            "Подтверждаете выполнение?"
        )
        if not messagebox.askyesno("Подтверждение перемещения", warning, icon=messagebox.WARNING):
            return
        
        if not messagebox.askyesno("ФИНАЛЬНОЕ ПОДТВЕРЖДЕНИЕ", 
            "Вы уверены? После удаления файлы нельзя восстановить стандартными средствами!",
            icon=messagebox.ERROR):
            return
        
        self.cancel_flag = False
        self.is_running = True
        self.move_btn.config(state="disabled")
        self.search_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.update_status("Выполняется перемещение файлов в архив...")
        self.log(f"Начало перемещения {len(self.found_files)} файлов в архив: {archive}")
        
        thread = threading.Thread(target=self.move_files, args=(archive,), daemon=True)
        thread.start()
    
    def move_files(self, archive_base):
        results = []
        success_count = 0
        error_count = 0
        start_time = datetime.datetime.now()
        
        for idx, (src_path, file_time) in enumerate(self.found_files, 1):
            if self.cancel_flag:
                break
            
            try:
                clean_src = src_path.replace('\\\\?\\', '') if src_path.startswith('\\\\?\\') else src_path
                rel_path = os.path.relpath(clean_src, self.source_root)
                dest_path = os.path.join(archive_base, rel_path)
                dest_path = self.normalize_long_path(dest_path)
                dest_dir = os.path.dirname(dest_path)
                src_norm = self.normalize_long_path(clean_src)
                
                os.makedirs(dest_dir, exist_ok=True)
                shutil.copy2(src_norm, dest_path)
                
                if os.path.getsize(src_norm) != os.path.getsize(dest_path):
                    raise Exception("Ошибка целостности: размеры не совпадают")
                
                os.remove(src_norm)
                results.append((clean_src, dest_path.replace('\\\\?\\', ''), "УСПЕХ", ""))
                success_count += 1
                self.root.after(0, lambda i=idx, t=len(self.found_files), p=os.path.basename(clean_src): 
                    self.log(f"[{i}/{t}] Перемещен: {p}"))
                
            except Exception as e:
                error_msg = str(e)[:100]
                results.append((clean_src, "", "ОШИБКА", error_msg))
                error_count += 1
                self.root.after(0, lambda p=os.path.basename(clean_src), err=error_msg:
                    self.log(f"Ошибка перемещения {p}: {err}", error=True))
            
            if idx % 10 == 0:
                self.root.after(0, lambda i=idx, t=len(self.found_files): 
                    self.update_status(f"Перемещение: {i}/{t} файлов"))
        
        duration = (datetime.datetime.now() - start_time).total_seconds()
        self.root.after(0, lambda: self.on_move_complete(results, success_count, error_count, duration, archive_base))
    
    def on_move_complete(self, results, success, errors, duration, archive_path):
        status_text = f"Перемещение завершено: {success} успешно, {errors} ошибок"
        self.update_status(status_text, error=(errors > 0))
        self.log(status_text, success=(errors == 0), error=(errors > 0))
        
        # Сохранение отчета с учетом опции
        report_path = filedialog.asksaveasfilename(
            title="Сохранить отчет о перемещении",
            defaultextension=".json" if not self.save_txt_report_var.get() else ".txt",
            filetypes=[
                ("Text files", "*.txt") if self.save_txt_report_var.get() else ("JSON files", "*.json"),
                ("JSON files", "*.json"),
                ("All files", "*.*")
            ],
            initialfile=f"archive_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
        )
        
        if report_path:
            # Определяем формат файла по расширению
            if report_path.endswith('.json'):
                self.save_move_report_json(report_path, results, archive_base)
                self.log(f"Отчет сохранен в формате JSON: {report_path}", success=True)
            elif report_path.endswith('.txt'):
                self.save_move_report_txt(report_path, results, archive_path, success, errors, duration)
                self.log(f"Отчет сохранен в формате TXT: {report_path}", success=True)
            
            messagebox.showinfo("Готово", 
                f"Перемещение завершено!\nУспешно: {success}\nОшибок: {errors}\nОтчет: {report_path}")
        else:
            self.log("Сохранение отчета отменено", error=True)
        
        self.found_files = []
        self.move_btn.config(state="disabled")
    
    def save_search_report(self, results, time_type, start_dt, end_dt, skipped_by_path):
        # Сохранение отчета в формате JSON всегда
        json_path = filedialog.asksaveasfilename(
            title="Сохранить отчет о найденных файлах",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"search_report_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        
        if not json_path:
            return
        
        # Сохраняем в формате JSON
        self.save_search_report_json(json_path, results, time_type, start_dt, end_dt, skipped_by_path)
        self.log(f"Отчет о поиске сохранен в формате JSON: {json_path}", success=True)
        
        # Сохраняем в формате TXT только если опция включена
        if self.save_txt_report_var.get():
            txt_path = json_path.replace('.json', '.txt')
            self.save_search_report_txt(txt_path, results, time_type, start_dt, end_dt, skipped_by_path)
            self.log(f"Отчет о поиске сохранен в формате TXT: {txt_path}", success=True)
    
    def save_search_report_txt(self, path, results, time_type, start_dt, end_dt, skipped_by_path):
        """Сохранение отчета о поиске в формате TXT"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("ОТЧЕТ О НАЙДЕННЫХ ФАЙЛАХ (Поиск)\n")
            f.write("="*80 + "\n")
            f.write(f"Дата формирования: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
            f.write(f"Исходная папка: {self.source_root}\n")
            f.write(f"Тип даты: {time_type}\n")
            f.write(f"Период поиска: с {start_dt.strftime('%d.%m.%Y %H:%M')} по {end_dt.strftime('%d.%m.%Y %H:%M')}\n")
            f.write(f"Найдено файлов: {len(results)}\n")
            f.write("\nПАРАМЕТРЫ ИСКЛЮЧЕНИЙ:\n")
            f.write(f"  Пропускать скрытые: {'Да' if self.skip_hidden_var.get() else 'Нет'}\n")
            f.write(f"  Маски файлов: {self.exclude_files_var.get()}\n")
            f.write(f"  Маски папок: {self.exclude_dirs_var.get()}\n")
            f.write(f"  Исключенные ПОЛНЫЕ ПУТИ к папкам:\n")
            if self.exclude_paths_var.get().strip():
                for path in self.exclude_paths_var.get().split(','):
                    f.write(f"    • {path.strip()}\n")
            else:
                f.write("    (нет)\n")
            f.write(f"  Исключать файлы меньше: {self.min_size_var.get() if self.exclude_small_var.get() else 'НЕТ'} КБ\n")
            f.write(f"  Системные папки ($RECYCLE.BIN и др.) всегда исключаются\n")
            f.write(f"\nСТАТИСТИКА ПРОПУСКОВ:\n")
            f.write(f"  По полным путям: {skipped_by_path} папок (полностью)\n")
            f.write("="*80 + "\n\n")
            f.write("ВАЖНО: Это отчет ТОЛЬКО о найденных файлах. Файлы НЕ были перемещены!\n")
            f.write("Для перемещения вернитесь в программу и нажмите 'Переместить в архив'\n\n")
            f.write("-"*80 + "\n")
            
            for src, dt in results:
                f.write(f"Путь: {src}\n")
                f.write(f"Дата: {dt.strftime('%d.%m.%Y %H:%M:%S')}\n")
                f.write("-"*80 + "\n")
    
    def save_search_report_json(self, path, results, time_type, start_dt, end_dt, skipped_by_path):
        """Сохранение отчета о поиске в формате JSON"""
        report_data = {
            "metadata": {
                "generated": datetime.datetime.now().isoformat(),
                "source_folder": self.source_root,
                "time_type": time_type,
                "period_start": start_dt.isoformat(),
                "period_end": end_dt.isoformat(),
                "total_found": len(results),
                "search_params": {
                    "skip_hidden": self.skip_hidden_var.get(),
                    "exclude_files": self.exclude_files_var.get(),
                    "exclude_dirs": self.exclude_dirs_var.get(),
                    "exclude_paths": self.exclude_paths_var.get(),
                    "exclude_small": self.exclude_small_var.get(),
                    "min_size_kb": int(self.min_size_var.get()) if self.min_size_var.get().isdigit() else 0
                },
                "statistics": {
                    "skipped_by_path": skipped_by_path
                }
            },
            "files": [
                {
                    "path": src,
                    "date": dt.isoformat()
                }
                for src, dt in results
            ]
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    def save_move_report_txt(self, path, results, archive_path, success, errors, duration):
        """Сохранение отчета о перемещении в формате TXT"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("ОТЧЕТ О ПЕРЕМЕЩЕНИИ ФАЙЛОВ В АРХИВ\n")
            f.write("="*80 + "\n")
            f.write(f"Дата: {datetime.datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n")
            f.write(f"Исходная папка: {self.source_root}\n")
            f.write(f"Папка архива: {archive_path}\n")
            f.write(f"Время операции: {duration:.1f} секунд\n")
            f.write(f"Успешно перемещено: {success}\n")
            f.write(f"Ошибок: {errors}\n")
            f.write("\nПАРАМЕТРЫ ИСКЛЮЧЕНИЙ ПРИ ПОИСКЕ:\n")
            f.write(f"  Пропускать скрытые: {'Да' if self.skip_hidden_var.get() else 'Нет'}\n")
            f.write(f"  Маски файлов: {self.exclude_files_var.get()}\n")
            f.write(f"  Маски папок: {self.exclude_dirs_var.get()}\n")
            f.write(f"  Исключенные ПОЛНЫЕ ПУТИ к папкам:\n")
            if self.exclude_paths_var.get().strip():
                for path in self.exclude_paths_var.get().split(','):
                    f.write(f"    • {path.strip()}\n")
            else:
                f.write("    (нет)\n")
            f.write(f"  Исключать файлы меньше: {self.min_size_var.get() if self.exclude_small_var.get() else 'НЕТ'} КБ\n")
            f.write("="*80 + "\n\n")
            f.write("ДЕТАЛИ ПО КАЖДОМУ ФАЙЛУ:\n")
            f.write("-"*80 + "\n")
            for src, dest, status, msg in results:
                f.write(f"Статус: {status}\n")
                f.write(f"Исходный путь: {src}\n")
                if status == "УСПЕХ":
                    f.write(f"Путь в архиве: {dest}\n")
                if msg:
                    f.write(f"Ошибка: {msg}\n")
                f.write("-"*80 + "\n")
    
    def save_move_report_json(self, path, results, archive_path):
        """Сохранение отчета о перемещении в формате JSON"""
        report_data = {
            "metadata": {
                "generated": datetime.datetime.now().isoformat(),
                "source_folder": self.source_root,
                "archive_folder": archive_path,
                "total_files": len(results),
                "success_count": sum(1 for r in results if r[2] == "УСПЕХ"),
                "error_count": sum(1 for r in results if r[2] == "ОШИБКА"),
                "search_params": {
                    "skip_hidden": self.skip_hidden_var.get(),
                    "exclude_files": self.exclude_files_var.get(),
                    "exclude_dirs": self.exclude_dirs_var.get(),
                    "exclude_paths": self.exclude_paths_var.get(),
                    "exclude_small": self.exclude_small_var.get(),
                    "min_size_kb": int(self.min_size_var.get()) if self.min_size_var.get().isdigit() else 0
                }
            },
            "files": [
                {
                    "source_path": src,
                    "archive_path": dest,
                    "status": status,
                    "error_message": msg if msg else None
                }
                for src, dest, status, msg in results
            ]
        }
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report_data, f, ensure_ascii=False, indent=2)
    
    def cancel_operation(self):
        self.cancel_flag = True
        self.log("Запрошена отмена операции...", error=True)
        self.update_status("Отмена операции...")
    
    def finalize_operation(self):
        self.is_running = False
        self.cancel_btn.config(state="disabled")
        self.search_btn.config(state="normal")
        self.validate_inputs()
    
    def show_help(self):
        help_text = (
            "ИНСТРУКЦИЯ:\n\n"
            "🎯 ДЛЯ АРХИВАЦИИ НЕИСПОЛЬЗУЕМЫХ ФАЙЛОВ:\n"
            "1. Выберите 'Время изменения' (рекомендуется)\n"
            "2. Установите период: 'Дата до' = вчера (или дата, до которой файлы считаются старыми)\n"
            "3. На вкладке 'Исключения' настройте правила:\n"
            "   • Маски файлов/папок (по умолчанию разумные значения)\n"
            "   • НОВОЕ: Добавьте ПОЛНЫЕ ПУТИ к папкам, которые нужно полностью исключить (кнопка '➕ Добавить папку')\n"
            "4. На вкладке 'Дополнительно' можно отключить сохранение отчетов в формате .txt\n"
            "5. Нажмите 'Найти файлы в периоде'\n"
            "6. После проверки отчета — переместите в архив\n\n"
            "✨ КЛЮЧЕВОЕ УЛУЧШЕНИЕ:\n"
            "• Исключение ПОЛНЫХ ПУТЕЙ к папкам (с содержимым):\n"
            "  - Нажмите '➕ Добавить папку'\n"
            "  - Выберите папку в проводнике\n"
            "  - Вся папка и её содержимое будут пропущены при поиске\n"
            "  - Можно добавить несколько папок через запятую\n"
            "  - Поддерживаются абсолютные и относительные пути\n\n"
            "📄 НОВОЕ: ОТЧЕТЫ В ФОРМАТЕ .TXT (НЕОБЯЗАТЕЛЬНО):\n"
            "• Вкладка 'Дополнительно' → чекбокс 'Сохранять отчеты в формате .txt'\n"
            "• ✅ Включено: сохраняются отчеты в формате .txt И .json (по умолчанию)\n"
            "• ❌ Отключено: сохраняются только отчеты в формате .json\n"
            "• Отчеты в формате .json всегда сохраняются (содержат полные метаданные)\n"
            "• Отчеты в формате .txt удобны для чтения человеком\n\n"
            "💡 ПРИМЕРЫ ИСПОЛЬЗОВАНИЯ:\n"
            "• Исключить папку 'C:\\Data\\Temp' со всем содержимым\n"
            "• Исключить 'Projects\\Legacy' (относительно исходной папки)\n"
            "• Отключить отчеты .txt для экономии места на диске\n"
            "• Оставить только .json для автоматической обработки отчетов\n\n"
            "⚠️ КРИТИЧЕСКИ ВАЖНО:\n"
            "• 'Время доступа' часто НЕДЕЙСТВИТЕЛЬНО в Windows! Используйте 'Время изменения'.\n"
            "• Для архивации старых файлов период должен ЗАКАНЧИВАТЬСЯ ДО текущей даты.\n"
            "• Перед операцией убедитесь, что файлы не открыты в других программах.\n"
            "• Сделайте резервную копию критичных данных.\n\n"
            "💾 Все настройки автоматически сохраняются между запусками!"
        )
        messagebox.showinfo("Справка", help_text)

if __name__ == "__main__":
    if sys.platform == 'win32':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            pass
    
    root = tk.Tk()
    app = ArchiveMoverApp(root)
    root.mainloop()