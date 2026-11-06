"""3-DOF ascent model for solid launch vehicles with three or four motors (CERES-1/2, ZK-1A, SD-3) from Jiuquan.

Flight law, after the Vega User's Manual and the solid-vehicle literature:
  S1  vertical rise, programmed pitch kick, zero incidence with the heading held on an Earth-fixed great circle
  S2  zero incidence, same great circle
  S3  bilinear-tangent exo-atmospheric burn to a sub-orbital state (impact fixed by the NOTAM zone)
  S4  one bilinear-tangent burn climbing directly to the circular target orbit (liquid low-thrust stage on CERES)
A solid motor cannot be shut down, so S1-S3 always burn their whole load: staging times and burnout energy are set
by the motor, and steering decides only where that energy goes.

Generic pieces (frames, atmosphere, J2-J4 gravity, coast / fall propagation, osculating elements, SGP4 mean-element
fit) are imported from ../launch_traj_NROL-97/nrol97.py, never copied.

Units: km, km/s, s, kg, N.  Inertial frame = TEME of date (GMST rotation of ECEF).
"""
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np
from numba import njit
from scipy.optimize import brentq, least_squares, minimize

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(Path("~/launch/launch_traj_NROL-97").expanduser()))
from nrol97 import (J2, MU, RE, WE, Arc, Frame, alt_of, atmosphere, bearing, coast, ecef_to_geodetic,  # noqa: E402
                    elements, fall, fit_tle, gc_dist, geodetic_to_ecef, gravity, plane_normal, rotz, unit_ll, v_rel)

G0 = 9.80665
PAD_95A = (40.9691, 100.3435)     # GCAT LC43/95A (commercial pad 95A, Dongfeng Commercial Space Innovation Zone)
PAD_LC130 = (40.8184, 100.2242)   # GCAT LC130 (ZK-1A)
PAD_H = 1.05                      # km
H_DESERT = 1.3                    # km, terrain under the near zone
H_PLATEAU = 4.4                   # km, Qinghai-Tibet terrain under the second zone

# normalised vacuum thrust against burn fraction; each curve has mean 1 (see _norm)
_S1_X = np.array([0.0, 0.015, 0.06, 0.25, 0.45, 0.60, 0.85, 0.95, 1.0])   # progressive start, max-Q bucket, tail-off
_S1_Y = np.array([0.55, 1.08, 1.14, 1.08, 0.92, 0.92, 1.04, 0.88, 0.05])
_S2_X = np.array([0.0, 0.02, 0.10, 0.50, 0.90, 0.97, 1.0])
_S2_Y = np.array([0.50, 1.06, 1.08, 1.04, 0.96, 0.60, 0.04])
_LIQ_X = np.array([0.0, 1.0])
_LIQ_Y = np.array([1.0, 1.0])


def _norm(x, y):
    return x, y / (np.sum((y[1:] + y[:-1]) * np.diff(x)) / 2.0)


SHAPE_S1, SHAPE_S2, SHAPE_LIQ = _norm(_S1_X, _S1_Y), _norm(_S2_X, _S2_Y), (_LIQ_X, _LIQ_Y)


# ---------------------------------------------------------------- vehicle
@dataclass(frozen=True)
class Motor:
    """prop kg, dry kg (case, interstage and hardware dropped with the stage), Isp s, burn s."""
    prop: float
    dry: float
    isp_vac: float
    t_burn: float
    isp_sl: float = 0.0           # S1 only: sets the nozzle exit area

    @property
    def f_mean(self):
        return self.prop * self.isp_vac * G0 / self.t_burn

    @property
    def mdot(self):
        return self.prop / self.t_burn

    @property
    def ae(self):
        """Nozzle exit area, m^2: (F_vac - F_sl) / p0 at the mean flow."""
        return 0.0 if not self.isp_sl else self.mdot * G0 * (self.isp_vac - self.isp_sl) / 101325.0


@dataclass(frozen=True)
class Vehicle:
    name: str
    s1: Motor
    s2: Motor
    s3: Motor
    s4_prop: float               # S4 propellant LOAD (the burn may use less)
    s4_dry: float
    s4_thrust: float             # N, S4 thrust (mean for a solid S4)
    s4_isp: float
    fairing: float
    diameter: float              # m, reference diameter (fairing)
    t_rise: float = 7.0          # s, vertical rise
    dt_sep1: float = 1.5         # burnout -> S2 ignition (hot staging)
    dt_c23: float = 18.0         # S2 burnout -> S3 ignition
    dt_c34: float = 12.0         # S3 burnout -> S4 ignition
    s2_blend: float = 10.0       # s, S2 pitch-over from the flight path to the commanded attitude
    beta_s1: float = 400.0       # kg/m^2, tumbling stages and fairing halves
    beta_s2: float = 330.0
    beta_s3: float = 260.0
    beta_fair: float = 30.0
    q_fair: float = 1135.0       # W/m^2, fairing jettison heat flux

    @property
    def area(self):
        return np.pi * (self.diameter / 2) ** 2

    def m_s4(self, payload):
        return self.s4_prop + self.s4_dry + payload

    def m_s3_stack(self, payload):
        return self.s3.prop + self.s3.dry + self.m_s4(payload)

    def m_s2_stack(self, payload):
        return self.s2.prop + self.s2.dry + self.m_s3_stack(payload) + self.fairing

    def m0(self, payload):
        return self.s1.prop + self.s1.dry + self.m_s2_stack(payload)


