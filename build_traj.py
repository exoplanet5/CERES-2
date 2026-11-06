#!/usr/bin/env python3
"""CERES-2 Y3 ascent: calibrate the vehicle, fit the NOTAM zones, fly to the orbit, write the products.

The mission flies the published 500 km SSO capability, 1.3 t at 100 t lift-off, with S4 climbing directly to the orbit in one
burn.  Stage loads keep the CERES-1 proportions.  One efficiency level f is solved so the budget closes: f = 0 is CERES-1 Isp
and structure, f = 1 an optimistic reference with the "295 s" propellant and lighter cases.

Run: ~/.venvs/astro313/bin/python build_traj.py [--t0 2026-11-06T23:38:00] [--payload 1300] [--alt 500] [--sens]
Writes CERES-2_Y3_{solution.json, traj.csv, orbit.csv, traj.kml, prelaunch.tle}.
"""
import argparse
import csv
import json
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import simplekml

import ceres2 as C

HERE = Path(__file__).resolve().parent
STEM = "CERES-2_Y3"
NOTAM = HERE / "notam_ceres-2_Y3"
PAD = C.PAD_95A
T0_DEFAULT = "2026-11-06T23:38:00"
CAPABILITY = 1300.0        # kg, published 500 km SSO
TOTAL = 100000.0           # kg, published lift-off
A2, B3 = 0.6, -0.3         # S2 pitch offset and S3 pitch rate: S4 propellant is nearly flat around these

# CERES-1 motor loads (validate_precedents.py) x 3.03 is the 100 t split; k scales them to close the lift-off mass.
BASE = dict(s1=54400.0, s2=22300.0, s3=11100.0)
S4_LOAD = 1200.0           # kg, assumed; a direct climb cannot close on 1000 kg at any efficiency level or S3 aim in the zone
S3_BURN = 120.0            # s, as Vega's Zefiro 9, which has almost the same propellant load
S3_AIM = 5450.0            # km, the farthest nominal that keeps CERES-1's +/-150 km zone half-length inside the 5611 km far edge


def vehicle(k=1.0, f=0.0, s4_prop=S4_LOAD, t1=80.0, t2=75.0, t3=S3_BURN, s4_thrust=4850.0, **kw):
    s1, s2, s3 = BASE["s1"] * k, BASE["s2"] * k, BASE["s3"] * k
    return C.Vehicle("CERES-2", C.Motor(s1, s1 * (0.085 - 0.010 * f), 276.0 + 4.0 * f, t1, 249.5 + 2.5 * f),
                     C.Motor(s2, s2 * (0.080 - 0.010 * f), 290.0 + 5.0 * f, t2), C.Motor(s3, s3 * (0.095 - 0.015 * f), 295.0 + 3.0 * f, t3),
                     s4_prop=s4_prop, s4_dry=400.0 - 50.0 * f, s4_thrust=s4_thrust, s4_isp=310.0, fairing=800.0 - 100.0 * f, diameter=2.9, **kw)


def closed_vehicle(f, **kw):
    """k so that a 1.3 t payload gives TOTAL at lift-off."""
    v = vehicle(k=1.0, f=f, **kw)
    upper = v.s4_prop + v.s4_dry + v.fairing + CAPABILITY
    return vehicle(k=(TOTAL - upper) / (v.m0(CAPABILITY) - upper), f=f, **kw)


def load_zones():
    z = C.parse_notams(NOTAM)
    named = dict(s1=z[0], s2=z[1], s3a=z[2], s3b=z[3])
    # S3 zone A0582 + E4059 runs along one corridor: fit its centreline and aim on it.
    ranges = [C.gc_dist(PAD, p) for p in z[2]["ring"] + z[3]["ring"]]
    s_end = np.mean(z[3]["ring"][:2], axis=0)          # far edge, E4059
    n_end = np.mean(z[2]["ring"][:2], axis=0)          # near edge, A0582
    az = C.bearing(tuple(n_end), tuple(s_end))
    p3 = C.dest(tuple(n_end), az, S3_AIM - C.gc_dist(PAD, tuple(n_end)))
    return named, dict(p1=C.centroid(z[0]["ring"]), p2=C.centroid(z[1]["ring"]), p3=p3, s3_aim=S3_AIM,
                       s3_near=min(ranges), s3_far=max(ranges), s3_axis=(tuple(n_end), tuple(s_end)))


