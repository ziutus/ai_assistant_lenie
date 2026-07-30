import React, { useRef } from "react";
import { AuthorizationContext } from "../context/authorizationContext";
import useFileSubmit from "../hooks/useFileSubmit";

type Upload = { key: string; filename: string; size: number; format: string };

const formatSize = (size: number) => size < 1024 * 1024
  ? `${Math.ceil(size / 1024)} KB`
  : `${(size / (1024 * 1024)).toFixed(1)} MB`;

const UploadFile = () => {
  const { message, isLoading, isError, isSuccess, submitFile } = useFileSubmit();
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext);
  const fileInput = useRef<HTMLInputElement | null>(null);
  const [uploads, setUploads] = React.useState<Upload[]>([]);
  const [listError, setListError] = React.useState("");

  const loadUploads = React.useCallback(async () => {
    try {
      const response = await fetch(`${apiUrl}/uploads?limit=100`, { headers: { "x-api-key": apiKey ?? "" } });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setUploads(data.uploads ?? []);
      setListError("");
    } catch (error) {
      setListError(`Nie udało się pobrać kolejki plików (${error instanceof Error ? error.message : "błąd połączenia"}).`);
    }
  }, [apiKey, apiUrl]);

  React.useEffect(() => { void loadUploads(); }, [loadUploads]);

  return (
    <div>
      <h2 style={{ marginBottom: "10px" }}>Plik do importu</h2>
      <input
        type="file"
        accept=".pdf,.epub,.mobi,application/pdf,application/epub+zip"
        ref={fileInput}
        style={{ width: "400px" }}
      />

      <div
        className={"flexBox"}
        style={{ maxWidth: "400px", marginTop: "10px", marginBottom: "10px" }}
      >
        <div className="flex-grow"></div>

        {isLoading && <div className="loader"></div>}
        <button
          style={{ marginLeft: "5px" }}
          disabled={isLoading}
          className={"button"}
          onClick={() => void submitFile(fileInput).then((key) => { if (key) return loadUploads(); })}
        >
          Upload
        </button>
      </div>

      {isError && message && <div className="errorText">{message}</div>}
      {isSuccess && message && <div>{message}</div>}

      <section style={{ marginTop: 28, maxWidth: 900 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <h3 style={{ margin: 0 }}>Pliki oczekujące na import ({uploads.length})</h3>
          <button type="button" className="button" onClick={() => void loadUploads()}>Odśwież</button>
        </div>
        <p style={{ color: "#475569" }}>Klucz przekaż importerowi PDF lub agentowi AI jako <code>--storage-key</code>.</p>
        {listError && <p className="errorText">{listError}</p>}
        <div style={{ overflowX: "auto" }}>
          <table style={{ borderCollapse: "collapse", width: "100%" }}>
            <thead><tr><th style={{ textAlign: "left", padding: 8 }}>Plik</th><th style={{ textAlign: "left", padding: 8 }}>Format</th><th style={{ textAlign: "right", padding: 8 }}>Rozmiar</th><th style={{ textAlign: "left", padding: 8 }}>Klucz MinIO</th></tr></thead>
            <tbody>{uploads.map((upload) => <tr key={upload.key} style={{ borderTop: "1px solid #cbd5e1" }}><td style={{ padding: 8 }}>{upload.filename}</td><td style={{ padding: 8 }}>{upload.format.toUpperCase()}</td><td style={{ padding: 8, textAlign: "right" }}>{formatSize(upload.size)}</td><td style={{ padding: 8 }}><code>{upload.key}</code></td></tr>)}{!uploads.length && <tr><td colSpan={4} style={{ padding: 8 }}>Brak plików oczekujących na import.</td></tr>}</tbody>
          </table>
        </div>
      </section>
    </div>
  );
};

export default UploadFile;