# ---------------------------------------------------------------- dynamics kernel
_CDM = np.array([0, 0.6, 0.9, 1.1, 1.5, 2.5, 5, 10.0])
_CDV = np.array([0.30, 0.30, 0.42, 0.60, 0.52, 0.38, 0.30, 0.28])
M_FREE, M_RISE, M_TURN, M_GUIDED = 0, 1, 2, 3
P_TH0, P_UP, P_NG, P_F, P_MD, P_AE, P_TIGN, P_TB, P_AREA, P_NH, P_PI0, P_PI1, P_YA0, P_YA1, P_TAN0, P_BLEND = (
    0, 1, 4, 7, 8, 9, 10, 11, 12, 13, 16, 17, 18, 19, 20, 21)
_NP = 22


@njit(cache=True)
def _deriv(t, y, mode, P, sx, sy):
    r = y[:3]
    v = y[3:6]
    m = y[6]
    out = np.empty(7)
    out[0], out[1], out[2] = v[0], v[1], v[2]
    a = gravity(r)
    md = 0.0
    if mode != M_FREE:
        tau = (t - P[P_TIGN]) / P[P_TB]
        f = np.interp(tau, sx, sy) if 0.0 <= tau <= 1.0 else 0.0
        md = P[P_MD] * f
        h = alt_of(r)
        rho, p, cs = atmosphere(h)
        thrust = max(P[P_F] * f - P[P_AE] * p, 0.0)
        acc = thrust / m * 1e-3
        vr0 = v[0] + WE * r[1]
        vr1 = v[1] - WE * r[0]
        vr2 = v[2]
        vrn = np.sqrt(vr0 * vr0 + vr1 * vr1 + vr2 * vr2)
        rn = np.sqrt(r[0] * r[0] + r[1] * r[1] + r[2] * r[2])
        u0, u1, u2 = r[0] / rn, r[1] / rn, r[2] / rn
        if mode == M_GUIDED:
            n0, n1, n2 = P[P_NH], P[P_NH + 1], P[P_NH + 2]
            s0, s1, s2 = n1 * u2 - n2 * u1, n2 * u0 - n0 * u2, n0 * u1 - n1 * u0
            sn = np.sqrt(s0 * s0 + s1 * s1 + s2 * s2)
            s0, s1, s2 = s0 / sn, s1 / sn, s2 / sn
            c0, c1, c2 = u1 * s2 - u2 * s1, u2 * s0 - u0 * s2, u0 * s1 - u1 * s0
            x = (t - P[P_TIGN]) / 100.0
            tan_p = P[P_PI0] + P[P_PI1] * x
            tan_y = P[P_YA0] + P[P_YA1] * x
            if P[P_BLEND] > 0.0:          # pitch over from the flight path at ignition, not a step
                w = min(1.0, (t - P[P_TIGN]) / P[P_BLEND])
                tan_p = P[P_TAN0] + (tan_p - P[P_TAN0]) * w
                tan_y = tan_y * w
            th = np.arctan(tan_p)
            ps = np.arctan(tan_y)
            cth, sth, cps, sps = np.cos(th), np.sin(th), np.cos(ps), np.sin(ps)
            a[0] += acc * (cps * (sth * u0 + cth * s0) + sps * c0)
            a[1] += acc * (cps * (sth * u1 + cth * s1) + sps * c1)
            a[2] += acc * (cps * (sth * u2 + cth * s2) + sps * c2)
        else:
            th = P[P_TH0] + WE * t
            ct, st = np.cos(th), np.sin(th)
            if mode == M_RISE:
                ux, uy, uz = P[P_UP], P[P_UP + 1], P[P_UP + 2]
                d0, d1, d2 = ct * ux - st * uy, st * ux + ct * uy, uz
            else:
                gx, gy, gz = P[P_NG], P[P_NG + 1], P[P_NG + 2]
                g0, g1, g2 = ct * gx - st * gy, st * gx + ct * gy, gz
                h0, h1, h2 = g1 * u2 - g2 * u1, g2 * u0 - g0 * u2, g0 * u1 - g1 * u0
                hn = np.sqrt(h0 * h0 + h1 * h1 + h2 * h2)
                h0, h1, h2 = h0 / hn, h1 / hn, h2 / hn
                vu = vr0 * u0 + vr1 * u1 + vr2 * u2
                vh = max(vr0 * h0 + vr1 * h1 + vr2 * h2, 0.0)
                nn = np.sqrt(vu * vu + vh * vh)
                d0, d1, d2 = (vu * u0 + vh * h0) / nn, (vu * u1 + vh * h1) / nn, (vu * u2 + vh * h2) / nn
            a[0] += acc * d0
            a[1] += acc * d1
            a[2] += acc * d2
        if rho > 0.0 and vrn > 1e-6 and P[P_AREA] > 0.0:
            q = 0.5 * rho * (vrn * 1e3) ** 2
            k = -q * np.interp(vrn * 1e3 / cs, _CDM, _CDV) * P[P_AREA] / m * 1e-3 / vrn
            a[0] += k * vr0
            a[1] += k * vr1
            a[2] += k * vr2
    out[3], out[4], out[5] = a[0], a[1], a[2]
    out[6] = -md
    return out


