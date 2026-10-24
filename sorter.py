import os
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import filedialog
from PIL import Image, ImageTk

# --- CONFIG ---
LABELS = [
    "cardinal", "bluejay", "woodpecker", "finch",
    "sparrow", "chickadee", "titmouse", "nuthatch",
    "mourning_dove", "starling", "grackle", "cat", "squirrel", "other"
]
IMAGE_EXTS = {".jpg", ".png", ".jpeg"}
# ---------------

class SorterApp:
    def __init__(self, master):
        self.master = master
        master.title("Simple Image Sorter")

        # ask for base folder
        self.src_dir = Path(filedialog.askdirectory(title="Select folder with images"))
        if not self.src_dir:
            master.destroy()
            return

        # destination folder
        self.dst_dir = self.src_dir.parent / "sorted"
        self.dst_dir.mkdir(exist_ok=True)

        for lbl in LABELS:
            (self.dst_dir / lbl).mkdir(exist_ok=True)

        # gather image paths
        self.files = [p for p in self.src_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS]
        self.idx = 0

        # create UI
        self.img_label = tk.Label(master)
        self.img_label.pack(pady=10)

        self.btn_frame = tk.Frame(master)
        self.btn_frame.pack()
        for lbl in LABELS:
            b = tk.Button(self.btn_frame, text=lbl, width=14, command=lambda l=lbl: self.move_image(l))
            b.pack(side=tk.LEFT, padx=4, pady=4)

        self.status = tk.Label(master, text="", fg="gray")
        self.status.pack(pady=5)

        self.show_image()

    def show_image(self):
        if self.idx >= len(self.files):
            self.status.config(text="All done!")
            self.img_label.config(image="")
            return

        path = self.files[self.idx]
        img = Image.open(path)
        img.thumbnail((640, 480))
        self.tk_img = ImageTk.PhotoImage(img)
        self.img_label.config(image=self.tk_img)
        self.status.config(text=f"{self.idx+1}/{len(self.files)}  -  {path.name}")

    def move_image(self, label):
        if self.idx >= len(self.files):
            return
        src = self.files[self.idx]
        dst = self.dst_dir / label / src.name
        shutil.move(src, dst)
        self.idx += 1
        self.show_image()


if __name__ == "__main__":
    root = tk.Tk()
    SorterApp(root)
    root.mainloop()
