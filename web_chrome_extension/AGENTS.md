# AGENTS.md — Chrome extension operational rules

## Phone distribution folder

Mobile phones (Kiwi Browser) install the extension from a shared Google Drive
folder, not from this repo:

`H:\Mój dysk\krzysiek_prywatne\lenie_ai_chrome`

**Always upload the latest extension version there** after any change to the
extension, once the version has been bumped. Keep the folder identical to the
shipped files:

- Copy every runtime file: `manifest.json`, `popup.html`, `popup.js`,
  `bootstrap.min.css`, `icon16.png`, `icon48.png`, `icon128.png`,
  `linkedin-comments.js`, `facebook-group-members.js`, `README.md`,
  `CHANGELOG.md`. Add any new runtime file the manifest/popup starts using.
  Never copy `tests/` or `.idea/`.
- Rebuild `lenie_ai_chrome.zip` in the same folder from exactly those files,
  with `/` path separators and files at the zip root (use Python `zipfile`;
  PowerShell 5.1 `Compress-Archive` writes `\` separators).
- Verify `manifest.json` `version` in the folder matches the repo.
