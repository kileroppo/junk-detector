"""Platform-specific scoring profiles.

Inspired by x-algorithm's OON Scorer which applies different scoring
adjustments for out-of-network vs in-network content.

Different platforms have different characteristics — a 公众号 article
should be penalized more for being a soft-ad than a tech blog.
"""

from __future__ import annotations

from urllib.parse import urlparse


def detect_platform(url: str | None) -> str:
    """Detect which platform a URL belongs to.

    Uses domain-based matching against the platform configurations
    in config.yaml.

    Args:
        url: The source URL of the content, or None.

    Returns:
        Platform key: "wechat", "xiaohongshu", "zhihu", "blog", or "default".
    """
    if not url:
        return "default"

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
    except Exception:
        return "default"

    if not hostname:
        return "default"

    # Load platform configs and match against domains
    platforms = _load_platform_configs()

    for platform_key, profile in platforms.items():
        if platform_key == "default":
            continue
        domains = profile.get("domains", [])
        for domain in domains:
            # Match exact domain or subdomain (e.g. "mp.weixin.qq.com" matches hostname)
            if hostname == domain or hostname.endswith("." + domain):
                return platform_key

    return "default"


def get_platform_profile(platform: str) -> dict:
    """Load the platform profile from config.yaml.

    Args:
        platform: The platform key (e.g. "wechat", "zhihu", "default").

    Returns:
        Dict with 'weight_overrides' and 'extra_rules'.
        Returns empty profile if platform not found.
    """
    platforms = _load_platform_configs()
    profile = platforms.get(platform, platforms.get("default", {}))

    return {
        "weight_overrides": profile.get("weight_overrides", {}),
        "extra_rules": profile.get("extra_rules", []),
    }


def apply_platform_weights(base_weights: dict[str, float], platform: str) -> dict[str, float]:
    """Merge base weights with platform-specific overrides.

    Platform overrides REPLACE the base weight for that dimension.
    This means if a platform specifies advertorial_prob: -1.5, it
    completely replaces whatever the base config had.

    Args:
        base_weights: The base dimension weights from ScoringConfig.
        platform: The platform key to load overrides for.

    Returns:
        New merged weights dict (does not mutate base_weights).
    """
    profile = get_platform_profile(platform)
    overrides = profile.get("weight_overrides", {})

    if not overrides:
        return base_weights

    # Create a copy and apply overrides (replacement semantics)
    merged = dict(base_weights)
    for dim, weight in overrides.items():
        merged[dim] = weight

    return merged


def get_platform_extra_rules(platform: str) -> list[str]:
    """Get platform-specific extra rule keywords.

    These get added to the rules engine check for this specific content.
    For example, WeChat articles containing "关注公众号" get flagged as
    having self-promotion signals.

    Args:
        platform: The platform key.

    Returns:
        List of keyword strings to check in content.
    """
    profile = get_platform_profile(platform)
    return profile.get("extra_rules", [])


def check_platform_extra_rules(content: str, platform: str) -> list[str]:
    """Check content against platform-specific extra rule keywords.

    Args:
        content: The text content to check.
        platform: The platform key.

    Returns:
        List of matched keywords found in the content.
    """
    extra_rules = get_platform_extra_rules(platform)
    if not extra_rules:
        return []

    matched = [keyword for keyword in extra_rules if keyword in content]
    return matched


def _load_platform_configs() -> dict:
    """Load platform configurations from config.yaml.

    Returns:
        Dict of platform_key → platform profile dict.
        Returns minimal default config if config.yaml is unavailable.
    """
    from src.core.config import _load_yaml

    data = _load_yaml()
    platforms = data.get("platforms", {})

    # Ensure default profile always exists
    if "default" not in platforms:
        platforms["default"] = {"weight_overrides": {}, "extra_rules": []}

    return platforms
