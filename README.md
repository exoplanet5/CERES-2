# CERES-2 Y3: ascent model and twilight jelly

Pre-launch model of CERES-2 Y3 (遥三), mission 砺锋行, the second CERES-2 flight, from Jiuquan, built from NOTAMs A5672/26, A5673/26, A0582/26 and E4059/26, with T0 assumed at **2026-11-06 23:38:00 UTC** (07:38 Beijing on 7 November). It is not telemetry and not an official ephemeris.

**T0.** Only "about 07:00 Beijing, 7 November, at the earliest" is reported. CERES-2 Y1 lifted off 11 min after its first zone opened and at that zone's midpoint. Here that rule gives 23:39, one minute from the assumed T0.

## Run the 3D page

The page is published at **https://exoplanet5.github.io/CERES-2/**. GitHub Pages serves `main` → `/docs`, so changes deploy when they reach `main`. To run it locally:

```sh
python3 tools/serve.py     # http://127.0.0.1:8770/
```

It needs an HTTP server, not `file://`. Everything is local. The page follows the CZ-6A framework: globe, MET playback, T0 slider, sky charts, borders and adaptive map tiles. Added here:

- A live twilight-jelly panel for the selected T0.
- 10° jelly zones, recomputed when T0 changes. They are shaded per pixel, and the night edge uses the same Sun vector as the Sun 0° line, so the two meet exactly at any zoom. That edge follows playback time; the area figures use the pickup epoch, as the map does.
- A best-viewers table. Click a city for its sky chart.
- Stage-fall tracks.
- A CERES-2 cartoon: one slender core with a hammerhead fairing and no side boosters. The stack shortens at each separation, and burning stages carry a flame.

The globe and sky:

- **Earth:** 8K Blue Marble (September 2004) and 8K Black Marble 2016 from SatObserver-MX, with sharper Blue Marble tiles when zoomed in. Small screens get the lighter 4K pair.
- **Atmosphere:** a limb shell, blue where the air is sunlit and red along the terminator, plus a thin haze on the ground near the limb. It is an illustration, not a scattering calculation.
- **Stars:** 9,827 Hipparcos stars after cislunar-eye's star background, in a separate rotation-only scene turning with GMST.
- **Sun and Moon:** Sun glare at infinity, and a textured Moon at its true DE440s position and size, oriented to face the Earth. A label sits beside each when in view; otherwise a chevron on the screen edge points to it. The Moon is close to new at this T0, so it shows a dim disc with a very thin crescent.
- **Colours:** the orbit is now violet, so it no longer resembles the cyan Sun −12° line. A clicked ground point gets a compact pin.

## Results

The mission flies **1.3 t to 500 km SSO**, S4 climbs **directly to orbit in one burn** with no transfer coast or second burn, and **S3 burns for 120 s**. These three settings are the user's, specified on 2026-11-06. The 120 s value is my choice for "longer": Vega's Zefiro 9 has almost the same propellant load and burns about that long.

### Flight sequence (T0 23:38)

| Event | MET | Lat, lon | Height | Relative speed |
|---|---:|---|---:|---:|
| Max-Q, 45 kPa | T+39 s | 40.96, 100.34 | 9.6 km | 0.46 km/s |
| Sunlight pickup, geometric | T+49 s | 40.95, 100.34 | 14.8 km | |
| S1 burnout | T+80 s | 40.88, 100.33 | 42.5 km | 1.28 km/s |
| S2 ignition | T+81.5 s | 40.87, 100.33 | 44.4 km | 1.27 km/s |
| S2 burnout | T+156.5 s | 40.01, 100.09 | 144 km | 2.87 km/s |
| Fairing jettison | T+161.5 s | 39.90, 100.05 | 151 km | 2.85 km/s |
| S3 ignition | T+174.5 s | 39.62, 99.97 | 167 km | 2.79 km/s |
| S3 burnout | T+294.5 s | 35.44, 98.78 | 291 km | 6.43 km/s |
| S4 ignition | T+306.5 s | 34.80, 98.61 | 301 km | 6.41 km/s |
| S4 cutoff, in orbit | T+1049 s | −7.45, 89.39 | 504 km | 7.69 km/s |

Two short gaps remain: 18 s between S2 and S3 (when the fairing goes) and 12 s between S3 and S4 (separation).

