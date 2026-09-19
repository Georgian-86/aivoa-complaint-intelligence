/**
 * Hand-drawn icon set on a 24px grid, 1.5 stroke, round caps.
 *
 * Deliberately not an off-the-shelf icon library: a bespoke set keeps the
 * product from reading like every other dashboard, and 20 glyphs is cheaper
 * than a dependency.
 */
import type { CSSProperties } from 'react'

export type IconName =
  | 'intake' | 'register' | 'dashboard' | 'settings' | 'search' | 'upload'
  | 'file' | 'sparkle' | 'send' | 'check' | 'alert' | 'shield' | 'clock'
  | 'copy' | 'reset' | 'save' | 'chevron' | 'close' | 'link' | 'flask'
  | 'sun' | 'moon' | 'trace' | 'duplicate' | 'arrow' | 'info' | 'plus' | 'download'

const PATHS: Record<IconName, JSX.Element> = {
  intake: <><rect x="3.5" y="3.5" width="12" height="17" rx="2" /><path d="M7 8h5M7 12h5M7 16h3" /><path d="M17 14.5v6M14 17.5h6" /></>,
  register: <><path d="M4 5.5h16M4 12h16M4 18.5h16" /><circle cx="7.5" cy="5.5" r="1.4" fill="currentColor" stroke="none" /><circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" /><circle cx="16.5" cy="18.5" r="1.4" fill="currentColor" stroke="none" /></>,
  dashboard: <><path d="M3.5 20V13M9 20V5M14.5 20v-4M20 20V9" /></>,
  settings: <><circle cx="12" cy="12" r="3" /><path d="M12 2.5v3M12 18.5v3M21.5 12h-3M5.5 12h-3M18.7 5.3l-2.1 2.1M7.4 16.6l-2.1 2.1M18.7 18.7l-2.1-2.1M7.4 7.4L5.3 5.3" /></>,
  search: <><circle cx="10.5" cy="10.5" r="6.5" /><path d="M15.5 15.5L21 21" /></>,
  upload: <><path d="M12 16V4M8 7.5L12 3.5l4 4" /><path d="M4 15v3.5A2.5 2.5 0 006.5 21h11a2.5 2.5 0 002.5-2.5V15" /></>,
  download: <><path d="M12 3.5v12M8 12l4 4 4-4" /><path d="M4 16v2.5A2.5 2.5 0 006.5 21h11a2.5 2.5 0 002.5-2.5V16" /></>,
  file: <><path d="M14 2.5H7a2 2 0 00-2 2v15a2 2 0 002 2h10a2 2 0 002-2V7.5L14 2.5z" /><path d="M14 2.5v5h5" /></>,
  sparkle: <><path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9L12 3z" /><path d="M18.5 15.5l.7 1.8 1.8.7-1.8.7-.7 1.8-.7-1.8-1.8-.7 1.8-.7.7-1.8z" /></>,
  send: <><path d="M21 3L10.5 13.5" /><path d="M21 3l-6.8 18-3.7-7.5L3 10.1 21 3z" /></>,
  check: <><path d="M4.5 12.5l5 5 10-11" /></>,
  alert: <><path d="M12 3.8L2.8 20h18.4L12 3.8z" /><path d="M12 10v4.5M12 17.4v.2" /></>,
  shield: <><path d="M12 2.8l8 3v6.4c0 4.6-3.3 8-8 9-4.7-1-8-4.4-8-9V5.8l8-3z" /><path d="M9 12l2.2 2.2L15.5 10" /></>,
  clock: <><circle cx="12" cy="12" r="8.8" /><path d="M12 7v5.3l3.3 2" /></>,
  copy: <><rect x="8.5" y="8.5" width="12" height="12" rx="2" /><path d="M15.5 8.5v-2a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2h2" /></>,
  reset: <><path d="M3.5 5.5v5h5" /><path d="M4.7 13a8 8 0 103-8.1L3.5 8.4" /></>,
  save: <><path d="M5.5 3.5h11L20.5 7.5v13a1 1 0 01-1 1h-14a1 1 0 01-1-1v-16a1 1 0 011-1z" /><path d="M8 3.5v6h7v-6M8 21.5v-6h8v6" /></>,
  chevron: <><path d="M9 5l7 7-7 7" /></>,
  close: <><path d="M5.5 5.5l13 13M18.5 5.5l-13 13" /></>,
  link: <><path d="M10.5 13.5a4.5 4.5 0 006.4 0l2.8-2.8a4.5 4.5 0 00-6.4-6.4l-1.6 1.6" /><path d="M13.5 10.5a4.5 4.5 0 00-6.4 0l-2.8 2.8a4.5 4.5 0 006.4 6.4l1.6-1.6" /></>,
  flask: <><path d="M9.5 3v6.2L4.3 18a2 2 0 001.7 3h12a2 2 0 001.7-3l-5.2-8.8V3" /><path d="M8 3h8M7.2 14.5h9.6" /></>,
  sun: <><circle cx="12" cy="12" r="4.2" /><path d="M12 2v2.4M12 19.6V22M22 12h-2.4M4.4 12H2M19.1 4.9l-1.7 1.7M6.6 17.4l-1.7 1.7M19.1 19.1l-1.7-1.7M6.6 6.6L4.9 4.9" /></>,
  moon: <><path d="M20.5 14.3A8.8 8.8 0 019.7 3.5a8.8 8.8 0 1010.8 10.8z" /></>,
  trace: <><circle cx="6" cy="6" r="2.4" /><circle cx="6" cy="18" r="2.4" /><circle cx="18" cy="12" r="2.4" /><path d="M8.4 6h4.1a3 3 0 013 3v.6M8.4 18h4.1a3 3 0 003-3v-.6" /></>,
  duplicate: <><rect x="3.5" y="3.5" width="11" height="11" rx="2" /><path d="M8 20.5h10a2.5 2.5 0 002.5-2.5V8" /></>,
  arrow: <><path d="M4 12h15M13.5 6.5L20 12l-6.5 5.5" /></>,
  info: <><circle cx="12" cy="12" r="8.8" /><path d="M12 11v5.2M12 7.8v.2" /></>,
  plus: <><path d="M12 5v14M5 12h14" /></>,
}

interface Props {
  name: IconName
  size?: number
  strokeWidth?: number
  className?: string
  style?: CSSProperties
}

export function Icon({ name, size = 16, strokeWidth = 1.5, className, style }: Props) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24" fill="none"
      stroke="currentColor" strokeWidth={strokeWidth}
      strokeLinecap="round" strokeLinejoin="round"
      className={className} style={style} aria-hidden="true" focusable="false"
    >
      {PATHS[name]}
    </svg>
  )
}
