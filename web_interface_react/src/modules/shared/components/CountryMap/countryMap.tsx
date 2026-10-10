import React from "react";
import L from "leaflet";
import { CircleMarker, GeoJSON, MapContainer, Polyline, TileLayer, Tooltip, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { COUNTRY_SLUG_TO_ISO3 } from "../../data/countryIso";
import { ISO3_TO_NAME_PL } from "../../data/countryNames";

export interface CountryTag {
  slug: string;
  name_pl: string;
  /** Optional kind of tie (organization pages): tints the country and labels it. */
  relation?: string;
  relation_label?: string;
}

/** Tint per tie, strongest first — a country with several ties takes the first one's colour. */
const RELATION_STYLES: { relation: string; label: string; fill: string; stroke: string }[] = [
  { relation: "based_in", label: "siedziba w", fill: "#0369a1", stroke: "#0c4a6e" },
  { relation: "operates_in", label: "działa w", fill: "#ea580c", stroke: "#9a3412" },
  { relation: "linked_to", label: "powiązana z", fill: "#7c3aed", stroke: "#4c1d95" },
];

/** Verified NER place (stage 3, geocode_cache coords) rendered as a point marker. */
export interface PlaceMarker {
  name: string;
  lat: number;
  lon: number;
}

/** Linear infrastructure route (Overpass/OSM data, infra_geometries cache)
 *  rendered as polylines — e.g. a gas pipeline an article discusses.
 *  Coordinates come as GeoJSON MultiLineString (lon/lat order). */
export interface PipelineLine {
  name: string;
  substance?: string | null;
  coordinates: [number, number][][]; // [lon, lat] per GeoJSON
}

interface Props {
  countries: CountryTag[];
  places?: PlaceMarker[];
  pipelines?: PipelineLine[];
  /** Heading above the map; defaults to the article wording used by the reader. */
  title?: string;
}

const GEOJSON_URL = "/geo/world-countries.geo.json";

const MATCHED_STYLE: L.PathOptions = {
  fillColor: "#0369a1",
  fillOpacity: 0.55,
  color: "#0c4a6e",
  weight: 1.2,
};

const UNMATCHED_STYLE: L.PathOptions = {
  fillColor: "#000000",
  fillOpacity: 0,
  color: "#94a3b8",
  weight: 0.4,
};

/** Fits the map view to the bounds of the matched features, once per data change. */
const FitToMatched: React.FC<{ data: GeoJSON.FeatureCollection; matchedIso: Set<string> }> = ({ data, matchedIso }) => {
  const map = useMap();
  React.useEffect(() => {
    const matchedFeatures = data.features.filter(f => matchedIso.has(String(f.id)));
    if (matchedFeatures.length === 0) return;
    const bounds = L.geoJSON({ type: "FeatureCollection", features: matchedFeatures } as GeoJSON.FeatureCollection).getBounds();
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [16, 16], maxZoom: 5 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, matchedIso]);
  return null;
};

/** Fits address/place markers only when country fitting has no priority. */
const FitToPlaces: React.FC<{ places: PlaceMarker[] }> = ({ places }) => {
  const map = useMap();
  React.useEffect(() => {
    const bounds = L.latLngBounds(places.map(p => [p.lat, p.lon] as [number, number]));
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [16, 16], maxZoom: 15 });
  }, [map, places]);
  return null;
};

/** Map of OpenStreetMap tiles highlighting the countries a geopolitical article discusses.
 *  Every country on the map is labeled in Polish (ISO3_TO_NAME_PL) — matched
 *  (article) countries prominently, everything else (including neighbors of
 *  the matched countries, which is the point) dimmed but still legible.
 *  Desktop-only by convention of the caller (see read.tsx) — loads tiles + a bundled
 *  world-countries GeoJSON only when actually rendered. Small island states / micro-states
 *  missing from the (lightweight, ~250KB) bundled GeoJSON won't appear on the map — they're
 *  still listed in the reader's "Encje" → "Państwa" block (EntitiesPanel), so nothing is
 *  silently dropped; this component itself no longer renders a text fallback list. */