**Orbit.** 500 km mean altitude, i 97.40°, RAAN 315.44° for this T0, **LTDN 05:57**. This is a dawn-dusk orbit, so the ground track runs near the terminator. That is why this launch has a twilight plume at all. Model TLE: `CERES-2_Y3_prelaunch.tle` (placeholder catalog number, labelled as not observed). RAAN moves +0.2507° per minute of later T0.

### Falls against the NOTAM zones

| Object | Impact | Range | Zone | Zone closes | Status |
|---|---:|---:|---|---:|---|
| S1 | T+462 s | 116 km | A5672/26 | T+12 min | fitted |
| S2 | T+658 s | 1091 km | A5673/26 | T+19 min | fitted |
| Fairing | T+1014 s | 1070 km | A5673/26 | T+19 min | **not fitted** |
| S3 | T+1303 s | 5450 km | E4059/26 | T+32 min | aimed |

Checks that were not fitted:

- The fairing lands inside A5673.
- It lands 21 km north of S2 and about 6 min later. That matches Y1's two overlapping zones: A0119, the northern one, closed 2 min after A0118. Y3's A5673 takes A0118's south edge and A0119's north edge.
- The S3 plane fitted to the zone is 97.35°, and S4 needs only 1.1° of yaw at most to reach the SSO plane. The zones and an SSO plane agree, though the plane itself is an input.

One corridor runs through all the zones, with pad-to-zone bearings of 189.4°, 193.8° and 194.5°.

### Twilight jelly

The Sun is at −4.05° at the pad at T0. S2 and S3 burn fully sunlit while the ground below is still in twilight.

| Quantity | Value |
|---|---|
| Sunlight pickup, geometric | T+49.2 s, 14.8 km |
| Pickup with 34′ refraction | T+41.9 s, 10.9 km |
| Clear sunlight (ray ≥20 km above the surface) | T+73 s, 34 km |
| Solid plume sunlit above 60 km | **T+94 to T+294.5 s** (S2 and S3, with the coast between) |
| Lit time | S1 last 31 of 80 s; S2 all 75 s; S3 all 120 s; S4 all 743 s |
| 10° zone, solid burns | 2.74 M km², 26.0–46.2 °N, 87.0–107.2 °E |
| The same zone with Sun ≤ −6° | 1.24 M km² |

At pickup the sunward ray grazes the ground, so the plume starts deep red and low. The jelly-like phase is the S2 and S3 burn. S4 is lit throughout, but its roughly 5 kN hypergolic plume is far weaker than the solids and should not be read as a jelly forecast; its 10° zone is drawn separately.

The sky is darkest **west of the track**. East of it the Sun is already near or above the horizon.

| Site | Max elevation, solid burns | At | Sun then |
|---|---:|---:|---:|
| Zhangye | 73° | T+201 s | −2.7° |
| Delingha | 56° | T+265 s | −4.4° |
| Jiuquan | 54° | T+194 s | −4.4° |
| Xining | 47° | T+267 s | −0.8° |
| Yushu | 41° | T+294 s | −3.2° |
| Golmud | 36° | T+294 s | −5.9° |
| **Dunhuang** | 24° | T+250 s | **−7.2°** |
| Chengdu | 18° | T+294 s | +3.2° (daylight) |
| **Nagqu** | 17° | T+294 s | **−6.8°** |
| **Hami** | 14° | T+246 s | **−8.7°** |
| **Lhasa** | 12° | T+294 s | **−7.1°** |
| **Shigatse** | 9° | T+294 s | **−9.0°** |

Bold marks Sun at or below −6°. Full table: `CERES-2_Y3_jelly.json`. Map: `CERES-2_Y3_jelly.png`.

**T0 matters as much as any vehicle assumption.** The path is Earth-fixed, so only the Sun moves:

| T0 | Pad Sun | Pickup | 10° zone | Zone with Sun ≤ −6° |
|---|---:|---:|---:|---:|
| 23:28 | −5.85° | T+70 s, 31 km | 3.16 M km² | 1.71 M km² |
| 23:38 | −4.05° | T+49 s, 15 km | 2.74 | 1.24 |
| 23:44 | −2.97° | T+35 s, 8 km | 2.47 | 0.98 |
| 23:50 | −1.91° | T+21 s, 3 km | 2.20 | 0.73 |

### Sensitivity (recalibrated and refitted, one assumption at a time, T0 fixed)

