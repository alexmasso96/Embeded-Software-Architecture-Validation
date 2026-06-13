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
