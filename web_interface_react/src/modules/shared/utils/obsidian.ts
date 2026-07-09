import { loadObsidianVaultName } from "../services/storage";

// Vault name is read per-device (see storage.ts) since Obsidian Sync can use a
// different display name per device for the same synced vault. If unset, the
// `vault` param is omitted — Obsidian falls back to the currently open vault.
export const buildObsidianNoteUrl = (notePath: string): string => {
  const withoutExtension = notePath.replace(/\.md$/i, "");
  const vaultName = loadObsidianVaultName();
  const vaultParam = vaultName ? `vault=${encodeURIComponent(vaultName)}&` : "";
  return `obsidian://open?${vaultParam}file=${encodeURIComponent(withoutExtension)}`;
};
