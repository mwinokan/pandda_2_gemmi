import time

import ray

from ..interfaces import *

@ray.remote
class RayWrapper(Generic[P, V]):

    def run(self, func: Callable[P, V], *args: P.args, **kwargs: P.kwargs) -> V:
        return func(*args, **kwargs)


@ray.remote
def ray_wrapper(func: Callable[P, V], *args: P.args, **kwargs: P.kwargs) -> V:
    return func(*args, **kwargs)

@ray.remote
def ray_batch_wrapper(funcs, args, kwargs):
    begin = time.time()
    result = [f(*args, **kwargs) for f, args, kwargs in zip(funcs, args, kwargs)]
    finish = time.time()
    print(f"Processed {len(result)} in {round(finish-begin,2)}")
    return result


class ProcessLocalRay(ProcessorInterface):

    def __init__(self, local_cpus):
        self.local_cpus = local_cpus
        ray.init(num_cpus=local_cpus)
        self.tag: Literal["not_async"] = "not_async"

    def put(self, object):
        return ray.put(object)

    def get(self, ref):
        return ray.get(ref)

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
        begin = time.time()
        tasks = [ray_wrapper.remote(f.func, *f.args, **f.kwargs) for f in funcs.values()]
        finish = time.time()
        print(f"\tSubmitted in: {round(finish-begin,1 )}")
        # print(tasks)

        begin = time.time()

        results = ray.get(tasks)
        finish = time.time()
        print(f"\tGet in: {round(finish-begin,1 )}")

        return {key: result for key, result in zip(funcs, results)}

    # def process_dict(self, funcs, ):
    #     assert ray.is_initialized() == True
    #     key_list = list(funcs.keys())
    #     func_list = list(funcs.values())
    #     num_keys = len(key_list)
    #
    #     batch_size = int(len(funcs) / self.local_cpus) + 1
    #
    #     tasks = []
    #     for j in range(self.local_cpus):
    #         funcs = func_list[j*batch_size: min(num_keys, (j+1)*batch_size)]
    #         tasks.append(
    #             ray_batch_wrapper.remote(
    #             [f.func for f in funcs],
    #             [f.args for f in funcs],
    #             [f.kwargs for f in funcs]
    #         )
    #         )
    #
    #     # tasks = [ray_wrapper.remote(f.func, *f.args, **f.kwargs) for f in funcs.values()]
    #     # print(tasks)
    #
    #     results = ray.get(tasks)
    #     result_dict = {}
    #     j = 0
    #     for result in results:
    #         for r in result:
    #             result_dict[key_list[j]] = r
    #             j = j + 1
    #     print(result_dict)
    #     return result_dict
        # return {key: result for key, result in zip(funcs, results)}

    def reset(self):
        ray.shutdown()
        ray.init(num_cpus=self.local_cpus)