const CountryMap: React.FC<Props> = ({ countries, places = [], pipelines = [], title }) => {
  const [geoData, setGeoData] = React.useState<GeoJSON.FeatureCollection | null>(null);
  const [error, setError] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    fetch(GEOJSON_URL)
      .then(r => { if (!r.ok) throw new Error(String(r.status)); return r.json(); })
      .then(data => { if (!cancelled) setGeoData(data); })
      .catch(() => { if (!cancelled) setError(true); });
    return () => { cancelled = true; };
  }, []);

  const matchedIso = React.useMemo(
    () => new Set(countries.map(c => COUNTRY_SLUG_TO_ISO3[c.slug]).filter((iso): iso is string => Boolean(iso))),
    [countries]
  );

  // ISO3 -> every tie label of that country ("działa w", "powiązana z"), and
  // the strongest relation for tinting. Empty when no country carries a relation.
  const relationsByIso = React.useMemo(() => {
    const map = new Map<string, { relations: Set<string>; labels: string[] }>();
    countries.forEach(c => {
      const iso = COUNTRY_SLUG_TO_ISO3[c.slug];
      if (!iso || !c.relation) return;
      const entry = map.get(iso) ?? { relations: new Set<string>(), labels: [] };
      entry.relations.add(c.relation);
      const label = c.relation_label ?? RELATION_STYLES.find(r => r.relation === c.relation)?.label ?? c.relation;
      if (!entry.labels.includes(label)) entry.labels.push(label);
      map.set(iso, entry);
    });
    return map;
  }, [countries]);

  const style = React.useCallback(
    (feature?: GeoJSON.Feature): L.PathOptions => {
      const iso = String(feature?.id);
      if (!matchedIso.has(iso)) return UNMATCHED_STYLE;
      const tint = RELATION_STYLES.find(r => relationsByIso.get(iso)?.relations.has(r.relation));
      return tint ? { ...MATCHED_STYLE, fillColor: tint.fill, color: tint.stroke } : MATCHED_STYLE;
    },
    [matchedIso, relationsByIso]
  );

  // Every country gets its Polish name (ISO3_TO_NAME_PL — the bundled GeoJSON
  // only has English names, and OSM tile labels are whatever language OSM
  // ships per region, e.g. Germany as "Deutschland"). Countries the article
  // actually discusses are labeled prominently; everything else (including
  // their neighbors, which is the point — context for the highlighted
  // countries) gets a smaller, muted label so the map doesn't turn into a
  // wall of text.
  const onEachFeature = React.useCallback(
    (feature: GeoJSON.Feature, layer: L.Layer) => {
      const namePl = ISO3_TO_NAME_PL[String(feature.id)];
      if (!namePl) return;
      const matched = matchedIso.has(String(feature.id));
      const labels = relationsByIso.get(String(feature.id))?.labels;
      layer.bindTooltip(labels?.length ? `${namePl} · ${labels.join(", ")}` : namePl, {
        permanent: true, direction: "center",
        className: matched ? "country-label" : "country-label-dim",
      });
    },
    [matchedIso, relationsByIso]
  );

  if ((countries.length === 0 && places.length === 0 && pipelines.length === 0) || error) return null;

  return (
    <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 10, marginTop: 12 }}>
      <style>{`
        .country-label {
          background: transparent;
          border: none;
          box-shadow: none;
          font-size: 11px;
          font-weight: 600;
          color: #0c2f4a;
          text-shadow: 0 0 3px #ffffff, 0 0 3px #ffffff, 0 0 3px #ffffff;
          padding: 0;
        }
        .country-label::before { display: none; }
        .country-label-dim {
          background: transparent;
          border: none;
          box-shadow: none;
          font-size: 9px;
          font-weight: 500;
          color: #64748b;
          text-shadow: 0 0 2px #ffffff, 0 0 2px #ffffff;
          padding: 0;
        }
        .country-label-dim::before { display: none; }
      `}</style>
      <strong style={{ fontSize: "0.85em", display: "block", marginBottom: 8 }}>
        🌍 {title ?? (places.length > 0 ? "Kraje i miejsca w artykule" : "Kraje w artykule")}
      </strong>
      {relationsByIso.size > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "2px 14px", fontSize: "0.8em", marginBottom: 6 }}>
          {RELATION_STYLES.filter(r => [...relationsByIso.values()].some(v => v.relations.has(r.relation))).map(r => (
            <span key={r.relation}>
              <span style={{ display: "inline-block", width: 10, height: 10, background: r.fill, borderRadius: 2, marginRight: 4 }} />
              {r.label}
            </span>
          ))}
        </div>
      )}
      {geoData && (
        <div style={{ height: 340, borderRadius: 6, overflow: "hidden" }}>
          <MapContainer
            style={{ height: "100%", width: "100%" }}
            center={[20, 10]}
            zoom={2}
            scrollWheelZoom={false}
            attributionControl={true}
          >
            <TileLayer
              url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            />
            <GeoJSON
              key={[...matchedIso].sort().join(",") + "|" + [...relationsByIso].map(([iso, v]) => `${iso}:${[...v.relations].sort()}`).sort().join(",")}
              data={geoData}
              style={style}
              onEachFeature={onEachFeature}
            />
            {pipelines.map(pl =>
              pl.coordinates.map((line, i) => (
                <Polyline
                  key={`${pl.name}-${i}`}
                  positions={line.map(([lon, lat]) => [lat, lon] as [number, number])}
                  pathOptions={{ color: pl.substance === "oil" ? "#7f1d1d" : "#c2410c", weight: 3, opacity: 0.9, dashArray: "6 4" }}
                >
                  {i === 0 && (
                    <Tooltip direction="top" sticky>
                      🛢️ {pl.name}{pl.substance ? ` (${pl.substance})` : ""} — dane © OpenStreetMap
                    </Tooltip>
                  )}
                </Polyline>
              ))
            )}
            {places.map(p => (
              <CircleMarker
                key={`${p.name}-${p.lat}-${p.lon}`}
                center={[p.lat, p.lon]}
                radius={6}
                pathOptions={{ color: "#b45309", fillColor: "#f59e0b", fillOpacity: 0.85, weight: 1.5 }}
              >
                <Tooltip direction="top" offset={[0, -6]}>{p.name}</Tooltip>
              </CircleMarker>
            ))}
            <FitToMatched data={geoData} matchedIso={matchedIso} />
            {matchedIso.size === 0 && places.length > 0 && <FitToPlaces places={places} />}
          </MapContainer>
        </div>
      )}
    </div>
  );
};

export default CountryMap;
