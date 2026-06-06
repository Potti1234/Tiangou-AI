import React from "react";
import { AlertTriangle, RefreshCcw } from "lucide-react";

export default class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Tiangou AI interface error", error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <main className="startup-error">
        <section className="startup-error__card">
          <AlertTriangle size={30} />
          <div>
            <p className="eyebrow">Interface recovery mode</p>
            <h1>The dashboard could not start correctly.</h1>
            <p>Refresh the page. If the issue persists, open the browser console and copy the first red error message.</p>
            <pre>{String(this.state.error?.message || this.state.error)}</pre>
            <button className="primary-btn" onClick={() => window.location.reload()}>
              <RefreshCcw size={16} /> Reload dashboard
            </button>
          </div>
        </section>
      </main>
    );
  }
}
