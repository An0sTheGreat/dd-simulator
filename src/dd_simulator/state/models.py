"""Small typed records exposed by state repositories."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CampaignRecord:
    campaign_id: str
    name: str
    status: str
    created_at: str
    updated_at: str
    creation_complete: bool = True
    premise: str = ""
