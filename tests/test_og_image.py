from PIL import Image

from aeo_research.og_image import OG_SIZE, cover_crop, make_og_image


def _gradient(w, h):
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (30, 60 + (x * 120 // w), 120 + (y * 100 // h))
    return img


def test_cover_crop_exact_size():
    # Wider-than-target source: cropped to exactly 1200x630, no distortion.
    out = cover_crop(_gradient(1600, 600), OG_SIZE)
    assert out.size == OG_SIZE


def test_make_og_image_dimensions_and_format(tmp_path):
    src = tmp_path / "src.png"
    _gradient(1568, 662).save(src)
    dst = make_og_image(src, tmp_path / "card.webp")
    assert dst.exists()
    with Image.open(dst) as im:
        assert im.size == (1200, 630)
        assert im.format == "WEBP"


def test_logo_is_stamped_lower_right(tmp_path):
    # A flat dark source; after stamping, the lower-right region should carry
    # the bright gold isotype, i.e. be measurably lighter than the top-left.
    src = tmp_path / "src.png"
    Image.new("RGB", (1200, 630), (10, 20, 40)).save(src)
    dst = make_og_image(src, tmp_path / "card.webp")
    im = Image.open(dst).convert("RGB")

    def brightness(box):
        crop = im.crop(box)
        px = list(crop.getdata())
        return sum(sum(p) for p in px) / (len(px) * 3)

    top_left = brightness((0, 0, 120, 120))
    lower_right = brightness((1080, 510, 1200, 630))
    assert lower_right > top_left + 15
