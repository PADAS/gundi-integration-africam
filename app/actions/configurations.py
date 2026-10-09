import string
import pydantic
from datetime import datetime
from typing import List, Optional
from app.actions.core import PullActionConfiguration
from app.services.utils import FieldWithUIOptions, UIOptions, GlobalUISchemaOptions

_DEFAULT_URL_TEMPLATE = "https://ranger-media.africam.com/gallery/{africam_event_id}"


def _reference(action: str, params: Optional[dict] = None, *, target: str = "self") -> dict:
    """Build a gundi:reference ui_schema annotation (same helper as the
    EarthRanger and cmore runners). Deliberately does NOT set ui:widget, so
    portals without reference support keep rendering plain text fields.

    ``target="destination"`` directs the portal to fetch from the destination
    integration(s) of this provider's connection instead of from this
    integration: the EarthRanger vocabulary this runner filters on is served
    by the EarthRanger runner's own reference actions.
    """
    return {
        "action": action,
        "target": target,
        "params": params or {},
        "allow_free_text": True,
    }


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
        description=(
            "Maximum number of hours to look back for events. Used as the window on "
            "the first run and as a cap on every later run."
        ),
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
    start_datetime: Optional[datetime] = FieldWithUIOptions(
        None,
        title="Start Datetime",
        description=(
            "ISO-8601 timestamp. Used only while 'Force Run From Start Datetime' is on: "
            "every configured event type is then fetched from this moment instead of from "
            "its saved watermark. Ignored otherwise."
        ),
        ui_options=UIOptions(widget="date-time"),
    )
    force_run_since_start: bool = FieldWithUIOptions(
        False,
        title="Force Run From Start Datetime",
        description=(
            "Resets the per-event-type watermarks so the next run starts at 'Start Datetime' "
            "(the Lookback Hours cap does not apply). Turn it off again once the catch-up run "
            "completes; while it stays on, every run re-pulls from 'Start Datetime'."
        ),
    )
    ui_global_options = GlobalUISchemaOptions(
        order=[
            "africam_api_url",
            "africam_token",
            "event_types",
            "lookback_hours",
            "africam_event_url_template",
            "start_datetime",
            "force_run_since_start",
            "run_on_schedule",
        ]
    )

    @classmethod
    def ui_schema(cls, *args, **kwargs):
        """Annotate event_types so the portal renders each item as a live
        dropdown of the EarthRanger destination's event types (its
        ``list_event_types`` reference action). The runner reads the ER site
        from the connection's destination at run time, so the dropdown offers
        exactly the slugs the pull can resolve. Free text stays allowed, and
        the list only populates once a destination is attached to the route.
        The annotation sits on the array's ``items`` node so rjsf applies it
        to every element.
        """
        base = super().ui_schema(*args, **kwargs)
        base["event_types"] = {"items": {"gundi:reference": _reference("list_event_types", target="destination")}}
        return base

    @pydantic.validator("start_datetime", pre=True)
    def empty_start_datetime_is_none(cls, v):
        # A cleared date-time picker submits "" rather than omitting the field.
        return None if v == "" else v

    @pydantic.root_validator(skip_on_failure=True)
    def force_run_requires_start_datetime(cls, values):
        if values.get("force_run_since_start") and values.get("start_datetime") is None:
            raise ValueError("start_datetime is required when force_run_since_start is enabled")
        return values

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
