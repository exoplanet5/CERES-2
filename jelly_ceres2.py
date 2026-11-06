#!/usr/bin/env python3
"""Twilight-jelly forecast for CERES-2 Y3, the second CERES-2 flight, from CERES-2_Y3_traj.csv (run build_traj.py first).

Two sunlight tests, reported side by side:
  geometric   the segment from the vehicle to the Sun's centre misses the WGS84 ellipsoid (DE440s, as the 3D page does);
  refracted   h >= R(sec(a - 34') - 1), the launch_jelly convention, imported from jelly_forecast.py (a = Sun depression at
              the sub-vehicle point).
The Sun is evaluated at each sample's own time; it climbs about 0.17 deg/min at the pad.

Visibility zones (10 deg minimum elevation, the launch-plot default): a ground point qualifies when the sunlit powered vehicle
reaches 10 deg AND the point is on the night side at one reference epoch, the sunlight pickup.  S1-S3 and S4 are kept
apart, because a solid motor's alumina exhaust is far brighter than the small S4 hypergolic plume.

Run: ~/.venvs/astro313/bin/python jelly_ceres2.py [--t0 2026-11-06T23:38:00]
Writes CERES-2_Y3_jelly.{json,png,kml}.
"""
import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import simplekml
from skyfield.api import Loader, load_file
from skyfield.framelib import itrs

HERE = Path(__file__).resolve().parent
sys.path.insert(0, os.path.expanduser("~/launch/launch_jelly"))
import jelly_forecast as JF  # noqa: E402

STEM = "CERES-2_Y3"
RE, F_E = 6378.137, 1 / 298.257223563
E2 = F_E * (2 - F_E)
RB = RE * (1 - F_E)
MIN_ELEV = 10.0
CLEAR_RAY_KM = 20.0
CITIES = [  # name, lat, lon
    ("Jiuquan", 39.73, 98.49), ("Zhangye", 38.93, 100.45), ("Jinchang", 38.52, 102.19), ("Dunhuang", 40.14, 94.66), ("Hami", 42.82, 93.51),
    ("Golmud", 36.40, 94.90), ("Delingha", 37.37, 97.36), ("Xining", 36.62, 101.78), ("Lanzhou", 36.06, 103.83), ("Yinchuan", 38.49, 106.23),
    ("Yushu", 33.00, 97.01), ("Chamdo", 31.14, 97.17), ("Nagqu", 31.48, 92.05), ("Lhasa", 29.65, 91.13), ("Shigatse", 29.27, 88.88),
    ("Nyingchi", 29.65, 94.36), ("Korla", 41.77, 86.15), ("Ürümqi", 43.80, 87.60), ("Hotan", 37.11, 79.92), ("Kashgar", 39.47, 75.99),
    ("Kangding", 30.05, 101.96), ("Chengdu", 30.66, 104.07), ("Lijiang", 26.86, 100.23), ("Kunming", 25.04, 102.71), ("Thimphu", 27.47, 89.64),
    ("Kathmandu", 27.70, 85.32), ("Guwahati", 26.14, 91.74), ("Dhaka", 23.81, 90.41), ("Kolkata", 22.57, 88.36), ("Mandalay", 21.96, 96.09),
    ("Yangon", 16.84, 96.17), ("Delhi", 28.61, 77.21), ("Bhubaneswar", 20.30, 85.82), ("Chennai", 13.08, 80.27), ("Colombo", 6.93, 79.86),
]
MAP_CITIES = {"Jiuquan", "Dunhuang", "Hami", "Golmud", "Xining", "Lanzhou", "Yinchuan", "Yushu", "Lhasa", "Shigatse", "Korla", "Ürümqi", "Kashgar", "Hotan",
              "Chengdu", "Kunming", "Lijiang", "Kathmandu", "Thimphu", "Dhaka", "Kolkata", "Mandalay", "Yangon", "Delhi", "Bhubaneswar", "Chennai", "Colombo", "Chamdo", "Nagqu"}
COL = dict(S1="#ff8a50", S2="#ffb84f", S3="#ffd54f", S4="#7ad97a", coast="#9fb7c8")


def ecef(lat, lon, h=0.0):
    la, lo = np.radians(lat), np.radians(lon)
    N = RE / np.sqrt(1 - E2 * np.sin(la) ** 2)
    return np.stack([(N + h) * np.cos(la) * np.cos(lo), (N + h) * np.cos(la) * np.sin(lo), (N * (1 - E2) + h) * np.sin(la)], axis=-1)


def up_vec(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)], axis=-1)