def fly(frame, veh, payload, targets, inc, alt, a2=A2, b3=B3):
    s1 = C.fit_s1(frame, veh, PAD, payload, targets["p1"])
    s2 = C.fit_s2(frame, veh, s1, payload, inc, PAD, targets["p2"], a2)
    s3 = C.fit_s3(frame, veh, s2, payload, inc, PAD, targets["p3"], b3)
    s4 = C.fit_s4(frame, veh, s3, payload, inc, alt)
    if s2["fit_cost"] > 1e-3 or s3["fit_cost"] > 1e-3 or s4["cost"] > 1e-3:
        raise RuntimeError(f"targeting did not converge: S2 {s2['fit_cost']:.1e} S3 {s3['fit_cost']:.1e} S4 {s4['cost']:.1e}")
    return dict(s1=s1, s2=s2, s3=s3, s4=s4, s4_used=s4["prop_used"])


def calibrate(frame, targets, inc, alt, **kw):
    """Efficiency level f closing 1.3 t at TOTAL lift-off with the S4 load and 1 % of it left."""
    def margin(f):
        veh = closed_vehicle(f, **kw)
        run = fly(frame, veh, CAPABILITY, targets, inc, alt)
        return veh.s4_prop * 0.99 - run["s4_used"]

    lo, hi = -0.5, 1.5
    mlo, mhi = margin(lo), margin(hi)
    hist = [(lo, mlo), (hi, mhi)]
    if mlo * mhi > 0:
        raise RuntimeError(f"efficiency level cannot close the budget: margins {mlo:.0f}, {mhi:.0f} kg")
    for _ in range(12):
        f = lo + (hi - lo) * mlo / (mlo - mhi)
        mf = margin(f)
        hist.append((f, mf))
        if abs(mf) < 3.0:
            break
        if mlo * mf < 0:
            hi, mhi = f, mf
        else:
            lo, mlo = f, mf
    return closed_vehicle(f, **kw), float(f), hist


# ---------------------------------------------------------------- sampling and products
def sample(frame, sol, t_end_orbit=None):
    """1 s rows lift-off -> S4 cutoff, 5 s rows on orbit."""
    s1, s2, s3, s4 = sol["s1"], sol["s2"], sol["s3"], sol["s4"]
    t_sep = s2["t_ign"]
    drift = C.coast(s1["arc"].r_end, s1["arc"].v_end, s1["arc"].t_end, t_sep, dt=0.25)
    pieces = [(0.0, s1["t_b"], s1["arc"], "S1"), (s1["t_b"], t_sep, drift, "S1-S2 staging"), (t_sep, s2["t_b"], s2["arc"], "S2"),
              (s2["t_b"], s3["t_ign"], s3["arc"], "coast S2-S3"), (s3["t_ign"], s3["t_b"], s3["arc"], "S3"),
              (s3["t_b"], s4["t_ign"], s4["arc"], "coast S3-S4"), (s4["t_ign"], s4["t_b"], s4["arc"], "S4")]
    t_cut = s4["t_b"]
    ts = np.unique(np.r_[np.arange(0.0, t_cut, 1.0), [p[1] for p in pieces]])
    rows = []
    for t in ts:
        piece = next(p for p in pieces if t <= p[1] + 1e-9)
        y = piece[2](float(np.clip(t, piece[2].T[0], piece[2].T[-1])))
        rows.append(row(frame, t, y[:3], y[3:], piece[3]))
    return rows, t_cut


