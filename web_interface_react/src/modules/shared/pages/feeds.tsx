import React from "react";
import { AuthorizationContext } from "../context/authorizationContext";

type Feed = { id:number; name:string; auto_import:boolean; auto_import_after:string|null; disabled:boolean; last_checked_at:string|null; last_error:string|null };
export default function Feeds() {
  const { apiUrl, apiKey } = React.useContext(AuthorizationContext); const [feeds,setFeeds]=React.useState<Feed[]>([]); const [message,setMessage]=React.useState("");
  const load=React.useCallback(async()=>{ const r=await fetch(`${apiUrl}/feed_sources`,{headers:{"x-api-key":apiKey||""}}); const d=await r.json(); setFeeds(d.feed_sources||[]); },[apiUrl,apiKey]); React.useEffect(()=>{void load();},[load]);
  const check=async(id:number)=>{ const r=await fetch(`${apiUrl}/feed_sources/${id}/check`,{method:"POST",headers:{"x-api-key":apiKey||""}}); setMessage(r.ok?"Check dodany do kolejki":"Nie udało się dodać checku"); };
  return <section><h1>Feedy</h1>{message&&<p>{message}</p>}<table><thead><tr><th>Nazwa</th><th>Auto import</th><th>Próg</th><th>Ostatni check</th><th/></tr></thead><tbody>{feeds.map(f=><tr key={f.id}><td>{f.name}{f.disabled?" (wyłączony)":""}</td><td>{f.auto_import?"tak":"nie"}</td><td>{f.auto_import_after||"—"}</td><td>{f.last_checked_at||"—"}{f.last_error&&<div>{f.last_error}</div>}</td><td><button onClick={()=>void check(f.id)}>Sprawdź teraz</button></td></tr>)}</tbody></table></section>;
}
