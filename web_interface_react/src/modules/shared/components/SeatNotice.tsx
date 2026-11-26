export type Seat = { country_added: boolean; address_added: string | null; message: string | null };

/** What the registry check wrote about the organization's seat, or why it wrote nothing. */
export default function SeatNotice({ seat }: { seat?: Seat }) {
  if (!seat) return null;
  return <>
    {seat.country_added && <p role="status">Dodano z rejestru: siedziba w: Polska.</p>}
    {seat.address_added && <p role="status">Dodano adres siedziby: {seat.address_added}.</p>}
    {seat.message && <p role="status">{seat.message}</p>}
  </>;
}
