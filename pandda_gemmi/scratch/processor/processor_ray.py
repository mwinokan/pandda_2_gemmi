import ray

from ..interfaces import *

@ray.remote
class RayWrapper(Generic[P, V]):

    def run(self, func: Callable[P, V], *args: P.args, **kwargs: P.kwargs) -> V:
        return func(*args, **kwargs)


@ray.remote
def ray_wrapper(func: Callable[P, V], *args: P.args, **kwargs: P.kwargs) -> V:
    return func(*args, **kwargs)


class ProcessLocalRay(ProcessorInterface):

    def __init__(self, local_cpus):
        self.local_cpus = local_cpus
        ray.init(num_cpus=local_cpus)
        self.tag: Literal["not_async"] = "not_async"

    def __call__(self, funcs: Iterable[PartialInterface[P, V]]) -> List[V]:
        assert ray.is_initialized() == True
        # actors = [RayWrapper.remote() for f in funcs]
        # This isn't properly typeable because the wrapper dynamically costructs the run method on the actor
        # print([f for f in funcs])
        # print([f.args for f in funcs])
        # print(f.kwargs for f in funcs)
        # tasks = [a.run.remote(f.func, *f.args, **f.kwargs) for a, f in zip(actors, funcs)]  # type: ignore
        tasks = [ray_wrapper.remote(f.func, *f.args, **f.kwargs) for f in funcs]
        # print(tasks)
        results = ray.get(tasks)
        # gc.collect()
        return results

    def process_local_ray(self, funcs):
        assert ray.is_initialized() == True
        tasks = [f.func.remote(*f.args, **f.kwargs) for f in funcs]
        results = ray.get(tasks)
        return results


    def process_dict(self, funcs):
        assert ray.is_initialized() == True
        tasks = [ray_wrapper.remote(f.func, *f.args, **f.kwargs) for f in funcs.values()]
        # print(tasks)
        results = ray.get(tasks)

        return {key: result for key, result in zip(funcs, results)}


    def reset(self):
        ray.shutdown()
        ray.init(num_cpus=self.local_cpus)
