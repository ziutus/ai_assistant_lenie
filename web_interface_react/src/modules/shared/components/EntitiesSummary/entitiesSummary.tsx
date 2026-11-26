import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../../context/authorizationContext";
import { describeRequestError, type RequestErrorInfo } from "../../utils/requestError";
import RequestErrorDetails from "../RequestErrorDetails/requestErrorDetails";
import type { EntitiesByType, EntityItem } from "../EntitiesPanel/entitiesPanel";

type Entities = Partial<EntitiesByType> & {
  eventName?: EntityItem[]; productName?: EntityItem[]; conceptName?: EntityItem[];
};
interface Summary { entities: Entities; countries: number; nerUnavailableAt: string | null }

const ACTIVE_JOB = ["queued", "running", "cancel_requested"];

// Same rows as the review page: country mentions and rejected places are not listed as entities there.
function counts({ entities, countries }: Summary): [string, number][] {
  const listed = (items: EntityItem[] | undefined) => (items ?? [])
    .filter((item) => !item.is_country && item.place_verification_status !== "rejected").length;
  return ([
    ["Osoby", entities.persName?.length ?? 0],
    ["Organizacje i źródła", listed(entities.orgName)],
    ["Miejsca", listed(entities.geogName) + listed(entities.placeName)],
    ["Państwa", countries],
    ["Wydarzenia", entities.eventName?.length ?? 0],
    ["Produkty i systemy", entities.productName?.length ?? 0],
    ["Pojęcia", entities.conceptName?.length ?? 0],
    ["Infrastruktura", entities.facility?.length ?? 0],
  ] as [string, number][]).filter(([, count]) => count > 0);
}

/**
 * The editor's short view of a document's NER entities: how many there are, a button that detects them and a link to
 * `/ner/:id`, where they are reviewed and corrected. Mount it with `key={docId}`.
 */
const EntitiesSummary = ({ docId, externalDisabled, onBusyChange, refreshKey }: {
  docId: number | string; externalDisabled?: boolean; onBusyChange?: (busy: boolean) => void; refreshKey?: number;
}) => {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [summary, setSummary] = React.useState<Summary | null>(null);
  const [loadError, setLoadError] = React.useState(false);
  const [jobStatus, setJobStatus] = React.useState<string | null>(null);
  const [detecting, setDetecting] = React.useState(false);
  const [message, setMessage] = React.useState("");
  const [error, setError] = React.useState<RequestErrorInfo | null>(null);
  const headers = React.useMemo(() => ({
    "Content-Type": "application/x-www-form-urlencoded", "x-api-key": `${apiKey}`,
  }), [apiKey]);

  const load = React.useCallback(() => {
    axios.get(`${apiUrl}/website_entities`, { params: { id: docId }, headers })
      .then((response) => {
        setSummary({
          entities: response.data.entities ?? {}, countries: response.data.countries?.length ?? 0,
          nerUnavailableAt: response.data.ner_unavailable_at ?? null,
        });
        setLoadError(false);
      })
      .catch(() => setLoadError(true));
    axios.get(`${apiUrl}/website_entities/enrichment_job`, { params: { id: docId }, headers })
      .then((response) => setJobStatus(response.data.job?.status ?? null))
      .catch(() => undefined);
  }, [docId, apiUrl, headers]);

  React.useEffect(() => { load(); }, [load, refreshKey]);

  const verifying = jobStatus !== null && ACTIVE_JOB.includes(jobStatus);
  React.useEffect(() => {
    if (!verifying) return undefined;
    const timer = window.setInterval(load, 3000);
    return () => window.clearInterval(timer);
  }, [verifying, load]);

  const detect = async () => {
    setDetecting(true);
    onBusyChange?.(true);
    setMessage("");
    setError(null);
    const startedAt = Date.now();
    try {
      // The same long timeout as on the review page: a long transcript needs minutes of server work.
      const response = await axios.post(`${apiUrl}/website_entities`, { id: docId }, { headers, timeout: 600000 });
      setJobStatus(response.data.enrichment_job?.status ?? null);
      setMessage(response.data.refreshed === 0
        ? "Nie wykryto żadnych osób ani miejsc w tym dokumencie."
        : "Wykryto encje. Trwa ich pełna weryfikacja w tle.");
      load();
    } catch (requestError: any) {
      setError(requestError.response?.data?.ner_unavailable
        ? { summary: "Serwis NER jest niedostępny — spróbuj ponownie za chwilę.", details: "" }
        : describeRequestError(requestError, "Nie udało się wykryć encji", { startedAt, context: { Dokument: docId } }));
    } finally {
      setDetecting(false);
      onBusyChange?.(false);
    }
  };

  const rows = summary ? counts(summary) : [];
  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <strong>Etap 2: osoby, miejsca i organizacje</strong>
        <button type="button" className="button" disabled={detecting || verifying || externalDisabled} onClick={detect}>
          {detecting ? "Wykrywam..." : "Wykryj osoby, miejsca i obiekty"}
        </button>
        <NavLink className="button" to={`/ner/${docId}`} style={{ fontSize: "0.85em" }}>
          🏷️ Przegląd NER
        </NavLink>
      </div>
      <p style={{ margin: "6px 0 0", color: "#475569" }}>
        {loadError ? "Nie udało się pobrać encji."
          : !summary ? "Wczytuję encje…"
            : rows.length === 0 ? "Brak zapisanych encji."
              : rows.map(([label, count]) => `${label}: ${count}`).join(" · ")}
      </p>
      <p style={{ margin: "4px 0 0", color: "#64748b", fontSize: "0.85em" }}>
        Listę encji, ich weryfikację i poprawki znajdziesz w „Przegląd NER”.
      </p>
      {summary?.nerUnavailableAt && (
        <div style={{ marginTop: 6, color: "#9a3412", fontSize: "0.9em" }}>
          ⚠️ Serwis NER był niedostępny ({new Date(summary.nerUnavailableAt).toLocaleString("pl-PL")}) — liczby mogą
          być niepełne.
        </div>
      )}
      <div role="status" aria-live="polite">
        {message && <div style={{ marginTop: 6, color: "#2e7d43" }}>{message}</div>}
        {verifying && <div style={{ marginTop: 6, color: "#667" }}>Pełna weryfikacja encji trwa w tle.</div>}
        {jobStatus === "failed" && (
          <div style={{ marginTop: 6, color: "#a33" }}>Pełna weryfikacja encji nie powiodła się.</div>
        )}
      </div>
      {error && (
        <div role="alert" style={{ marginTop: 6, color: "#a33" }}>
          {error.summary}
          {error.details && <RequestErrorDetails details={error.details} />}
        </div>
      )}
    </div>
  );
};

export default EntitiesSummary;
