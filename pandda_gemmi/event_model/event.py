from ..interfaces import *


class EventBuild(EventBuildInterface):
    def __init__(self, build_path, ligand_key, score, centroid, bdc, build_score=0.0, noise=0.0, signal=0.0, num_contacts=0):
        self.build_path = build_path
        self.ligand_key = ligand_key
        self.score = score
        self.centroid = centroid
        self.bdc = bdc
        self.build_score = build_score
        self.noise = noise
        self.signal = signal
        self.num_contacts = num_contacts


class Event(EventInterface):
    def __init__(self, pos_array, point_array, centroid, score=0.0, bdc=0.0, build=None):
        self.pos_array = pos_array
        self.point_array = point_array
        self.centroid = centroid
        self.score = score
        self.bdc = bdc
        self.build = build