const stroke = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };

export const IconClose = (p) => (
  <svg width="14" height="14" viewBox="0 0 24 24" {...stroke} {...p}>
    <path d="M18 6 6 18" /><path d="m6 6 12 12" />
  </svg>
);

export const IconHistory = (p) => (
  <svg width="14" height="14" viewBox="0 0 24 24" {...stroke} {...p}>
    <path d="M3 12a9 9 0 1 0 2.6-6.34" />
    <path d="M3 3v5h5" />
    <path d="M12 7v5l3 2" />
  </svg>
);

export const IconSigma = (p) => (
  <svg width="15" height="15" viewBox="0 0 24 24" {...stroke} {...p}>
    <path d="M18 7V5a1 1 0 0 0-1-1H7a1 1 0 0 0-.75 1.66L11 12l-4.75 5.34A1 1 0 0 0 7 19h10a1 1 0 0 0 1-1v-2" />
  </svg>
);

export const IconPlus = (p) => (
  <svg width="13" height="13" viewBox="0 0 24 24" {...stroke} {...p}>
    <path d="M5 12h14" /><path d="M12 5v14" />
  </svg>
);

export const IconSend = (p) => (
  <svg width="16" height="16" viewBox="0 0 24 24" {...stroke} {...p}>
    <path d="m5 12 7-7 7 7" /><path d="M12 19V5" />
  </svg>
);

// CB-19: export/download icon for the "Export study sheet" button
export const IconDownload = (p) => (
  <svg width="14" height="14" viewBox="0 0 24 24" {...stroke} {...p}>
    <path d="M12 3v12" /><path d="m7 10 5 5 5-5" /><path d="M5 21h14" />
  </svg>
);