| Assumption | Value | Level f | S3 burnout | Clear sun | Golmud / Dunhuang / Hami / Nagqu elevation |
|---|---|---:|---:|---:|---|
| Nominal | | 0.40 | T+294.5 s, 291 km | T+73 s | 36.2 / 23.6 / 14.0 / 17.0° |
| S3 burn | 75 s | 0.23 | T+249.5 s, 250 km | T+74 s | 30.3 / 22.9 / 13.6 / 11.2° |
| | 100 s | 0.30 | T+274.5 s, 274 km | T+74 s | 34.5 / 23.4 / 13.9 / 14.3° |
| | 140 s | 0.51 | T+314.5 s, 307 km | T+73 s | 36.8 / 23.8 / 14.1 / 19.7° |
| S1 burn | 72 s | 0.37 | T+286.5 s, 293 km | T+67 s | 36.4 / 23.9 / 14.2 / 17.1° |
| | 88 s | 0.42 | T+302.5 s, 289 km | T+80 s | 36.0 / 23.4 / 13.8 / 16.9° |
| S2 burn | 68 s | 0.39 | T+287.5 s, 288 km | T+73 s | 36.0 / 23.5 / 13.9 / 16.6° |
| | 82 s | 0.40 | T+301.5 s, 295 km | T+73 s | 36.5 / 23.8 / 14.2 / 17.4° |
| S1 impact | 90 km | 0.70 | T+294.5 s, 309 km | T+73 s | 37.9 / 25.4 / 15.4 / 17.5° |
| S3 aim | 5600 km | 0.29 | T+294.5 s, 296 km | T+74 s | 36.7 / 23.8 / 14.2 / 17.2° |

**The budget closes only narrowly.** With 1.3 t, a direct climb and a 1200 kg S4 load, these cases do not close even at f = 1.5, the top of the search range:

| Case | Short by |
|---|---:|
| S3 aim 5091 km, the zone's mid-range | 135 kg |
| S3 aim 5300 km | 25 kg |
| S1 impact 145 km | 22 kg |
| S4 thrust 7 kN | 2 kg |
| S4 thrust 3.5 kN | no converged solution |

A longer S3 burn costs little propellant but does need more efficiency: f rises from 0.23 at 75 s to 0.40 at 120 s and 0.51 at 140 s. In return it extends the bright solid phase and carries S3 about 40 km higher, which widens the zone.

## Method

`ceres2.py` is a 3-DOF model with J2–J4 gravity, US76 atmosphere, Mach-dependent drag and rotating air. Generic pieces are imported from `../launch_traj_NROL-97/nrol97.py`, the same base as the Zhuque builder. The Sun comes from the shared DE440s kernel.

The flight law follows the Vega User's Manual and the solid-vehicle pattern. A solid cannot be shut down, so burnout energy is fixed and steering only decides where it goes.

| Stage | Law | What fixes it |
|---|---|---|
| S1 | Vertical rise, pitch kick, zero incidence on a great circle | Kick and azimuth drop S1 on the A5672 centroid |
| S2 | From the flight path to a bilinear-tangent attitude in 10 s, constant yaw | Pitch rate and yaw drop S2 on the A5673 centroid |
| Coast | Fairing goes 5 s after S2 burnout | Heat flux is already far below 1135 W/m² |
| S3 | Bilinear tangent, constant yaw | Drops S3 at 5450 km in the E4059 tail |
| S4 | One bilinear-tangent burn | Circular at 500 km mean altitude, fuel-optimal node |

**Why S1 is so steep.** A 1.3 km/s burnout landing only 116 km away is ballistically possible only near vertical (72° here) or very flat. The flat branch leaves S2 inside the atmosphere, so only the steep one flies. S2 lights at 44 km at q under 3 kPa, which leaves room for a large pitch-over: peak qα is 18 kPa·deg. That climb carries Earth's rotation with it, so the instantaneous inertial inclination runs 63° at S1 burnout, 93° at S2 burnout, 97.35° at S3 burnout and 97.40° in orbit.

**Why S3 falls so far south.** A direct climb needs S3 to end high and still rising, so S4 does not have to pitch steeply. Here S3 burns out at 291 km with an 8° flight path and a 411 km apogee, and S4 pitches gently from 32° to 3°. That lofted arc lands far downrange. Aimed at the zone's 5091 km mid-range, S3 flies too flat and 1.3 t does not close. CERES-1's own S3 zones are at similar range (5470–5610 km). 5450 km is the farthest nominal that keeps CERES-1's ±150 km zone half-length inside the 5611 km far edge.

