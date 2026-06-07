
[0:00 – 0:12 — CONTEXT]

Power grids run at a fixed frequency. When generation and demand go out of balance, frequency drops. Below certain thresholds, protection systems start tripping generators — and that can cascade.

[0:12 – 0:30 — THE PROBLEM]

Frequency dynamics follow the swing equation: the rate of change depends on the power imbalance and the grid's inertia. As more inverter-coupled renewables replace synchronous generators, inertia drops — and the same disturbance now causes a faster, harder-to-catch frequency decline.

[0:30 – 1:05 — THE APPROACH]

We use a Physics-Informed Neural Network to estimate the grid's effective inertia in real time. That estimate feeds directly into the swing equation, which we use to project a 60-second frequency trajectory every second.

If the predicted minimum breaches 49.5 Hz, we dispatch immediately — before the frequency has actually started falling. That early trigger gives 30 to 60 seconds of lead time over classical rate-of-change detection.

Battery storage responds in under a second. Gas turbines are pre-warmed so they're available earlier to stabelise the grid.

Here we run two parallel simulation timelines: one with no intervention, one with AI-guided dispatch. The difference in outcomes — specifically nadir frequency and whether cascade conditions are reached — is what the system is evaluated against.

[1:05 – 1:20 — WHY PHYSICS-INFORMED]

Constraining the network with the swing equation keeps predictions physically plausible and the decisions interpretable — both requirements for anything touching critical infrastructure.

~190 words / ~1:20


-----------------------------------------------------------------------
Tiangou AI — 2-Minute Technical Script (revised)
[0:00 – 0:18 — CONTEXT]

Power grids are designed to operate at a fixed frequency. When generation and demand go out of balance, frequency deviates. Relay protection systems trip generators automatically below certain thresholds, which can trigger a cascade. The challenge is detecting and responding to imbalances fast enough to stay within those bounds.

[0:18 – 0:45 — THE PHYSICS PROBLEM]

Frequency dynamics are governed by the swing equation. The rate of change is proportional to the power imbalance divided by the system's inertia constant H.

Traditionally, large synchronous generators — nuclear, coal and gas   — contribute significant rotational inertia, which naturally slows frequency deviations and buys response time. As grids integrate more inverter-coupled renewables like solar and wind, that inertia decreases. The same power imbalance now causes a faster frequency drop, leaving less time for corrective action.

[0:45 – 1:22 — WHAT TIANGOU AI DOES]

We built a Physics-Informed Neural Network that estimates the current effective inertia H of the grid in real time, trained on synthetical Hong Kong grid data.

Most of the model is a small four-layer network mapping grid state to predicted frequency. The key learnable quantity is a single scalar — the inertia estimate — which feeds directly into the swing equation.

Every second, we take that H estimate, plug it into the swing equation alongside current generation and demand, and roll out a 60-second frequency trajectory. If the predicted minimum is going to breach 49.5 Hz, we issue dispatch commands immediately, before the frequency has actually started falling.

That trajectory-based trigger typically gives 30 to 60 seconds of additional lead time compared to waiting for rate-of-change thresholds to fire.

[1:22 – 1:46 — DISPATCH LOGIC]

The dispatch layer selects the minimum set of actions needed to lift the predicted frequency above threshold. Fast resources like battery storage respond in the same second. Slower resources like gas turbines are pre-warmed so they're available in way shorter time

Here, we run two parallel simulation timelines: one with no intervention, one with AI-guided dispatch. The difference in outcomes — specifically  the frequency and whether cascade conditions are reached — is what the system is evaluated against.

[1:46 – 2:00 — WHY PHYSICS-INFORMED]

A pure data-driven model would work as a black box. The physics-informed approach matters here because the swing equation constrains the network's predictions to be physically plausible. That makes the model's behavior interpretable and its outputs directly usable as engineering inputs — which is a requirement for deploying anything in critical infrastructure.

Total: ~340 words / ~2:00