"""Generate gender silhouette PNG icons for the seat map."""
import os
from PIL import Image, ImageDraw

SIZE = 64
OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'icons')
os.makedirs(OUT_DIR, exist_ok=True)


def new_canvas():
    return Image.new('RGBA', (SIZE, SIZE), (0, 0, 0, 0))


def draw_male():
    img = new_canvas()
    d = ImageDraw.Draw(img)
    W = SIZE  # 64

    # Head — circle, r=10, centre (32, 13)
    hcx, hcy, hr = W // 2, 13, 10
    d.ellipse([hcx - hr, hcy - hr, hcx + hr, hcy + hr], fill='white')

    # Neck — thin rectangle
    neck_w, neck_h = 7, 5
    nx = W // 2 - neck_w // 2
    ny = hcy + hr
    d.rectangle([nx, ny, nx + neck_w, ny + neck_h], fill='white')

    # Torso — broad rectangle (wide shoulders)
    torso_top = ny + neck_h
    torso_w, torso_h = 30, 16
    tx = W // 2 - torso_w // 2
    d.rectangle([tx, torso_top, tx + torso_w, torso_top + torso_h], fill='white')

    # Legs — two rectangles with a gap
    legs_top = torso_top + torso_h
    leg_w, leg_h = 11, 17
    gap = 8
    lx = W // 2 - gap // 2 - leg_w   # left leg x
    rx = W // 2 + gap // 2             # right leg x
    d.rectangle([lx, legs_top, lx + leg_w, legs_top + leg_h], fill='white')
    d.rectangle([rx, legs_top, rx + leg_w, legs_top + leg_h], fill='white')

    return img


def draw_female():
    img = new_canvas()
    d = ImageDraw.Draw(img)
    W = SIZE  # 64

    # Head — circle, r=9, centre (32, 11)
    hcx, hcy, hr = W // 2, 11, 9
    d.ellipse([hcx - hr, hcy - hr, hcx + hr, hcy + hr], fill='white')

    # Neck — thin
    neck_w, neck_h = 6, 4
    nx = W // 2 - neck_w // 2
    ny = hcy + hr
    d.rectangle([nx, ny, nx + neck_w, ny + neck_h], fill='white')

    # Upper body — narrow rectangle
    body_top = ny + neck_h
    body_w, body_h = 14, 10
    bx = W // 2 - body_w // 2
    d.rectangle([bx, body_top, bx + body_w, body_top + body_h], fill='white')

    # Skirt — trapezoid (wider at bottom)
    skirt_top = body_top + body_h
    skirt_h = 18
    skirt_top_w = 18
    skirt_bot_w = 34
    stx = W // 2 - skirt_top_w // 2
    sbx = W // 2 - skirt_bot_w // 2
    skirt_bot = skirt_top + skirt_h
    d.polygon([
        (stx, skirt_top),
        (stx + skirt_top_w, skirt_top),
        (sbx + skirt_bot_w, skirt_bot),
        (sbx, skirt_bot),
    ], fill='white')

    # Legs — two thin rectangles below skirt
    leg_w, leg_h = 7, 12
    gap = 6
    lx = W // 2 - gap // 2 - leg_w
    rx = W // 2 + gap // 2
    d.rectangle([lx, skirt_bot, lx + leg_w, skirt_bot + leg_h], fill='white')
    d.rectangle([rx, skirt_bot, rx + leg_w, skirt_bot + leg_h], fill='white')

    return img


if __name__ == '__main__':
    male_path = os.path.join(OUT_DIR, 'male.png')
    female_path = os.path.join(OUT_DIR, 'female.png')

    draw_male().save(male_path)
    draw_female().save(female_path)

    print(f'Generated: {male_path}')
    print(f'Generated: {female_path}')
