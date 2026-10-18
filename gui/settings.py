"""Persistent user settings (QSettings, per Windows user)."""

import json
import os

from core import APP_AUTHOR, APP_NAME
from core.overview.options import OverviewOptions
from PySide6.QtCore import QSettings

SETTINGS_FILE_ENV = "DC6OV_SETTINGS_FILE"  # optional .ini path instead of the registry (tests)


class Settings:
    def __init__(self) -> None:
        ini = os.environ.get(SETTINGS_FILE_ENV)
        self._s = QSettings(ini, QSettings.Format.IniFormat) if ini else QSettings(APP_AUTHOR, APP_NAME)

    def _get(self, key: str, default, kind=str):
        value = self._s.value(key, default)
        try:
            return kind(value)
        except (TypeError, ValueError):
            return default

    # viewer
    @property
    def default_zoom(self) -> int:
        return self._get("viewer/default_zoom", 8, int)

    @default_zoom.setter
    def default_zoom(self, value: int) -> None:
        self._s.setValue("viewer/default_zoom", int(value))

    @property
    def palette(self) -> str:
        return self._get("viewer/palette", "act1")

    @palette.setter
    def palette(self, value: str) -> None:
        self._s.setValue("viewer/palette", value)

    def last_dir(self, key: str, default: str = "") -> str:
        return self._get(f"dirs/{key}", default)

    def set_last_dir(self, key: str, path: str) -> None:
        self._s.setValue(f"dirs/{key}", path)

    @property
    def export_format(self) -> str:
        return self._get("viewer/export_format", "BMP")

    @export_format.setter
    def export_format(self, value: str) -> None:
        self._s.setValue("viewer/export_format", value)

    # overview
    def overview_options(self) -> OverviewOptions:
        try:
            return OverviewOptions.from_dict(json.loads(self._get("overview/options", "{}")))
        except (json.JSONDecodeError, TypeError):
            return OverviewOptions()

    def set_overview_options(self, opts: OverviewOptions) -> None:
        self._s.setValue("overview/options", json.dumps(opts.to_dict()))

    @property
    def output_dir(self) -> str:
        return self._get("overview/output_dir", "")

    @output_dir.setter
    def output_dir(self, value: str) -> None:
        self._s.setValue("overview/output_dir", value)

    # window
    def geometry(self):
        return self._s.value("window/geometry")

    def set_geometry(self, data) -> None:
        self._s.setValue("window/geometry", data)
