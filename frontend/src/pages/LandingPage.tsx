import { useEffect, useRef, useState } from "react"
import { Link } from "@tanstack/react-router"
import { ArrowRight, Gauge, MapPinned, RadioTower } from "lucide-react"

import blackoutFrame01 from "@/assets/landing/blackout-frame-01-lit.png"
import blackoutFrame02 from "@/assets/landing/blackout-frame-02-partial.png"
import blackoutFrame03 from "@/assets/landing/blackout-frame-03-cascade.png"
import blackoutFrame04 from "@/assets/landing/blackout-frame-04-dark.png"
import heroBackground from "@/assets/landing-hero-bg.png"
import tiangouLogo from "@/assets/tiangou-logo-transparent-no-text.png"
import { Button } from "@/components/ui/button"

const BLACKOUT_FRAMES = [
  {
    src: blackoutFrame01,
    label: "Fully lit",
    time: "00:00",
    title: "The city is balanced.",
    body: "Frequency holds while generation and demand remain in sync.",
  },
  {
    src: blackoutFrame02,
    label: "First outage",
    time: "00:18",
    title: "The first districts go dark.",
    body: "A low-inertia grid has less time to absorb the disturbance.",
  },
  {
    src: blackoutFrame03,
    label: "Cascade",
    time: "00:42",
    title: "The cascade becomes visible.",
    body: "Critical loads remain, but the wider system is already losing stability.",
  },
  {
    src: blackoutFrame04,
    label: "Blackout",
    time: "01:00",
    title: "Then silence.",
    body: "By the time the lights are off, the physics has already happened.",
  },
]

function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

function frameOpacity(progress: number, index: number) {
  const center = index / (BLACKOUT_FRAMES.length - 1)
  const distance = Math.abs(progress - center)
  return clamp(1 - distance * 3.25, 0, 1)
}

export function LandingPage() {
  useEffect(() => {
    document.documentElement.classList.add("tiangou-landing-snap")
    return () => document.documentElement.classList.remove("tiangou-landing-snap")
  }, [])

  return (
    <main className="min-h-[100dvh] bg-[#efe8d3] text-[#1d1913]">
      <section className="relative min-h-[100svh] snap-start snap-always overflow-hidden border-b border-[#1d1913]/20">
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
            className="grid h-14 w-14 place-items-center transition hover:opacity-75"
            aria-label="Tiangou-AI home"
          >
            <img src={tiangouLogo} alt="" aria-hidden="true" className="h-full w-full object-contain" />
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
      <BlackoutColdOpen />
    </main>
  )
}

