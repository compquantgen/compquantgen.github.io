# compquantgen.github.io

Website of the Computational Quantitative Genetics Lab, NC State University.
Live at <https://compquantgen.github.io>.

## Editing

All content lives in plain-text files under `content/`:

| File | What it controls |
|---|---|
| `content/site.yml` | Lab name, tagline, About text, Join us text, contact and links |
| `content/research.yml` | Research themes, their text, and the papers shown under each |
| `content/software.yml` | Software tools and code accompanying papers |
| `content/publications.yml` | Selected publications (a short, curated list) |
| `content/people.yml` | PI, current team, former members, collaborators |

Lab members listed in `people.yml` are shown in bold in author lists automatically.
Papers on the Research page are referenced by DOI and must also appear in `publications.yml`.

Push to `main` and the site rebuilds and publishes itself in about a minute
(see the Actions tab).

## Previewing locally

Requires Python 3.9+.

```
pip install -r requirements.txt
python build.py
```

Then open `_site/index.html` in a browser.

## Layout

```
build.py            builds the site into _site/
content/            text and data (edit these)
templates/          page layouts (Jinja2)
assets/             stylesheet and icon
.github/workflows/  build-and-publish workflow
```
