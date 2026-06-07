Tiangou AI — 2-Minute Technical Script (revised)
[0:00 – 0:18 — CONTEXT]

Power grids are designed to operate at a fixed frequency. When generation and demand go out of balance, frequency deviates. Relay protection systems trip generators automatically below certain thresholds, which can trigger a cascade. The challenge is detecting and responding to imbalances fast enough to stay within those bounds.

[0:18 – 0:42 — THE GRID WE BUILT ON]

We grounded this in a real grid. Our Hong Kong energy grid was reconstructed from OpenStreetMap data. That gave us real transmission distances, node locations, and a generation mix that reflects an actual system: coal and gas as the backbone, a nuclear import link, offshore wind, solar, and grid-scale battery storage.


[0:42 – 1:22 — WHAT TIANGOU AI DOES]

We built a Physics-Informed Neural Network trained on synthetic Hong Kong grid data. The network predicts frequency trajectories over the next 60 seconds, constrained throughout by the swing equation — allowing it to infer normally hidden grid dynamics such as effective inertia directly from observed state.

Every second, we take the current generation and demand, plug them into the model, and roll out that trajectory. If our risk score — based on the predicted frequency minimum, the inferred grid dynamics, and the current frequency — breaches a certain threshold, we issue dispatch commands immediately, often before the frequency has actually started falling.

That trajectory-based trigger typically gives 30 to 60 seconds of additional lead time compared to waiting for rate-of-change thresholds to fire.

[1:22 – 1:46 — DISPATCH LOGIC]

The dispatch layer selects the minimum set of actions needed to lift the predicted frequency above threshold. Fast resources like battery storage respond in the same second. Slower resources like gas turbines are pre-warmed so they're available in way shorter time.

Here, we run two parallel simulation timelines: one with no intervention, one with AI-guided dispatch. The difference in outcomes — specifically the frequency and whether cascade conditions are reached — is what the system is evaluated against.

[1:46 – 2:00 — WHY PHYSICS-INFORMED]

A pure data-driven model would work as a black box. The physics-informed approach matters here because the swing equation constrains the network's predictions to be physically plausible. That makes the model's behavior interpretable and its outputs directly usable as engineering inputs — which is a requirement for deploying anything in critical infrastructure.

Total: ~360 words / ~2:00
