def calculate_compatibility_score(user_chart, crush_chart):
    score = 50
    pairs = [
        ("Sun", "Moon"),
        ("Moon", "Moon"),
        ("Venus", "Mars"),
        ("Mars", "Venus"),
        ("Sun", "Venus"),
        ("Moon", "Venus"),
    ]

    # Safely extract planets dicts (default to empty)
    user_planets = user_chart.get("planets", {}) if isinstance(user_chart, dict) else {}
    crush_planets = crush_chart.get("planets", {}) if isinstance(crush_chart, dict) else {}

    for u, c in pairs:
        user_planet = user_planets.get(u)
        crush_planet = crush_planets.get(c)
        if not user_planet or not crush_planet:
            continue

        diff = abs(user_planet.get("longitude", 0) - crush_planet.get("longitude", 0)) % 360
        if diff > 180:
            diff = 360 - diff

        if diff < 5:
            score += 10
        elif diff < 15:
            score += 6
        elif abs(diff - 60) < 5:
            score += 4
        elif abs(diff - 120) < 5:
            score += 5
        elif abs(diff - 90) < 5:
            score -= 3
        elif abs(diff - 180) < 5:
            score -= 5

    # Rescale raw score (50–100) to premium range (76–98)
    min_raw, max_raw = 50, 100
    min_premium, max_premium = 76, 98
    score = min_premium + (score - min_raw) * (max_premium - min_premium) / (max_raw - min_raw)
    return round(score)
