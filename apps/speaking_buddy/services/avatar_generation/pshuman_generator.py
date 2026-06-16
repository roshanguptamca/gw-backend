class PSHumanGenerator:
    available = False

    def generate(self, avatar, detected, options):
        raise RuntimeError("PSHuman is not configured; use template generation.")
