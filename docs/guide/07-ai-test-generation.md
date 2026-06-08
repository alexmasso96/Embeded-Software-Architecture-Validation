# 7. AI Test Case Generation

[← Collaboration & Safety](06-collaboration-and-safety.md) · **AI Test Case Generation**

---

> 📷 _Screenshot coming soon._

The **Test Case Design** tab (section 5) produces the *high-level* test cases — the Given / When / Then structure for every port. The **AI Test Generation** tab takes those a step further: it sends each high-level case, your project's source code, and your rules to an AI model, and fills in the detailed **low-level** test steps (breakpoints, reads, verifications) for you.

It's the same job an engineer would do by hand in an editor with Copilot — point at the code, apply the rules, write the steps — just driven from inside the app.

## Before you start

1. **Generate the high-level designs first.** In the *Test Case Design* tab, click **Generate**. This writes `<Model>_Test_Case_Design.md` files into a `Test Case Design/` folder next to your project. The AI tab reads those files from disk — if none exist yet, it will tell you to generate them first.
2. **Connect a provider** (below).

## Connecting an AI provider

Open **Configure Providers…** on the left of the tab. You have four options; you only need one:

| Provider | What you need | Notes |
|---|---|---|
| **GitHub Copilot** | A GitHub account with an active Copilot subscription | Click **Sign In** and authorize via the code shown at github.com/login/device. No manual token. Serves Claude/GPT models *through* Copilot. |
| **Anthropic (Claude)** | An API key from console.anthropic.com | Direct, billed to your Anthropic account. |
| **OpenAI (ChatGPT)** | An API key from platform.openai.com | Direct. |
| **Google Gemini** | An API key from aistudio.google.com | Direct. |

> **Where are my keys stored?** Encrypted, on **this computer only**, in a `credentials.aikeys` file in your user profile — never inside the `.arch` project file, and never in plain text. You configure a provider once per machine and it works across all your projects.

> **Copilot in a managed company?** Copilot sign-in is account-based, so any Copilot-entitled account should work — but some organizations block third-party OAuth apps, enforce SSO authorization, or firewall the Copilot endpoint. If sign-in fails, that's usually why; use a direct API key as a fallback. See the in-app **Help** button for details.

## Generating low-level test cases

On the left panel:

1. Pick a **Provider** and **Model**.
2. Set the **Source code path** to your firmware source folder (the AI uses the most relevant files as context).
3. Choose the **Test case design** file and tick **which test cases** to generate (all, or just a few).
4. *(Optional)* Expand **Prompt & Rules** to tailor the instructions — see below.
5. Click **▶ Generate** (use **■ Stop** to abort).

On the right you'll see three tabs:

- **Low-Level Design** — the generated markdown, rendered. When it finishes, the result is saved as `<Model>_LowLevel.md` next to your project.
- **Thought Process** — live progress and any errors.
- **Chat** — ask the model follow-up questions.

**Write Back** fills the generated steps into the `### Low Level Test Case Design` sections of the *original* high-level file, in place.

## Prompt & Rules

The AI is steered by two pieces of text, both **stored in your project** and editable from the tab:

- **Rules** — the hard constraints (HiL environment, no code compilation, debugger step paradigms, no CANoe signals, output format).
- **Prompt** — the task instructions.

They come pre-filled with sensible defaults; edit them and click **Save** to persist, or **Reset to default**. Because they live in the project, your edits survive across sessions and are shared with anyone who opens the project.

> The *Test Case Design* tab no longer auto-writes `rules.md` / `copilot_prompt.txt` every time you generate. Instead, when you generate high-level cases it **asks** whether to also export those two files — handy if you want to paste them into an external editor's Copilot chat manually.

---

[← Collaboration & Safety](06-collaboration-and-safety.md) · [Back to contents](README.md)
