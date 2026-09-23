"""Tests for canonical PDF coordinates, scale semantics, and SI unit conversions."""

import pytest
from tz_plan_pipeline.core.coordinates import (
    CoordinateOrigin,
    DrawingScale,
    PageGeometry,
    ScaleStatus,
    pixels_to_pt,
    pt_to_pixels,
    pt_to_real_world_meters,
    real_world_meters_to_pt,
)
from tz_plan_pipeline.core.errors import (
    ScaleCalibrationError,
    UncalibratedScaleError,
    UnitConversionError,
)
from tz_plan_pipeline.core.units import (
    convert_from_si,
    convert_to_si,
    convert_units,
    get_unit_dimension,
    normalize_unit_str,
    UnitDimension,
)


class TestUnits:
    def test_length_conversions_to_si(self):
        val_si, unit = convert_to_si(1000.0, "mm")
        assert val_si == pytest.approx(1.0)
        assert unit == "m"

        val_si, unit = convert_to_si(150.0, "cm")
        assert val_si == pytest.approx(1.5)
        assert unit == "m"

        val_si, unit = convert_to_si(1.0, "m")
        assert val_si == pytest.approx(1.0)
        assert unit == "m"

    def test_area_and_volume_conversions(self):
        val_si, unit = convert_to_si(250000.0, "cm2")
        assert val_si == pytest.approx(25.0)
        assert unit == "m2"

        val_si, unit = convert_to_si(500.0, "liter")
        assert val_si == pytest.approx(0.5)
        assert unit == "m3"

    def test_convert_between_units(self):
        # 2.5 meters to millimeters
        mm = convert_units(2.5, "m", "mm")
        assert mm == pytest.approx(2500.0)

        # 300 mm to cm
        cm = convert_units(300.0, "mm", "cm")
        assert cm == pytest.approx(30.0)

    def test_incompatible_dimensions_raise_error(self):
        with pytest.raises(UnitConversionError, match="Incompatible unit conversion"):
            convert_units(10.0, "m", "m2")

    def test_unknown_unit_raises_error(self):
        with pytest.raises(UnitConversionError, match="Cannot convert unknown unit"):
            convert_to_si(10.0, "lightyears")


class TestCoordinatesAndScales:
    def test_pt_and_pixels_conversion(self):
        # At 72 DPI, 1 pt = 1 pixel
        assert pt_to_pixels(72.0, dpi=72.0) == 72.0
        assert pixels_to_pt(72.0, dpi=72.0) == 72.0

        # At 300 DPI, 72 pt (1 inch) = 300 pixels
        assert pt_to_pixels(72.0, dpi=300.0) == pytest.approx(300.0)
        assert pixels_to_pt(300.0, dpi=300.0) == pytest.approx(72.0)

    def test_uncalibrated_scale_prohibits_authoritative_measurement(self):
        # Declared scale (e.g. printed 'M=1:50') is NOT authoritative
        scale = DrawingScale(
            status=ScaleStatus.DECLARED,
            declared_ratio=50.0,
            declared_label="M=1:50"
        )
        assert not scale.is_authoritative()

        # Converting with require_authoritative=True must raise UncalibratedScaleError
        with pytest.raises(UncalibratedScaleError, match="Printed scale labels .* must be calibrated"):
            pt_to_real_world_meters(100.0, scale, require_authoritative=True)

        # In non-authoritative exploratory mode, it can return preliminary value
        exploratory_m = pt_to_real_world_meters(100.0, scale, require_authoritative=False)
        assert exploratory_m > 0

    def test_scale_calibration_success(self):
        # At 1:50 scale: 1 meter in real world = 1/50 m on paper = 0.02 m on paper.
        # 0.02 m on paper in pt = 0.02 / (0.0254 / 72) = 56.6929 pt.
        declared = DrawingScale(
            status=ScaleStatus.DECLARED,
            declared_ratio=50.0,
            declared_label="M=1:50"
        )
        measured_pt = 56.692913
        calibrated = declared.calibrate(
            measured_pt=measured_pt,
            actual_meters=1.0,
            evidence_id="dim-line-001",
            calibrated_by="architect_verified"
        )

        assert calibrated.status == ScaleStatus.CALIBRATED
        assert calibrated.is_authoritative()
        assert calibrated.calibrated_ratio == pytest.approx(50.0, rel=1e-3)

        # Now authoritative measurement works
        real_m = pt_to_real_world_meters(measured_pt, calibrated, require_authoritative=True)
        assert real_m == pytest.approx(1.0, rel=1e-3)

    def test_scale_calibration_failure(self):
        # Expected ~56.7 pt for 1 meter at 1:50, but measured 100 pt -> diff is way over 1% tolerance
        declared = DrawingScale(
            status=ScaleStatus.DECLARED,
            declared_ratio=50.0,
            tolerance_percent=1.0
        )
        failed = declared.calibrate(
            measured_pt=100.0,
            actual_meters=1.0
        )
        assert failed.status == ScaleStatus.FAILED_CALIBRATION
        assert not failed.is_authoritative()

        with pytest.raises(UncalibratedScaleError):
            pt_to_real_world_meters(100.0, failed, require_authoritative=True)

    def test_page_geometry_validation(self):
        geom = PageGeometry(
            width_pt=841.89,
            height_pt=595.28,
            rotation=0,
            origin=CoordinateOrigin.TOP_LEFT
        )
        assert geom.width_pt > 0
        assert geom.height_pt > 0

        with pytest.raises(ValueError, match="Invalid page rotation"):
            PageGeometry(width_pt=100, height_pt=100, rotation=45)