function BlackoutColdOpen() {
  const sectionRef = useRef<HTMLElement | null>(null)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const updateProgress = () => {
      const section = sectionRef.current
      if (!section) return
      const rect = section.getBoundingClientRect()
      const travel = Math.max(1, rect.height - window.innerHeight)
      setProgress(clamp(-rect.top / travel, 0, 1))
    }

    updateProgress()
    window.addEventListener("scroll", updateProgress, { passive: true })
    window.addEventListener("resize", updateProgress)
    return () => {
      window.removeEventListener("scroll", updateProgress)
      window.removeEventListener("resize", updateProgress)
    }
  }, [])

  const activeIndex = Math.min(BLACKOUT_FRAMES.length - 1, Math.round(progress * (BLACKOUT_FRAMES.length - 1)))
  const activeFrame = BLACKOUT_FRAMES[activeIndex]

  return (
    <section ref={sectionRef} className="relative h-[420svh] snap-start snap-always bg-[#0f1212] text-[#fff8e7]">
      <div className="sticky top-0 h-[100svh] overflow-hidden">
        {BLACKOUT_FRAMES.map((frame, index) => (
          <img
            key={frame.src}
            src={frame.src}
            alt=""
            aria-hidden="true"
            className="absolute inset-0 h-full w-full object-cover transition-opacity duration-300 ease-out"
            style={{ opacity: frameOpacity(progress, index) }}
          />
        ))}
        <div className="absolute inset-0 bg-[linear-gradient(90deg,rgba(10,12,12,0.9)_0%,rgba(10,12,12,0.64)_36%,rgba(10,12,12,0.22)_68%,rgba(10,12,12,0.58)_100%)]" />
        <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-[#0f1212] to-transparent" />
        <div className="absolute inset-x-0 bottom-0 h-36 bg-gradient-to-t from-[#0f1212] to-transparent" />

        <div className="relative z-[1] mx-auto grid h-full w-full max-w-[1720px] grid-rows-[auto_1fr_auto] px-5 py-6 sm:px-8 lg:px-10">
          <div className="flex items-center justify-between gap-4 border-b border-[#fff8e7]/24 pb-4">
            <div className="flex items-center gap-3 text-sm font-medium text-[#fff8e7]/78">
              <RadioTower className="size-4 text-[#ce4748]" />
              <span>Section 02</span>
              <span className="hidden h-px w-16 bg-[#ce4748]/70 sm:block" />
              <span className="hidden sm:inline">Blackout cold open</span>
            </div>
            <div className="font-['Vercetti',Geist,ui-sans-serif] text-2xl tabular-nums text-[#ce4748]">
              {activeFrame.time}
            </div>
          </div>

          <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,0.72fr)_minmax(320px,0.38fr)]">
            <div className="max-w-[760px]">
              <p className="mb-5 max-w-xl border-l border-[#ce4748] pl-4 text-base leading-7 text-[#fff8e7]/72">
                April 28, 2025. The Iberian Peninsula went dark. Hospitals switched to backup power,
                deaths were reported, and losses were estimated above EUR 1.6B.
              </p>
              <h2 className="font-['Vercetti',Geist,ui-sans-serif] text-[clamp(3.1rem,7.4vw,6rem)] leading-[0.9] tracking-[-0.03em] text-[#fff8e7]">
                This was not an accident.
              </h2>
              <p className="mt-5 text-[clamp(1.8rem,3.2vw,3rem)] leading-[1] text-[#ce4748]">
                It was physics.
              </p>
            </div>

            <aside className="max-w-md border border-[#fff8e7]/28 bg-[#0f1212]/72 p-4 backdrop-blur-[2px]">
              <div className="flex items-center justify-between gap-3 border-b border-[#fff8e7]/20 pb-3">
                <span className="text-sm font-semibold text-[#fff8e7]">{activeFrame.label}</span>
                <span className="text-xs font-medium text-[#fff8e7]/60">
                  {Math.round(progress * 100).toString().padStart(2, "0")}%
                </span>
              </div>
              <h3 className="mt-5 text-2xl leading-tight text-[#fff8e7]">{activeFrame.title}</h3>
              <p className="mt-3 text-sm leading-6 text-[#fff8e7]/72">{activeFrame.body}</p>
              <div className="mt-6 grid grid-cols-4 gap-2">
                {BLACKOUT_FRAMES.map((frame, index) => (
                  <div key={frame.label} className="space-y-2">
                    <div className="h-1 bg-[#fff8e7]/20">
                      <div
                        className="h-full bg-[#ce4748] transition-[width] duration-200"
                        style={{ width: progress >= index / (BLACKOUT_FRAMES.length - 1) ? "100%" : "0%" }}
                      />
                    </div>
                    <div className="text-[0.68rem] leading-tight text-[#fff8e7]/55">{frame.label}</div>
                  </div>
                ))}
              </div>
            </aside>
          </div>

          <div className="grid gap-3 border-t border-[#fff8e7]/24 pt-4 text-sm text-[#fff8e7]/68 md:grid-cols-[1fr_auto] md:items-end">
            <p className="max-w-[72ch] leading-6">
              The pitch starts with darkness because grid instability is not abstract. Once frequency leaves the safe band,
              operators have seconds, not hours.
            </p>
            <div className="font-['Vercetti',Geist,ui-sans-serif] text-xl text-[#ce4748]">
              Scroll to advance time
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
