# CLAUDE.md

CERES-2 Y3 (遥三), the second CERES-2 flight, from Jiuquan 95A: ascent model fitted to the NOTAM zones, twilight-jelly forecast and a 3D page. Repo: github.com/exoplanet5/CERES-2. GitHub Pages serves `main` → `/docs`, so a push to `main` deploys https://exoplanet5.github.io/CERES-2/. README.md has the results, assumptions and sources.

Everything runs with `~/.venvs/astro313/bin/python`. Serve the page with `python3 tools/serve.py` (port 8770).

## Pipeline (order matters)

1. `validate_precedents.py`: CERES-1 and ZK-1A on the same model. Run it before trusting a model change.
2. `build_traj.py [--t0 ISO] [--payload 1300] [--alt 500] [--sens]`: calibrates and flies. `--sens` takes several minutes.
3. `jelly_ceres2.py [--t0 ISO]`: reads the CSV. Writes the JSON, KML and the map PNG.
4. `web_export.py`: writes `docs/data/ceres2-y3.json` and `profiles.json`.

`ceres2.py` is the core module. Generic frames, gravity, atmosphere, coast/fall, elements and `fit_tle` are imported from `../launch_traj_NROL-97/nrol97.py`, and jelly physics from `~/launch/launch_jelly/jelly_forecast.py`. Do not copy them.

## Key facts

- **The flight is named CERES-2 Y3** (user, 2026-11-07), in file names, page and map.
- **T0 23:38:00 UTC is the user's assumption.**
- **S1 flies the steep branch.** S1 impact range has a maximum against the kick. `fit_s1` takes the steep side; the flat side leaves S2 inside the atmosphere.
- **Zero incidence stops at S2 ignition.** Flown through S2 it ends about 78° at 220 km and S3 cannot fit. S2 is guided in pitch and yaw, with a 10 s blend from the flight path.
- **User's settings (2026-11-06): 1.3 t to 500 km SSO, S4 direct climb with no transfer coast or second burn, S3 burning longer.** Do not bring back the two-burn plan. The 120 s S3 burn is my choice of "longer", from Vega's Zefiro 9.
- **S3 aims at 5450 km in the E4059 tail, not the zone's mid-range.** A direct climb needs a lofted S3, and from the 5091 km mid-range 1.3 t cannot close. 5450 km is the farthest nominal that keeps CERES-1's ±150 km zone half-length inside the far edge.
- **`alt_cmd` 503.7 km gives a 500 km orbit mean**, because of J2 and the cutoff latitude.
- **The budget closes narrowly.** S4 load 1200 kg, 1185 used, f = 0.40 solved and not published. A 1000 kg load, an S3 aim of 5300 km or less, S1 impact 145 km and S4 at 7 kN do not close. At 3.5 kN the solver finds no orbit: S3 is sub-orbital and S4 runs out of time.
- **Stage falls in `validate_precedents.py` are fit targets**, so reaching a zone validates nothing. The test is mass and Δv closure. The CERES-1 S4 thrust of 1.6 kN was picked from the Y19 510 s report, so its burn time is not an independent check either.
- **Sunlight has two definitions.** The page and the headline pickup use geometric WGS84 occultation. The 34′ value follows launch_jelly. Clear sunlight means the ray passes at least 20 km above the surface.
- **Solid and S4 zones stay separate.** The S4 plume is far fainter. Do not merge them into one jelly zone.

## Page

`docs/` is a copy of `~/launch/CZ-6A/docs`, with the same mission contract (`~/launch/CZ-6A/PROFILE_FORMAT.md`). Unlike CZ-6A, this page has a jelly panel and dynamic 10° zones, because this mission's point is the jelly. The added `meta` fields are `met_default`, `s4_cutoff_met`, `solid_end_met`, `stack` and `jelly`, and there is an optional top-level `moon` table.

- **Zones (`js/jelly-zone.js`):** the grid holds only the elevation fields. The night clip is per pixel in the shader, from the same `sunDir` uniform as the Sun 0° line, so never put it back on the grid: that caused the stair-steps and the mismatch at the terminator. Area figures use the pickup epoch.
- **Sky (`js/sky-background.js`):** stars and Sun are a separate rotation-only scene drawn before a depth clear, so `renderer.autoClear` is false. The scene is Earth-fixed, so stars turn at −GMST.
- **Sprites:** canvas textures are sRGB and sprites do not write depth; otherwise colours wash out and sprite quads punch holes in later transparent layers.
- **Base maps and tiles:** the page opens on the 4K WebP pair, and `sharpenBase` swaps in the 8K maps only when the view needs them, so never block startup on 8K. The 8K base covers up to 8192 px wide, so only tile levels 2–3 exist. `chooseLevel` takes the current base width. Tiles carry day imagery only, so `candidates` skips any tile wholly past the day edge; keep `DAY_EDGE` in step with the fade in the Earth shader.
- **Headless Chrome is slow:** allow a few seconds per view. Coverage is SwiftShader only unless noted.

The page and the Python agree: pickup to 0.1 s, solid zone area to about 0.3 %. Recheck both after a change. Test in headless Chrome over CDP with `--use-angle=swiftshader --enable-unsafe-swiftshader`, using `window.__ceres2`.

## After the launch

See README.md. Fetch the earliest TLEs with the space-track skill, compare, solve T0 from RAAN, then rerun `jelly_ceres2.py --t0 <actual>`.
