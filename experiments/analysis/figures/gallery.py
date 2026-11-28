#!/usr/bin/env python3
"""Build figures/paper/GALLERY.pdf: every paper figure at true size in an acmart sigconf page, with its caption.

OFFLINE, CPU only. Reads figures/paper/F*.pgf and F*.caption.txt, writes the gallery .tex to figures/paper/preview/
and copies the compiled PDF to figures/paper/GALLERY.pdf. Single-column figures (3.33 in) sit in figure, double
(7.0 in) in figure*. Needs pdflatex and bibtex on PATH (export PATH=$HOME/texlive/2026/bin/aarch64-linux:$PATH).
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paperstyle as P  # noqa: E402

PREAMBLE = r"""\documentclass[sigconf]{acmart}
\usepackage{pgf}
\usepackage[T1]{fontenc}
\usepackage{libertine}
\settopmatter{printacmref=false}
\pagestyle{plain}
\begin{document}
\title{Paper figure gallery (placeholder data)}
\author{fm-switching}
\maketitle
\noindent Each figure is shown at its true size. Status tags: OLD DATA, DEV DATA, or NO DATA YET where a figure
has no committed data. Captions start with the status placeholder.
"""


def pgf_width(path: Path) -> float:
    m = re.search(r"pgfqpoint\{([\d.]+)in\}\{([\d.]+)in\}", path.read_text(errors="ignore"))
    if not m:
        raise RuntimeError(f"no picture size in {path}")
    return float(m.group(1))


def caption_tex(path: Path) -> str:
    text = path.read_text().strip()
    return text.replace("\n", " ")


def main():
    stems = sorted(p.stem for p in P.OUTDIR.glob("F*.pgf"))
    parts = [PREAMBLE]
    for stem in stems:
        pgf = P.OUTDIR / f"{stem}.pgf"
        cap = P.OUTDIR / f"{stem}.caption.txt"
        width = pgf_width(pgf)
        env = "figure*" if width > 5 else "figure"
        parts.append(
            "\\begin{%s}[t]\n\\centering\n{\\fontfamily{LinuxBiolinumT}\\selectfont\n\\input{../%s.pgf}}\n"
            "\\caption{%s}\n\\label{fig:%s}\n\\end{%s}\n" % (env, stem, caption_tex(cap), stem, env))
    parts.append("\\bibliographystyle{ACM-Reference-Format}\n\\bibliography{refs_stub}\n\\end{document}\n")
    P.PREVIEW.mkdir(parents=True, exist_ok=True)
    (P.PREVIEW / "refs_stub.bib").write_text(P.STUB_BIB)
    tex = P.PREVIEW / "GALLERY.tex"
    tex.write_text("".join(parts))
    for cmd in (["pdflatex", "-interaction=nonstopmode", "GALLERY.tex"], ["bibtex", "GALLERY"],
                ["pdflatex", "-interaction=nonstopmode", "GALLERY.tex"],
                ["pdflatex", "-interaction=nonstopmode", "GALLERY.tex"]):
        subprocess.run(cmd, cwd=P.PREVIEW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
    pdf = P.PREVIEW / "GALLERY.pdf"
    if not pdf.exists():
        raise SystemExit(f"gallery did not compile: see {P.PREVIEW / 'GALLERY.log'}")
    (P.OUTDIR / "GALLERY.pdf").write_bytes(pdf.read_bytes())
    print(f"figures: {len(stems)}  ->  {P.OUTDIR / 'GALLERY.pdf'}")


if __name__ == "__main__":
    main()
