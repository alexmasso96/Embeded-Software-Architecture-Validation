"""
AI Test Case Generation — Help dialog.

Explains what each provider needs, the Copilot caveats, and troubleshooting.
The same content is mirrored into the in-app guide.
"""
from PyQt6 import QtWidgets, QtCore


_COPILOT = """
## GitHub Copilot

**What you need:** a GitHub account with an **active Copilot subscription**
(Individual, Business, or Enterprise). No manual token — click **Sign In** and
authorize via GitHub's device flow (you'll enter a short code at
github.com/login/device).

**Models:** Claude and GPT models are served *through* your Copilot subscription
(billed against Copilot, not a separate API key).

**Known limitations (it may not work in every org):**
- Some organizations require third-party OAuth apps to be **admin-approved** —
  sign-in is blocked until approved.
- Orgs with **enforced SSO** may require the token to be SSO-authorized.
- Corporate **proxies/firewalls** can block `api.githubcopilot.com`.
- This uses the same (unofficial) Copilot endpoint the editors use; if GitHub
  changes it, it may stop working. If so, use a direct API-key provider below.
"""

_KEYS = """
## Claude / OpenAI / Gemini (API key)

Each works with its own API key, independent of Copilot — useful if you don't
have a Copilot seat, want separate billing, or as a fallback.

- **Anthropic (Claude):** key from console.anthropic.com → Settings → API Keys.
- **OpenAI (ChatGPT):** key from platform.openai.com → API keys.
- **Google Gemini:** key from aistudio.google.com → API key.

Paste the key in **Configure Providers**. Keys are stored **encrypted on this
computer only** (custom `.aikeys` file in your user profile) and are never
written into the project file.
"""

_USAGE = """
## How to use

1. **Generate the high-level designs first** in the *Test Case Design* tab —
   this writes `*_Test_Case_Design.md` files the AI tab reads.
2. In this tab: pick a **provider** and **model**, point to the **source code**,
   choose the **HLT file** and the **test cases** to generate.
3. (Optional) edit the **Prompt & Rules** — they are saved in the project.
4. Click **Generate**. Results appear on the right and are written to
   `<Model>_LowLevel.md`. Use **Write Back** to fill the original HLT file.
5. Use the **Chat** tab to ask follow-up questions with full context.
"""

_TROUBLE = """
## Troubleshooting

- **"Not signed in / no subscription"** — Copilot account lacks access, or the
  org blocks the OAuth app. Try a direct API-key provider.
- **403 / authentication failed** — bad/expired key, or no model access.
- **No models listed** — provider not configured; open *Configure Providers*.
- **Generation stops** — you pressed Stop, or the prompt exceeded the model's
  limit (reduce selected test cases or source scope).
"""


class AIHelpDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI Test Case Generation — Help")
        self.resize(640, 560)
        lay = QtWidgets.QVBoxLayout(self)
        tabs = QtWidgets.QTabWidget()
        for title, md in (
            ("Copilot", _COPILOT),
            ("API Keys", _KEYS),
            ("How to use", _USAGE),
            ("Troubleshooting", _TROUBLE),
        ):
            browser = QtWidgets.QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setMarkdown(md)
            tabs.addTab(browser, title)
        lay.addWidget(tabs)

        btn = QtWidgets.QPushButton("Close")
        btn.clicked.connect(self.accept)
        row = QtWidgets.QHBoxLayout()
        row.addStretch()
        row.addWidget(btn)
        lay.addLayout(row)


# Plain-text/markdown export of the help, reused by the in-app guide.
def help_markdown() -> str:
    return "\n".join([_COPILOT, _KEYS, _USAGE, _TROUBLE])
