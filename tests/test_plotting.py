import matplotlib.pyplot as plt
from PIL import Image

from aeo_research.plotting import OG_FIGSIZE, decile_plot, save_figure, theme
from aeo_research.synthetic import synthesize


def test_save_figure_writes_svg_and_png(tmp_path):
    theme()
    fig, ax = plt.subplots(figsize=(9, 5.4))
    ax.plot([1, 2, 3], [1, 4, 9])
    paths = save_figure(fig, tmp_path, "demo")
    assert paths["svg"].exists() and paths["svg"].stat().st_size > 0
    assert paths["png"].exists() and paths["png"].stat().st_size > 0
    # Watermark + caption are baked into the SVG output.
    svg = paths["svg"].read_text()
    assert "research.spyglasses.io" in svg
    assert "image" in svg  # embedded watermark raster


def test_og_figure_is_exactly_1200x630(tmp_path):
    theme()
    fig, ax = plt.subplots()
    ax.plot([1, 2], [1, 2])
    paths = save_figure(fig, tmp_path, "og", og=True)
    with Image.open(paths["png"]) as im:
        assert im.size == (1200, 630)
    assert fig.get_size_inches().tolist() == list(OG_FIGSIZE)


def test_decile_plot_runs(tmp_path):
    theme()
    df = synthesize(n=1500, n_other_platforms=0, seed=3)
    df["moment"] = df["timestamp_seconds"].notna().astype(int)
    df["log_subs"] = df["audience_size"].apply(lambda v: v + 1).apply("log10")
    fig = decile_plot(
        df,
        "log_subs",
        "moment",
        xlabel="Channel size decile",
        ylabel="Share moment-cited",
        title="Moment-citation rate by channel size",
    )
    paths = save_figure(fig, tmp_path, "decile")
    assert paths["png"].exists()
