# Lenie AI Assistant — Browser Extension

Chrome/Kiwi browser extension for capturing webpages and sending them to the Lenie AI backend. Supports different content types: webpages, links, YouTube videos, and movies.

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
