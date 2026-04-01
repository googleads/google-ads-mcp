"""Campaign management tools for the Google Ads MCP server."""

from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils
from google.ads.googleads.v23.common.types.bidding import TargetSpend
from google.protobuf import field_mask_pb2


# ─────────────────────────────────────────────
# BUDGETS
# ─────────────────────────────────────────────

@mcp.tool()
def create_campaign_budget(
    customer_id: str,
    name: str,
    amount_rupees: float,
) -> dict:
    """Create a shared campaign budget.

    Args:
        customer_id: Google Ads customer ID (digits only, e.g. '4170793536')
        name: Unique name for the budget
        amount_rupees: Daily budget in Indian Rupees (e.g. 500)
    """
    client = utils.get_googleads_client()
    svc = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    b = op.create
    b.name = name
    b.delivery_method = client.enums.BudgetDeliveryMethodEnum.STANDARD
    b.amount_micros = int(amount_rupees * 1_000_000)
    resp = svc.mutate_campaign_budgets(customer_id=customer_id, operations=[op])
    return {"budget_resource": resp.results[0].resource_name}


@mcp.tool()
def update_campaign_budget(
    customer_id: str,
    budget_resource: str,
    amount_rupees: float,
) -> dict:
    """Update the daily amount of an existing campaign budget.

    Args:
        customer_id: Google Ads customer ID (digits only)
        budget_resource: Budget resource name (e.g. 'customers/XXX/campaignBudgets/YYY')
        amount_rupees: New daily budget in Indian Rupees
    """
    client = utils.get_googleads_client()
    svc = client.get_service("CampaignBudgetService")
    op = client.get_type("CampaignBudgetOperation")
    b = op.update
    b.resource_name = budget_resource
    b.amount_micros = int(amount_rupees * 1_000_000)
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["amount_micros"]))
    resp = svc.mutate_campaign_budgets(customer_id=customer_id, operations=[op])
    return {"updated_budget": resp.results[0].resource_name, "amount_rupees": amount_rupees}


# ─────────────────────────────────────────────
# CAMPAIGNS
# ─────────────────────────────────────────────

@mcp.tool()
def create_search_campaign(
    customer_id: str,
    name: str,
    budget_resource: str,
    status: str = "PAUSED",
) -> dict:
    """Create a Search campaign.

    Args:
        customer_id: Google Ads customer ID (digits only)
        name: Campaign name
        budget_resource: Budget resource name (from create_campaign_budget)
        status: PAUSED (default, safe for review) or ENABLED
    """
    client = utils.get_googleads_client()
    svc = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    c = op.create
    c.name = name
    c.advertising_channel_type = client.enums.AdvertisingChannelTypeEnum.SEARCH
    c.status = client.enums.CampaignStatusEnum[status]
    c.campaign_budget = budget_resource
    c.network_settings.target_google_search = True
    c.network_settings.target_search_network = True
    c.network_settings.target_content_network = False
    c.target_spend = TargetSpend()
    c.contains_eu_political_advertising = client.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING
    resp = svc.mutate_campaigns(customer_id=customer_id, operations=[op])
    return {"campaign_resource": resp.results[0].resource_name}


@mcp.tool()
def update_campaign_status(
    customer_id: str,
    campaign_resource: str,
    status: str,
) -> dict:
    """Enable or pause a campaign.

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_resource: Campaign resource name (e.g. 'customers/XXX/campaigns/YYY')
        status: ENABLED or PAUSED
    """
    client = utils.get_googleads_client()
    svc = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    c = op.update
    c.resource_name = campaign_resource
    c.status = client.enums.CampaignStatusEnum[status]
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    resp = svc.mutate_campaigns(customer_id=customer_id, operations=[op])
    return {"updated": resp.results[0].resource_name, "status": status}


