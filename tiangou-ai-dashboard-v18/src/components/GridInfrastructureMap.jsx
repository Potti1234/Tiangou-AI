
import React, { useMemo, useState } from "react";
import {
  Building2,
  Cable,
  ExternalLink,
  Factory,
  Filter,
  Layers3,
  MapPinned,
  RadioTower,
  RefreshCcw,
  Zap,
} from "lucide-react";
import useGridInfrastructure from "../hooks/useGridInfrastructure";
import { StatusBadge, cx } from "./ui";

function voltageGroup(voltage) {
  if (voltage >= 400) return "400";
  if (voltage >= 250) return "275";
  if (voltage >= 120) return "132";
  return "other";
}

function createMapDocument({ assets, circuits, resourcesOnly, publicMode }) {
  const safeAssets = JSON.stringify(assets).replace(/</g, "\\u003c");
  const safeCircuits = JSON.stringify(circuits).replace(/</g, "\\u003c");

  return `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <link rel="stylesheet" href="https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.css" />
  <style>
    :root{
      --water:#dcecef;--land:#f6f5ee;--ink:#12343d;--muted:#5d777c;
      --plant:#16836b;--substation:#397db8;--control:#7659a6;
      --kv400:#7659a6;--kv275:#b8781b;--kv132:#397db8;--other:#6f8589;
    }
    html,body,#map{width:100%;height:100%;margin:0;background:var(--water);font-family:Aptos,"Segoe UI",Arial,sans-serif}
    .maplibregl-popup-content{padding:11px 12px;border-radius:8px;background:#fff;color:var(--ink);border:1px solid rgba(24,84,92,.24);box-shadow:0 10px 28px rgba(20,61,68,.18)}
    .maplibregl-popup-close-button{color:#607b80;font-size:17px}
    .map-popup strong,.map-popup span{display:block}.map-popup strong{font-size:13px}.map-popup span{margin-top:4px;color:#587479;font-size:11px;line-height:1.35}
    .maplibregl-ctrl-group{overflow:hidden;border:1px solid rgba(24,84,92,.18);border-radius:8px;background:rgba(255,255,255,.94)}
    .maplibregl-ctrl-attrib{font-size:9px;background:rgba(255,255,255,.86)!important;color:#587479}
    .maplibregl-ctrl-attrib a{color:#176f75}
    .legend{position:absolute;z-index:4;left:12px;bottom:12px;max-width:460px;display:grid;gap:7px;padding:10px;border:1px solid rgba(24,84,92,.18);border-radius:9px;background:rgba(255,255,255,.94);box-shadow:0 10px 22px rgba(20,61,68,.12)}
    .legend strong{color:var(--ink);font-size:11px;letter-spacing:.06em;text-transform:uppercase}
    .legend-row{display:flex;flex-wrap:wrap;gap:8px 12px}
    .legend span{display:inline-flex;align-items:center;gap:5px;color:#46666c;font-size:10px}
    .dot{width:9px;height:9px;border-radius:50%;display:inline-block}
    .line{width:20px;display:inline-block;border-top:3px solid currentColor}
    .dash{border-top-style:dashed}
    .plant{background:var(--plant)}.substation{background:var(--substation)}.control{background:var(--control)}
    .kv400{color:var(--kv400)}.kv275{color:var(--kv275)}.kv132{color:var(--kv132)}.other{color:var(--other)}
    .loading{position:absolute;z-index:5;inset:0;display:grid;place-items:center;color:#41676c;background:#e8f2f2;font-size:13px;font-weight:700}
  </style>
</head>
<body>
  <div id="map"></div>
  <div class="loading" id="loading">Loading real Hong Kong geography…</div>
  <div class="legend">
    <strong>${resourcesOnly ? "Generation resources and grid connections" : "Public high-voltage grid infrastructure"}</strong>
    <div class="legend-row">
      <span><i class="dot plant"></i>Power station</span>
      ${resourcesOnly ? "" : '<span><i class="dot substation"></i>Substation</span><span><i class="dot control"></i>Control centre</span>'}
    </div>
    <div class="legend-row">
      <span class="kv400"><i class="line"></i>400 kV</span>
      <span class="kv275"><i class="line"></i>275 kV</span>
      <span class="kv132"><i class="line"></i>132 kV</span>
      <span class="other"><i class="line dash"></i>Cable / submarine route</span>
    </div>
  </div>

  <script src="https://unpkg.com/maplibre-gl@5.24.0/dist/maplibre-gl.js"></script>
  <script>
    const assets = ${safeAssets};
    const circuits = ${safeCircuits};
    const publicMode = ${publicMode ? "true" : "false"};

    function minimalise(style){
      const allow = /(background|water|waterway|landcover|landuse|park|natural|coast|boundary)/i;
      const reject = /(road|street|transport|rail|bridge|tunnel|building|poi|place|label|housenum|airport|ferry|transit)/i;
      style.layers = (style.layers || []).filter(layer => {
        const key = String(layer.id || "") + " " + String(layer["source-layer"] || "");
        if(layer.type === "background") return true;
        return allow.test(key) && !reject.test(key) && layer.type !== "symbol";
      });
      style.layers = style.layers.map(layer => {
        const next = {...layer, paint:{...(layer.paint || {})}};
        if(next.type === "background") next.paint["background-color"] = "#dcecef";
        if(next.id && /water/i.test(next.id) && next.type === "fill") next.paint["fill-color"] = "#dcecef";
        if(next.id && /(landcover|landuse|park|natural)/i.test(next.id) && next.type === "fill") {
          next.paint["fill-opacity"] = 0.58;
        }
        if(next.id && /(boundary|coast)/i.test(next.id) && next.type === "line") {
          next.paint["line-color"] = "#93b0b5";
          next.paint["line-opacity"] = 0.72;
        }
        return next;
      });
      return style;
    }

    function fallbackStyle(){
      return {
        version:8,
        sources:{
          "carto-light":{
            type:"raster",
            tiles:["https://a.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}.png"],
            tileSize:256,
            attribution:"© OpenStreetMap contributors © CARTO"
          }
        },
        layers:[
          {id:"background",type:"background",paint:{"background-color":"#dcecef"}},
          {id:"carto-light",type:"raster",source:"carto-light",paint:{"raster-opacity":0.74,"raster-saturation":-0.92,"raster-contrast":-0.18}}
        ]
      };
    }

    async function loadStyle(){
      try{
        const response = await fetch("https://tiles.openfreemap.org/styles/positron");
        if(!response.ok) throw new Error("OpenFreeMap style unavailable");
        return minimalise(await response.json());
      }catch(error){
        return fallbackStyle();
      }
    }

    function lineWidthExpression(){
      return ["interpolate",["linear"],["zoom"],8,
        ["match",["get","voltage"],400,2.3,275,2.0,132,1.55,1.2],
        13,
        ["match",["get","voltage"],400,6.6,275,5.7,132,4.6,3.6]
      ];
    }

    loadStyle().then(style => {
      const map = new maplibregl.Map({
        container:"map",
        style,
        center:[114.13,22.34],
        zoom:10.15,
        minZoom:8.5,
        maxZoom:16,
        attributionControl:true
      });

      map.addControl(new maplibregl.NavigationControl({visualizePitch:true}),"top-right");
      map.addControl(new maplibregl.FullscreenControl(),"top-right");

      map.on("load", () => {
        document.getElementById("loading").style.display = "none";

        const assetFeatures = assets.map(asset => ({
          type:"Feature",
          geometry:{type:"Point",coordinates:[asset.lon,asset.lat]},
          properties:{
            id:asset.id,name:asset.name,kind:asset.kind,owner:asset.owner||"Unknown",
            voltage:asset.voltage||"",source:asset.source||"",note:asset.note||""
          }
        }));

        const circuitFeatures = circuits.map(circuit => ({
          type:"Feature",
          geometry:{type:"LineString",coordinates:circuit.points},
          properties:{
            id:circuit.id,name:circuit.name||"Transmission circuit",owner:circuit.owner||"Unknown",
            voltage:circuit.voltage||0,cableType:circuit.cableType||"line",
            submarine:String(circuit.cableType||"").includes("submarine"),
            cable:String(circuit.cableType||"").includes("cable"),
            circuits:circuit.circuits||""
          }
        }));

        map.addSource("grid-circuits",{type:"geojson",data:{type:"FeatureCollection",features:circuitFeatures}});
        map.addLayer({
          id:"grid-circuit-shadow",type:"line",source:"grid-circuits",
          paint:{"line-color":"rgba(255,255,255,.88)","line-width":["+",lineWidthExpression(),2.4],"line-opacity":.86}
        });
        map.addLayer({
          id:"grid-circuits",type:"line",source:"grid-circuits",
          paint:{
            "line-color":["match",["get","voltage"],400,"#7659a6",275,"#b8781b",132,"#397db8","#6f8589"],
            "line-width":lineWidthExpression(),
            "line-opacity":publicMode?.96:.86,
            "line-dasharray":["case",["any",["boolean",["get","submarine"],false],["boolean",["get","cable"],false]],["literal",[2,1.4]],["literal",[1,0]]]
          }
        });
        map.addLayer({
          id:"grid-circuit-labels",type:"symbol",source:"grid-circuits",minzoom:10.2,
          layout:{
            "symbol-placement":"line",
            "text-field":["case",[">",["get","voltage"],0],["concat",["to-string",["get","voltage"]]," kV"],""],
            "text-size":10,
            "text-allow-overlap":false
          },
          paint:{"text-color":"#31565e","text-halo-color":"rgba(255,255,255,.92)","text-halo-width":1.5}
        });

        map.addSource("grid-assets",{type:"geojson",data:{type:"FeatureCollection",features:assetFeatures}});
        map.addLayer({
          id:"grid-assets",type:"circle",source:"grid-assets",
          paint:{
            "circle-radius":["match",["get","kind"],"plant",8.6,"control",7.4,"substation",5.8,5],
            "circle-color":["match",["get","kind"],"plant","#16836b","control","#7659a6","substation","#397db8","#6f8589"],
            "circle-stroke-color":"#ffffff","circle-stroke-width":1.9,"circle-opacity":.98
          }
        });
        map.addLayer({
          id:"grid-asset-labels",type:"symbol",source:"grid-assets",minzoom:9.3,
          filter:["in",["get","kind"],["literal",${resourcesOnly ? '["plant"]' : '["plant","control","substation"]'}]],
          layout:{
            "text-field":["get","name"],"text-size":10.5,"text-offset":[0,1.25],"text-anchor":"top",
            "text-allow-overlap":false
          },
          paint:{"text-color":"#12343d","text-halo-color":"rgba(255,255,255,.95)","text-halo-width":1.7}
        });

        map.on("click","grid-assets",(event)=>{
          const feature=event.features[0],p=feature.properties;
          new maplibregl.Popup({offset:12})
            .setLngLat(feature.geometry.coordinates)
            .setHTML('<div class="map-popup"><strong>'+p.name+'</strong><span>'+p.owner+(p.voltage?' · '+p.voltage+' kV':'')+'</span><span>'+p.kind+(p.source?' · '+p.source:'')+(p.note?' · '+p.note:'')+'</span></div>')
            .addTo(map);
        });
        map.on("click","grid-circuits",(event)=>{
          const feature=event.features[0],p=feature.properties;
          new maplibregl.Popup({offset:8})
            .setLngLat(event.lngLat)
            .setHTML('<div class="map-popup"><strong>'+p.name+'</strong><span>'+p.owner+(p.voltage?' · '+p.voltage+' kV':'')+'</span><span>'+p.cableType+(p.circuits?' · circuits '+p.circuits:'')+'</span></div>')
            .addTo(map);
        });
        ["grid-assets","grid-circuits"].forEach(layer=>{
          map.on("mouseenter",layer,()=>map.getCanvas().style.cursor="pointer");
          map.on("mouseleave",layer,()=>map.getCanvas().style.cursor="");
        });
      });
    });
  </script>
</body>
</html>`;
}

