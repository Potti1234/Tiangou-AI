from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    key: str
    label: str
    area_names: tuple[str, ...]


REGIONS: dict[str, Region] = {
    "hong-kong": Region(
        key="hong-kong",
        label="Hong Kong",
        area_names=("Hong Kong",),
    ),
    "greater-bay-area": Region(
        key="greater-bay-area",
        label="Greater Bay Area",
        area_names=(
            "Hong Kong",
            "Macao",
            "Guangzhou",
            "Shenzhen",
            "Zhuhai",
            "Foshan",
            "Dongguan",
            "Zhongshan",
            "Jiangmen",
            "Huizhou",
            "Zhaoqing",
        ),
    ),
}


def get_region(region_key: str) -> Region:
    try:
        return REGIONS[region_key]
    except KeyError as exc:
        known = ", ".join(sorted(REGIONS))
        raise ValueError(f"Unknown region '{region_key}'. Known regions: {known}") from exc
