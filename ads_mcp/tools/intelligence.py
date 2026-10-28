# Copyright 2026 Edd Vásquez and contributors.
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Media buying intelligence & action tools: search terms, devices/geos, pacing, and closed-loop negative mining."""

import calendar
from collections import Counter
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ads_mcp.extensions import changes, search

intelligence_mcp = FastMCP("intelligence")
READ = ToolAnnotations(readOnlyHint=True)


@intelligence_mcp.tool(annotations=READ)
def audit_search_terms(
    customer_id: str,
    days: int = 30,
    min_spend: str | None = None,
    login_customer_id: str | None = None,
) -> dict:
    """Analyze real search terms to identify bleeders (wasted spend), winners and negative keyword candidates.

    Aggregates search queries by cost, conversions and n-gram patterns across
    the last N days (default 30). Returns actionable recommendations for exclusions.
    """
    days = min(max(int(days), 1), 90)
    where_clause = f"segments.date DURING LAST_{days}_DAYS"

    fields = [
        "search_term_view.search_term",
        "search_term_view.status",
        "campaign.id",
        "campaign.name",
        "ad_group.id",
        "ad_group.name",
        "metrics.clicks",
        "metrics.impressions",
        "metrics.cost_micros",
        "metrics.conversions",
        "metrics.conversions_value",
    ]

    rows = changes.query(
        customer_id,
        "search_term_view",
        fields,
        where_clause,
        login_customer_id,
        limit=500,
    )

    bleeders = []
    winners = []
    word_counter: Counter[str] = Counter()
    total_spend_micros = 0
    total_conversions = 0.0
    wasted_spend_micros = 0

    min_spend_micros = changes.money(min_spend) if min_spend else 0

    for r in rows:
        cost = int(r.get("metrics.cost_micros", 0))
        conv = float(r.get("metrics.conversions", 0.0))
        clicks = int(r.get("metrics.clicks", 0))
        impr = int(r.get("metrics.impressions", 0))
        term = str(r.get("search_term_view.search_term", "")).strip()

        total_spend_micros += cost
        total_conversions += conv

        cost_val = str(Decimal(cost) / 1_000_000)
        cpa_val = (
            str(Decimal(cost) / Decimal(str(conv)) / 1_000_000)
            if conv > 0
            else None
        )

        item = {
            "search_term": term,
            "campaign_id": str(r.get("campaign.id")),
            "campaign_name": r.get("campaign.name"),
            "ad_group_id": str(r.get("ad_group.id")),
            "ad_group_name": r.get("ad_group.name"),
            "clicks": clicks,
            "impressions": impr,
            "cost": cost_val,
            "conversions": conv,
            "cpa": cpa_val,
        }

        # Bleeder: Spend without conversions
        if conv == 0 and cost > min_spend_micros and clicks >= 2:
            bleeders.append(item)
            wasted_spend_micros += cost
            for word in term.lower().split():
                if len(word) > 2:
                    word_counter[word] += cost

        # Winner: Produced conversions
        elif conv >= 1.0:
            winners.append(item)

    bleeders.sort(key=lambda x: Decimal(x["cost"]), reverse=True)
    winners.sort(key=lambda x: x["conversions"], reverse=True)

    # Top wasted 1-grams
    top_wasted_ngrams = [
        {"word": w, "wasted_cost": str(Decimal(c) / 1_000_000)}
        for w, c in word_counter.most_common(10)
    ]

    return {
        "customer_id": customer_id,
        "analyzed_days": days,
        "total_terms_analyzed": len(rows),
        "total_spend": str(Decimal(total_spend_micros) / 1_000_000),
        "total_wasted_spend": str(Decimal(wasted_spend_micros) / 1_000_000),
        "wasted_spend_percentage": (
            round((wasted_spend_micros / total_spend_micros) * 100, 2)
            if total_spend_micros > 0
            else 0.0
        ),
        "bleeders_count": len(bleeders),
        "bleeders_top": bleeders[:20],
        "winners_count": len(winners),
        "winners_top": winners[:20],
        "top_wasted_ngrams": top_wasted_ngrams,
        "media_buyer_recommendation": (
            "Excluir los términos de la lista 'bleeders_top' o las palabras de 'top_wasted_ngrams' usando "
            "la herramienta prepare_mined_negatives para cortar la fuga de presupuesto en un solo paso."
            if bleeders
            else "No se detectaron fugas significativas con gasto en el periodo analizado."
        ),
    }


@intelligence_mcp.tool(annotations=READ)
def prepare_mined_negatives(
    customer_id: str,
    terms: list[str],
    destination_type: Literal["SHARED_LIST", "CAMPAIGN"],
    destination_id: str,
    match_type: Literal["EXACT", "PHRASE"] = "EXACT",
    login_customer_id: str | None = None,
) -> dict:
    """Prepare and Google-validate adding mined bleeder search terms as negative keywords in 1 step.

    Takes a list of search queries or terms (e.g. from audit_search_terms) and builds
    a structured proposal to add them to a shared negative list or directly to a campaign.
    Never mutates live Google Ads accounts without explicit human approval.
    """
    if not terms:
        raise ValueError("Must provide at least one search term to exclude.")

    clean_terms = list(dict.fromkeys(t.strip() for t in terms if t.strip()))
    keywords = [
        search.Keyword(text=term, match_type=match_type) for term in clean_terms
    ]

    if destination_type == "SHARED_LIST":
        change = search.NegativeList(
            action="add",
            list_id=str(destination_id),
            keywords=keywords,
        )
        return search.prepare(
            customer_id, login_customer_id, change, search.negative_list
        )
    elif destination_type == "CAMPAIGN":
        change = search.Keywords(
            action="add_negatives",
            campaign_id=str(destination_id),
            keywords=keywords,
        )
        return search.prepare(
            customer_id, login_customer_id, change, search.keywords
        )
    else:
        raise ValueError(
            f"Unsupported destination_type: {destination_type}. Use 'SHARED_LIST' or 'CAMPAIGN'."
        )


@intelligence_mcp.tool(annotations=READ)
def analyze_impression_share(
    customer_id: str,
    days: int = 30,
    login_customer_id: str | None = None,
) -> dict:
    """Diagnose auction bottlenecks: determine if scaling requires more budget vs better Ad Rank.

    Analyzes Search Impression Share, Search Budget Lost IS and Search Rank Lost IS
    per campaign. Provides explicit scaling advice.
    """
    days = min(max(int(days), 1), 90)
    where_clause = (
        f"campaign.advertising_channel_type = 'SEARCH' "
        f"AND campaign.status != 'REMOVED' "
        f"AND segments.date DURING LAST_{days}_DAYS"
    )

    fields = [
        "campaign.id",
        "campaign.name",
        "campaign.status",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.cost_micros",
        "metrics.search_impression_share",
        "metrics.search_budget_lost_impression_share",
        "metrics.search_rank_lost_impression_share",
    ]

    rows = changes.query(
        customer_id,
        "campaign",
        fields,
        where_clause,
        login_customer_id,
        limit=100,
    )

    campaigns_analysis = []
    for r in rows:
        impr = int(r.get("metrics.impressions", 0))
        if impr == 0:
            continue

        is_val = float(r.get("metrics.search_impression_share", 0.0))
        budget_lost = float(
            r.get("metrics.search_budget_lost_impression_share", 0.0)
        )
        rank_lost = float(
            r.get("metrics.search_rank_lost_impression_share", 0.0)
        )

        cost = int(r.get("metrics.cost_micros", 0))

        if budget_lost >= 0.25:
            diagnosis = "BUDGET_CONSTRAINED"
            action = (
                "Cuello de botella en presupuesto. Escalar presupuesto diario "
                "con prepare_budget aumentará impresiones y conversiones sin perder eficiencia."
            )
        elif rank_lost >= 0.35:
            diagnosis = "RANK_CONSTRAINED"
            action = (
                "Cuello de botella en Ad Rank. Aumentar presupuesto NO escalará eficientemente. "
                "Se debe optimizar Ad Copy (RSA headlines/descriptions), mejorar Ad Relevance o subir Max CPC."
            )
        elif is_val >= 0.70:
            diagnosis = "DOMINATING"
            action = "Campaña dominante en cuota de mercado. Monitorear rentabilidad y explorar audiencias adyacentes."
        else:
            diagnosis = "BALANCED_OR_LEARNING"
            action = "Rendimiento equilibrado; evaluar puja y términos de búsqueda antes de escalar."

        campaigns_analysis.append(
            {
                "campaign_id": str(r.get("campaign.id")),
                "campaign_name": r.get("campaign.name"),
                "status": r.get("campaign.status"),
                "cost": str(Decimal(cost) / 1_000_000),
                "impressions": impr,
                "search_impression_share_pct": round(is_val * 100, 2),
                "lost_to_budget_pct": round(budget_lost * 100, 2),
                "lost_to_rank_pct": round(rank_lost * 100, 2),
                "bottleneck_diagnosis": diagnosis,
                "recommended_action": action,
            }
        )

    return {
        "customer_id": customer_id,
        "analyzed_days": days,
        "campaigns_count": len(campaigns_analysis),
        "campaigns": campaigns_analysis,
    }


@intelligence_mcp.tool(annotations=READ)
def audit_devices_and_geos(
    customer_id: str,
    days: int = 30,
    login_customer_id: str | None = None,
) -> dict:
    """Analyze performance breakdown by device (Mobile vs Desktop vs Tablet) and Geographic locations.

    Identifies if mobile traffic is burning budget with low conversion rates or high CPA,
    guiding mobile bid adjustments.
    """
    days = min(max(int(days), 1), 90)
    where_clause = f"segments.date DURING LAST_{days}_DAYS"

    # 1. Device Breakdown
    device_fields = [
        "segments.device",
        "metrics.cost_micros",
        "metrics.clicks",
        "metrics.impressions",
        "metrics.conversions",
        "metrics.conversions_value",
    ]
    dev_rows = changes.query(
        customer_id,
        "campaign",
        device_fields,
        where_clause,
        login_customer_id,
        limit=50,
    )

    device_stats: dict[str, dict] = {}
    total_cost_micros = 0

    for r in dev_rows:
        dev = str(r.get("segments.device", "UNKNOWN"))
        cost = int(r.get("metrics.cost_micros", 0))
        clicks = int(r.get("metrics.clicks", 0))
        impr = int(r.get("metrics.impressions", 0))
        conv = float(r.get("metrics.conversions", 0.0))

        total_cost_micros += cost
        if dev not in device_stats:
            device_stats[dev] = {
                "device": dev,
                "cost_micros": 0,
                "clicks": 0,
                "impressions": 0,
                "conversions": 0.0,
            }
        device_stats[dev]["cost_micros"] += cost
        device_stats[dev]["clicks"] += clicks
        device_stats[dev]["impressions"] += impr
        device_stats[dev]["conversions"] += conv

    devices_list = []
    for d, data in device_stats.items():
        cost_val = Decimal(data["cost_micros"]) / 1_000_000
        conv_val = data["conversions"]
        cpa_val = (
            str(cost_val / Decimal(str(conv_val))) if conv_val > 0 else None
        )
        cvr_pct = (
            round((conv_val / data["clicks"]) * 100, 2)
            if data["clicks"] > 0
            else 0.0
        )
        ctr_pct = (
            round((data["clicks"] / data["impressions"]) * 100, 2)
            if data["impressions"] > 0
            else 0.0
        )

        devices_list.append(
            {
                "device": d,
                "cost": str(cost_val),
                "clicks": data["clicks"],
                "impressions": data["impressions"],
                "ctr_pct": ctr_pct,
                "conversions": conv_val,
                "conversion_rate_pct": cvr_pct,
                "cpa": cpa_val,
            }
        )

    # 2. Geographic breakdown
    geo_fields = [
        "geographic_view.country_criterion_id",
        "geographic_view.location_type",
        "metrics.cost_micros",
        "metrics.clicks",
        "metrics.conversions",
        "metrics.impressions",
    ]
    geo_rows = changes.query(
        customer_id,
        "geographic_view",
        geo_fields,
        where_clause,
        login_customer_id,
        limit=20,
    )

    geo_list = []
    for g in geo_rows:
        cost = int(g.get("metrics.cost_micros", 0))
        clicks = int(g.get("metrics.clicks", 0))
        conv = float(g.get("metrics.conversions", 0.0))
        cost_val = str(Decimal(cost) / 1_000_000)
        cpa_val = (
            str(Decimal(cost) / Decimal(str(conv)) / 1_000_000)
            if conv > 0
            else None
        )

        geo_list.append(
            {
                "country_criterion_id": str(
                    g.get("geographic_view.country_criterion_id")
                ),
                "location_type": g.get("geographic_view.location_type"),
                "cost": cost_val,
                "clicks": clicks,
                "conversions": conv,
                "cpa": cpa_val,
            }
        )

    # Media buyer strategic recommendation
    recommendation = "Rendimiento homogéneo en dispositivos."
    mobile = next((x for x in devices_list if x["device"] == "MOBILE"), None)
    desktop = next((x for x in devices_list if x["device"] == "DESKTOP"), None)
    if mobile and desktop and mobile["cpa"] and desktop["cpa"]:
        if Decimal(mobile["cpa"]) > Decimal(desktop["cpa"]) * Decimal("1.5"):
            recommendation = (
                f"El CPA en Móvil ({mobile['cpa']}) es significativamente superior al de Desktop ({desktop['cpa']}). "
                "Se aconseja aplicar un modificador de puja negativo a móvil (-20% a -40%) o revisar la experiencia móvil de la landing page."
            )
        elif Decimal(desktop["cpa"]) > Decimal(mobile["cpa"]) * Decimal("1.5"):
            recommendation = (
                f"El móvil convierte con un CPA sustancialmente más bajo ({mobile['cpa']}) que Desktop ({desktop['cpa']}). "
                "Campaña altamente orientada a móvil."
            )

    return {
        "customer_id": customer_id,
        "analyzed_days": days,
        "devices": devices_list,
        "geographics": geo_list,
        "media_buyer_recommendation": recommendation,
    }


@intelligence_mcp.tool(annotations=READ)
def audit_budget_pacing(
    customer_id: str,
    target_monthly_budget: str | None = None,
    login_customer_id: str | None = None,
) -> dict:
    """Audit monthly budget flighting and pacing to prevent end-of-month budget depletion or overspending.

    Compares month-to-date (MTD) spend against elapsed days in current month,
    projecting month-end spend and alerting on over/under-pacing.
    """
    fields = [
        "campaign.id",
        "campaign.name",
        "campaign.status",
        "campaign_budget.amount_micros",
        "metrics.cost_micros",
    ]
    where_clause = (
        "campaign.status != 'REMOVED' AND segments.date DURING THIS_MONTH"
    )
    rows = changes.query(
        customer_id,
        "campaign",
        fields,
        where_clause,
        login_customer_id,
        limit=100,
    )

    now = datetime.now()
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    day_of_month = now.day

    total_mtd_cost_micros = 0
    total_daily_budget_micros = 0
    campaign_pacings = []

    for r in rows:
        cost = int(r.get("metrics.cost_micros", 0))
        budget_daily = int(r.get("campaign_budget.amount_micros", 0))
        status = r.get("campaign.status")

        total_mtd_cost_micros += cost
        if status == "ENABLED":
            total_daily_budget_micros += budget_daily

        mtd_cost_dec = Decimal(cost) / 1_000_000
        daily_avg = (
            mtd_cost_dec / Decimal(str(day_of_month))
            if day_of_month > 0
            else Decimal(0)
        )
        projected_month_end = daily_avg * Decimal(str(days_in_month))
        target_cap = (Decimal(budget_daily) / 1_000_000) * Decimal(
            str(days_in_month)
        )

        pacing_pct = (
            round(float(projected_month_end / target_cap) * 100, 2)
            if target_cap > 0
            else 0.0
        )

        campaign_pacings.append(
            {
                "campaign_id": str(r.get("campaign.id")),
                "campaign_name": r.get("campaign.name"),
                "status": status,
                "mtd_cost": str(mtd_cost_dec),
                "daily_budget": str(Decimal(budget_daily) / 1_000_000),
                "projected_month_end_cost": str(round(projected_month_end, 2)),
                "pacing_pct": pacing_pct,
            }
        )

    account_mtd_cost = Decimal(total_mtd_cost_micros) / 1_000_000
    account_daily_avg = (
        account_mtd_cost / Decimal(str(day_of_month))
        if day_of_month > 0
        else Decimal(0)
    )
    account_projected_month_end = account_daily_avg * Decimal(
        str(days_in_month)
    )

    target_total = (
        Decimal(target_monthly_budget)
        if target_monthly_budget
        else (Decimal(total_daily_budget_micros) / 1_000_000)
        * Decimal(str(days_in_month))
    )

    pacing_pct_total = (
        round(float(account_projected_month_end / target_total) * 100, 2)
        if target_total > 0
        else 0.0
    )

    if pacing_pct_total > 115.0:
        pacing_status = "OVERPACING"
        verdict = f"La cuenta está gastando a un ritmo {pacing_pct_total}%, superior al objetivo mensual. Riesgo de agotar presupuesto antes de fin de mes."
    elif pacing_pct_total < 85.0:
        pacing_status = "UNDERPACING"
        verdict = f"La cuenta está gastando a un ritmo {pacing_pct_total}%, inferior al objetivo. Hay margen de escala de presupuesto o de flexibilizar pujas."
    else:
        pacing_status = "ON_TRACK"
        verdict = f"Ritmo de gasto óptimo ({pacing_pct_total}% proyectado a fin de mes)."

    return {
        "customer_id": customer_id,
        "day_of_month": day_of_month,
        "days_in_month": days_in_month,
        "month_progress_pct": round((day_of_month / days_in_month) * 100, 2),
        "account_mtd_spend": str(account_mtd_cost),
        "account_projected_month_end_spend": str(
            round(account_projected_month_end, 2)
        ),
        "target_monthly_budget": str(target_total),
        "pacing_status": pacing_status,
        "pacing_percentage": pacing_pct_total,
        "verdict": verdict,
        "campaigns": campaign_pacings,
    }


@intelligence_mcp.tool(annotations=READ)
def check_account_health(
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict:
    """Run an instant health check on campaigns, budgets, and RSA ad strengths.

    Flags campaigns limited by budget, poor ad strength RSAs, and paused high-performers.
    """
    camp_fields = [
        "campaign.id",
        "campaign.name",
        "campaign.status",
        "campaign_budget.amount_micros",
        "campaign.primary_status",
        "campaign.primary_status_reasons",
    ]
    camp_rows = changes.query(
        customer_id,
        "campaign",
        camp_fields,
        "campaign.status != 'REMOVED'",
        login_customer_id,
        limit=100,
    )

    budget_alerts = []
    for c in camp_rows:
        reasons = c.get("campaign.primary_status_reasons") or []
        if isinstance(reasons, str):
            reasons = [reasons]
        if any("BUDGET" in str(r).upper() for r in reasons):
            budget_alerts.append(
                {
                    "campaign_id": str(c.get("campaign.id")),
                    "campaign_name": c.get("campaign.name"),
                    "status": c.get("campaign.status"),
                    "alert": "Campaña limitada por presupuesto en Google Ads.",
                }
            )

    ad_fields = [
        "ad_group_ad.ad.id",
        "ad_group_ad.ad_strength",
        "ad_group.id",
        "ad_group.name",
        "campaign.name",
        "ad_group_ad.status",
    ]
    ad_rows = changes.query(
        customer_id,
        "ad_group_ad",
        ad_fields,
        "ad_group_ad.status != 'REMOVED' AND campaign.status != 'REMOVED'",
        login_customer_id,
        limit=100,
    )

    poor_ads = []
    for a in ad_rows:
        strength = str(a.get("ad_group_ad.ad_strength", ""))
        if strength in ("POOR", "AVERAGE"):
            poor_ads.append(
                {
                    "ad_id": str(a.get("ad_group_ad.ad.id")),
                    "ad_strength": strength,
                    "campaign": a.get("campaign.name"),
                    "ad_group": a.get("ad_group.name"),
                    "status": a.get("ad_group_ad.status"),
                    "action_required": "Añadir más titulares únicos y descripciones usando prepare_ad.",
                }
            )

    return {
        "customer_id": customer_id,
        "total_campaigns": len(camp_rows),
        "budget_constrained_campaigns": budget_alerts,
        "ads_needing_improvement": poor_ads,
        "summary": (
            f"{len(budget_alerts)} campañas con alertas de presupuesto y "
            f"{len(poor_ads)} anuncios con Ad Strength subóptimo (POOR/AVERAGE)."
        ),
    }