def row(frame, t, r, v, phase):
    re, ve = frame.to_ecef(r, t, v)
    lat, lon, h = C.ecef_to_geodetic(re)
    vn = np.linalg.norm(ve)
    rn = np.linalg.norm(re)
    fpa = float(np.degrees(np.arcsin(np.clip(re @ ve / (rn * vn), -1, 1)))) if vn > 1e-6 else 90.0
    return dict(t=float(t), utc=frame.utc(t).isoformat(timespec="milliseconds"), phase=phase, lat=float(lat), lon=float(lon),
                alt_km=float(h), x=float(re[0]), y=float(re[1]), z=float(re[2]), v_inertial=float(np.linalg.norm(v)), v_rel=float(vn),
                fpa=fpa, downrange_km=float(C.gc_dist(PAD, (lat, lon))))


def fall_rows(frame, f, dt=5.0):
    arc = f["arc"]
    ts = np.r_[np.arange(arc.T[0], arc.T[-1], dt), arc.T[-1]]
    out = []
    for t in ts:
        y = arc(float(t))
        lat, lon, h = frame.lla(y[:3], t)
        out.append([round(float(t), 2), round(float(lat), 4), round(float(lon), 4), round(float(max(h, 0.0)), 2)])
    return out


def ltan_of(frame, raan, t):
    """Local solar time of the descending and ascending nodes, mean Sun (J2000 mean longitude)."""
    jd = frame.jd0 + t / 86400.0
    d = jd - 2451545.0
    mean_sun_ra = (280.46 + 0.9856474 * d) % 360
    ltan = ((raan - mean_sun_ra) / 15.0 + 12.0) % 24.0
    return ltan, (ltan + 12.0) % 24.0


def events_of(frame, sol, veh, payload):
    s1, s2, s3, s4 = sol["s1"], sol["s2"], sol["s3"], sol["s4"]
    q, t_q = C.max_q(s1["arc"])

    def state(t, arc, label, **kw):
        y = arc(float(np.clip(t, arc.T[0], arc.T[-1])))
        lat, lon, h = frame.lla(y[:3], t)
        vr = np.linalg.norm(C.v_rel(y[:3], y[3:6]))
        return dict(event=label, t=round(float(t), 2), lat=round(float(lat), 3), lon=round(float(lon), 3), h_km=round(float(h), 2),
                    v_rel_kms=round(float(vr), 4), v_inertial_kms=round(float(np.linalg.norm(y[3:6])), 4), **kw)

    return [state(0.0, s1["arc"], "Liftoff"),
            state(t_q, s1["arc"], "Max-Q", q_kpa=round(q / 1e3, 1)),
            state(s1["t_b"], s1["arc"], "S1 burnout"),
            state(s2["t_ign"], s2["arc"], "S1 separation, S2 ignition"),
            state(s2["t_b"], s2["arc"], "S2 burnout"),
            state(s3["t_fair"], s3["arc"], "Fairing jettison", heat_w_m2=round(float(C.heat_flux(*(lambda y: (y[:3], y[3:6]))(s3["arc"](s3["t_fair"])))), 1)),
            state(s3["t_ign"], s3["arc"], "S3 ignition"),
            state(s3["t_b"], s3["arc"], "S3 burnout"),
            state(s4["t_ign"], s4["arc"], "S4 ignition"),
            state(s4["t_b"], s4["arc"], "S4 cutoff, orbit")]


def write_csv(path, rows):
    keys = list(rows[0])
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        for q in rows:
            w.writerow({k: (f"{q[k]:.6f}" if isinstance(q[k], float) else q[k]) for k in keys})


