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


@intelligence_mcp.tool(annotations=READ)
def audit_campaign_assets(
    customer_id: str,
    campaign_id: str | None = None,
    login_customer_id: str | None = None,
) -> dict:
    """Audit ad asset coverage (sitelinks, callouts, snippets, calls) to diagnose Ad Rank penalties.

    Checks which extensions are attached, enabled, or paused, calculating an asset
    completeness score per campaign to unlock maximum Ad Rank and lower CPCs.
    """
    fields = [
        "campaign.id",
        "campaign.name",
        "campaign.status",
        "campaign_asset.asset",
        "campaign_asset.field_type",
        "campaign_asset.status",
        "asset.name",
        "asset.type",
    ]
    where_clause = (
        "campaign.status != 'REMOVED' AND campaign_asset.status != 'REMOVED'"
    )
    if campaign_id:
        where_clause += f" AND campaign.id = {campaign_id}"

    rows = changes.query(
        customer_id,
        "campaign_asset",
        fields,
        where_clause,
        login_customer_id,
        limit=200,
    )

    campaigns: dict[str, dict] = {}
    for r in rows:
        cid = str(r.get("campaign.id"))
        cname = r.get("campaign.name")
        cstatus = r.get("campaign.status")
        ftype = str(r.get("campaign_asset.field_type", ""))
        astatus = str(r.get("campaign_asset.status", ""))

        if cid not in campaigns:
            campaigns[cid] = {
                "campaign_id": cid,
                "campaign_name": cname,
                "campaign_status": cstatus,
                "enabled_assets": {
                    "SITELINK": 0,
                    "CALLOUT": 0,
                    "STRUCTURED_SNIPPET": 0,
                    "CALL": 0,
                },
                "paused_assets": {
                    "SITELINK": 0,
                    "CALLOUT": 0,
                    "STRUCTURED_SNIPPET": 0,
                    "CALL": 0,
                },
            }

        target_dict = (
            campaigns[cid]["enabled_assets"]
            if astatus == "ENABLED"
            else campaigns[cid]["paused_assets"]
        )
        if ftype in target_dict:
            target_dict[ftype] += 1

    audit_results = []
    for cid, data in campaigns.items():
        enabled = data["enabled_assets"]
        paused = data["paused_assets"]

        # Minimum best-practice thresholds: >=4 sitelinks, >=4 callouts, >=1 snippet
        sitelinks_ok = enabled["SITELINK"] >= 4
        callouts_ok = enabled["CALLOUT"] >= 4
        snippets_ok = enabled["STRUCTURED_SNIPPET"] >= 1

        score = 0
        if enabled["SITELINK"] >= 2:
            score += 25
        if enabled["SITELINK"] >= 4:
            score += 15
        if enabled["CALLOUT"] >= 2:
            score += 20
        if enabled["CALLOUT"] >= 4:
            score += 15
        if enabled["STRUCTURED_SNIPPET"] >= 1:
            score += 25

        recommendations = []
        if not sitelinks_ok:
            recommendations.append(
                f"Faltan sitelinks activos (actual: {enabled['SITELINK']}, pausados: {paused['SITELINK']}, meta: >=4). Activar o añadir sitelinks."
            )
        if not callouts_ok:
            recommendations.append(
                f"Faltan textos destacados (Callouts) activos (actual: {enabled['CALLOUT']}, meta: >=4)."
            )
        if not snippets_ok:
            recommendations.append(
                f"Falta al menos 1 fragmento estructurado activo (actual: {enabled['STRUCTURED_SNIPPET']})."
            )

        audit_results.append(
            {
                "campaign_id": cid,
                "campaign_name": data["campaign_name"],
                "campaign_status": data["campaign_status"],
                "asset_completeness_score_pct": score,
                "active_sitelinks": enabled["SITELINK"],
                "paused_sitelinks": paused["SITELINK"],
                "active_callouts": enabled["CALLOUT"],
                "active_snippets": enabled["STRUCTURED_SNIPPET"],
                "recommendations": recommendations
                or ["Cobertura de activos excelente para Ad Rank óptimo."],
            }
        )

    return {
        "customer_id": customer_id,
        "campaigns_audited": len(audit_results),
        "campaigns": audit_results,
        "media_buyer_verdict": (
            "Campañas con cobertura incompleta de activos pierden automáticamente entre 15% y 25% de Ad Rank, "
            "elevando el CPC medio en subasta."
        ),
    }


