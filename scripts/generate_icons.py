"""Generate gender silhouette PNG icons for the seat map.
Draws at 2× (128×128) then downsamples to 64×64 for clean antialiasing.
"""
import os
from PIL import Image, ImageDraw

RENDER = 128   # draw at 2×
OUT    = 64    # output size
W = RENDER

OUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'app', 'static', 'icons')
os.makedirs(OUT_DIR, exist_ok=True)


def canvas():
    return Image.new('RGBA', (W, W), (0, 0, 0, 0))


def save(img, name):
    img = img.resize((OUT, OUT), Image.LANCZOS)
    path = os.path.join(OUT_DIR, name)
    img.save(path)
    print(f'Generated: {path}')


# ── Male silhouette ─────────────────────────────────────────────
def draw_male():
    img = canvas()
    d = ImageDraw.Draw(img)
    cx = W // 2     # 64

    # Head (larger, dominant)
    hr = 19
    hcy = 22
    d.ellipse([cx - hr, hcy - hr, cx + hr, hcy + hr], fill='white')

    # Torso: trapezoidal — wide at shoulders, slightly narrower at waist
    t_top   = hcy + hr + 2        # 43
    t_bot   = t_top + 38          # 81
    t_top_w = 54                  # shoulder width
    t_bot_w = 42                  # waist width
    torso = [
        (cx - t_top_w // 2, t_top),
        (cx + t_top_w // 2, t_top),
        (cx + t_bot_w // 2, t_bot),
        (cx - t_bot_w // 2, t_bot),
    ]
    d.polygon(torso, fill='white')

    # Legs: two solid blocks, narrow gap between them
    leg_top = t_bot
    leg_bot = W - 8               # 120
    leg_w   = 18
    gap     = 10
    lx = cx - gap // 2 - leg_w   # left leg start x
    rx = cx + gap // 2            # right leg start x
    d.rectangle([lx, leg_top, lx + leg_w, leg_bot], fill='white')
    d.rectangle([rx, leg_top, rx + leg_w, leg_bot], fill='white')

    return img


# ── Female silhouette ────────────────────────────────────────────
def draw_female():
    img = canvas()
    d = ImageDraw.Draw(img)
    cx = W // 2     # 64

    # Head
    hr = 18
    hcy = 21
    d.ellipse([cx - hr, hcy - hr, cx + hr, hcy + hr], fill='white')

    # Neck + upper body: narrow rectangle
    body_top = hcy + hr + 2        # 41
    body_bot = body_top + 18       # 59
    body_w   = 26
    bx = cx - body_w // 2
    d.rectangle([bx, body_top, bx + body_w, body_bot], fill='white')

    # Skirt: wide trapezoid — distinctive feminine shape
    sk_top   = body_bot
    sk_bot   = W - 22              # 106
    sk_top_w = 40
    sk_bot_w = 82
    skirt = [
        (cx - sk_top_w // 2, sk_top),
        (cx + sk_top_w // 2, sk_top),
        (cx + sk_bot_w // 2, sk_bot),
        (cx - sk_bot_w // 2, sk_bot),
    ]
    d.polygon(skirt, fill='white')

    # Legs below skirt (short, peeking out)
    leg_top = sk_bot
    leg_bot = W - 6                # 122
    leg_w   = 16
    gap     = 12
    lx = cx - gap // 2 - leg_w
    rx = cx + gap // 2
    d.rectangle([lx, leg_top, lx + leg_w, leg_bot], fill='white')
    d.rectangle([rx, leg_top, rx + leg_w, leg_bot], fill='white')

    return img


if __name__ == '__main__':
    save(draw_male(),   'male.png')
    save(draw_female(), 'female.png')
