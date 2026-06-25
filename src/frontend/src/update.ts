// In-app "Check for Updates": compares the running version against the latest
// published GitHub release and exposes a small status machine the launcher and
// Preferences subscribe to. The GitHub Releases API serves permissive CORS, so
// the fetch works from both the desktop shell and a plain dev browser.

import { useCallback, useEffect, useState } from "react";

// Single source of truth for the running version. Keep in lockstep with
// package.json / RELEASE_NOTES.md on every release.
export const APP_VERSION = "3.0.0";

export const GITHUB_REPO = "alexmasso96/Embeded-Software-Architecture-Validation";
export const RELEASES_API = `https://api.github.com/repos/${GITHUB_REPO}/releases/latest`;

export type UpdateStatus =
  | "idle"
  | "checking"
  | "latest"
  | "update-available"
  | "error";

export interface UpdateInfo {
  status: UpdateStatus;
  latestVersion?: string; // normalised, no leading "v"
  body?: string; // release notes markdown
  errorMsg?: string;
}

// GitHub → compare URL between the running version and the latest release.
export function compareUrl(latestVersion: string): string {
  return `https://github.com/${GITHUB_REPO}/compare/v${APP_VERSION}...v${latestVersion}`;
}

// "v2.1.1" / "2.1.1-rc1" → [2, 1, 1] (pre-release suffix dropped for ordering).
function parseVersion(v: string): number[] {
  return v.trim().replace(/^v/i, "").split("-")[0].split(".").map((n) => parseInt(n, 10) || 0);
}

// Is `latest` strictly newer than `current`? Component-wise numeric compare.
export function isNewer(latest: string, current: string): boolean {
  const a = parseVersion(latest);
  const b = parseVersion(current);
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const diff = (a[i] ?? 0) - (b[i] ?? 0);
    if (diff !== 0) return diff > 0;
  }
  return false;
}

async function fetchLatestRelease(): Promise<{ tag: string; body: string }> {
  const res = await fetch(RELEASES_API, {
    headers: { Accept: "application/vnd.github+json" },
  });
  if (!res.ok) {
    throw new Error(
      res.status === 404
        ? "No published releases found."
        : `GitHub API responded ${res.status}.`,
    );
  }
  const json = await res.json();
  return { tag: String(json.tag_name ?? ""), body: String(json.body ?? "") };
}

// Owns the update-check lifecycle. App mounts this once and threads the result
// down to the launcher card + Preferences. `check` re-runs it (manual button).
export function useUpdateCheck(): { update: UpdateInfo; check: () => void } {
  const [update, setUpdate] = useState<UpdateInfo>({ status: "idle" });

  const check = useCallback(async () => {
    setUpdate({ status: "checking" });
    try {
      const { tag, body } = await fetchLatestRelease();
      if (!tag) {
        setUpdate({ status: "error", errorMsg: "Release has no version tag." });
        return;
      }
      const latestVersion = tag.replace(/^v/i, "");
      setUpdate({
        status: isNewer(tag, APP_VERSION) ? "update-available" : "latest",
        latestVersion,
        body,
      });
    } catch (e) {
      setUpdate({ status: "error", errorMsg: (e as Error).message });
    }
  }, []);

  // Silent background check on first mount.
  useEffect(() => {
    check();
  }, [check]);

  return { update, check };
}
