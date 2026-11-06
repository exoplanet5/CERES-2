#!/usr/bin/env python3
"""Fly the CERES-2 model family on the flown siblings, using only their public motor figures.

CERES-1 (Galactic Energy's own 3-solid + liquid vehicle) is the closest check: published thrust, burn and Isp give the
motor loads, and the model must then reach 500 km SSO with 300 kg on about the 300 kg AVCS load, dropping S1 and S3 in the
real zones.  Propellant use barely depends on the assumed S4 thrust; the S4 burn time does (1.6 kN is chosen from the 510 s
Y19 report, so the burn time is not an independent check).  ZK-1A shares the steep solid S1 but has a solid S4; it checks that S1 and S2 fit its zones and that the
SSO mass budget closes.

Run: ~/.venvs/astro313/bin/python validate_precedents.py       Writes validation.json
"""
import json
from datetime import datetime
from pathlib import Path

import numpy as np

import ceres2 as C

HERE = Path(__file__).resolve().parent
FRAME = C.Frame(datetime(2026, 11, 6, 23, 38, 0))


def motor(thrust, burn, isp, eps, isp_sl=0.0):
    """Motor load from published thrust (sea-level when isp_sl is given), burn time and Isp."""
    prop = thrust * burn / ((isp_sl or isp) * C.G0)
    return C.Motor(prop=prop, dry=prop * eps, isp_vac=isp, t_burn=burn, isp_sl=isp_sl)


# GS-1 60-65 t / 73.9 s / 249.5 s SL; GS-2 30 t / 70 s / 285.8 s; GS-3 15 t / 70 s / 287 s (Baike, zh-Wikipedia, GCAT).
# S3 mass ratio 0.926 (published), so eps ~ 0.08 for the motor; separation hardware added.
CERES1 = C.Vehicle("CERES-1", motor(600e3, 73.9, 276.0, 0.085, 249.5), motor(294e3, 70.0, 285.8, 0.08),
                   motor(147e3, 70.0, 287.0, 0.095), s4_prop=300.0, s4_dry=180.0, s4_thrust=1600.0, s4_isp=310.0,
                   fairing=180.0, diameter=1.6, t_rise=6.0)
# Propellant and peak thrust are public (70.74 t / 2067 kN, 35 t / 1081 kN, 10 t / 439 kN, 1.99 t / 78 kN); the burn times
# follow from those at a mean of about 90 % of peak, and the structure closes the 135 t lift-off mass.
ZK1A = C.Vehicle("ZK-1A", C.Motor(70740, 6200, 278.0, 92.0, 250.0), C.Motor(35000, 3000, 285.0, 85.0),
                 C.Motor(10000, 1000, 288.0, 68.0), s4_prop=1990.0, s4_dry=300.0, s4_thrust=78000.0, s4_isp=290.0,
                 fairing=1100.0, diameter=2.65, t_rise=8.0, dt_c34=420.0)


def impulsive_budget(veh, payload, st3, inc, h_orbit):
    """Solid S4: delta-v from S3 apogee to the circular target orbit with the plane change, against what the load gives."""
    el = st3["el"]
    ra = el["ra"]
    v_a = np.sqrt(C.MU * (2 / ra - 1 / el["a"]))
    v_t = np.sqrt(C.MU / (C.RE + h_orbit))
    di = np.radians(abs(inc - el["i"]))
    need = np.sqrt(v_a ** 2 + v_t ** 2 - 2 * v_a * v_t * np.cos(di)) * 1e3
    m0 = veh.m_s4(payload)
    have = veh.s4_isp * C.G0 * np.log(m0 / (m0 - veh.s4_prop))
    return dict(s3_apogee_km=round(el["ha"], 1), plane_change_deg=round(np.degrees(di), 2), dv_need=round(need), dv_have=round(have))


