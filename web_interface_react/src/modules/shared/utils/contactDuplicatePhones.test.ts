import { describe, expect, it } from "vitest";
import { havePhoneConflict, isNameOnlyPhoneConflict } from "./contactDuplicatePhones";

describe("havePhoneConflict", () => {
  it.each([
    [null, "123456789", false],
    [undefined, "123456789", false],
    ["", "123456789", false],
    ["   ", "123456789", false],
    ["+() -", "123456789", false],
    ["", null, false],
    ["123 456-789", "(123)456789", false],
    ["+48 123 456 789", "123456789", false],
    ["0048 123456789", "+48 123456789", false],
    ["+48 123456789", "987654321", true],
    ["123456789", "123456788", true],
    ["12345", "12345", false],
    ["12345", "4812345", true],
    ["+48 123456789", "+49 123456789", true],
  ] as const)("compares %s and %s symmetrically", (a, b, expected) => {
    expect(havePhoneConflict(a, b)).toBe(expected);
    expect(havePhoneConflict(b, a)).toBe(expected);
  });
});

describe("isNameOnlyPhoneConflict", () => {
  const pair = { contact_a: { phone_number: "123456789" }, contact_b: { phone_number: "987654321" }, reasons: [] };

  it("hides conflicting phones only for name-only matches", () => {
    expect(isNameOnlyPhoneConflict(pair)).toBe(true);
    for (const reason of ["ten sam numer telefonu", "ten sam adres e-mail", "ta sama data urodzenia"]) {
      expect(isNameOnlyPhoneConflict({ ...pair, reasons: [reason] })).toBe(false);
    }
  });

  it("treats a shared group alone as a name-only match", () => {
    expect(isNameOnlyPhoneConflict({ ...pair, reasons: ["wspólna grupa"] })).toBe(true);
    expect(isNameOnlyPhoneConflict({ ...pair, reasons: ["wspólna grupa", "ten sam adres e-mail"] })).toBe(false);
  });

  it("keeps name-only matches with missing or equivalent phones", () => {
    expect(isNameOnlyPhoneConflict({ ...pair, contact_b: { phone_number: null } })).toBe(false);
    expect(isNameOnlyPhoneConflict({ ...pair, contact_b: { phone_number: "+48 123456789" } })).toBe(false);
  });
});
