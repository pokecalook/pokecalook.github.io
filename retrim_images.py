"""既存の画像ファイルを一括で余白トリミングする（1回実行用）"""
import os
from PIL import Image

IMAGES_DIR = "images"
THR = 250
count = 0
skipped = 0

for fname in os.listdir(IMAGES_DIR):
    if not fname.endswith(".webp"):
        continue
    if fname.startswith("box_") or fname.startswith("tw_"):
        continue
    filepath = os.path.join(IMAGES_DIR, fname)
    try:
        img = Image.open(filepath).convert("RGB")
        w, h = img.size
        top = 0
        for y in range(h):
            if all(img.getpixel((x, y))[0] > THR and img.getpixel((x, y))[1] > THR and img.getpixel((x, y))[2] > THR for x in range(0, w, 3)):
                top = y + 1
            else:
                break
        bot = h
        for y in range(h - 1, -1, -1):
            if all(img.getpixel((x, y))[0] > THR and img.getpixel((x, y))[1] > THR and img.getpixel((x, y))[2] > THR for x in range(0, w, 3)):
                bot = y
            else:
                break
        left = 0
        for x in range(w):
            if all(img.getpixel((x, y))[0] > THR and img.getpixel((x, y))[1] > THR and img.getpixel((x, y))[2] > THR for y in range(0, h, 3)):
                left = x + 1
            else:
                break
        right = w
        for x in range(w - 1, -1, -1):
            if all(img.getpixel((x, y))[0] > THR and img.getpixel((x, y))[1] > THR and img.getpixel((x, y))[2] > THR for y in range(0, h, 3)):
                right = x
            else:
                break
        if top > 0 or bot < h or left > 0 or right < w:
            img = img.crop((left, top, right, bot))
            img.save(filepath, "WEBP", quality=90)
            count += 1
        else:
            skipped += 1
    except Exception as e:
        print(f"  エラー: {fname}: {e}")

print(f"トリミング完了: {count}枚処理, {skipped}枚変更なし")