**What the direct climb costs.** On the earlier two-burn vehicle, a direct climb took about 240 kg more S4 propellant. So the S4 load is now 1200 kg, up from 900 kg, and no aim in the zone closes on 1000 kg.

### Vehicle (estimates except where marked)

| | Propellant | Structure dropped | Burn | Mean vacuum thrust | Isp vac |
|---|---:|---:|---:|---:|---:|
| S1 | 55.2 t | 4.5 t | 80 s | 1880 kN (1696 kN sea level) | 277.6 s (250.5 s sea level) |
| S2 | 22.6 t | 1.7 t | 75 s | 865 kN | 292.0 s |
| S3 | 11.3 t | 1.0 t | **120 s** | 273 kN | 296.2 s |
| S4 | 1200 kg load, 1185 used | 380 kg | **743 s, one burn** | 4.85 kN | 310 s |

Fairing 760 kg, 2.9 m diameter; lift-off T/W 1.73; about 7 g at S3 burnout, against about 14 g with a 75 s burn.

Published: 100 t lift-off, 2.35 m core, 2.9 or 3.35 m fairing, 1.3 t to 500 km SSO, three solids plus a liquid stage.

Calibration:

1. Stage loads keep the CERES-1 proportions, scaled to 100 t.
2. One efficiency level f is solved so that 1.3 t closes: **f = 0.40**, between CERES-1 Isp and structure (f = 0) and an optimistic reference (f = 1) that reflects the published "295 s" propellant. The solver searches f from −0.5 to 1.5.
3. S4 keeps 1 % of its load as the only reserve, so this vehicle has no spare payload. Y3's real payload is unknown; Y1 carried "over 1 t".

The burn times, S4 load and S4 thrust are assumptions; no source gives them for CERES-2. The 4.85 kN is CERES-1's assumed 1.6 kN scaled by three. GCAT lists S4 at 2 kN and about 1 t, which is not compatible with a direct climb in this model: S3 is sub-orbital, so a weak S4 runs out of time before it falls back.

### Validation on flown vehicles (`validate_precedents.py`, `validation.json`)

The stage falls in this script are **fit targets**, not predictions, so landing in a zone proves nothing by itself. The real test is whether the published payload and lift-off mass close once the model is aimed at the real zones.

| Vehicle | Test | Model | Published or flown |
|---|---|---:|---:|
| CERES-1 | Lift-off mass from public motor figures, with my structure fractions | 32.6 t | ~33 t |
| | S4 propellant to put 300 kg in 500 km SSO, direct climb | 312–315 kg | no published load; 300 kg assumed |
| ZK-1A | S4 Δv budget for 1.5 t to 530 km SSO | needs 1853 m/s | 2118 m/s from the public 1.99 t load |

- **Not an independent check:** the CERES-1 S4 burn time of about 600 s. I picked its 1.6 kN thrust from the Y19 report of an anomaly after 510 s of S4 burn. Propellant use barely depends on that thrust.
- **ZK-1A plane:** its S3 plane fits at about 93.4°, so its solid S4 must carry a 4° dogleg to reach 97.5°. Its corridor differs from CERES (Z2 bearing 188° against 194°).

