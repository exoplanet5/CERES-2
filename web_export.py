#!/usr/bin/env python3
"""Export the CERES-2 model to the 3D page's mission data (docs/data/ceres2-y3.json, schema: CZ-6A PROFILE_FORMAT.md).

Resamples the built trajectory onto uniform grids; it does not fit or integrate anything.  The Earth-fixed track holds for every
T0 on the page; only the Sun moves.  Sun vectors come from the shared DE440s kernel, which is read, never copied.

Run after build_traj.py and jelly_ceres2.py:  ~/.venvs/astro313/bin/python web_export.py
"""
import csv
import json
import math
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np
from skyfield.api import Loader, load_file
from skyfield.framelib import itrs

import ceres2 as C
import jelly_ceres2 as J

HERE = Path(__file__).resolve().parent
DOCS = HERE / "docs"
STEM = "CERES-2_Y3"
MISSION = "ceres2-y3"
T0_MIN, T0_MAX = "23:28:00", "23:50:00"    # A5672/26 window
ORBIT_DT = 5.0
RAD_TO_6 = 6


def load_csv(name):
    with open(HERE / name) as fh:
        rows = list(csv.DictReader(fh))
    return (np.array([float(q["t"]) for q in rows]), np.array([[float(q[k]) for k in ("x", "y", "z")] for q in rows]))


def uniform(t, X, t_a, t_b, dt_max):
    """Uniform samples t_a..t_b ending exactly at t_b, linear in ECEF. -> track dict without style"""
    n = max(1, int(math.ceil((t_b - t_a) / dt_max - 1e-9)))
    dt = (t_b - t_a) / n
    lon, lat, alt = [], [], []
    for k in range(n + 1):
        tt = t_b if k == n else t_a + k * dt
        i = int(np.clip(np.searchsorted(t, tt) - 1, 0, len(t) - 2))
        f = (tt - t[i]) / (t[i + 1] - t[i]) if t[i + 1] > t[i] else 0.0
        la, lo, h = C.ecef_to_geodetic(X[i] + (X[i + 1] - X[i]) * f)
        lat.append(round(float(la), RAD_TO_6))
        lon.append(round(float(lo), RAD_TO_6))
        alt.append(round(max(float(h), 0.0), 4))
    return dict(met0=float(t_a), dt=float(dt), lon=lon, lat=lat, alt=alt)


def fall_track(rows, color, label):
    a = np.array(rows, float)
    t = a[:, 0]
    n = max(1, int(math.ceil((t[-1] - t[0]) / 5.0)))
    ts = np.linspace(t[0], t[-1], n + 1)
    return dict(met0=float(t[0]), dt=float((t[-1] - t[0]) / n), lon=[round(float(x), 4) for x in np.interp(ts, t, a[:, 2])],
                lat=[round(float(x), 4) for x in np.interp(ts, t, a[:, 1])], alt=[round(float(x), 3) for x in np.interp(ts, t, a[:, 3])],
                color=color, label=label, dashed=True)


