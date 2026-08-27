# Lenie AI Assistant — Browser Extension

Chrome/Kiwi browser extension for capturing webpages and sending them to the Lenie AI backend. Supports webpages, links, YouTube videos, movies, individual Facebook or LinkedIn posts, and an open Gmail message.

After a successful send, the popup states whether the request reached NAS or AWS and shows the returned document ID. AWS returns its DynamoDB document ID while the import is queued for later synchronization to NAS.

For a social media post the extension sends only the editable post text. Comments, service UI and page HTML are not imported. If Facebook or LinkedIn hides the post content, paste it into the displayed text field before sending.

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
