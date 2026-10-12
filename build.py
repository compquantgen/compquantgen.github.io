"""Build the lab website into _site/.

    pip install -r requirements.txt
    python build.py

Then open _site/index.html in a browser.
"""

import datetime as dt
import hashlib
import html
import math
import random
import re
import shutil
import sys
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"


def load(name):
    return yaml.safe_load((ROOT / "content" / f"{name}.yml").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Publications
# --------------------------------------------------------------------------

def norm_name(s):
    s = s.lower().replace(".", " ").replace("‐", "-")
    return re.sub(r"\s+", " ", s).strip()


def clean_title(s):
    """Keep only <i>, <sub>, <sup> from Crossref's markup."""
    s = html.escape(re.sub(r"\s+", " ", s or "").strip(), quote=False)
    for tag in ("i", "sub", "sup"):
        s = re.sub(rf"&lt;(/?){tag}&gt;", rf"<\1{tag}>", s)
    s = re.sub(r"&lt;/?(scp|b|em|strong|mml:[a-z]+)[^&]*&gt;", "", s)
    return s


class Members:
    def __init__(self, people):
        pi = people["pi"]
        self.pi_family = norm_name(pi["name"]).split()[-1]
        self.pi_initial = norm_name(pi["name"])[0]
        names = set()
        for p in [pi] + people.get("current", []) + people.get("alumni", []):
            names.add(norm_name(p["name"]))
            for a in p.get("aliases", []):
                names.add(norm_name(a))
        self.names = names

    def is_pi(self, name):
        parts = norm_name(name).split()
        return (
            len(parts) >= 2
            and parts[-1] == self.pi_family
            and parts[0][0] == self.pi_initial
        )

    def is_member(self, name):
        return self.is_pi(name) or norm_name(name) in self.names


def format_authors(authors, members):
    """Comma-separated author string -> HTML with lab members in bold."""
    out = []
    for a in [x.strip() for x in authors.split(",") if x.strip()]:
        esc = html.escape(a)
        out.append(f"<strong>{esc}</strong>" if a != "…" and members.is_member(a) else esc)
    return Markup(", ".join(out))


def load_papers(cfg, members):
    papers = []
    for p in cfg["papers"]:
        doi = str(p["doi"]).lower()
        papers.append(
            {
                "doi": doi,
                "url": f"https://doi.org/{doi}",
                "kind": "preprint" if p.get("preprint") else "article",
                "title": clean_title(p["title"]),
                "journal": p.get("venue", ""),
                "year": p.get("year", ""),
                "authors": format_authors(p.get("authors", ""), members),
            }
        )
    return papers


# --------------------------------------------------------------------------
# Illustrations (inline SVG, colored by CSS variables so dark mode works)
# --------------------------------------------------------------------------


def svg_matrix(n=24, seed=4, size=240, label="Genomic relationship matrix"):
    """A dense relationship matrix: a strong diagonal, weak relatedness between
    almost every pair, and a few scattered close relatives. No family blocks."""
    rng = random.Random(seed)
    v = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(i + 1, n):
            v[i][j] = v[j][i] = max(0.0, rng.gauss(0.08, 0.04))   # background
    for _ in range(int(n * 0.55)):                                  # close relatives
        i, j = rng.sample(range(n), 2)
        r = rng.choice([0.25, 0.25, 0.25, 0.5])
        v[i][j] = v[j][i] = r + rng.gauss(0, 0.03)
    cell = size / n
    rects = []
    for i in range(n):
        for j in range(n):
            op = 1.0 if i == j else min(0.66, 0.14 + 1.2 * v[i][j])
            rects.append(
                f'<rect x="{j*cell:.1f}" y="{i*cell:.1f}" width="{cell-1.2:.1f}" '
                f'height="{cell-1.2:.1f}" rx="1.5" fill="var(--motif)" fill-opacity="{op:.2f}"/>'
            )
    return Markup(
        f'<svg viewBox="0 0 {size} {size}" role="img" aria-label="{label}">'
        + "".join(rects)
        + "</svg>"
    )


def svg_locus(seed=3, w=320, h=200):
    """Association signal at one locus, with the credible set highlighted."""
    rng = random.Random(seed)
    pts = []
    for k in range(140):
        x = rng.uniform(10, w - 10)
        d = (x - w * 0.56) / (w * 0.09)
        peak = 9.5 * math.exp(-d * d) * (0.55 + 0.45 * rng.random())
        y = max(0.2, peak + rng.expovariate(1.6))
        pts.append((x, y))
    pts.sort(key=lambda p: -p[1])
    cs = set(pts[:4])
    ymax = max(p[1] for p in pts) * 1.08
    sy = lambda y: h - 18 - (y / ymax) * (h - 34)
    dots = []
    for p in pts:
        if p in cs:
            continue
        dots.append(f'<circle cx="{p[0]:.1f}" cy="{sy(p[1]):.1f}" r="2.6" fill="var(--motif)" fill-opacity="0.42"/>')
    for p in cs:
        dots.append(f'<circle cx="{p[0]:.1f}" cy="{sy(p[1]):.1f}" r="4.2" fill="var(--accent-2)"/>')
    xs = [p[0] for p in cs]
    x0, x1 = min(xs) - 8, max(xs) + 8
    bracket = (
        f'<path d="M{x0:.1f} {h-8} L{x0:.1f} {h-4} L{x1:.1f} {h-4} L{x1:.1f} {h-8}" '
        f'fill="none" stroke="var(--accent-2)" stroke-width="1.5"/>'
    )
    axis = f'<line x1="6" y1="{h-14}" x2="{w-6}" y2="{h-14}" stroke="var(--line)" stroke-width="1"/>'
    return Markup(
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Fine-mapping a locus">'
        + axis + "".join(dots) + bracket + "</svg>"
    )


def svg_bounds(w=320, h=200):
    """Sigmoid curves approaching a common ceiling."""
    paths = []
    for k, (c, s, op) in enumerate([(0.30, 0.07, 0.35), (0.45, 0.08, 0.55), (0.60, 0.09, 0.8), (0.75, 0.10, 1.0)]):
        pts = []
        for i in range(81):
            x = i / 80
            y = 1 / (1 + math.exp(-(x - c) / s))
            pts.append(f"{10 + x*(w-20):.1f},{h-16 - y*(h-44):.1f}")
        col = "var(--accent-2)" if k == 3 else "var(--motif)"
        paths.append(
            f'<polyline points="{" ".join(pts)}" fill="none" stroke="{col}" '
            f'stroke-opacity="{op}" stroke-width="2.2" stroke-linecap="round"/>'
        )
    ceil_y = h - 16 - (h - 44)
    ceiling = (
        f'<line x1="10" y1="{ceil_y}" x2="{w-10}" y2="{ceil_y}" stroke="var(--ink-soft)" '
        f'stroke-dasharray="4 5" stroke-width="1.2"/>'
    )
    axis = f'<line x1="10" y1="{h-16}" x2="{w-10}" y2="{h-16}" stroke="var(--line)"/>'
    return Markup(
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Curves bounded by a common limit">'
        + axis + ceiling + "".join(paths) + "</svg>"
    )


def svg_sequence(seed=11, w=320, h=200):
    """A token sequence feeding a forecast trajectory."""
    rng = random.Random(seed)
    toks = []
    n, tw = 12, (w - 20) / 12
    for i in range(n):
        op = 0.25 + 0.6 * rng.random()
        toks.append(
            f'<rect x="{10 + i*tw:.1f}" y="{h-40}" width="{tw-4:.1f}" height="22" rx="4" '
            f'fill="var(--motif)" fill-opacity="{op:.2f}"/>'
        )
    pts, y = [], 0.5
    for i in range(n):
        y = min(0.95, max(0.1, y + rng.uniform(-0.18, 0.2)))
        pts.append((10 + i * tw + (tw - 4) / 2, 18 + (1 - y) * (h - 84)))
    hist = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in pts[:8])
    fut = " ".join(f"{x:.1f},{yy:.1f}" for x, yy in pts[7:])
    nodes = "".join(
        f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="3.4" fill="{"var(--accent-2)" if i >= 8 else "var(--motif)"}"/>'
        for i, (x, yy) in enumerate(pts)
    )
    links = "".join(
        f'<line x1="{x:.1f}" y1="{yy+5:.1f}" x2="{x:.1f}" y2="{h-42}" stroke="var(--line)" stroke-dasharray="2 3"/>'
        for x, yy in pts
    )
    return Markup(
        f'<svg viewBox="0 0 {w} {h}" role="img" aria-label="Sequence model forecasting a trajectory">'
        + links + "".join(toks)
        + f'<polyline points="{hist}" fill="none" stroke="var(--motif)" stroke-width="2.2"/>'
        + f'<polyline points="{fut}" fill="none" stroke="var(--accent-2)" stroke-width="2.2" stroke-dasharray="5 4"/>'
        + nodes + "</svg>"
    )


