# Lenie AI Assistant — Browser Extension

Chrome/Kiwi browser extension for capturing webpages and sending them to the Lenie AI backend. Supports webpages, links, YouTube videos, movies, individual Facebook or LinkedIn posts, and an open Gmail message.

After a successful send, the popup states whether the request reached NAS or AWS and shows the returned document ID. AWS returns its DynamoDB document ID while the import is queued for later synchronization to NAS.

For a social media post the extension sends the editable post text, without service UI or page HTML. If Facebook or LinkedIn hides the post content, paste it into the displayed text field before sending.

### LinkedIn comments (1.0.58)

1. Open the individual post. Load the comments and expand the replies you want to capture on LinkedIn before opening the extension — the extension does not scroll or click on your behalf.
2. Select **Dołącz komentarze z LinkedIn**. Review the separate editable comments field; remove any unwanted comments there. Each entry keeps the author name and profile link, the relative timestamp, in-body links, and — for replies — who it answers; replies are shown indented under `↳`.
3. Send to create a new post with a separate comments section. The preview always states how many comments/replies were captured and warns that it is only a fragment when the post has more comments than were loaded (LinkedIn's selected sorting/filtering also applies). Only the currently loaded discussion is captured. If the page structure cannot be recognized, the extension shows a warning and you can paste comments manually instead.
4. For an already imported post, select **Zastąp treść istniejącego wpisu… (NAS)**. This explicitly replaces the stored post text and any previous comments with the current preview. It requires the updated NAS backend and a matching existing LinkedIn social post URL. Metadata and analysis history remain; old search vectors and summary are cleared and the document returns to `URL_ADDED`. Run analysis again to include the comments.

New captures can still use AWS. Replacing an existing capture is NAS-only and does not fall back to AWS. Reload the unpacked extension in `chrome://extensions/` after updating these files; restart/deploy the updated backend for replacement support.

Extractor tests (uses jsdom from the installed React frontend dependencies): `node --test web_chrome_extension/tests/*.test.cjs` from the repository root.

For Gmail the extension imports the visible text and sent date of the most recently expanded message in the open conversation. Visible links are kept as `label (URL)` and Gmail redirect URLs are unwrapped locally without opening them. Message-body images are saved as external HTTPS URLs and placed with `[imgN]` markers; 1×1 tracking pixels are ignored. It sends a synthetic `gmail://` identifier, not the Gmail page HTML, and the content remains editable in the popup before sending. It does not scan the inbox or use Google OAuth.

See [CLAUDE.md](CLAUDE.md) for detailed technical documentation (features, API communication, data flow, permissions, directory structure).

## Installation

1. Clone this repository:
   ```bash
   git clone <repository_url>
   ```
2. Open [chrome://extensions/](chrome://extensions/) in Chrome.
3. Enable **Developer mode**.
4. Click **Load unpacked** and select this folder.

Works on **Chrome** (desktop) and **Kiwi Browser** (Android).

## Configuration

1. After installing the extension, click its icon in the browser toolbar.
2. Enter the API key in the "API Key" field.
3. Set the API server URL.
4. Configure additional options: content type, source, AI options, etc.

## Requirements

- Chrome browser with Extensions API v3 support.
- An account at `lenie-ai.eu` to obtain an API key.

## Contributing

Pull requests are welcome! Before submitting changes, make sure your code follows the project standards.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.
