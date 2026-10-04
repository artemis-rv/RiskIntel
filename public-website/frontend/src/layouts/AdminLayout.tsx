/**
 * layouts/AdminLayout.tsx
 * ───────────────────────
 * Shell for the administrative area.
 *
 * Visually distinct on purpose: a dark green chrome and a persistent sidebar,
 * so it is never mistaken for the public site. That distinction is a safeguard
 * against acting on the wrong surface, not an access control — every request
 * this area makes is authorised by the server through `require_admin`.
 *
 * There is exactly one admin area. No second portal, no elevated tier.
 */

import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation } from 'react-router-dom';
import { ROUTES } from '@/constants/routes';
import { PRODUCT } from '@/constants/content';
import { useAuth } from '@/hooks/useAuth';
import { useRouteFocus } from '@/hooks/useDocumentTitle';
import { displayName, initials } from '@/utils/format';
import {
  ChartIcon,
  ChatIcon,
  DashboardIcon,
  ExternalIcon,
  InboxIcon,
  LogoutIcon,
  MenuIcon,
  PackageIcon,
  ShieldIcon,
  UsersIcon,
  XIcon,
} from '@/components/common/Icons';

const ADMIN_NAV = [
  { to: ROUTES.admin, label: 'Overview', Icon: DashboardIcon, end: true },
  { to: ROUTES.adminUsers, label: 'Users', Icon: UsersIcon, end: false },
  { to: ROUTES.adminReleases, label: 'Releases', Icon: PackageIcon, end: false },
  { to: ROUTES.adminDownloads, label: 'Downloads', Icon: ChartIcon, end: false },
  { to: ROUTES.adminFeedback, label: 'Feedback', Icon: ChatIcon, end: false },
  { to: ROUTES.adminContact, label: 'Contact requests', Icon: InboxIcon, end: false },
];

function AdminNavLinks({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="space-y-1" aria-label="Admin sections">
      {ADMIN_NAV.map(({ to, label, Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          onClick={onNavigate}
          className={({ isActive }) =>
            `admin-nav-link ${isActive ? 'admin-nav-link-active' : ''}`
          }
        >
          <Icon className="h-5 w-5 shrink-0" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

export function AdminLayout() {
  const mainRef = useRef<HTMLElement>(null);
  useRouteFocus(mainRef);
  const { user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const location = useLocation();

  // Close the drawer whenever the route changes. Adjusted during render for the
  // same reason as the public navbar: it is derived from the current route.
  const [lastPath, setLastPath] = useState(location.pathname);
  if (lastPath !== location.pathname) {
    setLastPath(location.pathname);
    setSidebarOpen(false);
  }

  useEffect(() => {
    if (!sidebarOpen) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') setSidebarOpen(false);
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [sidebarOpen]);

  return (
    <div className="admin-shell flex min-h-screen">
      <a href="#admin-main" className="skip-link">
        Skip to main content
      </a>

      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-white/10 lg:flex">
        <div className="flex h-16 items-center gap-2 border-b border-white/10 px-5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15 text-white">
            <ShieldIcon className="h-5 w-5" />
          </span>
          <div className="leading-tight">
            <p className="text-sm font-bold text-white">{PRODUCT.name}</p>
            <p className="text-[0.6875rem] font-semibold uppercase tracking-wider text-admin-200">
              Admin
            </p>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          <AdminNavLinks />
        </div>

        <div className="border-t border-white/10 p-3">
          <Link
            to={ROUTES.home}
            className="admin-nav-link"
            title="Open the public website"
          >
            <ExternalIcon className="h-5 w-5 shrink-0" />
            <span>Public site</span>
          </Link>
        </div>
      </aside>

      {/* Mobile drawer */}
      {sidebarOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 bg-ink-950/60"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
          <aside
            className="relative flex h-full w-72 max-w-[85vw] flex-col bg-admin-950 shadow-popover"
            aria-label="Admin navigation"
          >
            <div className="flex h-16 items-center justify-between border-b border-white/10 px-4">
              <div className="flex items-center gap-2">
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/15 text-white">
                  <ShieldIcon className="h-5 w-5" />
                </span>
                <p className="text-sm font-bold text-white">Admin</p>
              </div>
              <button
                type="button"
                onClick={() => setSidebarOpen(false)}
                className="rounded-lg p-2 text-admin-100 hover:bg-white/10"
                aria-label="Close admin navigation"
              >
                <XIcon className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3">
              <AdminNavLinks onNavigate={() => setSidebarOpen(false)} />
            </div>
            <div className="border-t border-white/10 p-3">
              <Link to={ROUTES.home} className="admin-nav-link">
                <ExternalIcon className="h-5 w-5" />
                <span>Public site</span>
              </Link>
            </div>
          </aside>
        </div>
      ) : null}

      {/* Content column */}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-white/10 px-4 sm:px-6">
          <div className="flex min-w-0 items-center gap-3">
            <button
              type="button"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open admin navigation"
              aria-expanded={sidebarOpen}
              className="rounded-lg p-2 text-admin-100 transition-colors hover:bg-white/10 lg:hidden"
            >
              <MenuIcon className="h-6 w-6" />
            </button>
            <p className="truncate text-sm font-semibold text-white">Administration</p>
          </div>

          <div className="flex items-center gap-3">
            {user ? (
              <div className="hidden items-center gap-2 sm:flex">
                <span
                  className="flex h-8 w-8 items-center justify-center rounded-full bg-white/15 text-xs font-bold text-white"
                  aria-hidden="true"
                >
                  {initials(user)}
                </span>
                <div className="leading-tight">
                  <p className="max-w-[12rem] truncate text-xs font-semibold text-white">
                    {displayName(user)}
                  </p>
                  <p className="text-[0.6875rem] text-admin-200">{user.role}</p>
                </div>
              </div>
            ) : null}

            <button
              type="button"
              onClick={() => void logout()}
              // The label is hidden below `sm`, which would otherwise leave an
              // icon-only control with no accessible name on exactly the
              // screens where it is hardest to identify by sight.
              aria-label="Sign out"
              className="flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium text-admin-100 transition-colors hover:bg-white/10 hover:text-white"
            >
              <LogoutIcon className="h-4 w-4" aria-hidden="true" />
              <span className="hidden sm:inline">Sign out</span>
            </button>
          </div>
        </header>

        <main
          id="admin-main"
          ref={mainRef}
          tabIndex={-1}
          className="flex-1 overflow-y-auto bg-ink-50 focus:outline-none"
        >
          <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
