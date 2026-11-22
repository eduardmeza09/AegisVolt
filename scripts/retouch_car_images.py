"""Retoque de las fotos del vehículo generadas con IA: quita emblemas de marca (capó y tapas de rueda),
recorta y exporta WebP (1800 px y 900 px) a frontend/public/img/.

uso: uv run --with opencv-python-headless --with numpy python scripts/retouch_car_images.py <dir_jpg> frontend/public/img <dir_debug>
  <dir_jpg> debe contener 2.jpg (azul), 3.jpg (gris) y 4.jpg (negro), 2816x1504.
"""

import sys

import cv2
import numpy as np

src, out, dbg = sys.argv[1], sys.argv[2], sys.argv[3]

# (cx, cy, rx, ry) en coordenadas de la imagen original 2816x1504, con margen.
LOGOS = [
    (655, 751, 30, 20),   # escudo del capó
    (1415, 935, 27, 29),  # tapa rueda delantera
    (2362, 882, 20, 25),  # tapa rueda trasera
]
CROP = (300, 300, 2580, 1270)  # x0, y0, x1, y1: auto completo + luz inferior
VARIANTS = {"2": "car-blue", "3": "car-grey", "4": "car-black"}

for n, name in VARIANTS.items():
    img = cv2.imread(f"{src}/{n}.jpg")
    mask = np.zeros(img.shape[:2], np.uint8)
    for cx, cy, rx, ry in LOGOS:
        cv2.ellipse(mask, (cx, cy), (rx, ry), 0, 0, 360, 255, -1)
    clean = cv2.inpaint(img, mask, 9, cv2.INPAINT_TELEA)
    # suaviza la zona retocada para que no quede textura de "mancha"
    blur = cv2.GaussianBlur(clean, (0, 0), 3)
    soft = cv2.GaussianBlur(mask, (0, 0), 4).astype(np.float32)[..., None] / 255.0
    clean = (clean * (1 - soft) + blur * soft).astype(np.uint8)
    # tapas de rueda genéricas: disco oscuro liso con aro metálico tenue (sin emblema)
    for cx, cy, rx, ry in LOGOS[1:]:
        ax = (rx - 6, ry - 6)
        cv2.ellipse(clean, (cx, cy), ax, 0, 0, 360, (24, 22, 20), -1, cv2.LINE_AA)
        cv2.ellipse(clean, (cx, cy), ax, 0, 0, 360, (44, 42, 40), 2, cv2.LINE_AA)
        cv2.ellipse(clean, (cx - 3, cy - 4), (ax[0] // 2, ax[1] // 3), -20, 200, 320, (36, 34, 33), 1, cv2.LINE_AA)

    for i, (cx, cy, rx, ry) in enumerate(LOGOS):  # recortes de control antes/después
        x0, y0 = cx - 70, cy - 70
        pair = np.hstack([img[y0:cy + 70, x0:cx + 70], clean[y0:cy + 70, x0:cx + 70]])
        cv2.imwrite(f"{dbg}/{name}-logo{i}.png", cv2.resize(pair, None, fx=2, fy=2))

    x0, y0, x1, y1 = CROP
    car = clean[y0:y1, x0:x1]
    for width, suffix in ((1800, ""), (900, "-sm")):
        h = round(car.shape[0] * width / car.shape[1])
        resized = cv2.resize(car, (width, h), interpolation=cv2.INTER_AREA)
        cv2.imwrite(f"{out}/{name}{suffix}.webp", resized, [cv2.IMWRITE_WEBP_QUALITY, 82])
    print(name, "ok", car.shape)
