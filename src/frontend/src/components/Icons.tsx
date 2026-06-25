// Small inline SVG icons so folders read as macOS-blue (emoji folders render
// yellow/grey on most platforms). Sized via the `size` prop.

// Folder uses currentColor (two-tone via opacity) so it follows the theme
// accent — set `color` on the wrapper where it's rendered.
export function FolderIcon({ size = 16 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      {/* back flap */}
      <path
        d="M3 6.2a1.8 1.8 0 0 1 1.8-1.8h3.7c.5 0 1 .2 1.3.6l1 1.1H19a1.8 1.8 0 0 1 1.8 1.8v.8H3z"
        fill="currentColor"
        opacity="0.62"
      />
      {/* front pocket */}
      <path
        d="M3 8.3h17.8a1.8 1.8 0 0 1 1.8 1.8v6.9a1.8 1.8 0 0 1-1.8 1.8H4.8A1.8 1.8 0 0 1 3 17z"
        fill="currentColor"
      />
    </svg>
  );
}

export function SunIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4" />
    </svg>
  );
}

export function MoonIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

export function AutoIcon({ size = 14 }: { size?: number }) {
  // Half-filled disc = "follow the system".
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 3a9 9 0 0 0 0 18z" fill="currentColor" stroke="none" />
    </svg>
  );
}

// Illustration for the "custom" file-browser option (issue 6): the in-app
// Finder-style Miller-columns picker. Accent traffic-lights + three nav columns.
export function CustomExplorerArt() {
  return (
    <svg viewBox="0 0 120 84" width="100%" height="100%" aria-hidden="true">
      <rect x="4" y="4" width="112" height="76" rx="8" fill="var(--card)"
        stroke="var(--border)" />
      <rect x="4" y="4" width="112" height="16" rx="8" fill="var(--titlebar-bg)" />
      <rect x="4" y="12" width="112" height="8" fill="var(--titlebar-bg)" />
      <circle cx="13" cy="12" r="2.4" fill="var(--accent)" />
      <circle cx="21" cy="12" r="2.4" fill="var(--border)" />
      <circle cx="29" cy="12" r="2.4" fill="var(--border)" />
      {/* three Miller columns */}
      <g fill="var(--muted)" opacity="0.5">
        <rect x="10" y="26" width="28" height="4" rx="2" />
        <rect x="10" y="34" width="28" height="4" rx="2" />
        <rect x="10" y="42" width="28" height="4" rx="2" />
        <rect x="46" y="26" width="28" height="4" rx="2" />
        <rect x="46" y="42" width="28" height="4" rx="2" />
        <rect x="82" y="26" width="28" height="4" rx="2" />
      </g>
      {/* selected row uses the accent */}
      <rect x="44" y="32" width="32" height="8" rx="3" fill="var(--accent)" opacity="0.85" />
    </svg>
  );
}

// Illustration for the "system" option: a plain OS-native file dialog window.
export function SystemExplorerArt() {
  return (
    <svg viewBox="0 0 120 84" width="100%" height="100%" aria-hidden="true">
      <rect x="14" y="8" width="92" height="68" rx="7" fill="var(--card)"
        stroke="var(--border)" />
      <rect x="14" y="8" width="92" height="14" rx="7" fill="var(--overlay)" />
      <rect x="14" y="15" width="92" height="7" fill="var(--overlay)" />
      <rect x="20" y="12" width="40" height="5" rx="2.5" fill="var(--muted)" opacity="0.5" />
      {/* sidebar + file grid to read as the OS chooser */}
      <rect x="20" y="28" width="22" height="42" rx="4" fill="var(--overlay)" />
      <g fill="var(--muted)" opacity="0.5">
        <rect x="24" y="33" width="14" height="3.5" rx="1.75" />
        <rect x="24" y="40" width="14" height="3.5" rx="1.75" />
        <rect x="24" y="47" width="14" height="3.5" rx="1.75" />
      </g>
      <g fill="var(--accent)" opacity="0.75">
        <rect x="50" y="30" width="22" height="16" rx="3" />
        <rect x="78" y="30" width="22" height="16" rx="3" opacity="0.5" />
        <rect x="50" y="52" width="22" height="16" rx="3" opacity="0.5" />
        <rect x="78" y="52" width="22" height="16" rx="3" opacity="0.5" />
      </g>
    </svg>
  );
}

// Compact terminal glyph for the visual terminal picker (issue 8). `tint` lets
// each terminal carry its own brand-ish colour.
export function TerminalIcon({ size = 26, tint = "var(--accent)" }: { size?: number; tint?: string }) {
  return (
    <svg viewBox="0 0 32 32" width={size} height={size} aria-hidden="true">
      <rect x="2" y="4" width="28" height="24" rx="4" fill={tint} />
      <rect x="2" y="4" width="28" height="6" rx="4" fill="#000" opacity="0.18" />
      <path d="M8 16l4 3-4 3" fill="none" stroke="#fff" strokeWidth="2"
        strokeLinecap="round" strokeLinejoin="round" />
      <path d="M15 23h7" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

export function FileIcon({ size = 16 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <path
        d="M6 2.5h7l5 5V20a1.5 1.5 0 0 1-1.5 1.5h-10A1.5 1.5 0 0 1 5 20V4A1.5 1.5 0 0 1 6.5 2.5z"
        fill="#F4F2EE"
        stroke="#C7C4BE"
        strokeWidth="1"
      />
      <path d="M13 2.6V7.5h4.9z" fill="#DAD7D1" stroke="#C7C4BE" strokeWidth="1" />
    </svg>
  );
}
