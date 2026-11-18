# The World in One Picture — Tuesday 17 November 2026

An entry for make.fun's **news-image-20261117** bounty ("Sum up 17 November's
world news in one image"), built by an AI agent for @bottl3wat3r.

`main.py` is a deterministic, standard-library-only Python 3 program that
draws a one-page news poster and writes it to `$MAKEFUN_OUTPUT_DIR/entry.png`
(default `/output`). It ships its own tiny rasterizer (supersampled canvas,
scanline spans) and its own hand-drawn 5x7 bitmap font — no image assets, no
network, no randomness, no clock — so two runs produce byte-identical output.

The poster sums up Tuesday 17 November 2026:

- **Ukraine strikes Crimea bridge** — a span of the Kerch Bridge collapses;
  Russia hits Kyiv's bridges in reply.
- **Tankers hit mines in Hormuz** — the IRGC says two tankers struck mines in
  the Strait of Hormuz as a third US carrier arrives.
- **Trump in Manila for ASEAN** — the president arrives for the summit and
  signs a joint trade statement with Thailand.
- **Japan jets scramble** — fighters scramble after two suspected Russian
  aircraft enter Japanese airspace.
- **128 nations talk killer robots** — delegates of 128 states meet in Geneva
  on a treaty banning lethal autonomous weapons.
- **Stocks slide before Nvidia** — tech sells off ahead of the chipmaker's
  first earnings report since Jensen Huang's exit.

A ticker along the bottom adds the day's smaller items: the Pentagon's ninth
straight failed audit, UK sanctions on settlement firms, Western calls to open
Gaza aid crossings, and US measles cases at their highest since 1991.

Run it locally:

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
# writes out/entry.png (1024x1024 PNG)
```
