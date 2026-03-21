# Copyright 2025 Google LLC.
#
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

"""Tools for creating and managing assets (sitelinks, callouts, etc.) via the MCP server."""

from typing import Dict, Any, List, Optional
from ads_mcp.coordinator import mcp
import ads_mcp.utils as utils


@mcp.tool()
def create_sitelink_asset(
    customer_id: str,
    link_text: str,
    final_url: str,
    description1: Optional[str] = None,
    description2: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a sitelink asset that can be linked to campaigns or ad groups.

    Sitelinks add additional links below your ad, directing users to specific pages.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        link_text: The text displayed for the sitelink (max 25 characters).
        final_url: The URL the sitelink directs to.
        description1: First line of description (max 35 characters). Optional.
        description2: Second line of description (max 35 characters). Optional.
        start_date: Start date in YYYY-MM-DD format. Optional.
        end_date: End date in YYYY-MM-DD format. Optional.

    Returns:
        Dictionary with the created asset resource name.
    """
    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create
    asset.sitelink_asset.link_text = link_text
    asset.final_urls.append(final_url)

    if description1:
        asset.sitelink_asset.description1 = description1
    if description2:
        asset.sitelink_asset.description2 = description2
    if start_date:
        asset.sitelink_asset.start_date = start_date
    if end_date:
        asset.sitelink_asset.end_date = end_date

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"Sitelink asset '{link_text}' created successfully.",
    }


@mcp.tool()
def create_callout_asset(
    customer_id: str,
    callout_text: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a callout asset that can be linked to campaigns or ad groups.

    Callouts add short snippets of text to your ad (e.g., "Free Shipping", "24/7 Support").

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        callout_text: The callout text (max 25 characters).
        start_date: Start date in YYYY-MM-DD format. Optional.
        end_date: End date in YYYY-MM-DD format. Optional.

    Returns:
        Dictionary with the created asset resource name.
    """
    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create
    asset.callout_asset.callout_text = callout_text

    if start_date:
        asset.callout_asset.start_date = start_date
    if end_date:
        asset.callout_asset.end_date = end_date

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"Callout asset '{callout_text}' created successfully.",
    }


@mcp.tool()
def create_structured_snippet_asset(
    customer_id: str,
    header: str,
    values: List[str],
) -> Dict[str, Any]:
    """Creates a structured snippet asset that can be linked to campaigns or ad groups.

    Structured snippets highlight specific aspects of your products/services
    (e.g., header "Brands" with values ["Nike", "Adidas", "Puma"]).

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        header: The snippet header. One of: Amenities, Brands, Courses, Degree programs,
            Destinations, Featured hotels, Insurance coverage, Models, Neighborhoods,
            Service catalog, Shows, Styles, Types.
        values: List of values for the snippet (min 3 values recommended).

    Returns:
        Dictionary with the created asset resource name.
    """
    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create
    asset.structured_snippet_asset.header = header
    for value in values:
        asset.structured_snippet_asset.values.append(value)

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"Structured snippet asset with header '{header}' created successfully.",
    }


@mcp.tool()
def create_call_asset(
    customer_id: str,
    country_code: str,
    phone_number: str,
    call_conversion_reporting_state: str = "DISABLED",
) -> Dict[str, Any]:
    """Creates a call asset that can be linked to campaigns or ad groups.

    Call assets add a phone number to your ad, allowing users to call directly.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        country_code: Two-letter country code (e.g., "US", "GB", "IN").
        phone_number: The phone number string.
        call_conversion_reporting_state: One of: DISABLED, USE_ACCOUNT_LEVEL_CALL_CONVERSION_ACTION,
            USE_RESOURCE_LEVEL_CALL_CONVERSION_ACTION. Default: DISABLED.

    Returns:
        Dictionary with the created asset resource name.
    """
    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create
    asset.call_asset.country_code = country_code
    asset.call_asset.phone_number = phone_number

    reporting_enum = client.enums.CallConversionReportingStateEnum
    asset.call_asset.call_conversion_reporting_state = getattr(
        reporting_enum, call_conversion_reporting_state
    )

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"Call asset with phone number '{phone_number}' created successfully.",
    }


@mcp.tool()
def create_image_asset(
    customer_id: str,
    image_source: str,
    asset_name: str,
) -> Dict[str, Any]:
    """Creates an image asset from a URL or local file path.

    Supports both web URLs and local file paths on the user's computer.

    Recommended image sizes for Performance Max:
    - Marketing image (landscape): 1200x628
    - Square marketing image: 1200x1200
    - Logo: 1200x1200
    - Landscape logo: 1200x300

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        image_source: Either a URL (https://...) or a local file path (/path/to/image.jpg).
        asset_name: A name for the image asset.

    Returns:
        Dictionary with the created asset resource name.
    """
    import os

    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    # Load image data from URL or local file
    if image_source.startswith(("http://", "https://")):
        import urllib.request

        image_data = urllib.request.urlopen(image_source).read()
    elif os.path.isfile(image_source):
        with open(image_source, "rb") as f:
            image_data = f.read()
    else:
        raise ValueError(
            f"Image source '{image_source}' is not a valid URL or file path."
        )

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create
    asset.type_ = client.enums.AssetTypeEnum.IMAGE
    asset.name = asset_name
    asset.image_asset.data = image_data

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"Image asset '{asset_name}' created successfully.",
    }