MOTIFS = {"matrix": lambda: svg_matrix(n=14, seed=9, size=200), "locus": svg_locus, "bounds": svg_bounds, "sequence": svg_sequence}


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------


def main():
    site = load("site")
    research = load("research")
    software = load("software")
    people = load("people")
    pubcfg = load("publications")
    members = Members(people)
    pubs = load_papers(pubcfg, members)
    by_doi = {p["doi"]: p for p in pubs}

    for t in research["themes"]:
        t["svg"] = MOTIFS[t["motif"]]()
        t["paper_items"] = [by_doi[d.lower()] for d in t.get("papers", []) if d.lower() in by_doi]
        t["tools"] = [s for s in software["tools"] if s["id"] in t.get("software", [])]
    for s in software["tools"]:
        dois = s.get("papers") or ([s["paper"]] if s.get("paper") else [])
        s["paper_items"] = [by_doi[str(d).lower()] for d in dois if str(d).lower() in by_doi]


    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    ctx = dict(
        site=site,
        research=research,
        software=software,
        people=people,
        pubs=pubs,
        hero_svg=svg_matrix(n=26, seed=4, size=330, label="Genomic relationship matrix"),
        built=dt.date.today().strftime("%B %-d, %Y") if sys.platform != "win32" else dt.date.today().strftime("%B %#d, %Y"),
        year=dt.date.today().year,
        # Changes whenever style.css changes, so browsers fetch the new file.
        css_v=hashlib.md5((ROOT / "assets" / "style.css").read_bytes()).hexdigest()[:8],
    )

    OUT.mkdir(exist_ok=True)
    shutil.copytree(ROOT / "assets", OUT / "assets", dirs_exist_ok=True)
    pages = {
        "index.html": "home",
        "research.html": "research",
        "software.html": "software",
        "publications.html": "publications",
        "people.html": "people",
        "404.html": "404",
    }
    for fname, page in pages.items():
        html_out = env.get_template(fname).render(page=page, **ctx)
        (OUT / fname).write_text(html_out, encoding="utf-8")
    (OUT / ".nojekyll").write_text("")
    print(f"Built {len(pages)} pages, {len(pubs)} publications -> {OUT}")


if __name__ == "__main__":
    main()
