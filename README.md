# Kingdom Kids

A Kingdom Hearts style platformer for a five-year-old, played on a phone in
landscape. Pick a kid, pick a world, run and jump to the Keyhole and seal it
with the Keyblade. A Disney friend follows you and helps; you can't lose (a
fall or running out of hearts just sends you back to the last save point).

- **World 1 -- Pride Lands**, with Simba. Hyenas and Shadow Heartless.
- **World 2 -- Arendelle**, with Olaf. Frozen lakes, crumbling ice bridges,
  snow bounce pads, wolves.

## Play

Open the GitHub Pages site on the phone. On an iPhone, tap **Share > Add to
Home Screen** to get it as a full-screen app; after the first launch it also
works offline.

Controls: the left/right buttons, the Keyblade button to swing, the arrow to
jump. On a computer: arrow keys, Space/X.

## Develop

No build step -- static files plus Phaser 3.90 from a CDN.

```
python tools/serve.py          # http://localhost:8000 and the LAN address for a phone
```

- `levels/*.txt` -- the levels, one character per tile; edit in any text
  editor (the legend is at the top of each file).
- `js/` -- the game. `js/characters.js` has the cast, worlds and tuning.
- `tools/` -- the art pipeline (`process_art.py`, `pixelize.py`,
  `build_gen_art.py`, `make_world_art.py`, `make_icons.py`) and
  `playtest.js`, a bot that plays a level and reports falls and hits. The
  pipeline's source art (`art/raw`, `art/gen`, ...) is not in this repository.
