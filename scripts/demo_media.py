"""Draw the demo case's pictures and video into fixtures/demo/ (hunt/demo.py builds the case from them).

Everything is drawn here, so nothing has a licence to track: fixtures/demo/LICENSE.md dedicates the
output to the public domain (CC0). Each picture says "DEMO · generated illustration" in a corner, so it
can't be mistaken for a real photograph. Run: uv run python scripts/demo_media.py
"""

from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "fixtures" / "demo"
INK, SKIN, BOX, VAN, SKY, GROUND = "#2b2d42", "#e0b089", "#c08a4a", "#e9ecef", "#bde0fe", "#9c8f80"


def font(size: int):
    return ImageFont.load_default(size=size)


def canvas(w: int, h: int, sky=SKY, ground=GROUND, horizon=0.7) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    im = Image.new("RGB", (w, h), sky)
    d = ImageDraw.Draw(im)
    d.rectangle([0, int(h * horizon), w, h], fill=ground)
    return im, d


def stamp(im: Image.Image) -> Image.Image:
    d = ImageDraw.Draw(im)
    d.rectangle([0, im.height - 22, 236, im.height], fill="#000000")
    d.text((6, im.height - 19), "DEMO · generated illustration", fill="#ffffff", font=font(13))
    return im


def person(d, x: int, feet: int, arms_up: float = 0.0, scale: float = 1.0):
    """A stick figure standing at x with feet at y=feet; arms_up 0 (down) to 1 (overhead)."""
    s = scale
    hip, shoulder, head = feet - 60 * s, feet - 110 * s, feet - 128 * s
    d.ellipse([x - 14 * s, head - 14 * s, x + 14 * s, head + 14 * s], fill=SKIN, outline=INK, width=3)
    d.line([x, shoulder - 4 * s, x, hip], fill=INK, width=int(6 * s))
    d.line([x, hip, x - 18 * s, feet], fill=INK, width=int(6 * s))
    d.line([x, hip, x + 18 * s, feet], fill=INK, width=int(6 * s))
    hand_y = shoulder + (1 - arms_up) * 45 * s - arms_up * 40 * s
    for side in (-1, 1):
        d.line([x, shoulder, x + side * 26 * s, hand_y], fill=INK, width=int(5 * s))
    return hand_y


def van(d, x: int, y: int):
    d.rectangle([x, y, x + 210, y + 110], fill=VAN, outline=INK, width=3)
    d.rectangle([x + 210, y + 40, x + 270, y + 110], fill=VAN, outline=INK, width=3)
    d.rectangle([x + 222, y + 50, x + 258, y + 75], fill=SKY, outline=INK, width=2)
    d.text((x + 18, y + 40), "VELL MOVING", fill=INK, font=font(22))
    for wx in (x + 40, x + 210):
        d.ellipse([wx - 18, y + 92, wx + 18, y + 128], fill=INK)


def moving_day():
    im, d = canvas(640, 480)
    van(d, 300, 250)
    hand = person(d, 200, 400, arms_up=0.45, scale=1.2)
    d.rectangle([170, hand - 8, 232, hand + 42], fill=BOX, outline=INK, width=3)
    return stamp(im)


def gym():
    im, d = canvas(640, 480, sky="#dee2e6", ground="#6c757d", horizon=0.82)
    hand = person(d, 320, 395, arms_up=1.0, scale=1.25)
    d.line([220, hand, 420, hand], fill=INK, width=8)
    for px in (225, 415):
        d.rectangle([px - 10, hand - 34, px + 10, hand + 34], fill="#343a40")
    return stamp(im)


def coffee():
    im, d = canvas(640, 480, sky="#f8f9fa", ground="#a47148", horizon=0.62)
    d.rounded_rectangle([270, 200, 370, 310], radius=12, fill="#ffffff", outline=INK, width=4)
    d.arc([350, 225, 400, 280], start=-90, end=90, fill=INK, width=6)
    for sx in (295, 320, 345):
        d.arc([sx - 8, 150, sx + 8, 195], start=200, end=340, fill="#adb5bd", width=3)
    return stamp(im)


def hike():
    im, d = canvas(640, 480, sky="#fde2c4", ground="#6a994e", horizon=0.75)
    d.polygon([(40, 360), (230, 120), (420, 360)], fill="#7f8c8d", outline=INK)
    d.polygon([(260, 360), (450, 160), (620, 360)], fill="#95a5a6", outline=INK)
    d.ellipse([500, 50, 560, 110], fill="#ffb703")
    person(d, 160, 420, arms_up=0.9, scale=0.9)
    return stamp(im)


def avatar():
    im = Image.new("RGB", (256, 256), "#2a9d8f")
    d = ImageDraw.Draw(im)
    d.ellipse([28, 28, 228, 228], fill="#264653")
    d.text((128, 128), "DV", fill="#e9c46a", font=font(96), anchor="mm")
    d.text((128, 222), "DEMO", fill="#ffffff", font=font(18), anchor="mm")
    return im


def profile(site: str, handle: str, bio: str):
    im = Image.new("RGB", (640, 400), "#ffffff")
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, 640, 56], fill="#343a40")
    d.text((16, 16), f"{site} · DEMO · fictional profile", fill="#ffffff", font=font(20))
    im.paste(avatar().resize((120, 120)), (24, 80))
    d.text((168, 92), "Dorian Vell", fill=INK, font=font(30))
    d.text((168, 134), handle, fill="#6c757d", font=font(20))
    d.text((168, 172), bio, fill=INK, font=font(17))
    for i in range(3):
        d.rectangle([24 + i * 204, 230, 212 + i * 204, 380], fill="#e9ecef", outline="#ced4da")
    return stamp(im)


def video(path: Path, frame_path: Path, seconds: int = 8, fps: int = 10):
    """A figure lifting a box from the ground into the van, from about 3 s to 8 s."""
    writer = imageio_ffmpeg.write_frames(str(path), (320, 240), fps=fps, codec="libx264", pix_fmt_out="yuv420p",
                                         quality=6, macro_block_size=8)
    writer.send(None)
    n = seconds * fps
    for i in range(n):
        im, d = canvas(640, 480)
        van(d, 330, 250)
        lift = min(max((i - 2.5 * fps) / (4 * fps), 0.0), 1.0)  # 0 on the ground, 1 into the van
        hand = person(d, 230 + 70 * lift, 400, arms_up=0.2 + 0.6 * lift, scale=1.2)
        d.rectangle([200 + 70 * lift, hand - 8, 262 + 70 * lift, hand + 42], fill=BOX, outline=INK, width=3)
        stamp(im)
        small = im.resize((320, 240))
        if i == n // 2 + 10:  # the stretch's middle: the frame a video flag keeps
            small.save(frame_path, quality=85)
        writer.send(small.tobytes())
    writer.close()


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for name, make in (("moving-day.jpg", moving_day), ("gym.jpg", gym), ("coffee.jpg", coffee), ("hike.jpg", hike)):
        make().save(OUT / name, quality=82)
    avatar().save(OUT / "avatar.png")
    for site, handle, bio in (("Bluesky", "@dorianvell.bsky.social", "Mover. Lifting heavy things since 2009."),
                              ("Instagram", "@dorianvell", "Vell Moving & Hauling"),
                              ("TikTok", "@dorianvell", "moving day vlogs")):
        profile(site, handle, bio).save(OUT / f"profile-{site.lower()}.png")
    video(OUT / "van-loading.mp4", OUT / "van-loading-frame.jpg")
    print("\n".join(f"{p.name}: {p.stat().st_size // 1024} KB" for p in sorted(OUT.iterdir())))
