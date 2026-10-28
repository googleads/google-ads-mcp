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

"""Read-only media buying intelligence tools: search terms, auction insights and health audits."""

from collections import Counter
from decimal import Decimal
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ads_mcp.extensions import changes

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
            "campaign_name": r.get("campaign.name"),
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
            "la herramienta prepare_negative_list para cortar la fuga de presupuesto inmediatamente."
            if bleeders
            else "No se detectaron fugas significativas con gasto en el periodo analizado."
        ),
    }


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

        # Strategic diagnosis
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
def check_account_health(
    customer_id: str,
    login_customer_id: str | None = None,
) -> dict:
    """Run an instant health check on campaigns, budgets, and RSA ad strengths.

    Flags campaigns limited by budget, poor ad strength RSAs, and paused high-performers.
    """
    # 1. Check budgets & status
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

    # 2. Check RSA Ad Strengths
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