@njit(cache=True)
def _rk4(t, y, dt, mode, P, sx, sy):
    k1 = _deriv(t, y, mode, P, sx, sy)
    k2 = _deriv(t + dt / 2, y + dt / 2 * k1, mode, P, sx, sy)
    k3 = _deriv(t + dt / 2, y + dt / 2 * k2, mode, P, sx, sy)
    k4 = _deriv(t + dt, y + dt * k3, mode, P, sx, sy)
    return y + dt / 6 * (k1 + 2 * k2 + 2 * k3 + k4)


@njit(cache=True)
def _march(t, y, t_end, dt, mode, P, sx, sy):
    n = int(np.ceil((t_end - t) / dt - 1e-9))
    n = max(n, 1)
    h = (t_end - t) / n
    T = np.empty(n + 1)
    Y = np.empty((n + 1, 7))
    T[0], Y[0] = t, y
    for k in range(n):
        y = _rk4(t, y, h, mode, P, sx, sy)
        t = t + h
        T[k + 1], Y[k + 1] = t, y
    return T, Y


def march(t, y, t_end, dt, mode, P, shape=SHAPE_LIQ):
    return Arc(*_march(float(t), np.asarray(y, float), float(t_end), float(dt), mode, P, shape[0], shape[1]))


def _y(r, v, m):
    return np.concatenate([np.asarray(r, float), np.asarray(v, float), [float(m)]])


# ---------------------------------------------------------------- pad geometry
def pad_frame(pad):
    lat, lon = pad
    la, lo = np.radians(lat), np.radians(lon)
    up = np.array([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo), np.sin(la)])
    east = np.array([-np.sin(lo), np.cos(lo), 0.0])
    north = np.cross(up, east)
    return up, east, north


def great_circle_normal(pad, az):
    up, east, north = pad_frame(pad)
    return np.cross(up, np.sin(np.radians(az)) * east + np.cos(np.radians(az)) * north)


def _motor_P(frame, motor, t_ign, area, pad=None, ng=None):
    P = np.zeros(_NP)
    P[P_TH0] = frame.g0
    if pad is not None:
        P[P_UP:P_UP + 3] = pad_frame(pad)[0]
    if ng is not None:
        P[P_NG:P_NG + 3] = ng
    P[P_F], P[P_MD], P[P_AE] = motor.f_mean, motor.mdot, motor.ae
    P[P_TIGN], P[P_TB], P[P_AREA] = t_ign, motor.t_burn, area
    return P


def _guided_P(frame, f, md, t_ign, t_burn, nh, x, area=0.0, tan0=0.0, blend=0.0):
    P = np.zeros(_NP)
    P[P_TH0] = frame.g0
    P[P_F], P[P_MD], P[P_TIGN], P[P_TB], P[P_AREA] = f, md, t_ign, t_burn, area
    P[P_TAN0], P[P_BLEND] = tan0, blend
    P[P_NH:P_NH + 3] = nh
    P[P_PI0], P[P_PI1], P[P_YA0], P[P_YA1] = x
    return P


# ---------------------------------------------------------------- S1, S2 (zero incidence on one great circle)
def fly_s1(frame, veh, pad, az, kick, payload, dt=0.1):
    """Lift-off -> S1 burnout.  kick: pitch-over from the vertical, deg, applied to the air-relative velocity."""
    up, east, north = pad_frame(pad)
    hz = np.sin(np.radians(az)) * east + np.cos(np.radians(az)) * north
    r0, v0 = frame.to_eci(geodetic_to_ecef(pad[0], pad[1], PAD_H), 0.0, np.zeros(3))
    ng = np.cross(up, hz)
    P = _motor_P(frame, veh.s1, 0.0, veh.area, pad=pad, ng=ng)
    a1 = march(0.0, _y(r0, v0, veh.m0(payload)), veh.t_rise, dt, M_RISE, P, SHAPE_S1)
    y = a1.Y[-1].copy()
    vr = v_rel(y[:3], y[3:6])
    d = rotz(frame.theta(veh.t_rise)) @ (np.cos(np.radians(kick)) * up + np.sin(np.radians(kick)) * hz)
    y[3:6] = y[3:6] - vr + np.linalg.norm(vr) * d
    a2 = march(veh.t_rise, y, veh.s1.t_burn, dt, M_TURN, P, SHAPE_S1)
    a2.Y[0] = a1.Y[-1]
    return dict(arc=Arc.join([a1, a2]), ng=ng, t_b=veh.s1.t_burn)


