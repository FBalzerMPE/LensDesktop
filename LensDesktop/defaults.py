import configparser
from dataclasses import dataclass
from pathlib import Path

from .processing import ChromaKeySettings


class DefaultsError(RuntimeError):
    pass


@dataclass(frozen=True)
class SourceDefaults:
    expanded: bool
    camera_setup_expanded: bool
    camera_index: int
    default_source: str


@dataclass(frozen=True)
class InputDefaults:
    expanded: bool
    key: ChromaKeySettings
    framing: str
    mirror: str
    preview: str
    zoom: int
    loaded_image_fitting: str
    frozen_input_fitting: str


@dataclass(frozen=True)
class BackgroundDefaults:
    expanded: bool
    fitting: str
    image: str


@dataclass(frozen=True)
class ConfigurationDefaults:
    expanded: bool
    enabled: bool
    size: int
    preset: str


@dataclass(frozen=True)
class PlacementDefaults:
    expanded: bool
    scale: int
    offset_x: int
    offset_y: int


@dataclass(frozen=True)
class ViewDefaults:
    expanded: bool
    critical_curve: bool
    dual_view: bool
    de_lensing: bool
    lens_light: bool


@dataclass(frozen=True)
class LensDefaults:
    expanded: bool
    einstein_radius: int
    axis_ratio: int
    core_radius: int
    position_angle: int
    mask_radius: int
    heart: bool


@dataclass(frozen=True)
class ExportDefaults:
    expanded: bool


@dataclass(frozen=True)
class GuiDefaults:
    source: SourceDefaults
    input: InputDefaults
    background: BackgroundDefaults
    configuration: ConfigurationDefaults
    placement: PlacementDefaults
    view: ViewDefaults
    lens: LensDefaults
    export: ExportDefaults


SECTION_KEYS = {
    "Source": {"expanded", "camera_setup_expanded", "camera_index", "default_source"},
    "Input / greenscreen": {
        "expanded",
        "key_enabled",
        "key_color",
        "key_tolerance",
        "key_softness",
        "key_saturation",
        "key_spill",
        "framing",
        "mirror",
        "preview",
        "zoom",
        "loaded_image_fitting",
        "frozen_input_fitting",
    },
    "Sky background": {"expanded", "fitting", "default_image"},
    "Source relative to lens": {"expanded", "enabled", "size", "preset"},
    "Source placement": {"expanded", "scale", "offset_x", "offset_y"},
    "View": {"expanded", "critical_curve", "dual_view", "de_lensing", "lens_light"},
    "Lens": {
        "expanded",
        "einstein_radius",
        "axis_ratio",
        "core_radius",
        "position_angle",
        "mask_radius",
        "heart",
    },
    "Print / export": {"expanded"},
}


def defaults_path() -> Path:
    return Path(__file__).resolve().parent.parent / "data" / "defaults.ini"


def _section(parser, name, path):
    if not parser.has_section(name):
        raise DefaultsError(f"Missing [{name}] section in GUI defaults: {path}")
    section = parser[name]
    expected = SECTION_KEYS[name]
    actual = set(section)
    if actual != expected:
        missing, unknown = sorted(expected - actual), sorted(actual - expected)
        details = []
        if missing:
            details.append(f"missing options: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown options: {', '.join(unknown)}")
        raise DefaultsError(f"Invalid [{name}] section in {path}: {'; '.join(details)}")
    return section


def _boolean(section, name, option, path):
    try:
        return section.getboolean(option)
    except (configparser.Error, ValueError) as error:
        raise DefaultsError(
            f"Invalid [{name}] {option} in GUI defaults: {path}"
        ) from error


def _integer(section, name, option, minimum, maximum, path):
    try:
        value = section.getint(option)
    except (configparser.Error, ValueError) as error:
        raise DefaultsError(
            f"Invalid integer [{name}] {option} in GUI defaults: {path}"
        ) from error
    if not minimum <= value <= maximum:
        raise DefaultsError(
            f"[{name}] {option} must be between {minimum} and {maximum}: {path}"
        )
    return value


def _choice(section, name, option, choices, path):
    value = section.get(option).strip().lower()
    if value not in choices:
        raise DefaultsError(
            f"[{name}] {option} must be one of {', '.join(choices)}: {path}"
        )
    return value