@mcp.tool()
def create_promotion_asset(
    customer_id: str,
    promotion_target: str,
    discount_modifier: str = "NONE",
    percent_off: Optional[int] = None,
    money_amount_off_micros: Optional[int] = None,
    money_amount_off_currency: Optional[str] = None,
    occasion: str = "NONE",
    language_code: str = "en",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    redemption_start_date: Optional[str] = None,
    redemption_end_date: Optional[str] = None,
    promotion_code: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a promotion asset that can be linked to campaigns or ad groups.

    Promotion assets highlight sales and special offers in your ads.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        promotion_target: What the promotion is for (e.g., "Summer Collection", "All Shoes").
        discount_modifier: One of: NONE, UP_TO. Default: NONE.
        percent_off: Percentage discount (e.g., 20 for 20% off). Use this OR money_amount_off.
        money_amount_off_micros: Money discount in micros (e.g., 5000000 = $5 off). Use this OR percent_off.
        money_amount_off_currency: Currency code for money discount (e.g., "USD").
        occasion: Occasion for the promotion. One of: NONE, NEW_YEARS, VALENTINES_DAY,
            EASTER, MOTHERS_DAY, FATHERS_DAY, LABOR_DAY, BACK_TO_SCHOOL, HALLOWEEN,
            BLACK_FRIDAY, CYBER_MONDAY, CHRISTMAS, BOXING_DAY, and more. Default: NONE.
        language_code: Language code (e.g., "en"). Default: "en".
        start_date: Asset start date in YYYY-MM-DD format. Optional.
        end_date: Asset end date in YYYY-MM-DD format. Optional.
        redemption_start_date: Promotion redemption start date in YYYY-MM-DD format. Optional.
        redemption_end_date: Promotion redemption end date in YYYY-MM-DD format. Optional.
        promotion_code: A promotion code users can use (e.g., "SAVE20"). Optional.

    Returns:
        Dictionary with the created asset resource name.
    """
    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create
    asset.promotion_asset.promotion_target = promotion_target
    asset.promotion_asset.language_code = language_code

    # Set discount
    discount_enum = client.enums.PromotionExtensionDiscountModifierEnum
    asset.promotion_asset.discount_modifier = getattr(
        discount_enum, discount_modifier
    )

    if percent_off is not None:
        asset.promotion_asset.percent_off = percent_off
    elif money_amount_off_micros is not None:
        asset.promotion_asset.money_amount_off.amount_micros = (
            money_amount_off_micros
        )
        if money_amount_off_currency:
            asset.promotion_asset.money_amount_off.currency_code = (
                money_amount_off_currency
            )

    # Set occasion
    occasion_enum = client.enums.PromotionExtensionOccasionEnum
    asset.promotion_asset.occasion = getattr(occasion_enum, occasion)

    # Set dates
    if start_date:
        asset.promotion_asset.start_date = start_date
    if end_date:
        asset.promotion_asset.end_date = end_date
    if redemption_start_date:
        asset.promotion_asset.redemption_start_date = redemption_start_date
    if redemption_end_date:
        asset.promotion_asset.redemption_end_date = redemption_end_date

    # Set promotion code
    if promotion_code:
        asset.promotion_asset.promotion_code = promotion_code

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"Promotion asset for '{promotion_target}' created successfully.",
    }


@mcp.tool()
def create_price_asset(
    customer_id: str,
    price_type: str,
    price_offerings: List[Dict[str, str]],
    language_code: str = "en",
    price_qualifier: str = "NONE",
) -> Dict[str, Any]:
    """Creates a price asset that can be linked to campaigns or ad groups.

    Price assets showcase your products or services with their prices.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        price_type: The type of price. One of: BRANDS, EVENTS, LOCATIONS, NEIGHBORHOODS,
            PRODUCT_CATEGORIES, PRODUCT_TIERS, SERVICES, SERVICE_CATEGORIES, SERVICE_TIERS.
        price_offerings: List of price offerings (min 3, max 8), each with:
            - header: The offering name (max 25 characters).
            - description: Description of the offering (max 25 characters).
            - price_micros: Price in micros (e.g., 9990000 = $9.99).
            - currency_code: Currency code (e.g., "USD").
            - unit: Price unit. One of: PER_HOUR, PER_DAY, PER_WEEK, PER_MONTH, PER_YEAR, NONE.
            - final_url: The landing page URL for this offering.
        language_code: Language code (e.g., "en"). Default: "en".
        price_qualifier: One of: NONE, FROM, UP_TO, AVERAGE. Default: "NONE".

    Returns:
        Dictionary with the created asset resource name.
    """
    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create

    # Set price type
    type_enum = client.enums.PriceExtensionTypeEnum
    asset.price_asset.type_ = getattr(type_enum, price_type)
    asset.price_asset.language_code = language_code

    # Set price qualifier
    qualifier_enum = client.enums.PriceExtensionPriceQualifierEnum
    asset.price_asset.price_qualifier = getattr(qualifier_enum, price_qualifier)

    # Add offerings
    for offering in price_offerings:
        price_offering = client.get_type("PriceOffering")
        price_offering.header = offering["header"]
        price_offering.description = offering["description"]
        price_offering.price.amount_micros = int(offering["price_micros"])
        price_offering.price.currency_code = offering.get(
            "currency_code", "USD"
        )
        price_offering.final_url = offering["final_url"]

        unit = offering.get("unit", "NONE")
        unit_enum = client.enums.PriceExtensionPriceUnitEnum
        price_offering.unit = getattr(unit_enum, unit)

        asset.price_asset.price_offerings.append(price_offering)

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"Price asset with {len(price_offerings)} offerings created successfully.",
    }


@mcp.tool()
def create_lead_form_asset(
    customer_id: str,
    business_name: str,
    headline: str,
    description: str,
    call_to_action_type: str,
    privacy_policy_url: str,
    fields: List[str],
    post_submit_headline: Optional[str] = None,
    post_submit_description: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a lead form asset that can be linked to campaigns or ad groups.

    Lead form assets collect user information directly from the ad.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        business_name: Your business name.
        headline: The lead form headline (max 30 characters).
        description: The lead form description (max 200 characters).
        call_to_action_type: One of: LEARN_MORE, GET_QUOTE, APPLY_NOW, SIGN_UP,
            CONTACT_US, SUBSCRIBE, DOWNLOAD, BOOK_NOW, GET_OFFER, REGISTER, GET_INFO,
            REQUEST_DEMO, JOIN_NOW, GET_STARTED.
        privacy_policy_url: URL to your privacy policy.
        fields: List of form fields to collect. Options: FULL_NAME, EMAIL, PHONE_NUMBER,
            POSTAL_CODE, CITY, REGION, COUNTRY, WORK_EMAIL, COMPANY_NAME, WORK_PHONE,
            JOB_TITLE, FIRST_NAME, LAST_NAME.
        post_submit_headline: Headline shown after form submission. Optional.
        post_submit_description: Description shown after form submission. Optional.

    Returns:
        Dictionary with the created asset resource name.
    """
    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create
    lead_form = asset.lead_form_asset
    lead_form.business_name = business_name
    lead_form.headline = headline
    lead_form.description = description
    lead_form.privacy_policy_url = privacy_policy_url

    # Set call to action
    cta_enum = client.enums.LeadFormCallToActionTypeEnum
    lead_form.call_to_action_type = getattr(cta_enum, call_to_action_type)

    # Add form fields
    for field_name in fields:
        field = client.get_type("LeadFormField")
        field_type_enum = client.enums.LeadFormFieldUserInputTypeEnum
        field.input_type = getattr(field_type_enum, field_name)
        lead_form.fields.append(field)

    # Post-submit content
    if post_submit_headline:
        lead_form.post_submit_headline = post_submit_headline
    if post_submit_description:
        lead_form.post_submit_description = post_submit_description

    # Default post-submit CTA
    post_cta_enum = client.enums.LeadFormPostSubmitCallToActionTypeEnum
    lead_form.post_submit_call_to_action_type = post_cta_enum.VISIT_SITE

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"Lead form asset '{headline}' created successfully.",
    }


