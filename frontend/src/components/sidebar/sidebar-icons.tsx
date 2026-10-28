interface IconProps {
  className?: string;
  filled?: boolean;
}

/**
 * Home icon matching the rounded home glyph in the navigation bar.
 * Renders filled when active, outline otherwise.
 */
export function HomeIcon({ className = "size-6", filled = false }: IconProps) {
  if (filled) {
    return (
      <svg
        viewBox="0 0 24 24"
        fill="currentColor"
        aria-hidden="true"
        className={className}
      >
        <path d="M11.23 2.65a1.2 1.2 0 0 1 1.54 0l7.8 6.24A1.2 1.2 0 0 1 21 9.83v9.37A2.8 2.8 0 0 1 18.2 22H5.8A2.8 2.8 0 0 1 3 19.2V9.83a1.2 1.2 0 0 1 .43-.94l7.8-6.24zM10.25 15a1.75 1.75 0 0 0 3.5 0v-0.5a1.75 1.75 0 0 0-3.5 0V15z" />
      </svg>
    );
  }

  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      <path d="M3 10.5 12 3l9 7.5v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9z" />
      <path d="M10 15a2 2 0 1 1 4 0" />
    </svg>
  );
}

/**
 * Storefront/Marketplace icon for "Explore", matching the scalloped awning shop glyph.
 */
export function ExploreIcon({ className = "size-6", filled = false }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={filled ? "0.5" : "1.75"}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {/* Awning top */}
      <path d="M3 9.5 4.5 4.5A1 1 0 0 1 5.5 4h13a1 1 0 0 1 1 .5L21 9.5" />
      {/* Scalloped awnings */}
      <path d="M3 9.5a2.25 2.25 0 0 0 4.5 0 2.25 2.25 0 0 0 4.5 0 2.25 2.25 0 0 0 4.5 0 2.25 2.25 0 0 0 4.5 0" />
      {/* Store base */}
      <path d="M4.5 12V19a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V12" />
      {/* Store door/window */}
      <path d="M9.5 21v-5a1.5 1.5 0 0 1 1.5-1.5h2a1.5 1.5 0 0 1 1.5 1.5v5" />
    </svg>
  );
}

/**
 * Shop icon — a shopping bag, for the product catalog (Shop & Escrow).
 */
export function ShopIcon({ className = "size-6", filled = false }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={filled ? "0.5" : "1.75"}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {/* Bag body */}
      <path d="M6 7h12l1 13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1L6 7Z" />
      {/* Handle */}
      <path d="M9 7V5.5a3 3 0 0 1 6 0V7" />
    </svg>
  );
}

/**
 * Wallet icon matching the rounded card flap wallet glyph.
 */
export function WalletIcon({ className = "size-6", filled = false }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {/* Outer wallet body */}
      <rect x="2.5" y="6" width="19" height="14" rx="3.5" />
      {/* Top opening flap */}
      <path d="M4 6V4.75A2.25 2.25 0 0 1 6.25 2.5h11.5A2.25 2.25 0 0 1 20 4.75V6" />
      {/* Clasp / card slot with button */}
      <path d="M15.5 12.5h4.5a1.5 1.5 0 0 1 1.5 1.5v0a1.5 1.5 0 0 1-1.5 1.5h-4.5a1.5 1.5 0 0 1-1.5-1.5v0a1.5 1.5 0 0 1 1.5-1.5z" />
      <circle cx="17.25" cy="14" r="0.75" fill="currentColor" />
    </svg>
  );
}

/**
 * Account/User profile icon with badge mark matching the screenshot glyph.
 */
export function AccountIcon({ className = "size-6", filled = false }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      className={className}
    >
      {/* Head */}
      <circle cx="12" cy="7" r="4" />
      {/* Body / Shoulders */}
      <path d="M4.5 20.5a7.5 7.5 0 0 1 13-3.5" />
      {/* Pencil / badge accessory */}
      <path d="M16.5 14.5l3.5-3.5a1.2 1.2 0 0 1 1.7 1.7l-3.5 3.5-2 0.5 0.3-2.2z" />
    </svg>
  );
}