SD-3 uses the same motor family as ZK-1A (Gunter's Space Page, GCAT) and flies from sea, so it has no Jiuquan zones to test. Guan et al. (2025) confirm its 71 t, 200 t-thrust first motor; the paper publishes no timeline.

### Limits

- Burn times, thrust curves, stage split and structure are estimates, not published values. Stage event times move by up to about ±10 s across the sensitivity cases, and the real error could be larger.
- **The S3 aim is a choice.** The zone runs 4571–5611 km. 5450 km comes from CERES-1's zone half-length and is not published for CERES-2. The S4 cutoff and S3 impact both move with it.
- **The direct climb and 1.3 t leave no margin.** Small changes in assumptions stop the budget closing (see the sensitivity section). The real flight may carry less payload or fly differently.
- Target altitude and inclination are assumed: 500 km and SSO. The press report says SSO; the altitude is the published reference orbit, not this mission's.
- The pad is 95A per secondary sources. The launch-time dependency is geometric only: the Earth-fixed track is held fixed when T0 moves.
- Jelly numbers are geometry. They include no plume size, brightness, cloud, extinction or terrain. Visibility is sea-level. The solid zone uses the night side at the pickup epoch, so at dawn it slightly overstates darkness later in the burn.
- A failure, as on Y1 (S1 nozzle), is not modeled.

## Files and pipeline

Run in this order with `~/.venvs/astro313/bin/python`:

| Step | Script | Output |
|---|---|---|
| 1 | `validate_precedents.py` | `validation.json` |
| 2 | `build_traj.py [--t0 ISO] [--payload 1300] [--alt 500] [--sens]` | `CERES-2_Y3_{solution.json, traj.csv, orbit.csv, traj.kml, prelaunch.tle}` |
| 3 | `jelly_ceres2.py [--t0 ISO]` | `CERES-2_Y3_jelly.{json, png, kml}` |
| 4 | `web_export.py` | `docs/data/ceres2-y3.json`, `docs/data/profiles.json` |

Step 2 takes about 1 min, or several minutes with `--sens`. `ceres2.py` is the core module.

`docs/` is the CZ-6A viewer (Apache-2.0, see `docs/LICENSE-CZ-6A-viewer.txt`) with this mission's data. New there: `js/jelly-zone.js`, `js/sky-background.js`, `js/vehicle-art.js`, the textures and `data/hipparcos.json`. Changed: `js/app.js`, `js/cities.js`, `js/map-lod.js`, `js/map-tiles.js`, one label in `js/skychart.js`, and `index.html`.

## After the launch

```sh
~/.venvs/astro313/bin/python ~/.claude/skills/space-track/st.py launch --date 2026-11-06 --site JSC --tle 2
```

If nothing is listed under that date, try `--date 2026-11-07`. Compare inclination and altitude with the model TLE, and solve the real T0 from RAAN at +0.2507° per minute. Then rerun `jelly_ceres2.py --t0 <actual>`.

## Sources

- NOTAMs: `notam_ceres-2_Y3`; CERES-2 Y1 and sibling zones from `../notam/notam_data.json`.
- Data from GCAT (J. McDowell, planet4589.org/space/gcat), CC-BY 4.0. Recent Jiuquan orbits from Space-Track.org.
- CERES-2: [NetEase, launch timing and SSO](https://www.163.com/dy/article/LB2CNNOM0552MUWE.html); [Zhihu, pad 95A, Y3, failure cause](https://zhuanlan.zhihu.com/p/2099524410411573251); [zh-Wikipedia](https://zh.wikipedia.org/zh-hans/%E8%B0%B7%E7%A5%9E%E6%98%9F%E4%BA%8C%E5%8F%B7%E8%BF%90%E8%BD%BD%E7%81%AB%E7%AE%AD); [Baike](https://baike.baidu.com/item/%E8%B0%B7%E7%A5%9E%E6%98%9F%E4%BA%8C%E5%8F%B7/65266086); [Beijing Daily](https://peking.bjd.com.cn/content/s68a30556e4b02424b0befb15.html); [China in Space](https://www.china-in-space.com/p/galactic-energy-prepares-to-debut).
- CERES-1: [zh-Wikipedia](https://zh.wikipedia.org/zh-hans/%E8%B0%B7%E7%A5%9E%E6%98%9F%E4%B8%80%E5%8F%B7%E8%BF%90%E8%BD%BD%E7%81%AB%E7%AE%AD); [Baike](https://baike.baidu.com/item/%E8%B0%B7%E7%A5%9E%E6%98%9F%E4%B8%80%E5%8F%B7/23780732).
- ZK-1A: [zh-Wikipedia](https://zh.wikipedia.org/zh-hans/%E5%8A%9B%E7%AE%AD%E4%B8%80%E5%8F%B7%E8%BF%90%E8%BD%BD%E7%81%AB%E7%AE%AD); [CAS Space](https://www.cas-space.com/list/39.html).
- SD-3: [Guan et al. 2025](https://www.sciengine.com/doi/pdf/F67DDF9D0D1D43F0A4ACC5DC9E772089); [CNSA](https://www.cnsa.gov.cn/n6759533/c6841762/content.html); [Gunter's Space Page](https://space.skyrocket.de/doc_lau/jielong-3.htm).
- Vega: [User's Manual, Issue 4](http://www.georing.biz/usefull/Vega-Users-Manual_Issue-04_April-2014.pdf).

Illustration: Mickey. Base map NASA Blue Marble; night lights NASA Black Marble 2016 (Suomi NPP VIIRS); Moon LROC; stars ESA Hipparcos (ESA SP-1200). Three.js, d3-celestial and Natural Earth attributions are in `docs/`.