def body_table(body, start, end, model):
    load = Loader(str(HERE), verbose=False)
    ts = load.timescale(builtin=True)
    eph = load_file(os.path.expanduser("~/JPLDE/de440s.bsp"))
    n = int((end - start).total_seconds() // 30) + 2
    utc = [start + timedelta(seconds=30 * k) for k in range(n)]
    ta = ts.from_datetimes(utc)
    vec = eph["earth"].at(ta).observe(eph[body]).frame_xyz(itrs).km.T
    return dict(start_utc=start.strftime("%Y-%m-%dT%H:%M:%SZ"), dt=30, vectors=[[round(float(v), 1) for v in p] for p in vec], model=model)


def main():
    sol = json.loads((HERE / f"{STEM}_solution.json").read_text())
    jelly = json.loads((HERE / f"{STEM}_jelly.json").read_text())
    ev = {e["event"]: e for e in sol["events"]}
    orb = sol["orbit"]
    t_cut, t_end = orb["t_cut"], orb["t_end"]
    t_s1, t_s2i, t_s2 = ev["S1 burnout"]["t"], ev["S1 separation, S2 ignition"]["t"], ev["S2 burnout"]["t"]
    t_s3i, t_s3, t_s4i = ev["S3 ignition"]["t"], ev["S3 burnout"]["t"], ev["S4 ignition"]["t"]

    ta, Xa = load_csv(f"{STEM}_traj.csv")
    to, Xo = load_csv(f"{STEM}_orbit.csv")
    ascent = uniform(ta, Xa, 0.0, t_cut, 1.0)
    orbit = uniform(to, Xo, t_cut, t_end, ORBIT_DT)
    ascent.update(color="#d95926", label="Ascent")
    orbit.update(color="#c77dff", label="Orbit")
    falls = sol["falls"]
    tracks = dict(ascent=ascent, orbit=orbit,
                  s1fall=fall_track(falls["S1"]["rows"], "#ff8a50", "S1 fall"), s2fall=fall_track(falls["S2"]["rows"], "#ffb84f", "S2 fall"),
                  fairfall=fall_track(falls["Fairing"]["rows"], "#cfd6dd", "Fairing fall"), s3fall=fall_track(falls["S3"]["rows"], "#ffd54f", "S3 fall"))

    z = {q["id"]: q for q in sol["zones"]}
    pad = (sol["pad"]["lat"], sol["pad"]["lon"])

    def zone(zid, role, color, desc, impact=None, note=None):
        q = z[zid]
        ring = [[round(lo, 5), round(la, 5)] for la, lo in q["ring"]]
        ring.append(ring[0])
        out = dict(key=zid.split("/")[0], id=zid, role=role, color=color, t0=q["t0"], t1=q["t1"], ring=ring,
                   centroid=[round(q["centroid"][1], 4), round(q["centroid"][0], 4)], dist_km=round(C.gc_dist(pad, q["centroid"]), 1),
                   bearing=round(C.bearing(pad, q["centroid"]), 2), desc=desc)
        if impact:
            out["impact"] = dict(met=impact["t"], lon=impact["lon"], lat=impact["lat"])
        if note:
            out["impact_note"] = note
        return out

    zones = [zone("A5672/26", "S1", "#ff8a50", "Stage 1 zone, Lanzhou FIR", falls["S1"]),
             zone("A5673/26", "S2 + fairing", "#ffb84f", f"Stage 2 falls at T+{falls['S2']['t']:.0f} s and the fairing at T+{falls['Fairing']['t']:.0f} s; "
                  "the zone is the union of CERES-2 Y1's A0118 and A0119", falls["S2"]),
             zone("A0582/26", "S3 north", "#ffd54f", "Stage 3 zone, Colombo FIR", None, "In E4059"),
             zone("E4059/26", "S3 south", "#ffd54f", "Stage 3 zone, Melbourne FIR ('Area PH')", falls["S3"])]

    def e(met, label, major=False, track=None):
        out = dict(met=float(met), label=label, major=major, kind="ship")
        if track:
            out["track"] = track
        return out

    events = [e(0, "Liftoff", True), e(ev["Max-Q"]["t"], f"Max-Q {ev['Max-Q']['q_kpa']:.0f} kPa"), e(t_s1, "S1 burnout", True), e(t_s2i, "S2 ignition"),
              e(t_s2, "S2 burnout", True), e(ev["Fairing jettison"]["t"], "Fairing jettison"), e(t_s3i, "S3 ignition"), e(t_s3, "S3 burnout", True),
              e(t_s4i, "S4 ignition"), e(t_cut, "S4 cutoff, orbit", True),
              e(t_cut + orb["period"], "1 revolution"), e(t_end, "1.5 revolutions"),
              e(falls["S1"]["t"], "S1 impact", True, "s1fall"), e(falls["S2"]["t"], "S2 impact", True, "s2fall"),
              e(falls["Fairing"]["t"], "Fairing impact", False, "fairfall"), e(falls["S3"]["t"], "S3 impact", True, "s3fall")]
    events.sort(key=lambda q: q["met"])

    b = sol["budget"]
    s4x = sol["steering"]["s4"]
    notes = [
        "Pre-launch model, not telemetry and not an official ephemeris. T0 23:38:00 UTC (07:38 Beijing) is assumed: the launch is only reported as 'about 07:00 Beijing, 7 November' at the earliest.",
        "CERES-2 Y3 (遥三), mission 砺锋行, is the second CERES-2 flight. Pad 95A is from secondary sources.",
        "Public data: 100 t lift-off, 1.3 t to 500 km SSO, three solid stages and a liquid upper stage, 2.35 m core. The mission flies that 1.3 t. Motor loads, Isp and structure are scaled from CERES-1, whose published payload and lift-off mass the same model closes (validate_precedents.py).",
        f"Stage split {b['s1_prop'] / 1e3:.1f} / {b['s2_prop'] / 1e3:.1f} / {b['s3_prop'] / 1e3:.1f} t of propellant, S4 load {b['s4_prop']:.0f} kg. Burn times 80 / 75 / {b['t_burn'][2]:.0f} s and the S4 thrust {b['s4_thrust'] / 1e3:.2f} kN are assumptions; lift-off T/W {b['liftoff_tw']:.2f}. S4 climbs directly to the orbit in one {b['t_burn'][3]:.0f} s burn, with no transfer coast and no second burn.",
        "Steep S1 climb: a 116 km S1 impact from a 1.3 km/s burnout allows only a near-vertical path (the flat ballistic solution leaves S2 in the air). S2 then pitches over and yaws out the Earth-rotation velocity carried from the pad.",
        f"Zones: S1 and S2 are fitted to the centres of A5672 and A5673. S3 is aimed at {sol['targets']['s3_aim']:.0f} km in the E4059 tail, because a direct S4 climb cannot close 1.3 t from the old mid-range aim. The orbit plane is an input, SSO i = {orb['i']:.2f} deg for 500 km, and those fits need at most {max(abs(math.degrees(math.atan(s4x[2]))), abs(math.degrees(math.atan(s4x[2] + s4x[3] * s4x[4])))):.1f} deg of S4 yaw to reach it, so the zones and an SSO plane agree. The fairing, 5 s after S2 burnout, lands in A5673 without being fitted.",
        f"LTDN {int(round(orb['ltdn_h'] * 60)) // 60:02d}:{int(round(orb['ltdn_h'] * 60)) % 60:02d}: a dawn-dusk orbit, so the ground track runs close to the terminator. That is why this launch has a twilight plume at all.",
        "Sunlight: geometric WGS84 occultation of the Sun's centre with DE440s, 30 s cadence. The 34' figure is the launch_jelly convention. Near pickup the ray grazes the ground, so the plume starts deep red; 'clear sunlight' means the ray passes at least 20 km above the surface.",
        "On this page the zones' night edge follows the live Sun 0 line exactly, so it moves during playback; the area figures use one reference epoch, the sunlight pickup, as the static map does. Glow is an illustration. Plume size and brightness, weather, extinction and terrain are not modeled. Geometric visibility is not a claim of naked-eye detection; the S4 plume is far weaker than the solid motors.",
        f"The page's 500 km is the orbit-mean altitude; the osculating orbit at cutoff is {orb['hp']:.0f} x {orb['ha']:.0f} km. Shifting T0 keeps the Earth-fixed path and moves the Sun. Stage failure, as on the first flight, is not modeled. Data from GCAT (J. McDowell, planet4589.org/space/gcat).",
    ]
    t_min, t_max = T0_MIN, T0_MAX
    meta = dict(
        title="CERES-2 Y3 Launch visibility", vehicle="CERES-2 Y3", mission="SSO 500 km", date="2026-11-06",
        pad=[pad[1], pad[0]], pad_alt=sol["pad"]["h"], pad_name="Jiuquan 95A",
        t0_default="23:38:00", t0_min=t_min, t0_max=t_max,
        t0_presets=[dict(label="Open 23:28", time="23:28:00"), dict(label="Model 23:38", time="23:38:00"), dict(label="Close 23:50", time="23:50:00")],
        met_default=200, insertion_met=t_cut, period_s=orb["period"], orbit_revolutions=orb["revolutions"], inc=orb["i"], perigee_km=orb["mean_alt"], apogee_km=orb["mean_alt"], az=sol["steering"]["az"],
        s4_cutoff_met=t_cut, solid_end_met=t_s3,
        # Rocket cartoon in the template's format: segment sizes in metres, and the states the stack passes through, each ending at a separation.
        stack=dict(total_m=30, burn_end=t_cut,
                   segments=dict(s1=dict(len=11.0, w=2.35, kind="solid", band=True), s2=dict(len=6.6, w=2.35, kind="solid"), s3=dict(len=3.4, w=1.9, kind="solid"),
                                 s4=dict(len=1.5, w=1.9, kind="liquid"), fairing=dict(len=7.5, w=2.9, kind="fairing"), payload=dict(len=2.6, w=1.5, kind="payload")),
                   states=[dict(until=t_s2i, segs=["s1", "s2", "s3", "s4", "fairing"], zoom=1, burn="solid"), dict(until=t_s2 + 2.0, segs=["s2", "s3", "s4", "fairing"], zoom=1.2, burn="solid"),
                           dict(until=ev["Fairing jettison"]["t"], segs=["s3", "s4", "fairing"], zoom=1.7, burn=None), dict(until=t_s3 + 3.0, segs=["s3", "s4", "payload"], zoom=2.3, burn="solid"),
                           dict(segs=["s4", "payload"], zoom=3.2, burn="liquid")]),
        observer_home="Golmud",
        # Corridor cities beyond the template's built-in list
        extra_cities=[["Delingha", 97.36, 37.37, 2], ["Thimphu", 89.64, 27.47, 2], ["Guwahati", 91.74, 26.14, 2], ["Dhaka", 90.41, 23.81, 1], ["Kolkata", 88.36, 22.57, 1],
                      ["Mandalay", 96.09, 21.96, 2], ["Bhubaneswar", 85.82, 20.30, 2], ["Yangon", 96.17, 16.84, 1], ["Port Blair", 92.74, 11.62, 2], ["Chennai", 80.27, 13.08, 1], ["Colombo", 79.86, 6.93, 1]],
        flight_segments=["ascent", "orbit"],
        powered_intervals=[[0.0, t_s1], [t_s2i, t_s2], [t_s3i, t_s3], [t_s4i, t_cut]],
        phases=[dict(until=0, label="Pre-launch"), dict(until=t_s1, label="S1 solid burn"), dict(until=t_s2i, label="Staging"), dict(until=t_s2, label="S2 solid burn"),
                dict(until=t_s3i, label="Coast, fairing off"), dict(until=t_s3, label="S3 solid burn"), dict(until=t_s4i, label="S3-S4 staging"), dict(until=t_cut, label="S4 direct climb"),
                dict(until=t_end + 1, label="500 km SSO")],
        views=[["Global", 95, 18, 3.6], ["Pad", pad[1], pad[0] - 1.0, 1.12], ["Jelly zone", 97, 36, 1.5], ["Corridor", 95, 14, 2.3]],
        visibility=dict(extent=[60, 124, -20, 58], grid_step_deg=0.25, time_step_s=2, levels=[10]),
        jelly=dict(prime_sun_deg=-6, clear_ray_km=J.CLEAR_RAY_KM, high_km=60, stages=[dict(label="S1", a=0.0, b=t_s1), dict(label="S2", a=t_s2i, b=t_s2), dict(label="S3", a=t_s3i, b=t_s3), dict(label="S4", a=t_s4i, b=t_cut)],
                   cities=[[n, lo, la] for n, la, lo in J.CITIES],
                   solid_label="S1–S3", viewers_title="Best views of the solid burns",
                   pickup_note="At pickup the sunward ray grazes the ground, so the plume starts deep red. Clear sunlight: the ray passes at least 20 km above the surface. Lit S4 is a far fainter plume than the solid motors.",
                   viewers_note="Sunlit S1–S3 only, sea-level sites. Bold: Sun at or below −6°, the darker sky. Dim: Sun already up."),
        notes=notes)
    t0_lo = datetime(2026, 11, 6, 23, 28, tzinfo=timezone.utc)
    t0_hi = datetime(2026, 11, 6, 23, 50, tzinfo=timezone.utc)
    t_a, t_b = t0_lo - timedelta(minutes=10), t0_hi + timedelta(seconds=t_end + 60)
    sun = body_table("sun", t_a, t_b, "DE440s geometric Sun centre; WGS84 occultation")
    moon = body_table("moon", t_a, t_b, "DE440s geometric Moon centre")
    tle = sol["tle"]["lines"]
    data = dict(schema_version=1, meta=meta, tracks=tracks, zones=zones, events=events,
                tle_ref=dict(t0=sol["t0"] + "Z", raan_rate_deg_per_min=orb["raan_rate_deg_per_min"], sets=[dict(name=tle[0], l1=tle[1], l2=tle[2])]), sun=sun, moon=moon)
    out = DOCS / "data" / f"{MISSION}.json"
    out.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False))
    manifest = dict(schema_version=1, default_profile="sso-97", supported_families=["retrograde", "polar", "sso", "low-inclination"],
                    profiles=[dict(id="sso-97", label="Sun-synchronous · 97.4°", family="sso", default_mission=MISSION,
                                   missions=[dict(id=MISSION, label="CERES-2 Y3 · 7 Nov", file=f"data/{MISSION}.json")])])
    (DOCS / "data" / "profiles.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"wrote {out} ({out.stat().st_size / 1e3:.0f} kB): " + ", ".join(f"{k} {len(v['lon'])} pts dt {v['dt']:.2f}" for k, v in tracks.items()))


if __name__ == "__main__":
    main()
