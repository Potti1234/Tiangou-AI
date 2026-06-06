
import { useCallback, useEffect, useMemo, useState } from "react";

const OVERPASS_URLS = [
  "https://overpass-api.de/api/interpreter",
  "https://overpass.kumi.systems/api/interpreter",
];

const HK_BBOX = "22.13,113.80,22.62,114.50";
const TOPOLOGY_MODE = import.meta.env.VITE_GRID_TOPOLOGY_MODE || "auto";
const TOPOLOGY_URL = import.meta.env.VITE_GRID_TOPOLOGY_URL || "/grid-topology.json";

const fallbackAssets = [
  { id: "castle-peak", kind: "plant", name: "Castle Peak Power Station", owner: "CLP", voltage: 400, source: "coal / gas", lat: 22.377, lon: 113.910 },
  { id: "black-point", kind: "plant", name: "Black Point Power Station", owner: "CLP", voltage: 400, source: "gas", lat: 22.416, lon: 113.911 },
  { id: "pennys-bay", kind: "plant", name: "Penny's Bay Power Station", owner: "CLP", voltage: 132, source: "gas turbine", lat: 22.318, lon: 114.040 },
  { id: "lamma", kind: "plant", name: "Lamma Power Station", owner: "HKE", voltage: 275, source: "gas / coal", lat: 22.220, lon: 114.108 },

  { id: "tuen-mun", kind: "substation", name: "Tuen Mun EHV hub", owner: "CLP", voltage: 400, lat: 22.391, lon: 113.975 },
  { id: "yuen-long", kind: "substation", name: "Yuen Long EHV hub", owner: "CLP", voltage: 400, lat: 22.445, lon: 114.032 },
  { id: "tai-po", kind: "substation", name: "Tai Po EHV hub", owner: "CLP", voltage: 400, lat: 22.447, lon: 114.177 },
  { id: "sha-tin", kind: "substation", name: "Sha Tin EHV hub", owner: "CLP", voltage: 400, lat: 22.382, lon: 114.196 },
  { id: "tseung-kwan-o", kind: "substation", name: "Tseung Kwan O EHV hub", owner: "CLP", voltage: 400, lat: 22.310, lon: 114.258 },
  { id: "tsing-yi", kind: "substation", name: "Tsing Yi hub", owner: "CLP", voltage: 132, lat: 22.348, lon: 114.103 },
  { id: "kowloon", kind: "substation", name: "Kowloon hub", owner: "CLP", voltage: 132, lat: 22.319, lon: 114.173 },
  { id: "lantau", kind: "substation", name: "Lantau hub", owner: "CLP", voltage: 132, lat: 22.294, lon: 113.944 },

  { id: "north-point", kind: "substation", name: "North Point hub", owner: "HKE", voltage: 132, lat: 22.291, lon: 114.201 },
  { id: "aberdeen", kind: "substation", name: "Aberdeen hub", owner: "HKE", voltage: 132, lat: 22.249, lon: 114.156 },
  { id: "cyberport", kind: "substation", name: "Cyberport hub", owner: "HKE", voltage: 132, lat: 22.261, lon: 114.130 },
  { id: "chai-wan", kind: "substation", name: "Chai Wan hub", owner: "HKE", voltage: 132, lat: 22.268, lon: 114.239 },

  { id: "clp-scc", kind: "control", name: "CLP System Control Centre", owner: "CLP", voltage: null, lat: 22.429, lon: 114.186, note: "Tai Po Kau" },
  { id: "hke-scc", kind: "control", name: "HK Electric System Control Centre", owner: "HKE", voltage: null, lat: 22.278, lon: 114.171, note: "generalised operator marker" },
];

const fallbackCircuits = [
  {
    id: "clp-400-ring-west",
    name: "CLP 400 kV western arc",
    owner: "CLP",
    voltage: 400,
    cableType: "overhead / line",
    points: [[113.910,22.377],[113.975,22.391],[114.032,22.445],[114.177,22.447]],
  },
  {
    id: "clp-400-ring-east",
    name: "CLP 400 kV eastern arc",
    owner: "CLP",
    voltage: 400,
    cableType: "overhead / line",
    points: [[114.177,22.447],[114.245,22.421],[114.258,22.310],[114.196,22.382]],
  },
  {
    id: "clp-400-ring-south",
    name: "CLP 400 kV southern reinforcement",
    owner: "CLP",
    voltage: 400,
    cableType: "overhead / cable",
    points: [[113.975,22.391],[114.103,22.348],[114.196,22.382],[114.258,22.310]],
  },
  {
    id: "clp-132-kowloon",
    name: "CLP 132 kV Kowloon corridor",
    owner: "CLP",
    voltage: 132,
    cableType: "underground / cable",
    points: [[114.103,22.348],[114.173,22.319],[114.258,22.310]],
  },
  {
    id: "clp-132-lantau",
    name: "CLP 132 kV Lantau corridor",
    owner: "CLP",
    voltage: 132,
    cableType: "submarine / cable",
    points: [[114.040,22.318],[113.944,22.294],[114.103,22.348]],
  },
  {
    id: "hke-275-lamma-west",
    name: "HKE 275 kV Lamma western route",
    owner: "HKE",
    voltage: 275,
    cableType: "submarine / cable",
    points: [[114.108,22.220],[114.130,22.261],[114.156,22.249],[114.171,22.278]],
  },
  {
    id: "hke-275-lamma-east",
    name: "HKE 275 kV Lamma eastern route",
    owner: "HKE",
    voltage: 275,
    cableType: "submarine / cable",
    points: [[114.108,22.220],[114.167,22.242],[114.201,22.291]],
  },
  {
    id: "hke-132-island",
    name: "HKE 132 kV island ring",
    owner: "HKE",
    voltage: 132,
    cableType: "underground / cable",
    points: [[114.130,22.261],[114.156,22.249],[114.171,22.278],[114.201,22.291],[114.239,22.268]],
  },
  {
    id: "clp-hke-link",
    name: "CLP–HKE cross-harbour emergency link",
    owner: "Shared",
    voltage: 132,
    cableType: "submarine / cable",
    points: [[114.173,22.319],[114.183,22.300],[114.201,22.291]],
  },
];