def s2_ignition(frame, veh, s1, payload, inc):
    """State at S2 ignition, the mission plane through it and the tangent of the air-relative flight path."""
    t_b1 = s1["t_b"]
    t_ign = t_b1 + veh.dt_sep1
    y = s1["arc"].Y[-1].copy()
    c = coast(y[:3], y[3:6], t_b1, t_ign, dt=0.25)
    y = c.Y[-1].copy()
    y[6] = veh.m_s2_stack(payload)
    nh, raan = plane_through(y[:3], inc, y[3:6])
    vr = v_rel(y[:3], y[3:6])
    u = y[:3] / np.linalg.norm(y[:3])
    vu = vr @ u
    return dict(t=t_ign, y=y, nh=nh, raan=raan, tan0=vu / np.linalg.norm(vr - vu * u))


def fly_s2(frame, veh, s1, payload, inc, a2, b2, c2, dt=0.1):
    """S1 burnout -> S2 burnout.  S2 lights above the dense air (q ~1 kPa and falling fast), pitches over to the attitude
    tan(pitch) = a2 + b2*tau (tau = (t - t_ign)/100 s) at constant yaw c2 (tan) about the mission plane.  The yaw is
    what cancels the Earth-rotation velocity carried out of the steep S1 climb."""
    ig = s2_ignition(frame, veh, s1, payload, inc)
    P = _guided_P(frame, veh.s2.f_mean, veh.s2.mdot, ig["t"], veh.s2.t_burn, ig["nh"],
                  np.array([a2, b2, c2, 0.0]), area=veh.area, tan0=ig["tan0"], blend=veh.s2_blend)
    a = march(ig["t"], ig["y"], ig["t"] + veh.s2.t_burn, dt, M_GUIDED, P, SHAPE_S2)
    return dict(arc=a, t_ign=ig["t"], t_b=ig["t"] + veh.s2.t_burn, nh=ig["nh"], tan0=ig["tan0"], a2=a2, b2=b2, c2=c2, P=P)


def heat_flux(r, v):
    rho = atmosphere(alt_of(r))[0]
    return 0.5 * rho * (np.linalg.norm(v_rel(r, v)) * 1e3) ** 3


def fairing_time(veh, s2, t_ign3):
    """First time at least 5 s after S2 burnout (S2 clear) when the heat flux is below veh.q_fair; capped at S3
    ignition + 5 s.  Jettison in the S2-S3 coast is what puts the fairing in the S2 zone."""
    arc = s2["arc"]
    c = coast(arc.r_end, arc.v_end, arc.t_end, t_ign3 + 5.0, dt=0.25)
    for k in range(len(c.T)):
        if c.T[k] >= arc.t_end + 5.0 and heat_flux(c.Y[k, :3], c.Y[k, 3:6]) < veh.q_fair:
            return float(c.T[k])
    return float(c.T[-1])


# ---------------------------------------------------------------- S3 (solid, burns everything)
def fly_s3(frame, veh, s2, payload, nh, x, t_fair=None, dt=0.1):
    """S2 burnout -> S3 burnout on a bilinear-tangent law about plane nh; x = [tan pitch0, tan pitch1, tan yaw0,
    tan yaw1], tau = (t - t_ign)/100 s.  The fairing goes at t_fair (before or after ignition)."""
    arc2 = s2["arc"]
    t_ign = arc2.t_end + veh.dt_c23
    t_fair = fairing_time(veh, s2, t_ign) if t_fair is None else t_fair
    y = arc2.Y[-1].copy()
    y[6] = veh.m_s3_stack(payload) + veh.fairing
    P = _guided_P(frame, veh.s3.f_mean, veh.s3.mdot, t_ign, veh.s3.t_burn, nh, x)
    segs = []
    fair_state = None
    if t_fair <= t_ign:
        c1 = march(arc2.t_end, y, t_fair, 0.25, M_FREE, P)
        fair_state = c1.Y[-1, :6].copy()
        y = c1.Y[-1].copy()
        y[6] -= veh.fairing
        c2 = march(t_fair, y, t_ign, 0.25, M_FREE, P)
        segs += [c1, c2]
        b = march(t_ign, c2.Y[-1], t_ign + veh.s3.t_burn, dt, M_GUIDED, P, SHAPE_S2)
        segs.append(b)
    else:
        c1 = march(arc2.t_end, y, t_ign, 0.25, M_FREE, P)
        b1 = march(t_ign, c1.Y[-1], t_fair, dt, M_GUIDED, P, SHAPE_S2)
        fair_state = b1.Y[-1, :6].copy()
        y = b1.Y[-1].copy()
        y[6] -= veh.fairing
        b2 = march(t_fair, y, t_ign + veh.s3.t_burn, dt, M_GUIDED, P, SHAPE_S2)
        segs += [c1, b1, b2]
    return dict(arc=Arc.join(segs), t_ign=t_ign, t_b=t_ign + veh.s3.t_burn, t_fair=t_fair, fair_state=fair_state, x=x)