@mcp.tool()
def create_text_asset(
    customer_id: str,
    text: str,
) -> Dict[str, Any]:
    """Creates a text asset for use in Performance Max asset groups.

    Use this to create headline, description, and long headline assets
    that can be linked to asset groups.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        text: The text content. Character limits depend on usage:
            - Headlines: max 30 characters
            - Long headlines: max 90 characters
            - Descriptions: max 90 characters

    Returns:
        Dictionary with the created asset resource name.
    """
    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create
    asset.text_asset.text = text

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"Text asset '{text}' created successfully.",
    }


@mcp.tool()
def create_youtube_video_asset(
    customer_id: str,
    youtube_video_id: str,
    asset_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Creates a YouTube video asset for use in Performance Max campaigns.

    Args:
        customer_id: The Google Ads customer ID (numbers only, no hyphens).
        youtube_video_id: The YouTube video ID (e.g., "dQw4w9WgXcQ" from the URL).
        asset_name: Optional name for the asset. If not provided, uses the video ID.

    Returns:
        Dictionary with the created asset resource name.
    """
    client = utils.get_googleads_client()
    asset_service = client.get_service("AssetService")

    asset_operation = client.get_type("AssetOperation")
    asset = asset_operation.create
    asset.name = asset_name or f"YouTube Video {youtube_video_id}"
    asset.youtube_video_asset.youtube_video_id = youtube_video_id

    response = asset_service.mutate_assets(
        customer_id=customer_id, operations=[asset_operation]
    )

    return {
        "asset_resource_name": response.results[0].resource_name,
        "message": f"YouTube video asset '{youtube_video_id}' created successfully.",
    }