function MapLegend({ resourcesOnly }) {
  return (
    <div className="infrastructure-map-legend">
      <span><i className="map-legend-dot map-legend-dot--plant" />Power station</span>
      {!resourcesOnly ? <span><i className="map-legend-dot map-legend-dot--substation" />Substation</span> : null}
      {!resourcesOnly ? <span><i className="map-legend-dot map-legend-dot--control" />Control centre</span> : null}
      <span><i className="map-legend-line map-legend-line--400" />400 kV</span>
      <span><i className="map-legend-line map-legend-line--275" />275 kV</span>
      <span><i className="map-legend-line map-legend-line--132" />132 kV</span>
      <span><i className="map-legend-line map-legend-line--cable" />Cable / submarine</span>
    </div>
  );
}

export default function GridInfrastructureMap({
  title = "Hong Kong grid infrastructure",
  compact = false,
  resourcesOnly = false,
}) {
  const infrastructure = useGridInfrastructure();
  const [owner, setOwner] = useState("all");
  const [voltage, setVoltage] = useState("all");
  const [showLines, setShowLines] = useState(true);
  const [showCables, setShowCables] = useState(true);
  const [showSubstations, setShowSubstations] = useState(!resourcesOnly);
  const [showPlants, setShowPlants] = useState(true);
  const [showControl, setShowControl] = useState(!resourcesOnly);

  const filteredAssets = useMemo(() => infrastructure.assets.filter((asset) => {
    if (resourcesOnly && asset.kind !== "plant") return false;
    if (owner !== "all" && asset.owner !== owner) return false;
    if (voltage !== "all" && String(voltageGroup(asset.voltage)) !== String(voltage)) return false;
    if (asset.kind === "plant" && !showPlants) return false;
    if (asset.kind === "substation" && !showSubstations) return false;
    if (asset.kind === "control" && !showControl) return false;
    return true;
  }), [infrastructure.assets, owner, voltage, resourcesOnly, showPlants, showSubstations, showControl]);

  const filteredCircuits = useMemo(() => infrastructure.circuits.filter((circuit) => {
    if (owner !== "all" && circuit.owner !== owner && circuit.owner !== "Shared") return false;
    if (voltage !== "all" && String(voltageGroup(circuit.voltage)) !== String(voltage)) return false;
    const cable = String(circuit.cableType).includes("cable") || String(circuit.cableType).includes("submarine");
    if (cable && !showCables) return false;
    if (!cable && !showLines) return false;
    return true;
  }), [infrastructure.circuits, owner, voltage, showLines, showCables]);

  const mapDocument = useMemo(
    () => createMapDocument({
      assets: filteredAssets,
      circuits: filteredCircuits,
      resourcesOnly,
      publicMode: infrastructure.mode === "osm-live" || infrastructure.mode === "python-topology",
    }),
    [filteredAssets, filteredCircuits, resourcesOnly, infrastructure.mode]
  );

  return (
    <section className={cx("infrastructure-map-card mapcn-map-card", compact && "infrastructure-map-card--compact")}>
      <header className="infrastructure-map-card__header mapcn-map-card__header">
        <div>
          <p className="eyebrow">{resourcesOnly ? "Resource map" : "Grid map"}</p>
          <h3>{title}</h3>
        </div>
        <div className="infrastructure-map-card__status">
          <StatusBadge severity={infrastructure.mode === "fallback" ? "warning" : "stable"}>
            {infrastructure.mode === "python-topology"
              ? "Python topology export"
              : infrastructure.mode === "osm-live"
                ? "Live public OSM geometry"
                : "Curated schematic fallback"}
          </StatusBadge>
          <button className="icon-btn" onClick={infrastructure.refresh} aria-label="Refresh infrastructure layer">
            <RefreshCcw size={16} className={infrastructure.loading ? "is-spinning" : ""} />
          </button>
        </div>
      </header>

      <div className="infrastructure-map-card__toolbar mapcn-map-toolbar">
        <div className="map-filter-group">
          <Filter size={15} />
          <span>Owner</span>
          {["all", "CLP", "HKE"].map((item) => (
            <button className={owner === item ? "is-active" : ""} key={item} onClick={() => setOwner(item)}>
              {item === "all" ? "All" : item}
            </button>
          ))}
        </div>
        <div className="map-filter-group">
          <Zap size={15} />
          <span>kV</span>
          {["all", "400", "275", "132"].map((item) => (
            <button className={String(voltage) === item ? "is-active" : ""} key={item} onClick={() => setVoltage(item)}>
              {item === "all" ? "All" : item}
            </button>
          ))}
        </div>
      </div>

      <div className="mapcn-frame-wrap">
        <iframe title={`${title} interactive map`} srcDoc={mapDocument} />
      </div>

      <div className="infrastructure-map-card__footer mapcn-map-card__footer">
        <MapLegend resourcesOnly={resourcesOnly} />
        <div className="infra-layer-toggles">
          <button className={showLines ? "is-active" : ""} onClick={() => setShowLines(!showLines)}><Layers3 size={14} />Circuits</button>
          <button className={showCables ? "is-active" : ""} onClick={() => setShowCables(!showCables)}><Cable size={14} />Cables</button>
          {!resourcesOnly ? <button className={showSubstations ? "is-active" : ""} onClick={() => setShowSubstations(!showSubstations)}><Building2 size={14} />Substations</button> : null}
          <button className={showPlants ? "is-active" : ""} onClick={() => setShowPlants(!showPlants)}><Factory size={14} />Power stations</button>
          {!resourcesOnly ? <button className={showControl ? "is-active" : ""} onClick={() => setShowControl(!showControl)}><RadioTower size={14} />Control centres</button> : null}
        </div>
        <div className="infrastructure-map-card__source-row">
          <small><MapPinned size={13} /> Real minimal Hong Kong geography from OpenFreeMap · public OSM grid geometry when available</small>
          <a href="https://openinframap.org/#10.1/22.34/114.13" target="_blank" rel="noreferrer">Open public infrastructure detail <ExternalLink size={13} /></a>
        </div>
      </div>
    </section>
  );
}
