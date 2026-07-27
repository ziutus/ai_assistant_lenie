import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

type Job = {
  id: string;
  type: string;
  status: string;
  attempt: number;
  parameters?: unknown;
  progress?: unknown;
  result?: unknown;
  error?: string | null;
};

const formatDetails = (job: Job) => job.error || job.result || job.progress || job.parameters || "—";

export default function Jobs() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const [rows, setRows] = React.useState<Job[]>([]);
  const [message, setMessage] = React.useState("");

  const load = React.useCallback(async () => {
    const response = await fetch(`${apiUrl}/jobs`, { headers: { "x-api-key": apiKey || "" } });
    if (!response.ok) {
      setMessage(`Nie udało się pobrać jobów (${response.status})`);
      return;
    }
    const data = await response.json();
    setRows(data.jobs || []);
  }, [apiUrl, apiKey]);

  React.useEffect(() => { void load(); }, [load]);

  return (
    <section>
      <h1>Joby</h1>
      {message && <p role="alert">{message}</p>}
      <button type="button" onClick={() => void load()}>Odśwież</button>
      <div style={{ overflowX: "auto", marginTop: "1rem" }}>
        <table>
          <thead>
            <tr><th>Typ</th><th>Status</th><th>Próba</th><th>Szczegóły</th></tr>
          </thead>
          <tbody>
            {rows.map((job) => (
              <tr key={job.id}>
                <td>{job.type}</td>
                <td>{job.status}</td>
                <td>{job.attempt}</td>
                <td>
                  <details>
                    <summary>pokaż</summary>
                    <pre>{JSON.stringify(formatDetails(job), null, 2)}</pre>
                  </details>
                </td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={4}>Brak jobów</td></tr>}
          </tbody>
        </table>
      </div>
    </section>
  );
}
