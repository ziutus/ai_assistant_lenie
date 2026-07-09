import React from "react";
import L from "leaflet";
import { GeoJSON, MapContainer, TileLayer, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { COUNTRY_SLUG_TO_ISO3 } from "../../data/countryIso";

export interface CountryTag {
  slug: string;
  name_pl: string;
}

interface Props {
  countries: CountryTag[];
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

/** Map of OpenStreetMap tiles highlighting the countries a geopolitical article discusses.
 *  Desktop-only by convention of the caller (see read.tsx) — loads tiles + a bundled
 *  world-countries GeoJSON only when actually rendered. Small island states / micro-states
 *  missing from the (lightweight, ~250KB) bundled GeoJSON won't appear on the map — they're
 *  still listed as text chips below it so nothing is silently dropped. */
const CountryMap: React.FC<Props> = ({ countries }) => {
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

  const style = React.useCallback(
    (feature?: GeoJSON.Feature): L.PathOptions => (matchedIso.has(String(feature?.id)) ? MATCHED_STYLE : UNMATCHED_STYLE),
    [matchedIso]
  );

  if (countries.length === 0 || error) return null;

  return (
    <div style={{ background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: 10, marginTop: 12 }}>
      <strong style={{ fontSize: "0.85em", display: "block", marginBottom: 8 }}>🌍 Kraje w artykule</strong>
      {geoData && (
        <div style={{ height: 260, borderRadius: 6, overflow: "hidden" }}>
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
            <GeoJSON key={[...matchedIso].sort().join(",")} data={geoData} style={style} />
            <FitToMatched data={geoData} matchedIso={matchedIso} />
          </MapContainer>
        </div>
      )}
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
        {countries.map(c => (
          <span
            key={c.slug}
            style={{
              fontSize: "0.78em", padding: "2px 8px", borderRadius: 999,
              background: matchedIso.has(COUNTRY_SLUG_TO_ISO3[c.slug]) ? "#e0f2fe" : "#f1f5f9",
              color: "#334155",
            }}
          >
            {c.name_pl}
          </span>
        ))}
      </div>
    </div>
  );
};

export default CountryMap;
