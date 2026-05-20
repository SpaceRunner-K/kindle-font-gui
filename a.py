import os
import re
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from fontTools.ttLib import TTFont

def sanitize_ps_name(name):
    # ASCII英数字とハイフン・ピリオドのみ許可（PostScript名仕様）
    return re.sub(r'[^A-Za-z0-9\-.]', '', name)

def select_file():
    path = filedialog.askopenfilename(filetypes=[("Font Files", "*.otf *.ttf")])
    if path:
        entry_file.delete(0, tk.END)
        entry_file.insert(0, path)

def process_font():
    input_path = entry_file.get().strip()
    family_name = entry_family.get().strip()
    style = style_var.get()

    if not input_path or not os.path.exists(input_path):
        messagebox.showerror("エラー", "正しいフォントファイルを選択してください。")
        return
    if not family_name:
        messagebox.showerror("エラー", "新しいファミリー名を入力してください。")
        return

    try:
        font = TTFont(input_path)

        is_bold = (style == "Bold")
        weight_class = 700 if is_bold else 400
        subfamily = "Bold" if is_bold else "Regular"
        full_name = f"{family_name} {subfamily}"

        # PostScript名はASCII文字のみ使用可能なのでサニタイズ
        ps_family = sanitize_ps_name(family_name.replace(' ', ''))
        ps_name = f"{ps_family}-{subfamily}"
        unique_id = f"KindleMod;{ps_name}"

        name_table = font["name"]

        # ID 16, 17, 21, 22 を完全削除（Kindle優先でシンプルなID1/2構成に）
        name_table.names = [r for r in name_table.names if r.nameID not in {16, 17, 21, 22}]

        # 既存レコードの組み合わせを重複排除して取得
        def get_unique_records(name_id):
            seen = set()
            for r in name_table.names:
                if r.nameID == name_id:
                    key = (r.platformID, r.platEncID, r.langID)
                    if key not in seen:
                        seen.add(key)
                        yield r

        # ID 1: ファミリー名（全プラットフォーム・全言語）
        for r in get_unique_records(1):
            name_table.setName(family_name, 1, r.platformID, r.platEncID, r.langID)

        # ID 2: Subfamily（全プラットフォーム・全言語）
        for r in get_unique_records(2):
            name_table.setName(subfamily, 2, r.platformID, r.platEncID, r.langID)

        # ID 3: Unique ID（全プラットフォーム）
        for r in get_unique_records(3):
            name_table.setName(unique_id, 3, r.platformID, r.platEncID, r.langID)

        # ID 4: Full name（全プラットフォーム・全言語）
        for r in get_unique_records(4):
            name_table.setName(full_name, 4, r.platformID, r.platEncID, r.langID)

        # ID 6: PostScript名（Mac英語 と Windows のみ）
        for r in get_unique_records(6):
            if r.platformID == 3 or (r.platformID == 1 and r.platEncID == 0):
                name_table.setName(ps_name, 6, r.platformID, r.platEncID, r.langID)

        # OS/2 テーブルの更新
        if "OS/2" in font:
            os2 = font["OS/2"]
            os2.usWeightClass = weight_class

            for bit in (0, 5, 6):
                os2.fsSelection &= ~(1 << bit)

            if is_bold:
                os2.fsSelection |= (1 << 5)
            else:
                os2.fsSelection |= (1 << 6)

            # bit 8 (WWS) は OS/2 version 4 以上でのみ有効
            if os2.version >= 4:
                os2.fsSelection |= (1 << 8)

        # head テーブルの更新
        if "head" in font:
            head = font["head"]
            head.macStyle &= ~0b11
            if is_bold:
                head.macStyle |= 0b01

        # 保存（元ファイルと同じフォルダに別名で出力）
        dir_name = os.path.dirname(input_path)
        out_name = f"{ps_family}-{subfamily}.otf"
        out_path = os.path.join(dir_name, out_name)

        font.save(out_path)
        messagebox.showinfo("完了", f"保存しました！\n{out_path}")

    except Exception as e:
        messagebox.showerror("エラー", f"処理中にエラーが発生しました:\n{str(e)}")

# --- GUI ---
root = tk.Tk()
root.title("Kindle Custom Font Fixer")
root.geometry("420x250")
root.resizable(False, False)

tk.Label(root, text="1. 変換するフォント (OTF/TTF):").pack(anchor="w", padx=10, pady=(10, 0))
frame_file = tk.Frame(root)
frame_file.pack(fill="x", padx=10)
entry_file = tk.Entry(frame_file)
entry_file.pack(side="left", fill="x", expand=True)
tk.Button(frame_file, text="参照", command=select_file).pack(side="right")

tk.Label(root, text="2. 新しいファミリー名 (例: Ryumin Kindle):").pack(anchor="w", padx=10, pady=(10, 0))
entry_family = tk.Entry(root)
entry_family.pack(fill="x", padx=10)

tk.Label(root, text="3. 割り当てるスタイル:").pack(anchor="w", padx=10, pady=(10, 0))
style_var = tk.StringVar(value="Regular")
frame_style = tk.Frame(root)
frame_style.pack(fill="x", padx=10)
ttk.Radiobutton(frame_style, text="Regular (400)", variable=style_var, value="Regular").pack(side="left", padx=(0, 20))
ttk.Radiobutton(frame_style, text="Bold (700)", variable=style_var, value="Bold").pack(side="left")

tk.Button(root, text="変換して保存", command=process_font,
          bg="#4CAF50", fg="white", font=("Arial", 10, "bold")).pack(pady=20, ipadx=20, ipady=5)

root.mainloop()