@intelligence_mcp.tool(annotations=READ)
def audit_creative_fatigue(
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict:
    """Audit RSA copy elements (headlines & descriptions) by Google performance label (LOW, GOOD, BEST).

    Identifies underperforming copy assets tagged as 'LOW' to replace them,
    and highlights 'BEST' headlines to inspire new winning variations.
    """
    fields = [
        "ad_group_ad_asset_view.ad_group_ad",
        "ad_group_ad_asset_view.field_type",
        "ad_group_ad_asset_view.performance_label",
        "ad_group_ad_asset_view.pinned_field",
        "asset.text_asset.text",
        "campaign.name",
        "ad_group.name",
    ]
    where_clause = "ad_group_ad_asset_view.performance_label IN ('LOW', 'GOOD', 'BEST', 'LEARNING')"

    rows = changes.query(
        customer_id,
        "ad_group_ad_asset_view",
        fields,
        where_clause,
        login_customer_id,
        limit=200,
    )

    low_assets = []
    best_assets = []
    good_assets = []

    for r in rows:
        label = str(r.get("ad_group_ad_asset_view.performance_label", ""))
        text = str(r.get("asset.text_asset.text", "")).strip()
        ftype = str(r.get("ad_group_ad_asset_view.field_type", ""))
        campaign = str(r.get("campaign.name", ""))
        ad_group = str(r.get("ad_group.name", ""))

        item = {
            "text": text,
            "type": ftype,
            "performance_label": label,
            "campaign": campaign,
            "ad_group": ad_group,
        }

        if label == "LOW":
            low_assets.append(item)
        elif label == "BEST":
            best_assets.append(item)
        elif label == "GOOD":
            good_assets.append(item)

    return {
        "customer_id": customer_id,
        "total_rated_elements": len(rows),
        "low_performing_elements_count": len(low_assets),
        "low_performing_elements": low_assets[:15],
        "best_performing_elements_count": len(best_assets),
        "best_performing_elements": best_assets[:15],
        "media_buyer_recommendation": (
            f"Se detectaron {len(low_assets)} elementos de copy calificados como 'LOW'. "
            "Reemplazarlos en prepare_ad utilizando variaciones basadas en los copys 'BEST' "
            "para elevar el Ad Strength y el Quality Score general."
            if low_assets
            else "No se detectaron titulares ni descripciones con calificación 'LOW'."
        ),
    }


@intelligence_mcp.tool(annotations=READ)
def audit_conversion_health(
    customer_id: str,
    days: int = 30,
    login_customer_id: str | None = None,
) -> dict:
    """Audit conversion tracking actions, primary/secondary goals, and orphan actions without recent data.

    Validates that Smart Bidding is optimizing against true business goals (not vanity metrics)
    and alerts on primary conversions that have ceased firing.
    """
    days = min(max(int(days), 1), 90)

    # 1. Conversion Action Definitions
    action_fields = [
        "conversion_action.id",
        "conversion_action.name",
        "conversion_action.type",
        "conversion_action.status",
        "conversion_action.primary_for_goal",
        "conversion_action.category",
    ]
    action_rows = changes.query(
        customer_id,
        "conversion_action",
        action_fields,
        "conversion_action.status != 'HIDDEN'",
        login_customer_id,
        limit=100,
    )

    # 2. Segmented campaign metrics
    metric_fields = [
        "segments.conversion_action",
        "metrics.conversions",
        "metrics.all_conversions",
    ]
    where_metrics = f"segments.date DURING LAST_{days}_DAYS"
    metric_rows = changes.query(
        customer_id,
        "campaign",
        metric_fields,
        where_metrics,
        login_customer_id,
        limit=500,
    )

    conversions_by_action: dict[str, float] = {}
    for mr in metric_rows:
        act_rn = str(mr.get("segments.conversion_action", ""))
        conv = float(mr.get("metrics.conversions", 0.0))
        conversions_by_action[act_rn] = (
            conversions_by_action.get(act_rn, 0.0) + conv
        )

    primary_actions = []
    secondary_actions = []
    orphan_primary_alerts = []

    for a in action_rows:
        aid = str(a.get("conversion_action.id"))
        aname = str(a.get("conversion_action.name"))
        atype = str(a.get("conversion_action.type"))
        astatus = str(a.get("conversion_action.status"))
        is_primary = bool(a.get("conversion_action.primary_for_goal", False))
        category = str(a.get("conversion_action.category"))
        rn = f"customers/{customer_id}/conversionActions/{aid}"

        recent_convs = conversions_by_action.get(rn, 0.0)

        info = {
            "id": aid,
            "name": aname,
            "type": atype,
            "status": astatus,
            "is_primary": is_primary,
            "category": category,
            "conversions_last_n_days": round(recent_convs, 1),
        }

        if is_primary:
            primary_actions.append(info)
            if astatus == "ENABLED" and recent_convs == 0.0:
                orphan_primary_alerts.append(
                    f"Acción primaria activa '{aname}' sin conversiones en los últimos {days} días (posible tracking roto)."
                )
        else:
            secondary_actions.append(info)

    return {
        "customer_id": customer_id,
        "evaluated_days": days,
        "total_actions": len(action_rows),
        "primary_actions_count": len(primary_actions),
        "primary_actions": primary_actions,
        "secondary_actions_count": len(secondary_actions),
        "secondary_actions": secondary_actions,
        "orphan_primary_alerts": orphan_primary_alerts,
        "media_buyer_recommendation": (
            "Verificar que solo las acciones de valor monetario directo (Leads cualificados, llamadas reales, compras) "
            "estén marcadas como Primarias. Acciones de navegación (visitas de página, clicks en botones secundarios) "
            "deben ser Secundarias para no confundir a los algoritmos de Smart Bidding."
        ),
    }


@intelligence_mcp.tool(annotations=READ)
def audit_copy_persuasion(
    customer_id: str,
    campaign_id: str | None = None,
    login_customer_id: str | None = None,
) -> dict:
    """Audit RSA copy elements under the Direct Response & ICP Qualification framework: identify weak clichés and evaluate ICP pain/hooks.

    Scans active responsive search ad headlines and descriptions, detecting prohibited generic
    clichés ('los mejores', 'económico', 'solución integral', 'calidad garantizada') and scoring
    whether copy prequalifies high-intent prospects or attracts low-intent clickers.
    """
    fields = [
        "ad_group_ad.ad.id",
        "ad_group_ad.ad.name",
        "ad_group_ad.status",
        "campaign.id",
        "campaign.name",
        "ad_group.id",
        "ad_group.name",
        "asset.text_asset.text",
        "ad_group_ad_asset_view.field_type",
    ]
    where_clause = (
        "ad_group_ad.status != 'REMOVED' AND campaign.status != 'REMOVED'"
    )
    if campaign_id:
        where_clause += f" AND campaign.id = {campaign_id}"

    rows = changes.query(
        customer_id,
        "ad_group_ad_asset_view",
        fields,
        where_clause,
        login_customer_id,
        limit=250,
    )

    cliche_patterns = [
        "los mejores",
        "el mejor",
        "la mejor",
        "economico",
        "barato",
        "solucion integral",
        "lideres en",
        "calidad garantizada",
        "atencion profesional",
        "100% garantizado",
        "precios bajos",
        "experiencia unica",
        "somos tu mejor opcion",
    ]

    detected_cliches = []
    analyzed_headlines = []
    analyzed_descriptions = []

    for r in rows:
        text = str(r.get("asset.text_asset.text", "")).strip()
        if not text:
            continue
        ftype = str(r.get("ad_group_ad_asset_view.field_type", ""))
        text_lower = text.lower()

        for c in cliche_patterns:
            if c in text_lower:
                detected_cliches.append(
                    {
                        "text": text,
                        "cliche_matched": c,
                        "type": ftype,
                        "campaign": r.get("campaign.name"),
                        "ad_group": r.get("ad_group.name"),
                    }
                )
                break

        if ftype == "HEADLINE":
            analyzed_headlines.append(text)
        elif ftype == "DESCRIPTION":
            analyzed_descriptions.append(text)

    # Unique samples
    unique_headlines = list(dict.fromkeys(analyzed_headlines))
    unique_descriptions = list(dict.fromkeys(analyzed_descriptions))

    # Persuasion verdict
    has_cliches = len(detected_cliches) > 0
    verdict = (
        f"Se detectaron {len(detected_cliches)} copys con lugares comunes o clichés genéricos prohibidos por los principios de Respuesta Directa. "
        "El anuncio es el filtro: los titulares genéricos atraen curiosos sin intención de pago. Reemplazarlos por copys anclados al dolor del ICP y con mecanismo único."
        if has_cliches
        else "Excelente higiene de copy: no se detectaron clichés genéricos prohibidos en la muestra analizada."
    )

    return {
        "customer_id": customer_id,
        "total_elements_audited": len(rows),
        "unique_headlines_count": len(unique_headlines),
        "unique_descriptions_count": len(unique_descriptions),
        "cliches_detected_count": len(detected_cliches),
        "cliches_detected": detected_cliches[:15],
        "strategic_verdict": verdict,
        "framework_rules": [
            "1. El anuncio es el primer filtro: repele a los no cualificados antes del clic.",
            "2. Prohibido usar clichés vacíos ('los mejores', 'solución integral').",
            "3. Cada titular debe anclar un dolor operativo específico o enunciar el mecanismo único de solución.",
            "4. Incluir siempre un CTA directo hacia desanonimización (Llamada o WhatsApp).",
        ],
    }


@intelligence_mcp.tool(annotations=READ)
def classify_intent_funnel(
    customer_id: str,
    days: int = 30,
    login_customer_id: str | None = None,
) -> dict:
    """Classify search query spend into Transactional (High Intent) vs. Informational (Low Intent / Waste).

    Separates commercial hiring terms ('urgente', 'servicio', 'precio', 'consulta', 'contratar')
    from informational research queries ('como', 'que es', 'gratis', 'definicion', 'por que'),
    identifying budget leaks on top-of-funnel curiosities.
    """
    days = min(max(int(days), 1), 90)
    where_clause = f"segments.date DURING LAST_{days}_DAYS"

    fields = [
        "search_term_view.search_term",
        "metrics.clicks",
        "metrics.cost_micros",
        "metrics.conversions",
    ]

    rows = changes.query(
        customer_id,
        "search_term_view",
        fields,
        where_clause,
        login_customer_id,
        limit=500,
    )

    informational_tokens = {
        "como",
        "cmo",
        "que",
        "qu",
        "definicion",
        "porque",
        "por que",
        "por qu",
        "gratis",
        "free",
        "diy",
        "tutorial",
        "ejemplo",
        "pdf",
        "pasos",
    }
    transactional_tokens = {
        "precio",
        "costo",
        "servicio",
        "urgente",
        "consulta",
        "contratar",
        "agencia",
        "especialista",
        "experto",
        "cita",
        "telefono",
        "whatsapp",
        "online",
        "ya",
    }

    trans_spend_micros = 0
    info_spend_micros = 0
    mixed_spend_micros = 0

    trans_conv = 0.0
    info_conv = 0.0

    sample_info_queries = []
    sample_trans_queries = []

    for r in rows:
        term = str(r.get("search_term_view.search_term", "")).strip().lower()
        cost = int(r.get("metrics.cost_micros", 0))
        conv = float(r.get("metrics.conversions", 0.0))
        words = set(term.split())

        is_info = bool(words & informational_tokens)
        is_trans = bool(words & transactional_tokens)

        if is_info and not is_trans:
            info_spend_micros += cost
            info_conv += conv
            if cost > 0:
                sample_info_queries.append(
                    {
                        "term": term,
                        "cost": str(Decimal(cost) / 1_000_000),
                        "conversions": conv,
                    }
                )
        elif is_trans:
            trans_spend_micros += cost
            trans_conv += conv
            if cost > 0:
                sample_trans_queries.append(
                    {
                        "term": term,
                        "cost": str(Decimal(cost) / 1_000_000),
                        "conversions": conv,
                    }
                )
        else:
            mixed_spend_micros += cost

    total_cost_micros = (
        trans_spend_micros + info_spend_micros + mixed_spend_micros
    )
    info_pct = (
        round((info_spend_micros / total_cost_micros) * 100, 2)
        if total_cost_micros > 0
        else 0.0
    )
    trans_pct = (
        round((trans_spend_micros / total_cost_micros) * 100, 2)
        if total_cost_micros > 0
        else 0.0
    )

    sample_info_queries.sort(key=lambda x: Decimal(x["cost"]), reverse=True)
    sample_trans_queries.sort(key=lambda x: Decimal(x["cost"]), reverse=True)

    diagnosis = "INTENT_OPTIMAL"
    if info_pct >= 25.0:
        diagnosis = "INFORMATIONAL_LEAK"
        verdict = f"Alerta Estratégica High-Ticket: El {info_pct}% del gasto se está fugando en búsquedas informativas ('cómo', 'qué es', 'gratis') que rara vez convierten en llamadas de alto valor. Se sugiere excluir estos términos con prepare_mined_negatives."
    else:
        verdict = f"Tráfico enfocado principalmente en términos comerciales y transaccionales ({trans_pct}% transaccional directo)."

    return {
        "customer_id": customer_id,
        "analyzed_days": days,
        "total_analyzed_spend": str(Decimal(total_cost_micros) / 1_000_000),
        "transactional_spend": str(Decimal(trans_spend_micros) / 1_000_000),
        "transactional_spend_pct": trans_pct,
        "transactional_conversions": trans_conv,
        "informational_spend": str(Decimal(info_spend_micros) / 1_000_000),
        "informational_spend_pct": info_pct,
        "informational_conversions": info_conv,
        "intent_diagnosis": diagnosis,
        "strategic_verdict": verdict,
        "top_informational_leaks": sample_info_queries[:10],
        "top_transactional_winners": sample_trans_queries[:10],
    }


@intelligence_mcp.tool(annotations=READ)
def prepare_high_ticket_negative_shield(
    customer_id: str,
    destination_type: Literal["SHARED_LIST", "CAMPAIGN"],
    destination_id: str,
    login_customer_id: str | None = None,
) -> dict:
    """Inject the pre-curated High-Ticket Universal Negative Shield to block low-ticket curiosities.

    Injects a master list of 45+ high-friction commercial negative keywords (gratis, barato,
    pdf, curso, como hacer, diy, empleo, sueldo, reclamos, plantilla) in 1 step via validate_only.
    Requires explicit human approval before live application.
    """
    master_shield_terms = [
        "gratis",
        "free",
        "barato",
        "barata",
        "baratos",
        "economico",
        "economica",
        "low cost",
        "como hacer",
        "como se hace",
        "tutorial",
        "curso",
        "diplomado",
        "universidad",
        "estudiar",
        "pdf",
        "descargar",
        "download",
        "plantilla",
        "template",
        "formato",
        "modelo de",
        "empleo",
        "vacantes",
        "trabajo",
        "sueldo",
        "salario",
        "pasantia",
        "requisitos para trabajar",
        "quejas",
        "reclamos",
        "denuncias",
        "demanda",
        "estafa",
        "opiniones negativas",
        "fraude",
        "significado de",
        "definicion de",
        "que significa",
        "wikipedia",
        "youtube",
        "login",
        "portal",
    ]

    keywords = [
        search.Keyword(text=term, match_type="PHRASE")
        for term in master_shield_terms
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
        raise ValueError("destination_type must be 'SHARED_LIST' or 'CAMPAIGN'")


@intelligence_mcp.tool(annotations=READ)
def audit_quality_score_triad(
    customer_id: str,
    days: int = 30,
    min_impressions: int = 5,
    login_customer_id: str | None = None,
) -> dict:
    """Audit the Google Ads Quality Score Triad (Expected CTR, Ad Relevance, Landing Page Experience).

    Diagnoses why campaigns suffer from Ad Rank penalties (Rank Lost IS) and reveals keywords
    where post-click landing page friction or weak message match is artificially inflating CPCs.
    """
    days = min(max(int(days), 1), 90)
    fields = [
        "ad_group_criterion.keyword.text",
        "ad_group_criterion.keyword.match_type",
        "ad_group_criterion.quality_info.quality_score",
        "ad_group_criterion.quality_info.creative_quality_score",
        "ad_group_criterion.quality_info.post_click_quality_score",
        "ad_group_criterion.quality_info.search_predicted_ctr",
        "campaign.name",
        "ad_group.name",
        "metrics.cost_micros",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.conversions",
    ]
    where_clause = (
        f"ad_group_criterion.status = 'ENABLED' "
        f"AND ad_group_criterion.negative = FALSE "
        f"AND metrics.impressions >= {min_impressions} "
        f"AND segments.date DURING LAST_{days}_DAYS"
    )

    rows = changes.query(
        customer_id,
        "keyword_view",
        fields,
        where_clause,
        login_customer_id,
        limit=150,
    )

    penalized_keywords = []
    landing_page_issues = []
    creative_relevance_issues = []

    for r in rows:
        kw_text = str(r.get("ad_group_criterion.keyword.text", ""))
        qs = int(r.get("ad_group_criterion.quality_info.quality_score", 0))
        creative_qs = str(
            r.get(
                "ad_group_criterion.quality_info.creative_quality_score",
                "UNSPECIFIED",
            )
        )
        post_click_qs = str(
            r.get(
                "ad_group_criterion.quality_info.post_click_quality_score",
                "UNSPECIFIED",
            )
        )
        exp_ctr = str(
            r.get(
                "ad_group_criterion.quality_info.search_predicted_ctr",
                "UNSPECIFIED",
            )
        )
        cost = int(r.get("metrics.cost_micros", 0))
        impr = int(r.get("metrics.impressions", 0))
        clicks = int(r.get("metrics.clicks", 0))

        item = {
            "keyword": kw_text,
            "quality_score": qs,
            "ad_relevance": creative_qs,
            "landing_page_experience": post_click_qs,
            "expected_ctr": exp_ctr,
            "cost": str(Decimal(cost) / 1_000_000),
            "impressions": impr,
            "clicks": clicks,
            "campaign": r.get("campaign.name"),
            "ad_group": r.get("ad_group.name"),
        }

        if post_click_qs == "BELOW_AVERAGE":
            landing_page_issues.append(item)
        if creative_qs == "BELOW_AVERAGE":
            creative_relevance_issues.append(item)
        if qs > 0 and qs < 6:
            penalized_keywords.append(item)

    penalized_keywords.sort(key=lambda x: Decimal(x["cost"]), reverse=True)

    recommendations = []
    if landing_page_issues:
        recommendations.append(
            f"Se detectaron {len(landing_page_issues)} keywords con experiencia de Landing Page 'BELOW_AVERAGE'. "
            "Alinear el titular de la landing page con la promesa del anuncio (Message Match) para reducir el CPC de castigo."
        )
    if creative_relevance_issues:
        recommendations.append(
            f"Se detectaron {len(creative_relevance_issues)} keywords con relevancia de anuncio 'BELOW_AVERAGE'. "
            "Incluir estas palabras clave exactas en los titulares y descripciones del RSA correspondiente."
        )

    return {
        "customer_id": customer_id,
        "analyzed_days": days,
        "total_active_keywords_analyzed": len(rows),
        "penalized_keywords_count": len(penalized_keywords),
        "penalized_keywords": penalized_keywords[:15],
        "landing_page_friction_count": len(landing_page_issues),
        "creative_relevance_friction_count": len(creative_relevance_issues),
        "recommendations": recommendations
        or [
            "Calidad de subasta y experiencia post-clic en niveles saludables."
        ],
    }


@intelligence_mcp.tool(annotations=READ)
def audit_lead_dropoff(
    customer_id: str,
    days: int = 30,
    login_customer_id: str | None = None,
) -> dict:
    """Audit funnel drop-off from Ad Clicks -> Landing Page Visits -> Qualified Contacts (WhatsApp/Calls).

    Diagnoses where prospects are dropping out in the desanonimization journey
    to isolate whether conversion bottlenecks are caused by traffic or by landing page friction.
    """
    days = min(max(int(days), 1), 90)
    where_clause = f"segments.date DURING LAST_{days}_DAYS"

    # Campaign metrics: Clicks, Cost, Impressions
    camp_fields = [
        "campaign.id",
        "campaign.name",
        "metrics.impressions",
        "metrics.clicks",
        "metrics.cost_micros",
        "metrics.conversions",
    ]
    camp_rows = changes.query(
        customer_id,
        "campaign",
        camp_fields,
        f"campaign.status != 'REMOVED' AND {where_clause}",
        login_customer_id,
        limit=50,
    )

    # Conversion action segmented metrics
    conv_fields = [
        "segments.conversion_action_name",
        "segments.conversion_action_category",
        "metrics.conversions",
        "metrics.all_conversions",
    ]
    conv_rows = changes.query(
        customer_id,
        "campaign",
        conv_fields,
        f"campaign.status != 'REMOVED' AND {where_clause}",
        login_customer_id,
        limit=200,
    )

    total_clicks = sum(int(r.get("metrics.clicks", 0)) for r in camp_rows)
    total_cost_micros = sum(
        int(r.get("metrics.cost_micros", 0)) for r in camp_rows
    )
    total_impr = sum(int(r.get("metrics.impressions", 0)) for r in camp_rows)

    whatsapp_leads = 0.0
    phone_leads = 0.0
    page_views = 0.0

    for cr in conv_rows:
        aname = str(cr.get("segments.conversion_action_name", "")).lower()
        conv = float(cr.get("metrics.conversions", 0.0))
        all_conv = float(cr.get("metrics.all_conversions", 0.0))

        if "whatsapp" in aname:
            whatsapp_leads += conv if conv > 0 else all_conv
        elif "tel" in aname or "llama" in aname:
            phone_leads += conv if conv > 0 else all_conv
        elif "landing" in aname or "visit" in aname or "page" in aname:
            page_views += all_conv

    total_contacts = whatsapp_leads + phone_leads
    ctr_pct = (
        round((total_clicks / total_impr) * 100, 2) if total_impr > 0 else 0.0
    )
    click_to_contact_rate = (
        round((total_contacts / total_clicks) * 100, 2)
        if total_clicks > 0
        else 0.0
    )
    cpc = (
        Decimal(total_cost_micros) / Decimal(str(total_clicks)) / 1_000_000
        if total_clicks > 0
        else Decimal(0)
    )
    cpa_contact = (
        Decimal(total_cost_micros) / Decimal(str(total_contacts)) / 1_000_000
        if total_contacts > 0
        else Decimal(0)
    )

    verdict = "Flujo de conversión equilibrado."
    if total_clicks >= 50 and click_to_contact_rate < 3.0:
        verdict = (
            f"Fricción severa en Landing Page: Tasa de conversión clic-a-contacto de solo {click_to_contact_rate}%. "
            "El tráfico llega pero no inicia contacto. Simplificar el botón de WhatsApp y colocar el CTA principal visible sin hacer scroll (Above the Fold)."
        )
    elif click_to_contact_rate >= 8.0:
        verdict = f"Excelente tasa de desanonimización ({click_to_contact_rate}% de clics convertidos en contactos directos)."

    return {
        "customer_id": customer_id,
        "analyzed_days": days,
        "impressions": total_impr,
        "ad_clicks": total_clicks,
        "ad_ctr_pct": ctr_pct,
        "cpc_average": str(round(cpc, 2)),
        "whatsapp_contacts": whatsapp_leads,
        "phone_call_contacts": phone_leads,
        "total_qualified_contacts": total_contacts,
        "click_to_contact_conversion_rate_pct": click_to_contact_rate,
        "cost_per_qualified_contact": str(round(cpa_contact, 2)),
        "funnel_diagnosis": verdict,
    }


@intelligence_mcp.tool(annotations=READ)
def calculate_high_ticket_unit_economics(
    customer_id: str,
    average_ticket_value: str,
    target_profit_margin_pct: float = 60.0,
    estimated_call_close_rate_pct: float = 20.0,
    days: int = 30,
    login_customer_id: str | None = None,
) -> dict:
    """Calculate unit economics: determine Max Allowable CPA per Lead and target Sales Calls based on ticket size.

    Connects ad spend to the bottom line (P&L): calculates how much can be spent per qualified contact
    without breaking profitability margins, and determines current Real vs. Target CAC.
    """
    ticket = Decimal(str(average_ticket_value))
    margin_pct = Decimal(str(target_profit_margin_pct)) / Decimal("100")
    close_rate = Decimal(str(estimated_call_close_rate_pct)) / Decimal("100")

    if close_rate <= 0:
        raise ValueError(
            "estimated_call_close_rate_pct must be greater than 0."
        )

    # Max CAC allowable
    max_allowable_cac = ticket * (Decimal("1") - margin_pct)
    # Max Allowable CPA per Lead/Conversation = Max CAC * Close Rate
    max_allowable_cpa_lead = max_allowable_cac * close_rate

    # Pull real account spend & contacts
    dropoff = audit_lead_dropoff(
        customer_id, days=days, login=login_customer_id
    )
    contacts = Decimal(str(dropoff["total_qualified_contacts"]))
    real_cpa_lead = (
        Decimal(str(dropoff["cost_per_qualified_contact"]))
        if contacts > 0
        else Decimal(0)
    )

    # Unit economics viability
    is_profitable = (
        real_cpa_lead <= max_allowable_cpa_lead if real_cpa_lead > 0 else True
    )

    if real_cpa_lead == 0:
        status = "NO_DATA"
        guidance = "No se registraron contactos calificados suficientes en el periodo para evaluar el CPA real."
    elif is_profitable:
        status = "HIGHLY_PROFITABLE"
        guidance = (
            f"Economía unitaria sólida: Tu CPA real por contacto ({real_cpa_lead}) está por debajo "
            f"del CPA máximo permitido ({round(max_allowable_cpa_lead, 2)}). La cuenta tiene margen para escalar presupuesto."
        )
    else:
        status = "UNIT_ECONOMICS_BROKEN"
        guidance = (
            f"Alerta de P&L: Tu CPA real por contacto ({real_cpa_lead}) supera el límite rentable "
            f"({round(max_allowable_cpa_lead, 2)}). Para recuperar rentabilidad debes: 1) Elevar la tasa de cierre en llamadas de venta, "
            "2) Subir el ticket promedio de la oferta, o 3) Eliminar términos con fuga usando prepare_mined_negatives."
        )

    return {
        "customer_id": customer_id,
        "average_ticket": str(ticket),
        "target_profit_margin_pct": target_profit_margin_pct,
        "call_close_rate_pct": estimated_call_close_rate_pct,
        "max_allowable_cac_customer": str(round(max_allowable_cac, 2)),
        "max_allowable_cpa_per_contact": str(round(max_allowable_cpa_lead, 2)),
        "current_real_cpa_per_contact": str(real_cpa_lead),
        "unit_economics_status": status,
        "strategic_guidance": guidance,
    }


@intelligence_mcp.tool(annotations=READ)
def audit_shared_negative_governance(
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict:
    """Audit shared negative keyword lists (shared sets) and campaign coverage.

    Detects orphaned lists (reference_count == 0) that harbor thousands of unused negative
    keywords, and flags active campaigns that lack shared negative protection.
    """
    cid = changes.customer(customer_id)
    login = changes.customer(login_customer_id) if login_customer_id else None

    # 1. Query shared sets of type NEGATIVE_KEYWORDS
    set_fields = [
        "shared_set.id",
        "shared_set.name",
        "shared_set.type",
        "shared_set.member_count",
        "shared_set.reference_count",
    ]
    shared_rows = changes.query(
        cid,
        "shared_set",
        set_fields,
        where="shared_set.type = " + repr("NEGATIVE_KEYWORDS"),
        login=login,
    )

    orphaned_lists = []
    active_shared_lists = []
    total_dormant_terms = 0

    for r in shared_rows:
        set_id = str(r.get("shared_set.id", ""))
        name = str(r.get("shared_set.name", ""))
        members = int(r.get("shared_set.member_count", 0))
        refs = int(r.get("shared_set.reference_count", 0))

        item = {
            "list_id": set_id,
            "name": name,
            "member_count": members,
            "reference_count": refs,
        }

        if refs == 0:
            item["status"] = "ORPHANED_INACTIVE"
            orphaned_lists.append(item)
            total_dormant_terms += members
        else:
            item["status"] = "ATTACHED_ACTIVE"
            active_shared_lists.append(item)

    # 2. Query active campaigns to check their attached negative lists
    camp_fields = [
        "campaign.id",
        "campaign.name",
        "campaign.status",
    ]
    camp_rows = changes.query(
        cid,
        "campaign",
        camp_fields,
        where="campaign.status = " + repr("ENABLED"),
        login=login,
    )

    # 3. Query campaign_shared_set attachments
    attach_fields = [
        "campaign_shared_set.campaign",
        "campaign_shared_set.shared_set",
        "campaign_shared_set.status",
    ]
    try:
        attach_rows = changes.query(
            cid,
            "campaign_shared_set",
            attach_fields,
            where="campaign_shared_set.status = " + repr("ENABLED"),
            login=login,
        )
    except Exception:
        attach_rows = []

    # Map campaigns to attached set IDs
    camp_attachments: dict[str, list[str]] = {}
    for att in attach_rows:
        camp_rn = att.get("campaign_shared_set.campaign", "")
        set_rn = att.get("campaign_shared_set.shared_set", "")
        camp_id = camp_rn.split("/")[-1] if "/" in camp_rn else camp_rn
        set_id = set_rn.split("/")[-1] if "/" in set_rn else set_rn
        camp_attachments.setdefault(camp_id, []).append(set_id)

    unprotected_campaigns = []
    for c in camp_rows:
        c_id = str(c.get("campaign.id", ""))
        c_name = str(c.get("campaign.name", ""))
        attached = camp_attachments.get(c_id, [])
        if not attached:
            unprotected_campaigns.append(
                {
                    "campaign_id": c_id,
                    "campaign_name": c_name,
                    "attached_negative_lists_count": 0,
                    "vulnerability": "HIGH_UNPROTECTED_AGAINST_SHARED_NEGATIVES",
                }
            )

    recommendations = []
    if orphaned_lists:
        recommendations.append(
            f"Alerta de Falsa Proteccion: Hay {len(orphaned_lists)} listas de negativas con "
            f"{total_dormant_terms:,} terminos inactivos (reference_count: 0). "
            "Usa prepare_negative_list(action='attach') para vincularlas a las campanas activas."
        )
    if unprotected_campaigns:
        recommendations.append(
            f"Vulnerabilidad de Campana: {len(unprotected_campaigns)} campanas activas no tienen "
            "ninguna lista de negativas compartida vinculada."
        )
    if not recommendations:
        recommendations.append(
            "Gobernanza de listas compartidas optima: todas las listas tienen campanas vinculadas."
        )

    return {
        "customer_id": customer_id,
        "total_negative_lists_found": len(shared_rows),
        "orphaned_negative_lists_count": len(orphaned_lists),
        "total_dormant_negative_terms": total_dormant_terms,
        "orphaned_negative_lists": orphaned_lists,
        "active_shared_lists": active_shared_lists,
        "unprotected_campaigns_count": len(unprotected_campaigns),
        "unprotected_campaigns": unprotected_campaigns,
        "recommendations": recommendations,
    }


@intelligence_mcp.tool(annotations=READ)
def inspect_negative_list_terms(
    customer_id: str,
    list_id: str,
    search_query: str | None = None,
    limit: int = 50,
    login_customer_id: str | None = None,
) -> dict:
    """Inspect and filter exact negative keyword terms inside a shared negative list.

    Allows fast searching inside large negative lists (e.g. 2,000+ terms) to verify if
    specific terms or match types are already blocked without dumping huge payloads.
    """
    cid = changes.customer(customer_id)
    login = changes.customer(login_customer_id) if login_customer_id else None
    clean_list_id = str(list_id).replace("customers/", "").split("/")[-1]
    shared_set_rn = f"customers/{cid}/sharedSets/{clean_list_id}"

    fields = [
        "shared_criterion.shared_set",
        "shared_criterion.criterion_id",
        "shared_criterion.keyword.text",
        "shared_criterion.keyword.match_type",
    ]
    where_clause = f"shared_criterion.shared_set = '{shared_set_rn}'"

    rows = changes.query(
        cid,
        "shared_criterion",
        fields,
        where=where_clause,
        login=login,
    )

    total_terms_in_list = len(rows)
    query_clean = (search_query or "").strip().lower()

    filtered_terms = []
    for r in rows:
        kw_text = str(r.get("shared_criterion.keyword.text", ""))
        match_type = str(r.get("shared_criterion.keyword.match_type", "BROAD"))
        crit_id = str(r.get("shared_criterion.criterion_id", ""))

        if not query_clean or query_clean in kw_text.lower():
            filtered_terms.append(
                {
                    "criterion_id": crit_id,
                    "keyword_text": kw_text,
                    "match_type": match_type,
                }
            )

    capped_limit = min(max(int(limit), 1), 200)

    return {
        "customer_id": customer_id,
        "list_id": clean_list_id,
        "total_terms_in_list": total_terms_in_list,
        "search_filter_applied": search_query if search_query else None,
        "matching_terms_count": len(filtered_terms),
        "terms_sample": filtered_terms[:capped_limit],
    }


@intelligence_mcp.tool(annotations=READ)
def audit_bidding_strategy_readiness(
    customer_id: str,
    days: int = 30,
    login_customer_id: str | None = None,
) -> dict:
    """Audit algorithmic bidding maturity and readiness for Smart Bidding (Target CPA / Max Conversions).

    Evaluates monthly conversion volume per campaign against statistical thresholds
    (30+ conversions for Smart Bidding, <15 for Maximize Clicks with CPC cap) to prevent
    campaign starvation or wild algorithmic bidding swings.
    """
    cid = changes.customer(customer_id)
    login = changes.customer(login_customer_id) if login_customer_id else None
    days = min(max(int(days), 7), 90)

    fields = [
        "campaign.id",
        "campaign.name",
        "campaign.status",
        "campaign.bidding_strategy_type",
        "campaign.target_cpa.target_cpa_micros",
        "campaign.maximize_conversions.target_cpa_micros",
        "metrics.conversions",
        "metrics.cost_micros",
        "metrics.cost_per_conversion",
    ]
    rows = changes.query(
        cid,
        "campaign",
        fields,
        where=f"segments.date DURING LAST_{days}_DAYS AND campaign.status = 'ENABLED'",
        login=login,
    )

    campaign_evaluations = []
    premature_smart_bidding_count = 0
    ready_for_scaling_count = 0

    for r in rows:
        camp_id = str(r.get("campaign.id", ""))
        name = str(r.get("campaign.name", ""))
        strategy = str(r.get("campaign.bidding_strategy_type", "UNKNOWN"))
        convs = float(r.get("metrics.conversions", 0.0))
        cost = Decimal(str(r.get("metrics.cost_micros", 0))) / Decimal(
            1_000_000
        )
        cpa = (
            Decimal(str(r.get("metrics.cost_per_conversion", 0)))
            / Decimal(1_000_000)
            if convs > 0
            else Decimal(0)
        )

        is_smart_bidding = strategy in (
            "MAXIMIZE_CONVERSIONS",
            "MAXIMIZE_CONVERSION_VALUE",
            "TARGET_CPA",
            "TARGET_ROAS",
        )

        if convs < 15:
            maturity = "LEARNING_TOO_EARLY"
            if is_smart_bidding:
                readiness_status = "PREMATURE_SMART_BIDDING"
                premature_smart_bidding_count += 1
                guidance = (
                    f"Riesgo de Estrangulamiento: Campana en {strategy} con solo {convs:.0f} conversiones en {days} dias. "
                    "El algoritmo carece de muestra estadistica suficiente. Recomendado: Migrar a MAXIMIZE_CLICKS "
                    "(TARGET_SPEND) con CPC Limite para acumular datos limpios."
                )
            else:
                readiness_status = "APPROPRIATELY_CAPPED"
                guidance = (
                    f"Pase de aprendizaje adecuado: Operando en {strategy} con {convs:.0f} conversiones. "
                    "Mantener hasta alcanzar al menos 15-30 conversiones antes de probar Smart Bidding."
                )
        elif 15 <= convs < 30:
            maturity = "TRANSITION_ZONE"
            readiness_status = "READY_FOR_MAX_CONVERSIONS_TEST"
            guidance = (
                f"Zona de transicion: {convs:.0f} conversiones acumuladas. Califica para probar MAXIMIZE_CONVERSIONS "
                "sin target estricto de tCPA para medir la elasticidad del volumen."
            )
        else:
            maturity = "SMART_BIDDING_MATURE"
            ready_for_scaling_count += 1
            readiness_status = "FULLY_READY_FOR_TARGET_CPA"
            guidance = (
                f"Madurez Algoritmica Optima: {convs:.0f} conversiones en {days} dias. Cumple el umbral estadistico "
                f"(>= 30 conversiones). Puedes activar TARGET_CPA fijandolo en base al CPA historico ({round(cpa, 2)})."
            )

        campaign_evaluations.append(
            {
                "campaign_id": camp_id,
                "campaign_name": name,
                "bidding_strategy": strategy,
                "conversions_in_period": round(convs, 1),
                "total_spend": str(round(cost, 2)),
                "cost_per_conversion": str(round(cpa, 2)),
                "algorithmic_maturity": maturity,
                "readiness_status": readiness_status,
                "guidance": guidance,
            }
        )

    return {
        "customer_id": customer_id,
        "analyzed_days": days,
        "active_campaigns_analyzed": len(campaign_evaluations),
        "premature_smart_bidding_alerts": premature_smart_bidding_count,
        "ready_for_target_cpa_campaigns": ready_for_scaling_count,
        "campaign_evaluations": campaign_evaluations,
    }


@intelligence_mcp.tool(annotations=READ)
def audit_lead_to_sale_discrepancy(
    customer_id: str,
    real_qualified_calls: int,
    real_closed_sales: int = 0,
    days: int = 30,
    login_customer_id: str | None = None,
) -> dict:
    """Audit discrepancy between Google Ads reported conversions and real CRM/sales calls.

    Detects 'Algorithmic Poisoning' where campaigns optimize for low-quality WhatsApp/form clicks
    that fail to materialize into scheduled calls or paying customers.
    """
    cid = changes.customer(customer_id)
    login = changes.customer(login_customer_id) if login_customer_id else None
    days = min(max(int(days), 7), 90)

    # 1. Total spend and conversions from campaign level
    camp_fields = [
        "metrics.conversions",
        "metrics.cost_micros",
    ]
    rows = changes.query(
        cid,
        "campaign",
        camp_fields,
        where=f"segments.date DURING LAST_{days}_DAYS AND campaign.status = 'ENABLED'",
        login=login,
    )

    total_google_conversions = sum(
        float(r.get("metrics.conversions", 0.0)) for r in rows
    )
    total_spend = sum(
        Decimal(str(r.get("metrics.cost_micros", 0))) / Decimal(1_000_000)
        for r in rows
    )

    qualified_calls = max(int(real_qualified_calls), 0)
    closed_sales = max(int(real_closed_sales), 0)

    # Lead qualification rate: real calls / google reported conversions
    qualification_rate_pct = (
        round((qualified_calls / total_google_conversions) * 100, 2)
        if total_google_conversions > 0
        else 0.0
    )

    # Real Cost Per Qualified Call
    cpa_qualified_call = (
        round(total_spend / Decimal(qualified_calls), 2)
        if qualified_calls > 0
        else Decimal(0)
    )

    # Real CAC
    real_cac = (
        round(total_spend / Decimal(closed_sales), 2)
        if closed_sales > 0
        else Decimal(0)
    )

    if total_google_conversions == 0:
        verdict = "NO_CONVERSIONS_RECORDED"
        guidance = "No se registraron conversiones en Google Ads durante el periodo para auditar discrepancia."
    elif qualification_rate_pct < 20.0:
        verdict = "ALGORITHMIC_POISONING"
        guidance = (
            f"Alerta Critica de Calificacion ({qualification_rate_pct}%): Solo {qualified_calls} llamadas calificadas de "
            f"{total_google_conversions:.0f} conversiones reportadas por Google. El algoritmo esta optimizando para clicks "
            "curiosos sin intencion ni capacidad de pago. Accion obligatoria: Endurecer el filtro en el copy del anuncio, "
            "anadir preguntas filtro en el formulario/WhatsApp y no enviar eventos de conversion blandos a Google Ads."
        )
    elif 20.0 <= qualification_rate_pct < 50.0:
        verdict = "MODERATE_FRICTION"
        guidance = (
            f"Friccion de Calificacion Media ({qualification_rate_pct}%): De cada 10 conversiones reportadas, menos de la mitad "
            "llegan a llamada calificada. Revisar el Message Match en la landing y la rapidez de respuesta del setter."
        )
    else:
        verdict = "HEALTHY_ACQUISITION_LOOP"
        guidance = (
            f"Bucle de Adquisicion Saludable ({qualification_rate_pct}%): Alta coherencia entre las conversiones de Google "
            "y las llamadas reales en el CRM. Tu CPA real por llamada calificada es de "
            f"${cpa_qualified_call:,.2f}."
        )

    return {
        "customer_id": customer_id,
        "analyzed_days": days,
        "total_spend": str(round(total_spend, 2)),
        "google_reported_conversions": round(total_google_conversions, 1),
        "real_crm_qualified_calls": qualified_calls,
        "real_closed_sales": closed_sales,
        "lead_qualification_rate_pct": qualification_rate_pct,
        "cpa_per_qualified_call": str(cpa_qualified_call),
        "real_cac_per_sale": str(real_cac),
        "discrepancy_verdict": verdict,
        "strategic_guidance": guidance,
    }
