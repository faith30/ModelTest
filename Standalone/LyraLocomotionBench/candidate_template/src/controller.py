"""Candidate entry point. This template contains no locomotion implementation."""


class LocomotionController:
    def __init__(self, graph: dict, assets: dict) -> None:
        self.graph = graph
        self.assets = assets
        # TODO: Initialize the candidate's configuration and state.

    def reset(self, seed: int = 0) -> None:
        """Reset all state affecting subsequent plans. See INTERFACE.md."""
        raise NotImplementedError("TODO: implement controller reset")

    def step(self, frame: dict) -> dict:
        """Return players, sync_groups and pose_operations for one input frame."""
        raise NotImplementedError("TODO: implement locomotion planning")
