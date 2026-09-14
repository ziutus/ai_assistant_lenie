import React from "react";
import axios from "axios";
import { NavLink } from "react-router-dom";
import { AuthorizationContext } from "../context/authorizationContext";

interface UpcomingBirthday {
  contact_id: number;
  display_name: string;
  groups: { id: number; name: string }[];
  birthday_month: number;
  birthday_day: number;
  has_year: boolean;
  next_occurrence: string;
  days_until: number;
  turning_age: number | null;
}

const months = [
  "stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca",
  "lipca", "sierpnia", "września", "października", "listopada", "grudnia",
];
const rowStyle: React.CSSProperties = { display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" };
const chipStyle: React.CSSProperties = { display: "inline-block", padding: "2px 8px", borderRadius: 12, background: "#eef2ff" };
const ageLabel = (age: number) => {
  const years = age === 1 ? "rok" : age % 10 >= 2 && age % 10 <= 4 && (age % 100 < 12 || age % 100 > 14) ? "lata" : "lat";
  return `(kończy ${age} ${years})`;
};

const ContactBirthdays = () => {
  const { apiKey, apiUrl } = React.useContext(AuthorizationContext);
  const [birthdays, setBirthdays] = React.useState<UpcomingBirthday[]>([]);
  const [days, setDays] = React.useState(30);
  const [isLoading, setIsLoading] = React.useState(true);
  const [message, setMessage] = React.useState("");
  const [isError, setIsError] = React.useState(false);
  const headers = { "Content-Type": "application/json", "x-api-key": `${apiKey}` };
  const report = (text: string, error = false) => { setMessage(text); setIsError(error); };

  React.useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setBirthdays([]); report("");
    axios.get(`${apiUrl}/contacts/upcoming_birthdays`, { params: { days }, headers })
      .then(response => {
        if (!cancelled) setBirthdays(response.data.upcoming_birthdays);
      }).catch(error => {
        if (!cancelled) report(`Nie udało się pobrać nadchodzących urodzin: ${error.response?.data?.message || error.message}`, true);
      }).finally(() => { if (!cancelled) setIsLoading(false); });
    return () => { cancelled = true; };
  }, [apiUrl, apiKey, days]);

  return <div>
    <h2>Nadchodzące urodziny</h2>
    {message && <p role={isError ? "alert" : "status"} style={{ color: isError ? "#b91c1c" : "#166534" }}>{message}</p>}
    {isLoading && <p>Ładowanie…</p>}
    <label>Zakres <select value={days} onChange={event => setDays(Number(event.target.value))}>
      {[7, 14, 30, 60, 90].map(value => <option key={value} value={value}>{value} dni</option>)}
    </select></label>
    <ul style={{ listStyle: "none", padding: 0 }}>
      {birthdays.map(birthday => <li key={birthday.contact_id}
        style={{ padding: "12px 0", borderBottom: "1px solid #eee" }}>
        <div style={rowStyle}>
          <NavLink to={`/contacts/${birthday.contact_id}`}>{birthday.display_name}</NavLink>
          <span>{birthday.birthday_day} {months[birthday.birthday_month - 1]}</span>
          <span>
            {birthday.days_until === 0 ? "dziś" : birthday.days_until === 1 ? "jutro" : `za ${birthday.days_until} dni`}
            {birthday.turning_age !== null && ` ${ageLabel(birthday.turning_age)}`}
          </span>
        </div>
        {birthday.groups.length > 0 && <div style={{ ...rowStyle, marginTop: 6 }}>
          {birthday.groups.map(group => <NavLink key={group.id} style={chipStyle} to={`/contact_groups/${group.id}`}>
            {group.name}
          </NavLink>)}
        </div>}
      </li>)}
    </ul>
    {!isLoading && !isError && !birthdays.length && <p style={{ color: "#667" }}>Brak urodzin w ciągu najbliższych {days} dni.</p>}
  </div>;
};

export default ContactBirthdays;
