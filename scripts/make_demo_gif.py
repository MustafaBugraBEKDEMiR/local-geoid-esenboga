"""Record figures/demo.gif from docs/index.html with a headless browser.

Needs Playwright with Chromium and ffmpeg. The page loads three.js from a CDN;
pass --three-dir to serve it from a local `npm i three@0.169.0` instead.

Usage:  python scripts/make_demo_gif.py [--three-dir node_modules/three]
"""
import argparse
import asyncio
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
W, H = 1200, 720


async def record(three_dir: Path | None, out_dir: Path):
    async with async_playwright() as p:
        b = await p.chromium.launch(args=["--use-gl=angle", "--use-angle=swiftshader",
                                          "--enable-unsafe-swiftshader"])
        pg = await b.new_page(viewport={"width": W, "height": H})

        async def route(r):
            u = r.request.url
            if three_dir and "cdn.jsdelivr.net/npm/three@0.169.0/" in u:
                await r.fulfill(path=str(three_dir / u.split("three@0.169.0/")[1]),
                                content_type="application/javascript")
            else:
                await r.continue_()

        await pg.route("**/*", route)
        await pg.goto((ROOT / "docs/index.html").as_uri())
        await pg.wait_for_function("window.viewer !== undefined")
        await pg.wait_for_timeout(1500)
        n = 0

        async def cam(az_deg, el_deg, dist, ty=0):
            await pg.evaluate("""([az, el, d, ty]) => {
                const {camera, controls} = window.viewer;
                const a = az*Math.PI/180, e = el*Math.PI/180;
                controls.target.set(0, ty, 0);
                camera.position.set(d*Math.cos(e)*Math.sin(a), ty + d*Math.sin(e), d*Math.cos(e)*Math.cos(a));
                controls.update(); }""", [az_deg, el_deg, dist, ty])

        async def shot(k=1):
            """Render once; repeat the frame k times (holds cost one screenshot)."""
            nonlocal n
            await pg.wait_for_timeout(60)
            first = out_dir / f"f{n:04d}.png"
            await pg.screenshot(path=str(first))
            n += 1
            for _ in range(k - 1):
                shutil.copyfile(first, out_dir / f"f{n:04d}.png")
                n += 1

        ease = lambda t: 0.5 - 0.5 * math.cos(math.pi * t)
        # 1) orbit + dolly in
        for i in range(48):
            t = ease(i / 47)
            await cam(20 + 70 * t, 38 - 8 * t, 3000 - 900 * t)
            await shot()
        # 2) geoid surfaces on
        await pg.click("#L_geoid")
        for i in range(36):
            t = ease(i / 35)
            await cam(90 + 40 * t, 30 - 18 * t, 2100 + 300 * t, 80 * t)
            await shot()
        await shot(6)
        await pg.click("#L_geoid")
        # 3) click a spot on the terrain
        for i in range(20):
            t = ease(i / 19)
            await cam(130 - 110 * t, 12 + 30 * t, 2400 - 400 * t)
            await shot()
        await pg.mouse.click(W * 0.56, H * 0.62)
        await shot(16)
        # 4) switch the control-point layout
        await pg.click("#layout button[data-v=d_optimal]")
        await shot(12)
        await pg.click("#infox")
        # 5) SDSS scenario: rule A, then rule B
        await pg.click("#tcol button[data-v=A]")
        for i in range(18):
            t = ease(i / 17)
            await cam(20 - 20 * t, 42 + 16 * t, 2000 + 1150 * t)
            await shot()
        await shot(12)
        await pg.click("#tcol button[data-v=B]")
        await shot(18)
        await b.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--three-dir", type=Path)
    ap.add_argument("--out", type=Path, default=ROOT / "figures/demo.gif")
    a = ap.parse_args()
    tmp = Path(tempfile.mkdtemp())
    asyncio.run(record(a.three_dir, tmp))
    vf = "fps=12,scale=900:-1:flags=lanczos"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "12", "-i", str(tmp / "f%04d.png"),
                    "-vf", f"{vf},palettegen=max_colors=128:stats_mode=diff", str(tmp / "pal.png")], check=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", "12", "-i", str(tmp / "f%04d.png"),
                    "-i", str(tmp / "pal.png"), "-lavfi",
                    f"{vf}[x];[x][1:v]paletteuse=dither=bayer:bayer_scale=4:diff_mode=rectangle",
                    str(a.out)], check=True)
    shutil.rmtree(tmp)
    print(a.out, round(a.out.stat().st_size / 1e6, 2), "MB")


if __name__ == "__main__":
    main()