function parseVoltage(raw) {
  if (!raw) return null;
  const token = String(raw).split(/[;,]/)[0];
  const number = Number(token.replace(/[^0-9.]/g, ""));
  if (!Number.isFinite(number)) return null;
  return number > 1000 ? Math.round(number / 1000) : Math.round(number);
}

function inferOwner(tags = {}, lat = 0, lon = 0) {
  const text = `${tags.operator || ""} ${tags.owner || ""} ${tags.name || ""}`.toLowerCase();
  if (text.includes("clp") || text.includes("china light")) return "CLP";
  if (text.includes("hongkong electric") || text.includes("hong kong electric") || text.includes("hke")) return "HKE";
  if (lat < 22.31 && lon > 114.08) return "HKE";
  return "CLP";
}

function geometryPoints(element) {
  if (Array.isArray(element.geometry) && element.geometry.length) {
    return element.geometry
      .filter((item) => Number.isFinite(item.lat) && Number.isFinite(item.lon))
      .map((item) => [item.lon, item.lat]);
  }

  if (Array.isArray(element.members)) {
    const points = [];
    element.members.forEach((member) => {
      if (!Array.isArray(member.geometry)) return;
      member.geometry.forEach((item) => {
        if (Number.isFinite(item.lat) && Number.isFinite(item.lon)) points.push([item.lon, item.lat]);
      });
    });
    return points;
  }

  return [];
}

function elementPoint(element) {
  if (Number.isFinite(element.lat) && Number.isFinite(element.lon)) return [element.lon, element.lat];
  if (element.center && Number.isFinite(element.center.lat) && Number.isFinite(element.center.lon)) return [element.center.lon, element.center.lat];
  const geometry = geometryPoints(element);
  return geometry.length ? geometry[Math.floor(geometry.length / 2)] : null;
}

function uniqueById(items) {
  return [...new Map(items.map((item) => [item.id, item])).values()];
}

function parseInfrastructure(elements = []) {
  const assets = [];
  const circuits = [];

  elements.forEach((element) => {
    const tags = element.tags || {};
    const power = tags.power;
    const voltage = parseVoltage(tags.voltage);
    const geometry = geometryPoints(element);
    const point = elementPoint(element);

    if (["line", "cable", "minor_line"].includes(power) && geometry.length >= 2) {
      circuits.push({
        id: `osm-${element.type}-${element.id}`,
        owner: inferOwner(tags, geometry[0]?.[1], geometry[0]?.[0]),
        voltage,
        cableType:
          power === "cable" ||
          tags.location === "underwater" ||
          tags.location === "submarine" ||
          tags.location === "underground"
            ? "submarine / cable"
            : "overhead / line",
        points: geometry,
        name: tags.name || tags.ref || `${voltage || "Unspecified"} kV public circuit`,
        circuits: tags.circuits || tags.cables || null,
        osm: true,
      });
      return;
    }

    if (!point || !["plant", "generator", "substation", "station"].includes(power)) return;
    const [lon, lat] = point;
    assets.push({
      id: `osm-${element.type}-${element.id}`,
      kind: power === "generator" || power === "plant" ? "plant" : "substation",
      name: tags.name || tags["name:en"] || `${power} ${element.id}`,
      owner: inferOwner(tags, lat, lon),
      voltage,
      source: tags.source || tags["plant:source"] || tags["generator:source"] || "unspecified",
      lat,
      lon,
      osm: true,
    });
  });

  return {
    assets: uniqueById([...assets, ...fallbackAssets.filter((item) => item.kind === "control")]),
    circuits: uniqueById(circuits),
  };
}