def write_kml(path, rows, orbit, falls, zones, events, t0):
    kml = simplekml.Kml(name=f"CERES-2 Y3 model, T0 {t0} UTC")
    col = {"S1": "ff2659d9", "S1-S2 staging": "ff2659d9", "S2": "ff37a4e8", "coast S2-S3": "ff9fb7c8", "S3": "ff4fd5ff",
           "coast S3-S4": "ff9fb7c8", "S4": "ff7fe0a0"}
    fold = kml.newfolder(name="Ascent (3-D)")
    run, phase = [], rows[0]["phase"]
    for q in rows + [None]:
        if q is None or q["phase"] != phase:
            ls = fold.newlinestring(name=phase, coords=run)
            ls.altitudemode = simplekml.AltitudeMode.absolute
            ls.style.linestyle.color = col[phase]
            ls.style.linestyle.width = 3
            if q is None:
                break
            run, phase = run[-1:], q["phase"]
        run.append((q["lon"], q["lat"], q["alt_km"] * 1e3))
    gt = kml.newfolder(name="Ground track").newlinestring(name="Ascent ground track", coords=[(q["lon"], q["lat"], 0) for q in rows])
    gt.tessellate = 1
    gt.style.linestyle.color = "aaffffff"
    orb = kml.newfolder(name="Orbit")
    runs, cur = [], []
    for a, b in zip(orbit[:-1], orbit[1:]):
        cur.append((a["lon"], a["lat"], a["alt_km"] * 1e3))
        if abs(a["lon"] - b["lon"]) > 180:
            runs.append(cur)
            cur = []
    runs.append(cur)
    for r in runs:
        if len(r) > 1:
            ls = orb.newlinestring(name="Orbit", coords=r)
            ls.altitudemode = simplekml.AltitudeMode.absolute
            ls.style.linestyle.color = "ffff7dc7"
    ff = kml.newfolder(name="Stage falls")
    for name, data in falls.items():
        ls = ff.newlinestring(name=f"{name} fall", coords=[(q[2], q[1], q[3] * 1e3) for q in data["rows"]])
        ls.altitudemode = simplekml.AltitudeMode.absolute
        ls.style.linestyle.color = "ff5252ff"
        pm = ff.newpoint(name=f"{name} impact T+{data['t']:.0f}s", coords=[(data["lon"], data["lat"])])
        pm.style.labelstyle.scale = 0.8
    zf = kml.newfolder(name="NOTAM zones")
    for z in zones:
        ring = [(lo, la) for la, lo in z["ring"]]
        p = zf.newpolygon(name=f"{z['id']} {z['t0']}-{z['t1']}", outerboundaryis=ring + ring[:1])
        p.style.polystyle.color = "33ededed"
        p.style.linestyle.color = "ffededed"
    ef = kml.newfolder(name="Events")
    for e in events:
        ef.newpoint(name=f"{e['event']} T+{e['t']:.0f}s", coords=[(e["lon"], e["lat"], e["h_km"] * 1e3)]).altitudemode = simplekml.AltitudeMode.absolute
    kml.save(path)


