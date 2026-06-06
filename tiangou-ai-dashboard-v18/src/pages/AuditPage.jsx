import React from "react";
import { Download, GitBranch, ShieldCheck } from "lucide-react";
import { SectionTitle, StatusBadge } from "../components/ui";

export default function AuditPage({ auditEvents }) {
  return (
    <>
      <section className="page-hero page-hero--compact">
        <div>
          <p className="eyebrow">Traceability</p>
          <h1>Audit trail</h1>
          <p>Review forecast events, validation outcomes, operator decisions and interface status changes.</p>
        </div>
        <StatusBadge severity="stable"><ShieldCheck size={13} />Logging active</StatusBadge>
      </section>

      <section className="panel-card">
        <SectionTitle
          eyebrow="Recorded events"
          title="Decision and validation log"
          note="Every recommendation should remain reproducible from its inputs, model version and operator decision."
          action={<button className="ghost-btn"><Download size={15} />Export log</button>}
        />
        <div className="table-wrap">
          <table>
            <thead><tr><th>Time</th><th>Severity</th><th>Type</th><th>Event</th><th>Source</th></tr></thead>
            <tbody>
              {auditEvents.map((event, index) => (
                <tr key={`${event.time}-${index}`}>
                  <td>{event.time}</td>
                  <td><StatusBadge severity={event.severity}>{event.severity}</StatusBadge></td>
                  <td>{event.type}</td>
                  <td>{event.event}</td>
                  <td>{event.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="info-card info-card--full">
        <p className="eyebrow">Auditability principle</p>
        <h3><GitBranch size={17} />Trace every material recommendation</h3>
        <p>
          A production implementation should retain the telemetry snapshot, data-quality flags, configured
          thresholds, model version, candidate actions, validation results, selected recommendation and
          operator decision.
        </p>
      </section>
    </>
  );
}
