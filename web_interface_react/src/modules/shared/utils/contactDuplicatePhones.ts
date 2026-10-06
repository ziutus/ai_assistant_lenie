// A shared group alone is too weak to count as corroboration of a name match.
const WEAK_REASON = "wspólna grupa";

export const havePhoneConflict = (a: string | null | undefined, b: string | null | undefined): boolean => {
  const first = (a ?? "").replace(/\D/g, "");
  const second = (b ?? "").replace(/\D/g, "");
  if (!first || !second || first === second) return false;
  if (first.length !== second.length && first.length >= 9 && second.length >= 9) {
    return first.slice(-9) !== second.slice(-9);
  }
  return true;
};

export const isNameOnlyPhoneConflict = (pair: {
  contact_a: { phone_number: string | null };
  contact_b: { phone_number: string | null };
  reasons: string[];
}): boolean => pair.reasons.every(reason => reason === WEAK_REASON)
  && havePhoneConflict(pair.contact_a.phone_number, pair.contact_b.phone_number);
