"""Experiment configuration and the local experiment runner (PRD §12–§15)."""

from tamil_tts.experiment.config import ExperimentConfig, load_experiment_config
from tamil_tts.experiment.runner import ExperimentError, RunOptions, RunSummary, run_experiment

__all__ = [
    "ExperimentConfig",
    "ExperimentError",
    "RunOptions",
    "RunSummary",
    "load_experiment_config",
    "run_experiment",
]