# ---------------------------------------------------------------- S4 (to the target orbit)
def fly_s4(frame, veh, s3, payload, nh, x, dt=1.0):
    """S3 burnout -> S4 cutoff. x = [tan pitch0, tan pitch1, tan yaw0, tan yaw1, t_burn/100]."""
    a3 = s3["arc"]
    t_ign = a3.t_end + veh.dt_c34
    t_burn = x[4] * 100.0
    md = veh.s4_thrust / (veh.s4_isp * G0)
    y = a3.Y[-1].copy()
    y[6] = veh.m_s4(payload)
    P = _guided_P(frame, veh.s4_thrust, md, t_ign, t_burn, nh, x[:4])
    c = march(a3.t_end, y, t_ign, 0.5, M_FREE, P)
    b = march(t_ign, c.Y[-1], t_ign + t_burn, dt, M_GUIDED, P)
    return dict(arc=Arc.join([c, b]), t_ign=t_ign, t_b=t_ign + t_burn, prop_used=md * t_burn, x=np.array(x))


def solve_s4(frame, veh, s3, payload, nh, r_t, x0=None):
    """Bilinear-tangent S4 burn ending circular at radius r_t in plane nh. -> (s4, x, cost)"""
    v_t = np.sqrt(MU / r_t)

    def res(p):
        a = fly_s4(frame, veh, s3, payload, nh, p, dt=2.0)["arc"]
        r, v = a.r_end, a.v_end
        rn = np.linalg.norm(r)
        vr = r @ v / rn
        vh = np.linalg.norm(np.cross(r, v)) / rn
        return [(rn - r_t) / 5.0, vr * 100.0, (vh - v_t) * 100.0, (r @ nh) / 5.0, (v @ nh) * 500.0]

    starts = [] if x0 is None else [np.asarray(x0, float)]
    starts += [np.array([0.8, -0.12, 0.0, 0.0, 7.0]), np.array([0.4, -0.05, 0.0, 0.0, 6.0]), np.array([1.2, -0.2, 0.0, 0.0, 7.0]),
               np.array([0.5, -0.1, 0.0, 0.0, 7.5]), np.array([1.8, -0.4, 0.0, 0.0, 6.0]), np.array([0.2, -0.02, 0.0, 0.0, 5.0])]
    best = None
    for s in starts:
        try:
            so = least_squares(res, s, diff_step=1e-5, max_nfev=160, ftol=1e-11, xtol=1e-11, gtol=1e-11)
        except (ValueError, FloatingPointError, ZeroDivisionError):
            continue
        if best is None or so.cost < best.cost:
            best = so
        if so.cost < 1e-8:
            break
    return fly_s4(frame, veh, s3, payload, nh, best.x), best.x, float(best.cost)


# ---------------------------------------------------------------- falls
def stage_fall(frame, arc_or_state, t, beta, h_stop):
    if hasattr(arc_or_state, "r_end"):
        r, v = arc_or_state.r_end, arc_or_state.v_end
    else:
        r, v = arc_or_state[:3], arc_or_state[3:]
    f = fall(r, v, t, beta, h_stop=h_stop, dt_hi=1.0, dt_lo=0.25)
    lat, lon, _ = frame.lla(f.r_end, f.t_end)
    return dict(arc=f, t=float(f.t_end), lat=float(lat), lon=float(lon))


# ---------------------------------------------------------------- planes
def sso_inclination(alt_km, ecc=0.0):
    a = RE + alt_km
    rate = 2 * np.pi / (365.2421897 * 86400.0)
    n = np.sqrt(MU / a ** 3)
    return float(np.degrees(np.arccos(-rate / (1.5 * n * J2 * (RE / (a * (1 - ecc * ecc))) ** 2))))