def sensitivity(frame, targets, inc, alt, payload):
    """Recalibrate and refit one assumption at a time, with the jelly numbers each case gives at this T0."""
    import jelly_ceres2 as J
    t0 = frame.t0
    sun = J.Sun(t0 - timedelta(minutes=20), t0 + timedelta(minutes=40))
    cases = [("nominal", {}, {}),
             ("S1 burn 72 s", dict(t1=72.0), {}), ("S1 burn 88 s", dict(t1=88.0), {}),
             ("S2 burn 68 s", dict(t2=68.0), {}), ("S2 burn 82 s", dict(t2=82.0), {}),
             ("S3 burn 75 s", dict(t3=75.0), {}), ("S3 burn 100 s", dict(t3=100.0), {}), ("S3 burn 140 s", dict(t3=140.0), {}),
             ("S1 impact 90 km", {}, dict(p1=C.dest(PAD, 189.4, 90.0))), ("S1 impact 145 km", {}, dict(p1=C.dest(PAD, 189.4, 145.0))),
             ("S3 aim 5091 km", {}, dict(p3=C.dest(PAD, 194.5, 5091.0))), ("S3 aim 5300 km", {}, dict(p3=C.dest(PAD, 194.5, 5300.0))), ("S3 aim 5600 km", {}, dict(p3=C.dest(PAD, 194.5, 5600.0))),
             ("S4 thrust 3.5 kN", dict(s4_thrust=3500.0), {}), ("S4 thrust 7 kN", dict(s4_thrust=7000.0), {})]
    out = []
    for name, vk, tk in cases:
        tg = {**targets, **tk}
        try:
            veh, f, _ = calibrate(frame, tg, inc, alt, **vk)
            run = fly(frame, veh, payload, tg, inc, alt)
        except (RuntimeError, ValueError) as err:
            out.append(dict(case=name, failed=str(err)[:90]))
            continue
        st = {k: C.state_of(frame, run[k]["arc"]) for k in ("s1", "s2", "s3", "s4")}
        rows, _ = sample(frame, run)
        for q in rows:
            q["p"] = np.array([q["x"], q["y"], q["z"]])
        info = J.analyse(rows, t0, sun)
        pg = info["pickup_geometric"]
        high = [q for q in rows if q["lit"] and q["phase"] in ("S1", "S2", "S3") and q["alt_km"] >= 60.0]
        cities = {c["name"]: c["solid"] for c in J.city_table(rows, t0, sun)}
        out.append(dict(case=name, f=round(f, 3), s1_t=round(st["s1"]["t"], 1), s1_h=round(st["s1"]["h"], 1), s1_v=round(st["s1"]["v_rel"] * 1e3),
                        s2_t=round(st["s2"]["t"], 1), s2_h=round(st["s2"]["h"], 1), s3_t=round(st["s3"]["t"], 1), s3_h=round(st["s3"]["h"], 1),
                        s3_v=round(st["s3"]["v_inertial"], 3), s3_i=round(st["s3"]["el"]["i"], 2), s4_burn=round(run["s4"]["x"][4] * 100, 1), t_cut=round(st["s4"]["t"], 1),
                        pickup_t=round(pg["t"], 1), pickup_h=round(pg["alt_km"], 1), clear_t=info["clear_sunlight"]["t"], high_from=high[0]["t"], high_s=round(high[-1]["t"] - high[0]["t"], 1),
                        golmud=cities["Golmud"]["el"], dunhuang=cities["Dunhuang"]["el"], hami=cities["Hami"]["el"], nagqu=cities["Nagqu"]["el"]))
        print(" ", out[-1], flush=True)
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--t0", default=T0_DEFAULT)
    ap.add_argument("--payload", type=float, default=CAPABILITY)
    ap.add_argument("--alt", type=float, default=500.0)
    ap.add_argument("--sens", action="store_true", help="also refit each assumption (several minutes)")
    a = ap.parse_args()
    t0 = datetime.fromisoformat(a.t0)
    frame = C.Frame(t0)
    inc = C.sso_inclination(a.alt)
    zones, targets = load_zones()
    zlist = [zones[k] for k in ("s1", "s2", "s3a", "s3b")]

    # "500 km" is the orbit-mean altitude: the osculating radius at cutoff differs from it (J2), so correct the aim
    def orbit_mean(run):
        arc = run["s4"]["arc"]
        period = C.elements(arc.r_end, arc.v_end)["period"]
        y = C.coast(arc.r_end, arc.v_end, arc.t_end, arc.t_end + period, dt=5.0).Y
        return float(np.mean(np.linalg.norm(y[:, :3], axis=1))) - C.RE

    def settle(veh, alt_cmd):
        for _ in range(5):
            mean = orbit_mean(fly(frame, veh, a.payload, targets, inc, alt_cmd))
            if abs(mean - a.alt) < 0.1:
                break
            alt_cmd += a.alt - mean
        return alt_cmd

    veh, level, hist = calibrate(frame, targets, inc, a.alt)
    alt_cmd = settle(veh, a.alt)
    veh, level, hist = calibrate(frame, targets, inc, alt_cmd)      # the budget closes at the final aim
    alt_cmd = settle(veh, alt_cmd)
    mean_alt = orbit_mean(fly(frame, veh, a.payload, targets, inc, alt_cmd))
    print(f"aim: cutoff at {alt_cmd:.1f} km for a mean altitude of {mean_alt:.1f} km")
    cap = fly(frame, veh, CAPABILITY, targets, inc, alt_cmd)
    print(f"calibration: level f {level:.3f}  k {veh.s1.prop / BASE['s1']:.4f}  m0 {veh.m0(CAPABILITY) / 1e3:.2f} t  S4 used {cap['s4_used']:.0f} of {veh.s4_prop:.0f} kg")

    sol = fly(frame, veh, a.payload, targets, inc, alt_cmd)
    s1, s2, s3, s4 = sol["s1"], sol["s2"], sol["s3"], sol["s4"]
    rows, t_cut = sample(frame, sol)

    # the orbit starts at S4 cutoff: there is no coast and no second burn
    r_c, v_c = s4["arc"].r_end, s4["arc"].v_end
    el = C.elements(r_c, v_c)
    orbit_revs = 1.5
    t_end = t_cut + el["period"] * orbit_revs
    orbit_arc = C.coast(r_c, v_c, t_cut, t_end, dt=2.0)
    orbit = []
    for t in np.r_[np.arange(t_cut, t_end, 5.0), t_end]:
        y = orbit_arc(float(t))
        orbit.append(row(frame, float(t), y[:3], y[3:], "orbit"))

    # falls
    fair = C.stage_fall(frame, s3["fair_state"], s3["t_fair"], veh.beta_fair, C.H_PLATEAU)
    falls = dict(S1=s1["fall"], S2=s2["fall"], Fairing=fair, S3=s3["fall"])
    falls_out = {}
    z_of = dict(S1=[zones["s1"]], S2=[zones["s2"]], Fairing=[zones["s2"]], S3=[zones["s3a"], zones["s3b"]])
    for name, f in falls.items():
        d = dict(t=round(f["t"], 1), lat=round(f["lat"], 3), lon=round(f["lon"], 3), range_km=round(C.gc_dist(PAD, (f["lat"], f["lon"])), 1),
                 inside=[z["id"] for z in z_of[name] if C.point_in_ring(f["lat"], f["lon"], z["ring"])], rows=fall_rows(frame, f))
        falls_out[name] = d

    events = events_of(frame, sol, veh, a.payload)
    tle, tle_rms, tle_max = C.fit_tle(frame, orbit_arc, t_cut, t_end, 0, "", "CERES-2 Y3 PRELAUNCH MODEL - NOT OBSERVED")
    ltan, ltdn = ltan_of(frame, el["raan"], t_cut)
    budget = dict(s1_prop=veh.s1.prop, s1_dry=veh.s1.dry, s2_prop=veh.s2.prop, s2_dry=veh.s2.dry, s3_prop=veh.s3.prop, s3_dry=veh.s3.dry,
                  s4_prop=veh.s4_prop, s4_dry=veh.s4_dry, s4_thrust=veh.s4_thrust, s4_isp=veh.s4_isp, s4_used=sol["s4_used"], fairing=veh.fairing, capability=CAPABILITY, payload=a.payload,
                  level=level, isp=[veh.s1.isp_sl, veh.s1.isp_vac, veh.s2.isp_vac, veh.s3.isp_vac], k=veh.s1.prop / BASE["s1"],
                  m0_capability=veh.m0(CAPABILITY), m0_mission=veh.m0(a.payload), t_burn=[veh.s1.t_burn, veh.s2.t_burn, veh.s3.t_burn, float(s4["x"][4] * 100)],
                  s1_thrust_sl_kN=veh.s1.prop * veh.s1.isp_sl * C.G0 / veh.s1.t_burn / 1e3, s1_thrust_vac_kN=veh.s1.f_mean / 1e3,
                  s2_thrust_kN=veh.s2.f_mean / 1e3, s3_thrust_kN=veh.s3.f_mean / 1e3, liftoff_tw=veh.s1.prop * veh.s1.isp_sl * C.G0 / veh.s1.t_burn / (veh.m0(a.payload) * C.G0))
    qa = C.s2_q_alpha(frame, s2)
    states = {k: C.state_of(frame, sol[k]["arc"]) for k in ("s1", "s2", "s3", "s4")}
    for st in states.values():
        st["el"] = {k: (float(v) if np.isscalar(v) else None) for k, v in st["el"].items() if k != "hhat"}
    solution = dict(t0=a.t0, pad=dict(lat=PAD[0], lon=PAD[1], h=C.PAD_H, name="Jiuquan 95A"), target=dict(alt=a.alt, inc=inc), budget=budget,
                    steering=dict(az=s1["az"], kick=s1["kick"], s2=dict(a2=s2["a2"], b2=s2["b2"], c2=s2["c2"], tan0=s2["tan0"]),
                                  s3=[float(x) for x in s3["x"]], s4=[float(x) for x in s4["x"]], q_alpha=dict(peak_kPa_deg=qa[0] / 1e3, q_kPa=qa[1] / 1e3, alpha_deg=qa[2], t=qa[3])),
                    targets=dict(p1=targets["p1"], p2=targets["p2"], p3=targets["p3"], s3_near=targets["s3_near"], s3_far=targets["s3_far"], s3_aim=targets["s3_aim"]),
                    zones=[dict(id=z["id"], fir=z["fir"], t0=z["t0"], t1=z["t1"], ring=z["ring"], centroid=C.centroid(z["ring"])) for z in zlist],
                    events=events, falls=falls_out, states=states, capability_run=dict(s4_used=cap["s4_used"], s4_burn=float(cap["s4"]["x"][4] * 100), t_cut=float(cap["s4"]["t_b"])),
                    orbit=dict(hp=float(el["hp"]), ha=float(el["ha"]), i=float(el["i"]), raan=float(el["raan"]), period=float(el["period"]), t_cut=float(t_cut), t_end=float(t_end),
                               alt_cmd=float(alt_cmd), mean_alt=float(mean_alt), revolutions=orbit_revs, ltan_h=ltan, ltdn_h=ltdn,
                               raan_rate_deg_per_min=360.98564736629 / 1440.0, raan_through_s4=s4["raan_through"]),
                    tle=dict(lines=tle, rms_km=tle_rms, max_km=tle_max), calibration=[list(map(float, h)) for h in hist])
    if a.sens:
        solution["sensitivity"] = sensitivity(frame, targets, inc, alt_cmd, a.payload)
    (HERE / f"{STEM}_solution.json").write_text(json.dumps(solution, indent=1, default=float))
    write_csv(HERE / f"{STEM}_traj.csv", rows)
    write_csv(HERE / f"{STEM}_orbit.csv", orbit)
    (HERE / f"{STEM}_prelaunch.tle").write_text("\n".join(tle) + "\n")
    write_kml(str(HERE / f"{STEM}_traj.kml"), rows, orbit, falls_out, zlist, events, a.t0)

    print(f"vehicle: S1 {veh.s1.prop / 1e3:.1f}+{veh.s1.dry / 1e3:.1f} t, S2 {veh.s2.prop / 1e3:.1f}+{veh.s2.dry / 1e3:.1f} t, S3 {veh.s3.prop / 1e3:.1f}+{veh.s3.dry / 1e3:.1f} t, "
          f"S4 {veh.s4_prop:.0f}+{veh.s4_dry:.0f} kg (used {sol['s4_used']:.0f}), fairing {veh.fairing:.0f} kg; T/W {budget['liftoff_tw']:.2f}; Isp {budget['isp']}")
    print(f"steering: az {s1['az']:.2f}, kick {s1['kick']:.2f}, S2 a {s2['a2']:.2f} b {s2['b2']:.2f} c {s2['c2']:.3f}, S2 q*alpha peak {qa[0] / 1e3:.1f} kPa deg")
    for e in events:
        print(f"  T+{e['t']:7.1f}  {e['event']:30s} {e['lat']:7.2f} {e['lon']:7.2f}  h {e['h_km']:7.1f}  v {e['v_rel_kms']:.3f} / {e['v_inertial_kms']:.3f}")
    for n, d in falls_out.items():
        print(f"  {n:8s} impact T+{d['t']:6.0f} {d['lat']:7.2f} {d['lon']:7.2f} range {d['range_km']:7.1f} km  inside {d['inside']}")
    print(f"orbit: {el['hp']:.1f} x {el['ha']:.1f} km, i {el['i']:.3f}, RAAN {el['raan']:.2f} (through S4 point {s4['raan_through']:.2f}), LTDN {ltdn:.2f} h, period {el['period']:.1f} s; TLE rms {tle_rms:.2f} km, max {tle_max:.2f}")
    print("\n".join(tle))
    if a.sens:
        for q in solution["sensitivity"]:
            print(q)


if __name__ == "__main__":
    main()