@mcp.tool()
def remove_campaign(
    customer_id: str,
    campaign_resource: str,
) -> dict:
    """Permanently remove (delete) a campaign.

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_resource: Campaign resource name (e.g. 'customers/XXX/campaigns/YYY')
    """
    client = utils.get_googleads_client()
    svc = client.get_service("CampaignService")
    op = client.get_type("CampaignOperation")
    op.remove = campaign_resource
    svc.mutate_campaigns(customer_id=customer_id, operations=[op])
    return {"removed": campaign_resource}


# ─────────────────────────────────────────────
# GEO TARGETING
# ─────────────────────────────────────────────

@mcp.tool()
def suggest_geo_targets(
    country_code: str,
    location_name: str,
) -> list:
    """Look up geo target constant IDs by location name. Use before add_geo_targets.

    Args:
        country_code: Two-letter country code, e.g. 'US', 'IN', 'AE', 'SG', 'AU', 'GB'
        location_name: City, region, or country name, e.g. 'United Arab Emirates', 'Singapore', 'Bangalore'
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GeoTargetConstantService")
    req = client.get_type("SuggestGeoTargetConstantsRequest")
    req.locale = "en"
    req.country_code = country_code
    req.location_names.names.append(location_name)
    resp = svc.suggest_geo_target_constants(request=req)
    results = []
    for r in resp.geo_target_constant_suggestions[:5]:
        g = r.geo_target_constant
        results.append({
            "id": g.id,
            "resource_name": g.resource_name,
            "name": g.name,
            "target_type": g.target_type,
            "country_code": g.country_code,
        })
    return results


@mcp.tool()
def add_geo_targets(
    customer_id: str,
    campaign_resource: str,
    geo_target_ids: list,
) -> dict:
    """Add location (geo) targets to a campaign.

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_resource: Campaign resource name
        geo_target_ids: List of geo target constant IDs (integers from suggest_geo_targets).
                        e.g. [2784, 2702, 2036] for UAE, Singapore, Australia
    """
    client = utils.get_googleads_client()
    svc = client.get_service("CampaignCriterionService")
    ops = []
    for geo_id in geo_target_ids:
        op = client.get_type("CampaignCriterionOperation")
        cr = op.create
        cr.campaign = campaign_resource
        cr.location.geo_target_constant = f"geoTargetConstants/{geo_id}"
        ops.append(op)
    svc.mutate_campaign_criteria(customer_id=customer_id, operations=ops)
    return {"geo_targets_added": len(ops), "ids": geo_target_ids}


# ─────────────────────────────────────────────
# AD GROUPS
# ─────────────────────────────────────────────

@mcp.tool()
def create_ad_group(
    customer_id: str,
    campaign_resource: str,
    name: str,
    cpc_bid_rupees: float = 80.0,
) -> dict:
    """Create an ad group inside a campaign.

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_resource: Campaign resource name
        name: Ad group name
        cpc_bid_rupees: Max CPC bid in Indian Rupees (default 80 ≈ ~$1 USD)
    """
    client = utils.get_googleads_client()
    svc = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    ag = op.create
    ag.name = name
    ag.campaign = campaign_resource
    ag.status = client.enums.AdGroupStatusEnum.ENABLED
    ag.type_ = client.enums.AdGroupTypeEnum.SEARCH_STANDARD
    ag.cpc_bid_micros = int(cpc_bid_rupees * 1_000_000)
    resp = svc.mutate_ad_groups(customer_id=customer_id, operations=[op])
    return {"ad_group_resource": resp.results[0].resource_name}


@mcp.tool()
def update_ad_group_status(
    customer_id: str,
    ad_group_resource: str,
    status: str,
) -> dict:
    """Enable or pause an ad group.

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_resource: Ad group resource name
        status: ENABLED or PAUSED
    """
    client = utils.get_googleads_client()
    svc = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    ag = op.update
    ag.resource_name = ad_group_resource
    ag.status = client.enums.AdGroupStatusEnum[status]
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    resp = svc.mutate_ad_groups(customer_id=customer_id, operations=[op])
    return {"updated": resp.results[0].resource_name, "status": status}


@mcp.tool()
def update_ad_group_bid(
    customer_id: str,
    ad_group_resource: str,
    cpc_bid_rupees: float,
) -> dict:
    """Update the CPC bid for an ad group.

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_resource: Ad group resource name
        cpc_bid_rupees: New max CPC in Indian Rupees
    """
    client = utils.get_googleads_client()
    svc = client.get_service("AdGroupService")
    op = client.get_type("AdGroupOperation")
    ag = op.update
    ag.resource_name = ad_group_resource
    ag.cpc_bid_micros = int(cpc_bid_rupees * 1_000_000)
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["cpc_bid_micros"]))
    resp = svc.mutate_ad_groups(customer_id=customer_id, operations=[op])
    return {"updated": resp.results[0].resource_name, "cpc_bid_rupees": cpc_bid_rupees}


# ─────────────────────────────────────────────
# KEYWORDS
# ─────────────────────────────────────────────

@mcp.tool()
def add_keywords(
    customer_id: str,
    ad_group_resource: str,
    keywords: list,
) -> dict:
    """Add keywords to an ad group.

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_resource: Ad group resource name
        keywords: List of dicts with keys 'text' and 'match_type' (BROAD, PHRASE, or EXACT)
                  e.g. [{"text": "RAG system development", "match_type": "PHRASE"}, ...]
    """
    client = utils.get_googleads_client()
    svc = client.get_service("AdGroupCriterionService")
    ops = []
    for kw in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = ad_group_resource
        c.status = client.enums.AdGroupCriterionStatusEnum.ENABLED
        c.keyword.text = kw["text"]
        c.keyword.match_type = client.enums.KeywordMatchTypeEnum[kw["match_type"]]
        ops.append(op)
    svc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops)
    return {"keywords_created": len(ops)}


@mcp.tool()
def add_negative_keywords(
    customer_id: str,
    ad_group_resource: str,
    keywords: list,
) -> dict:
    """Add negative keywords to an ad group to prevent irrelevant clicks.

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_resource: Ad group resource name
        keywords: List of dicts with keys 'text' and 'match_type' (BROAD, PHRASE, or EXACT)
                  e.g. [{"text": "free", "match_type": "BROAD"}, {"text": "jobs", "match_type": "BROAD"}]
    """
    client = utils.get_googleads_client()
    svc = client.get_service("AdGroupCriterionService")
    ops = []
    for kw in keywords:
        op = client.get_type("AdGroupCriterionOperation")
        c = op.create
        c.ad_group = ad_group_resource
        c.negative = True
        c.keyword.text = kw["text"]
        c.keyword.match_type = client.enums.KeywordMatchTypeEnum[kw["match_type"]]
        ops.append(op)
    svc.mutate_ad_group_criteria(customer_id=customer_id, operations=ops)
    return {"negative_keywords_created": len(ops)}


@mcp.tool()
def add_campaign_negative_keywords(
    customer_id: str,
    campaign_resource: str,
    keywords: list,
) -> dict:
    """Add campaign-level negative keywords (apply to all ad groups in campaign).

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_resource: Campaign resource name
        keywords: List of dicts with keys 'text' and 'match_type' (BROAD, PHRASE, or EXACT)
                  e.g. [{"text": "free", "match_type": "BROAD"}, {"text": "tutorial", "match_type": "BROAD"}]
    """
    client = utils.get_googleads_client()
    svc = client.get_service("CampaignCriterionService")
    ops = []
    for kw in keywords:
        op = client.get_type("CampaignCriterionOperation")
        c = op.create
        c.campaign = campaign_resource
        c.negative = True
        c.keyword.text = kw["text"]
        c.keyword.match_type = client.enums.KeywordMatchTypeEnum[kw["match_type"]]
        ops.append(op)
    svc.mutate_campaign_criteria(customer_id=customer_id, operations=ops)
    return {"campaign_negative_keywords_created": len(ops)}


# ─────────────────────────────────────────────
# ADS
# ─────────────────────────────────────────────

@mcp.tool()
def create_responsive_search_ad(
    customer_id: str,
    ad_group_resource: str,
    headlines: list,
    descriptions: list,
    final_url: str,
) -> dict:
    """Create a Responsive Search Ad (RSA) in an ad group.

    IMPORTANT limits:
    - Headlines: 3-15 items, each max 30 characters
    - Descriptions: 2-4 items, each max 90 characters

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_resource: Ad group resource name
        headlines: List of headline strings (3-15, each ≤30 chars)
        descriptions: List of description strings (2-4, each ≤90 chars)
        final_url: Landing page URL
    """
    # Validate lengths before sending
    errors = []
    for i, h in enumerate(headlines):
        if len(h) > 30:
            errors.append(f"Headline {i+1} too long ({len(h)} chars, max 30): '{h}'")
    for i, d in enumerate(descriptions):
        if len(d) > 90:
            errors.append(f"Description {i+1} too long ({len(d)} chars, max 90): '{d}'")
    if errors:
        return {"error": "Text length violations", "details": errors}

    client = utils.get_googleads_client()
    svc = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    aa = op.create
    aa.ad_group = ad_group_resource
    aa.status = client.enums.AdGroupAdStatusEnum.ENABLED
    rsa = aa.ad.responsive_search_ad
    for h in headlines:
        a = client.get_type("AdTextAsset"); a.text = h; rsa.headlines.append(a)
    for d in descriptions:
        a = client.get_type("AdTextAsset"); a.text = d; rsa.descriptions.append(a)
    aa.ad.final_urls.append(final_url)
    resp = svc.mutate_ad_group_ads(customer_id=customer_id, operations=[op])
    return {"ad_resource": resp.results[0].resource_name}


# ─────────────────────────────────────────────
# AD-LEVEL MANAGEMENT
# ─────────────────────────────────────────────

@mcp.tool()
def list_ads(
    customer_id: str,
    ad_group_id: str,
) -> list:
    """List all ads in an ad group with approval status and ad strength.

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_id: Ad group ID (numeric only, e.g. '198060513554')
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    query = f"""
        SELECT ad_group_ad.ad.id, ad_group_ad.ad.type,
               ad_group_ad.status, ad_group_ad.ad_strength,
               ad_group_ad.policy_summary.approval_status,
               ad_group_ad.policy_summary.review_status
        FROM ad_group_ad
        WHERE ad_group.id = {ad_group_id}
          AND ad_group_ad.status != 'REMOVED'
        ORDER BY ad_group_ad.ad.id
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            aa = row.ad_group_ad
            results.append({
                "ad_id": aa.ad.id,
                "ad_resource": f"customers/{customer_id}/adGroupAds/{ad_group_id}~{aa.ad.id}",
                "type": aa.ad.type_.name,
                "status": aa.status.name,
                "ad_strength": aa.ad_strength.name,
                "approval_status": aa.policy_summary.approval_status.name,
                "review_status": aa.policy_summary.review_status.name,
            })
    return results


@mcp.tool()
def update_ad_status(
    customer_id: str,
    ad_group_ad_resource: str,
    status: str,
) -> dict:
    """Pause, enable, or remove a specific ad.

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_ad_resource: Ad resource name in format 'customers/XXX/adGroupAds/YYY~ZZZ'
                              (get from list_ads)
        status: ENABLED, PAUSED, or REMOVED
    """
    client = utils.get_googleads_client()
    svc = client.get_service("AdGroupAdService")
    op = client.get_type("AdGroupAdOperation")
    if status == "REMOVED":
        op.remove = ad_group_ad_resource
    else:
        aa = op.update
        aa.resource_name = ad_group_ad_resource
        aa.status = client.enums.AdGroupAdStatusEnum[status]
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    resp = svc.mutate_ad_group_ads(customer_id=customer_id, operations=[op])
    return {"updated": resp.results[0].resource_name, "status": status}


@mcp.tool()
def update_keyword_status(
    customer_id: str,
    ad_group_criterion_resource: str,
    status: str,
) -> dict:
    """Pause, enable, or remove a specific keyword.

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_criterion_resource: Criterion resource name 'customers/XXX/adGroupCriteria/YYY~ZZZ'
                                     (use list_keywords to find — criterion_id gives the ZZZ part)
        status: ENABLED, PAUSED, or REMOVED
    """
    client = utils.get_googleads_client()
    svc = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    if status == "REMOVED":
        op.remove = ad_group_criterion_resource
    else:
        c = op.update
        c.resource_name = ad_group_criterion_resource
        c.status = client.enums.AdGroupCriterionStatusEnum[status]
        op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["status"]))
    resp = svc.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
    return {"updated": resp.results[0].resource_name, "status": status}


@mcp.tool()
def update_keyword_bid(
    customer_id: str,
    ad_group_criterion_resource: str,
    cpc_bid_rupees: float,
) -> dict:
    """Update the CPC bid for a specific keyword.

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_criterion_resource: Criterion resource name 'customers/XXX/adGroupCriteria/YYY~ZZZ'
        cpc_bid_rupees: New CPC bid in Indian Rupees
    """
    client = utils.get_googleads_client()
    svc = client.get_service("AdGroupCriterionService")
    op = client.get_type("AdGroupCriterionOperation")
    c = op.update
    c.resource_name = ad_group_criterion_resource
    c.cpc_bid_micros = int(cpc_bid_rupees * 1_000_000)
    op.update_mask.CopyFrom(field_mask_pb2.FieldMask(paths=["cpc_bid_micros"]))
    resp = svc.mutate_ad_group_criteria(customer_id=customer_id, operations=[op])
    return {"updated": resp.results[0].resource_name, "cpc_bid_rupees": cpc_bid_rupees}


# ─────────────────────────────────────────────
# PERFORMANCE & ANALYTICS
# ─────────────────────────────────────────────

@mcp.tool()
def get_ad_group_performance(
    customer_id: str,
    campaign_id: str,
    date_range: str = "LAST_30_DAYS",
) -> list:
    """Get performance metrics broken down by ad group.

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_id: Campaign ID (numeric only)
        date_range: LAST_7_DAYS, LAST_30_DAYS, LAST_90_DAYS, THIS_MONTH, LAST_MONTH
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    query = f"""
        SELECT ad_group.id, ad_group.name, ad_group.status,
               metrics.clicks, metrics.impressions, metrics.cost_micros,
               metrics.average_cpc, metrics.ctr, metrics.conversions,
               metrics.cost_per_conversion
        FROM ad_group
        WHERE campaign.id = {campaign_id}
          AND ad_group.status != 'REMOVED'
          AND segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            m = row.metrics
            results.append({
                "ad_group_id": row.ad_group.id,
                "ad_group_name": row.ad_group.name,
                "status": row.ad_group.status.name,
                "date_range": date_range,
                "clicks": m.clicks,
                "impressions": m.impressions,
                "cost_rupees": round(m.cost_micros / 1_000_000, 2),
                "avg_cpc_rupees": round(m.average_cpc / 1_000_000, 2),
                "ctr_percent": round(m.ctr * 100, 2),
                "conversions": m.conversions,
                "cost_per_conversion_rupees": round(m.cost_per_conversion / 1_000_000, 2) if m.conversions else None,
            })
    return results


@mcp.tool()
def get_keyword_performance(
    customer_id: str,
    campaign_id: str,
    date_range: str = "LAST_30_DAYS",
) -> list:
    """Get performance metrics per keyword — use to identify top/worst performers and adjust bids.

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_id: Campaign ID (numeric only)
        date_range: LAST_7_DAYS, LAST_30_DAYS, LAST_90_DAYS, THIS_MONTH, LAST_MONTH
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    query = f"""
        SELECT ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type,
               ad_group_criterion.criterion_id,
               ad_group_criterion.cpc_bid_micros,
               ad_group_criterion.status,
               ad_group.id, ad_group.name,
               metrics.clicks, metrics.impressions, metrics.cost_micros,
               metrics.average_cpc, metrics.ctr, metrics.conversions,
               metrics.search_impression_share,
               ad_group_criterion.quality_info.quality_score
        FROM keyword_view
        WHERE campaign.id = {campaign_id}
          AND ad_group_criterion.status != 'REMOVED'
          AND segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
        LIMIT 100
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            m = row.metrics
            c = row.ad_group_criterion
            results.append({
                "keyword": c.keyword.text,
                "match_type": c.keyword.match_type.name,
                "criterion_id": c.criterion_id,
                "ad_group_id": row.ad_group.id,
                "ad_group_name": row.ad_group.name,
                "ad_group_criterion_resource": f"customers/{customer_id}/adGroupCriteria/{row.ad_group.id}~{c.criterion_id}",
                "cpc_bid_rupees": round(c.cpc_bid_micros / 1_000_000, 2),
                "quality_score": c.quality_info.quality_score,
                "clicks": m.clicks,
                "impressions": m.impressions,
                "cost_rupees": round(m.cost_micros / 1_000_000, 2),
                "avg_cpc_rupees": round(m.average_cpc / 1_000_000, 2),
                "ctr_percent": round(m.ctr * 100, 2),
                "impression_share_pct": round(m.search_impression_share * 100, 1) if m.search_impression_share else None,
                "conversions": m.conversions,
            })
    return results


@mcp.tool()
def get_search_terms_report(
    customer_id: str,
    campaign_id: str,
    date_range: str = "LAST_30_DAYS",
    min_impressions: int = 5,
) -> list:
    """Get the actual search queries that triggered your ads. Critical for adding negative keywords.

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_id: Campaign ID (numeric only)
        date_range: LAST_7_DAYS, LAST_30_DAYS, LAST_90_DAYS, THIS_MONTH, LAST_MONTH
        min_impressions: Only return terms with at least this many impressions (default 5)
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    query = f"""
        SELECT search_term_view.search_term,
               search_term_view.status,
               ad_group.id, ad_group.name,
               metrics.clicks, metrics.impressions, metrics.cost_micros,
               metrics.ctr, metrics.conversions, metrics.average_cpc
        FROM search_term_view
        WHERE campaign.id = {campaign_id}
          AND segments.date DURING {date_range}
          AND metrics.impressions >= {min_impressions}
        ORDER BY metrics.cost_micros DESC
        LIMIT 200
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            m = row.metrics
            results.append({
                "search_term": row.search_term_view.search_term,
                "status": row.search_term_view.status.name,
                "ad_group_id": row.ad_group.id,
                "ad_group_name": row.ad_group.name,
                "impressions": m.impressions,
                "clicks": m.clicks,
                "cost_rupees": round(m.cost_micros / 1_000_000, 2),
                "avg_cpc_rupees": round(m.average_cpc / 1_000_000, 2),
                "ctr_percent": round(m.ctr * 100, 2),
                "conversions": m.conversions,
            })
    return results


@mcp.tool()
def get_ad_performance(
    customer_id: str,
    campaign_id: str,
    date_range: str = "LAST_30_DAYS",
) -> list:
    """Get performance metrics per individual ad — use to identify and pause underperforming ads.

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_id: Campaign ID (numeric only)
        date_range: LAST_7_DAYS, LAST_30_DAYS, LAST_90_DAYS, THIS_MONTH, LAST_MONTH
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    query = f"""
        SELECT ad_group_ad.ad.id, ad_group_ad.status,
               ad_group_ad.ad_strength,
               ad_group_ad.policy_summary.approval_status,
               ad_group.id, ad_group.name,
               metrics.clicks, metrics.impressions, metrics.cost_micros,
               metrics.ctr, metrics.conversions, metrics.average_cpc
        FROM ad_group_ad
        WHERE campaign.id = {campaign_id}
          AND ad_group_ad.status != 'REMOVED'
          AND segments.date DURING {date_range}
        ORDER BY metrics.cost_micros DESC
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            aa = row.ad_group_ad
            m = row.metrics
            results.append({
                "ad_id": aa.ad.id,
                "ad_resource": f"customers/{customer_id}/adGroupAds/{row.ad_group.id}~{aa.ad.id}",
                "ad_group_id": row.ad_group.id,
                "ad_group_name": row.ad_group.name,
                "status": aa.status.name,
                "ad_strength": aa.ad_strength.name,
                "approval_status": aa.policy_summary.approval_status.name,
                "date_range": date_range,
                "impressions": m.impressions,
                "clicks": m.clicks,
                "cost_rupees": round(m.cost_micros / 1_000_000, 2),
                "avg_cpc_rupees": round(m.average_cpc / 1_000_000, 2),
                "ctr_percent": round(m.ctr * 100, 2),
                "conversions": m.conversions,
            })
    return results


# ─────────────────────────────────────────────
# CONVERSION ACTIONS
# ─────────────────────────────────────────────

@mcp.tool()
def list_conversion_actions(
    customer_id: str,
) -> list:
    """List all conversion actions configured in the account.

    Args:
        customer_id: Google Ads customer ID (digits only)
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    query = """
        SELECT conversion_action.id, conversion_action.name,
               conversion_action.status, conversion_action.type,
               conversion_action.category,
               conversion_action.tag_snippets
        FROM conversion_action
        WHERE conversion_action.status != 'REMOVED'
        ORDER BY conversion_action.id
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            ca = row.conversion_action
            results.append({
                "id": ca.id,
                "name": ca.name,
                "status": ca.status.name,
                "type": ca.type_.name,
                "category": ca.category.name,
                "resource_name": ca.resource_name,
            })
    return results


@mcp.tool()
def create_conversion_action(
    customer_id: str,
    name: str,
    category: str = "SUBMIT_LEAD_FORM",
) -> dict:
    """Create a conversion action for tracking leads/form submissions.

    Args:
        customer_id: Google Ads customer ID (digits only)
        name: Descriptive name e.g. 'Contact Form Submission' or 'Thank You Page Visit'
        category: SUBMIT_LEAD_FORM (default), PURCHASE, SIGNUP, PAGE_VIEW, DOWNLOAD,
                  PHONE_CALL_LEAD, IMPORTED_LEAD, QUALIFIED_LEAD, CONVERTED_LEAD, DEFAULT
    """
    client = utils.get_googleads_client()
    svc = client.get_service("ConversionActionService")
    op = client.get_type("ConversionActionOperation")
    ca = op.create
    ca.name = name
    ca.type_ = client.enums.ConversionActionTypeEnum.WEBPAGE
    ca.category = getattr(client.enums.ConversionActionCategoryEnum, category)
    ca.status = client.enums.ConversionActionStatusEnum.ENABLED
    ca.value_settings.default_value = 0.0
    ca.value_settings.always_use_default_value = True
    resp = svc.mutate_conversion_actions(customer_id=customer_id, operations=[op])
    result = resp.results[0]
    return {
        "conversion_action_resource": result.resource_name,
        "name": name,
        "category": category,
        "note": "Add the conversion action ID to your thank-you page gtag snippet",
    }


# ─────────────────────────────────────────────
# LISTING / INSPECTION
# ─────────────────────────────────────────────

@mcp.tool()
def list_campaigns(
    customer_id: str,
    include_removed: bool = False,
) -> list:
    """List all campaigns with their status, budget, and resource name.

    Args:
        customer_id: Google Ads customer ID (digits only)
        include_removed: Whether to include removed campaigns (default False)
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    where = "" if include_removed else "WHERE campaign.status != 'REMOVED'"
    query = f"""
        SELECT campaign.id, campaign.name, campaign.status,
               campaign.advertising_channel_type,
               campaign_budget.amount_micros, campaign_budget.resource_name
        FROM campaign
        {where}
        ORDER BY campaign.id DESC
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            results.append({
                "id": row.campaign.id,
                "name": row.campaign.name,
                "status": row.campaign.status.name,
                "channel": row.campaign.advertising_channel_type.name,
                "daily_budget_rupees": row.campaign_budget.amount_micros / 1_000_000,
                "campaign_resource": f"customers/{customer_id}/campaigns/{row.campaign.id}",
                "budget_resource": row.campaign_budget.resource_name,
            })
    return results


@mcp.tool()
def list_ad_groups(
    customer_id: str,
    campaign_id: str,
) -> list:
    """List all ad groups in a campaign.

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_id: Campaign ID (numeric only, e.g. '23711872931')
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    query = f"""
        SELECT ad_group.id, ad_group.name, ad_group.status, ad_group.cpc_bid_micros
        FROM ad_group
        WHERE campaign.id = {campaign_id}
          AND ad_group.status != 'REMOVED'
        ORDER BY ad_group.id
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            results.append({
                "id": row.ad_group.id,
                "name": row.ad_group.name,
                "status": row.ad_group.status.name,
                "cpc_bid_rupees": row.ad_group.cpc_bid_micros / 1_000_000,
                "ad_group_resource": f"customers/{customer_id}/adGroups/{row.ad_group.id}",
            })
    return results


@mcp.tool()
def list_keywords(
    customer_id: str,
    ad_group_id: str,
) -> list:
    """List all keywords in an ad group.

    Args:
        customer_id: Google Ads customer ID (digits only)
        ad_group_id: Ad group ID (numeric only, e.g. '198060513554')
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    query = f"""
        SELECT ad_group_criterion.keyword.text,
               ad_group_criterion.keyword.match_type,
               ad_group_criterion.status,
               ad_group_criterion.negative,
               ad_group_criterion.criterion_id
        FROM ad_group_criterion
        WHERE ad_group.id = {ad_group_id}
          AND ad_group_criterion.type = 'KEYWORD'
          AND ad_group_criterion.status != 'REMOVED'
        ORDER BY ad_group_criterion.criterion_id
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    results = []
    for batch in stream:
        for row in batch.results:
            c = row.ad_group_criterion
            results.append({
                "text": c.keyword.text,
                "match_type": c.keyword.match_type.name,
                "negative": c.negative,
                "status": c.status.name,
                "criterion_id": c.criterion_id,
            })
    return results


@mcp.tool()
def get_campaign_performance(
    customer_id: str,
    campaign_id: str,
    date_range: str = "LAST_30_DAYS",
) -> dict:
    """Get performance metrics for a campaign (clicks, impressions, cost, conversions).

    Args:
        customer_id: Google Ads customer ID (digits only)
        campaign_id: Campaign ID (numeric only)
        date_range: One of LAST_7_DAYS, LAST_30_DAYS, LAST_90_DAYS, THIS_MONTH, LAST_MONTH
    """
    client = utils.get_googleads_client()
    svc = client.get_service("GoogleAdsService")
    query = f"""
        SELECT campaign.name,
               metrics.clicks, metrics.impressions, metrics.cost_micros,
               metrics.average_cpc, metrics.ctr, metrics.conversions,
               metrics.cost_per_conversion
        FROM campaign
        WHERE campaign.id = {campaign_id}
          AND segments.date DURING {date_range}
    """
    stream = svc.search_stream(customer_id=customer_id, query=query)
    for batch in stream:
        for row in batch.results:
            m = row.metrics
            return {
                "campaign_name": row.campaign.name,
                "date_range": date_range,
                "clicks": m.clicks,
                "impressions": m.impressions,
                "cost_rupees": m.cost_micros / 1_000_000,
                "avg_cpc_rupees": m.average_cpc / 1_000_000,
                "ctr_percent": round(m.ctr * 100, 2),
                "conversions": m.conversions,
                "cost_per_conversion_rupees": m.cost_per_conversion / 1_000_000 if m.conversions else None,
            }
    return {"campaign_id": campaign_id, "message": "No data yet for this period"}
