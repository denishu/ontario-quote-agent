from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """Base for all schema models. Rejects unknown fields so a typo in a
    hand-edited intake.json (or a malformed automation-written result)
    fails loudly at load time instead of being silently dropped.
    """

    model_config = ConfigDict(extra="forbid")
