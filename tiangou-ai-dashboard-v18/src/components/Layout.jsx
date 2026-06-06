
import React, { useState } from "react";
import {
  Activity,
  ClipboardCheck,
  Gauge,
  GitBranch,
  Home,
  Leaf,
  Menu,
  Moon,
  Network,
  ShieldCheck,
  SlidersHorizontal,
  Sun,
  X,
} from "lucide-react";
import NotificationsPanel from "./NotificationsPanel";
import { cx } from "./ui";

const navigationLinks = [
  ["home", "Home", Home],
  ["overview", "Live overview", Activity],
  ["stability", "Grid stability", Gauge],
  ["resources", "Resource mix", Network],
  ["impact", "Impact", Leaf],
  ["readiness", "Readiness", ShieldCheck],
  ["actions", "Decision engine", SlidersHorizontal],
  ["scenarios", "Scenarios", ClipboardCheck],
  ["audit", "Audit trail", GitBranch],
];

export default function Layout({ route, navigate, theme, toggleTheme, simulation, notifications, dismissNotification, children }) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const onNavigate = (page) => { navigate(page); setMobileOpen(false); };
  const liveLabel = simulation.phase === "live" ? "LIVE" : simulation.phase === "buffering" ? "BUFFERING" : simulation.phase === "running" ? "SIMULATING" : simulation.phase === "paused" ? "PAUSED" : "VALIDATED";

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand" onClick={() => onNavigate("home")}>
          <span className="brand__mark"><ShieldCheck size={20} /></span>
          <span><strong>TIANGOU <em>AI</em></strong><small>Grid Stability Command Center</small></span>
        </button>

        <nav className="desktop-nav desktop-nav--all-pages" aria-label="Main pages">
          {navigationLinks.map(([page, label, Icon]) => (
            <button key={page} className={cx("desktop-nav__link", route === page && "is-active")} onClick={() => onNavigate(page)}>
              <Icon size={15} /><span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="topbar__actions">
          <span className={`live-label live-label--${simulation.phase}`}><i />{liveLabel}</span>
          <button className="theme-toggle" onClick={toggleTheme} aria-label={`Switch to ${theme === "dark" ? "light" : "dark"} mode`}>
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}<span>{theme === "dark" ? "Light" : "Dark"}</span>
          </button>
          <NotificationsPanel notifications={notifications} navigate={navigate} dismissNotification={dismissNotification} />
          <button className="mobile-menu-btn" onClick={() => setMobileOpen(!mobileOpen)} aria-label="Menu">{mobileOpen ? <X size={20} /> : <Menu size={20} />}</button>
        </div>
      </header>

      {mobileOpen ? <aside className="mobile-nav">{navigationLinks.map(([page, label, Icon]) => <button key={page} className={route === page ? "is-active" : ""} onClick={() => onNavigate(page)}><Icon size={18} />{label}</button>)}</aside> : null}
      <main className="page-container">{children}</main>
    </div>
  );
}