def plane_through(r, inc, v_hint):
    """Normal of the plane of inclination inc containing r, branch whose motion matches v_hint. -> (n, raan)"""
    rh = r / np.linalg.norm(r)
    ci, si = np.cos(np.radians(inc)), np.sin(np.radians(inc))
    A, B, C = si * rh[0], -si * rh[1], ci * rh[2]
    R = np.hypot(A, B)
    if abs(C) > R:
        raise ValueError("inclination below the latitude of r")
    phi = np.arctan2(B, A)
    best = None
    for O in (np.arcsin(-C / R) - phi, np.pi - np.arcsin(-C / R) - phi):
        n = plane_normal(inc, np.degrees(O))
        s = np.cross(n, rh) @ v_hint
        if best is None or s > best[0]:
            best = (s, n, np.degrees(O) % 360)
    return best[1], best[2]


# ---------------------------------------------------------------- NOTAM text -> polygons
_PATTERNS = [re.compile(r"\b([NS])(\d{2})(\d{2})(\d{2})([EW])(\d{3})(\d{2})(\d{2})\b"),   # N401500E1000000
             re.compile(r"\b(\d{2})(\d{2})(\d{2})([NS])\s+(\d{3})(\d{2})(\d{2})([EW])\b")]   # 005535N 0900321E


def _dms(d, m, s, hemi):
    v = int(d) + int(m) / 60 + int(s) / 3600
    return -v if hemi in "SW" else v


def parse_notams(path):
    """-> list of dict(id, fir, t0, t1, ring [(lat, lon), ...] open).  Only the E) section is read, so the Q-line centre
    and the ATS route names never enter a polygon; a repeated first point closes the ring."""
    text = Path(path).read_text()
    out = []
    for block in re.split(r"\n\s*\n", text.strip()):
        head = re.search(r"([A-Z]\d{4}/\d{2})\s+NOTAMN", block)
        fir = re.search(r"A\)\s*([A-Z ]+?)\s*(?:B\)|\n)", block).group(1).strip()
        b = re.search(r"B\)\s*(\d{10})", block).group(1)
        c = re.search(r"C\)\s*(\d{10})", block).group(1)
        body = re.split(r"\bE\)", block, maxsplit=1)[1]
        body = re.split(r"\bF\)", body, maxsplit=1)[0]
        pts = []
        for m in _PATTERNS[0].finditer(body):
            g = m.groups()
            pts.append((m.start(), _dms(g[1], g[2], g[3], g[0]), _dms(g[5], g[6], g[7], g[4])))
        for m in _PATTERNS[1].finditer(body):
            g = m.groups()
            pts.append((m.start(), _dms(g[0], g[1], g[2], g[3]), _dms(g[4], g[5], g[6], g[7])))
        pts = [(la, lo) for _, la, lo in sorted(pts)]
        if len(pts) > 2 and np.allclose(pts[0], pts[-1]):
            pts = pts[:-1]
        out.append(dict(id=head.group(1), fir=fir, b=b, c=c, t0=b[-4:], t1=c[-4:], ring=pts))
    return out


def centroid(ring):
    u = np.sum([unit_ll(*p) for p in ring], axis=0)
    u /= np.linalg.norm(u)
    return float(np.degrees(np.arcsin(u[2]))), float(np.degrees(np.arctan2(u[1], u[0])))


def point_in_ring(lat, lon, ring):
    inside = False
    n = len(ring)
    for i in range(n):
        y1, x1 = ring[i]
        y2, x2 = ring[(i + 1) % n]
        if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def dest(p, az, d_km):
    """Great-circle destination from p at azimuth az after d_km."""
    la, lo, de, a = np.radians(p[0]), np.radians(p[1]), d_km / 6371.0, np.radians(az)
    la2 = np.arcsin(np.sin(la) * np.cos(de) + np.cos(la) * np.sin(de) * np.cos(a))
    lo2 = lo + np.arctan2(np.sin(a) * np.sin(de) * np.cos(la), np.cos(de) - np.sin(la) * np.sin(la2))
    return float(np.degrees(la2)), float(np.degrees(lo2))


def range_bearing(pad, p):
    return float(gc_dist(pad, p)), float(bearing(pad, p))


def cross_track(pad, az, p):
    """Signed km right of the great circle leaving pad at azimuth az; and km along it."""
    n = great_circle_normal(pad, az)
    u = unit_ll(*p)
    cr = 6371.0 * np.arcsin(np.clip(-u @ n, -1, 1))
    up, east, north = pad_frame(pad)
    hz = np.sin(np.radians(az)) * east + np.cos(np.radians(az)) * north
    al = 6371.0 * np.arctan2(u @ hz, u @ up)
    return float(al), float(cr)


# ---------------------------------------------------------------- targeting
def impact_of(frame, f):
    return f["lat"], f["lon"]


