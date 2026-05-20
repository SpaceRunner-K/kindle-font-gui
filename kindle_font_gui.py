import os
import re
import sys
import copy
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from fontTools.ttLib import TTFont

APP_TITLE = "Kindle Font Inspector & Fixer"
TARGET_EXTS = [("Font Files", "*.otf *.ttf"), ("All Files", "*.*")]

WIN_EN = (3, 1, 0x409)
WIN_JA = (3, 1, 0x411)
MAC_EN = (1, 0, 0x000)
MAC_JA = (1, 1, 0x00B)
NAME_IDS_PRIMARY = [1, 2, 3, 4, 5, 6, 16, 17, 20]
PS_NAME_ALLOWED_TARGETS = {(3, 1), (1, 0)}
STYLE_KEYWORD_MAP = {
    "regular": "Regular",
    "medium": "Regular",
    "bold": "Bold",
    "heavy": "Bold",
    "black": "Bold",
    "semibold": "Bold",
    "demibold": "Bold",
}


def sanitize_ps_name(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[^A-Za-z0-9\-\.]", "", text)
    text = re.sub(r"-+", "-", text).strip("-.")
    return text or "Font"


def format_bits(value: int, width: int = 16) -> str:
    b = bin(value)[2:].zfill(width)
    return " ".join(b[i:i + 8] for i in range(0, len(b), 8))


def name_record_text(rec):
    try:
        return rec.toUnicode()
    except Exception:
        try:
            return str(rec.string, errors="replace")
        except Exception:
            return "<unreadable>"


def guess_style_from_path(path: str) -> str:
    stem = Path(path).stem.lower()
    for kw, style in STYLE_KEYWORD_MAP.items():
        if kw in stem:
            return style
    return "Regular"


def open_folder(path: str):
    try:
        if os.name == "nt":
            os.startfile(path)
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except Exception:
        pass


class FontEditor:
    def __init__(self):
        self.path = None
        self.font = None
        self.loaded_index = None
        self.current_summary = {}

    def close(self):
        if self.font is not None:
            try:
                self.font.close()
            except Exception:
                pass
        self.font = None
        self.path = None
        self.loaded_index = None
        self.current_summary = {}

    def load(self, path: str, font_number: int = 0):
        self.close()
        self.path = path
        self.loaded_index = font_number
        self.font = TTFont(path, fontNumber=font_number)
        self.current_summary = self.analyze()
        return self.current_summary

    def analyze(self):
        font = self.font
        name = font["name"] if "name" in font else None
        os2 = font["OS/2"] if "OS/2" in font else None
        head = font["head"] if "head" in font else None

        debug_names = {}
        if name:
            for nid in NAME_IDS_PRIMARY:
                debug_names[nid] = name.getDebugName(nid) or ""

        tables = sorted(font.keys())
        summary = {
            "path": self.path,
            "font_number": self.loaded_index,
            "sfntVersion": getattr(font.reader, "sfntVersion", ""),
            "tables": tables,
            "has_vorg": "VORG" in tables,
            "has_gsub": "GSUB" in tables,
            "has_gpos": "GPOS" in tables,
            "name": debug_names,
            "os2_version": getattr(os2, "version", None),
            "weight": getattr(os2, "usWeightClass", None),
            "width": getattr(os2, "usWidthClass", None),
            "vendor": getattr(os2, "achVendID", "") if os2 else "",
            "fsSelection": getattr(os2, "fsSelection", None),
            "macStyle": getattr(head, "macStyle", None),
            "name_records": [],
        }
        if name:
            for rec in name.names:
                summary["name_records"].append({
                    "nameID": rec.nameID,
                    "platformID": rec.platformID,
                    "platEncID": rec.platEncID,
                    "langID": rec.langID,
                    "text": name_record_text(rec),
                })
        return summary

    def _unique_keys(self, name_table, name_id):
        seen, rows = set(), []
        for rec in name_table.names:
            if rec.nameID == name_id:
                key = (rec.platformID, rec.platEncID, rec.langID)
                if key not in seen:
                    seen.add(key)
                    rows.append(key)
        return rows

    def _set_on_existing(self, name_table, name_id, value_map, fallback_keys=None):
        targets = self._unique_keys(name_table, name_id)
        if not targets and fallback_keys:
            targets = fallback_keys
        for key in targets:
            val = value_map.get(key)
            if val is not None:
                name_table.setName(val, name_id, *key)

    def apply_preset(self, *, family_en, family_ja, style, weight_mode, keep_typographic, add_wws):
        if self.font is None:
            raise RuntimeError("No font loaded")

        font = self.font
        name = font["name"]
        os2 = font["OS/2"] if "OS/2" in font else None
        head = font["head"] if "head" in font else None

        is_bold = (style == "Bold")
        legacy_sub = "Bold" if is_bold else "Regular"
        weight = int(os2.usWeightClass) if (weight_mode == "preserve" and os2 is not None) else (700 if is_bold else 400)

        full_en = f"{family_en} {legacy_sub}".strip()
        full_ja = f"{family_ja} {legacy_sub}".strip() if family_ja else None
        ps_base = sanitize_ps_name(family_en)
        ps_name = f"{ps_base}-{legacy_sub}"
        version = name.getDebugName(5) or "Version 1.000"
        vendor = getattr(os2, "achVendID", "UKWN") if os2 else "UKWN"
        unique_id = f"{version};{vendor};{ps_name}"

        if not keep_typographic:
            name.names = [r for r in name.names if r.nameID not in {16, 17, 21, 22}]

        v1 = {WIN_EN: family_en, MAC_EN: family_en}
        if family_ja:
            v1.update({WIN_JA: family_ja, MAC_JA: family_ja})
        self._set_on_existing(name, 1, v1, [WIN_EN, MAC_EN])

        v2 = {WIN_EN: legacy_sub, MAC_EN: legacy_sub, WIN_JA: legacy_sub, MAC_JA: legacy_sub}
        self._set_on_existing(name, 2, v2, [WIN_EN, MAC_EN])

        v3 = {WIN_EN: unique_id, MAC_EN: unique_id}
        self._set_on_existing(name, 3, v3, [WIN_EN])

        v4 = {WIN_EN: full_en, MAC_EN: full_en}
        if family_ja:
            v4.update({WIN_JA: full_ja, MAC_JA: full_ja})
        self._set_on_existing(name, 4, v4, [WIN_EN, MAC_EN])

        targets_id6 = [key for key in self._unique_keys(name, 6) if (key[0], key[1]) in PS_NAME_ALLOWED_TARGETS]
        if not targets_id6:
            targets_id6 = [WIN_EN, MAC_EN]
        for key in targets_id6:
            name.setName(ps_name, 6, *key)

        if keep_typographic:
            v16 = {WIN_EN: family_en, MAC_EN: family_en}
            v17 = {WIN_EN: legacy_sub, MAC_EN: legacy_sub}
            if family_ja:
                v16.update({WIN_JA: family_ja, MAC_JA: family_ja})
                v17.update({WIN_JA: legacy_sub, MAC_JA: legacy_sub})
            self._set_on_existing(name, 16, v16, [WIN_EN])
            self._set_on_existing(name, 17, v17, [WIN_EN])

        if os2 is not None:
            os2.usWeightClass = weight
            for bit in (0, 5, 6, 8):
                os2.fsSelection &= ~(1 << bit)
            if is_bold:
                os2.fsSelection |= (1 << 5)
            else:
                os2.fsSelection |= (1 << 6)
            if add_wws and os2.version is not None and int(os2.version) >= 4:
                os2.fsSelection |= (1 << 8)

        if head is not None:
            head.macStyle &= ~0b11
            if is_bold:
                head.macStyle |= 0b01

        self.current_summary = self.analyze()
        return self.current_summary

    def save_copy(self, out_path: str):
        if self.font is None:
            raise RuntimeError("No font loaded")
        self.font.save(out_path)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1300x900")
        self.minsize(1080, 760)
        self.editors = {"Regular": FontEditor(), "Bold": FontEditor()}
        self.summaries = {"Regular": None, "Bold": None}
        self.last_saved_files = []
        self._build()

    def _build(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=(10, 10, 10, 4))
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=1)
        ttk.Label(
            top,
            text="Single flow: 1本または2本のフォントを選択 → family名/オプション設定 → 事前チェック → 保存 → 事後チェック",
            font=("TkDefaultFont", 10, "bold")
        ).grid(row=0, column=0, sticky="w")

        body = ttk.Panedwindow(self, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 6))

        left = ttk.Frame(body, padding=8)
        center = ttk.Frame(body, padding=8)
        right = ttk.Frame(body, padding=8)
        body.add(left, weight=3)
        body.add(center, weight=3)
        body.add(right, weight=2)

        self._build_left(left)
        self._build_center(center)
        self._build_right(right)

        bottom = ttk.Frame(self, padding=(10, 0, 10, 8))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(bottom, textvariable=self.status_var).grid(row=0, column=0, sticky="w")

    def _build_left(self, parent):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="1. Input fonts", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))

        self.path_vars = {"Regular": tk.StringVar(), "Bold": tk.StringVar()}
        self.style_override_vars = {"Regular": tk.StringVar(value="Regular"), "Bold": tk.StringVar(value="Bold")}

        row = 1
        for role in ("Regular", "Bold"):
            ttk.Label(parent, text=f"{role} file:").grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(parent, textvariable=self.path_vars[role]).grid(row=row, column=1, sticky="ew", pady=4)
            ttk.Button(parent, text="Browse", command=lambda r=role: self.browse_font(r)).grid(row=row, column=2, padx=(6, 0), pady=4)
            row += 1

            ttk.Label(parent, text=f"{role} style:").grid(row=row, column=0, sticky="w", pady=(0, 8))
            ttk.Combobox(parent, textvariable=self.style_override_vars[role], values=["Regular", "Bold"], state="readonly", width=12).grid(row=row, column=1, sticky="w", pady=(0, 8))
            ttk.Button(parent, text="Guess", command=lambda r=role: self.guess_style_for(r)).grid(row=row, column=2, padx=(6, 0), pady=(0, 8))
            row += 1

        ttk.Button(parent, text="Load selected fonts", command=self.load_selected_fonts).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 8))
        row += 1

        ttk.Separator(parent).grid(row=row, column=0, columnspan=3, sticky="ew", pady=8)
        row += 1

        ttk.Label(parent, text="Loaded summaries", font=("TkDefaultFont", 10, "bold")).grid(row=row, column=0, columnspan=3, sticky="w")
        row += 1

        self.loaded_text = tk.Text(parent, width=48, height=24, wrap="word", font=("TkDefaultFont", 9))
        self.loaded_text.grid(row=row, column=0, columnspan=3, sticky="nsew")
        parent.rowconfigure(row, weight=1)

    def _build_center(self, parent):
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)
        ttk.Label(parent, text="2. Spec preview", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, sticky="w", pady=(0, 8))

        cols = ("role", "nameID", "platformID", "platEncID", "langID", "text")
        tree = ttk.Treeview(parent, columns=cols, show="headings")
        self.tree = tree
        for col, width in [("role", 70), ("nameID", 60), ("platformID", 80), ("platEncID", 80), ("langID", 80), ("text", 420)]:
            tree.heading(col, text=col)
            tree.column(col, width=width, anchor="w")
        ys = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
        xs = ttk.Scrollbar(parent, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
        tree.grid(row=1, column=0, sticky="nsew")
        ys.grid(row=1, column=1, sticky="ns")
        xs.grid(row=2, column=0, sticky="ew")

    def _build_right(self, parent):
        parent.columnconfigure(1, weight=1)
        ttk.Label(parent, text="3. Family & options", font=("TkDefaultFont", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        self.family_en_var = tk.StringVar()
        self.family_ja_var = tk.StringVar()
        self.weight_mode_var = tk.StringVar(value="kindle")
        self.keep_typo_var = tk.BooleanVar(value=False)
        self.wws_var = tk.BooleanVar(value=False)
        self.open_folder_var = tk.BooleanVar(value=True)
        self.post_check_var = tk.BooleanVar(value=True)

        ttk.Label(parent, text="Family (EN):").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.family_en_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(parent, text="Family (JA):").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(parent, textvariable=self.family_ja_var).grid(row=2, column=1, sticky="ew", pady=4)

        ttk.Label(parent, text="Weight mode:").grid(row=3, column=0, sticky="w", pady=4)
        ttk.Combobox(parent, textvariable=self.weight_mode_var, values=["kindle", "preserve"], state="readonly").grid(row=3, column=1, sticky="ew", pady=4)

        ttk.Checkbutton(parent, text="Keep name IDs 16/17/21/22", variable=self.keep_typo_var).grid(row=4, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(parent, text="Add WWS bit when OS/2 version >= 4", variable=self.wws_var).grid(row=5, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(parent, text="Run post-save file check", variable=self.post_check_var).grid(row=6, column=0, columnspan=2, sticky="w", pady=3)
        ttk.Checkbutton(parent, text="Open output folder after save", variable=self.open_folder_var).grid(row=7, column=0, columnspan=2, sticky="w", pady=3)

        ttk.Button(parent, text="Fill family from loaded spec", command=self.fill_family_from_loaded).grid(row=8, column=0, columnspan=2, sticky="ew", pady=(8, 4))
        ttk.Button(parent, text="Run pre-save check", command=self.run_pre_save_check).grid(row=9, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(parent, text="Preview transformed spec", command=self.preview_transformed_spec).grid(row=10, column=0, columnspan=2, sticky="ew", pady=4)
        ttk.Button(parent, text="Save all", command=self.save_all).grid(row=11, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        ttk.Separator(parent).grid(row=12, column=0, columnspan=2, sticky="ew", pady=10)
        ttk.Label(parent, text="4. Validation report", font=("TkDefaultFont", 10, "bold")).grid(row=13, column=0, columnspan=2, sticky="w", pady=(0, 4))
        self.verify_text = tk.Text(parent, width=40, height=20, wrap="word", font=("TkDefaultFont", 9))
        self.verify_text.grid(row=14, column=0, columnspan=2, sticky="nsew", pady=(6, 0))
        parent.rowconfigure(14, weight=1)

    def browse_font(self, role):
        path = filedialog.askopenfilename(filetypes=TARGET_EXTS)
        if path:
            self.path_vars[role].set(path)
            self.style_override_vars[role].set(guess_style_from_path(path))

    def guess_style_for(self, role):
        path = self.path_vars[role].get().strip()
        if path:
            self.style_override_vars[role].set(guess_style_from_path(path))

    def load_selected_fonts(self):
        loaded_any = False
        self.loaded_text.delete("1.0", tk.END)
        self.verify_text.delete("1.0", tk.END)
        for item in self.tree.get_children():
            self.tree.delete(item)

        for role in ("Regular", "Bold"):
            path = self.path_vars[role].get().strip()
            self.summaries[role] = None
            self.editors[role].close()
            if not path:
                continue
            if not os.path.exists(path):
                messagebox.showerror(APP_TITLE, f"{role} file not found:\n{path}")
                return
            try:
                summary = self.editors[role].load(path, 0)
                self.summaries[role] = summary
                loaded_any = True
                self._append_loaded_summary(role, summary)
                for rec in summary.get("name_records", []):
                    self.tree.insert("", tk.END, values=(role, rec["nameID"], rec["platformID"], rec["platEncID"], hex(rec["langID"]), rec["text"]))
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Failed to load {role}:\n{e}")
                return

        if not loaded_any:
            messagebox.showinfo(APP_TITLE, "Select at least one font.")
            return

        self.fill_family_from_loaded()
        self.status_var.set("Fonts loaded. Run pre-save check or save directly.")

    def _append_loaded_summary(self, role, summary):
        self.loaded_text.insert(tk.END, f"[{role}] {os.path.basename(summary['path'])}\n")
        self.loaded_text.insert(tk.END, f"  ID1  : {summary['name'].get(1, '')}\n")
        self.loaded_text.insert(tk.END, f"  ID2  : {summary['name'].get(2, '')}\n")
        self.loaded_text.insert(tk.END, f"  ID4  : {summary['name'].get(4, '')}\n")
        self.loaded_text.insert(tk.END, f"  ID6  : {summary['name'].get(6, '')}\n")
        self.loaded_text.insert(tk.END, f"  ID16 : {summary['name'].get(16, '')}\n")
        self.loaded_text.insert(tk.END, f"  ID17 : {summary['name'].get(17, '')}\n")
        self.loaded_text.insert(tk.END, f"  weight={summary.get('weight')}  os2ver={summary.get('os2_version')}  vendor={summary.get('vendor')}\n")
        self.loaded_text.insert(tk.END, f"  fsSelection={summary.get('fsSelection')}  macStyle={summary.get('macStyle')}\n")
        self.loaded_text.insert(tk.END, f"  tables: {', '.join(summary.get('tables', []))}\n\n")

    def fill_family_from_loaded(self):
        candidates = [self.summaries[r] for r in ("Regular", "Bold") if self.summaries[r]]
        if not candidates:
            return
        first = candidates[0]
        names = first.get("name", {})
        self.family_en_var.set(names.get(16) or names.get(1) or "")
        family_ja = ""
        for rec in first.get("name_records", []):
            if rec["nameID"] in (16, 1) and rec["langID"] in (0x411, 0x00B):
                family_ja = rec["text"]
                break
        self.family_ja_var.set(family_ja)

    def _collect_roles_to_process(self):
        return [role for role in ("Regular", "Bold") if self.summaries[role]]

    def _planned_output_name(self, role, ext=None):
        family_en = self.family_en_var.get().strip() or "Font"
        style = self.style_override_vars[role].get()
        if ext is None:
            editor = self.editors[role]
            ext = Path(editor.path).suffix.lower() or ".otf"
        return f"{sanitize_ps_name(family_en)}-{style}{ext}"

    def _collect_pre_save_checks(self):
        roles = self._collect_roles_to_process()
        results = []
        family_en = self.family_en_var.get().strip()
        family_ja = self.family_ja_var.get().strip()

        if not roles:
            results.append(("error", "No font loaded."))
            return results

        if not family_en:
            results.append(("error", "Family (EN) is empty."))
        else:
            results.append(("ok", f"Family (EN) = {family_en}"))

        ps_base = sanitize_ps_name(family_en)
        if len(ps_base) < 3:
            results.append(("warn", f"Sanitized PostScript base is very short: {ps_base}"))
        else:
            results.append(("ok", f"PostScript base = {ps_base}"))

        styles = [self.style_override_vars[r].get() for r in roles]
        if len(styles) != len(set(styles)):
            results.append(("error", f"Styles are duplicated: {styles}"))
        else:
            results.append(("ok", f"Styles assigned = {', '.join(f'{r}:{self.style_override_vars[r].get()}' for r in roles)}"))

        planned = {}
        duplicates = set()
        for role in roles:
            out_name = self._planned_output_name(role)
            if out_name in planned.values():
                duplicates.add(out_name)
            planned[role] = out_name
        if duplicates:
            results.append(("error", f"Planned output filenames collide: {', '.join(sorted(duplicates))}"))
        else:
            results.append(("ok", "Planned output filenames are unique."))

        if len(roles) == 2:
            results.append(("ok", "Two-font workflow detected; pair linking will be checked."))
        else:
            results.append(("warn", "Only one font loaded. Kindle can synthesize missing bold/italic, but true pair is usually preferable."))

        for role in roles:
            summary = self.summaries[role]
            source_id1 = summary["name"].get(1, "") if summary else ""
            source_id16 = summary["name"].get(16, "") if summary else ""
            results.append(("ok", f"{role} source family = {source_id16 or source_id1}"))
            if summary.get("os2_version") is None:
                results.append(("warn", f"{role} has no OS/2 version info visible."))

        if self.keep_typo_var.get() and len(roles) == 2:
            missing_typo = []
            for role in roles:
                summary = self.summaries[role]
                if not (summary["name"].get(16) or summary["name"].get(17)):
                    missing_typo.append(role)
            if missing_typo:
                results.append(("warn", f"Keep typographic IDs is ON, but missing ID16/17 in: {', '.join(missing_typo)}"))
            else:
                results.append(("ok", "Typographic IDs exist in both loaded fonts."))

        if family_ja:
            results.append(("ok", f"Family (JA) = {family_ja}"))

        return results

    def run_pre_save_check(self):
        results = self._collect_pre_save_checks()
        self.verify_text.delete("1.0", tk.END)
        self.verify_text.insert(tk.END, "Pre-save validation\n")
        self.verify_text.insert(tk.END, "=" * 64 + "\n")
        has_error = False
        has_warn = False
        for level, text in results:
            mark = {"ok": "[OK] ", "warn": "[WARN] ", "error": "[ERROR] "}[level]
            self.verify_text.insert(tk.END, f"{mark}{text}\n")
            if level == "error":
                has_error = True
            elif level == "warn":
                has_warn = True

        if len(self._collect_roles_to_process()) == 2:
            self.verify_text.insert(tk.END, "\n")
            self.verify_text.insert(tk.END, self._build_pair_preview_report())

        if has_error:
            self.status_var.set("Pre-save check found errors.")
        elif has_warn:
            self.status_var.set("Pre-save check passed with warnings.")
        else:
            self.status_var.set("Pre-save check passed.")

    def _build_pair_preview_report(self):
        reg_role = "Regular"
        bold_role = "Bold"
        if not self.summaries[reg_role] or not self.summaries[bold_role]:
            return ""

        lines = []
        lines.append("Pair preview")
        lines.append("-" * 64)
        lines.append(f"Target family: {self.family_en_var.get().strip()}")
        lines.append(f"Planned filenames: {self._planned_output_name(reg_role)} / {self._planned_output_name(bold_role)}")
        lines.append(f"Assigned styles: {reg_role}={self.style_override_vars[reg_role].get()}, {bold_role}={self.style_override_vars[bold_role].get()}")
        fam_ok = bool(self.family_en_var.get().strip())
        style_ok = self.style_override_vars[reg_role].get() != self.style_override_vars[bold_role].get()
        lines.append(f"Family target set: {'OK' if fam_ok else 'NG'}")
        lines.append(f"Style split valid: {'OK' if style_ok else 'NG'}")
        return "\n".join(lines) + "\n"

    def preview_transformed_spec(self):
        roles = self._collect_roles_to_process()
        if not roles:
            messagebox.showinfo(APP_TITLE, "Load at least one font first.")
            return
        family_en = self.family_en_var.get().strip()
        if not family_en:
            messagebox.showerror(APP_TITLE, "Family (EN) is required.")
            return

        self.verify_text.delete("1.0", tk.END)
        self.verify_text.insert(tk.END, "Preview (in memory only)\n")
        self.verify_text.insert(tk.END, "=" * 64 + "\n\n")

        preview_rows = []
        for role in roles:
            editor = self.editors[role]
            tmp_font = copy.deepcopy(editor.font)
            tmp_editor = FontEditor()
            tmp_editor.font = tmp_font
            tmp_editor.path = editor.path
            try:
                summary = tmp_editor.apply_preset(
                    family_en=family_en,
                    family_ja=self.family_ja_var.get().strip(),
                    style=self.style_override_vars[role].get(),
                    weight_mode=self.weight_mode_var.get(),
                    keep_typographic=self.keep_typo_var.get(),
                    add_wws=self.wws_var.get(),
                )
                preview_rows.append((role, summary))
                self.verify_text.insert(tk.END, f"[{role}]\n")
                self.verify_text.insert(tk.END, f"  Planned file : {self._planned_output_name(role)}\n")
                self.verify_text.insert(tk.END, f"  ID1          : {summary['name'].get(1, '')}\n")
                self.verify_text.insert(tk.END, f"  ID2          : {summary['name'].get(2, '')}\n")
                self.verify_text.insert(tk.END, f"  ID4          : {summary['name'].get(4, '')}\n")
                self.verify_text.insert(tk.END, f"  ID6          : {summary['name'].get(6, '')}\n")
                self.verify_text.insert(tk.END, f"  weight       : {summary.get('weight')}\n")
                self.verify_text.insert(tk.END, f"  fsSelection  : {summary.get('fsSelection')}\n")
                self.verify_text.insert(tk.END, f"  macStyle     : {summary.get('macStyle')}\n\n")
            except Exception as e:
                self.verify_text.insert(tk.END, f"[{role}] preview error: {e}\n\n")

        if len(preview_rows) == 2:
            reg = next(s for r, s in preview_rows if r == "Regular")
            bold = next(s for r, s in preview_rows if r == "Bold")
            fam_ok = reg['name'].get(1, '') == bold['name'].get(1, '')
            self.verify_text.insert(tk.END, f"Pair check: ID1 family match = {'OK' if fam_ok else 'NG'}\n")
        self.status_var.set("Preview generated in memory.")

    def _validate_saved_font(self, path, expected_style):
        report = []
        ok = True
        expected_family = self.family_en_var.get().strip()
        expected_ps = f"{sanitize_ps_name(expected_family)}-{expected_style}"
        try:
            font = TTFont(path, fontNumber=0)
            name = font["name"] if "name" in font else None
            os2 = font["OS/2"] if "OS/2" in font else None
            head = font["head"] if "head" in font else None

            basename = os.path.basename(path)
            expected_suffix = f"-{expected_style}{Path(path).suffix.lower()}"
            if basename.endswith(expected_suffix):
                report.append(("ok", f"Filename matches style suffix: {basename}"))
            else:
                ok = False
                report.append(("error", f"Filename does not match expected suffix {expected_suffix}: {basename}"))

            id1 = name.getDebugName(1) if name else ""
            id2 = name.getDebugName(2) if name else ""
            id6 = name.getDebugName(6) if name else ""

            if id1 == expected_family:
                report.append(("ok", f"name ID 1 matches target family: {id1}"))
            else:
                ok = False
                report.append(("error", f"name ID 1 mismatch: got '{id1}', expected '{expected_family}'"))

            if id2 == expected_style:
                report.append(("ok", f"name ID 2 matches target style: {id2}"))
            else:
                ok = False
                report.append(("error", f"name ID 2 mismatch: got '{id2}', expected '{expected_style}'"))

            if id6 == expected_ps:
                report.append(("ok", f"name ID 6 matches PostScript name: {id6}"))
            else:
                ok = False
                report.append(("error", f"name ID 6 mismatch: got '{id6}', expected '{expected_ps}'"))

            if os2 is not None:
                expected_weight = 700 if expected_style == "Bold" else 400
                if self.weight_mode_var.get() == "kindle":
                    if int(os2.usWeightClass) == expected_weight:
                        report.append(("ok", f"usWeightClass = {os2.usWeightClass}"))
                    else:
                        ok = False
                        report.append(("error", f"usWeightClass mismatch: got {os2.usWeightClass}, expected {expected_weight}"))
                else:
                    report.append(("ok", f"usWeightClass preserved: {os2.usWeightClass}"))

                if expected_style == "Bold":
                    if os2.fsSelection & (1 << 5):
                        report.append(("ok", f"fsSelection bold bit set: {format_bits(os2.fsSelection)}"))
                    else:
                        ok = False
                        report.append(("error", f"fsSelection bold bit not set: {format_bits(os2.fsSelection)}"))
                else:
                    if os2.fsSelection & (1 << 6):
                        report.append(("ok", f"fsSelection regular bit set: {format_bits(os2.fsSelection)}"))
                    else:
                        ok = False
                        report.append(("error", f"fsSelection regular bit not set: {format_bits(os2.fsSelection)}"))

            if head is not None:
                if expected_style == "Bold":
                    if head.macStyle & 0b01:
                        report.append(("ok", f"head.macStyle bold bit set: {format_bits(head.macStyle)}"))
                    else:
                        ok = False
                        report.append(("error", f"head.macStyle bold bit not set: {format_bits(head.macStyle)}"))
                else:
                    if head.macStyle & 0b01:
                        ok = False
                        report.append(("error", f"head.macStyle bold bit unexpectedly set: {format_bits(head.macStyle)}"))
                    else:
                        report.append(("ok", f"head.macStyle regular state: {format_bits(head.macStyle)}"))

            font.close()
        except Exception as e:
            ok = False
            report.append(("error", f"Failed to reopen saved font: {e}"))
        return ok, report

    def _run_post_save_check(self, saved_files):
        self.verify_text.delete("1.0", tk.END)
        self.verify_text.insert(tk.END, "Post-save file validation\n")
        self.verify_text.insert(tk.END, "=" * 64 + "\n\n")

        overall_ok = True
        pair_data = {}
        for path, style in saved_files:
            ok, report = self._validate_saved_font(path, style)
            pair_data[style] = path
            overall_ok &= ok
            self.verify_text.insert(tk.END, f"[{style}] {os.path.basename(path)}\n")
            for level, text in report:
                mark = {"ok": "[OK] ", "warn": "[WARN] ", "error": "[ERROR] "}[level]
                self.verify_text.insert(tk.END, f"{mark}{text}\n")
            self.verify_text.insert(tk.END, "\n")

        if "Regular" in pair_data and "Bold" in pair_data:
            self.verify_text.insert(tk.END, "Pair file check\n")
            self.verify_text.insert(tk.END, "-" * 64 + "\n")
            try:
                reg_font = TTFont(pair_data["Regular"], fontNumber=0)
                bold_font = TTFont(pair_data["Bold"], fontNumber=0)
                reg_name = reg_font["name"].getDebugName(1) or ""
                bold_name = bold_font["name"].getDebugName(1) or ""
                if reg_name == bold_name:
                    self.verify_text.insert(tk.END, f"[OK] name ID 1 matches across saved pair: {reg_name}\n")
                else:
                    overall_ok = False
                    self.verify_text.insert(tk.END, f"[ERROR] saved pair family mismatch: {reg_name} / {bold_name}\n")
                reg_font.close()
                bold_font.close()
            except Exception as e:
                overall_ok = False
                self.verify_text.insert(tk.END, f"[ERROR] pair file validation failed: {e}\n")

        self.verify_text.insert(tk.END, "\n")
        self.verify_text.insert(tk.END, "=" * 64 + "\n")
        self.verify_text.insert(tk.END, f"Result: {'PASS' if overall_ok else 'FAIL'}\n")
        self.status_var.set("Post-save check passed." if overall_ok else "Post-save check found problems.")
        return overall_ok

    def save_all(self):
        roles = self._collect_roles_to_process()
        if not roles:
            messagebox.showinfo(APP_TITLE, "Load at least one font first.")
            return

        pre_results = self._collect_pre_save_checks()
        errors = [text for level, text in pre_results if level == "error"]
        warns = [text for level, text in pre_results if level == "warn"]
        if errors:
            self.run_pre_save_check()
            messagebox.showerror(APP_TITLE, "Pre-save check found errors. Fix them before saving.")
            return
        if warns:
            self.run_pre_save_check()
            go = messagebox.askyesno(APP_TITLE, "Pre-save check found warnings. Save anyway?")
            if not go:
                return

        family_en = self.family_en_var.get().strip()
        out_dir = filedialog.askdirectory(title="Select output folder")
        if not out_dir:
            return

        saved_files = []
        for role in roles:
            editor = self.editors[role]
            try:
                editor.apply_preset(
                    family_en=family_en,
                    family_ja=self.family_ja_var.get().strip(),
                    style=self.style_override_vars[role].get(),
                    weight_mode=self.weight_mode_var.get(),
                    keep_typographic=self.keep_typo_var.get(),
                    add_wws=self.wws_var.get(),
                )
                ext = Path(editor.path).suffix.lower() or ".otf"
                out_name = self._planned_output_name(role, ext)
                out_path = os.path.join(out_dir, out_name)
                editor.save_copy(out_path)
                saved_files.append((out_path, self.style_override_vars[role].get()))
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"Failed to save {role}:\n{e}")
                return

        self.last_saved_files = saved_files
        msg = "Saved:\n" + "\n".join(path for path, _ in saved_files)
        messagebox.showinfo(APP_TITLE, msg)

        if self.post_check_var.get():
            self._run_post_save_check(saved_files)

        if self.open_folder_var.get():
            open_folder(out_dir)


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