def load_gui_defaults(path: str | Path | None = None) -> GuiDefaults:
    path = Path(path) if path is not None else defaults_path()
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with path.open("r", encoding="utf-8") as config_file:
            parser.read_file(config_file)
    except (OSError, UnicodeError, configparser.Error) as error:
        raise DefaultsError(f"Cannot load GUI defaults from {path}: {error}") from error
    if parser.defaults():
        raise DefaultsError(f"Unexpected DEFAULT section in GUI defaults: {path}")
    unknown_sections = set(parser.sections()) - set(SECTION_KEYS)
    if unknown_sections:
        raise DefaultsError(
            f"Unknown GUI defaults sections in {path}: {', '.join(sorted(unknown_sections))}"
        )

    sections = {
        name: _section(parser, name, path)
        for name in SECTION_KEYS
    }
    source = sections["Source"]
    input_settings = sections["Input / greenscreen"]
    background = sections["Sky background"]
    configuration = sections["Source relative to lens"]
    placement = sections["Source placement"]
    view = sections["View"]
    lens = sections["Lens"]
    export = sections["Print / export"]

    color_value = input_settings.get("key_color").strip()
    if (
        len(color_value) != 7
        or color_value[0] != "#"
        or any(character not in "0123456789abcdefABCDEF" for character in color_value[1:])
    ):
        raise DefaultsError(f"[Input / greenscreen] key_color must be #RRGGBB: {path}")
    color = tuple(int(color_value[index:index + 2], 16) for index in (1, 3, 5))
    data_path = defaults_path().parent.resolve()
    background_name = background.get("default_image").strip()
    background_path = (data_path / background_name).resolve()
    if (
        Path(background_name).name != background_name
        or not background_path.is_relative_to(data_path.resolve())
        or not background_path.is_file()
    ):
        raise DefaultsError(
            f"[Sky background] default_image must name an existing bundled image: {path}"
        )

    try:
        key = ChromaKeySettings(
            enabled=_boolean(input_settings, "Input / greenscreen", "key_enabled", path),
            color=color,
            tolerance=_integer(input_settings, "Input / greenscreen", "key_tolerance", 0, 180, path),
            softness=_integer(input_settings, "Input / greenscreen", "key_softness", 0, 90, path),
            saturation=_integer(input_settings, "Input / greenscreen", "key_saturation", 0, 100, path) / 100,
            spill=_integer(input_settings, "Input / greenscreen", "key_spill", 0, 100, path) / 100,
        )
    except ValueError as error:
        raise DefaultsError(f"Invalid chroma-key GUI defaults: {path}: {error}") from error

    return GuiDefaults(
        SourceDefaults(
            _boolean(source, "Source", "expanded", path),
            _boolean(source, "Source", "camera_setup_expanded", path),
            _integer(source, "Source", "camera_index", 0, 99, path),
            _choice(source, "Source", "default_source", ("desktop", "hand_example"), path),
        ),
        InputDefaults(
            _boolean(input_settings, "Input / greenscreen", "expanded", path),
            key,
            _choice(input_settings, "Input / greenscreen", "framing", ("default", "fit", "fill"), path),
            _choice(input_settings, "Input / greenscreen", "mirror", ("default", "off", "on"), path),
            _choice(input_settings, "Input / greenscreen", "preview", ("scene", "source", "mask"), path),
            _integer(input_settings, "Input / greenscreen", "zoom", 100, 400, path),
            _choice(input_settings, "Input / greenscreen", "loaded_image_fitting", ("fit", "fill"), path),
            _choice(input_settings, "Input / greenscreen", "frozen_input_fitting", ("fit", "fill"), path),
        ),
        BackgroundDefaults(
            _boolean(background, "Sky background", "expanded", path),
            _choice(background, "Sky background", "fitting", ("fill", "fit"), path),
            background_name,
        ),
        ConfigurationDefaults(
            _boolean(configuration, "Source relative to lens", "expanded", path),
            _boolean(configuration, "Source relative to lens", "enabled", path),
            _integer(configuration, "Source relative to lens", "size", 1, 100, path),
            _choice(configuration, "Source relative to lens", "preset", ("cross", "cusp", "fold"), path),
        ),
        PlacementDefaults(
            _boolean(placement, "Source placement", "expanded", path),
            _integer(placement, "Source placement", "scale", 10, 200, path),
            _integer(placement, "Source placement", "offset_x", -100, 100, path),
            _integer(placement, "Source placement", "offset_y", -100, 100, path),
        ),
        ViewDefaults(
            _boolean(view, "View", "expanded", path),
            _boolean(view, "View", "critical_curve", path),
            _boolean(view, "View", "dual_view", path),
            _boolean(view, "View", "de_lensing", path),
            _boolean(view, "View", "lens_light", path),
        ),
        LensDefaults(
            _boolean(lens, "Lens", "expanded", path),
            _integer(lens, "Lens", "einstein_radius", 40, 99, path),
            _integer(lens, "Lens", "axis_ratio", 40, 99, path),
            _integer(lens, "Lens", "core_radius", 40, 99, path),
            _integer(lens, "Lens", "position_angle", 40, 99, path),
            _integer(lens, "Lens", "mask_radius", 40, 99, path),
            _boolean(lens, "Lens", "heart", path),
        ),
        ExportDefaults(_boolean(export, "Print / export", "expanded", path)),
    )
