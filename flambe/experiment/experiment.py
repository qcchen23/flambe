from typing import Optional, Dict

import ray

from flambe.compile import Schema
from flambe.search import Algorithm
from flambe.runner.runnable import Runnable, Environment
from flambe.experiment.pipeline import Pipeline
from flambe.experiment.stage import Stage


class Experiment(Runnable):

    def __init__(self,
                 name: str,
                 save_path: str = 'flambe_output',
                 pipeline: Optional[Dict[str, Schema]] = None,
                 algorithm: Optional[Dict[str, Algorithm]] = None,
                 reduce: Optional[Dict[str, int]] = None,
                 cpus_per_trial: Dict[str, int] = None,
                 gpus_per_trial: Dict[str, int] = None) -> None:
        """Iniatilize an experiment.

        Parameters
        ----------
        name : str
            The name of the experiment to run.
        pipeline : Optional[Dict[str, Schema]], optional
            A set of Searchable schemas, possibly including links.
        save_path : Optional[str], optional
            [description], by default None
        algorithm : Optional[Dict[str, Algorithm]], optional
            [description], by default None
        reduce : Optional[Dict[str, int]], optional
            [description], by default None
        cpus_per_trial : int
            The number of CPUs to allocate per trial.
            Note: if the object you are searching over spawns ray
            remote tasks, then you should set this to 1.
        gpus_per_trial : int
            The number of GPUs to allocate per trial.
            Note: if the object you are searching over spawns ray
            remote tasks, then you should set this to 0.

        """
        self.name = name
        self.save_path = save_path
        self.pipeline = pipeline if pipeline is not None else dict()
        self.algorithm = algorithm if algorithm is not None else dict()
        self.reduce = reduce if reduce is not None else dict()
        self.cpus_per_trial: Dict[str, int] = dict()
        self.gpus_per_trial: Dict[str, int] = dict()

    def run(self, env: Optional[Environment] = None):
        """Execute the Experiment.

        Parameters
        ----------
        env : Environment, optional
            An optional environment object.

        """
        # Set up envrionment
        env = env if env is not None else Environment(self.save_path)
        if not ray.is_initialized():
            ray.init("auto", local_mode=env.debug)

        stage_to_id: Dict[str, int] = {}
        pipeline = Pipeline(self.pipeline)

        # Construct and execute stages as a DAG
        for name, schema in pipeline.schemas.items():
            # Get dependencies
            sub_pipeline = pipeline.sub_pipeline(name)
            depedency_ids = [stage_to_id[d] for d in sub_pipeline.dependencies]

            # Construct the stage
            stage = ray.remote(Stage).remote(
                name=name,
                pipeline=sub_pipeline,
                reductions=self.reduce.get(name, None),
                dependencies=depedency_ids,  # Passing object ids sets the order of computation
                cpus_per_trial=self.cpus_per_trial.get(name, None),
                gpus_per_trial=self.gpus_per_trial.get(name, None),
                environment=env
            )

            # Execute the stage remotely
            object_id = stage.run.remote()
            # Keep the object id, to use as future dependency
            stage_to_id[name] = object_id

        # Wait until the extperiment is done
        # TODO progress tracking
        ray.wait(stage_to_id.values(), num_returns=len(stage_to_id))
