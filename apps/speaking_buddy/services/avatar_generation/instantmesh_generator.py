class InstantMeshGenerator:
    available = False

    def generate(self, avatar, detected, options):
        raise RuntimeError("InstantMesh is not configured; use template generation.")