def fit_s1(frame, veh, pad, payload, p1, h_stop=H_DESERT, guess=(1.5, 190.0), kick_hi=None):
    """Kick and azimuth dropping S1 on point p1, on the steep (lofted) side of range-versus-kick.  S1's range has a
    maximum against the kick: the flat side leaves S2 in the air and the fairing no way off, so it is not flyable."""
    target = gc_dist(pad, p1)
    az = bearing(pad, p1)

    def rng(k, az_):
        s = fly_s1(frame, veh, pad, az_, k, payload, dt=0.2)
        f = stage_fall(frame, s["arc"], s["arc"].t_end, veh.beta_s1, h_stop)
        return gc_dist(pad, (f["lat"], f["lon"])), f

    for _ in range(4):
        ks = np.geomspace(0.15, 6.0, 26)
        rs = [rng(k, az)[0] for k in ks]
        i = int(np.argmax(rs))
        if rs[i] < target:
            raise RuntimeError(f"S1 range peaks at {rs[i]:.0f} km, below the {target:.0f} km target")
        j = next(j for j in range(i + 1) if rs[j] >= target)
        k = brentq(lambda q: rng(q, az)[0] - target, ks[max(j - 1, 0)], ks[j], xtol=1e-4)
        _, f = rng(k, az)
        az += bearing(pad, p1) - bearing(pad, (f["lat"], f["lon"]))
    s1 = fly_s1(frame, veh, pad, az, k, payload)
    s1.update(az=float(az), kick=float(k), fall=stage_fall(frame, s1["arc"], s1["arc"].t_end, veh.beta_s1, h_stop))
    return s1


def fit_s2(frame, veh, s1, payload, inc, pad, p2, a2, h_stop=H_PLATEAU, guess=(-0.5, -0.05)):
    """With the pitch offset a2 fixed, the pitch rate and yaw that drop S2 on point p2."""
    az = bearing(pad, p2)
    rng = gc_dist(pad, p2)

    def res(x):
        s2 = fly_s2(frame, veh, s1, payload, inc, a2, x[0], x[1], dt=0.2)
        try:
            f = stage_fall(frame, s2["arc"], s2["arc"].t_end, veh.beta_s2, h_stop)
        except RuntimeError:
            return [2000.0, 0.0]
        if abs(x[0]) > 4.0:             # no pitch reversal: a huge rate means the solver left the physical branch
            return [2000.0 * abs(x[0]), 0.0]
        al, cr = cross_track(pad, az, (f["lat"], f["lon"]))
        return [(al - rng) / 5.0, cr / 5.0]

    best = None
    for g in (guess, (-0.2, -0.05), (-0.8, -0.05), (-1.2, -0.1), (0.2, -0.05), (0.6, -0.05), (-1.8, -0.1), (1.2, -0.05)):
        so = least_squares(res, g, diff_step=1e-4, max_nfev=50)
        if best is None or so.cost < best.cost:
            best = so
        if so.cost < 1e-4:
            break
    s2 = fly_s2(frame, veh, s1, payload, inc, a2, *best.x)
    s2.update(fit_cost=float(best.cost), fall=stage_fall(frame, s2["arc"], s2["arc"].t_end, veh.beta_s2, h_stop))
    return s2


def fit_s3(frame, veh, s2, payload, inc, pad, p3, b3, guess=(0.1, -0.05), h_stop=0.0):
    """Pitch offset and yaw (tan pitch-rate b3 fixed) dropping the burnt S3 on point p3.  -> s3 with fall"""
    t_ign = s2["arc"].t_end + veh.dt_c23
    yi = coast(s2["arc"].r_end, s2["arc"].v_end, s2["arc"].t_end, t_ign, dt=0.25)
    nh, _ = plane_through(yi.r_end, inc, yi.v_end)
    az = bearing(pad, p3)
    t_fair = fairing_time(veh, s2, t_ign)

    def res(x):
        s3 = fly_s3(frame, veh, s2, payload, nh, np.array([x[0], b3, x[1], 0.0]), t_fair=t_fair, dt=0.2)
        try:
            f = stage_fall(frame, s3["arc"], s3["arc"].t_end, veh.beta_s3, h_stop)
        except RuntimeError:
            return [500.0, 0.0]
        al, cr = cross_track(pad, az, (f["lat"], f["lon"]))
        return [(al - gc_dist(pad, p3)) / 20.0, cr / 20.0]

    best = None
    for g in (guess, (0.0, -0.05), (0.2, -0.1), (-0.2, -0.05), (0.4, -0.1), (-0.4, 0.0), (0.7, -0.1), (-0.7, 0.0)):
        so = least_squares(res, g, diff_step=1e-4, max_nfev=50)
        if best is None or so.cost < best.cost:
            best = so
        if so.cost < 1e-4:
            break
    x = best.x
    s3 = fly_s3(frame, veh, s2, payload, nh, np.array([x[0], b3, x[1], 0.0]), t_fair=t_fair)
    s3.update(fit_cost=float(best.cost), nh=nh, fall=stage_fall(frame, s3["arc"], s3["arc"].t_end, veh.beta_s3, h_stop))
    return s3


