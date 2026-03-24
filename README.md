# Google Ads MCP Server (Full)

This repo extends the [official Google Ads MCP server](https://github.com/googleads/google-ads-mcp) with **30 write tools**, transforming it from read-only to a full campaign management platform. Manage campaigns, ad groups, ads, keywords, assets, and Performance Max — all through natural language.

> For detailed setup instructions, see [SETUP.md](SETUP.md).

## Tools

The server uses the
[Google Ads API](https://developers.google.com/google-ads/api/reference/rpc/v21/overview)
to provide **32**
[Tools](https://modelcontextprotocol.io/docs/concepts/tools) for use with LLMs.

### Tools available (32)

#### Read & Discovery (3)

| Tool | Description |
|---|---|
| `list_accessible_customers` | List all Google Ads accounts you have access to |
| `search` | Query Google Ads data using [GAQL](https://developers.google.com/google-ads/api/docs/query/overview) |
| `get_resource_metadata` | Get selectable, filterable, and sortable fields for any resource |

#### Campaign Management (4)

| Tool | Description |
|---|---|
| `create_campaign` | Create Search, Display, or Shopping campaigns with budget and bidding strategy |
| `create_performance_max_campaign` | Create PMax campaigns with business name and logo via batch mutate |
| `update_campaign` | Update campaign name, status, budget, or dates |
| `set_campaign_status` | Quick enable/pause/remove toggle |

#### Ad Group Management (2)

| Tool | Description |
|---|---|
| `create_ad_group` | Create ad groups with CPC bids and type settings |
| `update_ad_group` | Update ad group name, status, or bids |

#### Ads & Keywords (6)

| Tool | Description |
|---|---|
| `create_responsive_search_ad` | Create RSAs with multiple headlines and descriptions |
| `add_keywords` | Add keywords with match types (exact, phrase, broad) and optional bids |
| `update_ad_status` | Enable, pause, or remove an ad |
| `update_keyword` | Update a keyword's status or bid |
| `remove_ad` | Permanently remove an ad (with [MCP elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation) confirmation) |
| `remove_keyword` | Permanently remove a keyword (with MCP elicitation confirmation) |

#### Asset Creation (10)

| Tool | Description |
|---|---|
| `create_text_asset` | Text assets for PMax headlines, descriptions, long headlines |
| `create_image_asset` | Upload images from URL or local file path |
| `create_youtube_video_asset` | YouTube video assets by video ID |
| `create_sitelink_asset` | Sitelink extensions with URLs and descriptions |
| `create_callout_asset` | Callout extensions (e.g., "Free Shipping", "24/7 Support") |
| `create_structured_snippet_asset` | Structured snippets (e.g., Brands: Nike, Adidas, Puma) |
| `create_call_asset` | Phone number extensions |
| `create_promotion_asset` | Promotion extensions with discounts and dates |
| `create_price_asset` | Price listing extensions with offerings |
| `create_lead_form_asset` | Lead generation form extensions with custom fields |

#### Asset Linking (4)

| Tool | Description |
|---|---|
| `link_asset_to_campaign` | Attach an asset to a campaign |
| `link_asset_to_ad_group` | Attach an asset to an ad group |
| `link_assets_to_customer` | Attach assets at account level (all campaigns) |
| `remove_campaign_asset` | Remove an asset from a campaign (with MCP elicitation confirmation) |

#### Asset Groups / Performance Max (3)

| Tool | Description |
|---|---|
| `create_asset_group` | Create a PMax asset group and link all assets in one batch mutate |
| `add_assets_to_asset_group` | Add more assets to an existing asset group |
| `remove_asset_from_asset_group` | Remove an asset from an asset group (with MCP elicitation confirmation) |

### MCP Elicitation

All 4 destructive tools (`remove_ad`, `remove_keyword`, `remove_campaign_asset`, `remove_asset_from_asset_group`) implement [MCP Elicitation](https://modelcontextprotocol.io/specification/2025-11-25/client/elicitation) to prompt users for confirmation before proceeding. Falls back gracefully on clients that don't support elicitation yet.

## Notes

1.  The MCP Server will expose your data to the Agent or LLM that you connect to it.
1.  If you have technical issues, please use the [GitHub issue tracker](https://github.com/googleads/google-ads-mcp/issues).
1.  To help us collect usage data, you will notice an extra header has been added to your API calls, this data is used to improve the product.

## Setup instructions

Setup involves the following steps:

1.  Configure Python.
1.  Configure Developer Token.
1.  Enable APIs in your project
1.  Configure Credentials.
1.  Configure Gemini.

### Configure Python

[Install pipx](https://pipx.pypa.io/stable/#install-pipx).

### Configure Developer Token

Follow the instructions for [Obtaining a Developer Token](https://developers.google.com/google-ads/api/docs/get-started/dev-token).

Record 'YOUR_DEVELOPER_TOKEN', you will need this for the the 'Configure Gemini' step below

### Enable APIs in your project

[Follow the instructions](https://support.google.com/googleapi/answer/6158841)
to enable the following APIs in your Google Cloud project:

* [Google Ads API](https://console.cloud.google.com/apis/library/googleads.googleapis.com)

### Configure Credentials
#### Option 1: Configure credentials using Application Default Credentials

Configure your [Application Default Credentials
(ADC)](https://cloud.google.com/docs/authentication/provide-credentials-adc).
Make sure the credentials are for a user with access to your Google Ads
accounts or properties.

Credentials must include the Google Ads API scope:

```
https://www.googleapis.com/auth/adwords
```

Check out
[Manage OAuth Clients](https://support.google.com/cloud/answer/15549257)
for how to create an OAuth client.

Here are some sample `gcloud` commands you might find useful:


- Set up ADC using user credentials and an OAuth desktop or web client after
  downloading the client JSON to `YOUR_CLIENT_JSON_FILE`.

  ```shell
  gcloud auth application-default login \
    --scopes https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform \
    --client-id-file=YOUR_CLIENT_JSON_FILE
  ```

- Set up ADC using service account impersonation.

  ```shell
  gcloud auth application-default login \
    --impersonate-service-account=SERVICE_ACCOUNT_EMAIL \
    --scopes=https://www.googleapis.com/auth/adwords,https://www.googleapis.com/auth/cloud-platform
  ```

When the `gcloud auth application-default` command completes, copy the
`PATH_TO_CREDENTIALS_JSON` file location printed to the console in the
following message. You will need this for a later step!

```
Credentials saved to file: [PATH_TO_CREDENTIALS_JSON]
```

#### Option 2: Configure credentials using the Google Ads API Python client library.

[Follow the instructions](https://developers.google.com/google-ads/api/docs/client-libs/python/)
to setup and configure the Google Ads API Python client library

If you have already done this and have a working `google-ads.yaml` , you can reuse this file!

In the utils.py file, change get_googleads_client() to use the load_from_storage() method.

### Configure your MCP Client

Add the server to your MCP client's configuration file. See [SETUP.md](SETUP.md) for detailed instructions for Claude Desktop, Claude Code CLI, and Gemini.

- Option 1: the Application Default Credentials method

    Replace `PATH_TO_CREDENTIALS_JSON` with the path you copied in the previous
    step.

    Replace `YOUR_PROJECT_ID` with the
    [project ID](https://support.google.com/googleapi/answer/7014113) of your
    Google Cloud project.



    ```json
    {
      "mcpServers": {
        "google-ads-mcp": {
          "command": "pipx",
          "args": [
            "run",
            "--spec",
            "git+https://github.com/SaiSatya16/google-ads-mcp-full.git",
            "google-ads-mcp"
          ],
          "env": {
            "GOOGLE_APPLICATION_CREDENTIALS": "PATH_TO_CREDENTIALS_JSON",
            "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
            "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN"
          }
        }
      }
    }
    ```

- Option 2: the Python client library method

    ```json
    {
      "mcpServers": {
        "google-ads-mcp": {
          "command": "pipx",
          "args": [
            "run",
            "--spec",
            "git+https://github.com/SaiSatya16/google-ads-mcp-full.git",
            "google-ads-mcp"
          ],
          "env": {
            "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
            "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN"
          }
        }
      }
    }
    ```

#### Login Customer Id

If your access to the customer account is through a manager account, you will
need to add the customer ID of the manager account to the settings file.

See [here](https://developers.google.com/google-ads/api/docs/concepts/call-structure#cid) for details.

The final file will look like this:

  ```json
  {
    "mcpServers": {
      "google-ads-mcp": {
        "command": "pipx",
        "args": [
          "run",
          "--spec",
          "git+https://github.com/SaiSatya16/google-ads-mcp-full.git",
          "google-ads-mcp"
        ],
        "env": {
          "GOOGLE_APPLICATION_CREDENTIALS": "PATH_TO_CREDENTIALS_JSON",
          "GOOGLE_PROJECT_ID": "YOUR_PROJECT_ID",
          "GOOGLE_ADS_DEVELOPER_TOKEN": "YOUR_DEVELOPER_TOKEN",
          "GOOGLE_ADS_LOGIN_CUSTOMER_ID": "YOUR_MANAGER_CUSTOMER_ID"
        }
      }
    }
  }
  ```


## Try it out

Restart your MCP client after configuration. Here are some sample prompts to get you started:

- Ask what the server can do:

  ```
  what can the ads-mcp server do?
  ```

- Ask about customers:

  ```
  what customers do I have access to?
  ```

- Ask about campaigns 

  ```
  How many active campaigns do I have?
  ```

  ```
  How is my campaign performance this week?
  ```

### Note about Customer ID

Your agent will need and ask for a customer id for most prompts. If you are 
moving between multiple customers, including the customer ID in the prompt may
be simpler.

```
How many active campaigns do I have for customer id 1234567890
```

- Create a campaign:

  ```
  Create a paused Search campaign called "Spring Sale" with $10/day budget
  ```

- Manage assets:

  ```
  Create a sitelink for "Free Shipping" pointing to /shipping and link it to my campaign
  ```

- Full PMax setup:

  ```
  Create a Performance Max campaign with headlines, descriptions, images, and sitelinks
  ```


## Contributing

Contributions welcome! See the [Contributing Guide](CONTRIBUTING.md).