class Sun:
    """Geometric Earth-to-Sun vector in ITRS km from the shared DE440s (never copied).  A 30 s table, linearly interpolated,
    the same scheme the 3D page uses."""

    def __init__(self, start, end):
        load = Loader(str(HERE), verbose=False)
        ts = load.timescale(builtin=True)
        eph = load_file(os.path.expanduser("~/JPLDE/de440s.bsp"))
        self.t0 = start
        self.n = int((end - start).total_seconds() // 30) + 2
        self.utc = [start + timedelta(seconds=30 * k) for k in range(self.n)]
        ta = ts.from_datetimes([u.replace(tzinfo=__import__("datetime").timezone.utc) for u in self.utc])
        earth, sun = eph["earth"], eph["sun"]
        self.vec = earth.at(ta).observe(sun).frame_xyz(itrs).km.T

    def at(self, when):
        x = (when - self.t0).total_seconds() / 30.0
        k = min(int(x), self.n - 2)
        return self.vec[k] + (self.vec[k + 1] - self.vec[k]) * (x - k)


def sun_el(lat, lon, s):
    """Sun-centre elevation, deg, from sea level at (lat, lon); finite distance, no refraction."""
    u = up_vec(lat, lon)
    d = s - ecef(lat, lon)
    return np.degrees(np.arcsin(np.sum(d * u, axis=-1) / np.linalg.norm(d, axis=-1)))


def lit_geometric(p, s):
    """Vehicle-to-Sun-centre segment misses the WGS84 ellipsoid."""
    ax = np.array([RE, RE, RB])
    r, d = p / ax, (s - p) / ax
    t = np.clip(-(r @ d) / (d @ d), 0.0, 1.0)
    q = r + t * d
    return bool(q @ q > 1.0)


def load_rows():
    with open(HERE / f"{STEM}_traj.csv") as fh:
        rows = list(csv.DictReader(fh))
    for q in rows:
        for k in ("t", "lat", "lon", "alt_km", "x", "y", "z", "v_rel", "fpa", "downrange_km"):
            q[k] = float(q[k])
        q["p"] = np.array([q["x"], q["y"], q["z"]])
    return rows


def stage_of(q):
    return q["phase"] if q["phase"] in ("S1", "S2", "S3", "S4") else None


def analyse(rows, t0, sun):
    """Adds sunlight fields to rows for this T0. -> dict with both pickups and per-stage lit time."""
    for q in rows:
        s = sun.at(t0 + timedelta(seconds=q["t"]))
        q["dep"] = float(-sun_el(q["lat"], q["lon"], s))
        q["h_geo"] = JF.shadow_altitude_km(q["dep"], refraction=False)
        q["h_ref"] = JF.shadow_altitude_km(q["dep"], refraction=True)
        q["lit"] = lit_geometric(q["p"], s)
        q["lit_ref"] = q["alt_km"] >= q["h_ref"]
        # height at which the sunward ray grazes the Earth: below about 20 km it crosses cloud, haze and ozone, so the light is red
        q["ray_km"] = (6371.0 + q["alt_km"]) * np.cos(np.radians(max(q["dep"], 0.0))) - 6371.0 if q["dep"] > 0 else q["alt_km"]

    def pickup(key):
        for a, b in zip(rows[:-1], rows[1:]):
            if not a[key] and b[key]:
                f = 0.0
                if key == "lit":
                    lo, hi = a["t"], b["t"]
                    for _ in range(24):
                        mid = 0.5 * (lo + hi)
                        w = (mid - a["t"]) / (b["t"] - a["t"])
                        if lit_geometric(a["p"] + (b["p"] - a["p"]) * w, sun.at(t0 + timedelta(seconds=mid))):
                            hi = mid
                        else:
                            lo = mid
                    f = (hi - a["t"]) / (b["t"] - a["t"])
                else:
                    da, db = a["alt_km"] - a["h_ref"], b["alt_km"] - b["h_ref"]
                    f = da / (da - db)
                g = lambda k: a[k] + (b[k] - a[k]) * f
                return dict(t=g("t"), lat=g("lat"), lon=g("lon"), alt_km=g("alt_km"), dep=g("dep"), phase=b["phase"],
                            utc=(t0 + timedelta(seconds=g("t"))).isoformat(timespec="seconds"))
        return dict(t=0.0, lat=rows[0]["lat"], lon=rows[0]["lon"], alt_km=rows[0]["alt_km"], dep=rows[0]["dep"], phase="S1",
                    utc=t0.isoformat(timespec="seconds")) if rows[0][key] else None

    pg, pr = pickup("lit"), pickup("lit_ref")
    clear = next((q for q in rows if q["lit"] and q["ray_km"] >= CLEAR_RAY_KM), None)
    by_stage = {}
    for st in ("S1", "S2", "S3", "S4"):
        q = [x for x in rows if x["phase"] == st]
        lit = [x for x in q if x["lit"]]
        by_stage[st] = dict(t_start=q[0]["t"], t_end=q[-1]["t"], burn_s=q[-1]["t"] - q[0]["t"], lit_s=(lit[-1]["t"] - lit[0]["t"]) if lit else 0.0,
                            lit_from=lit[0]["t"] if lit else None, h_start=q[0]["alt_km"], h_end=q[-1]["alt_km"],
                            dep_start=q[0]["dep"], dep_end=q[-1]["dep"], lat_end=q[-1]["lat"], lon_end=q[-1]["lon"])
    return dict(pickup_geometric=pg, pickup_refracted=pr, by_stage=by_stage,
                clear_sunlight=dict(t=clear["t"], alt_km=clear["alt_km"], ray_km=clear["ray_km"], phase=clear["phase"]) if clear else None)


def max_elevation(glat, glon, pts):
    """Max elevation, deg, on a lat/lon grid over pts (n,3) ECEF; argmax index too."""
    O = ecef(glat, glon)
    U = up_vec(glat, glon)
    best = np.full(glat.shape, -90.0)
    who = np.zeros(glat.shape, dtype=int)
    for k, p in enumerate(pts):
        d = p - O
        el = np.degrees(np.arcsin(np.sum(d * U, axis=-1) / np.linalg.norm(d, axis=-1)))
        m = el > best
        best[m] = el[m]
        who[m] = k
    return best, who


def az_of(lat, lon, p):
    O, U = ecef(lat, lon), up_vec(lat, lon)
    d = p - O
    la, lo = np.radians(lat), np.radians(lon)
    east = np.array([-np.sin(lo), np.cos(lo), 0.0])
    north = np.cross(U, east)
    return float(np.degrees(np.arctan2(d @ east, d @ north)) % 360)


def zone_samples(rows, phases):
    return [q for q in rows if q["phase"] in phases and q["lit"]]


def zone_area(mask, glat, dlon, dlat):
    return float(np.sum(mask * np.cos(np.radians(glat))) * (111.195 * dlon) * (111.195 * dlat))


def visibility(rows, t0, sun, ref_t, extent=(68.0, 120.0, -14.0, 54.0), step=0.2):
    x0, x1, y0, y1 = extent
    glon, glat = np.meshgrid(np.arange(x0, x1 + 1e-6, step), np.arange(y0, y1 + 1e-6, step))
    s_ref = sun.at(t0 + timedelta(seconds=ref_t))
    alt_ref = sun_el(glat, glon, s_ref)
    solid = zone_samples(rows, ("S1", "S2", "S3"))[::2]
    s4 = zone_samples(rows, ("S4",))[::6]
    me_solid, who_s = max_elevation(glat, glon, np.array([q["p"] for q in solid]))
    me_s4, _ = max_elevation(glat, glon, np.array([q["p"] for q in s4]))
    night = alt_ref <= 0.0
    return dict(glon=glon, glat=glat, alt_ref=alt_ref, me_solid=me_solid, me_s4=me_s4, night=night, solid=solid, s4=s4, step=step,
                mask_solid=(me_solid >= MIN_ELEV) & night, mask_s4=(me_s4 >= MIN_ELEV) & night, mask_prime=(me_solid >= MIN_ELEV) & (alt_ref <= -6.0),
                # continuous fields for smooth contours: positive inside, zero on either the 10 deg edge or the terminator
                f_solid=np.minimum(me_solid - MIN_ELEV, -alt_ref), f_s4=np.minimum(me_s4 - MIN_ELEV, -alt_ref), f_prime=np.minimum(me_solid - MIN_ELEV, -6.0 - alt_ref))


def city_table(rows, t0, sun):
    solid = zone_samples(rows, ("S1", "S2", "S3"))
    s4 = zone_samples(rows, ("S4",))
    out = []
    for name, la, lo in CITIES:
        def best(samples):
            if not samples:
                return None
            O, U = ecef(la, lo), up_vec(la, lo)
            d = np.array([q["p"] for q in samples]) - O
            el = np.degrees(np.arcsin(np.sum(d * U, axis=-1) / np.linalg.norm(d, axis=-1)))
            k = int(np.argmax(el))
            return dict(el=round(float(el[k]), 1), t=round(samples[k]["t"], 1), az=round(az_of(la, lo, samples[k]["p"]), 0), stage=samples[k]["phase"],
                        sun=round(float(sun_el(la, lo, sun.at(t0 + timedelta(seconds=samples[k]["t"])))), 1))
        out.append(dict(name=name, lat=la, lon=lo, solid=best(solid), s4=best(s4)))
    out.sort(key=lambda c: -(c["solid"]["el"] if c["solid"] else -90))
    return out


def t0_scan(rows, t0, sun, ref_key="pickup_geometric"):
    """Earth-fixed path, Sun moved.  T0 inside A5672's 23:28-23:50 window."""
    table = []
    base = t0.replace(hour=23, minute=28, second=0)
    for m in range(0, 23, 2):
        t = base + timedelta(minutes=m)
        info = analyse(rows, t, sun)
        pg, pr = info["pickup_geometric"], info["pickup_refracted"]
        v = visibility(rows, t, sun, pg["t"] if pg else 0.0, step=0.5)
        table.append(dict(t0=t.strftime("%H:%M"), pad_sun=round(float(sun_el(rows[0]["lat"], rows[0]["lon"], sun.at(t))), 2),
                          pickup_t=round(pg["t"], 1) if pg else None, pickup_h=round(pg["alt_km"], 1) if pg else None,
                          pickup_ref_t=round(pr["t"], 1) if pr else None, pickup_ref_h=round(pr["alt_km"], 1) if pr else None,
                          area_solid=round(zone_area(v["mask_solid"], v["glat"], 0.5, 0.5) / 1e6, 2), area_prime=round(zone_area(v["mask_prime"], v["glat"], 0.5, 0.5) / 1e6, 2)))
    return table


def contour_rings(glon, glat, field):
    """Closed rings where a continuous field crosses zero (lon, lat), biggest first."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    cs = ax.contour(glon, glat, field, levels=[0.0])
    rings = [p for p in cs.allsegs[0] if len(p) > 12]
    plt.close(fig)
    rings.sort(key=lambda p: -len(p))
    return rings


def write_kml(path, rows, info, vis, t0):
    kml = simplekml.Kml(name=f"CERES-2 Y3 twilight jelly, T0 {t0:%Y-%m-%d %H:%M} UTC")
    f = kml.newfolder(name="Sunlit plume")
    run = []
    for q in rows + [None]:
        if q is not None and q["lit"] and stage_of(q):
            run.append((q["lon"], q["lat"], q["alt_km"] * 1e3))
        else:
            if len(run) > 1:
                ls = f.newlinestring(name="Sunlit powered arc", coords=run)
                ls.altitudemode = simplekml.AltitudeMode.absolute
                ls.style.linestyle.color = "ff4fd5ff"
                ls.style.linestyle.width = 4
            run = []
    pg = info["pickup_geometric"]
    if pg:
        pt = kml.newpoint(name=f"Sunlight pickup T+{pg['t']:.0f} s, {pg['alt_km']:.0f} km", coords=[(pg["lon"], pg["lat"], pg["alt_km"] * 1e3)])
        pt.altitudemode = simplekml.AltitudeMode.absolute
    z = kml.newfolder(name="10 deg visibility, clipped to the night side at pickup")
    for name, key, colour in (("Solid burns S1-S3", "f_solid", "22ffffff"), ("S4 burn", "f_s4", "1150e0a0"), ("Solid burns, Sun below -6 deg", "f_prime", "2250d5ff")):
        for ring in contour_rings(vis["glon"], vis["glat"], vis[key]):
            p = z.newpolygon(name=name, outerboundaryis=[(float(a), float(b)) for a, b in ring])
            p.style.polystyle.color = colour
            p.style.linestyle.color = "ffffffff"
    kml.save(path)


def edge_line(ax, vis, key, color, lw, ls):
    """Draw a zone's 10 deg edge only.  Along the night clip the zone ends exactly on the Sun 0 contour, so that stretch is left
    to the Sun line: a dashed line over it would read as a broken boundary.  The edge runs right up to the Sun line."""
    from scipy.interpolate import RegularGridInterpolator
    alt = RegularGridInterpolator((vis["glat"][:, 0], vis["glon"][0, :]), vis["alt_ref"], bounds_error=False, fill_value=None)
    for ring in contour_rings(vis["glon"], vis["glat"], vis[key]):
        keep = alt(ring[:, ::-1]) < -0.02
        p = ring.copy()
        p[~keep] = np.nan
        ax.plot(p[:, 0], p[:, 1], color=color, lw=lw, ls=ls, zorder=4)


def render_map(path, rows, sol, info, vis, t0, zones):
    sys.path.insert(0, os.path.expanduser("~/sda/starship-ITF-14/work"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import patheffects as pe
    from matplotlib.lines import Line2D
    from matplotlib.patches import Patch
    import ift14_style as st

    x0, x1, y0, y1 = 72.0, 112.0, -10.0, 49.0
    LONG = 13.2
    top_in, bot_in, side = 0.42, 0.62, 0.012
    H = LONG
    ax_h = H - top_in - bot_in
    ax_w = ax_h * (x1 - x0) / (y1 - y0) * 1.05         # a little wider than equal-degree: the map centres near 20 N
    W = ax_w / (1 - 2 * side)
    fig = plt.figure(figsize=(W, H), facecolor=st.BG)
    ax = fig.add_axes([side, bot_in / H, ax_w / W, ax_h / H])
    ax.set_facecolor("#05070a")
    for s in ax.spines.values():
        s.set_edgecolor("#2a323c")
    title = "CERES-2 Y3 Launch visibility"
    fig.text(side, 1 - 0.5 * top_in / H, title, color="#cfd6dd", fontsize=13, fontweight="bold", va="center", ha="left")
    fig.text(side + (0.112 * len(title) + 0.25) / W, 1 - 0.5 * top_in / H, t0.strftime("%Y-%m-%d %H:%M UTC"), color=st.FG, fontsize=12, va="center", ha="left")

    pg = info["pickup_geometric"]
    ref = t0 + timedelta(seconds=pg["t"] if pg else 0.0)
    st.draw_base(ax, (x0, x1, y0, y1), np.datetime64(ref.isoformat()), grat=10, night=False, sun=False, label_step=10)
    alt = vis["alt_ref"]
    shade = np.zeros(alt.shape + (4,))
    shade[..., 2] = 10 / 255
    shade[..., 3] = np.where(alt < -12, 0.48, np.where(alt < 0, 0.32, 0.0))
    ext = (vis["glon"].min(), vis["glon"].max(), vis["glat"].min(), vis["glat"].max())
    ax.imshow(shade, extent=ext, aspect="auto", origin="lower", zorder=1, interpolation="bilinear")
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.contour(vis["glon"], vis["glat"], alt, levels=[0], colors=[st.SUN], linewidths=1.5, linestyles="solid", zorder=3)
    ax.contour(vis["glon"], vis["glat"], alt, levels=[-12], colors=[st.ACCENT], linewidths=1.3, linestyles="solid", zorder=3)

    # zones: S4 (faint plume) under the solid-burn zone
    ax.contourf(vis["glon"], vis["glat"], vis["f_s4"], levels=[0.0, 1e3], colors=[(0.48, 0.85, 0.48, 0.07)], zorder=2)
    edge_line(ax, vis, "f_s4", color=(0.48, 0.85, 0.48, 0.8), lw=1.0, ls=(0, (2, 2)))
    ax.contourf(vis["glon"], vis["glat"], vis["f_solid"], levels=[0.0, 1e3], colors=[(1, 1, 1, 0.13)], zorder=2)
    edge_line(ax, vis, "f_solid", color=(1, 1, 1, 0.9), lw=1.3, ls=(0, (5, 3)))

    # NOTAM zones and falls
    for z in zones:
        ring = list(z["ring"]) + [z["ring"][0]]
        ax.fill([p[1] for p in ring], [p[0] for p in ring], color=(1, 82 / 255, 82 / 255, 0.28), zorder=5)
        ax.plot([p[1] for p in ring], [p[0] for p in ring], color=st.DANGER, lw=1.1, zorder=5)
    for name, f in sol["falls"].items():
        ax.plot([q[2] for q in f["rows"]], [q[1] for q in f["rows"]], color=st.DANGER, lw=0.8, alpha=0.75, ls=(0, (2, 2)), zorder=5)
        ax.plot(f["lon"], f["lat"], "x", ms=6, mew=1.5, color="#ffffff", zorder=9)

    # cities
    INSET = (0.012, 0.735, 0.285, 0.25)         # axes fraction, upper left, over the Tarim: outside the solid-burn zone
    in_inset = lambda la, lo: lo < x0 + (x1 - x0) * (INSET[0] + INSET[2]) + 0.8 and la > y0 + (y1 - y0) * INSET[1] - 0.8
    for name, la, lo in CITIES:
        if name not in MAP_CITIES or not (x0 + 0.5 < lo < x1 - 0.5 and y0 + 0.5 < la < y1 - 0.5) or in_inset(la, lo):
            continue
        ax.plot(lo, la, "o", ms=3.0, mfc="#d8dde3", mec=(0, 0, 0, 0.7), mew=0.6, zorder=6)
        ha, dx = ("right", -0.28) if name in ("Jiuquan", "Golmud", "Yushu", "Chamdo", "Mandalay", "Kolkata", "Kathmandu", "Shigatse", "Dhaka", "Dunhuang") else ("left", 0.28)
        st.label(ax, lo + dx, la + 0.08, name, color="#d8dde3", size=8, ha=ha)

    # trajectory
    for phase, colour, lw in (("S1", COL["S1"], 3.0), ("S2", COL["S2"], 3.0), ("S3", COL["S3"], 3.4), ("S4", COL["S4"], 2.2)):
        q = [r for r in rows if r["phase"] == phase]
        ax.plot([r["lon"] for r in q], [r["lat"] for r in q], color=colour, lw=lw, solid_capstyle="round", zorder=8,
                path_effects=[pe.withStroke(linewidth=lw + 2.0, foreground=(0, 0, 0, 0.55))])
    for phase in ("coast S2-S3", "coast S3-S4"):
        q = [r for r in rows if r["phase"] == phase]
        ax.plot([r["lon"] for r in q], [r["lat"] for r in q], color=COL["coast"], lw=1.3, ls=(0, (1.5, 2)), zorder=7)
    with open(HERE / f"{STEM}_orbit.csv") as fh:
        orb = [dict(lat=float(r["lat"]), lon=float(r["lon"]), t=float(r["t"])) for r in csv.DictReader(fh)]
    orb = [r for r in orb if r["t"] < rows[-1]["t"] + 330]
    ax.plot([r["lon"] for r in orb], [r["lat"] for r in orb], color=COL["coast"], lw=1.3, ls=(0, (1.5, 2)), zorder=7)
    st.star(ax, rows[0]["lon"], rows[0]["lat"], st.ACCENT, ms=13)
    st.label(ax, rows[0]["lon"] + 0.5, rows[0]["lat"] + 0.25, "Jiuquan 95A", color=st.ACCENT, size=9)
    if pg:
        ax.plot(pg["lon"], pg["lat"], "s", ms=6, mfc=st.OK, mec=(0, 0, 0, 0.8), mew=0.8, zorder=10)
    ev = {e["event"]: e for e in sol["events"]}
    for key, text, dx, dy, ha in (("S3 burnout", "S3 burnout", -0.45, 0.0, "right"), ("S4 cutoff, orbit", "S4 cutoff", 0.45, 0.0, "left")):
        e = ev[key]
        ax.plot(e["lon"], e["lat"], "o", ms=4, mfc=st.BG, mec="#ffffff", mew=1.0, zorder=9)
        st.label(ax, e["lon"] + dx, e["lat"] + dy, f"{text} T+{e['t']:.0f} s", color="#e8eaed", size=8, ha=ha)

    # launch-corridor inset: S1 and S2 climb nearly straight up over 100 km of ground, invisible at the main scale
    ia = ax.inset_axes(INSET)
    iext = (99.35, 100.95, 39.45, 41.25)
    im_base = st.earth_img()
    Ww, Hh = im_base.size
    c0, c1 = int((iext[0] + 180) / 360 * Ww), int(np.ceil((iext[1] + 180) / 360 * Ww))
    r0, r1 = int((90 - iext[3]) / 180 * Hh), int(np.ceil((90 - iext[2]) / 180 * Hh))
    ia.imshow(np.asarray(im_base.crop((c0, r0, c1, r1))), extent=[c0 / Ww * 360 - 180, c1 / Ww * 360 - 180, 90 - r1 / Hh * 180, 90 - r0 / Hh * 180], aspect="auto", interpolation="lanczos", zorder=0)
    ia.imshow(np.full((2, 2, 4), (0.0, 0.0, 10 / 255, 0.32)), extent=iext, aspect="auto", zorder=1)
    ia.set_xlim(iext[0], iext[1])
    ia.set_ylim(iext[2], iext[3])
    ia.set_xticks([])
    ia.set_yticks([])
    for sp in ia.spines.values():
        sp.set_edgecolor("#cfd6dd")
        sp.set_linewidth(0.8)
    ring = list(zones[0]["ring"]) + [zones[0]["ring"][0]]
    ia.fill([p[1] for p in ring], [p[0] for p in ring], color=(1, 82 / 255, 82 / 255, 0.28), zorder=2)
    ia.plot([p[1] for p in ring], [p[0] for p in ring], color=st.DANGER, lw=1.0, zorder=2)
    for phase, colour, lw in (("S1", COL["S1"], 2.6), ("S2", COL["S2"], 2.6), ("S3", COL["S3"], 3.0)):
        q = [r for r in rows if r["phase"] == phase]
        ia.plot([r["lon"] for r in q], [r["lat"] for r in q], color=colour, lw=lw, solid_capstyle="round", zorder=4,
                path_effects=[pe.withStroke(linewidth=lw + 1.8, foreground=(0, 0, 0, 0.55))])
    q = [r for r in rows if r["phase"] == "coast S2-S3"]
    ia.plot([r["lon"] for r in q], [r["lat"] for r in q], color=COL["coast"], lw=1.2, ls=(0, (1.5, 2)), zorder=4)
    f = sol["falls"]["S1"]
    ia.plot(f["lon"], f["lat"], "x", ms=6, mew=1.5, color="#ffffff", zorder=6)
    ia.plot(rows[0]["lon"], rows[0]["lat"], "*", ms=12, mfc=st.ACCENT, mec=(0, 0, 0, 0.8), mew=0.6, zorder=6)
    st.label(ia, rows[0]["lon"] + 0.05, rows[0]["lat"] + 0.075, "95A", color=st.ACCENT, size=8)
    tags = []
    if pg:
        ia.plot(pg["lon"], pg["lat"], "s", ms=5, mfc=st.OK, mec=(0, 0, 0, 0.8), mew=0.7, zorder=7)
        tags.append((pg["lon"], pg["lat"], f"Pickup T+{pg['t']:.0f} s · {pg['alt_km']:.0f} km", st.OK, 0.0))
    e1, e2, e3 = ev["S1 burnout"], ev["S2 burnout"], ev["S3 ignition"]
    tags += [(e1["lon"], e1["lat"], f"S1 off T+{e1['t']:.0f} s · {e1['h_km']:.0f} km", "#e8eaed", -0.03),
             (e2["lon"], e2["lat"], f"S2 off T+{e2['t']:.0f} s · {e2['h_km']:.0f} km", "#e8eaed", 0.0),
             (e3["lon"], e3["lat"], f"S3 on T+{e3['t']:.0f} s · {e3['h_km']:.0f} km", "#e8eaed", 0.0)]
    for lo, la, text, colour, dy in tags:
        if colour != st.OK:
            ia.plot(lo, la, "o", ms=3.8, mfc=st.BG, mec="#ffffff", mew=0.9, zorder=6)
        right = text.startswith(("S2", "S3"))        # the track runs to the lower left: these labels go to its east
        st.label(ia, lo + (0.05 if right else -0.05), la + dy, text, color=colour, size=7, ha="left" if right else "right")

    handles = [Line2D([], [], color=COL["S1"], lw=3, label="S1"), Line2D([], [], color=COL["S2"], lw=3, label="S2"), Line2D([], [], color=COL["S3"], lw=3, label="S3"),
               Line2D([], [], color=COL["S4"], lw=2.2, label="S4"), Line2D([], [], color=COL["coast"], lw=1.3, ls=(0, (1.5, 2)), label="Coast"),
               Line2D([], [], marker="s", ls="", ms=6, mfc=st.OK, mec="k", label="Sunlight pickup"),
               Patch(facecolor=(1, 1, 1, 0.14), edgecolor="white", ls=(0, (5, 3)), label="10° S1–S3"),
               Patch(facecolor=(0.48, 0.85, 0.48, 0.1), edgecolor=(0.48, 0.85, 0.48), ls=(0, (2, 2)), label="10° S4"),
               Line2D([], [], color=st.SUN, lw=1.5, label="Sun 0°"), Line2D([], [], color=st.ACCENT, lw=1.3, label="Sun −12°"),
               Patch(facecolor=(1, 82 / 255, 82 / 255, 0.3), edgecolor=st.DANGER, label="NOTAM"), Line2D([], [], marker="x", ls="", ms=6, mew=1.5, color="#ffffff", label="Impact")]
    fig.legend(handles=handles, loc="lower left", bbox_to_anchor=(side, 0.06 / H), ncol=6, frameon=False, fontsize=8.0, labelcolor=st.FG,
               handlelength=2.0, columnspacing=1.2, handletextpad=0.5, borderaxespad=0.0)
    fig.text(1 - side, 0.10 / H, "Illustration: Mickey · base map NASA Blue Marble", color=st.FGDIM, fontsize=7.5, ha="right", va="bottom")
    fig.savefig(path, dpi=300, facecolor=st.BG)
    plt.close(fig)
    return W, H


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default=None)
    a = ap.parse_args()
    sol = json.loads((HERE / f"{STEM}_solution.json").read_text())
    t0 = datetime.fromisoformat(a.t0 or sol["t0"])
    rows = load_rows()
    sun = Sun(t0.replace(hour=23, minute=18, second=0), t0.replace(hour=23, minute=28, second=0) + timedelta(hours=1))
    info = analyse(rows, t0, sun)
    pg, pr = info["pickup_geometric"], info["pickup_refracted"]
    vis = visibility(rows, t0, sun, pg["t"] if pg else 0.0)
    cities = city_table(rows, t0, sun)
    # along-track samples for the README
    along = [dict(t=q["t"], phase=q["phase"], lat=round(q["lat"], 2), lon=round(q["lon"], 2), h=round(q["alt_km"], 1), dep=round(q["dep"], 2), h_geo=round(q["h_geo"], 1), h_ref=round(q["h_ref"], 1), lit=q["lit"])
             for q in rows if q["t"] in (0, 30, 45, 50, 55, 60, 70, 80, 100, 120, 150, 175, 200, 225, 250, 275, 300, 400, 500, 600, 700, 800, 900, 1000) or q is rows[-1]]
    scan = t0_scan(rows, t0, sun)
    info = analyse(rows, t0, sun)          # the scan overwrote the row fields; restore this T0
    jelly_above = [q for q in rows if q["lit"] and stage_of(q) in ("S1", "S2", "S3") and q["alt_km"] >= 60.0]
    out = dict(t0=t0.isoformat(), reference_epoch=(t0 + timedelta(seconds=pg["t"] if pg else 0.0)).isoformat(timespec="seconds"),
               pad_sun_deg=round(float(sun_el(rows[0]["lat"], rows[0]["lon"], sun.at(t0))), 2),
               pickup_geometric=pg, pickup_refracted=pr, clear_sunlight=info["clear_sunlight"], by_stage=info["by_stage"],
               solid_sunlit_above_60km=dict(t_start=jelly_above[0]["t"], t_end=jelly_above[-1]["t"]) if jelly_above else None,
               zones_km2=dict(solid=round(zone_area(vis["mask_solid"], vis["glat"], vis["step"], vis["step"])), s4_only=round(zone_area(vis["mask_s4"] & ~vis["mask_solid"], vis["glat"], vis["step"], vis["step"])),
                              prime=round(zone_area(vis["mask_prime"], vis["glat"], vis["step"], vis["step"]))),
               extent_solid=dict(lat=[round(float(vis["glat"][vis["mask_solid"]].min()), 1), round(float(vis["glat"][vis["mask_solid"]].max()), 1)],
                                 lon=[round(float(vis["glon"][vis["mask_solid"]].min()), 1), round(float(vis["glon"][vis["mask_solid"]].max()), 1)]),
               cities=cities, along_track=along, t0_scan=scan, min_elev_deg=MIN_ELEV)
    (HERE / f"{STEM}_jelly.json").write_text(json.dumps(out, indent=1, default=float, ensure_ascii=False))
    write_kml(str(HERE / f"{STEM}_jelly.kml"), rows, info, vis, t0)
    W, H = render_map(HERE / f"{STEM}_jelly.png", rows, sol, info, vis, t0, sol["zones"])

    print(f"pad Sun {out['pad_sun_deg']} deg; map {W * 300:.0f} x {H * 300:.0f} px")
    print(f"pickup geometric T+{pg['t']:.1f} s at {pg['alt_km']:.1f} km ({pg['lat']:.2f},{pg['lon']:.2f}) dep {pg['dep']:.2f}; refracted T+{pr['t']:.1f} s at {pr['alt_km']:.1f} km; clear sunlight {info['clear_sunlight']}")
    for st_, d in info["by_stage"].items():
        print(f"  {st_}: T+{d['t_start']:.0f}-{d['t_end']:.0f} lit {d['lit_s']:.0f} of {d['burn_s']:.0f} s, h {d['h_start']:.0f}-{d['h_end']:.0f} km, dep {d['dep_start']:.2f}->{d['dep_end']:.2f}")
    print("zones km2", out["zones_km2"], "solid extent", out["extent_solid"], "above 60 km", out["solid_sunlit_above_60km"])
    print(f"{'city':14s} solid: el  stage  T+   az  sun | S4: el  sun")
    for c in cities:
        s, f = c["solid"], c["s4"]
        print(f"{c['name']:14s} {s['el']:6.1f} {s['stage']:3s} {s['t']:6.0f} {s['az']:4.0f} {s['sun']:6.1f} | {f['el']:6.1f} {f['sun']:6.1f}")
    print("T0 scan:")
    for q in scan:
        print(" ", q)


if __name__ == "__main__":
    main()