def fit_s4(frame, veh, s3, payload, inc, h_t, x0=None):
    """S4 direct to a circular orbit at h_t km, inclination inc, at the fuel-optimal node: the mission picks the plane but T0
    is free to match it, so the node that minimises the burn is the one a planned ascent flies.  Warm-started grid about the
    plane through the S4 ignition point.  The burn is nearly flat against the node, so among nodes within 0.5 s of the best
    the one needing the least yaw is flown. -> s4 with raan"""
    a3 = s3["arc"]
    t_ign = a3.t_end + veh.dt_c34
    c = coast(a3.r_end, a3.v_end, a3.t_end, t_ign, dt=0.5)
    n0, raan0 = plane_through(c.r_end, inc, c.v_end)
    r_t = RE + h_t
    good = {}

    def solve(off, start):
        _, xs, cost = solve_s4(frame, veh, s3, payload, plane_normal(inc, raan0 + off), r_t, start)
        if cost < 1e-6 and 0 < xs[4] < 30:
            good[off] = xs
            return xs
        return start

    x = solve(0.0, x0)
    seed = x
    for off in (0.1, 0.2, 0.3, 0.45, 0.6):
        x = solve(off, x)
    x = seed
    for off in (-0.1, -0.2, -0.3, -0.45, -0.6):
        x = solve(off, x)
    if not good:
        s4, xs, cost = solve_s4(frame, veh, s3, payload, n0, r_t, x0)
        s4.update(raan=float(raan0) % 360, raan_through=float(raan0), cost=cost)
        return s4
    tb_min = min(q[4] for q in good.values())
    yaw = lambda q: abs(q[2]) + abs(q[2] + q[3] * q[4])
    best_off = min((o for o, q in good.items() if q[4] <= tb_min + 0.005), key=lambda o: yaw(good[o]))
    s4, xs, cost = solve_s4(frame, veh, s3, payload, plane_normal(inc, raan0 + best_off), r_t, good[best_off])
    s4.update(raan=float(raan0 + best_off) % 360, raan_through=float(raan0), cost=cost)
    return s4


def state_of(frame, arc):
    y = arc.Y[-1]
    lat, lon, h = frame.lla(y[:3], arc.t_end)
    vi = np.linalg.norm(y[3:6])
    ri = np.linalg.norm(y[:3])
    vr = v_rel(y[:3], y[3:6])
    return dict(t=float(arc.t_end), lat=float(lat), lon=float(lon), h=float(h), v_inertial=float(vi),
                v_rel=float(np.linalg.norm(vr)), fpa=float(np.degrees(np.arcsin(y[:3] @ y[3:6] / (ri * vi)))),
                fpa_rel=float(np.degrees(np.arcsin(y[:3] @ vr / (ri * np.linalg.norm(vr))))), m=float(y[6]),
                el=elements(y[:3], y[3:6]))


def s2_q_alpha(frame, s2):
    """Peak dynamic pressure x angle of attack on the S2 arc, Pa*deg, with where it peaks."""
    P = s2["P"]
    arc = s2["arc"]
    best = (0.0, 0.0, 0.0, 0.0)
    for k in range(len(arc.T)):
        t, y = arc.T[k], arc.Y[k]
        r, v = y[:3], y[3:6]
        u = r / np.linalg.norm(r)
        nh = P[P_NH:P_NH + 3]
        sd = np.cross(nh, u)
        sd /= np.linalg.norm(sd)
        cd = np.cross(u, sd)
        x = (t - P[P_TIGN]) / 100.0
        w = min(1.0, (t - P[P_TIGN]) / P[P_BLEND])
        tp = P[P_TAN0] + (P[P_PI0] + P[P_PI1] * x - P[P_TAN0]) * w
        ty = (P[P_YA0] + P[P_YA1] * x) * w
        th, ps = np.arctan(tp), np.arctan(ty)
        d = np.cos(ps) * (np.sin(th) * u + np.cos(th) * sd) + np.sin(ps) * cd
        vr = v_rel(r, v)
        al = np.degrees(np.arccos(np.clip(d @ vr / np.linalg.norm(vr), -1, 1)))
        rho = atmosphere(alt_of(r))[0]
        q = 0.5 * rho * (np.linalg.norm(vr) * 1e3) ** 2
        if q * al > best[0]:
            best = (float(q * al), float(q), float(al), float(t))
    return best


def max_q(arc):
    best = (0.0, 0.0)
    for k in range(len(arc.T)):
        r, v = arc.Y[k, :3], arc.Y[k, 3:6]
        q = 0.5 * atmosphere(alt_of(r))[0] * (np.linalg.norm(v_rel(r, v)) * 1e3) ** 2
        if q > best[0]:
            best = (float(q), float(arc.T[k]))
    return best
