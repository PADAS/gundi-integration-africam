import string
import pydantic
from typing import List
from app.actions.core import PullActionConfiguration
from app.services.utils import FieldWithUIOptions, UIOptions, GlobalUISchemaOptions

_DEFAULT_URL_TEMPLATE = "https://ranger-media.africam.com/gallery/{africam_event_id}"


class AfricamActionConfiguration(PullActionConfiguration):
    africam_api_url: str = FieldWithUIOptions(
        "https://ranger-media.africam.com",
        title="Africam API URL",
        description="Base URL of the Africam API.",
    )
    africam_token: pydantic.SecretStr = FieldWithUIOptions(
        ...,
        title="Africam API Token",
        description="Bearer token for authenticating with Africam.",
        ui_options=UIOptions(widget="password"),
    )
    event_types: List[str] = FieldWithUIOptions(
        ["wildlife_sighting"],
        title="Event Types",
        description="EarthRanger event types to forward to Africam.",
    )
    lookback_hours: int = FieldWithUIOptions(
        1,
        ge=1,
        le=168,
        title="Lookback Hours",
        description="How many hours back to look for events on the first run.",
        ui_options=UIOptions(widget="range"),
    )
    africam_event_url_template: str = FieldWithUIOptions(
        _DEFAULT_URL_TEMPLATE,
        regex=r"^https://.*\{africam_event_id\}.*$",
        title="Africam Event URL Template",
        description=(
            "Format string used to build the Africam gallery URL stored in the "
            "EarthRanger event details. Must contain {africam_event_id}. "
            f"Default: {_DEFAULT_URL_TEMPLATE}"
        ),
        ui_options=UIOptions(widget="text"),
    )
    ui_global_options = GlobalUISchemaOptions(
        order=[
            "africam_api_url",
            "africam_token",
            "event_types",
            "lookback_hours",
            "africam_event_url_template",
        ]
    )

    @pydantic.validator("africam_event_url_template")
    def validate_url_template(cls, v):
        # Verify {africam_event_id} is present
        field_names = {
            fname
            for _, fname, _, _ in string.Formatter().parse(v)
            if fname is not None
        }
        if "africam_event_id" not in field_names:
            raise ValueError("Template must contain the {africam_event_id} placeholder.")
        # Verify the string is a valid format string with only africam_event_id
        try:
            v.format(africam_event_id="test-id")
        except (KeyError, IndexError) as exc:
            raise ValueError(f"Invalid format string: {exc}") from exc
        return v
