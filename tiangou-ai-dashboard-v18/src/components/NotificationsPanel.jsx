import React, { useState } from "react";
import { AlertTriangle, Bell, CheckCircle2, ChevronRight, X } from "lucide-react";
import { cx } from "./ui";

export default function NotificationsPanel({ notifications, navigate, dismissNotification }) {
  const [open, setOpen] = useState(false);
  const unread = notifications.filter((item) => !item.dismissed).length;
  const active = notifications.find((item) => !item.dismissed && item.popup);

  const openDecision = (notification) => {
    setOpen(false);
    dismissNotification?.(notification.id, { keepInHistory: true });
    navigate("actions");
  };

  return (
    <>
      <div className="notification-center">
        <button className={cx("icon-btn notification-center__button", unread && "has-notifications")} onClick={() => setOpen(!open)} aria-label={`${unread} notifications`}>
          <Bell size={18} />
          {unread ? <b>{unread}</b> : null}
        </button>
        {open ? (
          <div className="notification-center__menu">
            <div className="notification-center__heading"><strong>Operator notifications</strong><span>{unread} unread</span></div>
            {notifications.length ? notifications.map((item) => (
              <button key={item.id} className={cx("notification-item", `notification-item--${item.severity}`, item.dismissed && "is-dismissed")} onClick={() => openDecision(item)}>
                {item.severity === "stable" ? <CheckCircle2 size={17} /> : <AlertTriangle size={17} />}
                <span><strong>{item.title}</strong><small>{item.message}</small></span>
                <ChevronRight size={15} />
              </button>
            )) : <p className="notification-center__empty">No active operator warning.</p>}
          </div>
        ) : null}
      </div>

      {active ? (
        <aside className={`operator-warning-popup operator-warning-popup--${active.severity}`}>
          <button className="operator-warning-popup__close" onClick={() => dismissNotification?.(active.id)} aria-label="Dismiss warning"><X size={16} /></button>
          <div className="operator-warning-popup__icon"><AlertTriangle size={24} /></div>
          <div>
            <p className="eyebrow">PINN early warning</p>
            <h3>{active.title}</h3>
            <p>{active.message}</p>
            <button className="primary-btn" onClick={() => openDecision(active)}>Review corrective action <ChevronRight size={15} /></button>
          </div>
        </aside>
      ) : null}
    </>
  );
}
