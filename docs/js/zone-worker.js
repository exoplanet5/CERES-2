// Twilight-jelly grid off the main thread. The 80,000-cell pass took 60-70 ms on an M1 Max: a hitch at startup and after every T0 change.
// The page posts the mission once, then {version, T0, pickupMet} per request, and keeps only the newest version's reply.
import {createFlight, solarEphemeris} from './profile.js';
import {createJellyZones} from './jelly-grid.js';

let zoneAt = null;
onmessage = ({data: m}) => {
  if (m.mission) {
    const {tracks, poweredAt} = createFlight(m.mission);
    zoneAt = createJellyZones(m.mission.meta, tracks.ascent, poweredAt, solarEphemeris(m.mission.sun));
    return;
  }
  const Z = zoneAt(m.T0, m.pickupMet);
  postMessage({version: m.version, zones: Z}, [Z.elevSolid.buffer, Z.elevS4.buffer]);
};
