# Copyright 2026 Google LLC.
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

"""Tools for generating file containing a list of resources and their fields."""

import utils
import json
import collections


def update_gaql_resource_file():
    """Fetches all Google Ads resources, and saves to a flat text file."""

    ga_service = utils.get_googleads_service("GoogleAdsFieldService")

    request = utils.get_googleads_type("SearchGoogleAdsFieldsRequest")

    # Query to select only the name attribute for ALL resources.
    query = "SELECT name WHERE category = 'RESOURCE'"
    request.query = query

    try:
        response = ga_service.search_google_ads_fields(request=request)
    except Exception as e:
        raise RuntimeError(f"API call to search_google_ads_fields failed: {e}")

    if response.total_results_count == 0:
        print("No GoogleAdsFields found.")
        return

    # Set to store unique resource names
    resource_names = set()

    for googleads_field in response:
        resource_names.add(googleads_field.name)

    # Sort the list of resources for consistent output
    output_list = sorted(list(resource_names))

    file_path = utils.get_gaql_resources_filepath()

    try:
        with open(file_path, "w") as file:
            file.write("\n".join(output_list) + "\n")
        print(f"Successfully updated resource file: {file_path}")
    except IOError as e:
        raise RuntimeError(f"Failed to write to file {file_path}: {e}")


if __name__ == "__main__":
    update_gaql_resource_file()