def fly(veh, payload, pad, p1, p2, p3, h_orbit, a2=0.6, b3=-0.3, solid_s4=False):
    inc = C.sso_inclination(h_orbit)
    s1 = C.fit_s1(FRAME, veh, pad, payload, p1)
    s2 = C.fit_s2(FRAME, veh, s1, payload, inc, pad, p2, a2)
    s3 = C.fit_s3(FRAME, veh, s2, payload, inc, pad, p3, b3)
    st1, st2, st3 = (C.state_of(FRAME, s["arc"]) for s in (s1, s2, s3))
    if solid_s4:
        s4_out = impulsive_budget(veh, payload, st3, inc, h_orbit)
    else:
        s4 = C.fit_s4(FRAME, veh, s3, payload, inc, h_orbit)
        s4_out = dict(burn_s=round(s4["x"][4] * 100, 1), prop_used_kg=round(s4["prop_used"]), load_kg=round(veh.s4_prop), cost=s4["cost"])
    return dict(vehicle=veh.name, m0_t=round(veh.m0(payload) / 1e3, 2), payload_kg=payload,
                s1=dict(az=round(s1["az"], 2), kick=round(s1["kick"], 2), t=round(st1["t"], 1), h=round(st1["h"], 1),
                        v=round(st1["v_rel"] * 1e3), fpa=round(st1["fpa_rel"], 1),
                        impact_km=round(C.gc_dist(pad, (s1["fall"]["lat"], s1["fall"]["lon"])), 1)),
                s2=dict(t=round(st2["t"], 1), h=round(st2["h"], 1), v=round(st2["v_rel"] * 1e3), fpa=round(st2["fpa_rel"], 1),
                        impact_km=round(C.gc_dist(pad, (s2["fall"]["lat"], s2["fall"]["lon"])), 1), fit=s2["fit_cost"]),
                s3=dict(t=round(st3["t"], 1), h=round(st3["h"], 1), v=round(st3["v_inertial"], 3), fpa=round(st3["fpa"], 1),
                        i=round(st3["el"]["i"], 2), impact_km=round(C.gc_dist(pad, (s3["fall"]["lat"], s3["fall"]["lon"])), 1),
                        impact_t=round(s3["fall"]["t"]), fit=s3["fit_cost"]),
                s4=s4_out)


def main():
    pad = C.PAD_95A
    # CERES-1 zones: Y12 S1 at 40.2 N 100.1 E (89 km), S3 at 8.1 S 89.3 E (5569 km). Its S2 zone is not in the archive.
    out = dict(ceres1=[fly(CERES1, 300.0, pad, (40.2, 100.1), C.dest(pad, 193.75, r2), (-8.1, 89.3), 500.0)
                       for r2 in (900.0, 1100.0)])
    # ZK-1A zones (2026-09-20, Y18): 39.8 N 100.0 E (130 km), 29.2 N 98.2 E (1323 km), 13.7 S 92.0 E (6138 km); orbit 97.5 deg
    out["zk1a"] = [fly(ZK1A, 1500.0, C.PAD_LC130, (39.8, 100.0), (29.2, 98.2), (-13.7, 92.0), 530.0, solid_s4=True)]
    out["notes"] = dict(zk1a_plane="The ZK-1A S3 plane fitted to its zone is about 93.4 deg, so its solid S4 carries a dogleg to 97.5 deg.",
                        ceres1_s4="The published CERES-1 Y19 failure was an early cutoff 'in the final phase' after 510 s of S4 burn.",
                        ceres1_capability="Published: 300 kg to 500 km SSO, lift-off about 33 t.",
                        zk1a_capability="Published: 1.5 t to 500 km SSO, lift-off 135 t. Solid S4 cannot stop, so a used load "
                                        "below 1.99 t means energy management, not spare payload.")
    (HERE / "validation.json").write_text(json.dumps(out, indent=1, default=float))
    for key in ("ceres1", "zk1a"):
        for run in out[key]:
            print(f"{run['vehicle']:8s} m0 {run['m0_t']:6.1f} t  pay {run['payload_kg']:.0f}")
            print(f"   S1 az {run['s1']['az']} kick {run['s1']['kick']}  t{run['s1']['t']} h{run['s1']['h']} v{run['s1']['v']} "
                  f"fpa{run['s1']['fpa']}  impact {run['s1']['impact_km']} km")
            print(f"   S2 t{run['s2']['t']} h{run['s2']['h']} v{run['s2']['v']} fpa{run['s2']['fpa']}  impact {run['s2']['impact_km']} km")
            print(f"   S3 t{run['s3']['t']} h{run['s3']['h']} v{run['s3']['v']} fpa{run['s3']['fpa']} i{run['s3']['i']}  "
                  f"impact {run['s3']['impact_km']} km at T+{run['s3']['impact_t']}")
            print("   S4", run["s4"])


if __name__ == "__main__":
    main()
