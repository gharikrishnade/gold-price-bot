"""
price_validator.py - Validation for scraped gold price data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


MIN_PER_GRAM_PRICE = 1000
MAX_PER_GRAM_PRICE = 20000


@dataclass
class CityValidation:
    city: str
    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class PriceValidationResult:
    valid: bool
    city_results: list[CityValidation]

    def to_dict(self) -> dict[str, Any]:
        failed = [city for city in self.city_results if not city.valid]
        return {
            "valid": self.valid,
            "checked_cities": len(self.city_results),
            "failed_cities": [
                {"city": city.city, "errors": city.errors}
                for city in failed
            ],
        }


def validate_state_price_data(price_data: dict[str, Any]) -> PriceValidationResult:
    """Validate that every city has complete, plausible 22K and 24K prices."""
    city_results = [
        _validate_city_prices(city, prices or {})
        for city, prices in price_data.get("cities", {}).items()
    ]

    if not city_results:
        city_results.append(CityValidation("all", False, ["no city price data found"]))

    return PriceValidationResult(
        valid=all(city.valid for city in city_results),
        city_results=city_results,
    )


def _validate_city_prices(city: str, prices: dict[str, Any]) -> CityValidation:
    errors = []
    required_fields = (
        "22k_per_gram",
        "24k_per_gram",
        "22k_per_10g",
        "24k_per_10g",
    )

    for field_name in required_fields:
        value = prices.get(field_name)
        if not _is_positive_number(value):
            errors.append(f"{field_name} must be a positive number")

    if errors:
        return CityValidation(city, False, errors)

    for field_name in ("22k_per_gram", "24k_per_gram"):
        value = float(prices[field_name])
        if value < MIN_PER_GRAM_PRICE or value > MAX_PER_GRAM_PRICE:
            errors.append(
                f"{field_name}={value:g} is outside expected range "
                f"{MIN_PER_GRAM_PRICE}-{MAX_PER_GRAM_PRICE}"
            )

    _validate_10g_consistency("22k", prices, errors)
    _validate_10g_consistency("24k", prices, errors)

    if float(prices["24k_per_gram"]) < float(prices["22k_per_gram"]):
        errors.append("24k_per_gram must be greater than or equal to 22k_per_gram")

    return CityValidation(city, not errors, errors)


def _validate_10g_consistency(prefix: str, prices: dict[str, Any], errors: list[str]) -> None:
    per_gram = float(prices[f"{prefix}_per_gram"])
    per_10g = float(prices[f"{prefix}_per_10g"])
    expected = per_gram * 10
    tolerance = max(5, expected * 0.01)
    if abs(per_10g - expected) > tolerance:
        errors.append(
            f"{prefix}_per_10g={per_10g:g} does not match {prefix}_per_gram x 10"
        )


def _is_positive_number(value: Any) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False