function normalisePythonTopology(payload = {}) {
  const sourceAssets = payload.assets || payload.nodes || payload.buses || [];
  const sourceCircuits = payload.circuits || payload.lines || payload.edges || payload.links || [];

  const assets = sourceAssets
    .map((asset, index) => ({
      id: String(asset.id ?? asset.name ?? `python-node-${index}`),
      kind: asset.kind || asset.type || (asset.generator || asset.source ? "plant" : "substation"),
      name: asset.name || asset.label || String(asset.id ?? `Node ${index + 1}`),
      owner: asset.owner || asset.operator || "Unknown",
      voltage: parseVoltage(asset.voltage ?? asset.kv ?? asset.voltage_kv),
      source: asset.source || asset.energy_source || asset.fuel || "unspecified",
      lat: Number(asset.lat ?? asset.latitude ?? asset.y),
      lon: Number(asset.lon ?? asset.lng ?? asset.longitude ?? asset.x),
      note: asset.note || asset.description || "",
      python: true,
    }))
    .filter((asset) => Number.isFinite(asset.lat) && Number.isFinite(asset.lon));

  const assetById = new Map(assets.map((asset) => [String(asset.id), asset]));

  const circuits = sourceCircuits
    .map((circuit, index) => {
      let points = circuit.points || circuit.geometry || circuit.coordinates || circuit.path || [];
      if (!Array.isArray(points) || points.length < 2) {
        const from = assetById.get(String(circuit.from ?? circuit.source ?? circuit.u ?? ""));
        const to = assetById.get(String(circuit.to ?? circuit.target ?? circuit.v ?? ""));
        if (from && to) points = [[from.lon, from.lat], [to.lon, to.lat]];
      }

      points = Array.isArray(points)
        ? points
            .map((point) => Array.isArray(point)
              ? [Number(point[0]), Number(point[1])]
              : [Number(point.lon ?? point.lng ?? point.longitude ?? point.x), Number(point.lat ?? point.latitude ?? point.y)])
            .filter(([lon, lat]) => Number.isFinite(lon) && Number.isFinite(lat))
        : [];

      if (points.length < 2) return null;

      return {
        id: String(circuit.id ?? circuit.name ?? `python-circuit-${index}`),
        name: circuit.name || circuit.label || `Circuit ${index + 1}`,
        owner: circuit.owner || circuit.operator || "Unknown",
        voltage: parseVoltage(circuit.voltage ?? circuit.kv ?? circuit.voltage_kv),
        cableType: circuit.cableType || circuit.cable_type || circuit.type || "overhead / line",
        circuits: circuit.circuits || circuit.number_of_circuits || null,
        points,
        python: true,
      };
    })
    .filter(Boolean);

  if (!assets.length && !circuits.length) {
    throw new Error("Python topology export does not contain valid assets or circuits");
  }

  return {
    assets: uniqueById(assets),
    circuits: uniqueById(circuits),
  };
}

async function requestPythonTopology() {
  const response = await fetch(TOPOLOGY_URL, { cache: "no-store" });
  if (!response.ok) throw new Error(`Python topology export returned ${response.status}`);
  return normalisePythonTopology(await response.json());
}

async function requestOverpass(query) {
  let lastError = null;

  for (const endpoint of OVERPASS_URLS) {
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8" },
        body: new URLSearchParams({ data: query }),
      });

      if (!response.ok) throw new Error(`Overpass returned ${response.status}`);
      return await response.json();
    } catch (error) {
      lastError = error;
    }
  }

  throw lastError || new Error("Public infrastructure API unavailable");
}

export default function useGridInfrastructure() {
  const [data, setData] = useState({
    assets: fallbackAssets,
    circuits: fallbackCircuits,
    mode: "fallback",
    loading: true,
    error: null,
  });

  const refresh = useCallback(async () => {
    setData((current) => ({ ...current, loading: true }));

    const query = `[out:json][timeout:28];
      (
        node["power"~"plant|generator|substation|station"](${HK_BBOX});
        way["power"~"plant|generator|substation|station|line|cable|minor_line"](${HK_BBOX});
        relation["power"~"plant|substation|station|line|cable"](${HK_BBOX});
      );
      out center geom tags;`;

    if (TOPOLOGY_MODE !== "osm") {
      try {
        const parsed = await requestPythonTopology();
        setData({
          ...parsed,
          mode: "python-topology",
          loading: false,
          error: null,
        });
        return;
      } catch (pythonError) {
        if (TOPOLOGY_MODE === "python") {
          setData({
            assets: fallbackAssets,
            circuits: fallbackCircuits,
            mode: "fallback",
            loading: false,
            error: pythonError instanceof Error ? pythonError.message : "Python topology export unavailable",
          });
          return;
        }
      }
    }

    try {
      const payload = await requestOverpass(query);
      const parsed = parseInfrastructure(payload.elements || []);

      if (!parsed.assets.length && !parsed.circuits.length) {
        throw new Error("No public OSM grid features returned");
      }

      setData({
        ...parsed,
        mode: "osm-live",
        loading: false,
        error: null,
      });
    } catch (error) {
      setData({
        assets: fallbackAssets,
        circuits: fallbackCircuits,
        mode: "fallback",
        loading: false,
        error: error instanceof Error ? error.message : "Infrastructure API unavailable",
      });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return useMemo(() => ({ ...data, refresh }), [data, refresh]);
}
