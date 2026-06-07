import { Link } from "@tanstack/react-router"
import { ArrowRight, Gauge, MapPinned } from "lucide-react"

import heroBackground from "@/assets/landing-hero-bg.png"
import { Button } from "@/components/ui/button"

export function LandingPage() {
  return (
    <main className="min-h-[100dvh] bg-[#efe8d3] text-[#1d1913]">
      <section className="relative min-h-[100svh] overflow-hidden border-b border-[#1d1913]/20">
        <img
          src={heroBackground}
          alt=""
          aria-hidden="true"
          className="absolute inset-0 h-full w-full object-cover"
        />
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(239,232,211,0.98)_0%,rgba(239,232,211,0.9)_34%,rgba(239,232,211,0.28)_58%,rgba(29,25,19,0.08)_100%)]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_72%_44%,rgba(206,71,72,0.1),transparent_35%)]" />

        <header className="relative z-[1] mx-auto flex w-full max-w-[1720px] items-center justify-between gap-4 px-5 py-5 sm:px-8 lg:px-10">
          <Link
            to="/"
            className="grid h-12 w-12 place-items-center border border-[#1d1913] bg-[#ce4748] text-sm font-semibold text-[#fff8e7]"
            aria-label="Tiangou-AI home"
          >
            TG
          </Link>
          <nav className="hidden items-center gap-8 text-sm font-medium text-[#1d1913]/78 md:flex">
            <Link to="/dashboard" className="transition hover:text-[#8d2024]">
              Dashboard
            </Link>
            <Link to="/dynamic" className="transition hover:text-[#8d2024]">
              Dynamic demo
            </Link>
            <Link to="/analytics" className="transition hover:text-[#8d2024]">
              Analytics
            </Link>
          </nav>
          <Button asChild className="rounded-none bg-[#1d1913] px-5 text-[#fff8e7] hover:bg-[#8d2024]">
            <Link to="/dynamic">
              Run demo
              <ArrowRight className="size-4" />
            </Link>
          </Button>
        </header>

        <div className="relative z-[1] mx-auto grid min-h-[calc(100svh-88px)] w-full max-w-[1720px] items-end px-5 pb-8 sm:px-8 lg:grid-cols-[minmax(0,0.82fr)_minmax(340px,0.42fr)] lg:px-10 lg:pb-10">
          <div className="max-w-[880px] pb-[8svh]">
            <div className="mb-8 flex max-w-xl items-center gap-3 border-y border-[#1d1913]/40 py-3 text-sm font-medium text-[#1d1913]/78">
              <Gauge className="size-4 text-[#8d2024]" />
              <span>PINN-estimated inertia on a reconstructed Hong Kong grid</span>
            </div>
            <h1 className="font-['Vercetti',Geist,ui-sans-serif] text-[clamp(4rem,8.7vw,6rem)] leading-[0.9] tracking-[-0.03em] text-[#1d1913]">
              TIANGOU-AI
            </h1>
            <p className="mt-5 max-w-2xl text-[clamp(1.35rem,2.2vw,2.3rem)] leading-[1.08] text-[#8d2024]">
              Hong Kong grid simulation as a moving system.
            </p>
            <p className="mt-7 max-w-[62ch] text-base leading-7 text-[#3b352d] sm:text-lg">
              Precompute a real-grid stress scenario, then scroll through the disturbance as frequency, generators,
              consumers, and intervention state change over time.
            </p>
            <div className="mt-9 flex flex-wrap gap-3">
              <Button asChild className="rounded-none bg-[#ce4748] px-6 text-[#fff8e7] hover:bg-[#8d2024]">
                <Link to="/dynamic">
                  Run dynamic demo
                  <ArrowRight className="size-4" />
                </Link>
              </Button>
              <Button asChild variant="outline" className="rounded-none border-[#1d1913] bg-[#fff8e7]/70 px-6 text-[#1d1913] hover:bg-[#fff8e7]">
                <Link to="/dashboard">
                  View dashboard
                  <MapPinned className="size-4" />
                </Link>
              </Button>
            </div>
          </div>

          <aside className="mb-10 hidden max-w-sm justify-self-end border border-[#1d1913]/45 bg-[#efe8d3]/86 p-4 shadow-[8px_8px_0_rgba(29,25,19,0.18)] backdrop-blur-[2px] lg:block">
            <div className="flex items-center justify-between border-b border-[#1d1913]/30 pb-3 text-xs font-semibold uppercase tracking-[0.08em] text-[#3b352d]">
              <span>Scroll simulation</span>
              <span>00:00</span>
            </div>
            <div className="mt-4 grid grid-cols-[1fr_auto_1fr] gap-3 text-sm">
              <div>
                <div className="text-[#8d2024]">Uncontrolled</div>
                <div className="mt-2 h-1.5 bg-[#8d2024]" />
                <p className="mt-3 text-xs leading-5 text-[#3b352d]">Frequency collapse, no corrective action.</p>
              </div>
              <div className="h-full w-px bg-[#1d1913]/35" />
              <div>
                <div className="text-[#1f8f54]">Stabilized</div>
                <div className="mt-2 h-1.5 bg-[#1f8f54]" />
                <p className="mt-3 text-xs leading-5 text-[#3b352d]">Producer and load actions hold the system.</p>
              </div>
            </div>
          </aside>
        </div>
      </section>
    </main>
  )
}
