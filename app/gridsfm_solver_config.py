from pathlib import Path


DEFAULT_GRIDSFM_SOLVER_DIR = Path("third_party/gridsfm_solver")

REQUIRED_SOLVER_SCRIPTS = (
    "solve_topo_json.jl",
    "export_gridsfm_data.jl",
    "solve_pyg_json.jl",
    "gen_perturbed_data.jl",
)

